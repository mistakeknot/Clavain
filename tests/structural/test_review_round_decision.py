"""One-use round decisions with dummy keys and receipts only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess

import pytest
from test_review_round_limit import ROOT, receipt, invoke

HEAD = "a" * 40


@pytest.fixture
def decision(tmp_path):
    key = tmp_path / "dummy-key"
    key.write_bytes(b"dummy-test-key-only")
    key.chmod(0o600)
    directory = tmp_path / "reviews/round-limits/decisions"
    directory.mkdir(parents=True)
    path = directory / "test-1.json"
    data = dict(schema_version=1, decision_id="dummy-decision", bead="test-1", head=HEAD,
                accepted_failures=3, authority="vizier", ruling="dummy stated limit",
                decided_at="2026-01-01T00:00:00+00:00")
    data["mac"] = hmac.new(key.read_bytes(), json.dumps(data, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode(), hashlib.sha256).hexdigest()
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return path, key


def gate(tmp_path, decision, head=HEAD, count=3):
    ledger = tmp_path / "runs.jsonl"
    if not ledger.exists():
        ledger.write_text("".join(json.dumps(receipt(attempt=str(i))) + "\n" for i in range(count)))
    args = ["python3", str(ROOT / "scripts/review-round-limit.py"), "test-1",
            str(ledger), str(tmp_path / "reviews")]
    if head is not None:
        args += ["--head", head]
    return subprocess.run(args, env=dict(os.environ,
        CLAVAIN_REVIEW_ROUND_TEST_KEY_FILE=str(decision[1])), capture_output=True, text=True)


def test_one_extra_round_then_consumed(tmp_path, decision):
    first = gate(tmp_path, decision)
    assert first.returncode == 0, first.stderr
    assert all(value in first.stderr for value in ("test-1", HEAD, "dummy-decision"))
    assert gate(tmp_path, decision).returncode == 25


def test_next_failure_expires_decision(tmp_path, decision):
    assert gate(tmp_path, decision).returncode == 0
    with (tmp_path / "runs.jsonl").open("a") as stream:
        stream.write(json.dumps(receipt(attempt="fourth")) + "\n")
    assert gate(tmp_path, decision).returncode == 25


@pytest.mark.parametrize("head", ["b" * 40, None, "short"])
def test_wrong_or_missing_head(tmp_path, decision, head):
    assert gate(tmp_path, decision, head=head).returncode == 25
    assert gate(tmp_path, decision).returncode == 0


def test_no_file(tmp_path, decision):
    decision[0].unlink()
    assert gate(tmp_path, decision).returncode == 25


@pytest.mark.parametrize("field,value", [("head", "b" * 40), ("accepted_failures", 4),
    ("mac", "0" * 64), ("bead", "other"), ("authority", "other"),
    ("ruling", "edited"), ("decided_at", "2026-02-01T00:00:00+00:00"),
    ("decision_id", "edited"), ("schema_version", 2)])
def test_tampered(tmp_path, decision, field, value):
    data = json.loads(decision[0].read_text())
    data[field] = value
    decision[0].write_text(json.dumps(data))
    assert gate(tmp_path, decision).returncode == 25


@pytest.mark.parametrize("mode", [0o620, 0o602, 0o666])
def test_bad_mode(tmp_path, decision, mode):
    decision[0].chmod(mode)
    assert gate(tmp_path, decision).returncode == 25


def test_symlink(tmp_path, decision):
    target = decision[0].with_suffix(".target")
    decision[0].rename(target)
    decision[0].symlink_to(target)
    assert gate(tmp_path, decision).returncode == 25


def test_malformed(tmp_path, decision):
    decision[0].write_text("dummy-invalid-json")
    result = gate(tmp_path, decision)
    assert result.returncode == 26
    assert "dummy-invalid-json" not in result.stderr


def test_count_mismatch(tmp_path, decision):
    assert gate(tmp_path, decision, count=4).returncode == 25


def test_concurrent_claim(tmp_path, decision):
    # Prepare history before starting competing readers.
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text("".join(json.dumps(receipt(attempt=str(i))) + "\n" for i in range(3)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: gate(tmp_path, decision), range(2)))
    assert sorted(r.returncode for r in results) == [0, 25]


def test_writer(tmp_path, decision):
    decision[0].unlink()
    args = ["python3", str(ROOT / "scripts/review-round-decision.py"),
            "--reviews-dir", str(tmp_path / "reviews"), "--bead", "test-1", "--head", HEAD,
            "--accepted-failures", "3", "--ruling", "dummy stated limit"]
    result = subprocess.run(args, env=dict(os.environ,
        CLAVAIN_REVIEW_ROUND_TEST_KEY_FILE=str(decision[1])), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert gate(tmp_path, decision).returncode == 0
    assert subprocess.run(args, env=dict(os.environ,
        CLAVAIN_REVIEW_ROUND_TEST_KEY_FILE=str(decision[1])), capture_output=True).returncode != 0


def test_outer_preflight_does_not_spend_child_claim(tmp_path, decision):
    rows = [receipt(attempt=str(i)) for i in range(3)]
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
    args = ["python3", str(ROOT / "scripts/review-round-limit.py"), "test-1", str(ledger),
            str(tmp_path / "reviews"), "--head", HEAD, "--check-only"]
    env = dict(os.environ, CLAVAIN_REVIEW_ROUND_TEST_KEY_FILE=str(decision[1]))
    assert subprocess.run(args, env=env, capture_output=True).returncode == 0
    assert gate(tmp_path, decision).returncode == 0
    assert subprocess.run(args, env=env, capture_output=True).returncode == 25


def test_wrong_owner(tmp_path, decision, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import review_round_decision as module
    monkeypatch.setattr(module.os, "getuid", lambda: decision[0].stat().st_uid + 1)
    with pytest.raises(module.DecisionRefused, match="unsafe decision file"):
        module.secure_read(decision[0])


def test_dispatch_passes_head_to_preflight_and_child(tmp_path, decision, monkeypatch):
    monkeypatch.setenv("CLAVAIN_REVIEW_ROUND_TEST_KEY_FILE", str(decision[1]))
    # Fake ic fails before launching a provider, so the outer preflight must
    # allow resolution while leaving the child claim available.
    rows = [receipt(attempt=str(i)) for i in range(3)]
    result = invoke(tmp_path, rows, head=HEAD)
    assert result.returncode != 25, result.stderr
    assert "review receipt needs all" in result.stderr
    child = invoke(tmp_path, rows, head=HEAD, child=True)
    assert child.returncode == 1
    assert "accepting one extra review round" in child.stderr
    assert gate(tmp_path, decision).returncode == 25
    assert invoke(tmp_path, rows, head=HEAD).returncode == 25


def test_key_bad_mode(tmp_path, decision):
    decision[1].chmod(0o644)
    assert gate(tmp_path, decision).returncode == 25
