import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/task-delivery.py"


def subject():
    assert SCRIPT.exists(), "Intercore enrollment helper is not implemented"
    spec = importlib.util.spec_from_file_location("task_delivery", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def enrollment():
    return dict(schema_version=1, cohort_id="c", cohort_kind="internal-tooling", enrollment_id="e",
                bead_id="b", objective="Implement accounting", enrolled_at="2026-09-05T12:00:00Z",
                manifest_sha256="a" * 64, role="main-integrator", model="gpt-6-astra",
                parent_session_id="parent", implementation_dispatched=False,
                evidence_kind="prospective_manual_enrollment", execution_status="enrolled",
                independent_acceptance="pending")


def decision(kind, context, ident=548):
    return dict(id=ident, rule_matched=f"measured-delivery-{kind}", context_json=json.dumps(context),
                selected_model=context.get("model", "gpt-6-astra"), agent=context.get("role", "main-integrator"),
                session_id=context.get("session_id", context.get("parent_session_id")),
                bead_id=context.get("bead_id", "b"), decided_at=1788609600)


def binding():
    return dict(enrollment_id="e", cohort_id="c", manifest_sha256="a" * 64,
                provider="codex", session_id="s", thread_id="s", attempt_id="a1", role="deep-execution",
                model="gpt-6-astra", configuration_sha256="b" * 64, executable="/bin/codex",
                executable_sha256="c" * 64, evidence_path="/evidence/s.jsonl")


def test_adopts_manual_enrollment_decisions_without_recreating():
    manifest = subject().export_manifest([decision("enrollment", enrollment())], "c")
    assert manifest["tasks"][0]["decision_id"] == 548
    assert manifest["tasks"][0]["execution_status"] == "enrolled"
    assert manifest["bindings"] == []
    assert manifest["cohort_kind"] == "internal-tooling"
    assert manifest["authoritative_decision_ids"] == [548]


def test_binding_and_failed_execution_do_not_grant_acceptance():
    records = [decision("enrollment", enrollment()), decision("binding", binding(), 549),
               decision("execution", dict(enrollment_id="e", cohort_id="c", execution_status="failed",
                                            attempt_id="a1", evidence_refs=["receipt.json"]), 550)]
    manifest = subject().export_manifest(records, "c")
    assert manifest["tasks"][0]["execution_status"] == "failed"
    assert manifest["tasks"][0]["independent_acceptance"] == "pending"
    assert manifest["bindings"][0]["binding_decision_id"] == 549
    assert manifest["tasks"][0]["execution_records"][0]["decision_id"] == 550


def test_conflicting_enrollment_reuse_is_rejected():
    with pytest.raises(ValueError, match="conflicting enrollment"):
        subject().export_manifest([decision("enrollment", enrollment()),
            decision("enrollment", enrollment() | {"objective": "Different task"}, 549)], "c")


def test_same_model_or_producer_cannot_accept_own_task():
    receipt = dict(enrollment_id="e", cohort_id="c", status="accepted", reviewer_identity="p",
                   producer_identity="p", reviewer_model="gpt-6-astra", producer_model="gpt-6-astra",
                   evidence_refs=["review.json"])
    with pytest.raises(ValueError, match="independent"):
        subject().validate_record("acceptance", receipt, [decision("enrollment", enrollment())])
    receipt["reviewer_identity"] = "different-session"
    with pytest.raises(ValueError, match="independent"):
        subject().validate_record("acceptance", receipt, [decision("enrollment", enrollment())])


def test_acceptance_keeps_independent_identity_and_decision_evidence():
    receipt = dict(enrollment_id="e", cohort_id="c", status="accepted", reviewer_identity="reviewer",
                   producer_identity="parent", reviewer_model="claude-fable-5-1", producer_model="gpt-6-astra",
                   evidence_refs=["review.json"], reviewer_binding_decision_id=550)
    review_binding = binding() | dict(session_id="reviewer", thread_id="reviewer", model="claude-fable-5-1", role="validation")
    records = [decision("enrollment", enrollment()), decision("binding", review_binding, 550), decision("acceptance", receipt, 551)]
    result = subject().export_manifest(records, "c")
    assert result["tasks"][0]["independent_acceptance"]["decision_id"] == 551
    assert result["tasks"][0]["execution_status"] == "enrolled"


@pytest.mark.parametrize("change", [
    {"implementation_dispatched": True}, {"enrolled_at": "bad-date"},
    {"manifest_sha256": "bad"}, {"objective": ""},
])
def test_invalid_or_retrospective_enrollment_rejected(change):
    with pytest.raises(ValueError):
        subject().validate_record("enrollment", enrollment() | change, [])


def test_binding_must_match_enrollment_hash_and_cohort():
    with pytest.raises(ValueError, match="manifest"):
        subject().validate_record("binding", binding() | {"manifest_sha256": "f" * 64},
                                  [decision("enrollment", enrollment())])
    with pytest.raises(ValueError, match="cohort"):
        subject().validate_record("binding", binding() | {"cohort_id": "other"},
                                  [decision("enrollment", enrollment())])


def test_missing_native_binding_identity_remains_explicit():
    b = binding() | dict(session_id=None, thread_id=None, evidence_path=None,
                         identity_coverage="incomplete", missing_identity_reason="runtime did not expose native session")
    result = subject().validate_record("binding", b, [decision("enrollment", enrollment())])
    assert result["session_id"] is None
    assert result["identity_coverage"] == "incomplete"


def test_intervention_does_not_infer_active_minutes():
    records = [decision("enrollment", enrollment()), decision("intervention",
        dict(cohort_id="c", enrollment_id="e", kind="clarification", elapsed_minutes=20), 549)]
    manifest = subject().export_manifest(records, "c")
    assert manifest["tasks"][0]["human_interventions"][0].get("active_minutes_estimate") is None


def test_reconciliation_appends_without_rewriting_attempt():
    records = [decision("enrollment", enrollment()), decision("execution",
        dict(cohort_id="c", enrollment_id="e", execution_status="failed", attempt_id="a1",
             failure_class="worker_outcome_indeterminate", evidence_refs=["original"]), 549),
        decision("reconciliation", dict(cohort_id="c", enrollment_id="e", attempt_id="a1",
             terminal_decision_id=549, outcome="observed_success", evidence_refs=["later"]), 550)]
    task = subject().export_manifest(records, "c")["tasks"][0]
    assert task["execution_status"] == "failed"
    assert task["execution_records"][0]["failure_class"] == "worker_outcome_indeterminate"
    assert task["reconciliations"][0]["terminal_decision_id"] == 549


def test_dispatch_is_canonical_and_requires_explicit_role(tmp_path):
    module = subject()
    args, env, receipt = module.prepare_dispatch([decision("enrollment", enrollment())], "e", "deep-execution",
                                               ["--prompt-file", str(tmp_path / "prompt.md"), "-C", str(tmp_path)])
    assert Path(args[1]).resolve() == SCRIPT.parent / "dispatch.sh"
    assert args[2:4] == ["--role", "deep-execution"]
    assert env["CLAVAIN_TASK_ENROLLMENT_ID"] == "e"
    assert env["CLAVAIN_TASK_MANIFEST_SHA256"] == "a" * 64
    assert env["CLAVAIN_DISPATCH_ID"] == receipt["dispatch_id"]
    assert receipt["dispatcher_sha256"]
    for forbidden in [["--tier", "deep"], ["--role=validation"], ["--model=gpt-other"], ["--to", "kimi"]]:
        with pytest.raises(ValueError, match="role"):
            module.prepare_dispatch([decision("enrollment", enrollment())], "e", "deep-execution", forbidden)


def test_dispatch_audit_is_composed_into_attempts_without_fabricated_native_identity():
    dispatched = dict(cohort_id="c", enrollment_id="e", dispatch_id="d1", role="deep-execution")
    audit = dict(id=550, rule_matched="dispatch-profile", dispatch_id="d1", context_json=json.dumps(dict(
        dispatch_id="d1", attempt_id="a1", state="failed", terminal=True,
        execution=dict(backend="codex", model="gpt-6-astra", session_id=""),
        result=dict(failure_class="terminal_error"))))
    records = [decision("enrollment", enrollment()), decision("dispatch-request", dispatched, 549), audit]
    manifest = subject().export_manifest(records, "c")
    assert manifest["tasks"][0]["execution_records"][0]["attempt_id"] == "a1"
    assert manifest["bindings"][0]["session_id"] is None
    assert manifest["bindings"][0]["identity_coverage"] == "incomplete"


def test_real_ic_record_and_export_round_trip(tmp_path):
    subject()
    ic = shutil.which("ic")
    if not ic:
        pytest.skip("Intercore CLI unavailable")
    db = tmp_path / "intercore.db"
    init = subprocess.run([ic, f"--db={db}", "init"], text=True, capture_output=True, cwd=tmp_path)
    assert init.returncode == 0, init.stderr
    data = tmp_path / "enrollment.json"
    data.write_text(json.dumps(enrollment()))
    base = [sys.executable, str(SCRIPT), "--db", str(db), "--ic", ic]
    first = subprocess.run(base + ["record", "--kind", "enrollment", "--record", str(data)], text=True, capture_output=True)
    assert first.returncode == 0, first.stderr
    second = subprocess.run(base + ["record", "--kind", "enrollment", "--record", str(data)], text=True, capture_output=True)
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout)["id"] == json.loads(second.stdout)["id"]
    exported = subprocess.run(base + ["export", "--cohort", "c"], text=True, capture_output=True)
    assert exported.returncode == 0, exported.stderr
    manifest = json.loads(exported.stdout)
    assert len(manifest["tasks"]) == 1
    assert manifest["authority"]["kind"] == "intercore-routing-decisions"


