"""Failure classification and persisted intercept evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "provider_errors", ROOT / "scripts" / "provider-errors.py"
)
provider_errors = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(provider_errors)


def test_stderr_usage_limit_envelope_is_classified_but_task_text_is_not():
    events = [
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": "ERROR: You've hit your usage limit. This is quoted task text.",
            },
        }
    ]

    assert provider_errors.classify(events) == ""
    assert provider_errors.classify(events, "ERROR: You've hit your usage limit.\n") == "quota_exhausted"


def test_failure_evidence_redacts_secrets_identity_and_home_paths(tmp_path):
    artifact = tmp_path / "evidence.json"
    aws_access = "AKIA" + "IOSFODNN7EXAMPLE"
    aws_session = "ASIA" + "IOSFODNN7EXAMPLE"
    stderr = (
        "Authorization: Bearer bearer-fixture-secret\n"
        "Cookie: session=cookie-fixture-secret\n"
        "Set-Cookie: __Secure-sid=set-cookie-fixture-secret; Path=/\n"
        "OPENAI_API_KEY=sk-fixture-secret-value\n"
        "api_key: key-fixture-secret-value\n"
        '{"Authorization":"auth-fixture-secret-value","client_secret":"client-fixture-secret-value"}\n'
        "JWT eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmaXh0dXJlIn0.signature-fixture\n"
        "tokens github_pat_fixturesecret123 gho_fixturesecret123 ghs_fixturesecret123 glpat-fixturesecret123\n"
        f"AWS {aws_access} {aws_session} password hunter2-fixture\n"
        "contact dev.person@example.test at /home/private-user/projects/secret/repo "
        "/root/.codex/auth.json /tmp/private-fixture /var/folders/zz/private-fixture\n"
    )
    events = [
        {
            "type": "turn.failed",
            "error": {
                "code": "unknown_failure",
                "provider_token": "tok-fixture-provider-secret",
                "cookie": "dict-cookie-fixture-secret",
            },
        }
    ]

    reference = provider_errors.write_evidence(
        artifact,
        events,
        stderr,
        failure_class="terminal_error",
        dispatch_id="dispatch-fixture",
        attempt_id="attempt-fixture",
        receipt_path=".clavain/intercept/attempt-fixture.json",
    )

    raw = artifact.read_bytes()
    text = raw.decode()
    for secret in (
        "bearer-fixture-secret",
        "cookie-fixture-secret",
        "set-cookie-fixture-secret",
        "sk-fixture-secret-value",
        "key-fixture-secret-value",
        "auth-fixture-secret-value",
        "client-fixture-secret-value",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmaXh0dXJlIn0.signature-fixture",
        "github_pat_fixturesecret123",
        "gho_fixturesecret123",
        "ghs_fixturesecret123",
        "glpat-fixturesecret123",
        aws_access,
        aws_session,
        "hunter2-fixture",
        "dev.person@example.test",
        "/home/private-user",
        "/root/",
        "/tmp/",
        "/var/folders/",
        "tok-fixture-provider-secret",
        "dict-cookie-fixture-secret",
    ):
        assert secret not in text
    assert "[REDACTED]" in text
    assert "~/projects/secret/repo" in text
    assert reference == {
        "path": ".clavain/intercept/attempt-fixture.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    assert artifact.stat().st_mode & 0o777 == 0o600


def test_failure_evidence_bounds_redacted_stderr_tail_to_4096_bytes(tmp_path):
    artifact = tmp_path / "evidence.json"
    stderr = "discard-me\n" * 800 + "tail-marker\n" + "z" * 5000

    provider_errors.write_evidence(
        artifact,
        [],
        stderr,
        failure_class="terminal_error",
        dispatch_id="dispatch-fixture",
        attempt_id="attempt-fixture",
        receipt_path=".clavain/intercept/attempt-fixture.json",
    )

    evidence = json.loads(artifact.read_text())
    assert len(evidence["stderr_tail"].encode()) <= 4096
    assert "discard-me" not in evidence["stderr_tail"]
    assert evidence["stderr_tail"].endswith("z" * 100)


def test_failure_evidence_captures_only_unmapped_failure_envelope_fields(tmp_path):
    artifact = tmp_path / "evidence.json"
    events = [
        {
            "type": "turn.failed",
            "request_id": "req-123",
            "error": {
                "code": "unknown_failure",
                "message": "error body must not be retained",
                "provider_reason": "seat_exhausted",
            },
        },
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "private task output"},
        },
    ]

    provider_errors.write_evidence(
        artifact,
        events,
        "",
        failure_class="terminal_error",
        dispatch_id="dispatch-fixture",
        attempt_id="attempt-fixture",
        receipt_path=".clavain/intercept/attempt-fixture.json",
    )

    evidence = json.loads(artifact.read_text())
    assert evidence["unmapped_provider_fields"] == [
        {
            "event_type": "turn.failed",
            "fields": {
                "request_id": "req-123",
                "error": {
                    "code": "unknown_failure",
                    "provider_reason": "seat_exhausted",
                },
            },
        }
    ]
    assert "private task output" not in artifact.read_text()
    assert "error body must not be retained" not in artifact.read_text()


def test_unmapped_capture_drops_claude_bodies_and_is_size_bounded(tmp_path):
    artifact = tmp_path / "evidence.json"
    body = "task-output-fixture-" * 1000
    events = [
        {
            "type": "result",
            "is_error": True,
            "request_id": "result-request",
            "result": body,
            "error": {
                "code": "unknown_result_failure",
                "provider_reason": "r" * 2000,
                "task_output": body,
            },
        },
        {
            "type": "assistant",
            "request_id": "assistant-request",
            "message": {"content": [{"type": "text", "text": body}]},
            "error": {
                "code": "unknown_assistant_failure",
                "provider_reason": "s" * 2000,
                "message_body": body,
            },
        },
    ] * 80

    provider_errors.write_evidence(
        artifact,
        events,
        "",
        failure_class="terminal_error",
        dispatch_id="dispatch-fixture",
        attempt_id="attempt-fixture",
        receipt_path=".clavain/intercept/attempt-fixture.json",
    )

    evidence = json.loads(artifact.read_text())
    serialized = json.dumps(evidence["unmapped_provider_fields"], separators=(",", ":")).encode()
    assert len(serialized) <= 4096
    assert "task-output-fixture" not in artifact.read_text()
    for row in evidence["unmapped_provider_fields"]:
        assert set(row["fields"]) <= {"request_id", "error"}
        for value in row["fields"].get("error", {}).values():
            if isinstance(value, str):
                assert len(value.encode()) <= 256
