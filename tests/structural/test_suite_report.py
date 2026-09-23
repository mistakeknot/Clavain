"""The summarizer must never let a skip, a truncation, or a green exit read as coverage.

Sylveste-psey: the Mac baseline was reported as "872 tests, 862 ok" when 57 of
those ok lines carried `# skip`, so 805 real passes were reported as 862. And a
red Tier 1 hid a red Tier 2 for eleven days because one badge stood for both.
This CLI exists so counts are exclusive, omissions are named, and an incomplete
run can never look like a complete one.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "suite-report.py"

PASS, FAIL, WARN = 0, 1, 3


def report(tmp_path, text, *, fmt="tap", exit_code=0, extra=()):
    src = tmp_path / ("input.tap" if fmt == "tap" else "input.xml")
    src.write_text(text)
    out = tmp_path / "summary.json"
    proc = subprocess.run(
        [sys.executable, str(CLI), "--format", fmt, "--input", str(src),
         "--exit-code", str(exit_code), "--output-json", str(out), *extra],
        capture_output=True, text=True, timeout=120,
    )
    data = json.loads(out.read_text()) if out.exists() else None
    return proc, data


def tap(*cases, plan=None):
    n = len(cases) if plan is None else plan
    return "\n".join([f"1..{n}", *cases]) + "\n"


def test_cli_exists():
    """Anti-vacuity: every test below shells out to this file."""
    assert CLI.is_file(), f"{CLI} missing — the tests below would all error identically"


def test_skips_are_excluded_from_passed(tmp_path):
    """The defect this whole file exists for: `ok N ... # skip` is NOT a pass."""
    proc, d = report(tmp_path, tap(
        "ok 1 real",
        "ok 2 held back # skip yq not available (standalone CI)",
        "ok 3 also held back # skip gawk required for JSONL parser tests",
    ))
    assert proc.returncode == PASS, proc.stdout + proc.stderr
    assert d["passed"] == 1, f"skips counted as passes: {d}"
    assert d["skipped"] == 2
    assert d["failed"] == 0
    assert d["passed"] + d["failed"] + d["skipped"] == d["observed"]
    assert d["skip_reasons"]["yq not available (standalone CI)"] == 1


def test_a_nonzero_exit_fails_even_when_every_line_is_ok(tmp_path):
    """Output text never overrides a process exit. A suite that printed all-ok and
    then died in teardown is not a pass."""
    proc, d = report(tmp_path, tap("ok 1 a", "ok 2 b"), exit_code=1)
    assert proc.returncode == FAIL
    assert d["status"] == "fail"
    assert d["exit_code"] == 1


def test_truncated_output_is_partial_and_fails(tmp_path):
    """Fewer records than planned means we could not look, which is not nothing."""
    proc, d = report(tmp_path, tap("ok 1 a", "ok 2 b", plan=10))
    assert proc.returncode == FAIL
    assert d["complete"] is False
    assert d["planned"] == 10 and d["observed"] == 2
    assert "partial" in d["summary"].lower() or "incomplete" in d["summary"].lower()


def test_empty_input_is_unavailable_not_zero(tmp_path):
    """An empty report is an unknown count, never a clean zero."""
    proc, d = report(tmp_path, "")
    assert proc.returncode == FAIL
    assert d["planned"] == "unavailable"
    assert d["complete"] is False


def test_an_empty_plan_is_not_a_silent_pass(tmp_path):
    """`1..0` means nothing ran. That is a finding, not success."""
    proc, d = report(tmp_path, "1..0\n")
    assert proc.returncode == FAIL
    assert d["observed"] == 0


def test_bail_out_fails(tmp_path):
    proc, d = report(tmp_path, "1..5\nok 1 a\nBail out! harness died\n")
    assert proc.returncode == FAIL
    assert d["complete"] is False
    assert "bail" in d["summary"].lower()


def test_duplicate_and_missing_numbers_are_rejected(tmp_path):
    proc, d = report(tmp_path, tap("ok 1 a", "ok 1 a again", "ok 3 c"))
    assert proc.returncode == FAIL
    assert d["complete"] is False


def test_diagnostics_are_not_counted_as_cases(tmp_path):
    """bats emits `# (in test file ...)` lines after a failure."""
    proc, d = report(tmp_path, tap(
        "not ok 1 broken",
        "# (in test file tests/shell/x.bats, line 11)",
        "#   `[ \"$status\" -eq 0 ]' failed",
        "ok 2 fine",
    ), exit_code=1)
    assert d["observed"] == 2, f"diagnostics counted as cases: {d}"
    assert d["failed"] == 1


def test_failure_summary_leads_with_the_first_failed_name(tmp_path):
    """The rig reader truncates its headline, so the actionable name must come first."""
    proc, d = report(tmp_path, tap(
        "ok 1 fine",
        "not ok 2 the name that must survive truncation",
        "not ok 3 another",
    ), exit_code=1)
    assert proc.returncode == FAIL
    assert d["summary"].startswith("the name that must survive truncation"), d["summary"]
    assert "passed: 1" in d["summary"] and "failed: 2" in d["summary"]
    assert d["failures"][0] == "the name that must survive truncation"


def test_the_real_mac_histogram_is_reported_exclusively(tmp_path):
    """The measured 872/862-ok/10-not-ok/57-skip run yields 805 passed."""
    cases = []
    n = 0
    for reason, count in [("yq not available (standalone CI)", 41),
                          ("gawk required for JSONL parser tests", 10),
                          ("interphase not installed", 5),
                          ("Intercore calibration candidate not available", 1)]:
        for _ in range(count):
            n += 1
            cases.append(f"ok {n} skipped case {n} # skip {reason}")
    for _ in range(805):
        n += 1
        cases.append(f"ok {n} passing case {n}")
    for _ in range(10):
        n += 1
        cases.append(f"not ok {n} failing case {n}")
    proc, d = report(tmp_path, tap(*cases, plan=872), exit_code=1)
    assert d["planned"] == 872 and d["observed"] == 872
    assert (d["passed"], d["failed"], d["skipped"]) == (805, 10, 57), d
    assert d["skip_reasons"] == {
        "yq not available (standalone CI)": 41,
        "gawk required for JSONL parser tests": 10,
        "interphase not installed": 5,
        "Intercore calibration candidate not available": 1,
    }


def test_junit_aggregates_leaf_cases_only(tmp_path):
    """Counting suite totals AND their children double-counts every case."""
    xml = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="outer" tests="3" failures="1" skipped="1">
    <testcase name="a" classname="m"/>
    <testcase name="b" classname="m"><failure message="boom"/></testcase>
    <testcase name="c" classname="m"><skipped message="no ic"/></testcase>
  </testsuite>
</testsuites>
"""
    proc, d = report(tmp_path, xml, fmt="junit", exit_code=1)
    assert d["observed"] == 3, f"leaf aggregation wrong: {d}"
    assert (d["passed"], d["failed"], d["skipped"]) == (1, 1, 1)
    assert d["failures"] == ["m.b"] or d["failures"] == ["b"], d["failures"]


