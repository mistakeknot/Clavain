"""Review-by-risk trial: class decisions, window, rollback and the round gate."""
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

SHIPPED_POLICY = yaml.safe_load((ROOT / "config/routing.yaml").read_text())["reasoning"]["review_policy"]
POLICY = dict(SHIPPED_POLICY, merge_day="2026-11-18")
IN = "2026-11-20"


def act(paths, today=IN, prototype=False, policy=POLICY):
    return rp.decide(paths, policy, prototype, rp._day(today))


def test_shipped_policy_is_a_two_week_window():
    assert SHIPPED_POLICY['merge_day'] == '2026-11-22'
    assert rp.valid_policy(SHIPPED_POLICY)
    assert rp.trial_active(SHIPPED_POLICY, today=datetime.date(2026, 11, 22))
    assert rp.trial_active(SHIPPED_POLICY, today=datetime.date(2026, 12, 5))
    assert not rp.trial_active(SHIPPED_POLICY, today=datetime.date(2026, 12, 6))
    assert not rp.trial_active(SHIPPED_POLICY, today=datetime.date(2026, 11, 21))
    assert POLICY['routine']['max_rounds'] == 1



@pytest.mark.parametrize("paths,klass", [
    (["README.md", "docs/a.md"], "doc-only"),
    (["tests/x/test_a.py"], "keep"),
    (["README.md", "tests/x/test_a.py"], "keep"),
    (["styles/theme.css"], "routine"),
    (["README.md", "styles/theme.css"], "routine"),
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


@pytest.mark.parametrize("path", [
    "scripts/claude_usage.py", "cmd/clavain-cli/review_worker.go", "cmd/clavain-cli/policy.go",
    "scripts/pre-commit-hook.sh", "scripts/ci-package.sh", "tools/sync-ci-policy.py",
    "tools/sync-model-service-authorization.py", "cloud/pre-push-public-repo.sh", "cloud/pre-push.sh",
    "cloud/pre-commit.sh", "cloud/compose-hook.py", "common/.local/bin/vizier-autoallow",
    "requirements.txt", "package.json", "go.mod", "notes/plan.md", "prompts/system.md", "main.sh",
])
def test_allow_list_unnamed_paths_keep_full_review(path):
    """Only a path a safe class names is reduced; every other path, listed or not, keeps full review."""
    for kw in ({}, {"prototype": True}):
        for paths in ([path], ["docs/a.md", path], ["styles/theme.css", path]):
            got = act(paths, **kw)
            assert (got["class"], got["action"], got["max_rounds"]) == ("keep", "full", 3), (paths, kw, got)


def test_prototype_does_not_widen_safe_paths():
    assert act(["index.html", "game.js", "art/ship.png"], prototype=True)["action"] == "full"
    assert act(["index.html", "run.sh"], prototype=True)["action"] == "full"


def test_cli_splits_only_on_newline(tmp_path):
    """A path holding VT or FS must reach the classifier whole, not be split into two docs paths."""
    cfg = tmp_path / "r.yaml"
    cfg.write_text(yaml.safe_dump({"reasoning": {"review_policy": dict(POLICY, first_day="2000-01-01", last_day="2999-12-31")}}))
    for sep in ("\x0b", "\x1c", "\x0c", "\r"):
        out = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/review_policy.py"), "decide", "--config", str(cfg)],
                             input=f"docs/a.md{sep}docs/b.md\n".encode(), capture_output=True, check=True).stdout
        got = json.loads(out)
        assert (got["class"], got["action"]) == ("keep", "full"), sep
    out = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/review_policy.py"), "decide", "--config", str(cfg)],
                         input=b"docs/a.md\ndocs/b.md\n", capture_output=True, check=True).stdout
    assert json.loads(out)["action"] == "skip"


def test_skip_and_one_round_actions():
    assert act(["docs/a.md"])["action"] == "skip"
    assert act(["tests/test_a.py"])["action"] == "full"
    assert act(["styles/theme.css"], prototype=True)["action"] == "one-round"
    assert act(["styles/theme.css"])["action"] == "one-round"


def test_no_paths_is_full_review():
    assert act([])["action"] == "full"


@pytest.mark.parametrize("today,live", [("2026-11-17", False), ("2026-11-18", True), ("2026-12-01", True), ("2026-12-02", False)])
def test_window_edges(today, live):
    assert act(["styles/theme.css"], today)["trial_active"] is live
    if not live:
        assert act(["docs/a.md"], today)["action"] == "full"


