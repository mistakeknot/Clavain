"""Review-by-risk trial (bead mk-h9541): class decisions, window, rollback and the round gate."""
import datetime
import importlib.util
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
    "scripts/dispatch.sh", "scripts/lib-routing.sh", "scripts/review-round-limit.py", "scripts/review_policy.py",
    "scripts/review-trial-report.py", "scripts/route-spawn.sh", "docs/canon/reasoning-routing.md",
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

def failed(attempt, paths, severities=None, bead="b-1", **extra):
    row = dict(schema_version=1, kind="cross-lab-review-receipt", role="cross-lab-review", bead_id=bead,
               verdict="BLOCK", dispatch_id="d", attempt_id=attempt, changed_paths=paths)
    if severities is not None:
        row["findings"] = [dict(severity=s) for s in severities]
    row.update(extra)
    return row


def passed(attempt, paths, bead="b-1"):
    return dict(failed(attempt, paths, [], bead), verdict="PASS")


def clock(monkeypatch, today):
    """The trial date comes only from the Pacific clock; tests fake that clock, never an environment variable."""
    monkeypatch.setattr(rp, "today_pacific", lambda: datetime.date.fromisoformat(today))


def gate(tmp_path, rows, monkeypatch, today=IN, off=False, bead="b-1"):
    reviews = tmp_path / "reviews" / "o__r"
    reviews.mkdir(parents=True, exist_ok=True)
    for n, row in enumerate(rows):
        (reviews / f"{n}.json").write_text(json.dumps(row))
    clock(monkeypatch, today)
    monkeypatch.setenv("CLAVAIN_ROUTING_POLICY", str(ROOT / "config/routing.yaml"))
    monkeypatch.delenv("CLAVAIN_REVIEW_POLICY", raising=False)
    if off:
        monkeypatch.setenv("CLAVAIN_REVIEW_POLICY", "off")
    spec = importlib.util.spec_from_file_location("rrl", ROOT / "scripts/review-round-limit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.check(bead, tmp_path / "none.jsonl", tmp_path / "reviews", check_only=True)


CODE = ["src/app.go"]
KEEP = ["src/auth/login.go"]


def test_routine_low_severity_failure_stops_after_one_round(tmp_path, monkeypatch):
    assert gate(tmp_path, [failed("a", CODE, ["P3", "Low"])], monkeypatch) == 25


def test_routine_high_severity_failure_allows_exactly_one_more(tmp_path, monkeypatch):
    one = [failed("a", CODE, ["P1"])]
    assert gate(tmp_path, one, monkeypatch) == 0
    assert gate(tmp_path / "two", one + [failed("b", CODE, ["P2"])], monkeypatch) == 25


def test_routine_zero_failures_is_untouched(tmp_path, monkeypatch):
    assert gate(tmp_path, [], monkeypatch) == 0


def test_missing_findings_count_as_high(tmp_path, monkeypatch):
    assert gate(tmp_path, [failed("a", CODE)], monkeypatch) == 0


def test_keep_list_keeps_three_rounds(tmp_path, monkeypatch):
    rows = [failed(c, KEEP, ["P3"]) for c in "ab"]
    assert gate(tmp_path, rows, monkeypatch) == 0
    assert gate(tmp_path / "x", rows + [failed("c", KEEP, ["P3"])], monkeypatch) == 25


def test_one_keep_list_round_keeps_the_whole_bead_on_three(tmp_path, monkeypatch):
    assert gate(tmp_path, [failed("a", CODE, ["P3"]), failed("b", KEEP, ["P3"])], monkeypatch) == 0


def test_failure_without_paths_keeps_three(tmp_path, monkeypatch):
    assert gate(tmp_path, [failed("a", [], ["P3"])], monkeypatch) == 0


def test_outside_window_and_rolled_back_keep_three(tmp_path, monkeypatch):
    rows = [failed("a", CODE, ["P3"]), failed("b", CODE, ["P3"])]
    assert gate(tmp_path / "w", rows, monkeypatch, today="2026-12-01") == 0
    assert gate(tmp_path / "r", rows, monkeypatch, off=True) == 0


# --- review round 1 findings (fail-safe direction) -------------------------

@pytest.mark.parametrize("path", [
    "commands\\quality-gates.md", ".github\\workflows\\build.yml", "/etc/passwd", "../AGENTS.md", "docs/../AGENTS.md",
    "./AGENTS.md", "docs//a.md", "docs/a\x01.md", '"docs/a.md"',
])
def test_ambiguous_paths_keep_full_review(path):
    for kw in ({}, {"prototype": True}):
        got = act(["README.md", path], **kw)
        assert (got["class"], got["action"]) == ("keep", "full")


def test_rename_hides_the_protected_source_unless_renames_are_off(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], capture_output=True, text=True, check=True).stdout
    git("init", "-q")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    body = "line\n" * 40
    (tmp_path / "AGENTS.md").write_text(body)
    git("add", ".")
    git("commit", "-qm", "base")
    git("mv", "AGENTS.md", "README.md")
    git("commit", "-qm", "rename")
    with_renames = git("diff", "--name-only", "HEAD~1", "HEAD").split()
    no_renames = git("diff", "--no-renames", "--name-only", "HEAD~1", "HEAD").split()
    assert act(with_renames)["action"] == "skip"  # the failure the documented command must avoid
    assert act(no_renames)["action"] == "full"
    for doc in ("skills/code-review-discipline/SKILL.md", "skills/code-review-discipline/SKILL-compact.md",
                "commands/quality-gates.md"):
        text = (ROOT / doc).read_text()
        assert "review_policy.py" in text and "--no-renames" in text, doc
        assert "git diff --name-only BASE" not in text, doc


