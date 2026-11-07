"""scripts/dispatch.sh argument handling, without launching a model.

What is pinned:
  * the governed `--role` path: what dispatch.sh asks `ic`, which CLI it
    starts with which argv, what the prompt starts with, the receipt it writes;
  * every refusal before a model starts (producer identity, option mixes,
    decision-context errors, missing `ic`, role/route mismatch);
  * `--dry-run` for every role through the real `ic` (golden keyed by policy).

The model CLIs and `ic` are fakes on PATH that record their arguments and
exit. The canned `ic` answers are fixtures of real `ic` output; they test how
dispatch.sh consumes a route, not what the routing policy says (that is
test_role_resolution.py).
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchlib as o  # noqa: E402

# Which behavior the checkout is required to have is read from its git history
# (see the comment above the scope-check tests).
SCOPE_CHECK = o.dispatch_feature("scope-check")


@pytest.fixture
def rig(tmp_path):
    r = o.Rig(tmp_path / "rig")
    r.use_route("routine-execution")
    return r


def _real_ic_rig(tmp_path, name="rig"):
    return o.Rig(tmp_path / name, real_ic_path=o.real_ic())


# ---------------------------------------------------------------------------
# Governed happy paths
# ---------------------------------------------------------------------------

def test_claude_seat_runs_claude_with_resolved_profile(rig):
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 0, r.stderr
    (call,) = rig.calls()
    assert call["cli"] == "claude"
    assert call["argv"] == [
        "--effort", "high", "--model", "claude-sonnet-5-5", "--permission-mode", "dontAsk",
        "--allowedTools", "Bash,Edit,Write,NotebookEdit", "--setting-sources", "project,local",
        "-p", "--output-format", "stream-json", "--verbose"]
    # The prompt arrives on stdin, behind the instruction contract block.
    assert call["stdin_head"].startswith("<!-- BEGIN CLAVAIN CODEX TOOL MAP -->")
    assert call["stdin_bytes"] > len("PROMPT\n")
    # The model's final text is the output file.
    assert rig.out.read_text().strip() == "done"


def test_codex_seat_runs_codex_with_resolved_profile(rig):
    rig.use_route("scout")
    r = rig.dispatch("--role", "scout", *rig.base_args(), CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 0, r.stderr
    (call,) = rig.calls()
    assert call["cli"] == "codex"
    argv = call["argv"]
    assert argv[:2] == ["exec", "-s"]
    for pair in (["-m", "gpt-6.1-sol"], ["-c", "model_reasoning_effort=medium"],
                 ["-c", "service_tier=default"]):
        assert any(argv[i:i + 2] == pair for i in range(len(argv) - 1)), (pair, argv)
    assert str(rig.repo) in argv


def test_ic_is_asked_for_the_role_with_policy_and_context(rig):
    rig.dispatch("--role", "routine-execution", *rig.base_args(),
                 CLAVAIN_DECISION_CONTEXT=rig.ctx)
    first = rig.ic_calls()[0]
    assert first[:3] == ["--json", "route", "dispatch"]
    assert "--role=routine-execution" in first
    assert f"--context-file={rig.ctx}" in first
    policy = [a for a in first if a.startswith("--policy=")]
    assert len(policy) == 1 and policy[0].endswith("config/routing.yaml")


def test_explicit_policy_env_is_passed_to_ic(rig, tmp_path):
    pol = tmp_path / "other-routing.yaml"
    pol.write_text("# any policy; the fake ic ignores it\n")
    rig.dispatch("--role", "routine-execution", *rig.base_args(), CLAVAIN_ROUTING_POLICY=pol)
    assert f"--policy={pol}" in rig.ic_calls()[0]


def test_context_file_flag_equals_form(rig):
    rig.dispatch("--role", "routine-execution", f"--context-file={rig.ctx}", *rig.base_args())
    assert f"--context-file={rig.ctx}" in rig.ic_calls()[0]


def test_no_decision_context_is_allowed_and_recorded_as_null(rig):
    r = rig.dispatch("--role", "routine-execution", *rig.base_args())
    assert r.returncode == 0, r.stderr
    assert not any(a.startswith("--context-file=") for a in rig.ic_calls()[0])
    assert rig.receipts()[0]["decision_context_sha256"] is None


def test_started_and_terminal_routing_decisions_are_recorded(rig):
    rig.dispatch("--role", "routine-execution", *rig.base_args(),
                 CLAVAIN_DECISION_CONTEXT=rig.ctx)
    records = [c for c in rig.ic_calls() if c[:2] == ["route", "record"]]
    states = [json.loads(next(a for a in c if a.startswith("--context="))[10:])["state"]
              for c in records]
    assert states == ["started", "completed"]
    for c in records:
        assert "--role=routine-execution" in c
        assert "--profile=routine-exec-sonnet" in c
        assert "--model=claude-sonnet-5-5" in c
        assert "--rule=dispatch-profile" in c


# Receipt fields present at the baseline (54d2fa43) and today.
CORE_RECEIPT = {
    "schema_version": 1, "kind": "dispatch-run-receipt", "role": "routine-execution",
    "backend": "claude", "model": "claude-sonnet-5-5", "effort": "high",
    "producer_identity": None, "bead_id": None, "thread_id": None, "session_id": None,
    "dispatch_id": "<volatile>", "attempt_id": "<volatile>",
    "started_at": "<volatile>", "ended_at": "<volatile>",
    "exit_code": 0, "outcome": "completed", "tokens_in": None, "tokens_out": None,
}
# Added after the baseline: what the receipt says about the model actually
# observed. Which of the two receipt shapes is required comes from the git
# history of the checkout (o.dispatch_feature), never from the receipt itself.
OBSERVED_RECEIPT = {
    "observed_model": "unknown", "observed_source": "unavailable",
    "observed_reason": "no request-bound model evidence for this transport or state",
    "observed_model_matches_requested": None,
    "usage_status": "unavailable",
    "usage_note": "no claude result usage in provider events",
}


def test_receipt_fields_for_a_completed_run(rig):
    import hashlib
    rig.dispatch("--role", "routine-execution", *rig.base_args(),
                 CLAVAIN_DECISION_CONTEXT=rig.ctx)
    (rec,) = rig.receipts()
    rec = o.normalize_receipt(rec)
    digest = rec.pop("decision_context_sha256")
    assert digest == hashlib.sha256(rig.ctx.read_bytes()).hexdigest()
    expected = dict(CORE_RECEIPT)
    if o.dispatch_feature("observed-receipt"):
        expected.update(OBSERVED_RECEIPT)
    assert rec == expected


def test_a_run_writes_only_the_known_state_files_in_tmp(rig):
    """dispatch.sh ignores TMPDIR for its state files; pin which ones it makes."""
    rig.dispatch("--role", "routine-execution", *rig.base_args(),
                 CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert set(rig.tmp_files) <= set(o.DISPATCH_TMP_SUFFIXES)
    assert ".json" in rig.tmp_files or rig.tmp_files == []  # the script removes its own state file


@pytest.mark.skipif(SCOPE_CHECK, reason="only the older script runs the inner dispatch here")
def test_the_inner_run_of_a_role_dispatch_is_reaped_too(rig):
    """A role is resolved, then dispatch.sh runs itself with the resolved
    backend; that inner run names its own /tmp files. They must be found by
    the fake CLI's ancestry, not left behind."""
    rig.dispatch("--role", "routine-execution", "--review-scratch", "x", *rig.base_args(),
                 CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert ".json.events.jsonl" in rig.tmp_files


def test_reaping_removes_known_files_and_rejects_unknown_ones(tmp_path):
    # Its own directory: nothing here is shared with another suite or the host.
    pid = 4242
    known = tmp_path / f"clavain-dispatch-{pid}.json.stderr"
    weird = tmp_path / f"clavain-dispatch-{pid}.surprise"
    other = tmp_path / "clavain-dispatch-4243.json"  # another pid: never touched
    other.write_text("y")
    known.write_text("x")
    assert o.reap_dispatch_tmp(pid, tmp_path) == [".json.stderr"]
    assert not known.exists() and other.exists()
    known.write_text("x")
    weird.write_text("x")
    with pytest.raises(AssertionError, match="unexpected dispatch file"):
        o.reap_dispatch_tmp(pid, tmp_path)
    assert weird.exists() and known.exists()  # nothing deleted when one name is unknown


def test_reaping_refuses_a_symlink_and_leaves_its_target_alone(tmp_path):
    victim = tmp_path / "victim"
    victim.write_text("precious")
    link = tmp_path / "clavain-dispatch-4242.json"
    link.symlink_to(victim)
    with pytest.raises(AssertionError, match="not a regular file of ours"):
        o.reap_dispatch_tmp(4242, tmp_path)
    assert link.is_symlink() and victim.read_text() == "precious"


def test_session_variables_do_not_reach_the_script(rig, tmp_path, monkeypatch):
    """BASH_ENV, ENV and INTERBAND_LIB of the caller must not be inherited."""
    leak = tmp_path / "leak"
    hook = tmp_path / "hook.sh"
    hook.write_text(f"touch {leak}\n")
    monkeypatch.setenv("BASH_ENV", str(hook))
    monkeypatch.setenv("ENV", str(hook))
    monkeypatch.setenv("INTERBAND_LIB", str(hook))
    monkeypatch.setenv("CLAVAIN_ROUTING_POLICY", "/nonexistent")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    env = rig.env()
    assert not {"BASH_ENV", "ENV", "CLAVAIN_ROUTING_POLICY", "PYTHONPATH"} & set(env)
    assert env["INTERBAND_LIB"] != str(hook)
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 0, r.stderr
    assert not leak.exists()


def test_receipt_carries_producer_and_bead(rig):
    rig.dispatch("--role", "routine-execution", *rig.base_args(),
                 "--producer-identity", "gpt-6.1-sol", "--bead", "mk-abc.1",
                 CLAVAIN_DECISION_CONTEXT=rig.ctx)
    (rec,) = rig.receipts()
    assert rec["producer_identity"] == "gpt-6.1-sol"
    assert rec["bead_id"] == "mk-abc.1"


def test_failed_model_exit_is_a_failed_receipt_with_that_exit_code(rig):
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx, FAKE_EXIT=3)
    assert r.returncode == 3
    assert "fallback suppressed" in r.stderr
    (rec,) = rig.receipts()
    assert (rec["exit_code"], rec["outcome"]) == (3, "failed")
    assert len(rig.calls()) == 1  # a terminal error does not fall through to a second seat


