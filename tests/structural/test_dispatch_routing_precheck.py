"""Opt-in CLAVAIN_ROUTING_PRECHECK guard in dispatch.sh, via a stub dispatch harness.

`ic` is a recording stub that always fails role resolution, so no model, BB seat
or network call can happen: reaching the stub means the guard let dispatch proceed.
"""
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

POLICY = {"dispatch": {
    "roles": {"routine-execution": "exec"},
    "tiers": {"exec": {"model": "claude-sonnet-5-5", "reasoning_effort": "high", "fallbacks": ["sol"]},
              "sol": {"model": "gpt-6.1-sol", "reasoning_effort": "medium", "backend": "codex"}}}}
RELEASED = {"models": [{"id": "claude-sonnet-5-5"}, {"id": "gpt-6.1-sol"}]}
SEAT = {"role": "routine-execution", "model": "claude-sonnet-5-5", "reasoning_effort": "high"}


@pytest.fixture
def harness(tmp_path):
    bins = tmp_path / "bin"
    bins.mkdir()
    calls = tmp_path / "ic-calls"
    (bins / "ic").write_text(f'#!/bin/sh\necho "$*" >> {calls}\nexit 1\n')
    (bins / "ic").chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    files = {name: tmp_path / name for name in ("routing.yaml", "models.json", "seats.json")}
    files["routing.yaml"].write_text(yaml.safe_dump(POLICY))
    files["models.json"].write_text(json.dumps(RELEASED))
    files["seats.json"].write_text(json.dumps({"seats": [SEAT]}))

    def run(script=SCRIPTS / "dispatch.sh", role="routine-execution", args=None, **env):
        base = {k: v for k, v in os.environ.items() if not k.startswith(("CLAVAIN_", "BB_"))}
        base.update(PATH=f"{bins}:{base['PATH']}", CLAVAIN_ROUTING_POLICY=str(files["routing.yaml"]),
                    CLAVAIN_POOL_HEADROOM="0")
        base.update(env)
        calls.write_text("")
        routing_args = ["--role", role] if args is None else args
        result = subprocess.run(["bash", str(script), *routing_args, "--dry-run", "-C", str(work),
                                 "-o", str(tmp_path / "out.txt"), "prompt"],
                                capture_output=True, text=True, timeout=60, env=base, cwd=work)
        return result, calls.read_text()

    def enabled(**extra):
        return {"CLAVAIN_ROUTING_PRECHECK": "1", "CLAVAIN_RELEASED_MODELS": str(files["models.json"]),
                "CLAVAIN_SEAT_RECORDS": str(files["seats.json"]), **extra}

    return run, enabled, files, tmp_path


def refused(result, calls):
    return result.returncode != 0 and calls == "" and "routing precheck" in result.stderr


def test_unset_and_zero_are_byte_identical(harness):
    run, enabled, files, _ = harness
    files["seats.json"].write_text("{")  # would fail the guard if it ran
    unset, unset_calls = run()
    zero, zero_calls = run(CLAVAIN_ROUTING_PRECHECK="0", CLAVAIN_RELEASED_MODELS="/nonexistent")
    assert unset_calls and zero_calls  # reached the stub ic
    assert (unset.returncode, unset.stdout, unset.stderr) == (zero.returncode, zero.stdout, zero.stderr)
    assert "routing precheck" not in unset.stderr


def test_enabled_clean_evidence_proceeds_to_resolution(harness):
    run, enabled, *_ = harness
    result, calls = run(**enabled())
    assert "route dispatch --role=routine-execution" in calls
    assert "routing precheck" not in result.stderr
    assert result.stdout == ""  # checker report goes to stderr, never dispatch stdout


def test_enabled_drift_refuses_before_resolution(harness):
    run, enabled, files, _ = harness
    files["seats.json"].write_text(json.dumps({"seats": [{**SEAT, "reasoning_effort": "low"}]}))
    assert refused(*run(**enabled()))