@pytest.mark.parametrize("real_ic", [False, True])
def test_role_audit_preserves_task_envelope_and_explicit_store(tmp_path, real_ic):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    recorder = fake_bin / "ic"
    recorder.write_text('#!/bin/sh\npwd > "$AUDIT_CWD"\nprintf "%s\\n" "$@" > "$AUDIT_ARGS"\n')
    recorder.chmod(0o755)
    project = tmp_path / "project"
    project.mkdir()
    database = tmp_path / "store" / "intercore.db"
    database.parent.mkdir()
    if real_ic:
        native_ic = shutil.which("ic")
        if not native_ic: pytest.skip("Intercore CLI unavailable")
        result = subprocess.run([native_ic, f"--db={database}", "init"], cwd=database.parent, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    else:
        database.touch()
    env = os.environ | dict(PATH=f"{fake_bin}:{os.environ['PATH']}", AUDIT_CWD=str(tmp_path / "cwd"),
        AUDIT_ARGS=str(tmp_path / "args"), WORKDIR=str(project), CLAVAIN_TASK_INTERCORE_DB=str(database),
        CLAVAIN_TASK_ENROLLMENT_ID="e", CLAVAIN_TASK_MANIFEST_SHA256="a" * 64, CLAVAIN_TASK_COHORT_ID="c",
        ROLE="deep-execution", ROLE_RESOLVED="true", ENGINE="flere", MODEL="m", DISPATCH_ID="d", ATTEMPT_ID="a",
        RESOLVED_PROFILE_REF="p", DISPATCH_SESSION_ID="parent", OUTPUT="", REASONING_EFFORT="high", SERVICE_TIER="standard",
        SANDBOX="read-only")
    if real_ic:
        env["PATH"] = os.environ["PATH"]
    result = subprocess.run(["bash", "-c", 'source "$1"; _record_role_routing_decision 0 success completed',
        "bash", str(SCRIPT.parent / "lib-dispatch-audit.sh")], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    if real_ic:
        result = subprocess.run([native_ic, f"--db={database}", "--json", "route", "list"],
                                cwd=database.parent, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        row = json.loads(result.stdout)[0]
        assert row["project_dir"] == str(project)
        payload = json.loads(row["context_json"])
    else:
        args = (tmp_path / "args").read_text().splitlines()
        assert f"--db={database}" in args
        assert f"--project={project}" in args
        payload = json.loads(next(a[len("--context="):] for a in args if a.startswith("--context=")))
    assert payload["task_envelope"] == dict(enrollment_id="e", manifest_sha256="a" * 64, cohort_id="c")


@pytest.mark.parametrize("observation", [None, {"executable": "/observed/claude", "configuration_coverage": "partial"}])
def test_role_audit_merges_observation_with_compatible_jq_grammar(tmp_path, observation):
    jq = os.environ.get("TASK_DELIVERY_TEST_JQ") or shutil.which("jq")
    if not jq:
        pytest.skip("jq unavailable")
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "jq").symlink_to(Path(jq).resolve())
    env = os.environ | dict(PATH=f"{tools}:{os.environ['PATH']}", WORKDIR=str(tmp_path), ENGINE="claude",
        MODEL="claude-fable-5-1", DISPATCH_ID="dispatch", ATTEMPT_ID="attempt", DISPATCH_SESSION_ID="parent",
        OUTPUT="", REASONING_EFFORT="", SERVICE_TIER="standard", SANDBOX="read-only", CHECKOUT_BEFORE="",
        DISPATCH_EXECUTION_OBSERVATION=json.dumps(observation))
    result = subprocess.run(["bash", "-c", 'source "$1"; _role_audit_context completed 0 success',
        "bash", str(SCRIPT.parent / "lib-dispatch-audit.sh")], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["execution"]["backend"] == "claude"
    assert payload["execution"]["model"] == "claude-fable-5-1"
    assert payload["terminal"] is True and payload["result"]["failure_class"] == "success"
    for key, value in (observation or {}).items():
        assert payload["execution"][key] == value


def test_wrapper_rejects_compact_model_and_resolved_profile_overrides():
    for flags in [["-mgpt-other"], ["--resolved-profile-json", "{}"], ["-c", "model=other"], ["-cmodel=other"]]:
        with pytest.raises(ValueError, match="role"):
            subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "deep-execution", flags)


def test_terminal_attempt_cannot_be_replaced_by_second_execution_receipt():
    terminal = dict(enrollment_id="e", cohort_id="c", execution_status="failed", attempt_id="a1", evidence_refs=["original"])
    records = [decision("enrollment", enrollment()), decision("execution", terminal, 549)]
    with pytest.raises(ValueError, match="immutable"):
        subject().validate_record("execution", terminal | dict(execution_status="completed"), records)


def test_latest_audit_native_identity_is_used_and_all_lifecycle_rows_retained():
    requested = dict(cohort_id="c", enrollment_id="e", dispatch_id="d1", role="deep-execution")
    initial = dict(dispatch_id="d1", attempt_id="a1", state="started", execution=dict(backend="codex", model="gpt-6-astra"))
    terminal = initial | dict(state="failed", execution=initial["execution"] | dict(session_id="actual", thread_id="actual"))
    records = [decision("enrollment", enrollment()), decision("dispatch-request", requested, 549)]
    for ident, audit in [(550, initial), (551, terminal)]:
        records.append(dict(id=ident, rule_matched="dispatch-profile", context_json=json.dumps(audit)))
    manifest = subject().export_manifest(records, "c")
    assert manifest["bindings"][0]["session_id"] == "actual"
    assert manifest["bindings"][0]["audit_decision_id"] == 551
    assert len(manifest["tasks"][0]["execution_records"]) == 2


def test_dispatch_request_without_audit_is_explicit_missing_attempt_coverage():
    records = [decision("enrollment", enrollment()), decision("dispatch-request",
        dict(cohort_id="c", enrollment_id="e", dispatch_id="d1", role="deep-execution"), 549)]
    manifest = subject().export_manifest(records, "c")
    assert manifest["bindings"][0]["dispatch_id"] == "d1"
    assert manifest["bindings"][0]["attempt_id"] is None
    assert manifest["bindings"][0]["identity_coverage"] == "incomplete"


def test_runtime_delegation_does_not_need_an_invented_dispatch_attempt():
    value = binding() | dict(attempt_id=None, identity_coverage="incomplete",
        missing_identity_reason="runtime delegation exposed native session but no dispatch attempt identity")
    assert subject().validate_record("binding", value, [decision("enrollment", enrollment())])["attempt_id"] is None


def test_binding_correction_preserves_original_decision_in_history():
    original = binding()
    correction = original | dict(session_id="parent", supersedes_binding_decision_id=549,
        correction_reason="Native request session is parent; native thread is child",
        correction_evidence_refs=[dict(path="/evidence/s.jsonl", line=4)])
    records = [decision("enrollment", enrollment()), decision("binding", original, 549),
               decision("binding", correction, 550)]
    manifest = subject().export_manifest(records, "c")
    assert len(manifest["bindings"]) == 1
    assert manifest["bindings"][0]["session_id"] == "parent"
    assert manifest["binding_history"][0]["session_id"] == "s"
    assert manifest["binding_history"][0]["decision_id"] == 549
    assert manifest["authoritative_decision_ids"] == [548, 549, 550]


def test_binding_correction_cannot_reassign_to_another_task():
    original = binding()
    other = enrollment() | dict(enrollment_id="e2", bead_id="b2")
    records = [decision("enrollment", enrollment()), decision("binding", original, 549), decision("enrollment", other, 550)]
    corrected = binding() | dict(enrollment_id="e2", supersedes_binding_decision_id=549,
        correction_reason="reassign", correction_evidence_refs=["ref"])
    with pytest.raises(ValueError, match="allocation"):
        subject().validate_record("binding", corrected, records)


def test_acceptance_cannot_lie_about_producer_model():
    receipt = dict(enrollment_id="e", cohort_id="c", status="accepted", reviewer_identity="integrator",
        producer_identity="child", reviewer_model="gpt-6-astra", producer_model="declared-other", evidence_refs=["review.json"])
    with pytest.raises(ValueError, match="independent"):
        subject().validate_record("acceptance", receipt, [decision("enrollment", enrollment())])


def test_null_runtime_attempt_does_not_hide_unrelated_dispatch():
    runtime = binding() | dict(attempt_id=None, identity_coverage="incomplete", missing_identity_reason="No native attempt")
    records = [decision("enrollment", enrollment()), decision("binding", runtime, 549),
        decision("dispatch-request", dict(cohort_id="c", enrollment_id="e", dispatch_id="d1", role="validation"), 550)]
    result = subject().export_manifest(records, "c")
    assert len(result["bindings"]) == 2
    assert result["bindings"][1]["dispatch_request_decision_id"] == 550
    assert result["bindings"][1]["audit_decision_id"] is None


@pytest.mark.parametrize("since", [None, "2026-09-05T11:59:59Z"])
def test_shared_binding_requires_prospective_boundary(since):
    value = binding()
    value.pop("enrollment_id")
    value.update(allocation="cohort_shared", since=since)
    with pytest.raises(ValueError, match="boundary"):
        subject().validate_record("binding", value, [decision("enrollment", enrollment())])


def test_dispatch_rejects_ambient_routing_overrides(monkeypatch):
    monkeypatch.setenv("CLAVAIN_ROLES_CONFIG", "/tmp/other-roles.yaml")
    with pytest.raises(ValueError, match="environment"):
        subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "deep-execution", ["prompt"])


def test_binding_cannot_validate_against_one_enrollment_and_allocate_another():
    with pytest.raises(ValueError,match="allocation"):
        subject().validate_record("binding",binding() | dict(allocation="e2"),[decision("enrollment",enrollment())])


def test_unbound_explicit_execution_exports_missing_usage_binding():
    records=[decision("enrollment",enrollment()),decision("binding",binding(),549),decision("execution",
        dict(cohort_id="c",enrollment_id="e",attempt_id="failed-repair",execution_status="failed",evidence_refs=["receipt"]),550)]
    manifest=subject().export_manifest(records,"c")
    repair=next(b for b in manifest["bindings"] if b["attempt_id"]=="failed-repair")
    assert repair["identity_coverage"]=="incomplete"
    assert repair["execution_decision_id"]==550


def test_dispatch_identity_reuse_cannot_overwrite_other_task():
    records=[decision("enrollment",enrollment()),decision("enrollment",enrollment() | dict(enrollment_id="e2",bead_id="b2"),549)]
    for ident,task in [(550,"e"),(551,"e2")]:
        records.append(decision("dispatch-request",dict(cohort_id="c",enrollment_id=task,dispatch_id="same",role="deep-execution"),ident))
    with pytest.raises(ValueError,match="dispatch.*identity"):
        subject().export_manifest(records,"c")


@pytest.mark.parametrize("original_kind,original_status,original_task",[("execution","running","e"),("binding","failed","e"),("execution","failed","e2")])
def test_reconciliation_requires_exact_own_terminal_execution(original_kind,original_status,original_task):
    records=[decision("enrollment",enrollment()),decision("enrollment",enrollment() | dict(enrollment_id="e2",bead_id="b2"),549),
        decision(original_kind,dict(cohort_id="c",enrollment_id=original_task,attempt_id="a",execution_status=original_status),550)]
    value=dict(cohort_id="c",enrollment_id="e",attempt_id="a",terminal_decision_id=550,outcome="observed_success",evidence_refs=["later"])
    with pytest.raises(ValueError,match="terminal"):
        subject().validate_record("reconciliation",value,records)


def test_role_resolved_internal_flag_cannot_bypass_canonical_resolution():
    with pytest.raises(ValueError,match="role"):
        subject().prepare_dispatch([decision("enrollment",enrollment())],"e","validation",["--role-resolved","--dry-run","prompt"])


def test_identical_dispatch_request_replay_preserves_task_and_decisions():
    request = dict(cohort_id="c", enrollment_id="e", dispatch_id="same", role="deep-execution")
    records = [decision("enrollment", enrollment()), decision("dispatch-request", request, 549),
               decision("dispatch-request", request, 550)]
    manifest = subject().export_manifest(records, "c")
    assert [b["enrollment_id"] for b in manifest["bindings"]] == ["e"]
    assert manifest["authoritative_decision_ids"] == [548, 549, 550]


@pytest.mark.parametrize("flags", [["--profile", "proxy"], ["-pproxy"], ["--oss"],
    ["--local-provider", "lmstudio"], ["--enable", "feature"], ["--disable", "feature"]])
def test_enrolled_dispatch_rejects_provider_and_feature_overrides(flags):
    with pytest.raises(ValueError, match="role"):
        subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "deep-execution", flags)