def test_receipt_appends_one_line_per_dispatch(rig):
    for _ in range(2):
        rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx)
    recs = rig.receipts()
    assert len(recs) == 2
    assert recs[0]["dispatch_id"] != recs[1]["dispatch_id"]


# ---------------------------------------------------------------------------
# Refusals before any model starts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["validation", "cross-lab-review", "plan-review"])
def test_review_roles_require_a_producer_identity(rig, role):
    r = rig.dispatch("--role", role, *rig.base_args(), CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 1
    assert r.stderr.strip() == (
        f"Error: role '{role}' requires --producer-identity so producer and validator "
        "models can be separated")
    assert rig.calls() == [] and rig.ic_calls() == [] and rig.receipts() == []


@pytest.mark.parametrize("flag,value", [
    ("--to", "claude"), ("--model", "x"), ("--tier", "fast"),
    ("--reasoning-effort", "high"), ("--service-tier", "fast"),
])
def test_role_cannot_be_combined_with_a_manual_seat_flag(rig, flag, value):
    r = rig.dispatch("--role", "routine-execution", flag, value, *rig.base_args())
    assert r.returncode == 1
    assert r.stderr.strip() == (
        "Error: --role cannot be combined with --to, --model, --tier, "
        "--reasoning-effort, or --service-tier")
    assert rig.calls() == [] and rig.ic_calls() == []


def test_inline_json_context_is_refused(rig):
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     CLAVAIN_DECISION_CONTEXT='{"reasons":[]}')
    assert r.returncode == 1
    assert r.stderr.strip() == (
        "Error: CLAVAIN_DECISION_CONTEXT / --context-file must be the path of a JSON file, "
        "not inline JSON")
    assert rig.calls() == [] and rig.ic_calls() == []