def test_rollback_flag_env_and_bad_window(monkeypatch):
    assert act(["docs/a.md"], policy=dict(POLICY, enabled=False))["action"] == "full"
    assert act(["docs/a.md"], policy=dict(POLICY, merge_day="soon"))["action"] == "full"
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
    monkeypatch.setattr(rp, "load_policy", lambda: POLICY)
    return mod.check(bead, tmp_path / "none.jsonl", tmp_path / "reviews", check_only=True, role="cross-lab-review")


CODE = ["styles/theme.css"]
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
    assert gate(tmp_path / "w", rows, monkeypatch, today="2026-12-02") == 0
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
    for paths in (["docs/a.md"], ["styles/theme.css"]):
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
        assert act(["styles/theme.css"], policy=policy)["action"] == "full"


def test_the_date_comes_only_from_the_clock(monkeypatch):
    monkeypatch.setenv("CLAVAIN_REVIEW_POLICY_TODAY", "2026-11-20")
    clock(monkeypatch, "2026-12-02")
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

    def row(att, head, sevs, paths=("styles/theme.css",)):
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
               created_at="2026-11-20T00:00:00Z", findings_source="unknown", findings=[], changed_paths=["styles/theme.css"],
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


# ---- round 2 of the cross-lab review ----

@pytest.mark.parametrize("path", [
    "config/agent-instructions.md", "config/codex-instructions.md", "config/anything.yaml",
    "scripts/clavain_selector/jev_client.py", "scripts/lib-fleet.sh", "scripts/pool-headroom.py",
    "scripts/sync-agent-instructions.py", "units/clavain.service", "docs/operating-contract.md",
    "common/.local/bin/vizier-autoallow", "common/.local/bin/dotfiles-converge.sh", "tools/bin/run", "etc/sudoers.d/x",
    "app/.config/tool.yaml", "server/refs/x.py", "deploy/foo.timer",
])
def test_instruction_and_authority_surfaces_keep_full_review(path):
    for proto in (False, True):
        assert act([path], prototype=proto)["action"] == "full", path


def test_decide_cli_has_no_date_override():
    out = subprocess.run([sys.executable, str(ROOT / "scripts/review_policy.py"), "decide", "--today", "2026-11-20"],
                         input="docs/a.md\n", capture_output=True, text=True)
    assert out.returncode != 0 and "unrecognized arguments" in out.stderr


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(keep_list=[None]),
    lambda p: p.update(keep_list=["unrelated"]),
    lambda p: p.update(keep_list=[["spend"]]),
    lambda p: p.update(keep_list=POLICY["keep_list"][:-1]),
    lambda p: p.pop("trial"),
    lambda p: p.pop("bead"),
    lambda p: p.pop("enabled"),
    lambda p: p.pop("merge_day"),
])
def test_invalid_policy_block_is_not_an_active_trial(mutate):
    bad = json.loads(json.dumps(POLICY, default=str))
    mutate(bad)
    assert act(["docs/a.md"], policy=bad)["action"] == "full"


@pytest.mark.parametrize("paths", [
    ["docs/a.md\t"], ["docs/a.md\n"], [" docs/a.md"], ["docs/a\x7f.md"], ["docs/a.md", None], ["docs/a.md", 3],
])
def test_raw_path_evidence_is_validated_before_cleanup(paths):
    assert act(paths)["action"] == "full"


def test_round_gate_treats_a_malformed_path_entry_as_unknown(tmp_path, monkeypatch):
    row = failed("a", CODE, ["P3"])
    row["changed_paths"] = ["styles/theme.css", None]
    assert gate(tmp_path, [row], monkeypatch) == 0


def test_round_gate_counts_truncated_findings_as_high(tmp_path, monkeypatch):
    row = failed("a", CODE, ["P3"] * 3)
    row["findings_truncated"] = True
    assert gate(tmp_path, [row], monkeypatch) == 0


def test_report_missing_head_is_not_a_code_change():
    rtr = load_report()
    def row(attempt, head):
        return dict(kind="cross-lab-review-receipt", repo="o/r", pr="1", dispatch_id="d" + attempt, attempt_id=attempt,
                    head_sha=head, created_at="2026-11-20T0%s:00:00Z" % attempt, findings_source="parsed",
                    findings=[{"severity": "P1"}], changed_paths=["styles/theme.css"], verdict="BLOCK")
    out = rtr.summarize(rtr.per_change([row("1", None), row("2", "h2")], POLICY))["all"]
    assert out["findings_changed_code"] == 0 and out["rounds_with_findings"] == 1
    assert out["rounds_unknown_heads"] == 1
    out = rtr.summarize(rtr.per_change([row("1", "h1"), row("2", "h2")], POLICY))["all"]
    assert out["findings_changed_code"] == 1