def test_enrolled_dispatch_rejects_ambient_usage_backend_fallback(monkeypatch):
    monkeypatch.setenv("CLAVAIN_REQUIRE_USAGE", "1")
    with pytest.raises(ValueError, match="environment"):
        subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "validation", ["--producer-identity", "codex/gpt-6-astra", "prompt"])


@pytest.mark.parametrize("field", ["enrollment_id", "cohort_id", "manifest_sha256"])
def test_audit_envelope_must_match_authoritative_dispatch_request(field):
    request = dict(cohort_id="c", enrollment_id="e", manifest_sha256="a" * 64, dispatch_id="d", role="deep-execution")
    envelope = {k:request[k] for k in ["enrollment_id", "cohort_id", "manifest_sha256"]}
    envelope[field] = "other"
    audit = dict(dispatch_id="d", attempt_id="a", task_envelope=envelope)
    records = [decision("enrollment", enrollment()), decision("dispatch-request", request, 549),
               dict(id=550, rule_matched="dispatch-profile", context_json=json.dumps(audit))]
    with pytest.raises(ValueError, match="envelope"):
        subject().export_manifest(records, "c")


@pytest.mark.parametrize("gap", [None, "missing", "identity", "invalid", "configuration", "conflict"])
def test_acceptance_record_requires_native_reviewer_proof(tmp_path, gap):
    core = dict(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    entries = [dict(type="user", uuid="u", parentUuid=None, sessionId="reviewer", promptId="p",
        timestamp="2026-09-05T12:00:01Z", message=dict(role="user", content="fixture")),
        dict(type="assistant", uuid="a", parentUuid="u", sessionId="reviewer", requestId="q", apiBlockIndex=0,
        timestamp="2026-09-05T12:00:02Z", message=dict(role="assistant", id="r", model="claude-fable-5-1",
        stop_reason="end_turn", content=[dict(type="text", text="fixture")],
        usage=core | dict(iterations=[core | dict(type="message")], output_tokens_details=dict(thinking_tokens=0),
            cache_creation=dict(ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=0))))]
    if gap == "identity": entries[1]["message"]["model"] = "gpt-6-astra"
    if gap == "invalid": entries[1]["message"]["usage"]["output_tokens"] = -1
    path = tmp_path / "reviewer.jsonl"
    if gap != "missing": path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    reviewer = binding() | dict(session_id="reviewer", thread_id="reviewer", provider="claude", model="claude-fable-5-1",
        role="validation", evidence_path=str(path))
    if gap == "configuration": reviewer.update(configuration_sha256=None, identity_coverage="incomplete", missing_identity_reason="not recorded")
    receipt = dict(enrollment_id="e", cohort_id="c", status="accepted", reviewer_identity="reviewer",
        producer_identity="parent", reviewer_model="claude-fable-5-1", producer_model="gpt-6-astra",
        reviewer_binding_decision_id=550, evidence_refs=["review.json"])
    records = [decision("enrollment", enrollment()), decision("binding", reviewer, 550)]
    if gap == "conflict": records.append(decision("binding", reviewer | dict(attempt_id="conflicting-attempt"), 552))
    if gap in (None, "configuration"):
        assert subject().validate_record("acceptance", receipt, records) == receipt
    else:
        with pytest.raises(ValueError, match="native evidence"):
            subject().validate_record("acceptance", receipt, records)
    result = subject().export_manifest(records + [decision("acceptance", receipt, 551)], "c")
    assert result["tasks"][0]["independent_acceptance"]["decision_id"] == 551


@pytest.mark.parametrize("flags", [["-p", "proxy"], ["-pproxy"], ["--profile=proxy"], ["--enable=feature"]])
def test_compact_provider_overrides_rejected(flags):
    with pytest.raises(ValueError, match="overrides"):
        subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "deep-execution", flags)