def test_unreadable_context_file_is_refused(rig):
    missing = rig.t / "missing.json"
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     CLAVAIN_DECISION_CONTEXT=missing)
    assert r.returncode == 1
    assert rig.norm(r.stderr.strip()) == (
        "Error: CLAVAIN_DECISION_CONTEXT / --context-file '<T>/missing.json' "
        "is not a readable file")
    assert rig.calls() == [] and rig.ic_calls() == []


def test_missing_ic_is_refused(rig):
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     env_path=o.SYSTEM_PATH, CLAVAIN_DECISION_CONTEXT=rig.ctx)
    if shutil.which("ic", path=o.SYSTEM_PATH):
        pytest.skip("a system ic is installed on the minimal PATH")
    assert r.returncode == 1
    assert r.stderr.strip() == "Error: ic is required for --role dispatch"
    assert rig.receipts() == []


def test_ic_rejecting_the_context_names_the_context(rig):
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx,
                     FAKE_IC_RC=1, FAKE_IC_STDERR="ic: unknown field foo")
    assert r.returncode == 1
    assert "ic: unknown field foo" in r.stderr
    assert ("Error: Intercore could not resolve dispatch role 'routine-execution' "
            "(the decision context was rejected: it has an unknown key or invalid JSON; "
            "see the error above)") in r.stderr
    assert rig.calls() == [] and rig.receipts() == []


