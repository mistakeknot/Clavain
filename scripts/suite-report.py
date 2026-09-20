#!/usr/bin/env python3
"""Summarise a test suite's real results, so no omission can read as coverage.

Sylveste-psey. Two defects motivate every rule here.

A skipped bats case prints as `ok N <name> # skip <reason>`, so a suite with 872
cases, 862 `ok` lines and 57 skips was reported as "862 ok" -- 57 omissions
counted as passes. Counts here are EXCLUSIVE: passed + failed + skipped ==
observed, always.

And for eleven days one red badge stood for two unrelated failures, so the real
one was invisible. A run that could not finish is therefore `partial` and fails;
an unknown count is reported as "unavailable", never as zero; and a nonzero
process exit fails regardless of what the output text says.

Exit codes: 0 pass, 1 fail, 3 warn (coverage changed but nothing broke).
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PASS, FAIL, WARN = 0, 1, 3
UNAVAILABLE = "unavailable"

ACCOUNTING_MODULE = "test_claude_usage"
ACCOUNTING_TOTAL = 29
ACCOUNTING_IC_FREE = "test_zaka_rejected_before_any_model_call"

TAP_PLAN = re.compile(r"^1\.\.(\d+)\s*$")
TAP_CASE = re.compile(r"^(not ok|ok)\s+(\d+)\s*(.*)$")
TAP_SKIP = re.compile(r"#\s*skip\s*(.*)$", re.IGNORECASE)
TAP_TODO = re.compile(r"#\s*todo\b", re.IGNORECASE)


class Result:
    def __init__(self):
        self.planned = UNAVAILABLE
        self.numbers: list[int] = []
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.skip_reasons: collections.Counter = collections.Counter()
        self.skipped_cases: dict[str, str] = {}
        self.failures: list[str] = []
        self.problems: list[str] = []
        self.bailed = False
        # False only when the report could not be READ or parsed at all. A
        # report that parsed and contained nothing has an observed count of 0,
        # which is a finding; "unavailable" is reserved for "could not look".
        self.readable = True

    @property
    def observed(self):
        return self.passed + self.failed + self.skipped


def parse_tap(text: str) -> Result:
    r = Result()
    if not text.strip():
        r.problems.append("report is empty")
        r.readable = False
        return r
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("Bail out!"):
            r.bailed = True
            r.problems.append("suite bailed out: " + stripped[len("Bail out!"):].strip())
            continue
        m = TAP_PLAN.match(stripped)
        if m:
            r.planned = int(m.group(1))
            continue
        # A diagnostic. bats emits several after each failure; they are not cases.
        if stripped.startswith("#"):
            continue
        m = TAP_CASE.match(stripped)
        if not m:
            continue
        status, number, rest = m.group(1), int(m.group(2)), m.group(3).strip()
        r.numbers.append(number)
        skip = TAP_SKIP.search(rest)
        name = rest.split("#", 1)[0].strip() if "#" in rest else rest
        if status == "ok" and skip:
            r.skipped += 1
            reason = skip.group(1).strip() or "(no reason given)"
            r.skip_reasons[reason] += 1
            r.skipped_cases[name] = reason
        elif status == "ok" and TAP_TODO.search(rest):
            # A TODO directive is not a pass either.
            r.skipped += 1
            r.skip_reasons["(todo)"] += 1
            r.skipped_cases[name] = "(todo)"
        elif status == "ok":
            r.passed += 1
        else:
            r.failed += 1
            r.failures.append(name)
    return r


def parse_junit(text: str) -> Result:
    r = Result()
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        r.problems.append(f"report could not be parsed: {exc}")
        r.readable = False
        return r
    # Leaf <testcase> elements only. Counting suite totals as well as their
    # children double-counts every case.
    cases = root.iter("testcase")
    n = 0
    for case in cases:
        n += 1
        name = case.get("name", "(unnamed)")
        cls = case.get("classname", "")
        ident = f"{cls}.{name}" if cls else name
        if case.find("failure") is not None or case.find("error") is not None:
            r.failed += 1
            r.failures.append(ident)
        elif case.find("skipped") is not None:
            r.skipped += 1
            el = case.find("skipped")
            reason = (el.get("message") or el.text or "").strip() or "(no reason given)"
            r.skip_reasons[reason] += 1
            r.skipped_cases[ident] = reason
        else:
            r.passed += 1
    r.planned = n if n else UNAVAILABLE
    r.numbers = list(range(1, n + 1))
    if n == 0:
        r.problems.append("report contains no test cases")
    return r


def completeness(r: Result) -> bool:
    if r.bailed or r.problems:
        return False
    if r.planned == UNAVAILABLE:
        r.problems.append("no plan line: cannot tell whether the run finished")
        return False
    if len(r.numbers) != len(set(r.numbers)):
        dupes = [n for n, c in collections.Counter(r.numbers).items() if c > 1]
        r.problems.append(f"duplicate case numbers: {sorted(dupes)[:5]}")
        return False
    if r.planned == 0:
        r.problems.append("plan is 1..0: nothing ran")
        return False
    if r.observed != r.planned:
        r.problems.append(
            f"partial report: planned {r.planned}, observed {r.observed}"
        )
        return False
    expected = set(range(1, r.planned + 1))
    if set(r.numbers) != expected:
        missing = sorted(expected - set(r.numbers))[:5]
        r.problems.append(f"missing case numbers: {missing}")
        return False
    return True


def compare_baseline(r: Result, baseline: dict) -> tuple[list[str], list[str]]:
    """Identity comparison, not a numeric ceiling.

    A count rots when a test file grows: `test_b3_calibration.bats` went from 37
    to 55 cases after the baseline run, and its setup() skips the whole file on a
    hosted runner, so the skip count rose by 18 without a single assertion being
    lost. `allowed_growth` names the reasons under which new identities are
    expected. Everything else is a finding.

    Known limit, stated rather than hidden: TAP carries no file name, so growth
    is matched by REASON, not by file. A new identity under an allowed reason is
    permitted even if it came from a different file sharing that reason.
    """
    errors, warnings = [], []
    base_cases = baseline.get("skipped_cases", {}) or {}
    base_reasons = baseline.get("reason_counts", {}) or {}
    growth_reasons = {
        spec.get("reason")
        for spec in (baseline.get("allowed_growth", {}) or {}).values()
        if isinstance(spec, dict) and spec.get("reason")
    }

    for reason, count in r.skip_reasons.items():
        if reason not in base_reasons:
            errors.append(f"new skip reason: {reason!r} ({count} case(s))")
            continue
        if count > base_reasons[reason] and reason not in growth_reasons:
            errors.append(
                f"skips increased for {reason!r}: {base_reasons[reason]} -> {count}"
            )

    new_ids = [i for i in r.skipped_cases if i not in base_cases]
    for ident in new_ids:
        reason = r.skipped_cases[ident]
        if reason in growth_reasons:
            continue
        if reason not in base_reasons:
            continue  # already reported as a new reason
        errors.append(f"newly skipped case: {ident!r} ({reason})")

    for reason, count in base_reasons.items():
        observed = r.skip_reasons.get(reason, 0)
        if observed < count:
            warnings.append(
                f"coverage improved for {reason!r}: {count} -> {observed}; "
                "baseline not rewritten automatically"
            )
    return errors, warnings


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--format", choices=["tap", "junit"], required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--exit-code", type=int, required=True)
    p.add_argument("--max-skipped", type=int, default=None)
    p.add_argument("--output-json")
    p.add_argument("--shell-skip-policy", action="store_true")
    p.add_argument("--actions-skip-baseline")
    p.add_argument("--require-claude-usage", action="store_true")
    args = p.parse_args(argv)

    src = Path(args.input)
    text = src.read_text(errors="replace") if src.exists() else ""
    r = parse_tap(text) if args.format == "tap" else parse_junit(text)
    complete = completeness(r)

    errors = list(r.problems)
    warnings: list[str] = []

    if args.exit_code != 0:
        errors.append(f"suite exited {args.exit_code}")
    if r.failed:
        errors.append(f"{r.failed} case(s) failed")

    if args.max_skipped is not None and isinstance(r.observed, int):
        if r.skipped > args.max_skipped:
            errors.append(f"{r.skipped} skips exceed the ceiling of {args.max_skipped}")

    if args.require_claude_usage:
        total = r.passed + r.failed + r.skipped
        module_skipped = [i for i in r.skipped_cases if ACCOUNTING_MODULE in i]
        module_failed = [i for i in r.failures if ACCOUNTING_MODULE in i]
        module_total = sum(
            1 for i in list(r.skipped_cases) + r.failures if ACCOUNTING_MODULE in i
        )
        # Passing cases are not individually named in TAP, so use the report's
        # own totals when the cohort is the whole report.
        seen = module_total if module_total else total
        if seen < ACCOUNTING_TOTAL:
            errors.append(
                f"{ACCOUNTING_MODULE}: expected {ACCOUNTING_TOTAL} executed cases, "
                f"saw {seen}; deselected coverage is not covered coverage"
            )
        if module_skipped:
            errors.append(f"{ACCOUNTING_MODULE}: {len(module_skipped)} case(s) skipped")
        if module_failed:
            errors.append(f"{ACCOUNTING_MODULE}: {len(module_failed)} case(s) failed")

    baseline_delta = None
    if args.actions_skip_baseline:
        baseline = json.loads(Path(args.actions_skip_baseline).read_text())
        berrors, bwarnings = compare_baseline(r, baseline)
        errors.extend(berrors)
        warnings.extend(bwarnings)
        baseline_delta = {"errors": berrors, "warnings": bwarnings}

    if args.shell_skip_policy:
        followup = (args.shell_skip_policy if isinstance(args.shell_skip_policy, str) else None)
        if r.skipped > 6:
            errors.append(f"{r.skipped} skips exceed the designated-host policy of 6")

    status = "fail" if (errors or not complete) else ("warn" if warnings else "pass")
    counts = f"passed: {r.passed}   failed: {r.failed}   skipped: {r.skipped}"
    if status == "fail" and r.failures:
        summary = f"{r.failures[0]}   {counts}"
    elif status == "fail":
        summary = f"{errors[0]}   {counts}" if errors else f"incomplete report   {counts}"
    elif status == "warn":
        summary = f"{warnings[0]}   {counts}"
    else:
        summary = counts

    doc = {
        "status": status,
        "summary": summary,
        "complete": complete,
        "planned": r.planned,
        "observed": r.observed if r.readable else UNAVAILABLE,
        "passed": r.passed,
        "failed": r.failed,
        "skipped": r.skipped,
        "skip_reasons": dict(r.skip_reasons.most_common()),
        "failures": r.failures,
        "exit_code": args.exit_code,
        "problems": errors,
        "warnings": warnings,
        "baseline_delta": baseline_delta,
    }
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(doc, indent=2) + "\n")
    print(summary)
    for line in errors + warnings:
        print("  " + line)
    return {"pass": PASS, "warn": WARN, "fail": FAIL}[status]


if __name__ == "__main__":
    sys.exit(main())