@pytest.mark.parametrize("broken", [
    dict(routine=None), dict(routine={}), dict(routine={"max_rounds": 99, "second_round_if_severity": ["P1"]}),
    dict(routine={"max_rounds": 0, "second_round_if_severity": ["P1"]}),
    dict(routine={"max_rounds": True, "second_round_if_severity": ["P1"]}),
    dict(routine={"max_rounds": 1}), dict(skip_classes=None), dict(skip_classes=[]),
    dict(skip_classes=["routine"]), dict(keep_list=None), dict(keep_list=[]),
])
def test_incomplete_or_invalid_policy_is_no_trial(broken):
    policy = {k: v for k, v in dict(POLICY, **broken).items() if v is not None}
    for paths in (["docs/a.md"], ["src/app.go"]):
        got = act(paths, policy=policy)
        assert (got["action"], got["max_rounds"], got["trial_active"]) == ("full", 3, False)


@pytest.mark.parametrize("path", [
    "server/refs/standing-approvals.md", "server/refs/review-by-risk.md",
    "server/refs/standing-approvals-index.md", "server/refs/batch-lane.md",
    "policies/independent-ci.md", "docs/vizier-card-per-message.md", "x/approvals-root-runs.md",
])
def test_fleet_instruction_and_approval_files_keep_full_review(path):
    for kw in ({}, {"prototype": True}):
        got = act(["README.md", path], **kw)
        assert (got["class"], got["action"]) == ("keep", "full"), path


def test_trial_window_is_pacific_time(monkeypatch):
    real = datetime.datetime
    class Fake(real):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 11, 17, 6, 30, tzinfo=datetime.timezone.utc).astimezone(tz)  # 22:30 on Nov 16 Pacific
    monkeypatch.setattr(rp.datetime, "datetime", Fake)
    assert rp.today_pacific() == datetime.date(2026, 11, 16)
    assert rp.trial_active(POLICY) is False


def test_unreadable_time_zone_is_no_trial(monkeypatch):
    monkeypatch.setattr(rp.zoneinfo, "ZoneInfo", lambda name: (_ for _ in ()).throw(KeyError(name)))
    assert rp.today_pacific() is None and rp.trial_active(POLICY) is False


