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
    stderr = (
        "Authorization: Bearer bearer-fixture-secret\n"
        "OPENAI_API_KEY=sk-fixture-secret-value\n"
        "api_key: key-fixture-secret-value\n"
        '{"Authorization":"auth-fixture-secret-value","client_secret":"client-fixture-secret-value"}\n'
        "contact dev.person@example.test at /home/private-user/projects/secret/repo\n"
    )
    events = [
        {
            "type": "turn.failed",
            "error": {
                "code": "unknown_failure",
                "provider_token": "tok-fixture-provider-secret",
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
        "sk-fixture-secret-value",
        "key-fixture-secret-value",
        "auth-fixture-secret-value",
        "client-fixture-secret-value",
        "dev.person@example.test",
        "/home/private-user",
        "tok-fixture-provider-secret",
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
                "message": "ordinary mapped message",
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
                    "message": "ordinary mapped message",
                    "provider_reason": "seat_exhausted",
                },
            },
        }
    ]
    assert "private task output" not in artifact.read_text()
