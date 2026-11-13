"""Receipt-backed review budget; dummy evidence only, no model calls."""
import json
import fcntl
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def receipt(bead="test-1", verdict="FAIL", role="cross-lab-review", attempt="a"):
    return dict(schema_version=1, kind="dispatch-run-receipt", role=role,
                bead_id=bead, verdict_class=verdict, attempt_id=attempt,
                dispatch_id="d", outcome="completed")


def invoke(tmp_path, rows, role="cross-lab-review", bead="test-1", child=False):
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "ic").write_text("#!/bin/sh\nexit 99\n")
    (bindir / "ic").chmod(0o755)
    env = dict(os.environ, CLAVAIN_DISPATCH_RECEIPT_FILE=str(ledger),
               PATH=str(bindir) + os.pathsep + os.environ["PATH"],
               CLAVAIN_REVIEW_RECEIPT_DIR=str(tmp_path / "reviews"))
    bead_args = ["--bead", bead]
    if child:
        env.update(CLAVAIN_BEAD_ID=bead, CLAVAIN_BEAD_CONTEXT_RESOLVED="1",
                   CLAVAIN_ROUTING_PRECHECK="0")
        bead_args = ["--role-resolved"]
    return subprocess.run(["bash", str(ROOT / "scripts/dispatch.sh"),
                           "--role", role, *bead_args, "--producer-identity", "gpt-6.1-sol",
                           "--prompt", "dummy"], env=env, capture_output=True, text=True)


def test_three_failures_across_heads_refuse_before_resolver(tmp_path):
    rows = [dict(receipt(attempt=str(i)), head_sha=str(i)) for i in range(3)]
    result = invoke(tmp_path, rows)
    assert result.returncode == 25, result.stderr
    assert "3 failed review rounds" in result.stderr
    summaries = list((tmp_path / "reviews").rglob("*.md"))
    assert len(summaries) == 1
    body = summaries[0].read_text()
    assert [line for line in body.splitlines() if line[:2] in ("1.", "2.", "3.")] == [
        "1. Park the bead.", "2. Redesign on a frontier seat.",
        "3. Accept a stated limit (record the limit and its consequences)."]
    assert invoke(tmp_path, rows).returncode == 25
    assert summaries[0].read_text() == body


def test_pass_does_not_reset_and_review_roles_share_budget(tmp_path):
    rows = [receipt(attempt=str(i), role=r) for i, r in enumerate(
        ["plan-review", "validation", "cross-lab-review"])]
    rows.append(receipt(verdict="PASS", attempt="pass"))
    for role in ("plan-review", "validation", "cross-lab-review"):
        assert invoke(tmp_path, rows, role).returncode == 25


def test_only_failures_for_this_bead_count_and_duplicates_count_once(tmp_path):
    rows = [receipt(attempt="a"), receipt(attempt="a"),
            receipt(bead="other", attempt="b"), receipt(role="planning", attempt="c")]
    rows += [receipt(verdict=v, attempt=v) for v in ["PASS", "PASS_WITH_NOTES", "UNKNOWN", "NONE"]]
    result = invoke(tmp_path, rows)
    assert result.returncode == 1
    assert "could not resolve dispatch role" in result.stderr
    assert not list((tmp_path / "reviews").rglob("*.md"))


def test_pr_receipts_count_across_heads_without_double_counting_run(tmp_path):
    directory = tmp_path / "reviews" / "dummy__repo"
    directory.mkdir(parents=True)
    for i in range(3):
        r = dict(receipt(attempt=str(i)), kind="cross-lab-review-receipt", verdict="BLOCK")
        (directory / f"7-head{i}.json").write_text(json.dumps(r))
    assert invoke(tmp_path, [receipt(attempt="0")]).returncode == 25


def test_two_pr_run_pairs_are_two_rounds(tmp_path):
    directory = tmp_path / "reviews" / "dummy__repo"
    directory.mkdir(parents=True)
    rows = [receipt(attempt=str(i)) for i in range(2)]
    for i, row in enumerate(rows):
        (directory / f"7-head{i}.json").write_text(json.dumps(dict(
            row, kind="cross-lab-review-receipt", verdict="BLOCK")))
    result = invoke(tmp_path, rows)
    assert result.returncode == 1
    assert "could not resolve dispatch role" in result.stderr


def test_unattributed_legacy_receipts_do_not_count(tmp_path):
    rows = [receipt(attempt=str(i)) for i in range(3)]
    for row in rows:
        del row["bead_id"]
    result = invoke(tmp_path, rows)
    assert result.returncode == 1
    assert "could not resolve dispatch role" in result.stderr


def test_two_failures_allow_resolver_and_non_review_roles_ignore_budget(tmp_path):
    assert "could not resolve dispatch role" in invoke(tmp_path, [
        receipt(attempt="1"), receipt(attempt="2")]).stderr
    assert "could not resolve dispatch role" in invoke(tmp_path, [
        receipt(attempt=str(i)) for i in range(3)], role="planning").stderr