def test_disabled_ambient_usage_fallback_keeps_normal_role_dispatch(monkeypatch):
    monkeypatch.setenv("CLAVAIN_REQUIRE_USAGE", "0")
    assert subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "validation", ["--producer-identity", "codex/gpt-6-astra"])[0][3] == "validation"


@pytest.mark.parametrize("key", ["OPENAI_BASE_URL", "CODEX_HOME", "ANTHROPIC_BASE_URL", "CLAUDE_CONFIG_DIR"])
def test_enrolled_dispatch_rejects_provider_environment(monkeypatch, key):
    monkeypatch.setenv(key, "/tmp/elsewhere")
    with pytest.raises(ValueError, match="environment"):
        subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "validation", ["prompt"])


def test_allowlist_retains_auth_and_identity_without_inheriting_arbitrary_configuration(monkeypatch):
    monkeypatch.setenv("ARBITRARY_PROVIDER_SELECTOR", "bad")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-secret")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread")
    _, env, receipt = subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "validation", ["prompt"])
    assert "ARBITRARY_PROVIDER_SELECTOR" not in env
    assert env["ANTHROPIC_API_KEY"] == "synthetic-test-secret"
    assert env["CODEX_THREAD_ID"] == "thread"
    assert env["PATH"] == os.environ["PATH"] and env["HOME"] == os.environ["HOME"]
    assert "synthetic-test-secret" not in json.dumps(receipt)


