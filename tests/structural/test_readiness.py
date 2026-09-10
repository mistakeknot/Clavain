"""Preparation must establish native authorship before enabling task writes."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("readiness", Path(__file__).parents[2] / "scripts/readiness.py")
readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readiness)


@pytest.mark.parametrize("value", [
    {"reasons": [], "rationale": ""},
    {"reasons": ["invented"], "rationale": "An unknown classification"},
    {"reasons": "difficult-verification", "rationale": "Wrong type"},
    {"reasons": [], "rationale": "ok", "accepted": True},
    {"reasons": [], "rationale": 42},
    [],
])
def test_invalid_decision_cannot_enable_writes(value):
    with pytest.raises(ValueError):
        readiness.validate_decision(json.dumps(value))


def test_duplicate_keys_and_oversized_decision_are_rejected():
    with pytest.raises(ValueError):
        readiness.validate_decision('{"reasons":[],"rationale":"a","rationale":"b"}')
    with pytest.raises(ValueError):
        readiness.validate_decision(json.dumps({"reasons": [], "rationale": "a" * 65536}))


def test_routine_accountable_judgment_is_valid():
    value = {"reasons": [], "rationale": "Settled small edit; existing approval boundaries apply."}
    assert readiness.validate_decision(json.dumps(value)) == value


def native_codex(tmp_path, *, session="subject", sandbox="read-only", model="gpt-6-astra", effort="high"):
    value = {"reasons": ["difficult-verification"], "rationale": "Native boundaries require a canary."}
    rows = [
        {"type": "session_meta", "payload": {"id": session, "source": "exec", "thread_source": "user"}},
        {"type": "turn_context", "payload": {"turn_id": "turn-1", "model": model, "effort": effort,
            "approval_policy": "never", "sandbox_policy": {"type": sandbox}}},
        {"type": "response_item", "payload": {"type": "message", "id": "message-1", "role": "assistant",
            "phase": "final_answer", "content": [{"type": "output_text", "text": json.dumps(value)}]}},
    ]
    path = tmp_path / "native.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path, value


def test_binding_uses_native_message_and_turn_not_parent_enrollment(tmp_path):
    path, value = native_codex(tmp_path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows.insert(2, {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
        "input": 'text(await tools.exec_command({cmd:"cat README.md"}));'}})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    binding = readiness.bind_decision("codex", path, "subject", value)
    assert binding["message_id"] == "message-1"
    assert binding["turn_id"] == "turn-1"
    assert binding["session_id"] == "subject"
    assert binding["model"] == "gpt-6-astra"
    assert binding["effort"] == "high"
    assert len(binding["native_sha256"]) == 64


@pytest.mark.parametrize("change", [{"session": "foreign"}, {"sandbox": "workspace-write"},
                                     {"model": "other"}, {"effort": "low"}])
def test_foreign_or_writable_preparation_is_rejected(tmp_path, change):
    path, value = native_codex(tmp_path, **change)
    with pytest.raises(ValueError):
        readiness.bind_decision("codex", path, "subject", value)


def test_changed_record_and_linked_evidence_are_rejected(tmp_path):
    path, value = native_codex(tmp_path)
    with pytest.raises(ValueError):
        readiness.bind_decision("codex", path, "subject", dict(value, rationale="Parent replacement"))
    link = tmp_path / "alias.jsonl"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        readiness.bind_decision("codex", link, "subject", value)
    directory = tmp_path / "linked-dir"
    directory.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        readiness.bind_decision("codex", directory / path.name, "subject", value)


def test_claude_binding_requires_actual_structured_tool_authorship(tmp_path):
    value = {"reasons": [], "rationale": "Settled canary with explicit fixture bounds."}
    row = {"type": "assistant", "sessionId": "subject", "uuid": "native-row-1", "effort": "high",
        "message": {"id": "provider-message-1", "model": "claude-fable-5-1", "content": [
            {"type": "tool_use", "id": "tool-1", "name": "StructuredOutput", "input": value}]}}
    path = tmp_path / "native.jsonl"
    start = {"type": "user", "sessionId": "subject", "permissionMode": "dontAsk", "message": {"content": "Prepare only."}}
    end = {"type": "user", "sessionId": "subject", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tool-1", "content": "Structured output provided successfully"}]}}
    path.write_text("".join(json.dumps(r) + "\n" for r in (start, row, end)))
    binding = readiness.bind_decision("claude", path, "subject", value)
    assert binding["message_id"] == "provider-message-1"
    assert binding["native_row_id"] == "native-row-1"
    assert binding["tool_use_id"] == "tool-1"
    row["message"]["content"][0]["type"] = "tool_result"
    path.write_text("".join(json.dumps(r) + "\n" for r in (start, row, end)))
    with pytest.raises(ValueError):
        readiness.bind_decision("claude", path, "subject", value)


@pytest.mark.parametrize("tool", ["Write", "Bash", "Agent", "mcp__external", "Skill"])
def test_claude_mutating_or_unapproved_skill_call_cannot_bind(tmp_path, tool):
    value = {"reasons": [], "rationale": "A later decision cannot excuse earlier actions."}
    rows = [
        {"type": "user", "sessionId": "subject", "permissionMode": "dontAsk", "message": {"content": "Prepare."}},
        {"type": "assistant", "sessionId": "subject", "uuid": "a", "effort": "high", "message": {
            "id": "m1", "model": "claude-fable-5-1", "content": [
                {"type": "tool_use", "id": "bad", "name": tool, "input": {"skill": "forked"}},
                {"type": "tool_use", "id": "decision", "name": "StructuredOutput", "input": value}]}},
        {"type": "user", "sessionId": "subject", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "decision", "content": "ok"}]}},
    ]
    path = tmp_path / "native.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError):
        readiness.bind_decision("claude", path, "subject", value)


def test_delegated_codex_session_and_external_call_are_rejected(tmp_path):
    path, value = native_codex(tmp_path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["payload"]["thread_source"] = "subagent"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError):
        readiness.bind_decision("codex", path, "subject", value)
    rows[0]["payload"]["thread_source"] = "user"
    rows.insert(2, {"type": "response_item", "payload": {"type": "function_call", "name": "mcp__publish"}})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError):
        readiness.bind_decision("codex", path, "subject", value)


@pytest.mark.parametrize("row", [None, [], {"type": "response_item", "payload": None},
                                 {"type": "assistant", "sessionId": "subject", "message": None}])
def test_malformed_native_shapes_fail_as_not_ready(tmp_path, row):
    path = tmp_path / "native.jsonl"
    path.write_text(json.dumps(row) + "\n")
    for host in ("codex", "claude"):
        with pytest.raises(ValueError):
            readiness.bind_decision(host, path, "subject", {"reasons": [], "rationale": "test"})


def test_hardlinked_native_evidence_is_rejected(tmp_path):
    import os
    path, value = native_codex(tmp_path)
    os.link(path, tmp_path / "second-name")
    with pytest.raises(ValueError):
        readiness.bind_decision("codex", path, "subject", value)


def claude_rows():
    value = {"reasons": [], "rationale": "Settled work with retained boundaries."}
    rows = [
        {"type": "user", "sessionId": "subject", "permissionMode": "dontAsk", "message": {"content": "Prepare."}},
        {"type": "assistant", "sessionId": "subject", "uuid": "row", "effort": "high", "message": {
            "id": "message", "model": "claude-fable-5-1", "content": [
                {"type": "tool_use", "id": "decision", "name": "StructuredOutput", "input": value}]}},
        {"type": "user", "sessionId": "subject", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "decision", "content": "ok"}]}},
    ]
    return value, rows


@pytest.mark.parametrize("mutation", ["late-tool", "error-result", "missing-result", "second-prompt",
    "mode", "sidechain", "server-tool", "mcp-tool", "earlier-model", "earlier-effort"])
def test_claude_boundary_regressions(tmp_path, mutation):
    import copy
    value, rows = claude_rows()
    if mutation == "late-tool":
        later = copy.deepcopy(rows[1]); later["message"]["content"][0]["name"] = "Read"; rows.append(later)
    elif mutation == "error-result": rows[2]["message"]["content"][0]["is_error"] = True
    elif mutation == "missing-result": rows.pop()
    elif mutation == "second-prompt": rows.append({"type": "user", "sessionId": "subject", "message": {"content": "Again."}})
    elif mutation == "mode": rows[0]["permissionMode"] = "default"
    elif mutation == "sidechain": rows[1]["isSidechain"] = True
    elif mutation in ("server-tool", "mcp-tool"):
        rows[1]["message"]["content"].insert(0, {"type": "server_tool_use" if mutation == "server-tool" else "mcp_tool_use"})
    else:
        earlier = copy.deepcopy(rows[1]); earlier["message"]["content"] = [{"type": "text", "text": "Observed."}]
        if mutation == "earlier-model": earlier["message"]["model"] = "other"
        else: earlier["effort"] = "low"
        rows.insert(1, earlier)
    path = tmp_path / "native.jsonl"; path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError): readiness.bind_decision("claude", path, "subject", value)


@pytest.mark.parametrize("kind", ["web_search_call", "local_shell_call", "future_call"])
def test_codex_rejects_unknown_or_provider_side_call_types(tmp_path, kind):
    path, value = native_codex(tmp_path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows.insert(2, {"type": "response_item", "payload": {"type": kind}})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError): readiness.bind_decision("codex", path, "subject", value)


def test_deep_json_and_duplicate_reasons_fail_cleanly():
    for text in ("[" * 5000, '{"reasons":["capability-failure","capability-failure"],"rationale":"x"}',
                 '{"reasons":[],"rationale":"  "}'):
        with pytest.raises(ValueError): readiness.validate_decision(text)


def test_opus_requires_explicit_fallback_binding(tmp_path):
    value, rows = claude_rows(); rows[1]["message"]["model"] = "claude-opus-5"
    path = tmp_path / "native.jsonl"; path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError): readiness.bind_decision("claude", path, "subject", value)
    with pytest.raises(ValueError): readiness.bind_decision("claude", path, "subject", value, "claude-opus-5")
    fallback = {"reason": "fable-usage-limit", "user_authorization": "explicit test fixture authorization", "evidence_sha256": "a" * 64}
    result = readiness.bind_decision("claude", path, "subject", value, "claude-opus-5", fallback)
    assert result["assignment"] == "authorized-fallback"
    assert result["fallback"] == fallback


@pytest.mark.parametrize("digest", [None, 42, [], "z" * 64, "a" * 63])
def test_fallback_digest_must_be_sha256(digest):
    with pytest.raises(ValueError):
        readiness.validate_fallback(dict(reason="fable-usage-limit", user_authorization="authorized", evidence_sha256=digest))


@pytest.mark.parametrize("index", [0, 1, 2])
def test_codex_duplicate_identity_context_or_final_rejected(tmp_path, index):
    path, value = native_codex(tmp_path)
    rows = path.read_text().splitlines(); rows.append(rows[index]); path.write_text("\n".join(rows) + "\n")
    with pytest.raises(ValueError): readiness.bind_decision("codex", path, "subject", value)
