#!/usr/bin/env python3
"""Select the test files a pull request needs, or fall back to the full suite.

Pilot for affected-only pull-request checks. Rules:

* Only pull-request runs may use the affected selection. Any other event
  (push to main, merge head, schedule, manual run) always selects the full
  suite, and so does a missing base ref.
* Anything this tool cannot map falls back to the full suite. No check is
  deleted; the full suite stays the required check on the merge head.
* An affected-only run is never qualification evidence.

Usage:
  affected-checks.py --event pull_request --base origin/main [--head HEAD]
  affected-checks.py --event pull_request --files a.py b.sh      # explicit list

Output (JSON on stdout): {"mode": "full"|"affected", "reason": str,
"pytest": [paths], "bats": [paths], "changed": [paths]}.
Exit code is 0 unless the tool itself failed; on any internal error it prints a
full-suite selection and exits 0, so a tool bug can only widen the run.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Changing any of these can change every test: always the full suite.
FULL_PREFIXES = (
    ".github/", ".claude-plugin/", ".codex/", "config/", "schemas/",
    "hooks/hooks.json", "tests/fixtures/", "tests/structural/conftest.py",
    "tests/structural/helpers.py", "tests/structural/selector_helpers.py",
    "tests/shell/helper", "tests/shell/test_helper", "units/",
)
FULL_NAMES = {
    "Makefile", "agent-rig.json", "upstreams.json", "kimi.plugin.json",
    "pyproject.toml", "uv.lock", "package.json", "package-lock.json",
    ".gitattributes", ".gitignore", ".tldrsignore", "RK-CI-GUARD.md",
}
FULL_SUFFIXES = ("run-tests.sh", ".bash", "conftest.py", "pyproject.toml",
                 "uv.lock", "package.json", "package-lock.json")

# Directories read by many glob-based tests, or built as a package (the Go CLI):
# a textual citation search cannot prove coverage of these, so any change under
# them selects the full suite.
FULL_DIRS = ("skills/", "commands/", "agents/", "cmd/", "hooks/", "galiana/",
             "adapters/", "bin/")

GENERIC_NAMES = {"main.go", "SKILL.md", "README.md", "__init__.py", "index.md",
                 "CHANGELOG.md", "plugin.json", "SKILL.md.tmpl"}



def full(reason: str, changed: list[str]) -> dict:
    return {"mode": "full", "reason": reason, "pytest": [], "bats": [],
            "changed": changed}


def is_test(path: str) -> bool:
    return path.startswith("tests/") or path.startswith("scripts/tests/")


def classify_test(path: str) -> str | None:
    if path.endswith(".bats"):
        return "bats"
    if path.endswith(".py") and Path(path).name.startswith("test_"):
        return "pytest"
    return None


def all_tests() -> list[str]:
    """Tracked test files only (never an installed dependency's tests)."""
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], check=True,
                         capture_output=True, text=True).stdout.split("\n")
    return sorted(r for r in out if r and (is_test(r) or r.startswith("scripts/tests/"))
                  and "node_modules" not in r and classify_test(r))


def _needles(path: str) -> tuple[str, set[str]]:
    """The repo path (substring match) and the bare names (token match)."""
    base = Path(path).name
    stem = Path(path).stem
    names = set()
    # A bare basename is a weak signal: skip short or generic names.
    if len(base) >= 6 and base not in GENERIC_NAMES:
        names.add(base)
        if len(stem) >= 8 and stem != base:
            names.add(stem)
    return path, names


def _text_files() -> dict[str, tuple[str, set[str]]]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], check=True,
                         capture_output=True, text=True).stdout.split("\n")
    texts = {}
    for rel in out:
        if not rel or "node_modules" in rel:
            continue
        p = ROOT / rel
        try:
            if p.stat().st_size > 2_000_000:
                continue
            text = p.read_text(errors="replace")
        except OSError:
            continue
        toks = {t.rstrip(".") for t in re.findall(r"[\w.-]+", text)}
        toks |= set(re.findall(r"\w+", text))  # may over-match; only widens
        texts[rel] = (text, toks)
    return texts


def _cites(entry: tuple[str, set[str]], needles: tuple[str, set[str]]) -> bool:
    text, toks = entry
    path, names = needles
    return path in text or not names.isdisjoint(toks)


def consumers_of_test(path: str, tests: list[str]) -> set[str]:
    """Test files that cite a changed test module, transitively (shared
    helpers imported by other tests)."""
    texts = _text_files()
    seen = {path}
    frontier = [path]
    while frontier:
        needles = _needles(frontier.pop())
        for t in tests:
            if t not in seen and t in texts and _cites(texts[t], needles):
                seen.add(t)
                frontier.append(t)
    return seen


def select(changed: list[str]) -> dict:
    """Affected mode is deliberately narrow, because a citation search cannot
    prove coverage when tests scan files by glob or read documentation. It
    covers only pull requests that change test modules and nothing else: every
    structural pytest file runs (several scan the whole test tree), plus the
    changed bats files and the tests that import a changed module. Every other
    path (code, docs, config, deletions) selects the full suite."""
    if not changed:
        return full("no changed files listed", changed)
    tests = all_tests()
    chosen: set[str] = set()
    for path in changed:
        name = Path(path).name
        if (path in FULL_NAMES or name in FULL_NAMES
                or path.startswith(FULL_PREFIXES)
                or path.endswith(FULL_SUFFIXES)):
            return full(f"config or shared test infrastructure changed: {path}",
                        changed)
        if not (ROOT / path).exists():
            return full(f"file deleted or renamed: {path}", changed)
        if not is_test(path) or not classify_test(path) or path not in tests:
            return full(f"not a plain test module: {path}", changed)
        chosen |= consumers_of_test(path, tests)
    chosen |= {t for t in tests if classify_test(t) == "pytest"
               and t.startswith("tests/structural/")}
    return {
        "mode": "affected",
        "reason": "only test modules changed",
        "pytest": sorted(t for t in chosen if classify_test(t) == "pytest"),
        "bats": sorted(t for t in chosen if classify_test(t) == "bats"),
        "changed": changed,
    }


def git_changed(base: str, head: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-status", "--no-renames",
         f"{base}...{head}"], check=True, capture_output=True, text=True).stdout
    return [line.split("\t", 1)[1] for line in out.splitlines() if "\t" in line]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", required=True)
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--files", nargs="*")
    a = ap.parse_args()
    try:
        if a.event != "pull_request":
            res = full(f"event {a.event} is not a pull request", [])
        elif a.files is not None:
            res = select(a.files)
        elif not a.base:
            res = full("no base ref given", [])
        else:
            res = select(git_changed(a.base, a.head))
    except Exception as exc:  # a tool failure may only widen the run
        res = full(f"selector error: {exc}", [])
    json.dump(res, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
