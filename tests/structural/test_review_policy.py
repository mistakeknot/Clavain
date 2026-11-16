"""Review-by-risk trial (bead mk-h9541): class decisions, window, rollback and the round gate."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import review_policy as rp  # noqa: E402

POLICY = yaml.safe_load((ROOT / "config/routing.yaml").read_text())["reasoning"]["review_policy"]
IN = "2026-11-20"


def act(paths, today=IN, prototype=False, policy=POLICY):
    return rp.decide(paths, policy, prototype, rp._day(today))


def test_shipped_policy_is_a_two_week_window():
    first, last = rp._day(POLICY["first_day"]), rp._day(POLICY["last_day"])
    assert (last - first).days == 13 and POLICY["bead"] == "mk-h9541" and POLICY["enabled"] is True
    assert POLICY["routine"]["max_rounds"] == 1


@pytest.mark.parametrize("paths,klass", [
    (["README.md", "docs/a.md"], "doc-only"),
    (["tests/x/test_a.py"], "test-only"),
    (["README.md", "tests/x/test_a.py"], "text-only"),
    (["src/app.go"], "routine"),
    (["README.md", "src/app.go"], "routine"),
])
def test_classes(paths, klass):
    assert act(paths)["class"] == klass


@pytest.mark.parametrize("path", [
    "AGENTS.md", "skills/x/SKILL.md", "commands/quality-gates.md", ".claude/settings.json",
    "hooks/pre.sh", ".github/workflows/ci.yml", "scripts/release.sh", "scripts/publish-npm.sh",
    "db/migrations/001.sql", "src/auth/login.go", "src/billing/invoice.py", "src/saves/format.go",
    "config/routing.yaml", "src/credentials.py", ".claude-plugin/plugin.json",
])
def test_keep_list_wins_over_every_skip_class(path):
    for kw in ({}, {"prototype": True}):
        got = act(["README.md", path], **kw)
        assert (got["class"], got["action"], got["max_rounds"]) == ("keep", "full", 3)


def test_skip_and_one_round_actions():
    assert act(["docs/a.md"])["action"] == "skip"
    assert act(["tests/test_a.py"])["action"] == "skip"
    assert act(["src/app.go"], prototype=True)["action"] == "skip"
    assert act(["src/app.go"])["action"] == "one-round"


def test_no_paths_is_full_review():
    assert act([])["action"] == "full"


@pytest.mark.parametrize("today,live", [("2026-11-16", False), ("2026-11-17", True), ("2026-11-30", True), ("2026-12-01", False)])
def test_window_edges(today, live):
    assert act(["src/a.go"], today)["trial_active"] is live
    if not live:
        assert act(["docs/a.md"], today)["action"] == "full"


def test_rollback_flag_env_and_bad_window(monkeypatch):
    assert act(["docs/a.md"], policy=dict(POLICY, enabled=False))["action"] == "full"
    assert act(["docs/a.md"], policy=dict(POLICY, last_day="soon"))["action"] == "full"
    assert act(["docs/a.md"], policy=None)["action"] == "full"
    monkeypatch.setenv("CLAVAIN_REVIEW_POLICY", "off")
    assert act(["docs/a.md"])["action"] == "full"


@pytest.mark.parametrize("sev,high", [("P1", True), ("HIGH", True), ("High", True), (None, True), ("", True),
                                      ("unheard-of", True), ("P2", False), ("P3", False), ("Medium", False),
                                      ("Low (accessibility)", False), ("Info", False), ("Low/Informational", False)])
def test_severity(sev, high):
    assert rp.is_high(sev, POLICY) is high


# --- the round gate -------------------------------------------------------

def failed(attempt, paths, severities=None, bead="b-1"):
    row = dict(schema_version=1, kind="cross-lab-review-receipt", role="cross-lab-review", bead_id=bead,
               verdict="BLOCK", dispatch_id="d", attempt_id=attempt, changed_paths=paths)
    if severities is not None:
        row["findings"] = [dict(severity=s) for s in severities]
    return row


def gate(tmp_path, rows, today=IN, off=False, bead="b-1"):
    reviews = tmp_path / "reviews" / "o__r"
    reviews.mkdir(parents=True, exist_ok=True)
    for n, row in enumerate(rows):
        (reviews / f"{n}.json").write_text(json.dumps(row))
    env = dict(os.environ, CLAVAIN_REVIEW_POLICY_TODAY=today, CLAVAIN_ROUTING_POLICY=str(ROOT / "config/routing.yaml"))
    env.pop("CLAVAIN_REVIEW_POLICY", None)
    if off:
        env["CLAVAIN_REVIEW_POLICY"] = "off"
    return subprocess.run([sys.executable, str(ROOT / "scripts/review-round-limit.py"), bead,
                           str(tmp_path / "none.jsonl"), str(tmp_path / "reviews"), "--check-only"],
                          env=env, capture_output=True, text=True).returncode


CODE = ["src/app.go"]
KEEP = ["src/auth/login.go"]


def test_routine_low_severity_failure_stops_after_one_round(tmp_path):
    assert gate(tmp_path, [failed("a", CODE, ["P3", "Low"])]) == 25


def test_routine_high_severity_failure_allows_exactly_one_more(tmp_path):
    one = [failed("a", CODE, ["P1"])]
    assert gate(tmp_path, one) == 0
    assert gate(tmp_path / "two", one + [failed("b", CODE, ["P2"])]) == 25


def test_routine_zero_failures_is_untouched(tmp_path):
    assert gate(tmp_path, []) == 0


def test_missing_findings_count_as_high(tmp_path):
    assert gate(tmp_path, [failed("a", CODE)]) == 0


def test_keep_list_keeps_three_rounds(tmp_path):
    rows = [failed(c, KEEP, ["P3"]) for c in "ab"]
    assert gate(tmp_path, rows) == 0
    assert gate(tmp_path / "x", rows + [failed("c", KEEP, ["P3"])]) == 25


def test_one_keep_list_round_keeps_the_whole_bead_on_three(tmp_path):
    assert gate(tmp_path, [failed("a", CODE, ["P3"]), failed("b", KEEP, ["P3"])]) == 0


def test_failure_without_paths_keeps_three(tmp_path):
    assert gate(tmp_path, [failed("a", [], ["P3"])]) == 0


def test_outside_window_and_rolled_back_keep_three(tmp_path):
    rows = [failed("a", CODE, ["P3"]), failed("b", CODE, ["P3"])]
    assert gate(tmp_path / "w", rows, today="2026-12-01") == 0
    assert gate(tmp_path / "r", rows, off=True) == 0


# --- the trial report -------------------------------------------------------

def test_report_counts_rounds_and_changed_code(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("rtr", ROOT / "scripts/review-trial-report.py")
    rtr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rtr)

    def row(att, head, sevs, paths=("src/a.go",)):
        return dict(kind="cross-lab-review-receipt", repo="o/r", pr="1", dispatch_id="d", attempt_id=att,
                    head_sha=head, created_at="2026-11-20T00:00:00Z", findings_source="structured",
                    findings=[dict(severity=s) for s in sevs], changed_paths=list(paths), verdict="BLOCK")
    rows = [row("a", "h1", ["P1", "P3"]), row("b", "h2", ["P3"])]
    got = rtr.per_change(rows, POLICY)["o/r#1"]
    assert got["rounds"] == 2 and got["klass"] == "one-round"
    assert got["findings_changed_code"] == 1  # only round 1's P1; its P3 is low, round 2 has no later head
    assert rtr.summarize({"x": got})["all"]["rounds_per_change"] == 2.0