def test_junit_errors_count_as_failures(tmp_path):
    xml = """<?xml version="1.0"?>
<testsuites><testsuite name="s" tests="1">
  <testcase name="a" classname="m"><error message="exploded"/></testcase>
</testsuite></testsuites>
"""
    proc, d = report(tmp_path, xml, fmt="junit", exit_code=1)
    assert d["failed"] == 1 and d["passed"] == 0


def test_malformed_junit_is_unavailable_not_zero(tmp_path):
    proc, d = report(tmp_path, "<testsuites", fmt="junit")
    assert proc.returncode == FAIL
    assert d["observed"] == "unavailable" or d["complete"] is False


def test_require_claude_usage_rejects_a_short_or_skipped_cohort(tmp_path):
    """The accounting cohort must have actually EXECUTED, not been deselected."""
    short = """<?xml version="1.0"?>
<testsuites><testsuite name="s" tests="1">
  <testcase name="test_zaka_rejected_before_any_model_call" classname="structural.test_claude_usage"/>
</testsuite></testsuites>
"""
    proc, d = report(tmp_path, short, fmt="junit", extra=["--require-claude-usage"])
    assert proc.returncode == FAIL, "a 1-case accounting cohort passed the required-module check"
    assert "claude_usage" in json.dumps(d)


def test_require_claude_usage_accepts_the_full_executed_cohort(tmp_path):
    cases = "".join(
        f'<testcase name="case_{i}" classname="structural.test_claude_usage"/>' for i in range(28)
    ) + '<testcase name="test_zaka_rejected_before_any_model_call" classname="structural.test_claude_usage"/>'
    xml = f'<?xml version="1.0"?><testsuites><testsuite name="s" tests="29">{cases}</testsuite></testsuites>'
    proc, d = report(tmp_path, xml, fmt="junit", extra=["--require-claude-usage"])
    assert proc.returncode == PASS, json.dumps(d)[:600]


def test_actions_baseline_unchanged_set_does_not_warn(tmp_path):
    base = tmp_path / "base.json"
    base.write_text(json.dumps({
        "run_id": "x", "plan": 2, "skipped": 1,
        "reason_counts": {"yq not available (standalone CI)": 1},
        "skipped_cases": {"held": "yq not available (standalone CI)"},
        "allowed_growth": {},
    }))
    proc, d = report(tmp_path, tap(
        "ok 1 fine", "ok 2 held # skip yq not available (standalone CI)"
    ), extra=["--actions-skip-baseline", str(base)])
    assert proc.returncode == PASS, json.dumps(d)[:600]
    assert d.get("baseline_delta") in (None, {}, []) or d["status"] == "pass"