def test_report_token_share_is_unknown_when_a_role_has_unknown_usage(monkeypatch):
    rtr = load_report()
    data = {"by_role": {"cross-lab-review": {"tokens": 10}, "execution": {"tokens": 90}, "validation": {"tokens": None}}}
    monkeypatch.setattr(rtr.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps(data), ""))
    got = rtr.tokens(14)
    assert got["review_share"] is None and got["roles_unknown_tokens"] == ["validation"]


def test_report_token_share_is_unknown_when_runs_lack_usage(monkeypatch):
    rtr = load_report()
    data = {"by_role": {"cross-lab-review": {"tokens": 10, "runs": 4, "runs_no_usage": 1},
                        "execution": {"tokens": 90, "runs": 9, "runs_no_usage": 0}}}
    monkeypatch.setattr(rtr.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps(data), ""))
    got = rtr.tokens(14)
    assert got["review_share"] is None and got["roles_with_runs_no_usage"] == ["cross-lab-review"]
    assert got["runs_no_usage"] == 1 and got["review_share_measured_runs_only"] == 0.1
    data["by_role"]["cross-lab-review"]["runs_no_usage"] = 0
    assert rtr.tokens(14)["review_share"] == 0.1
    del data["by_role"]["execution"]["runs_no_usage"]  # a missing count is unknown, not zero
    assert rtr.tokens(14)["review_share"] is None

@pytest.mark.parametrize('path', ['README.py', 'README.json', 'LICENSE.sh', 'CHANGELOG.yaml', 'src/gate.py', 'src/dispatch.ts', 'src/routing.js'])
def test_unsafe_names_never_reduce(path):
    assert act([path])['action'] == 'full'


def test_known_empty_findings_are_in_metric_denominator():
    report = load_report()
    rows = [dict(repo='o/r', pr=1, dispatch_id='d', attempt_id='a', head_sha='a'*40,
                 findings=[], findings_source='body', changed_paths=['styles/theme.css'])]
    result = report.summarize(report.per_change(rows, POLICY))['all']
    assert result['findings_changed_code_per_round'] == 0