def test_enabled_stale_pin_refuses(harness):
    run, enabled, files, _ = harness
    files["models.json"].write_text(json.dumps({"models": [{"id": "other"}]}))
    assert refused(*run(**enabled()))


@pytest.mark.parametrize("seats", [{"seats": []}, {"seats": [{**SEAT, "role": "other"}]}])
def test_enabled_unknown_evidence_refuses(harness, seats):
    run, enabled, files, _ = harness
    files["seats.json"].write_text(json.dumps(seats))
    assert refused(*run(**enabled()))


@pytest.mark.parametrize("missing", ["CLAVAIN_RELEASED_MODELS", "CLAVAIN_SEAT_RECORDS"])
def test_enabled_without_evidence_paths_refuses(harness, missing):
    run, enabled, *_ = harness
    env = enabled()
    env.pop(missing)
    assert refused(*run(**env))


def test_enabled_with_unreadable_evidence_refuses(harness):
    run, enabled, files, _ = harness
    assert refused(*run(**enabled(CLAVAIN_SEAT_RECORDS=str(files["seats.json"]) + ".missing")))


def test_enabled_with_unknown_role_refuses(harness):
    run, enabled, *_ = harness
    assert refused(*run(role="not-a-role", **enabled()))


def test_enabled_with_ambiguous_setting_refuses(harness):
    run, enabled, *_ = harness
    assert refused(*run(**enabled(CLAVAIN_ROUTING_PRECHECK="yes")))


def test_enabled_with_absent_checker_cannot_bypass(harness):
    run, enabled, files, tmp = harness
    shadow = tmp / "shadow"
    shadow.mkdir()
    for entry in SCRIPTS.iterdir():
        if entry.name != "routing-check.py":
            (shadow / entry.name).symlink_to(entry)
    result, calls = run(script=shadow / "dispatch.sh", **enabled())
    assert refused(result, calls) and "routing-check.py is missing" in result.stderr
    # The same shadow tree without the opt-in still dispatches (guard truly opt-in).
    assert run(script=shadow / "dispatch.sh")[1]


# Round 2: replayed decisions and bare policy tiers must not bypass the guard.
def resolved_args(decision, role=None):
    args = ["--role-resolved", "--resolved-route-json", json.dumps(decision),
            "--to", "codex", "--model", "gpt-6.1-sol"]
    if role is not None:
        args += ["--role", role]
    return args


@pytest.mark.parametrize("decision", [
    {"requested_role": "routine-execution"},
    {"profile": {"role": "routine-execution"}},
])
def test_resolved_role_is_derived_and_drift_refuses(harness, decision):
    run, enabled, files, _ = harness
    files["seats.json"].write_text(json.dumps({"seats": [{**SEAT, "reasoning_effort": "low"}]}))
    assert refused(*run(args=resolved_args(decision), **enabled()))


@pytest.mark.parametrize("decision,role", [
    ({}, None), ({}, "routine-execution"),
    ({"requested_role": None}, None),
    ({"requested_role": ["routine-execution"]}, None),
    ({"requested_role": "routine-execution", "profile": {"role": "validation"}}, None),
    ({"requested_role": "routine-execution"}, "validation"),
    ({"requested_role": "ghost"}, None),
])
def test_resolved_missing_invalid_or_conflicting_role_refuses(harness, decision, role):
    run, enabled, *_ = harness
    assert refused(*run(args=resolved_args(decision, role), **enabled()))


@pytest.mark.parametrize("evidence", ["missing", "unknown", "malformed", "clean"])
def test_resolved_rechecks_evidence(harness, evidence):
    run, enabled, files, _ = harness
    if evidence == "unknown":
        files["seats.json"].write_text('{"seats": []}')
    elif evidence == "malformed":
        files["seats.json"].write_text('{')
    env = enabled()
    if evidence == "missing":
        env.pop("CLAVAIN_SEAT_RECORDS")
    result, calls = run(args=resolved_args({"requested_role": "routine-execution"}), **env)
    if evidence == "clean":
        assert '"status": "clean"' in result.stderr
        assert "routing precheck" not in result.stderr
    else:
        assert refused(result, calls)


