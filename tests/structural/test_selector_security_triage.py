"""mk-42j9.9: security-review triage, SHADOW ONLY.

The load-bearing tests here are the ones that prove Jev can never cancel,
skip, weaken or pre-approve a review: the vocabulary and authorize policy name
no such candidate, the shipped registry pins shadow, and an end-to-end sweep
over every mode and every Jev outcome shows the hook's stdout is empty or a
bare `ask`.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from selector_helpers import selector_socket_guard  # noqa: F401

import clavain_selector.selector as selector
from clavain_selector import credentials, egress, flags, jev_client, preparers, security_triage
from clavain_selector.adapters.claude_code import ClaudeCodeAdapter
from clavain_selector.adapters.base import HostEvent
from clavain_selector.contract import FallbackReason, Point

REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO / "config" / "selector-integrations.json"
FLAG = "CLAVAIN_SELECTOR_SECURITY_TRIAGE"
FORBIDDEN_WORDS = re.compile(r"skip|cancel|bypass|disable|approve|allow|suppress|dismiss|waive|ignore", re.I)


def _shipped_registry():
    return json.loads(REGISTRY_PATH.read_text())


def _entry():
    return _shipped_registry()["integrations"]["security_triage"]


def _event(tool="Edit", tool_input=None, root=None):
    root = root or Path("/proj")
    if tool_input is None:
        tool_input = {"file_path": str(root / "src" / "auth.py"), "old_string": "a", "new_string": "check_password(token)"}
    return HostEvent(point=Point.PRE_TOOL, session_id="s1", tool_name=tool, tool_input=tool_input)


# ---------------------------------------------------------------------------
# Static: the vocabulary, the policy and the registry entry cannot skip a review
# ---------------------------------------------------------------------------


def test_vocabulary_names_no_skip_capable_candidate():
    assert security_triage.VOCABULARY == {"keep_native_review", "light_check_suffices", "raise_scrutiny"}
    assert security_triage.vocabulary(Path("/anywhere")) == security_triage.VOCABULARY
    for cid in security_triage.VOCABULARY:
        assert not FORBIDDEN_WORDS.search(cid), cid
    assert "escalate" not in security_triage.VOCABULARY


def test_built_candidates_carry_no_skip_capable_text(tmp_path):
    built = security_triage.build(_event(root=tmp_path), tmp_path)
    assert {c.id for c in built.candidates} == security_triage.VOCABULARY
    for candidate in built.candidates:
        assert not FORBIDDEN_WORDS.search(candidate.id)
        # Payloads are inert labels, never a host action.
        assert candidate.payload == {"triage": candidate.id}


def test_only_raise_scrutiny_can_be_authorized_and_measurement_only_ids_cannot_be_emitted(tmp_path):
    built = security_triage.build(_event(root=tmp_path), tmp_path)
    by_id = {c.id: c for c in built.candidates}
    assert by_id["raise_scrutiny"].preconditions == ()
    for cid in ("keep_native_review", "light_check_suffices"):
        assert by_id[cid].preconditions == (security_triage.NEVER_EMITTED,)


def test_shipped_registry_entry_is_shadow_only_and_escalate_only():
    entry = _entry()
    assert entry["shadow_only"] is True
    assert entry["active_allowed"] is False
    assert entry["flag"] == FLAG
    assert entry["authorize"] == {
        "allow_ids": ["raise_scrutiny"],
        "deny_ids": ["keep_native_review", "light_check_suffices"],
    }
    assert "allow_all" not in entry["authorize"]
    assert "allow_id_prefixes" not in entry["authorize"]
    assert entry["preparer"] == "security_triage"
    assert entry["points"] == ["pre_tool"]
    assert entry["hooks"] == [{"host": "claude-code", "point": "pre_tool"}]
    assert entry["owner_bead"] == "mk-42j9.9"


def test_shipped_registry_is_structurally_valid():
    assert not flags.registry_errors(_shipped_registry())


def test_flag_defaults_off_and_active_is_downgraded_to_shadow():
    registry = _shipped_registry()
    assert flags.resolve_mode("security_triage", {}, registry).mode == "off"
    assert flags.resolve_mode("security_triage", {FLAG: "garbage"}, registry).mode == "off"
    assert flags.resolve_mode("security_triage", {FLAG: "shadow"}, registry).mode == "shadow"
    active = flags.resolve_mode("security_triage", {FLAG: "active"}, registry)
    assert active.mode == "shadow" and active.active_denied
    assert flags.resolve_mode("security_triage", {FLAG: "shadow", "CLAVAIN_SELECTOR": "off"}, registry).mode == "off"


def test_preparer_registered_immutably_for_pre_tool_only():
    assert set(preparers.PREPARERS) == {"security_triage"}
    definition = preparers.PREPARERS["security_triage"]
    assert definition.points == frozenset({Point.PRE_TOOL})
    # The preparer never sees tool_response or the raw event.
    assert definition.event_fields == frozenset({"session_id", "tool_name", "tool_input"})
    with pytest.raises(TypeError):
        preparers.PREPARERS["other"] = definition


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Edit", {"file_path": "{root}/a.py", "old_string": "x", "new_string": "os.system(cmd)"}),
        ("Write", {"file_path": "{root}/a.py", "content": "os.system(cmd)"}),
        ("MultiEdit", {"file_path": "{root}/a.py", "edits": [{"old_string": "x", "new_string": "os.system(cmd)"}]}),
        ("NotebookEdit", {"notebook_path": "{root}/a.ipynb", "new_source": "os.system(cmd)"}),
    ],
)
def test_prepare_builds_for_every_edit_tool(tmp_path, tool, tool_input):
    tool_input = {k: (v.format(root=tmp_path) if isinstance(v, str) else v) for k, v in tool_input.items()}
    prepared = preparers.prepare(
        _shipped_registry(), "security_triage", Point.PRE_TOOL, _event(tool, tool_input, tmp_path), tmp_path
    )
    assert {c.id for c in prepared.candidates} == security_triage.VOCABULARY
    assert "shell" in prepared.context
    assert "os.system" not in prepared.context
    assert prepared.integration == "security_triage"
    assert prepared.point == Point.PRE_TOOL


@pytest.mark.parametrize(
    "event",
    [
        None,
        HostEvent(point=Point.PRE_TOOL, session_id="s", tool_name="Bash", tool_input={"command": "ls"}),
        HostEvent(point=Point.PRE_TOOL, session_id="s", tool_name="Edit", tool_input="not a mapping"),
        HostEvent(point=Point.PRE_TOOL, session_id="s", tool_name="Edit", tool_input={"new_string": "x"}),
        HostEvent(point=Point.PRE_TOOL, session_id="s", tool_name=None, tool_input={"file_path": "/x"}),
    ],
)
def test_non_edit_or_malformed_events_are_not_prepared(tmp_path, event):
    with pytest.raises(preparers.NotPrepared):
        preparers.prepare(_shipped_registry(), "security_triage", Point.PRE_TOOL, event, tmp_path)


def test_other_points_are_not_prepared(tmp_path):
    with pytest.raises(preparers.NotPrepared):
        preparers.prepare(_shipped_registry(), "security_triage", Point.POST_TOOL_OUTPUT, _event(root=tmp_path), tmp_path)


def test_preparer_never_sees_tool_response(tmp_path):
    event = HostEvent(
        point=Point.PRE_TOOL,
        session_id="s",
        tool_name="Edit",
        tool_input={"file_path": str(tmp_path / "a.py"), "new_string": "x"},
        tool_response="TOP-SECRET-RESPONSE",
    )
    prepared = preparers.prepare(_shipped_registry(), "security_triage", Point.PRE_TOOL, event, tmp_path)
    assert "TOP-SECRET-RESPONSE" not in prepared.context


def test_context_is_bounded_and_revision_tracks_the_edit(tmp_path):
    big = "x = 1\n" * 5000
    ev = _event("Write", {"file_path": str(tmp_path / "a.py"), "content": big}, tmp_path)
    built = security_triage.build(ev, tmp_path)
    assert len(built.context) < 600
    other = security_triage.build(_event("Write", {"file_path": str(tmp_path / "a.py"), "content": big + "y"}, tmp_path), tmp_path)
    assert built.task_revision != other.task_revision
    assert built.task_revision == security_triage.build(ev, tmp_path).task_revision


@pytest.mark.parametrize("name", [".env", ".env.production"])
def test_env_file_edits_never_reach_egress(tmp_path, name):
    ev = _event("Write", {"file_path": str(tmp_path / name), "content": "K=v"}, tmp_path)
    prepared = preparers.prepare(_shipped_registry(), "security_triage", Point.PRE_TOOL, ev, tmp_path)
    request = _request_for(prepared)
    refusal = egress.admit(request)
    assert isinstance(refusal, egress.Refusal)
    assert "src.denylisted_path" in refusal.rule_ids


# Provider-shaped prefixes are assembled at runtime so the fixtures are not
# themselves committed credential-looking literals.
_SK = "sk" + "_live_"
_GH = "gh" + "p_"

CREDENTIAL_FIXTURES = [
    ('API_KEY = "abc123"', "abc123"),
    ("password: hunter2", "hunter2"),
    ('password = (\n    "hunter2"\n)', "hunter2"),
    ("cat <<EOF\nsecret=hunter2\nEOF", "hunter2"),
    ("conn = 'postgres://admin:hunter2@db/x'", "hunter2"),
    ("key = 'abc123'", "abc123"),
    ("pass = 'abc123'", "abc123"),
    ("p\u0430ssword = 'abc123'", "abc123"),  # Cyrillic a
    ("\u03c1assword = 'abc123'", "abc123"),  # Greek rho
    (f"token = '{_SK}abc123'", f"{_SK}abc123"),
    (f"g = '{_GH}abc123def'", f"{_GH}abc123def"),
    ("blob = 'YWJjMTIzZGVmNDU2'", "YWJjMTIzZGVmNDU2"),
    ("//registry.example/:_authToken=abc123", "abc123"),
    ("no name at all: hunter2-value", "hunter2-value"),
]


@pytest.mark.parametrize("line,value", CREDENTIAL_FIXTURES)
def test_raw_edit_text_never_leaves_the_machine(tmp_path, monkeypatch, line, value):
    """No name-based filter can be complete, so no raw text is sent at all.
    Asserted on the built request and every candidate; an egress refusal cannot
    mask a leak because the check is on the request itself."""
    monkeypatch.setattr(egress, "project_owner", lambda root: "mistakeknot")
    ev = _event("Write", {"file_path": str(tmp_path / "cfg.py"), "content": f"x = 1\n{line}\ny = 2"}, tmp_path)
    prepared = preparers.prepare(_shipped_registry(), "security_triage", Point.PRE_TOOL, ev, tmp_path)
    request = _request_for(prepared)
    for text in (request.context, request.task, *(c.description for c in request.candidates)):
        assert value not in text
        assert "x = 1" not in text and "y = 2" not in text
    assert security_triage.EXCERPT_POLICY in request.context
    # the metadata Jev still needs survives
    assert "file: cfg.py" in request.context and "new_text_chars:" in request.context
    assert not isinstance(egress.admit(request, high_entropy=True), egress.Refusal)


@pytest.mark.parametrize("tool,field", [("Write", "content"), ("Edit", "new_string"), ("NotebookEdit", "new_source")])
def test_no_edit_shape_sends_raw_text(tmp_path, tool, field):
    key = "file_path" if tool != "NotebookEdit" else "notebook_path"
    built = security_triage.build(_event(tool, {key: str(tmp_path / "m.py"), field: "def add(a, b): return a + b"}, tmp_path), tmp_path)
    assert "return a + b" not in built.context
    multi = security_triage.build(
        _event("MultiEdit", {"file_path": str(tmp_path / "m.py"), "edits": [{"new_string": "return a + b"}]}, tmp_path), tmp_path
    )
    assert "return a + b" not in multi.context


def test_redaction_keeps_host_signals_from_the_original_text(tmp_path):
    built = security_triage.build(
        _event("Write", {"file_path": str(tmp_path / "a.py"), "content": 'API_KEY = "abc123"'}, tmp_path), tmp_path
    )
    assert "secrets" in built.context


def test_relative_edit_paths_resolve_against_the_project_not_the_cwd(tmp_path, monkeypatch):
    other = tmp_path / "elsewhere"
    other.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(other)
    built = security_triage.build(_event("Edit", {"file_path": "src/auth.py", "new_string": "x"}, project), project)
    assert "file: src/auth.py" in built.context
    assert built.sources == (str(project / "src" / "auth.py"),)
    same = security_triage.build(
        _event("Edit", {"file_path": str(project / "src" / "auth.py"), "new_string": "x"}, project), project
    )
    assert same.task_revision == built.task_revision


def test_relative_env_path_is_still_refused_when_cwd_is_elsewhere(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    ev = _event("Write", {"file_path": ".env", "content": "K=v"}, project)
    prepared = preparers.prepare(_shipped_registry(), "security_triage", Point.PRE_TOOL, ev, project)
    refusal = egress.admit(_request_for(prepared))
    assert isinstance(refusal, egress.Refusal)
    assert "src.denylisted_path" in refusal.rule_ids


def _request_for(prepared):
    from clavain_selector.contract import SelectionRequest, SessionRef

    return SelectionRequest(
        integration=prepared.integration,
        point=prepared.point,
        task=prepared.task,
        context=prepared.context,
        candidates=prepared.candidates,
        task_revision=prepared.task_revision,
        session=SessionRef(host_session_id="s"),
        sources=prepared.sources,
        project_root=prepared.project_root,
    )


# ---------------------------------------------------------------------------
# End to end: Jev can only ever escalate. Never cancel, skip, allow or rewrite.
# ---------------------------------------------------------------------------


def _load_cli():
    path = REPO / "scripts" / "clavain-select.py"
    spec = importlib.util.spec_from_file_location("clavain_select_triage_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Budget:
    def __init__(self, *a, **k):
        pass

    def consume(self):
        return None


class _Breaker:
    def __init__(self, *a, **k):
        pass

    def check(self):
        return None

    def record(self, result):
        pass


def _client_for(outcome):
    """A fake Jev client. `outcome` is a candidate id, "escalate", "low_confidence" or a FallbackReason."""

    class Client:
        def __init__(self, credential):
            pass

        def call(self, call):
            if isinstance(outcome, FallbackReason):
                detail = {
                    FallbackReason.TIMEOUT: jev_client.FailureDetail.DEADLINE,
                    FallbackReason.HTTP_ERROR: jev_client.FailureDetail.CONNECT_ERROR,
                    FallbackReason.INVALID_RESPONSE: jev_client.FailureDetail.BAD_JSON,
                }[outcome]
                return jev_client.JevFailure(reason=outcome, detail=detail, attempts=1, http_status=None, latency_ms=3)
            ids = tuple(cid for cid, _ in call.battery.select.criteria)
            chosen = "raise_scrutiny" if outcome == "low_confidence" else outcome
            confidence = 0.55 if outcome == "low_confidence" else 0.95
            rest = (1.0 - confidence) / (len(ids) - 1)
            probs = tuple((cid, confidence if cid == chosen else rest) for cid in ids)
            response = jev_client.JevResponse(
                model=jev_client.PINNED_MODEL,
                select=jev_client.ChoiceAnswer(choice=chosen, confidence=confidence, probabilities=probs),
                fits=tuple(
                    jev_client.NoulAnswer(key=f.key, candidate_id=f.candidate_id, noul=0.95) for f in call.battery.fits
                ),
                usage=jev_client.Usage(input_tokens=10, output_tokens=2),
            )
            return jev_client.JevOk(response=response, attempts=1, http_status=200, latency_ms=4)

    return Client


class _FirstHandAdapter(ClaudeCodeAdapter):
    """Simulates a future matrix upgrade of pre_tool to first-hand evidence."""

    def capabilities(self):
        import dataclasses

        return {
            point: dataclasses.replace(cap, status="reachable", evidence_level="first_hand")
            for point, cap in super().capabilities().items()
        }


OUTCOMES = [
    "keep_native_review",
    "light_check_suffices",
    "raise_scrutiny",
    "escalate",
    "low_confidence",
    FallbackReason.TIMEOUT,
    FallbackReason.HTTP_ERROR,
    FallbackReason.INVALID_RESPONSE,
]


def _run_hook(monkeypatch, tmp_path, *, mode, outcome, registry, tool="Edit", adapter=None):
    cli = _load_cli()
    monkeypatch.setenv("CLAVAIN_SELECTOR_RECORD_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(selector.egress, "project_owner", lambda root: "mistakeknot")
    monkeypatch.setattr(selector.credentials, "load", lambda: credentials.SecretStr("zq-unmatched-fake-credential-9f3a"))
    monkeypatch.setattr(selector.jev_client, "Budget", _Budget)
    monkeypatch.setattr(selector.jev_client, "Breaker", _Breaker)
    monkeypatch.setattr(selector.jev_client, "JevClient", _client_for(outcome))
    monkeypatch.setattr(cli, "_load_registry", lambda: registry)
    monkeypatch.setattr(cli, "_get_host_adapter", lambda host: adapter or ClaudeCodeAdapter())
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAVAIN_SELECTOR", raising=False)
    if mode is None:
        monkeypatch.delenv(FLAG, raising=False)
    else:
        monkeypatch.setenv(FLAG, mode)
    raw = {
        "session_id": "sess",
        "tool_name": tool,
        "tool_input": {"file_path": str(tmp_path / "auth.py"), "new_string": "verify(password, token)"},
    }
    monkeypatch.setattr(cli.sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(raw).encode())))
    stdout = SimpleNamespace(buffer=io.BytesIO())
    monkeypatch.setattr(cli.sys, "stdout", stdout)
    status = cli.main_hook(SimpleNamespace(point="pre_tool", host="claude-code"))
    return status, stdout.buffer.getvalue()


def _assert_escalate_only(output: bytes):
    """Empty, or exactly a bare `ask`. Never a deny, allow, rewrite, skip or continue=false."""
    if not output:
        return
    payload = json.loads(output)
    assert set(payload) == {"hookSpecificOutput"}
    inner = payload["hookSpecificOutput"]
    assert set(inner) == {"hookEventName", "permissionDecision", "permissionDecisionReason"}
    assert inner["hookEventName"] == "PreToolUse"
    assert inner["permissionDecision"] == "ask"
    text = output.decode()
    for banned in ('"allow"', '"deny"', '"approve"', "updatedInput", '"continue"', '"decision"', "suppressOutput"):
        assert banned not in text


@pytest.mark.parametrize("outcome", OUTCOMES, ids=lambda o: getattr(o, "value", o))
@pytest.mark.parametrize("mode", ["shadow", "active"])
def test_shipped_registry_never_emits_anything(monkeypatch, tmp_path, mode, outcome):
    """As shipped, `active` is downgraded to shadow: stdout is always empty."""
    status, output = _run_hook(monkeypatch, tmp_path, mode=mode, outcome=outcome, registry=_shipped_registry())
    assert status == 0
    assert output == b""


def _active_capable_registry():
    registry = _shipped_registry()
    registry["integrations"]["security_triage"].update({"active_allowed": True, "shadow_only": False})
    return registry


def test_claude_code_pre_tool_is_not_active_capable_in_the_shipped_matrix():
    """Layer four: active needs first-hand evidence, and pre_tool has only `binary`."""
    capability = ClaudeCodeAdapter().capabilities()[Point.PRE_TOOL]
    assert capability.evidence_level != "first_hand"


@pytest.mark.parametrize("outcome", OUTCOMES, ids=lambda o: getattr(o, "value", o))
@pytest.mark.parametrize("mode", ["shadow", "active"])
def test_flipping_the_registry_alone_still_emits_nothing(monkeypatch, tmp_path, mode, outcome):
    """Registry says active, real host matrix says not first-hand: still empty."""
    status, output = _run_hook(monkeypatch, tmp_path, mode=mode, outcome=outcome, registry=_active_capable_registry())
    assert status == 0
    assert output == b""


@pytest.mark.parametrize("outcome", OUTCOMES, ids=lambda o: getattr(o, "value", o))
@pytest.mark.parametrize("mode", ["shadow", "active"])
def test_worst_case_every_gate_open_jev_can_only_ask(monkeypatch, tmp_path, mode, outcome):
    """Registry active AND matrix first-hand: only `raise_scrutiny` may speak, and only as a bare `ask`."""
    status, output = _run_hook(
        monkeypatch, tmp_path, mode=mode, outcome=outcome, registry=_active_capable_registry(), adapter=_FirstHandAdapter()
    )
    assert status == 0
    _assert_escalate_only(output)
    # Positive control: the sweep is not vacuous. The one path that may speak
    # does, and as a bare `ask`.
    if mode == "active" and outcome == "raise_scrutiny":
        assert json.loads(output)["hookSpecificOutput"]["permissionDecision"] == "ask"
    else:
        assert output == b""


@pytest.mark.parametrize("outcome", ["keep_native_review", "light_check_suffices"])
def test_measurement_only_ids_stay_inert_even_with_allow_all(monkeypatch, tmp_path, outcome):
    """Belt and braces: a mis-edited `allow_all` still cannot emit the measurement-only ids."""
    registry = _shipped_registry()
    registry["integrations"]["security_triage"].update(
        {"active_allowed": True, "shadow_only": False, "authorize": {"allow_all": True}}
    )
    status, output = _run_hook(
        monkeypatch, tmp_path, mode="active", outcome=outcome, registry=registry, adapter=_FirstHandAdapter()
    )
    assert status == 0
    assert output == b""


@pytest.mark.parametrize("mode", [None, "off", "OFF", "", "0", "true"])
def test_flag_off_by_default_is_fully_inert(monkeypatch, tmp_path, mode):
    monkeypatch.setattr(selector, "select", lambda *a, **k: pytest.fail("select reached with flag off"))
    status, output = _run_hook(monkeypatch, tmp_path, mode=mode, outcome="raise_scrutiny", registry=_shipped_registry())
    assert status == 0
    assert output == b""
    assert not (tmp_path / "records").exists()


def test_non_edit_tool_is_inert(monkeypatch, tmp_path):
    status, output = _run_hook(
        monkeypatch, tmp_path, mode="shadow", outcome="raise_scrutiny", registry=_shipped_registry(), tool="Bash"
    )
    assert status == 0
    assert output == b""
    assert not (tmp_path / "records").exists()


def test_shadow_run_records_the_would_be_triage(monkeypatch, tmp_path):
    """Shadow still measures: a record is written, naming the triage but not the edit text."""
    status, output = _run_hook(
        monkeypatch, tmp_path, mode="shadow", outcome="raise_scrutiny", registry=_shipped_registry()
    )
    assert status == 0 and output == b""
    files = list((tmp_path / "records").rglob("*.jsonl"))
    assert files, "shadow mode wrote no decision record"
    text = "\n".join(f.read_text() for f in files)
    record = json.loads(text.splitlines()[-1])
    assert record["mode"] == "shadow"
    assert record["applied"] == "native"
    assert record["result"]["kind"] == "selected"
    assert record["fallback"]["reason"] in ("", None, "shadow_mode")
    assert "verify(password, token)" not in text


# ---------------------------------------------------------------------------
# hooks.json wiring
# ---------------------------------------------------------------------------


def test_hooks_json_wires_exactly_one_flag_gated_triage_hook():
    hooks = json.loads((REPO / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"]
    found = [
        (group["matcher"], hook)
        for group in hooks
        for hook in group.get("hooks", [])
        if "security-triage-hook.sh" in hook.get("command", "")
    ]
    assert len(found) == 1
    matcher, hook = found[0]
    assert re.fullmatch(matcher, "Edit") and re.fullmatch(matcher, "NotebookEdit")
    assert not re.fullmatch(matcher, "Bash")
    assert hook["type"] == "command"
    assert 0 < hook["timeout"] <= 5
    script = REPO / "hooks" / "security-triage-hook.sh"
    assert script.stat().st_mode & stat.S_IXUSR


def test_shadow_measurement_runs_off_the_edit_critical_path():
    """Shadow detaches the selection; only the (never-printing) hand-off is inline."""
    text = (REPO / "hooks" / "security-triage-hook.sh").read_text()
    shadow = text.split('if [[ "$mode" == "active" ]]', 1)[1].split("fi\n", 1)[1]
    assert "&\n" in shadow and "> /dev/null 2>&1" in shadow
    assert "selector-hook.sh" in shadow
    assert _entry()["deadline_ms"]["pre_tool"] <= 1500