@pytest.mark.parametrize('role', ['plan-review', 'validation', None])
def test_routine_limit_does_not_block_other_roles(tmp_path, monkeypatch, role):
    assert gate(tmp_path, [passed('a', CODE)], monkeypatch) == 25
    spec = importlib.util.spec_from_file_location('rrl_other', ROOT / 'scripts/review-round-limit.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.check('b-1', tmp_path / 'none.jsonl', tmp_path / 'reviews', role=role) == 0


def test_trial_cannot_bypass_baseline_on_malformed_history(tmp_path, monkeypatch):
    rows = [failed(c, CODE, ['P3']) for c in 'abc']
    assert gate(tmp_path, rows, monkeypatch) == 25
    (tmp_path / 'reviews/o__r/broken.json').write_text('{')
    spec = importlib.util.spec_from_file_location('rrl_broken', ROOT / 'scripts/review-round-limit.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.check('b-1', tmp_path / 'none.jsonl', tmp_path / 'reviews', role='cross-lab-review') == 25


def test_incomplete_trial_evidence_does_not_allow_fourth_failure(tmp_path, monkeypatch):
    rows = [failed(c, CODE, ['P3'], changed_paths_truncated=True) for c in 'abc']
    assert gate(tmp_path, rows, monkeypatch) == 25

@pytest.mark.parametrize('path', ['src/password_reset.ts', 'src/signup.tsx', 'src/apiKeys.ts',
    'app/settings.py', 'src/config.ts', 'src/subscription/refund.ts', 'src/pricing.ts',
    'src/lib/crypto.ts', 'src/admin/users.ts', 'src/unknown.ts',
    'tests/structural/test_review_policy.py', 'tests/structural/test_review_round_limit.py'])
def test_sensitive_and_unnamed_source_requires_full_review(path):
    assert act([path])['action'] == 'full'

@pytest.mark.parametrize('extra', [dict(findings=[], findings_total=0),
    dict(findings_source='conflict', findings_total=3), dict(findings_total=4)])
def test_incomplete_failed_findings_allow_second_round(tmp_path, monkeypatch, extra):
    row = failed('a', CODE, ['P2'])
    row.update(extra)
    assert gate(tmp_path, [row], monkeypatch) == 0
    assert gate(tmp_path/'two', [row, passed('b', CODE)], monkeypatch) == 25

@pytest.mark.parametrize('value', [20261120, '20261120', '2026-W47-5', datetime.date(2026,11,20)])
def test_merge_day_requires_calendar_string(value):
    assert not rp.trial_active(dict(POLICY, merge_day=value), rp._day(IN))

@pytest.mark.parametrize('routine', [[], {'max_rounds':1, 'second_round_if_severity':5}])
@pytest.mark.parametrize('inactive', [dict(enabled=False), dict(merge_day=None)])
def test_inactive_bad_routine_preserves_baseline(tmp_path, monkeypatch, routine, inactive, capsys):
    bad = dict(POLICY, routine=routine, **inactive)
    monkeypatch.setattr(rp, 'load_policy', lambda: bad)
    spec = importlib.util.spec_from_file_location('bad_rrl', ROOT / 'scripts/review-round-limit.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    reviews = tmp_path / 'reviews/o__r'
    reviews.mkdir(parents=True)
    (reviews/'1.json').write_text(json.dumps(failed('a', CODE, ['P2'])))
    for role in ('cross-lab-review', 'plan-review', 'validation', None):
        assert mod.check('b-1', tmp_path/'none', tmp_path/'reviews', role=role) == 0
    assert 'config' in capsys.readouterr().err.lower()


def test_trial_refusal_writes_summary(tmp_path, monkeypatch):
    assert gate(tmp_path, [passed('a', CODE)], monkeypatch) == 25
    assert 'CLAVAIN_REVIEW_POLICY=off' in (tmp_path/'reviews/round-limits/b-1.md').read_text()

@pytest.mark.parametrize('unavailable', ['zone', 'override'])
def test_report_flags_unavailable_classification(monkeypatch, unavailable, capsys):
    if unavailable == 'zone':
        monkeypatch.setattr(rp, 'today_pacific', lambda: None)
    else:
        monkeypatch.setenv('CLAVAIN_REVIEW_POLICY', 'off')
    rows = [dict(repo='o/r', pr=1, dispatch_id='d', attempt_id='a', changed_paths=CODE)]
    assert load_report().per_change(rows, POLICY)['o/r#1']['klass'] == 'unknown'
    assert 'classification' in capsys.readouterr().err


@pytest.mark.parametrize("path", [
    "src/password_reset.ts", "src/apiKeys.ts", "src/pricing.ts",
    "src/subscription/refund.ts", "src/lib/crypto.ts", "src/admin/users.ts",
    "src/config.ts", "app/settings.ts", "server.js", "api/handler.ts",
    "scripts/build.js", "deep/unknown/component.tsx", "game.js",
])
def test_prototype_cannot_skip_unknown_code(path):
    assert act([path], prototype=True)["action"] == "full"


@pytest.mark.parametrize("path", [
    "tests/structural/test_review_round_decision.py",
    "tests/structural/test_review_downgrade_safety.py",
    "tests/shell/review_round.bats", "tests/shell/lib_verdict.bats",
    "tests/structural/conftest.py", "tests/pyproject.toml", "tests/run-tests.sh",
    "tests/new_gate_check.py", "nested/__tests__/decision.ts",
    "e2e/admission.spec.ts", "other/cancel.test.js", "new_test.go",
    "docs/tests/harness.md", "conftest.py", "pytest.ini", "tox.ini",
    "run-tests.sh",
])
def test_tests_and_harness_always_get_full_review(path):
    for prototype in (False, True):
        assert act([path], prototype=prototype)["action"] == "full"


def test_quality_gate_command_includes_untracked_protected_file(tmp_path):
    import re
    text = (ROOT / "commands/quality-gates.md").read_text()
    command = re.search(r'also run `([^`]+)`', text).group(1)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a.md").write_text("before")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "-qm", "initial"], cwd=tmp_path, check=True)
    (tmp_path / "docs/a.md").write_text("after")
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks/new.sh").write_text("exit 0")
    cfg = tmp_path.parent / "untracked-command-policy.yaml"
    cfg.write_text(yaml.safe_dump({"reasoning": {"review_policy": dict(
        POLICY, merge_day=rp.today_pacific().isoformat())}}))
    env = dict(os.environ, CLAVAIN_SOURCE_DIR=str(ROOT), CLAVAIN_ROUTING_POLICY=str(cfg))
    out = subprocess.run(["bash", "-c", command], cwd=tmp_path, env=env,
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["action"] == "full"
