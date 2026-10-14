#!/usr/bin/env python3
"""Compare versions quoted in AGENTS.md and READMEs with the repo's manifests.

Drift is a warning: the script prints it and exits 0 unless --strict is given.
It never edits a document, so pinned text stays intact; the gardener fixes the
prose in the same commit that moves the pin.

Manifests read: package.json, go.mod, pyproject.toml (stdlib only).
Documents read: AGENTS.md and README.md at the root and beside each manifest.

Usage: python3 -I docs-pins.py [--root DIR] [--strict] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", "node_modules", "vendor", ".venv", "dist", "build", "target", ".agent_sources"}
DOC_NAMES = ("AGENTS.md", "README.md")
VERSION_RE = re.compile(r"\d+(?:\.\d+)*(?:-[0-9A-Za-z.]+)?")


def find_manifests(root: Path) -> list[Path]:
    found = []
    for pattern in ("package.json", "go.mod", "pyproject.toml"):
        for path in sorted(root.rglob(pattern)):
            if not SKIP_DIRS.intersection(path.relative_to(root).parts):
                found.append(path)
    return found


def clean_version(spec: str) -> str | None:
    """Return the first concrete version in a spec such as ^1.2.3 or >=2.0, else None."""
    spec = spec.strip()
    if spec.startswith(("workspace:", "file:", "link:", "git", "http", "npm:")):
        return None
    match = re.search(r"\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z.]+)?", spec)
    return match.group(0) if match else None


def package_json_pins(path: Path) -> dict[str, set[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pins: dict[str, set[str]] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, spec in (data.get(key) or {}).items():
            version = clean_version(str(spec))
            if version:
                pins.setdefault(name, set()).add(version)
    return pins


def go_aliases(module: str) -> list[str]:
    parts = module.split("/")
    if re.fullmatch(r"v\d+", parts[-1]) and len(parts) > 1:
        parts = parts[:-1]
    return [module, parts[-1]]


def go_mod_pins(path: Path) -> dict[str, set[str]]:
    pins: dict[str, set[str]] = {}
    in_block = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if line.startswith("go ") or line.startswith("toolchain go"):
            version = clean_version(line.split()[-1].removeprefix("go"))
            if version:
                pins.setdefault("Go", set()).add(version)
            continue
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        entry = line.removeprefix("require ").strip() if (in_block or line.startswith("require ")) else ""
        fields = entry.split()
        if len(fields) >= 2:
            version = clean_version(fields[1])
            if version:
                for alias in go_aliases(fields[0]):
                    pins.setdefault(alias, set()).add(version)
    return pins


def pyproject_pins(path: Path) -> dict[str, set[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    specs = list((data.get("project") or {}).get("dependencies") or [])
    for group in ((data.get("project") or {}).get("optional-dependencies") or {}).values():
        specs.extend(group)
    specs.extend(v for group in (data.get("dependency-groups") or {}).values() for v in group if isinstance(v, str))
    pins: dict[str, set[str]] = {}
    for spec in specs:
        match = re.match(r"\s*([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*(.*)", spec)
        if match:
            version = clean_version(match.group(2))
            if version:
                pins.setdefault(match.group(1), set()).add(version)
    return pins


READERS = {"package.json": package_json_pins, "go.mod": go_mod_pins, "pyproject.toml": pyproject_pins}


def compatible(documented: str, pinned: str) -> bool:
    """True when one version is a whole-component prefix of the other (1.25 vs 1.25.3)."""
    a, b = documented.split("."), pinned.split(".")
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def mention_re(name: str) -> re.Pattern[str]:
    # name, optional markdown marks, then @, space, ':' '=' or '(' and a dotted version.
    return re.compile(
        r"(?<![\w@/.-])" + re.escape(name) + r"[`*_]*(?:@|\s+|\s*[:=(]\s*)v?(" + VERSION_RE.pattern + r")(?![\w])"
    )


def check(root: Path) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    manifests = find_manifests(root)
    pins: dict[str, dict[str, set[str]]] = {}  # dir -> name -> versions
    for manifest in manifests:
        found = READERS[manifest.name](manifest)
        scope = pins.setdefault(str(manifest.parent.relative_to(root)), {})
        for name, versions in found.items():
            scope.setdefault(name, set()).update(versions)
    root_scope = pins.get(".", {})
    for scope_dir, scope_pins in sorted(pins.items()):
        for doc_name in DOC_NAMES:
            doc = root / scope_dir / doc_name
            if not doc.is_file():
                continue
            visible = {**root_scope, **scope_pins}
            text = doc.read_text(encoding="utf-8", errors="replace").splitlines()
            for name, versions in visible.items():
                pattern = mention_re(name)
                for number, line in enumerate(text, 1):
                    for found_version in pattern.findall(line):
                        if "." not in found_version and "@" not in line:
                            continue
                        if not any(compatible(found_version, pinned) for pinned in versions):
                            warnings.append({
                                "doc": str(doc.relative_to(root)),
                                "line": number,
                                "name": name,
                                "documented": found_version,
                                "pinned": sorted(versions),
                            })
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any drift is found")
    parser.add_argument("--json", action="store_true", help="print warnings as JSON")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"docs-pins: not a directory: {root}", file=sys.stderr)
        return 2
    warnings = check(root)
    if args.json:
        print(json.dumps({"drift": warnings}, indent=2))
    else:
        for w in warnings:
            print(f"WARNING {w['doc']}:{w['line']}: {w['name']} documented as {w['documented']}, "
                  f"manifest pins {', '.join(w['pinned'])}")
        print(f"docs-pins: {len(warnings)} drift warning(s)")
    return 1 if (warnings and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
