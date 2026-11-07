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
# observed. All or none of these are present, so the test is strict both ways.
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
    extras = {k: rec.pop(k) for k in list(rec) if k in OBSERVED_RECEIPT}
    assert rec == CORE_RECEIPT
    assert extras in ({}, OBSERVED_RECEIPT), extras


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
# non-review role (the seat then ran); today they are refused before any call. Both behaviors are pinned, chosen by
# the presence of the refusal text in the script under test.
SCOPE_CHECK = "apply to --role cross-lab-review only" in o.DISPATCH.read_text()


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
