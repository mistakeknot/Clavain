"""Native preparation records for the opt-in two-phase launch.

The two required fields are the accountable subset of Intercore's
internal/routing/reasoning.go DecisionContext. This validator neither assigns
reasons nor grants acceptance. Native authorship and execution ordering are
necessary evidence; independent review still judges the decision and planning.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import stat

REASONS = (
    "unresolved-success-criteria", "foundational-invariants", "broad-consequences",
    "difficult-verification", "capability-failure",
)
SCHEMA = {
    "type": "object",
    "properties": {
        # Codex's native structured-output schema rejects uniqueItems. Enforce
        # uniqueness below without making a valid host request impossible.
        "reasons": {"type": "array", "items": {"type": "string", "enum": list(REASONS)}},
        "rationale": {"type": "string", "minLength": 1, "pattern": "\\S"},
    },
    "required": ["reasons", "rationale"], "additionalProperties": False,
}
MODELS = {"codex": "gpt-6-astra", "claude": "claude-fable-5-1"}


def validate_fallback(fallback):
    if (not isinstance(fallback, dict) or fallback.get("reason") != "fable-usage-limit"
            or not isinstance(fallback.get("user_authorization"), str) or not fallback["user_authorization"].strip()
            or not isinstance(fallback.get("evidence_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", fallback["evidence_sha256"])):
        raise ValueError("recorded conditional fallback authorization and capacity evidence required")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def validate_decision(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 16384:
        raise ValueError("decision exceeds 16 KiB")
    try:
        value = json.loads(text, object_pairs_hook=_unique)
    except RecursionError as error:
        raise ValueError("decision JSON nesting exceeds supported depth") from error
    if not isinstance(value, dict) or set(value) != {"reasons", "rationale"}:
        raise ValueError("decision requires only reasons and rationale")
    reasons, rationale = value["reasons"], value["rationale"]
    if (not isinstance(reasons, list) or any(not isinstance(x, str) or x not in REASONS for x in reasons)
            or len(set(reasons)) != len(reasons)):
        raise ValueError("invalid classification reasons")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("accountable rationale required even for routine work")
    return value


def read_regular(path, limit=64 * 1024**2):
    """Read one bounded regular file without following a final symlink."""
    if any(parent.is_symlink() for parent in Path(path).absolute().parents):
        raise ValueError("linked evidence ancestor")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit or before.st_nlink != 1:
            raise ValueError("evidence must be a bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(fd)
        if len(raw) > limit or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("evidence changed while reading")
        return raw
    finally:
        os.close(fd)


def _codex(rows, session, decision):
    contexts, matches = [], []
    identity = None
    for row in rows:
        value = row.get("payload", {})
        if row.get("type") == "response_item" and value.get("type") not in {
                "message", "reasoning", "function_call", "function_call_output",
                "custom_tool_call", "custom_tool_call_output"}:
            raise ValueError("unknown or provider-side native response item")
        if row.get("type") == "session_meta":
            if identity is not None:
                raise ValueError("duplicate native session metadata")
            identity = value.get("id")
            if value.get("source") != "exec" or value.get("thread_source") != "user":
                raise ValueError("native preparation must be a root exec session")
        elif row.get("type") == "turn_context":
            contexts.append(value)
        elif row.get("type") == "response_item" and value.get("type") in ("function_call", "custom_tool_call"):
            if value.get("name") not in {"exec", "exec_command", "write_stdin", "view_image",
                    "functions.exec", "functions.exec_command", "functions.write_stdin"}:
                raise ValueError("external or unverified preparation tool")
        elif (row.get("type") == "response_item" and value.get("type") == "message"
              and value.get("role") == "assistant" and value.get("phase") in ("final", "final_answer")):
            text = "".join(c.get("text", "") for c in value.get("content", []) if c.get("type") == "output_text")
            try:
                actual = validate_decision(text)
            except ValueError:
                continue
            if actual == decision:
                matches.append((value, contexts[-1] if contexts else {}))
    if identity != session or len(matches) != 1 or len(contexts) != 1:
        raise ValueError("one fresh native preparation turn and matching final decision required")
    message, context = matches[0]
    if (context.get("sandbox_policy", {}).get("type") != "read-only"
            or context.get("approval_policy") != "never"):
        raise ValueError("preparation was not native read-only with approvals disabled")
    return dict(message_id=message.get("id"), turn_id=context.get("turn_id"),
                model=context.get("model"), effort=context.get("effort"),
                sandbox_policy=context["sandbox_policy"], approval_policy="never")


def _claude(rows, session, decision, expected_model):
    matches, user_turns, successful_results = [], [], set()
    decision_seen = False
    for row in rows:
        if row.get("type") in ("user", "assistant"):
            if row.get("sessionId") != session or row.get("isSidechain"):
                raise ValueError("foreign or delegated native preparation")
        if row.get("type") == "user":
            content = row.get("message", {}).get("content", [])
            purely_results = isinstance(content, list) and content and all(
                isinstance(item, dict) and item.get("type") == "tool_result" for item in content)
            if not row.get("isMeta") and not purely_results:
                user_turns.append(row)
            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "tool_result" and not item.get("is_error"):
                        successful_results.add(item.get("tool_use_id"))
            continue
        if row.get("type") != "assistant":
            continue
        message = row.get("message", {})
        blocks = message.get("content", [])
        synthetic = (decision_seen and message.get("model") == "<synthetic>" and row.get("effort") is None
                     and all(item.get("type") == "text" for item in blocks))
        if not synthetic and (message.get("model") != expected_model or row.get("effort") != "high"):
            raise ValueError("native preparation changed model or effort")
        for item in blocks:
            if item.get("type") not in {"text", "thinking", "redacted_thinking", "tool_use"}:
                raise ValueError("unknown or provider-side Claude content block")
            if item.get("type") != "tool_use":
                continue
            if decision_seen:
                raise ValueError("tool execution after preparation decision")
            if item.get("name") not in {"Read", "Glob", "Grep", "StructuredOutput"}:
                raise ValueError("non-read-only Claude preparation tool")
            if item.get("name") == "StructuredOutput" and item.get("input") == decision:
                matches.append(dict(message_id=message.get("id"), native_row_id=row.get("uuid"),
                                    tool_use_id=item.get("id"), model=message.get("model"), effort=row.get("effort")))
                decision_seen = True
    if (len(matches) != 1 or len(user_turns) != 1 or user_turns[0].get("permissionMode") != "dontAsk"
            or matches[0]["tool_use_id"] not in successful_results):
        raise ValueError("one completed native read-tool-only preparation turn required")
    return matches[0]


def bind_decision(host, path, session, decision, expected_model=None, fallback=None):
    """Bind a frozen first-phase snapshot, selected from the native session store.

    The launcher must enforce that origin and verify native tool configuration;
    this validator rejects unexpected outer native calls. Codex nested tools
    remain governed by the OS sandbox and disabled features/connectors; the
    outer exec name does not establish what every nested tool did.
    An expected Opus model is permitted only when the caller has recorded the
    user's conditional fallback authorization and the Fable capacity failure.
    """
    if host not in MODELS or not isinstance(session, str) or not session:
        raise ValueError("known host and native session required")
    expected_model = expected_model or MODELS[host]
    allowed = {MODELS[host]} | ({"claude-opus-5"} if host == "claude" else set())
    if expected_model not in allowed:
        raise ValueError("unsupported model assignment")
    if expected_model != MODELS[host]:
        validate_fallback(fallback)
    try:
        decision = validate_decision(json.dumps(decision, ensure_ascii=False))
        raw = read_regular(path)
    except OSError as error:
        raise ValueError("native evidence cannot be linked or unavailable") from error
    except TypeError as error:
        raise ValueError("decision must be JSON serializable") from error
    try:
        rows = [json.loads(line, object_pairs_hook=_unique) for line in raw.splitlines()]
        if not rows or any(not isinstance(row, dict) for row in rows):
            raise ValueError("native evidence must contain object records")
        binding = _codex(rows, session, decision) if host == "codex" else _claude(rows, session, decision, expected_model)
    except (AttributeError, TypeError, KeyError, RecursionError) as error:
        raise ValueError("unsupported native evidence shape") from error
    required = ("message_id", "turn_id") if host == "codex" else ("message_id", "native_row_id", "tool_use_id")
    if any(not isinstance(binding.get(k), str) or not binding[k] for k in required):
        raise ValueError("native message identity incomplete")
    if binding.get("model") != expected_model or binding.get("effort") != "high":
        raise ValueError("native preparation model or effort differs from fixed assignment")
    return dict(binding, session_id=session, host=host,
                assignment="fixed" if expected_model == MODELS[host] else "authorized-fallback",
                fallback=fallback if expected_model != MODELS[host] else None,
                native_path=str(Path(path).absolute()),
                native_sha256=hashlib.sha256(raw).hexdigest(), native_bytes=len(raw),
                decision_sha256=hashlib.sha256(json.dumps(decision, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                acceptance="not-established")
