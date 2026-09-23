"""Failure classification and persisted intercept evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import string
from urllib.parse import quote
import uuid

import pytest


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


def generated_secrets(seed=8252):
    """Stable property-style corpus; no production credential fixtures."""
    rng = random.Random(seed)
    for length in (8, 13, 20, 32, 64, 96):
        for alphabet in (string.ascii_letters + string.digits,
                         string.ascii_letters + string.digits + "_-.+/="):
            yield "".join(rng.choice(alphabet) for _ in range(length))


@pytest.mark.parametrize("header", [
    "Authorization", "Proxy-Authorization", "Cookie", "Set-Cookie",
    "X-Account-Pool-Token", "X-Api-Key", "Service-Key", "Service-Secret",
    "Service-Token",
])
def test_generated_credentials_in_headers_and_folds(header):
    for secret in generated_secrets():
        for scheme in ("", "Token ", "Digest username=operator, response=", "FutureAuth "):
            text = f"{header}: {scheme}{secret}\r\n\tcontinued={secret}\r\nSafe: visible\r\n"
            redacted = provider_errors.redact_text(text)
            assert secret not in redacted
            assert redacted.splitlines()[0] == f"{header}: [REDACTED]"
            assert "Safe: visible" in redacted
        for text in (json.dumps({header: f"Custom {secret}"}),
                     f"curl -H '{header}: Custom {secret}'",
                     f"> {header}: Custom {secret}\n>   {secret}\n> Safe: visible"):
            assert secret not in provider_errors.redact_text(text)


@pytest.mark.parametrize("key", [
    "token", "futureSecret", "passw", "password", "pwd", "api_key", "api-key",
    "auth", "cookie", "session", "credential", "private", "APP_SESSION_ID",
])
def test_generated_credentials_in_structured_text_and_fields(key):
    for secret in generated_secrets():
        values = [secret, secret + ' spaces : ; , & "quoted"',
                  {"unknown": [secret, {"nested": secret}]}]
        for value in values:
            text = json.dumps({key: value, "safe": "visible"})
            redacted = provider_errors.redact_text(text)
            assert secret not in redacted
            assert "visible" in redacted
            assert secret not in str(provider_errors._redact({key: value}))
        for text in (
            f"{key}={secret}\nSAFE=visible",
            f"export {key}='{secret} spaces , ; &'\nSAFE=visible",
            f"{key}: {secret} unquoted credential tail\nsafe: visible",
            f"{key}: |\n  {secret}\n  more {secret}\nsafe: visible",
            f"{key}:\n  nested:\n    - {secret}\nsafe: visible",
            f"{key}:\n- {secret}\nsafe: visible",
            f"https://localhost/route?{key}={secret}&safe=visible",
        ):
            redacted = provider_errors.redact_text(text)
            assert secret not in redacted
            assert "visible" in redacted


def test_punctuation_does_not_split_env_or_query_credential_values():
    for secret in generated_secrets():
        for text in (
            f"export API_KEY=first,{secret}\nSAFE=visible",
            f"export API_KEY='first,'\"{secret}\"\nSAFE=visible",
            f"https://localhost/route?session=first,{secret}&safe=visible",
            f"- credential: first,{secret}\nsafe: visible",
        ):
            redacted = provider_errors.redact_text(text)
            assert secret not in redacted
            assert "visible" in redacted


@pytest.mark.parametrize("host", ["localhost:3128", "10.0.0.1", "proxy", "[::1]:3128", "example.test"])
def test_generated_url_userinfo_for_any_host(host):
    for secret in generated_secrets():
        # URL userinfo uses percent encoding for delimiter characters.
        userinfo = quote(secret, safe="")
        for text in (f"https://operator:{userinfo}@{host}/route",
                     f"proxy=socks5://{userinfo}@{host}/route"):
            redacted = provider_errors.redact_text(text)
            assert userinfo not in redacted
            assert host in redacted


def test_generated_bare_high_entropy_secrets_and_safe_shapes():
    rng = random.Random(32003)
    for length in (20, 32, 48, 96, 200):
        for _ in range(20):
            secret = "aB9_" + "".join(rng.choice(string.ascii_letters + string.digits + "_-./+=")
                                      for _ in range(length - 4))
            assert secret not in provider_errors.redact_text(f"diagnostic [{secret}] end")
    safe_shapes = [
        hashlib.sha1(str(i).encode()).hexdigest() for i in range(40)
    ] + [hashlib.sha256(str(i).encode()).hexdigest() for i in range(40)] + [
        str(uuid.UUID(int=rng.getrandbits(128))) for _ in range(40)
    ] + ["2026-09-23T16:04:46Z", "2026-09-23T16:04:46.123456+00:00"]
    for safe in safe_shapes:
        for text in (f"identity {safe} end", f"revision={safe}", json.dumps({"revision": safe})):
            assert safe in provider_errors.redact_text(text)
        # Shape exemptions never apply inside a credential context.
        assert safe not in provider_errors.redact_text(f"credential={safe}")


def test_pem_blocks_and_macos_private_paths():
    for secret in generated_secrets():
        for label in ("PRIVATE KEY", "CERTIFICATE", "VENDOR CREDENTIAL", "PUBLIC KEY"):
            for separator in ("\n", r"\n"):
                text = f"before -----BEGIN {label}-----{separator}{secret}{separator}-----END {label}----- after"
                redacted = provider_errors.redact_text(text)
                assert secret not in redacted
                assert "before" in redacted and "after" in redacted
    for prefix in ("/private/tmp", "/private/var/folders"):
        assert prefix not in provider_errors.redact_text(f"file {prefix}/operator/work/cache")


def test_generated_secrets_absent_from_saved_evidence(tmp_path):
    for index, secret in enumerate(generated_secrets()):
        artifact = tmp_path / f"evidence-{index}.json"
        provider_errors.write_evidence(
            artifact,
            [{"type": "turn.failed", "error": {"code": "unknown_failure", "session": secret,
                "details": json.dumps({"cookie": secret})}}],
            f'Authorization: Custom {secret}\nCookie: sid={secret}\n\t{secret}\n'
            f'{{"credential": "{secret}"}}\nhttp://user:{secret}@localhost:3128',
            failure_class="terminal_error", dispatch_id="dispatch-fixture",
            attempt_id="attempt-fixture", receipt_path=f"evidence-{index}.json",
        )
        assert secret not in artifact.read_text()


def test_encoded_structured_credentials_and_malformed_values():
    for secret in generated_secrets():
        encoded_json = json.dumps({"cookie": secret})
        for text in (
            json.dumps(encoded_json),
            json.dumps({"log": encoded_json}),
            'log: ' + json.dumps(encoded_json),
            '{"coo\\u006bie": ' + json.dumps(secret) + '}',
            f'https://localhost/?api%5Fkey={quote(secret, safe="")}&safe=visible',
            f'https://localhost/?%61uth={quote(secret, safe="")}&safe=visible',
            f'token="unterminated {secret}',
            f'credential={{"value": "{secret}"',
        ):
            redacted = provider_errors.redact_text(text)
            assert secret not in redacted
            assert quote(secret, safe="") not in redacted


def test_vendor_extras_still_cover_low_entropy_probe_shapes():
    for prefix, size in (("AIza", 35), ("ya29.", 30), ("xoxe-", 30)):
        fake = prefix + "q" * size
        assert fake not in provider_errors.redact_text(f"provider diagnostic: {fake}")
