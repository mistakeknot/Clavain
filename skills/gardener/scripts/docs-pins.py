#!/usr/bin/env python3
"""Compare versions quoted in AGENTS.md and READMEs with the repo's manifests.

Drift is a warning: the script prints it and exits 0 unless --strict is given.
It never edits a document, so pinned text stays intact; the gardener fixes the
prose in the same commit that moves the pin.

Manifests read: package.json, go.mod, pyproject.toml (stdlib only).
Documents read: AGENTS.md and README.md at the root and beside each manifest.
A root document is checked against every manifest in the repository; a nested
document is checked against the manifests in its own directory and above.

A documented version agrees with a manifest spec when it satisfies the spec
(exact, ^, ~, ~=, >=, <, ==x.*, 18.x, ranges joined by space, comma or ||) or
is a whole-component prefix of the spec's lower bound (1.25 vs 1.25.3).
Specs it cannot evaluate (URLs, workspace:, tags, local paths) are skipped and
listed as notes, never guessed at.

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
VERSION_RE = r"\d+(?:\.\d+)*(?:-[0-9A-Za-z.]+)?"
TOKEN_RE = re.compile(
    r"(?P<op>\^|~>|~=|~|===|==|!=|>=|<=|>|<|=)?\s*v?"
    r"(?P<ver>\d+(?:\.(?:\d+|[xX*]))*|[xX*])"
)
LOWER_OPS = {"", "=", "==", "===", "^", "~", "~>", "~=", ">=", ">"}
READ_ERRORS = (OSError, ValueError, UnicodeDecodeError)  # JSON/TOML decode errors are ValueErrors

Pins = dict[str, list[str]]  # name -> specs


def find_manifests(root: Path) -> list[Path]:
    found = []
    for pattern in ("package.json", "go.mod", "pyproject.toml"):
        for path in sorted(root.rglob(pattern)):
            if not SKIP_DIRS.intersection(path.relative_to(root).parts):
                found.append(path)
    return found


def is_reference(spec: str) -> bool:
    """URLs, VCS refs, local paths and protocol-prefixed specs carry no version to compare."""
    spec = spec.strip()
    return (not spec or spec.startswith(("@", ".", "/")) or "://" in spec
            or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", spec) is not None)


def add(pins: Pins, skipped: list[str], name: str, spec: str) -> None:
    if is_reference(spec) or not any(TOKEN_RE.search(alt) for alt in spec.split("||")):
        skipped.append(f"{name} {spec.strip()}".strip())
    else:
        pins.setdefault(name, []).append(spec.strip())


def package_json_pins(path: Path) -> tuple[Pins, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pins: Pins = {}
    skipped: list[str] = []
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, spec in (data.get(key) or {}).items():
            add(pins, skipped, name, str(spec))
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
    replaced: dict[str, tuple[str | None, str | None]] = {}  # module -> (old version, new version or None)
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
        elif directive == "toolchain" and entry:
            add(pins, skipped, "Go", go_version(entry[0].removeprefix("go")))
        elif directive == "require" and len(entry) >= 2:
            required[entry[0]] = go_version(entry[1])
        elif directive == "replace" and "=>" in entry:
            at = entry.index("=>")
            left, right = entry[:at], entry[at + 1:]
            old = go_version(left[1]) if len(left) > 1 else None
            new = go_version(right[1]) if len(right) > 1 else None  # a local path has no version
            replaced[left[0]] = (old, new)
    for module, version in required.items():
        if module in replaced:
            old, new = replaced[module]
            if old is not None and old != version:
                pass  # replacement targets another version; the requirement stands
            elif new is None:
                skipped.append(f"{module} replaced by a local path")
                continue
            else:
                version = new
        for alias in go_aliases(module):
            add(pins, skipped, alias, version)
    return pins, skipped


def pyproject_pins(path: Path) -> tuple[Pins, list[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project") or {}
    specs = list(project.get("dependencies") or [])
    for group in (project.get("optional-dependencies") or {}).values():
        specs.extend(group)
    specs.extend(v for group in (data.get("dependency-groups") or {}).values() for v in group if isinstance(v, str))
    pins: Pins = {}
    skipped: list[str] = []
    for spec in specs:
        requirement = str(spec).split(";", 1)[0]  # drop the environment marker
        match = re.match(r"\s*([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*(.*)", requirement)
        if match and match.group(2).strip():
            add(pins, skipped, match.group(1), match.group(2).strip("() "))
    return pins, skipped


READERS = {"package.json": package_json_pins, "go.mod": go_mod_pins, "pyproject.toml": pyproject_pins}


def parts_of(version: str) -> list[int | None]:
    """'1.2.x' -> [1, 2, None]; None marks a wildcard component."""
    return [None if p in ("x", "X", "*") else int(p) for p in version.split(".")]


def padded(values: list[int], size: int) -> tuple[int, ...]:
    return tuple(values + [0] * (size - len(values)))


def prefix_compatible(documented: list[int | None], pinned: list[int | None]) -> bool:
    n = min(len(documented), len(pinned))
    return documented[:n] == pinned[:n]


def satisfies(doc: list[int | None], op: str, ver: list[int | None]) -> bool:
    if None in ver:  # 18.x / 2.0.* / *: match on the concrete prefix
        prefix = ver[: ver.index(None)]
        return prefix_compatible(doc, prefix)
    size = max(len(doc), len(ver), 3)
    d = padded([int(p or 0) for p in doc], size)
    v = padded([int(p or 0) for p in ver if p is not None], size)
    n = len(ver)
    if op in ("", "=", "==", "==="):
        return d == v
    if op == "!=":
        return d != v
    if op == ">=":
        return d >= v
    if op == ">":
        return d > v
    if op == "<=":
        return d <= v
    if op == "<":
        return d < v
    concrete = [int(p) for p in ver if p is not None]
    if op == "^":
        index = next((i for i, p in enumerate(concrete) if p), n - 1)
        upper = concrete[:index] + [concrete[index] + 1]
    elif op == "~=" and n > 1:
        upper = concrete[: n - 2] + [concrete[n - 2] + 1]
    elif op == "~=":
        return d >= v
    else:  # ~ and ~>
        upper = [concrete[0] + 1] if n == 1 else [concrete[0], concrete[1] + 1]
    return v <= d < padded(upper, size)


def agrees(documented: str, spec: str) -> bool | None:
    """True/False when the spec can be evaluated; None when it cannot."""
    doc = parts_of(documented)
    evaluated = False
    for alternative in spec.split("||"):
        tokens = list(TOKEN_RE.finditer(alternative))
        if not tokens:
            continue
        evaluated = True
        if all(satisfies(doc, t["op"] or "", parts_of(t["ver"])) for t in tokens):
            return True
        lower = next((t for t in tokens if (t["op"] or "") in LOWER_OPS and "x" not in t["ver"].lower()
                      and "*" not in t["ver"]), None)
        if lower and prefix_compatible(doc, parts_of(lower["ver"])):
            return True
    return False if evaluated else None


def mention_res(name: str) -> list[re.Pattern[str]]:
    # name (any case, optionally with .js), markdown marks, then @, space, ':' '=' or '(' and a version.
    return [
        re.compile(
            r"(?<![\w@/.-])" + re.escape(alias) + r"[`*_]*(?P<sep>@|\s+|\s*[:=(]\s*)[`*_]*v?(?P<ver>"
            + VERSION_RE + r")(?![\w])",
            re.IGNORECASE,
        )
        for alias in (name, name + ".js")
    ]


def doc_mentions(text: list[str], pins: Pins) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for name, specs in pins.items():
        patterns = mention_res(name)
        for number, line in enumerate(text, 1):
            for pattern in patterns:
                for match in pattern.finditer(line):
                    version, sep = match["ver"], match["sep"]
                    if "." not in version and "@" not in sep:
                        continue  # "react 2 times", not a version
                    if not any(agrees(version, spec) is not False for spec in specs):
                        found.append({"line": number, "name": name, "documented": version, "pinned": sorted(set(specs))})
    return found


def check(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[dict[str, Any]] = []
    scopes: dict[str, Pins] = {}
    skipped: list[str] = []
    for manifest in find_manifests(root):
        label = manifest.relative_to(root).as_posix()
        try:
            found, notes = READERS[manifest.name](manifest)
        except READ_ERRORS as exc:
            skipped.append(f"{label}: unreadable ({type(exc).__name__})")
            continue
        skipped.extend(f"{label}: {note}" for note in notes)
        scope = scopes.setdefault(manifest.parent.relative_to(root).as_posix(), {})
        for name, specs in found.items():
            scope.setdefault(name, []).extend(specs)

    everything: Pins = {}
    for scope in scopes.values():
        for name, specs in scope.items():
            everything.setdefault(name, []).extend(specs)

    for scope_dir in sorted({".", *scopes}):
        if scope_dir == ".":
            visible = everything
        else:
            visible = {}
            chain = [Path(*Path(scope_dir).parts[: i + 1]).as_posix() for i in range(len(Path(scope_dir).parts))]
            for ancestor in [".", *chain]:
                visible.update(scopes.get(ancestor, {}))
        for doc_name in DOC_NAMES:
            doc = root / scope_dir / doc_name
            if not doc.is_file():
                continue
            text = doc.read_text(encoding="utf-8", errors="replace").splitlines()
            label = doc.relative_to(root).as_posix()
            warnings.extend({"doc": label, **w} for w in doc_mentions(text, visible))
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
                  f"manifest pins {', '.join(w['pinned'])}")
        for note in skipped:
            print(f"NOTE skipped: {note}")
        print(f"docs-pins: {len(warnings)} drift warning(s), {len(skipped)} skipped spec(s)")
    return 1 if (warnings and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
