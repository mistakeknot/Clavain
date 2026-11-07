#!/usr/bin/env python3
"""Run the characterization tests against a mutated copy of the tree.

Usage: mutcheck.py REL_FILE OLD NEW [TEST_ARG ...] [--count N]

Copies the directories the suite reads into a temp dir, replaces OLD with NEW
(exactly N times, default 1) in REL_FILE, and runs pytest there on TEST_ARGs
(default: the whole suite). An unmodified control run goes first and must pass
with at least one test run. A mutant is CAUGHT only when tests ran and reported
failures of their own; a collection or import failure, or zero tests, is ERROR,
never CAUGHT. Exit 0 when caught, 1 when the mutant survived, 2 on a usage,
control or execution error. The tracked tree is never edited.

`mutcheck.py --all` runs the standing mutation list (MUTANTS) and prints a
table; it exits 1 if any mutant survives.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
COPY = ["scripts", "config", ".claude-plugin", "tests/orchcompat", "tests/fixtures/roster"]

# (file, old, new, tests it must break, why it matters)
MUTANTS = [
    ("scripts/dispatch.sh", "dontAsk}", "acceptEdits}", "tests/orchcompat/test_dispatch_args.py",
     "claude seat permission mode"),
    ("scripts/dispatch.sh", "requires --producer-identity so producer and validator models",
     "needs --producer-identity so producer and validator models",
     "tests/orchcompat/test_dispatch_args.py", "producer-identity refusal text"),
    ("scripts/dispatch.sh", "Error: ic is required for --role dispatch", "Error: ic is needed for --role dispatch",
     "tests/orchcompat/test_dispatch_args.py", "missing-ic refusal"),
    ("scripts/sync-agent-instructions.py", "policy SHA256: {policy_hash}",
     "policy sha: {policy_hash}", "tests/orchcompat/test_contract_generator.py",
     "receipt line format"),
    ("scripts/check-instruction-contract.sh", "[--explicit]\" >&2\n  exit 2", "[--explicit]\" >&2\n  exit 1",
     "tests/orchcompat/test_contract_generator.py", "drift checker usage exit code"),
    ("config/roster-slugs.yaml", "slug: claude-opus-5-high\n", "slug: claude-opus-5-hxgh\n", "tests/orchcompat/test_roster_config.py",
     "a slug-table entry"),
    ("config/routing.yaml", "      role: main-integrator\n      backend: main\n      model: opus\n      reasoning_effort: high", "      role: main-integrator\n      backend: main\n      model: opus\n      reasoning_effort: low",
     "tests/orchcompat/test_role_resolution.py tests/orchcompat/test_dispatch_args.py",
     "pilot-opus profile effort"),
    # Main only (the behavior they break does not exist at the baseline):
    ("scripts/lib-dispatch-audit.sh",
     'observed=\'{"observed_model":"unknown","observed_source":"unavailable","observed_reason":"no request-bound model evidence for this transport or state","observed_model_matches_requested":null}\'',
     "observed='{}'", "tests/orchcompat/test_dispatch_args.py",
     "receipt loses every observed_* field (main only)"),
    ("scripts/lib-dispatch-audit.sh", "{usage_status, usage_basis, usage_note, tokens_in,",
     "{usage_basis, tokens_in,", "tests/orchcompat/test_dispatch_args.py",
     "receipt loses usage_status/usage_note (main only)"),
    ("scripts/dispatch.sh", "if _review_receipt_requested; then", "if false && _review_receipt_requested; then",
     "tests/orchcompat/test_dispatch_args.py",
     "scope refusal gone: --repo on a non-review role is accepted again (main only)"),
]


def copy_tree(root):
    for rel in COPY:
        src = REPO / rel
        if not src.exists():
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=True,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            shutil.copy2(src, dst)


def dispatch_generation():
    """baseline|main for the REAL tree, decided from its git history. The
    scratch copy has no .git, so it is handed the answer; the mutated files
    never take part in the choice."""
    sys.path.insert(0, str(HERE))
    import orchlib
    feats = [orchlib.dispatch_feature(f) for f in orchlib.DISPATCH_FEATURES]
    if len(set(feats)) != 1:
        raise SystemExit("mutcheck: tree is between baseline and main; set ORCHCOMPAT_DISPATCH_GEN")
    return "main" if feats[0] else "baseline"


def run_tests(root, tests):
    env = dict(os.environ, ORCHCOMPAT_DISPATCH_GEN=os.environ.get("ORCHCOMPAT_DISPATCH_GEN")
               or dispatch_generation())
    cmd = ["nice", "-n", "19", sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "--orchcompat-require-ic", *tests]
    return subprocess.run(cmd, cwd=root, capture_output=True, text=True, env=env)


def classify(r):
    out = r.stdout + r.stderr
    passed = re.search(r"(\d+) passed", out)
    failed = re.search(r"(\d+) failed", out)
    errors = re.search(r"(\d+) errors?\b", out)
    if errors and not failed:
        return "ERROR", "collection or setup error: " + (out.strip().splitlines() or [""])[-1]
    if failed and r.returncode != 0:
        names = re.findall(r"^FAILED (\S+)", out, re.M)
        return "FAILED", "; ".join(names[:2]) or "failed"
    if passed and r.returncode == 0:
        return "PASSED", ""
    return "ERROR", "no usable result (rc %d): %s" % (
        r.returncode, (out.strip().splitlines() or ["no output"])[-1])


def mutate(path, old, new, count):
    text = path.read_text()
    if old is None:  # drop the first non-comment mapping line of a yaml table
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.strip() and not line.lstrip().startswith("#") and ":" in line and i > 3 \
                    and line.startswith("  "):
                del lines[i]
                path.write_text("".join(lines))
                return None
        return "no mapping line found"
    if text.count(old) != count:
        return "%r found %d times in %s, expected %d" % (old, text.count(old), path.name, count)
    path.write_text(text.replace(old, new))
    return None


def check_one(file, old, new, tests, count=1):
    with tempfile.TemporaryDirectory(prefix="mutcheck-") as td:
        root = Path(td)
        copy_tree(root)
        control = classify(run_tests(root, tests))
        if control[0] != "PASSED":
            return "ERROR", "control run did not pass: %s" % (control[1],)
        problem = mutate(root / file, old, new, count)
        if problem:
            return "ERROR", problem
        return classify(run_tests(root, tests))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("file", nargs="?")
    ap.add_argument("old", nargs="?")
    ap.add_argument("new", nargs="?")
    ap.add_argument("tests", nargs="*", default=["tests/orchcompat"])
    ap.add_argument("--count", type=int, default=1)
    a = ap.parse_args()
    if a.all:
        bad = 0
        for file, old, new, tests, why in MUTANTS:
            kind, detail = check_one(file, old, new, tests.split())
            print("%-8s %-40s %s %s" % (kind if kind != "FAILED" else "CAUGHT", file, why,
                                        ("(" + detail + ")") if detail else ""))
            bad += kind != "FAILED"
        return 1 if bad else 0
    if not (a.file and a.old is not None and a.new is not None):
        ap.error("need FILE OLD NEW or --all")
    kind, detail = check_one(a.file, a.old, a.new, a.tests, a.count)
    label = {"FAILED": "CAUGHT", "PASSED": "SURVIVED"}.get(kind, kind)
    print("%s %s: %r -> %r %s" % (label, a.file, a.old, a.new, detail))
    return {"FAILED": 0, "PASSED": 1}.get(kind, 2)


if __name__ == "__main__":
    sys.exit(main())