@pytest.mark.parametrize("args", [resolved_args({}), ["--tier", "exec"],
                                    ["--to", "claude", "--tier", "exec"]])
def test_other_paths_unset_and_zero_are_byte_identical(harness, args):
    run, _, files, _ = harness
    files["seats.json"].write_text('{')
    unset, _ = run(args=args)
    zero, _ = run(args=args, CLAVAIN_ROUTING_PRECHECK="0")
    assert (unset.returncode, unset.stdout, unset.stderr) == (zero.returncode, zero.stdout, zero.stderr)
    assert "routing precheck" not in unset.stderr


@pytest.mark.parametrize("engine", [None, "claude"])
def test_policy_tier_path_rejects_drift(harness, engine):
    run, enabled, files, _ = harness
    files["seats.json"].write_text(json.dumps({"seats": [{**SEAT, "reasoning_effort": "low"}]}))
    args = ["--tier", "exec"] + (["--to", engine] if engine else [])
    assert refused(*run(args=args, **enabled()))


def test_resolved_checks_supplied_policy(harness):
    run, enabled, files, tmp = harness
    policy = json.loads(json.dumps(POLICY))
    policy["dispatch"]["tiers"]["exec"]["model"] = "gpt-5.6-sol"
    stale = tmp / "resolved-policy.yaml"
    stale.write_text(yaml.safe_dump(policy))
    decision = {"requested_role": "routine-execution", "policy_source": str(stale)}
    assert refused(*run(args=resolved_args(decision), **enabled()))


def test_tier_checks_discovered_policy(harness):
    run, enabled, _, tmp = harness
    policy = json.loads(json.dumps(POLICY))
    policy["dispatch"]["tiers"]["exec"]["model"] = "gpt-5.6-sol"
    stale = tmp / "tier-policy.yaml"
    stale.write_text(yaml.safe_dump(policy))
    result, calls = run(args=["--tier", "exec"],
                        **enabled(CLAVAIN_ROUTING_POLICY="", CLAVAIN_ROUTING_CONFIG=str(stale)))
    assert refused(result, calls)
    assert '"subject": "tier:exec"' in result.stderr and '"kind": "retired-pin"' in result.stderr


@pytest.mark.parametrize("model", ["gpt-5.6-sol", "claude-sonnet-5", "gpt-6-astra", "unknown-model"])
def test_replayed_execution_model_must_match_role(harness, model):
    run, enabled, *_ = harness
    args = resolved_args({"requested_role": "routine-execution"})
    args[-1] = model
    assert refused(*run(args=args, **enabled()))


@pytest.mark.parametrize("extra", [
    ["--resolved-profile-ref", "exec"],
    ["--resolved-profile-ref", "ghost"],
    ["--reasoning-effort", "high"],
    ["--resolved-profile-json", '{"profile_ref":"sol","profile":{"model":"gpt-5.6-sol"}}'],
    ["--resolved-profile-json", '{"profile_ref":"exec","profile":{"model":"gpt-6.1-sol"}}'],
    ["--resolved-profile-json", '{"profile_ref":"sol","profile":{"role":"validation"}}'],
    ["--resolved-profile-json", '{'],
    ["--resolved-profile-json", '[]'],
    ["--to", "claude"],
])
def test_replayed_execution_profile_must_match_candidate(harness, extra):
    run, enabled, *_ = harness
    assert refused(*run(args=resolved_args({"requested_role": "routine-execution"}) + extra,
                        **enabled()))


def test_replayed_declared_fallback_is_allowed(harness):
    run, enabled, *_ = harness
    decision = {"requested_role": "routine-execution", "profile_ref": "exec",
                "profile": {"role": "routine-execution", "model": "claude-sonnet-5-5"}}
    args = resolved_args(decision) + ["--resolved-profile-ref", "sol", "--reasoning-effort", "medium",
        "--resolved-profile-json", json.dumps({"profile_ref": "sol", "profile": {
            "role": "routine-execution", "model": "gpt-6.1-sol", "backend": "codex",
            "reasoning_effort": "medium"}})]
    result, _ = run(args=args, **enabled())
    assert '"status": "clean"' in result.stderr
    assert "routing precheck" not in result.stderr