@pytest.mark.parametrize("key,value", [("CLAUDE_CODE_ENTRYPOINT", "cli"), ("CLAUDE_PROJECT_DIR", "/synthetic/host-project")])
def test_claude_host_metadata_is_dropped_without_blocking_enrolled_dispatch(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    command, env, receipt = subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "validation", ["prompt"])
    assert command[3] == "validation"
    assert key not in env
    assert key not in json.dumps(receipt)
    if key == "CLAUDE_PROJECT_DIR":
        assert value not in json.dumps(receipt)


def test_dropping_known_host_metadata_keeps_unknown_reserved_selectors_rejected(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/synthetic/host-project")
    monkeypatch.setenv("CLAUDE_UNRECOGNIZED_CONFIG_SELECTOR", "synthetic-private-value")
    with pytest.raises(ValueError, match="CLAUDE_UNRECOGNIZED_CONFIG_SELECTOR") as error:
        subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "validation", ["prompt"])
    assert "synthetic-private-value" not in str(error.value)


def test_dispatch_request_does_not_mislabel_producer_as_selected_reviewer_model():
    _, _, receipt = subject().prepare_dispatch([decision("enrollment", enrollment())], "e", "validation", ["prompt"])
    assert receipt.get("model") is None
    assert receipt["producer_model"] == "gpt-6-astra"