def test_corrupt_receipt_is_skipped_without_echoing_contents(tmp_path):
    directory = tmp_path / "reviews" / "dummy__repo"
    directory.mkdir(parents=True)
    (directory / "7-head.json").write_text("dummy-invalid-json")
    result = invoke(tmp_path, [])
    assert result.returncode == 1
    assert "skipped 1 malformed review history record" in result.stderr
    assert "dummy-invalid-json" not in result.stderr


@pytest.mark.parametrize("valid_count, expected", [(2, 0), (3, 25)])
def test_bad_ledger_rows_do_not_poison_other_beads_or_hide_valid_failures(tmp_path, valid_count, expected):
    ledger = tmp_path / "runs.jsonl"
    rows = [json.dumps(receipt(attempt=str(i))) for i in range(valid_count)]
    ledger.write_bytes((rows[0] + '\n{"dummy-torn":\n' + '\n'.join(rows[1:]) +
                        '\n[]\n' + json.dumps(dict(receipt(), attempt_id=[])) + '\n' +
                        json.dumps(dict(receipt(), role=[])) + '\n').encode() + b'\xff\n')
    result = subprocess.run(["python3", str(ROOT / "scripts/review-round-limit.py"),
                             "test-1", str(ledger), str(tmp_path / "reviews")],
                            capture_output=True, text=True)
    assert result.returncode == expected
    assert "skipped 5 malformed review history records" in result.stderr
    assert "dummy-torn" not in result.stderr


def test_reader_waits_for_writer_lock_before_reading_partial_append(tmp_path):
    ledger = tmp_path / "runs.jsonl"
    rows = [json.dumps(receipt(attempt=str(i))) for i in range(3)]
    ledger.write_text('\n'.join(rows[:2]) + '\n' + rows[2][:12])
    with (tmp_path / "runs.jsonl.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        proc = subprocess.Popen(["python3", str(ROOT / "scripts/review-round-limit.py"),
                                 "test-1", str(ledger), str(tmp_path / "reviews")],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                proc.communicate(timeout=0.3)
            with ledger.open("a") as stream:
                stream.write(rows[2][12:] + '\n')
            fcntl.flock(lock, fcntl.LOCK_UN)
            _, stderr = proc.communicate(timeout=5)
            assert proc.returncode == 25
            assert "malformed" not in stderr
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()


def test_summary_symlink_still_fails_closed(tmp_path):
    directory = tmp_path / "reviews" / "round-limits"
    directory.mkdir(parents=True)
    target = tmp_path / "dummy-target"
    target.write_text("dummy unchanged")
    (directory / "test-1.md").symlink_to(target)
    assert invoke(tmp_path, [receipt(attempt=str(i)) for i in range(3)]).returncode == 26
    assert target.read_text() == "dummy unchanged"


@pytest.mark.parametrize("marker", [
    {"experimental": True}, {"gate_review_eligible": False}, {"experiment_arm": "dummy"},
    {"policy_profile": "experiment-dummy"}, {"resolved_route": {"policy_profile": "experiment-dummy"}},
])
def test_marked_experiment_receipts_do_not_use_ordinary_budget(tmp_path, marker):
    rows = [receipt(attempt=str(i)) for i in range(2)]
    rows += [dict(receipt(attempt="experiment"), **marker)]
    directory = tmp_path / "reviews" / "dummy__repo"
    directory.mkdir(parents=True)
    (directory / "7-head.json").write_text(json.dumps(dict(
        receipt(attempt="experiment-pr"), kind="cross-lab-review-receipt", verdict="BLOCK", **marker)))
    result = invoke(tmp_path, rows)
    assert result.returncode == 1
    assert "could not resolve dispatch role" in result.stderr


def test_resolved_child_rejects_invalid_nonempty_bead(tmp_path):
    result = invoke(tmp_path, [], bead="../dummy", child=True)
    assert result.returncode == 1
    assert "invalid CLAVAIN_BEAD_ID in resolved child" in result.stderr


@pytest.mark.parametrize("bead", ["", "test-1"])
def test_resolved_child_preserves_empty_or_valid_attribution(tmp_path, bead):
    result = invoke(tmp_path, [], bead=bead, child=True)
    assert result.returncode == 1
    # It passes bead validation and reaches the later governed-contract gate.
    assert "requires an immutable policy hash" in result.stderr


def test_receipt_directory_default_handles_unset_home():
    result = subprocess.run(["bash", "-u", "-c",
                             'source "$1"; unset HOME XDG_STATE_HOME CLAVAIN_REVIEW_RECEIPT_DIR; _review_receipt_dir',
                             "_", str(ROOT / "scripts/lib-review-receipt.sh")],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "/nonexistent/.local/state/clavain/reviews"


def test_no_ids_count_individual_receipts_and_summary_write_error_is_closed(tmp_path):
    rows = [receipt(attempt=None) for _ in range(3)]
    (tmp_path / "reviews").mkdir()
    (tmp_path / "reviews" / "round-limits").write_text("dummy obstruction")
    assert invoke(tmp_path, rows).returncode == 26