def test_actions_baseline_flags_a_new_reason(tmp_path):
    base = tmp_path / "base.json"
    base.write_text(json.dumps({
        "run_id": "x", "plan": 2, "skipped": 1,
        "reason_counts": {"yq not available (standalone CI)": 1},
        "skipped_cases": {"held": "yq not available (standalone CI)"},
        "allowed_growth": {},
    }))
    proc, d = report(tmp_path, tap(
        "ok 1 held # skip yq not available (standalone CI)",
        "ok 2 newly held # skip jsonschema not installed",
    ), extra=["--actions-skip-baseline", str(base)])
    assert proc.returncode == FAIL, "a brand-new skip reason was accepted"
    assert "jsonschema not installed" in json.dumps(d)


def test_actions_baseline_allows_declared_growth_in_one_file(tmp_path):
    """A file that gains cases under an ALREADY-ALLOWED reason is not a coverage
    loss. This is the test_b3_calibration.bats case that made the old numeric
    274 cap unmeetable."""
    base = tmp_path / "base.json"
    base.write_text(json.dumps({
        "run_id": "x", "plan": 2, "skipped": 1,
        "reason_counts": {"lib-interspect.sh not found": 1},
        "skipped_cases": {"b3 case one": "lib-interspect.sh not found"},
        "allowed_growth": {
            "tests/shell/test_b3_calibration.bats": {"reason": "lib-interspect.sh not found"}
        },
    }))
    proc, d = report(tmp_path, tap(
        "ok 1 b3 case one # skip lib-interspect.sh not found",
        "ok 2 b3 case two # skip lib-interspect.sh not found",
        "ok 3 b3 case three # skip lib-interspect.sh not found",
    ), extra=["--actions-skip-baseline", str(base)])
    assert proc.returncode == PASS, json.dumps(d)[:800]


def test_actions_baseline_warns_when_coverage_improves(tmp_path):
    """A decrease is visible too, so the baseline is never silently rewritten."""
    base = tmp_path / "base.json"
    base.write_text(json.dumps({
        "run_id": "x", "plan": 2, "skipped": 2,
        "reason_counts": {"yq not available (standalone CI)": 2},
        "skipped_cases": {"a": "yq not available (standalone CI)",
                          "b": "yq not available (standalone CI)"},
        "allowed_growth": {},
    }))
    proc, d = report(tmp_path, tap(
        "ok 1 a # skip yq not available (standalone CI)", "ok 2 b"
    ), extra=["--actions-skip-baseline", str(base)])
    assert proc.returncode == WARN, f"an improvement was not surfaced: {json.dumps(d)[:600]}"


def test_an_accepted_improvement_stops_warning_without_rewriting_history(tmp_path):
    """A reviewed decrease is recorded as an accepted delta, not by editing the
    historical run's record. The baseline stays a faithful account of run
    34150176247; acceptance is a separate, cited statement."""
    base = tmp_path / "base.json"
    base.write_text(json.dumps({
        "run_id": "34150176247", "plan": 2, "skipped": 2,
        "reason_counts": {"ic not available (standalone CI)": 2},
        "skipped_cases": {"a": "ic not available (standalone CI)",
                          "b": "ic not available (standalone CI)"},
        "allowed_growth": {},
        "accepted_improvements": {
            "ic not available (standalone CI)": {
                "count": 0,
                "why": "guards were vestigial; assertions recovered",
                "accepted_in_run": "35499967436",
            }
        },
    }))
    proc, d = report(tmp_path, tap("ok 1 a", "ok 2 b"),
                     extra=["--actions-skip-baseline", str(base)])
    assert proc.returncode == PASS, json.dumps(d)[:600]
    # The historical counts are still readable; only the expectation moved.
    assert d["status"] == "pass"


def test_an_unaccepted_improvement_still_warns(tmp_path):
    """[negative control] Acceptance must be per-reason and explicit."""
    base = tmp_path / "base.json"
    base.write_text(json.dumps({
        "run_id": "x", "plan": 2, "skipped": 2,
        "reason_counts": {"gawk required for JSONL parser tests": 2},
        "skipped_cases": {"a": "gawk required for JSONL parser tests",
                          "b": "gawk required for JSONL parser tests"},
        "allowed_growth": {},
        "accepted_improvements": {"some other reason": {"count": 0}},
    }))
    proc, d = report(tmp_path, tap("ok 1 a", "ok 2 b"),
                     extra=["--actions-skip-baseline", str(base)])
    assert proc.returncode == WARN, json.dumps(d)[:600]