def test_missing_keys_are_no_trial():
    for key in ("routine", "skip_classes", "keep_list"):
        policy = {k: v for k, v in POLICY.items() if k != key}
        assert act(["src/app.go"], policy=policy)["action"] == "full"


def test_the_date_comes_only_from_the_clock(monkeypatch):
    monkeypatch.setenv("CLAVAIN_REVIEW_POLICY_TODAY", "2026-11-20")
    clock(monkeypatch, "2026-12-01")
    assert rp.trial_active(POLICY) is False
    assert rp.decide(["docs/a.md"], POLICY)["action"] == "full"


def test_a_passing_routine_round_uses_the_one_round(tmp_path, monkeypatch):
    assert gate(tmp_path, [passed("a", CODE)], monkeypatch) == 25
    assert gate(tmp_path / "keep", [passed("a", KEEP)], monkeypatch) == 0


def test_high_finding_then_pass_then_third_is_refused(tmp_path, monkeypatch):
    rows = [failed("a", CODE, ["P1"]), passed("b", CODE)]
    assert gate(tmp_path, rows[:1], monkeypatch) == 0
    assert gate(tmp_path / "t", rows, monkeypatch) == 25


def test_unparsed_findings_count_as_high(tmp_path, monkeypatch):
    row = failed("a", CODE, [], findings_source="unknown", findings_total=None)
    assert gate(tmp_path, [row], monkeypatch) == 0
    assert gate(tmp_path / "two", [row, passed("b", CODE)], monkeypatch) == 25


def test_truncated_path_list_keeps_the_full_cap(tmp_path, monkeypatch):
    rows = [failed("a", CODE, ["P3"], changed_paths_truncated=True), failed("b", CODE, ["P3"], changed_paths_truncated=True)]
    assert gate(tmp_path, rows, monkeypatch) == 0


def test_failed_plan_review_keeps_the_full_cap(tmp_path, monkeypatch):
    plan = dict(failed("p", CODE, ["P3"]), role="plan-review")
    assert gate(tmp_path, [plan, passed("a", CODE)], monkeypatch) == 0


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


def load_report():
    spec = importlib.util.spec_from_file_location("rtr", ROOT / "scripts/review-trial-report.py")
    rtr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rtr)
    return rtr


def test_report_keeps_unknown_unknown():
    rtr = load_report()
    row = dict(kind="cross-lab-review-receipt", repo="o/r", pr="1", dispatch_id="d", attempt_id="a", head_sha="h1",
               created_at="2026-11-20T00:00:00Z", findings_source="unknown", findings=[], changed_paths=["src/a.go"],
               verdict="BLOCK")
    out = rtr.summarize(rtr.per_change([row], POLICY))["all"]
    assert out["findings_changed_code_per_round"] is None and out["rounds_without_findings"] == 1


def test_report_token_share_is_unknown_without_review_roles(monkeypatch):
    rtr = load_report()
    def fake(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"by_role": {"execution": {"tokens": 100}}}), "")
    monkeypatch.setattr(rtr.subprocess, "run", fake)
    got = rtr.tokens(14)
    assert got["review_share"] is None and got["review_tokens"] is None


def test_report_leaves_out_merges_whose_follow_up_is_not_over(monkeypatch):
    rtr = load_report()
    today = datetime.date.today()
    merged = (today - datetime.timedelta(days=2)).isoformat() + "T00:00:00Z"
    old = (today - datetime.timedelta(days=30)).isoformat() + "T00:00:00Z"
    prs = [dict(number=1, title="a", mergedAt=merged, files=[{"path": "x"}]),
           dict(number=2, title="b", mergedAt=old, files=[{"path": "y"}])]
    monkeypatch.setattr(rtr, "gh_json", lambda args: prs)
    got = rtr.escapes(["o/r"], today - datetime.timedelta(days=40), today)
    assert got["merged"] == 1 and got["merged_follow_up_incomplete"] == 1
