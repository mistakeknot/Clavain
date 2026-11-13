"""Receipt-backed review budget; dummy evidence only, no model calls."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def receipt(bead="test-1", verdict="FAIL", role="cross-lab-review", attempt="a"):
    return dict(schema_version=1, kind="dispatch-run-receipt", role=role,
                bead_id=bead, verdict_class=verdict, attempt_id=attempt,
                dispatch_id="d", outcome="completed")


def invoke(tmp_path, rows, role="cross-lab-review", bead="test-1"):
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "ic").write_text("#!/bin/sh\nexit 99\n")
    (bindir / "ic").chmod(0o755)
    env = dict(os.environ, CLAVAIN_DISPATCH_RECEIPT_FILE=str(ledger),
               PATH=str(bindir) + os.pathsep + os.environ["PATH"],
               CLAVAIN_REVIEW_RECEIPT_DIR=str(tmp_path / "reviews"))
    return subprocess.run(["bash", str(ROOT / "scripts/dispatch.sh"),
                           "--role", role, "--bead", bead, "--producer-identity", "gpt-6.1-sol",
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


def test_corrupt_history_fails_closed_without_echoing_contents(tmp_path):
    directory = tmp_path / "reviews" / "dummy__repo"
    directory.mkdir(parents=True)
    (directory / "7-head.json").write_text("dummy-invalid-json")
    result = invoke(tmp_path, [])
    assert result.returncode == 26
    assert "dummy-invalid-json" not in result.stderr


def test_no_ids_count_individual_receipts_and_summary_write_error_is_closed(tmp_path):
    rows = [receipt(attempt=None) for _ in range(3)]
    (tmp_path / "reviews").mkdir()
    (tmp_path / "reviews" / "round-limits").write_text("dummy obstruction")
    assert invoke(tmp_path, rows).returncode == 26