@pytest.mark.parametrize("tier,var", [("fast", "CLAVAIN_CLAUDE_MODEL_FAST"),
                                      ("deep", "CLAVAIN_CLAUDE_MODEL_DEEP")])
def test_retired_claude_environment_override_refuses(harness, tier, var):
    run, enabled, *_ = harness
    args = ["--to", "claude", "--tier", tier]
    assert refused(*run(args=args, **enabled(**{var: "claude-sonnet-5"})))


@pytest.mark.parametrize("args", [resolved_args({"requested_role": "routine-execution"}) +
                                ["--model", "gpt-5.6-sol"], ["--to", "claude", "--tier", "fast"]])
def test_bad_execution_overrides_unset_and_zero_are_byte_identical(harness, args):
    run, _, *_ = harness
    env = {"CLAVAIN_CLAUDE_MODEL_FAST": "claude-sonnet-5"}
    unset, _ = run(args=args, **env)
    zero, _ = run(args=args, CLAVAIN_ROUTING_PRECHECK="0", **env)
    assert (unset.returncode, unset.stdout, unset.stderr) == (zero.returncode, zero.stdout, zero.stderr)


@pytest.mark.parametrize("var", ["CLAVAIN_CLAUDE_MODEL_FAST", "CLAVAIN_CLAUDE_MODEL_DEEP"])
def test_role_precheck_audits_environment_overrides(harness, var):
    run, enabled, *_ = harness
    assert refused(*run(**enabled(**{var: "gpt-5.6-sol"})))


@pytest.mark.parametrize("field", ["model", "model_identity"])
def test_replayed_profile_retired_alias_cannot_hide_behind_current_model(harness, field):
    run, enabled, files, _ = harness
    policy = json.loads(json.dumps(POLICY))
    policy["dispatch"]["model_aliases"] = {"gpt-5.6-sol": "gpt-6.1-sol"}
    files["routing.yaml"].write_text(yaml.safe_dump(policy))
    args = resolved_args({"requested_role": "routine-execution"}) + [
        "--resolved-profile-json", json.dumps({"profile_ref": "sol", "profile": {field: "gpt-5.6-sol"}})]
    assert refused(*run(args=args, **enabled()))


@pytest.mark.parametrize("tier,var", [("fast", "CLAVAIN_CLAUDE_MODEL_FAST"),
                                      ("deep", "CLAVAIN_CLAUDE_MODEL_DEEP")])
@pytest.mark.parametrize("path", ["tier", "role"])
def test_unreleased_environment_override_refuses_before_dispatch(harness, tier, var, path):
    run, enabled, *_ = harness
    args = ["--to", "claude", "--tier", tier] if path == "tier" else None
    result, calls = run(args=args, **enabled(**{var: "claude-nonexistent-99"}))
    assert refused(result, calls)
    assert '"kind": "unreleased-model"' in result.stderr
    assert f'"subject": "env:{var}"' in result.stderr


@pytest.mark.parametrize("var", ["CLAVAIN_CLAUDE_MODEL_FAST", "CLAVAIN_CLAUDE_MODEL_DEEP"])
@pytest.mark.parametrize("alias", ["sonnet", "opus", "haiku"])
def test_enabled_environment_policy_alias_proceeds_to_resolution(harness, var, alias):
    run, enabled, files, _ = harness
    policy = yaml.safe_load(files["routing.yaml"].read_text())
    policy["dispatch"]["model_aliases"] = {alias: "claude-sonnet-5-5"}
    files["routing.yaml"].write_text(yaml.safe_dump(policy))
    result, calls = run(**enabled(**{var: alias}))
    assert "route dispatch --role=routine-execution" in calls
    assert '"status": "clean"' in result.stderr
    assert "routing precheck" not in result.stderr
