"""Failure classification and persisted intercept evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import string
import subprocess
import sys
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


def claude_limit_events(text):
    """Claude CLI stream-json shape for a subscription limit (mk-esex)."""
    return [
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": text}]},
            "error": "rate_limit",
        },
        {"type": "result", "subtype": "success", "is_error": True, "result": text},
    ]


@pytest.mark.parametrize("text", [
    "You've hit your usage limit · resets Sep 26, 7pm (UTC)",
    "You've hit your weekly limit · resets Sep 26, 7pm (UTC)",
    "You’ve hit your session limit · resets 3am (UTC)",
    "You've hit your Opus limit · resets Sep 26, 7pm (UTC)",
    "Claude AI usage limit reached|1790000000",
])
def test_claude_subscription_limit_is_quota_exhausted(text):
    # Without this, a Claude seat that runs out of quota classifies as
    # terminal_error and dispatch suppresses its declared fallback, so an
    # Opus-authored plan review blocks on a Fable outage instead of degrading.
    assert provider_errors.classify(claude_limit_events(text)) == "quota_exhausted"
    assert provider_errors.classify(claude_limit_events(text)[1:]) == "quota_exhausted"


def test_claude_rate_limit_without_limit_text_stays_terminal():
    # A transient 429 or overload carries the same error code; only the
    # subscription-limit text makes it a capacity failure.
    events = claude_limit_events("API Error: Request rejected (429) · retry later")
    assert provider_errors.classify(events) == "terminal_error"


def test_claude_limit_text_in_ordinary_output_is_not_a_failure():
    events = [
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "You've hit your weekly limit · quoted"}]},
        },
        {"type": "result", "subtype": "success", "is_error": False,
         "result": "You've hit your weekly limit · quoted"},
    ]
    assert provider_errors.classify(events) == ""


CODEX_EXHAUSTED_429 = "exceeded retry limit, last status: 429 Too Many Requests"


def test_codex_exhausted_429_retries_is_rate_limited():
    # Captured 2026-09-25 from a pooled cross-lab review: Codex had already
    # retried internally. As terminal_error it suppressed the review's
    # fallback chain; rate_limited lets dispatch retry, then walk.
    events = [
        {"type": "thread.started", "thread_id": "fixture"},
        {"type": "turn.started"},
        {"type": "error", "message": CODEX_EXHAUSTED_429},
        {"type": "turn.failed", "error": {"message": CODEX_EXHAUSTED_429}},
    ]
    assert provider_errors.classify(events) == "rate_limited"


def test_recovered_codex_429_is_not_a_failure():
    events = [
        {"type": "error", "message": CODEX_EXHAUSTED_429},
        {"type": "turn.completed"},
    ]
    assert provider_errors.classify(events) == ""


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
    assert "<redacted>" in text
    assert "~/projects/secret/repo" in text
    assert reference == {
        "path": ".clavain/intercept/attempt-fixture.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    assert artifact.stat().st_mode & 0o777 == 0o600


def test_failure_evidence_bounds_redacted_stderr_tail_to_4096_bytes(tmp_path):
    artifact = tmp_path / "evidence.json"
    # Exercise truncation after allowlisting, not just compression of one huge
    # unknown word into a placeholder. Use multibyte fixture vocabulary too.
    stderr = "before\n" * 800 + "You’ve hit your usage limit.\n" * 200 + "z" * 5000

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
    assert 4093 <= len(evidence["stderr_tail"].encode()) <= 4096
    assert "before" not in evidence["stderr_tail"]
    assert evidence["stderr_tail"].endswith("You’ve hit your usage limit.\n<word>")
    assert "z" * 100 not in evidence["stderr_tail"]


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
                "request_id": "<id>",
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
                "provider_reason": "connection refused " * 2000,
                "task_output": body,
            },
        },
        {
            "type": "assistant",
            "request_id": "assistant-request",
            "message": {"content": [{"type": "text", "text": body}]},
            "error": {
                "code": "unknown_assistant_failure",
                "provider_reason": "server error " * 2000,
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
    assert len(evidence["unmapped_provider_fields"]) >= 2
    assert len(serialized) >= 3500  # Actually fill the budget, not an empty capture.
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
    "X-Bb-Account-Pool-Token", "X-Api-Key", "Service-Key", "Service-Secret",
    "Service-Token",
])
def test_generated_credentials_in_headers_and_folds(header):
    for secret in generated_secrets():
        for scheme in ("", "Token ", "Digest username=operator, response=", "FutureAuth "):
            text = f"{header}: {scheme}{secret}\r\n\tcontinued={secret}\r\nSafe: visible\r\n"
            redacted = provider_errors.redact_text(text)
            assert secret not in redacted
            label = "<id>" if header == "X-Bb-Account-Pool-Token" else header
            assert redacted.splitlines()[0] == f"{label}: <redacted>"
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


@pytest.mark.parametrize(("host", "summary"), [
    ("localhost:3128", "localhost:3128"), ("10.0.0.1", "unknown"),
    ("proxy", "unknown"), ("[::1]:3128", "unknown"), ("example.test", "*.example.test"),
])
def test_generated_url_userinfo_for_any_host(host, summary):
    for secret in generated_secrets():
        # URL userinfo uses percent encoding for delimiter characters.
        userinfo = quote(secret, safe="")
        for text in (f"https://operator:{userinfo}@{host}/route",
                     f"proxy=socks5://{userinfo}@{host}/route"):
            redacted = provider_errors.redact_text(text)
            assert userinfo not in redacted
            assert f"<url-host:{summary}>" in redacted


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


@pytest.mark.parametrize("safe", [
    "error", "429", "a" * 40, "b" * 64,
    "01a0cafd-2e09-75a1-94ec-14aafc8c38b9", "2026-09-23T16:04:46Z",
])
def test_contexts_override_allowlist_even_for_safe_values(safe):
    for template in (
        "codex --token={}", "codex --password={}", "codex --api-key={}",
        "codex --token {}", "pass={}", "pw={}", "pass: {}", "password {}",
        "curl -u alice:{}", "curl --user alice:{}", "sshpass -p {}", "mysql -p {}",
        "creds[token]={}", "token => {}", '{{"token":\n"{}"}}',
        "Bearer {}", "Basic {}", "Cookie: {}", "Authorization: Digest {}",
        "https://operator:{}@localhost:3128/route",
        "-----BEGIN VENDOR CREDENTIAL-----\n{}\n-----END VENDOR CREDENTIAL-----",
    ):
        sanitized = provider_errors.redact_text(template.format(safe))
        assert safe not in sanitized, (template, sanitized)


@pytest.mark.parametrize("digits", [11, 40, 64, 300])
def test_long_numbers_cannot_use_identifier_exemptions(digits):
    value = "7" * digits
    assert provider_errors.redact_text(f"status={value}") == "status=<num>"
    assert provider_errors._bounded_scalar(int(value), "status") == "<num>"
    assert provider_errors.redact_text(f"~/repo/{value}") == "<path>"


def test_identifier_exemption_never_exempts_its_prefix():
    for value in ("c" * 40, "2026-09-23T16:04:46Z"):
        assert provider_errors.redact_text(f"hUntEr2={value}") == f"<id>={value}"


def test_url_summary_drops_path_query_fragment_but_keeps_host_and_punctuation():
    for secret in generated_secrets():
        value = quote(secret, safe="")
        sanitized = provider_errors.redact_text(f"POST (https://api.openai.com/{value}?q={value}#{value}).")
        assert secret not in sanitized and value not in sanitized
        assert sanitized == "POST (<url-host:api.openai.com>)."


def test_paths_only_keep_vocabulary_components_or_known_ids():
    for prefix in ("/home/operator", "/Users/operator", "/root", "/tmp", "/var/folders",
                   "/private/tmp", "/private/var/folders", "~"):
        assert provider_errors.redact_text(f"{prefix}/repo/scripts/") == "~/repo/scripts/"
        for secret in generated_secrets():
            assert secret not in provider_errors.redact_text(f"{prefix}/repo/{secret}/file.py")


def test_unknown_metadata_key_collisions_do_not_drop_fields():
    events = [{"type": "turn.failed", "error": {"hunter2": "missing", "hunter3": "invalid"}}]
    fields = provider_errors._unmapped_provider_fields(events)[0]["fields"]["error"]
    assert set(fields) == {"<id>:0", "<id>:1"}
    assert set(fields.values()) == {"missing", "invalid"}


@pytest.mark.parametrize("option", ["curl -u", "curl --user", "sshpass -p", "mysql -p", "codex --token"])
@pytest.mark.parametrize("inner", ["c", "c" * 10, "c" * 30, 'c --password d'])
def test_overlapping_cli_credentials_are_removed_as_a_union(option, inner, tmp_path):
    # The inner replacement used to change the string length before the outer
    # span was removed, exposing the allowlisted word/number at its tail.
    raw = f'{option} "a:b --token {inner} xxxxxxxx 123456 request"'
    expected = option + " <redacted>"
    assert provider_errors._redact_cli(raw) == expected
    assert provider_errors.redact_text(raw) == provider_errors.redact_text(expected)
    artifact = tmp_path / "overlapping.json"
    provider_errors.write_evidence(
        artifact, [{"type": "turn.failed", "error": {"details": raw}}], raw,
        failure_class="terminal_error", dispatch_id="dispatch-fixture",
        attempt_id="attempt-fixture", receipt_path=artifact.name,
    )
    assert "123456" not in artifact.read_text()
    assert "request" not in artifact.read_text()


def test_disjoint_cli_credential_spans_preserve_intervening_text():
    raw = 'curl -u "short --token x tail" --retry 429 --password "error"'
    assert provider_errors._redact_cli(raw) == 'curl -u <redacted> --retry 429 --password <redacted>'


@pytest.mark.parametrize(("host", "summary"), [
    ("api.openai.com", "api.openai.com"), ("chatgpt.com", "chatgpt.com"),
    ("api.anthropic.com", "api.anthropic.com"), ("localhost:3128", "localhost:3128"),
    ("127.0.0.1:3128", "127.0.0.1:3128"), ("API.OPENAI.COM", "api.openai.com"),
    ("hunter2.oast.example", "*.oast.example"), ("hunter2.api.openai.com", "*.openai.com"),
    ("api.openai.com.hunter2.example.com", "*.example.com"),
    ("hunter2.example.co.uk", "*.example.co.uk"), ("hunter2.example.com.au", "*.example.com.au"),
    ("hunter2.example.co.jp", "*.example.co.jp"), ("example.com", "*.example.com"),
    ("co.uk", "unknown"), ("hunter2", "unknown"), ("10.0.0.1", "unknown"),
])
def test_url_hostnames_disclose_only_known_hosts_or_registrable_part(host, summary):
    sanitized = provider_errors.redact_text(f"https://{host}/route")
    assert sanitized == f"<url-host:{summary}>"
    assert "hunter2" not in sanitized


def test_generated_secret_subdomains_are_absent_from_saved_evidence(tmp_path):
    rng = random.Random(82524)
    for index in range(20):
        secret = "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(32))
        artifact = tmp_path / f"host-{index}.json"
        url = f"https://{secret}.tenant.example.co.uk/"
        provider_errors.write_evidence(
            artifact, [{"type": "turn.failed", "error": {"details": url}}], url,
            failure_class="terminal_error", dispatch_id="dispatch-fixture",
            attempt_id="attempt-fixture", receipt_path=artifact.name,
        )
        assert secret not in artifact.read_text()
        assert "<url-host:*.example.co.uk>" in artifact.read_text()


def ordinal_day(day):
    suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def test_ordinal_dates_are_a_bounded_class_not_vocabulary_entries():
    vocabulary = provider_errors._vocabulary()
    assert "x-account-pool-token" not in vocabulary
    for day in range(1, 32):
        ordinal = ordinal_day(day)
        assert ordinal not in vocabulary
        assert provider_errors.redact_text(ordinal) == ordinal
        assert provider_errors.redact_text(f"token={ordinal}") == "token=<redacted>"
    for invalid in ("0th", "32nd", "111th", "1th", "11st", "21th", "12345678901st"):
        assert provider_errors.redact_text(invalid) == "<id>"


def test_pem_blocks_and_macos_private_paths():
    for secret in generated_secrets():
        for label in ("PRIVATE KEY", "CERTIFICATE", "VENDOR CREDENTIAL", "PUBLIC KEY",
                      "RSA PRIVATE KEY", "OPENSSH PRIVATE KEY", "ENCRYPTED PRIVATE KEY"):
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
    for prefix in ("AIza", "ya29.", "xoxe-", "xoxb-", "xoxp-", "xoxa-", "xoxr-", "xoxs-",
                   "sk-", "sk-proj-", "sk-ant-api03-", "ghp_", "gho_", "ghs_", "ghu_", "ghr_",
                   "github_pat_", "glpat-"):
        fake = prefix + "q" * 35
        assert fake not in provider_errors.redact_text(f"provider diagnostic: {fake}")


@pytest.mark.parametrize("template", [
    "codex --token={}", "codex --password={}", "codex --api-key={}",
    "pass={}", "pass: {}", "PASS={}", "pw={}", "curl -u alice:{}",
    "curl --user alice:{}", "sshpass -p {}", "mysql -p {}", "codex --token {}",
    '{{"token":\n"{}"}}', "Basic {}", "creds[token]={}", "token => {}",
    "token%3D{}", "FOO={}", "diagnostic {} end",
])
def test_round_three_probes_and_generated_unrecognized_tokens(template, tmp_path):
    # All contexts are persisted, not just passed through an isolated regex.
    for index, secret in enumerate(["hunter2", "abc123", "aB9xQz7L", *generated_secrets()]):
        artifact = tmp_path / f"probe-{index}.json"
        provider_errors.write_evidence(
            artifact, [{"type": "turn.failed", "error": {"details": template.format(secret)}}],
            template.format(secret), failure_class="terminal_error",
            dispatch_id="dispatch-fixture", attempt_id="attempt-fixture",
            receipt_path=artifact.name,
        )
        assert secret not in artifact.read_text()


def test_allowlist_replaces_unknown_tokens_and_preserves_diagnostic_shape():
    raw = ("mysteryword 12345678901 hUntEr2 /opt/customer-data/credentials "
           "~/projects/customer-data POST https://api.openai.com/v1/responses 429\n"
           "request_id: req_011CRkDkPz9xKq2mNv7wYtLb\n"
           "model=claude-fable-5-1 effort=high\n"
           "attempt_id=dispatch-20260923T160446Z-a1b2c3\n"
           'File "/home/mk/.local/lib/python3.12/site-packages/anthropic/_base_client.py", line 1034\n'
           "EPIPE ECONNRESET authentication_error 403 1234567890\n")
    sanitized = provider_errors.redact_text(raw)
    for secret in ("mysteryword", "12345678901", "hUntEr2", "customer-data",
                   "req_011CRkDkPz9xKq2mNv7wYtLb", "dispatch-20260923T160446Z-a1b2c3"):
        assert secret not in sanitized
    for useful in ("<word>", "<num>", "<id>", "<path>",
                   "POST <url-host:api.openai.com> 429", "request_id: <id>",
                   "model=<id> effort=high", "attempt_id=<id>",
                   "~/.local/lib/python3.12/site-packages/anthropic/_base_client.py",
                   "EPIPE ECONNRESET authentication_error 403 1234567890"):
        assert useful in sanitized


@pytest.mark.parametrize(("month", "day"), [
    (month, day)
    for month in ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    for day in range(1, 32)
])
def test_real_usage_limit_fixtures_classify_and_meet_placeholder_budget(month, day):
    messages = []
    for filename in ("codex-usage-limit-rollout.jsonl", "codex-usage-limit-stdout.jsonl"):
        events = [json.loads(line) for line in (ROOT / "tests/fixtures" / filename).read_text().splitlines()]
        assert provider_errors.classify(events) == "quota_exhausted"
        for event in events:
            _, _, error = provider_errors._envelope(event)
            if isinstance(error, dict) and "message" in error:
                messages.append(error["message"])
    assert len(messages) == 3
    for message in messages:
        date = f"{month} {ordinal_day(day)}, 2027 2:36 AM"
        message, replacements = re.subn(
            r"[A-Z][a-z]{2} [0-9]{1,2}(?:st|nd|rd|th), [0-9]{4} [0-9]{1,2}:[0-9]{2} [AP]M",
            date, message,
        )
        assert replacements == 1
        for raw in (message, "ERROR: " + message, message.replace("’", "'")):
            sanitized = provider_errors.redact_text(raw)
            assert provider_errors.classify([], sanitized) == "quota_exhausted"
            assert "usage limit" in sanitized and "try again at" in sanitized
            assert date in sanitized
            assert "<url-host:chatgpt.com>" in sanitized
            # Same <=5% budget regardless of the calendar date in the fixture.
            placeholders = re.findall(r"<[^<>]+>", sanitized)
            words = re.findall(r"<[^<>]+>|[\w’']+", sanitized)
            assert len(placeholders) / len(words) <= 0.05


def test_scalar_metadata_uses_same_allowlist_including_keys_and_large_numbers(tmp_path):
    artifact = tmp_path / "metadata.json"
    provider_errors.write_evidence(
        artifact, [{"type": "turn.failed", "request_id": "req_011CRkDkPz9xKq2mNv7wYtLb",
                    "error": {"hunter2": "shortunknown", "details": 123456789012345,
                              "retry_after": 120, "will_retry": False}}],
        "", failure_class="terminal_error", dispatch_id="dispatch-fixture",
        attempt_id="attempt-fixture", receipt_path=artifact.name,
    )
    raw = artifact.read_text()
    for secret in ("hunter2", "shortunknown", "123456789012345", "req_011CRkDkPz9xKq2mNv7wYtLb"):
        assert secret not in raw
    fields = json.loads(raw)["unmapped_provider_fields"][0]["fields"]
    assert fields["request_id"] == "<id>"
    assert fields["error"]["retry_after"] == 120
    assert fields["error"]["will_retry"] is False


def test_missing_vocabulary_cannot_break_provider_classification(tmp_path):
    # The evidence dependency must not become a classification dependency.
    isolated = tmp_path / "provider-errors.py"
    isolated.write_bytes((ROOT / "scripts/provider-errors.py").read_bytes())
    events = ROOT / "tests/fixtures/codex-usage-limit-rollout.jsonl"
    result = subprocess.run([sys.executable, str(isolated), str(events)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "quota_exhausted"
    stderr = tmp_path / "stderr.txt"
    stderr.write_text("ERROR: You've hit your usage limit.\n")
    artifact = tmp_path / "evidence.json"
    result = subprocess.run([
        sys.executable, str(isolated), str(events), "--stderr", str(stderr),
        "--write-evidence", str(artifact), "--receipt-path", artifact.name,
        "--failure-class", "quota_exhausted", "--dispatch-id", "dispatch-fixture",
        "--attempt-id", "attempt-fixture",
    ], text=True, capture_output=True)
    assert result.returncode != 0
    assert not artifact.exists()
