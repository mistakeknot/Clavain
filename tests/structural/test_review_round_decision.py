"""One-use round decisions with dummy keys and receipts only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import shlex

import pytest
from test_review_round_limit import ROOT, receipt, invoke

HEAD = "a" * 40

# Only this test wrapper patches the imported key reader. No production flag
# or environment variable can enable it, and every injected key is dummy data.
DUMMY_RUNNER = """
import runpy, sys
from pathlib import Path
key, script = Path(sys.argv[1]), sys.argv[2]
sys.argv = [script, *sys.argv[3:]]
sys.path.insert(0, str(Path(script).parent))
import review_round_decision
review_round_decision.key_bytes = lambda: review_round_decision.secure_read(key, key=True)
runpy.run_path(script, run_name='__main__')
"""


def dummy_run(args, key):
    return subprocess.run([sys.executable, "-c", DUMMY_RUNNER, str(key), *args],
                          capture_output=True, text=True)


def dummy_python(tmp_path, key):
    directory = tmp_path / "bin"
    directory.mkdir(exist_ok=True)
    shim = directory / "python3"
    shim.write_text("#!/bin/sh\ncase \"$1\" in\n *review-round-limit.py) exec " +
        shlex.quote(sys.executable) + " -c " + shlex.quote(DUMMY_RUNNER) + " " +
        shlex.quote(str(key)) + " \"$@\";;\n *) exec " + shlex.quote(sys.executable) + " \"$@\";;\nesac\n")
    shim.chmod(0o755)


@pytest.fixture
def decision(tmp_path):
    key = tmp_path / "dummy-key"
    key.write_bytes(b"dummy-test-key-only")
    key.chmod(0o600)
    directory = tmp_path / "reviews/round-limits/decisions"
    directory.mkdir(parents=True)
    directory.chmod(0o700)
    path = directory / "test-1.json"
    data = dict(schema_version=1, decision_id="dummy-decision", bead="test-1", head=HEAD,
                accepted_failures=3, authority="vizier", ruling="dummy stated limit",
                decided_at="2026-01-01T00:00:00+00:00")
    data["mac"] = hmac.new(key.read_bytes(), json.dumps(data, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode(), hashlib.sha256).hexdigest()
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return path, key


def gate(tmp_path, decision, head=HEAD, count=3, role=None, check_only=False):
    ledger = tmp_path / "runs.jsonl"
    if not ledger.exists():
        ledger.write_text("".join(json.dumps(receipt(attempt=str(i))) + "\n" for i in range(count)))
    args = [str(ROOT / "scripts/review-round-limit.py"), "test-1",
            str(ledger), str(tmp_path / "reviews")]
    if head is not None:
        args += ["--head", head]
    if role is not None:
        args += ["--role", role]
    if check_only:
        args += ["--check-only"]
    return dummy_run(args, decision[1])


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
    args = [str(ROOT / "scripts/review-round-decision.py"),
            "--reviews-dir", str(tmp_path / "reviews"), "--bead", "test-1", "--head", HEAD,
            "--accepted-failures", "3", "--ruling", "dummy stated limit"]
    result = dummy_run(args, decision[1])
    assert result.returncode == 0, result.stderr
    assert gate(tmp_path, decision).returncode == 0
    assert dummy_run(args, decision[1]).returncode != 0


def test_outer_preflight_does_not_spend_child_claim(tmp_path, decision):
    rows = [receipt(attempt=str(i)) for i in range(3)]
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
    args = [str(ROOT / "scripts/review-round-limit.py"), "test-1", str(ledger),
            str(tmp_path / "reviews"), "--head", HEAD, "--check-only"]
    assert dummy_run(args, decision[1]).returncode == 0
    assert gate(tmp_path, decision).returncode == 0
    assert dummy_run(args, decision[1]).returncode == 25


def test_wrong_owner(tmp_path, decision, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import review_round_decision as module
    monkeypatch.setattr(module.os, "getuid", lambda: decision[0].stat().st_uid + 1)
    with pytest.raises(module.DecisionRefused, match="unsafe decision file"):
        module.secure_read(decision[0])


def test_dispatch_passes_head_to_preflight_and_child(tmp_path, decision, monkeypatch):
    dummy_python(tmp_path, decision[1])
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


def test_key_path_ignores_environment(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import review_round_decision as module
    monkeypatch.setenv("CLAVAIN_REVIEW_ROUND_TEST_KEY_FILE", str(tmp_path / "dummy-forged"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "dummy-state"))
    seen = []
    monkeypatch.setattr(module, "secure_read", lambda path, **kwargs: seen.append(path) or b"dummy")
    assert module.key_bytes() == b"dummy"
    assert seen[0] != tmp_path / "dummy-forged"
    assert seen[0] != tmp_path / "dummy-state/clavain/review-round-decision.key"


def test_uppercase_decision_and_head_refused(tmp_path, decision):
    data = json.loads(decision[0].read_text())
    data["head"] = HEAD.upper()
    data["mac"] = hmac.new(b"dummy-test-key-only", json.dumps(
        {k: v for k, v in data.items() if k != "mac"}, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode(), hashlib.sha256).hexdigest()
    decision[0].write_text(json.dumps(data))
    assert gate(tmp_path, decision, head=HEAD.upper()).returncode == 25


def test_writer_publishes_only_complete_json(tmp_path, decision, monkeypatch):
    import importlib.util
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("decision_writer", ROOT / "scripts/review-round-decision.py")
    writer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(writer)
    monkeypatch.setattr(writer, "key_bytes", lambda: b"dummy-test-key-only")
    destination = tmp_path / "fresh-reviews/round-limits/decisions/test-1.json"
    monkeypatch.setattr(sys, "argv", ["writer", "--reviews-dir", str(tmp_path / "fresh-reviews"),
        "--bead", "test-1", "--head", HEAD, "--accepted-failures", "3", "--ruling", "dummy"])
    def crash(*args, **kwargs):
        assert not destination.exists()
        raise OSError("dummy interrupted serialization")
    monkeypatch.setattr(writer.json, "dump", crash)
    with pytest.raises(OSError):
        writer.main()
    assert not destination.exists()
    assert destination.parent.stat().st_mode & 0o777 == 0o700


def test_consumed_notice_requires_new_decision(tmp_path, decision):
    assert gate(tmp_path, decision).returncode == 0
    result = gate(tmp_path, decision)
    assert result.returncode == 25
    assert "new decision" in result.stderr


@pytest.mark.parametrize("role", ["cross-lab-review", "plan-review", "validation"])
@pytest.mark.parametrize("round_head", [False, True])
def test_outer_dispatch_forwards_head_to_actual_child(tmp_path, decision, role, round_head):
    import shutil
    # Copy scripts only; the receipt derivation stub avoids any repository or
    # remote lookup. Fake routing cannot reach a provider: the child fails its
    # immutable-policy contract after the real gate consumes the decision.
    scripts = tmp_path / "scripts"
    shutil.copytree(ROOT / "scripts", scripts, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "config", tmp_path / "config")
    with (scripts / "lib-review-receipt.sh").open("a") as stream:
        # A round-only head must never activate PR receipt preparation.
        stream.write("\n_review_receipt_prepare() { return " +
                     ("88" if round_head else "0") + "; }\n")
    dummy_python(tmp_path, decision[1])
    route = dict(profile_ref="dummy", profile=dict(backend="codex", model="dummy"))
    ic = tmp_path / "bin/ic"
    ic.write_text("#!/bin/sh\nprintf '%s\\n' " + shlex.quote(json.dumps(route)) + "\n")
    ic.chmod(0o755)
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text("".join(json.dumps(receipt(attempt=str(i))) + "\n" for i in range(3)))
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAVAIN_")}
    env.update(PATH=str(tmp_path / "bin") + os.pathsep + env["PATH"],
        CLAVAIN_DISPATCH_RECEIPT_FILE=str(ledger),
        CLAVAIN_REVIEW_RECEIPT_DIR=str(tmp_path / "reviews"), CLAVAIN_ROUTING_PRECHECK="0")
    result = subprocess.run(["bash", str(scripts / "dispatch.sh"), "--role", role,
        "--bead", "test-1", "--producer-identity", "gpt-6.1-sol",
        "--round-head" if round_head else "--head" if role == "cross-lab-review" else "--review-head", HEAD,
        "-o", str(tmp_path / "review.md"),
        "--prompt", "dummy"], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1, result.stderr
    assert f"head {HEAD} decision dummy-decision" in result.stderr
    assert "requires an immutable policy hash" in result.stderr
    assert gate(tmp_path, decision).returncode == 25


def test_writer_rejects_uppercase_head(tmp_path, decision):
    decision[0].unlink()
    args = [str(ROOT / "scripts/review-round-decision.py"), "--reviews-dir", str(tmp_path / "reviews"),
            "--bead", "test-1", "--head", HEAD.upper(), "--accepted-failures", "3", "--ruling", "dummy"]
    assert dummy_run(args, decision[1]).returncode == 26
    assert not decision[0].exists()


def test_concurrent_writers_publish_one_complete_decision(tmp_path, decision):
    decision[0].unlink()
    args = [str(ROOT / "scripts/review-round-decision.py"), "--reviews-dir", str(tmp_path / "reviews"),
            "--bead", "test-1", "--head", HEAD, "--accepted-failures", "3", "--ruling", "dummy"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: dummy_run(args, decision[1]), range(2)))
    assert sorted(r.returncode for r in results) == [0, 26]
    assert decision[0].stat().st_mode & 0o777 == 0o600
    assert gate(tmp_path, decision).returncode == 0


@pytest.mark.parametrize("role", ["plan-review", "validation"])
def test_head_only_decision_consumed_once(tmp_path, decision, role):
    dummy_python(tmp_path, decision[1])
    rows = [receipt(attempt=str(i)) for i in range(3)]
    outer = invoke(tmp_path, rows, role=role, review_head=HEAD)
    assert outer.returncode == 1, outer.stderr
    assert "could not resolve dispatch role" in outer.stderr
    child = invoke(tmp_path, rows, role=role, review_head=HEAD, child=True)
    assert child.returncode == 1, child.stderr
    assert "accepting one extra review round" in child.stderr
    assert "requires an immutable policy hash" in child.stderr
    second = invoke(tmp_path, rows, role=role, review_head=HEAD, child=True)
    assert second.returncode == 25, second.stderr
    assert "consumed" in second.stderr


@pytest.mark.parametrize("role", ["plan-review", "validation"])
def test_head_only_without_decision_refuses(tmp_path, role):
    rows = [receipt(attempt=str(i)) for i in range(3)]
    result = invoke(tmp_path, rows, role=role, review_head=HEAD)
    assert result.returncode == 25, result.stderr


@pytest.mark.parametrize("head", ["", "short", "a" * 39, "a" * 41, "A" * 40, "g" * 40])
@pytest.mark.parametrize("role", ["plan-review", "validation"])
def test_head_only_bad_hex_refuses(tmp_path, role, head):
    result = invoke(tmp_path, [], role=role, review_head=head)
    assert result.returncode == 1, result.stderr
    assert "--review-head" in result.stderr


@pytest.mark.parametrize("role", ["cross-lab-review", "planning"])
def test_head_only_wrong_role_refuses(tmp_path, role):
    result = invoke(tmp_path, [], role=role, review_head=HEAD)
    assert result.returncode == 1, result.stderr
    assert "--review-head applies to --role plan-review or validation only" in result.stderr


@pytest.mark.parametrize("role", ["plan-review", "validation"])
def test_head_only_cannot_mix_receipt_head(tmp_path, decision, role):
    dummy_python(tmp_path, decision[1])
    result = invoke(tmp_path, [receipt(attempt=str(i)) for i in range(3)],
                    role=role, head=HEAD, review_head=HEAD, child=True)
    assert result.returncode == 1, result.stderr
    assert "--review-head cannot be combined" in result.stderr
    assert gate(tmp_path, decision).returncode == 0


@pytest.mark.parametrize("role", ["plan-review", "validation"])
@pytest.mark.parametrize("child", [False, True])
def test_receipt_head_wrong_role_keeps_decision(tmp_path, decision, role, child):
    # Only child=True cases fail on the old code; outer calls never consume.
    dummy_python(tmp_path, decision[1])
    result = invoke(tmp_path, [receipt(attempt=str(i)) for i in range(3)],
                    role=role, head=HEAD, child=child)
    assert result.returncode == 1, result.stderr
    assert "apply to --role cross-lab-review only" in result.stderr
    assert "accepting one extra review round" not in result.stderr
    assert gate(tmp_path, decision).returncode == 0



@pytest.mark.parametrize("role", ["cross-lab-review", "plan-review", "validation"])
def test_round_head_consumes_once_then_refuses(tmp_path, decision, role):
    dummy_python(tmp_path, decision[1])
    rows = [receipt(attempt=str(i)) for i in range(3)]
    first = invoke(tmp_path, rows, role=role, round_head=HEAD, child=True)
    assert first.returncode == 1, first.stderr
    assert "accepting one extra review round" in first.stderr
    assert "requires an immutable policy hash" in first.stderr
    second = invoke(tmp_path, rows, role=role, round_head=HEAD, child=True)
    assert second.returncode == 25, second.stderr
    assert "consumed" in second.stderr


@pytest.mark.parametrize("role", ["cross-lab-review", "plan-review", "validation"])
@pytest.mark.parametrize("head", ["", "short", "a" * 39, "a" * 41, "A" * 40, "g" * 40])
def test_round_head_rejects_malformed_head(tmp_path, role, head):
    result = invoke(tmp_path, [], role=role, round_head=head)
    assert result.returncode == 1, result.stderr
    assert "--round-head" in result.stderr
    assert "requires a value" in result.stderr or "lowercase 40-hex" in result.stderr


@pytest.mark.parametrize("role", ["cross-lab-review", "plan-review", "validation"])
@pytest.mark.parametrize("child", [False, True])
@pytest.mark.parametrize("head", [None, "b" * 40])
def test_round_head_mismatch_or_absence_keeps_decision(tmp_path, decision, role, child, head):
    dummy_python(tmp_path, decision[1])
    result = invoke(tmp_path, [receipt(attempt=str(i)) for i in range(3)],
                    role=role, round_head=head, child=child)
    assert result.returncode == 25, result.stderr
    assert ("no exact review head" if head is None else
            "decision bead or head mismatch") in result.stderr
    assert gate(tmp_path, decision).returncode == 0


@pytest.mark.parametrize("child", [False, True])
@pytest.mark.parametrize("flag", ["head", "review_head"])
def test_conflicting_round_head_flags_keep_decision(tmp_path, decision, child, flag):
    dummy_python(tmp_path, decision[1])
    role = "cross-lab-review" if flag == "head" else "plan-review"
    result = invoke(tmp_path, [receipt(attempt=str(i)) for i in range(3)],
                    role=role, round_head=HEAD, child=child, **{flag: "b" * 40})
    assert result.returncode == 1, result.stderr
    assert "--round-head" in result.stderr and "must match" in result.stderr
    assert gate(tmp_path, decision).returncode == 0


def test_matching_round_and_receipt_heads_claim_same_decision(tmp_path, decision):
    dummy_python(tmp_path, decision[1])
    result = invoke(tmp_path, [receipt(attempt=str(i)) for i in range(3)],
                    head=HEAD, round_head=HEAD, child=True)
    assert "accepting one extra review round" in result.stderr
    assert gate(tmp_path, decision).returncode == 25


@pytest.mark.parametrize("role", ["plan-review", "validation"])
def test_matching_round_and_review_heads_keep_compatibility(tmp_path, decision, role):
    dummy_python(tmp_path, decision[1])
    result = invoke(tmp_path, [receipt(attempt=str(i)) for i in range(3)],
                    role=role, review_head=HEAD, round_head=HEAD, child=True)
    assert "accepting one extra review round" in result.stderr
    assert gate(tmp_path, decision).returncode == 25


def test_round_head_rejects_non_review_role(tmp_path):
    result = invoke(tmp_path, [], role="planning", round_head=HEAD)
    assert result.returncode == 1, result.stderr
    assert "--round-head applies to" in result.stderr


def bind_decision_role(decision, role):
    data = json.loads(decision[0].read_text())
    data["role"] = role
    data["mac"] = hmac.new(decision[1].read_bytes(), json.dumps(
        {k: v for k, v in data.items() if k != "mac"}, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode(), hashlib.sha256).hexdigest()
    decision[0].write_text(json.dumps(data))


@pytest.mark.parametrize("role", ["plan-review", "validation", "cross-lab-review"])
def test_role_bound_decision_wrong_role_preserves_right_role_claim(tmp_path, decision, role):
    bind_decision_role(decision, role)
    for other in (None, "plan-review", "validation", "cross-lab-review"):
        if other == role:
            continue
        for check_only in (False, True):
            result = gate(tmp_path, decision, role=other, check_only=check_only)
            assert result.returncode == 25, result.stderr
            assert "role mismatch" in result.stderr
    assert gate(tmp_path, decision, role=role, check_only=True).returncode == 0
    assert gate(tmp_path, decision, role=role).returncode == 0
    assert gate(tmp_path, decision, role=role).returncode == 25


@pytest.mark.parametrize("role", [None, "", "planning", 3, []])
def test_invalid_bound_role_refuses_without_consuming(tmp_path, decision, role):
    bind_decision_role(decision, role)
    assert gate(tmp_path, decision, role="plan-review").returncode == 25
    bind_decision_role(decision, "plan-review")
    assert gate(tmp_path, decision, role="plan-review").returncode == 0


@pytest.mark.parametrize("role", ["plan-review", "validation", "cross-lab-review"])
def test_writer_optional_role(tmp_path, decision, role):
    decision[0].unlink()
    args = [str(ROOT / "scripts/review-round-decision.py"),
            "--reviews-dir", str(tmp_path / "reviews"), "--bead", "test-1", "--head", HEAD,
            "--accepted-failures", "3", "--ruling", "dummy stated limit", "--role", role]
    result = dummy_run(args, decision[1])
    assert result.returncode == 0, result.stderr
    assert json.loads(decision[0].read_text())["role"] == role
    assert gate(tmp_path, decision, role=role).returncode == 0


def test_bound_role_tamper_fails_mac(tmp_path, decision):
    bind_decision_role(decision, "plan-review")
    data = json.loads(decision[0].read_text())
    data["role"] = "validation"
    decision[0].write_text(json.dumps(data))
    result = gate(tmp_path, decision, role="validation")
    assert result.returncode == 25, result.stderr
    assert "MAC mismatch" in result.stderr


def test_dispatch_plumbs_role_before_claim(tmp_path, decision):
    bind_decision_role(decision, "plan-review")
    dummy_python(tmp_path, decision[1])
    rows = [receipt(attempt=str(i)) for i in range(3)]
    for child in (False, True):
        wrong = invoke(tmp_path, rows, role="validation", review_head=HEAD, child=child)
        assert wrong.returncode == 25, wrong.stderr
        assert "role mismatch" in wrong.stderr
    right = invoke(tmp_path, rows, role="plan-review", review_head=HEAD, child=True)
    assert "accepting one extra review round" in right.stderr
    assert gate(tmp_path, decision, role="plan-review").returncode == 25


def test_unbound_plan_review_claim_blocks_cross_lab_review(tmp_path, decision):
    dummy_python(tmp_path, decision[1])
    rows = [receipt(attempt=str(i)) for i in range(3)]
    first = invoke(tmp_path, rows, role="plan-review", review_head=HEAD, child=True)
    assert "accepting one extra review round" in first.stderr
    later = invoke(tmp_path, rows, role="cross-lab-review", head=HEAD, child=True)
    assert later.returncode == 25, later.stderr
    assert "consumed" in later.stderr
