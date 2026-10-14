#!/usr/bin/env python3
"""Compare versions quoted in AGENTS.md and READMEs with the repo's manifests.

Drift is a warning: the script prints it and exits 0 unless --strict is given.
It never edits a document, so pinned text stays intact; the gardener fixes the
prose in the same commit that moves the pin.

Manifests read: package.json, go.mod, pyproject.toml (stdlib only).
Documents read: AGENTS.md and README.md at the root and beside each manifest.
A nested document answers to the nearest manifest, in its directory or above,
that pins the name. A root document answers to the root manifest when it pins
the name, otherwise to every nested manifest that does, so one quoting a
version that differs in any of them is flagged (move the sentence beside the
manifest it describes). Each warning names the disagreeing manifests.

A pin is compared only when the manifest spec is one plain version: 1.25.3,
v1.25.3, =1.25.3, ==1.25.3, or that version after ^ or ~ (the declared base).
A documented version agrees when it equals the pin or is a whole-component
prefix of it, or the other way round (1.25 for 1.25.3, 18 for ^18.3.1).
Everything else is listed as a note and never guessed at: ranges, comparators,
wildcards, || alternatives, prereleases, URLs, VCS refs, workspace:, tags, local
paths, versions with more than three parts, and a name pinned with different
specs in one manifest. Python package names are matched as written, ignoring case.

Usage: python3 -I docs-pins.py [--root DIR] [--strict] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", "node_modules", "vendor", ".venv", "dist", "build", "target", ".agent_sources"}
DOC_NAMES = ("AGENTS.md", "README.md")
VERSION_RE = r"\d+(?:\.\d+)*"
SPEC_RE = re.compile(r"(?:\^|~|==?)?\s*v?(\d+(?:\.\d+){0,2})")
MANIFESTS = ("package.json", "go.mod", "pyproject.toml")
READ_ERRORS = (OSError, ValueError, TypeError, AttributeError, KeyError)  # decode errors are ValueErrors

Pins = dict[str, list[str]]  # name -> specs


def find_manifests(root: Path) -> list[Path]:
    found = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        found.extend(Path(directory) / name for name in MANIFESTS if name in filenames)
    return sorted(found)


def is_reference(spec: str) -> bool:
    """URLs, VCS refs, local paths and protocol-prefixed specs carry no version to compare."""
    spec = spec.strip()
    return (not spec or spec.startswith(("@", ".", "/")) or "://" in spec
            or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", spec) is not None)


def add(pins: Pins, skipped: list[str], name: str, spec: str) -> None:
    """Record every spec for a name; `drop_ambiguous` decides afterwards which can be compared."""
    pins.setdefault(name, []).append(spec.strip())


def drop_ambiguous(pins: Pins, skipped: list[str]) -> None:
    """A name pinned with different specs (npm overrides, extras, same Go module basename) is not compared,
    whatever the specs are. A name left with one spec is compared only when it is one plain version."""
    for name in list(pins):
        specs = set(pins.pop(name))
        if len(specs) > 1:
            skipped.append(f"{name} pinned with differing specs: {', '.join(sorted(specs))}")
            continue
        spec = specs.pop()
        if is_reference(spec) or SPEC_RE.fullmatch(spec) is None:
            skipped.append(f"{name} {spec}".strip())
        else:
            pins[name] = [spec]


def package_json_pins(path: Path) -> tuple[Pins, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("package.json is not an object")
    pins: Pins = {}
    skipped: list[str] = []
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        table = data.get(key) or {}
        if not isinstance(table, dict):
            raise ValueError(f"{key} is not an object")
        for name, spec in table.items():
            add(pins, skipped, name, str(spec))
    drop_ambiguous(pins, skipped)
    return pins, skipped


def go_aliases(module: str) -> list[str]:
    parts = module.split("/")
    if re.fullmatch(r"v\d+", parts[-1]) and len(parts) > 1:
        parts = parts[:-1]
    return [module, parts[-1]]


def go_version(token: str) -> str:
    return token.removeprefix("v").removesuffix("+incompatible")


def go_mod_pins(path: Path) -> tuple[Pins, list[str]]:
    pins: Pins = {}
    skipped: list[str] = []
    required: dict[str, str] = {}
    replaced: dict[str, list[tuple[str | None, str | None]]] = {}  # module -> (old version, new version or None)
    block = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        fields = raw.split("//", 1)[0].split()
        if not fields:
            continue
        if block:
            if fields == [")"]:
                block = ""
                continue
            directive, entry = block, fields
        elif len(fields) == 2 and fields[1] == "(":
            block = fields[0]
            continue
        else:
            directive, entry = fields[0], fields[1:]
        if directive == "go" and entry:
            add(pins, skipped, "Go", go_version(entry[0]))
        elif directive == "require" and len(entry) >= 2:
            required[entry[0]] = go_version(entry[1])
        elif directive == "replace" and "=>" in entry:
            at = entry.index("=>")
            left, right = entry[:at], entry[at + 1:]
            if not left or not right:
                skipped.append("malformed replace directive")
                continue
            old = go_version(left[1]) if len(left) > 1 else None
            new = go_version(right[1]) if len(right) > 1 else None  # a local path has no version
            replaced.setdefault(left[0], []).append((old, new))
    for module, version in required.items():
        rules = replaced.get(module, [])
        rule = next((r for r in rules if r[0] == version), None) or next((r for r in rules if r[0] is None), None)
        if rule is not None:
            if rule[1] is None:
                skipped.append(f"{module} replaced by a local path")
                continue
            version = rule[1]
        for alias in go_aliases(module):
            add(pins, skipped, alias, version)
    drop_ambiguous(pins, skipped)
    return pins, skipped


def pyproject_pins(path: Path) -> tuple[Pins, list[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project") or {}
    if not isinstance(project, dict) or not isinstance(project.get("dependencies") or [], list):
        raise ValueError("unexpected [project] shape")
    specs = list(project.get("dependencies") or [])
    for group in (project.get("optional-dependencies") or {}).values():
        specs.extend(group)
    specs.extend(v for group in (data.get("dependency-groups") or {}).values() for v in group if isinstance(v, str))
    if not all(isinstance(spec, str) for spec in specs):
        raise ValueError("dependency entry is not a string")
    pins: Pins = {}
    skipped: list[str] = []
    for spec in specs:
        requirement = str(spec).split(";", 1)[0]  # drop the environment marker
        match = re.match(r"\s*([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*(.*)", requirement)
        if match and match.group(2).strip():
            add(pins, skipped, match.group(1), match.group(2).strip("() "))
    drop_ambiguous(pins, skipped)
    return pins, skipped


READERS = {"package.json": package_json_pins, "go.mod": go_mod_pins, "pyproject.toml": pyproject_pins}


def agrees(documented: str, spec: str) -> bool | None:
    """True/False for a plain version spec; None when the spec is not one."""
    match = SPEC_RE.fullmatch(spec.strip())
    if match is None:
        return None
    doc, pin = documented.split("."), match[1].split(".")
    n = min(len(doc), len(pin))
    return [int(p) for p in doc[:n]] == [int(p) for p in pin[:n]]


def mention_res(name: str) -> list[re.Pattern[str]]:
    # name (any case, optionally with .js), markdown marks, then @, space, ':' '=' or '(' and a version.
    return [
        re.compile(
            r"(?<![\w@/.-])" + re.escape(alias) + r"[`*_]*(?P<sep>@|\s+|\s*[:=(]\s*)[`*_]*v?(?P<ver>"
            + VERSION_RE + r")(?!\w|[-+]\w|\.\d)",
            re.IGNORECASE,
        )
        for alias in (name, name + ".js")
    ]


Manifest = tuple[str, str, Pins]  # (directory, label, pins)


def applicable(manifests: list[Manifest], scope_dir: str, name: str) -> list[tuple[str, list[str]]]:
    """Manifests that govern `name` for a document in scope_dir, as (label, specs).

    A nested document answers to the nearest ancestor directory that pins the
    name. A root document answers to the root manifest when it pins the name,
    otherwise to every nested manifest that does."""
    holders = [(d, label, pins[name]) for d, label, pins in manifests if name in pins]
    if scope_dir == ".":
        nearest = [h for h in holders if h[0] == "."]
        chosen = nearest or holders
    else:
        here = Path(scope_dir)
        reachable = [h for h in holders if h[0] == "." or Path(h[0]) == here or Path(h[0]) in here.parents]
        depth = max((0 if h[0] == "." else len(Path(h[0]).parts) for h in reachable), default=0)
        chosen = [h for h in reachable if (0 if h[0] == "." else len(Path(h[0]).parts)) == depth]
    return [(label, specs) for _, label, specs in chosen]


def doc_mentions(text: list[str], names: set[str]) -> list[tuple[int, str, str]]:
    found = []
    for name in sorted(names):
        patterns = mention_res(name)
        for number, line in enumerate(text, 1):
            for pattern in patterns:
                for match in pattern.finditer(line):
                    version, sep = match["ver"], match["sep"]
                    if "." not in version and "@" not in sep:
                        continue  # "react 2 times", not a version
                    found.append((number, name, version))
    return found


def check(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[dict[str, Any]] = []
    manifests: list[Manifest] = []
    skipped: list[str] = []
    for manifest in find_manifests(root):
        label = manifest.relative_to(root).as_posix()
        try:
            found, notes = READERS[manifest.name](manifest)
        except READ_ERRORS as exc:
            skipped.append(f"{label}: unreadable ({type(exc).__name__})")
            continue
        skipped.extend(f"{label}: {note}" for note in notes)
        manifests.append((manifest.parent.relative_to(root).as_posix(), label, found))

    names = {name for _, _, pins in manifests for name in pins}
    for scope_dir in sorted({".", *(d for d, _, _ in manifests)}):
        for doc_name in DOC_NAMES:
            doc = root / scope_dir / doc_name
            if not doc.is_file():
                continue
            text = doc.read_text(encoding="utf-8", errors="replace").splitlines()
            label = doc.relative_to(root).as_posix()
            for number, name, version in doc_mentions(text, names):
                bad = [(m, specs) for m, specs in applicable(manifests, scope_dir, name)
                       if not any(agrees(version, spec) is not False for spec in specs)]
                if bad:
                    warnings.append({"doc": label, "line": number, "name": name, "documented": version,
                                     "pinned": sorted({s for _, specs in bad for s in specs}),
                                     "manifests": sorted(m for m, _ in bad)})
    return warnings, skipped


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
    warnings, skipped = check(root)
    if args.json:
        print(json.dumps({"drift": warnings, "skipped": skipped}, indent=2))
    else:
        for w in warnings:
            print(f"WARNING {w['doc']}:{w['line']}: {w['name']} documented as {w['documented']}, "
                  f"manifest pins {', '.join(w['pinned'])} ({', '.join(w['manifests'])})")
        for note in skipped:
            print(f"NOTE skipped: {note}")
        print(f"docs-pins: {len(warnings)} drift warning(s), {len(skipped)} skipped spec(s)")
    return 1 if (warnings and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