def test_binding_requires_absolute_native_evidence_path():
    with pytest.raises(ValueError, match="absolute"):
        subject().validate_record("binding", binding() | dict(evidence_path="relative.jsonl"), [decision("enrollment", enrollment())])


def test_observed_executable_and_configuration_hashes_do_not_claim_full_provenance(tmp_path, monkeypatch):
    executable = tmp_path / "claude"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    settings = home / ".claude/settings.json"
    settings.write_text('{"env":{"secret":"fixture-secret"}}')
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("HOME", str(home))
    observed = subject().observe_execution("claude", tmp_path, {})
    assert observed["executable"] == str(executable)
    assert observed["executable_sha256"] == subject().sha256(executable)
    assert observed["configuration_sha256"] is None
    assert observed["configuration_coverage"] == "partial"
    assert "fixture-secret" not in json.dumps(observed)
    assert any(f.get("sha256") == subject().sha256(settings) for f in observed["configuration_observation"]["files"])


@pytest.mark.parametrize("mutation", [False, True])
def test_profiler_receipt_identifies_exact_invoked_bytes(tmp_path, mutation):
    profiler = tmp_path / "profiler.py"
    profiler.write_text("import pathlib\nprint('{}')\n" + ("pathlib.Path(__file__).write_text('changed')\n" if mutation else ""))
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{}')
    module = subject()
    if mutation:
        with pytest.raises(ValueError, match="changed"):
            module.invoke_profiler(profiler, manifest)
    else:
        report, code = module.invoke_profiler(profiler, manifest)
        assert code == 0
        assert report["profiler"] == dict(path=str(profiler), sha256=module.sha256(profiler), canonical=False)