def test_ic_failure_without_a_context_does_not_blame_the_context(rig):
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     FAKE_IC_RC=1, FAKE_IC_STDERR="ic: boom")
    assert r.returncode == 1
    assert "Error: Intercore could not resolve dispatch role 'routine-execution'" in r.stderr
    assert "decision context was rejected" not in r.stderr
    assert rig.calls() == []


def test_ic_failure_with_a_valid_context_does_not_blame_the_context(rig):
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx,
                     FAKE_IC_RC=1, FAKE_IC_STDERR="ic: boom")
    assert r.returncode == 1
    assert "ic: boom" in r.stderr
    assert rig.calls() == []


@pytest.mark.parametrize("role", ["bogus", "release-authority"])
def test_route_for_a_different_role_is_refused_without_a_model_call(rig, role):
    # The fake ic answers with the routine-execution route whatever it is asked.
    r = rig.dispatch("--role", role, *rig.base_args(), CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 128
    assert "fallback suppressed" in r.stderr
    assert rig.calls() == []
    (rec,) = rig.receipts()
    assert (rec["role"], rec["exit_code"], rec["outcome"]) == (role, 128, "failed")


# ---------------------------------------------------------------------------
# Option validation
# ---------------------------------------------------------------------------

def test_bead_id_charset_is_validated(rig):
    r = rig.dispatch("--bead", "bad id", "--role", "routine-execution", *rig.base_args())
    assert r.returncode == 1
    assert r.stderr.strip() == (
        "Error: invalid --bead; expected a non-empty ID containing only letters, digits, "
        "_, ., :, or -")
    assert rig.calls() == [] and rig.ic_calls() == []


@pytest.mark.parametrize("bead", ["mk-j1zww.12", "A_b:c.d-9"])
def test_bead_id_accepts_the_documented_charset(rig, bead):
    r = rig.dispatch("--bead", bead, "--role", "routine-execution", *rig.base_args(),
                     "--dry-run")
    assert r.returncode == 0, r.stderr


# At the baseline these flags were accepted and ignored with a warning on a
# non-review role (the seat then ran); today they are refused before any call.
# Both behaviors are pinned. Which one is required comes from the git history of
# the checkout (o.dispatch_feature), not from the script text, so a change that
# brings the old warn-and-run behavior back into a current tree fails.


def test_review_scratch_on_a_non_review_role(rig):
    r = rig.dispatch("--role", "routine-execution", "--review-scratch", "x", *rig.base_args())
    if SCOPE_CHECK:
        assert r.returncode == 1
        assert r.stderr.strip() == "Error: --review-scratch applies to --role cross-lab-review only"
    else:
        assert r.returncode == 0
        assert "ignoring: --review-scratch" in r.stderr
    assert len(rig.calls()) == (0 if SCOPE_CHECK else 1)


def test_repo_flag_on_a_non_review_role(rig):
    r = rig.dispatch("--role", "routine-execution", "--repo", "x", *rig.base_args())
    if SCOPE_CHECK:
        assert r.returncode == 1
        assert r.stderr.strip() == (
            "Error: --repo/--repo-id/--pr/--head/--base apply to --role cross-lab-review only")
    else:
        assert r.returncode == 0
        assert "ignoring: --repo" in r.stderr
    assert len(rig.calls()) == (0 if SCOPE_CHECK else 1)


def test_review_input_needs_a_review_role(rig):
    r = rig.dispatch("--role", "routine-execution", "--review-input", "x", *rig.base_args())
    assert r.returncode == 1
    assert r.stderr.strip() == (
        "Error: --review-input/--review-packet require --role plan-review, validation, "
        "or cross-lab-review (got 'routine-execution')")


def test_help_exits_zero_and_names_the_role_option(rig):
    r = rig.dispatch("--help")
    assert r.returncode == 0
    assert r.stdout.startswith("clavain dispatch")
    assert "--role" in r.stdout and "--context-file <PATH>" in r.stdout
    assert rig.calls() == []


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def test_dry_run_prints_the_command_and_starts_nothing(rig):
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(), "--dry-run",
                     CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 0, r.stderr
    first = rig.norm(r.stdout.splitlines()[0])
    assert first.startswith("cd <T>/repo && claude --effort high --model claude-sonnet-5-5 ")
    assert first.endswith("> <T>/out.md")
    assert "# Would execute:" in r.stderr
    assert "# Prompt (" in r.stdout
    assert rig.calls() == []
    assert rig.receipts() == []
    assert not rig.out.exists()
    # ic was asked to resolve, but nothing was recorded as started.
    assert [c for c in rig.ic_calls() if c[:2] == ["route", "record"]] == []


# ---------------------------------------------------------------------------
# Real ic: refusals that come from the routing engine, and the dry-run table
# ---------------------------------------------------------------------------

@pytest.mark.requires_ic
def test_real_ic_refuses_the_reserved_release_authority_role(tmp_path):
    rig = _real_ic_rig(tmp_path)
    r = rig.dispatch("--role", "release-authority", *rig.base_args(), "--dry-run",
                     "--producer-identity", "claude-opus-5-5",
                     CLAVAIN_ROUTING_POLICY=o.policy_under_test(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 1
    assert r.stderr.strip().splitlines()[-1] == (
        "Error: role 'release-authority' is reserved for the main integrator and "
        "cannot be delegated")


@pytest.mark.requires_ic
def test_real_ic_refuses_an_unknown_role(tmp_path):
    rig = _real_ic_rig(tmp_path)
    r = rig.dispatch("--role", "no-such-role", *rig.base_args(), "--dry-run",
                     CLAVAIN_ROUTING_POLICY=o.policy_under_test(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 1
    assert "no-such-role" in r.stderr
    assert "Intercore could not resolve dispatch role 'no-such-role'" in r.stderr


@pytest.mark.requires_ic
def test_real_ic_refuses_an_unknown_classification_reason(tmp_path):
    rig = _real_ic_rig(tmp_path)
    rig.ctx.write_text(json.dumps({"reasons": ["not-a-reason"], "rationale": "x"}))
    r = rig.dispatch("--role", "routine-execution", *rig.base_args(), "--dry-run",
                     CLAVAIN_ROUTING_POLICY=o.policy_under_test(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 1
    assert "unknown classification reason" in r.stderr


@pytest.mark.requires_ic
def test_real_ic_review_role_refuses_without_producer(tmp_path):
    rig = _real_ic_rig(tmp_path)
    r = rig.dispatch("--role", "cross-lab-review", *rig.base_args(), "--dry-run",
                     CLAVAIN_ROUTING_POLICY=o.policy_under_test(),
                     CLAVAIN_DECISION_CONTEXT=rig.ctx)
    assert r.returncode == 1
    assert "requires --producer-identity" in r.stderr


def _dry_golden():
    return json.loads((o.GOLDEN / "dispatch_dry_run.json").read_text())["policies"]


def _dry_cases():
    sha = o.policy_sha256(o.policy_under_test())
    table = _dry_golden().get(sha)
    return sha, table


@pytest.mark.requires_ic
def test_dry_run_table_matches_golden(tmp_path):
    """Role -> CLI, model, effort and argv for every role, with and without reasons.

    A fake codex (version 9.9.9) is on PATH so the Astra seats' minimum-version
    gate passes on any host. A changed row is a changed dispatch decision.
    """
    sha, expected = _dry_cases()
    if expected is None:
        pytest.fail(f"no dispatch golden for policy {sha}; regenerate with "
                    "tests/orchcompat/gen_golden.py --dispatch")
    got = o.dispatch_dry_table(o.real_ic(), o.policy_under_test(), tmp_path)
    assert got == expected


def test_dry_golden_records_both_known_policies():
    # The baseline and the then-current policy are both pinned, so the same
    # golden gates the code before and after the later slices.
    assert len(_dry_golden()) >= 2


def test_dry_golden_covers_every_role_and_reason_set():
    for table in _dry_golden().values():
        assert len(table) == len(o.ROLES) * len(o.DRY_REASON_SETS)
        refused = {k.split("|")[0] for k, v in table.items() if v["rc"] != 0}
        assert refused == {"release-authority"}


# ---------------------------------------------------------------------------
# git is run without the caller's environment or config
# ---------------------------------------------------------------------------
def _commit(repo, name):
    (repo / name).write_text(name)
    ident = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                 GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    assert o.run_git("add", name, cwd=repo).returncode == 0
    r = o.run_git("commit", "-q", "-m", name, cwd=repo, **ident)
    assert r.returncode == 0, r.stderr
    return o.run_git("rev-parse", "HEAD", cwd=repo).stdout.strip()


def _hostile_git_env(monkeypatch, tmp_path):
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    assert o.run_git("init", "-q", cwd=decoy).returncode == 0
    template = tmp_path / "template"
    (template / "hooks").mkdir(parents=True)
    (template / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 1\n")
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = leaked\n[core]\n\thooksPath = /nonexistent\n")
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(decoy))
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(template))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "user.email")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "leaked@example.invalid")
    monkeypatch.setenv("HOME", str(tmp_path))
    return decoy, template


def test_hostile_git_variables_do_not_redirect_the_rig_repo(tmp_path, monkeypatch):
    decoy, template = _hostile_git_env(monkeypatch, tmp_path)
    before = sorted(p.name for p in (decoy / ".git").iterdir())
    rig = o.Rig(tmp_path / "rig")
    assert (rig.repo / ".git").is_dir(), "git init was redirected by the caller's GIT_DIR"
    assert sorted(p.name for p in (decoy / ".git").iterdir()) == before  # decoy untouched
    assert not (rig.repo / ".git" / "hooks" / "pre-commit").exists()  # template not used
    cfg = o.run_git("config", "--list", "--show-origin", cwd=rig.repo).stdout
    assert "leaked" not in cfg and "hooksPath" not in cfg


def test_hostile_git_variables_do_not_change_the_ancestry_answer(tmp_path, monkeypatch):
    repo = tmp_path / "real"
    repo.mkdir()
    assert o.run_git("init", "-q", "-b", "main", cwd=repo).returncode == 0
    first = _commit(repo, "a")
    assert o.run_git("checkout", "-q", "-b", "side", cwd=repo).returncode == 0
    side = _commit(repo, "s")
    assert o.run_git("checkout", "-q", "main", cwd=repo).returncode == 0
    second = _commit(repo, "b")
    # GIT_DIR now names a repository that has none of these commits.
    _hostile_git_env(monkeypatch, tmp_path)
    assert o.is_ancestor(repo, first) is True
    assert o.is_ancestor(repo, second) is True
    assert o.is_ancestor(repo, side) is False


def test_git_init_ignores_a_template_even_when_one_is_handed_in(tmp_path):
    # Second layer: besides the allowlist, `git init` is given an empty template.
    template = tmp_path / "template"
    (template / "hooks").mkdir(parents=True)
    (template / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 1\n")
    repo = tmp_path / "r"
    assert o.run_git("init", "-q", str(repo), GIT_TEMPLATE_DIR=template).returncode == 0
    assert (repo / ".git").is_dir()
    assert not (repo / ".git" / "hooks" / "pre-commit").exists()


def test_git_runs_with_system_and_global_config_switched_off(tmp_path):
    env = o.git_env()
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert not any(k in env for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_TEMPLATE_DIR", "GIT_INDEX_FILE"))
    # and the effect: a user-level config file in HOME is not read
    (tmp_path / ".gitconfig").write_text("[user]\n\tname = leaked\n")
    repo = tmp_path / "r"
    assert o.run_git("init", "-q", str(repo), HOME=tmp_path).returncode == 0
    assert o.run_git("config", "user.name", cwd=repo, HOME=tmp_path).stdout.strip() == ""
