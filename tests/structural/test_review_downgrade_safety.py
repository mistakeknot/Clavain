"""Adversarial writer-to-budget regressions, using isolated real receipts."""
import importlib.util
import json
import os
import re
import string
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
spec = importlib.util.spec_from_file_location("receipt_findings", SCRIPTS / "receipt-findings.py")
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)
LOW = "### [P2] [style-naming] naming (a.py:1)\n"
PUNCTUATED_LABELS = [
    "VERDICT: FAIL (high)",
    "VERDICT: FAIL — High.",
    "VERDICT: BLOCK: high, auth bypass",
    "- Auth bypass remains, severity: high.",
]
STRUCTURAL_LABELS = [
    "- *High*: auth bypass remains", "- _High_: auth bypass remains",
    "| High | auth bypass |", "VERDICT: FAIL, high, auth bypass",
    "* *High*: auth bypass", "VERDICT: FAIL — *high*: auth bypass",
    "VERDICT: FAIL / high / auth bypass", 'VERDICT: FAIL "high"',
    "VERDICT: FAIL `high`", "High! auth",
]
HOSTILE = [
    "### [P1]: 0-day SQL injection (auth.py:42)",
    "### P1: 0-day SQL injection (auth.py:42)",
    "### [P0]: 0-byte overwrite destroys data (db.py:42)",
    "### [P1]: none of the access checks run (auth.py:42)",
    "### [P1]: N/A checks allow unauthorized writes (auth.py:42)",
    "### [Critical]: none of the data is persisted (db.py:42)",
    "### [P2]: none of the P1 checks run",
    "FINDINGS: 1 (P0: 0, P1: 1, P2: 0)",
    "- FINDINGS: 1 (P0: 0, P1: 1, P2: 0)",
    "**Findings:** 1 (P0: 0, P1: 1, P2: 0)",
    "FINDINGS: 1 (P0: 0, P1: 0, P2: 1) see below",
    "FINDINGS: 9 (P0: 0, P1: 0, P2: 1)",
    "- findings", "High: auth bypass", "[High] auth bypass",
    "Severity: High — auth bypass", "Ｐ１: auth bypass", "P\u200b1: auth bypass",
    "### [P2] Parser drops findings: on wrap (x.py:1)",
] + PUNCTUATED_LABELS + STRUCTURAL_LABELS


@pytest.mark.parametrize("fragment", HOSTILE[:6])
def test_prefix_titles_are_counted(tmp_path, fragment):
    path = tmp_path / "review.md"
    path.write_text(fragment + "\n")
    result = parser.extract_detail(path)
    assert result["total"] == 1
    assert result["P0"] + result["P1"] == 1


@pytest.mark.parametrize("fragment", ["- **High: none**", "### P1: None found",
                                       "- P1: none.", "**P0:** none", "- [P2]: N/A"])
def test_complete_empty_declarations_preserve_reporting(tmp_path, fragment):
    path = tmp_path / "review.md"
    path.write_text(fragment)
    assert parser.extract_detail(path)["findings"] == []


@pytest.fixture
def writer(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    for key, value in [("user.name", "test"), ("user.email", "test@example.invalid")]:
        subprocess.run(["git", "-C", str(repo), "config", key, value], check=True)
    (repo / "a").write_text("a")
    subprocess.run(["git", "-C", str(repo), "add", "a"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (repo / "a").write_text("b")
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "head"], check=True)
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    def write(body, expect_format_rejection=False):
        output = tmp_path / "review.md"
        output.write_text(body)
        env = dict(os.environ, CLAVAIN_REVIEW_RECEIPT_DIR=str(tmp_path / "reviews"),
                   CLAVAIN_DISPATCH_RECEIPT_FILE=str(tmp_path / "unused.jsonl"))
        result = subprocess.run(["bash", "-c", '''
source "$1/lib-review-receipt.sh"
RR_REPO=o/r RR_REPO_ID=R_test RR_PR=7 RR_HEAD="$3" RR_BASE="$4"
PRODUCER_IDENTITY=claude-sonnet-5-5 MODEL=gpt-6.1-sol CAPACITY_SUBSTITUTE_JSON=""
DISPATCH_ID=d ATTEMPT_ID=0 CLAVAIN_BEAD_ID=test-1
RESOLVED_ROUTE_JSON="{\\"policy_hash\\":\\"$6\\"}"
VALIDATOR_RELATIONSHIP=different-model
_review_receipt_prepare "$2" && _review_receipt_write "$5" 0
''', "_", str(SCRIPTS), str(repo), head, base, str(output), "a" * 64],
                                env=env, text=True, capture_output=True)
        receipt = tmp_path / "reviews" / "o__r" / f"7-{head}.json"
        if expect_format_rejection:
            assert result.returncode != 0
            assert "invalid review output format" in result.stderr
            assert not receipt.exists()
            return None
        assert result.returncode == 0, result.stderr
        return json.loads(receipt.read_text())
    return write, head


@pytest.mark.parametrize("fragment", HOSTILE + [
    "### [P1]: 0", "### [High]: none", "### P1: None found",
    "FINDINGS: 1 (P0: 0, P1: 0, P2: 1)\nFINDINGS: 1 (P0: 0, P1: 1, P2: 0)",
])
def test_writer_keeps_hostile_body_blocked(writer, fragment):
    write, _ = writer
    result = write(LOW + fragment + "\n\nVERDICT: FAIL\n")
    assert result["verdict"] == "BLOCK"
    assert "block_downgraded" not in result


@pytest.mark.parametrize("explanation", PUNCTUATED_LABELS + STRUCTURAL_LABELS + ["high-severity auth bypass", "[High] auth bypass",
                                          "the high-severity auth bypass", "contains High: auth bypass",
                                          "Ｐ１ auth bypass", "P\u200b1 auth bypass", "Critical: loss"])
def test_writer_scans_verdict_explanation(writer, tmp_path, explanation):
    write, _ = writer
    # Exercise the exact reported verdicts as well as explanatory suffixes.
    if explanation.startswith("VERDICT:"):
        body = LOW + "\n" + explanation + "\n"
    elif explanation in STRUCTURAL_LABELS or explanation.startswith("- "):
        body = LOW + explanation + "\n\nVERDICT: FAIL\n"
    else:
        body = LOW + "\nVERDICT: FAIL - " + explanation + "\n"
    path = tmp_path / "strict-review.md"
    path.write_text(body)
    assert parser.strict_clean(path) is False
    if explanation == "VERDICT: FAIL `high`":
        # This closing format is independently refused by the verdict parser;
        # strict-clean still must reject it if called on its own.
        assert write(body, expect_format_rejection=True) is None
    else:
        assert write(body)["verdict"] == "BLOCK"


@pytest.mark.parametrize("closing", [")", ".", ",", ";", "]", "}", "】", "」"])
def test_high_label_punctuation_followers(tmp_path, closing):
    path = tmp_path / "review.md"
    path.write_text(LOW + "\nVERDICT: FAIL (High" + closing + "\n")
    assert parser.strict_clean(path) is False


@pytest.mark.parametrize("raw", ["FAIL", "fail", "FAIL.", "BLOCK: two P2 follow-ups"])
def test_writer_positive_label_only_residual_and_benign_heading(writer, raw):
    write, _ = writer
    result = write("## Findings:\n" + LOW + "Do not merge; data loss. Major: auth bypass.\n\nVERDICT: " + raw)
    # The conservative evidence scan also blocks lower-severity words in an
    # explanation. Raw FAIL-class recognition remains a separate contract.
    expected = "BLOCK" if "P2" in raw else "PASS WITH NOTES"
    assert result["verdict"] == expected
    assert result["verdict_raw"] == raw
    assert result.get("block_downgraded", False) is (expected == "PASS WITH NOTES")


@pytest.mark.parametrize("alias", list(parser.SEVERITY) + ["blocker", "blockers", "blocking", "unknown"])
def test_every_severity_alias_in_non_heading_evidence_blocks(tmp_path, alias):
    path = tmp_path / "review.md"
    path.write_text(LOW + f"The assessment was / `{alias}` / after inspection.\n\nVERDICT: FAIL\n")
    assert parser.strict_clean(path) is False


@pytest.mark.parametrize("separator", list(string.punctuation) + ["☂", "•", "…", "※"])
def test_arbitrary_separators_cannot_hide_severity_words(tmp_path, separator):
    path = tmp_path / "review.md"
    path.write_text(LOW + f'\nVERDICT: FAIL {separator}High{separator} evidence\n')
    assert parser.strict_clean(path) is False


@pytest.mark.parametrize("zero_width", ["\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u034f", "\ufe0f"])
def test_zero_width_and_nfkc_labels_cannot_hide_severity(tmp_path, zero_width):
    path = tmp_path / "review.md"
    path.write_text(LOW + f'\nVERDICT: FAIL / Ｈｉ{zero_width}ｇｈ / evidence\n')
    assert parser.strict_clean(path) is False


def test_verdict_block_source_is_serialized_body_but_never_downgraded(writer):
    write, _ = writer
    result = write(LOW + "\n--- VERDICT ---\nFINDINGS: 1 (P0: 0, P1: 0, P2: 1)\n---\n\nVERDICT: FAIL\n")
    assert result["verdict"] == "BLOCK"
    assert result["findings_source"] == "body"


def run_row(attempt="0", head="a" * 40):
    return dict(schema_version=1, kind="dispatch-run-receipt", bead_id="test-1",
                role="cross-lab-review", dispatch_id="d", attempt_id=attempt,
                verdict_class="FAIL", head_sha=head)


def pr_row(head="a" * 40):
    return dict(run_row(head=head), kind="cross-lab-review-receipt", pr=7,
                verdict="PASS WITH NOTES", verdict_raw="FAIL", block_downgraded=True,
                findings_source="body", findings_total=1,
                findings=[dict(severity="P2", **{"class": "other"}, summary="naming", file=None, line=None)])


def counter(tmp_path, rows, prs=(), extra="", special=None):
    ledger = tmp_path / "runs.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows) + extra)
    directory = tmp_path / "reviews" / "o__r"
    directory.mkdir(parents=True, exist_ok=True)
    for i, row in enumerate(prs):
        suffix = "" if i == 0 else f".{i + 1}"
        (directory / f"7-{row.get('head_sha', 'a' * 40)}{suffix}.json").write_text(json.dumps(row))
    if special:
        special(directory)
    return subprocess.run(["python3", str(SCRIPTS / "review-round-limit.py"), "test-1",
                           str(ledger), str(directory.parent)], text=True, capture_output=True)


@pytest.mark.parametrize("change", [
    {"head_sha": "b" * 40}, {"role": "plan-review"}, {"verdict_raw": "PASS"},
    {"findings": [{"severity": "P1"}]}, {"findings_source": "unknown", "findings_total": None},
    {"findings_total": True}, {"findings_total": 2}, {"findings_truncated": True},
    {"findings": [None]}, {"findings": [{"severity": "P2"}]}, {"verdict": "UNKNOWN"},
    {"block_downgraded": "true"}, {"head_sha": ""}, {"experimental": True},
])
def test_inconsistent_pr_cannot_cancel(tmp_path, change):
    rows = [run_row(str(i)) for i in range(3)]
    assert counter(tmp_path, rows, [dict(pr_row(), **change)]).returncode == 25


@pytest.mark.parametrize("raw", ["FAIL", "fail", "FAIL.", "BLOCK: two P2 follow-ups"])
def test_valid_downgrade_cancels_only_its_bound_failure(tmp_path, raw):
    assert counter(tmp_path, [run_row(str(i)) for i in range(3)],
                   [dict(pr_row(), verdict_raw=raw)]).returncode == 0


@pytest.mark.parametrize("raw", ["BLOCKER", "FAILURE", "FAIL:", " BLOCK; notes ",
                                  "FaIl(two notes)", "BLOCK,P2", "BLOCK\tP2", "PASS", ""])
def test_raw_verdict_matches_shared_classifier(tmp_path, raw):
    classified = subprocess.check_output(["bash", "-c",
        'source "$1/lib-verdict.sh"; verdict_word_class "$2"', "_", str(SCRIPTS), raw], text=True).strip()
    result = counter(tmp_path, [run_row(str(i)) for i in range(3)], [dict(pr_row(), verdict_raw=raw)])
    assert result.returncode == (0 if classified == "FAIL" else 25)


def test_duplicate_bound_receipts_and_numbered_filename_cancel_once(tmp_path):
    rows = [run_row(str(i)) for i in range(4)]
    assert counter(tmp_path, rows, [pr_row(), pr_row()]).returncode == 25


def test_all_fully_bound_downgrades_cancel_their_own_failures(tmp_path):
    rows = [run_row(str(i)) for i in range(3)]
    prs = [dict(pr_row(), attempt_id=str(i)) for i in range(3)]
    assert counter(tmp_path, rows, prs).returncode == 0


@pytest.mark.parametrize("fragment", ["FINDINGS: 1 (P0: 0, P1: 0, P2: 1)",
                                      "- **FINDINGS:** 1 (P0: 0, P1: 0, P2: 1)",
                                      "Findings:", "## Findings:", "### [P3]: none."])
def test_valid_declarations_and_lower_only_controls(writer, fragment):
    write, _ = writer
    assert write(LOW + fragment + "\n\nVERDICT: FAIL")["verdict"] == "PASS WITH NOTES"


@pytest.mark.parametrize("count", [0, 2, 3])
@pytest.mark.parametrize("extra", ['{"torn":\n', '[]\n', '{"schema_version":1,"bead_id":[]}\n'])
def test_malformed_shared_history_disables_cancellation_without_global_error(tmp_path, count, extra):
    result = counter(tmp_path, [run_row(str(i)) for i in range(count)], [pr_row()], extra)
    assert result.returncode == (25 if count == 3 else 0)
    assert "cancellation" in result.stderr and "off" in result.stderr


@pytest.mark.parametrize("reverse", [False, True])
def test_malformed_matching_block_vetoes_pair_in_any_order(tmp_path, reverse):
    prs = [pr_row(), dict(pr_row(), verdict="BLOCK", verdict_class=[])]
    if reverse:
        prs.reverse()
    result = counter(tmp_path, [run_row(str(i)) for i in range(3)], prs)
    assert result.returncode == 25
    assert "cancellation" in result.stderr


def test_veto_preserves_failure_when_only_ancillary_field_is_malformed(tmp_path):
    # Every cancellation field is valid; only consider()'s type validation
    # rejects this companion. Removing the veto must expose cancellation.
    malformed = dict(pr_row(), verdict_class=[])
    result = counter(tmp_path, [run_row(str(i)) for i in range(3)], [pr_row(), malformed])
    assert result.returncode == 25


def test_conflicting_pass_run_preserves_the_failed_attempt(tmp_path):
    rows = [run_row(str(i)) for i in range(3)]
    rows.append(dict(run_row(), verdict_class="PASS"))
    assert counter(tmp_path, rows, [pr_row()]).returncode == 25


@pytest.mark.parametrize("severity", ["P0", "P1", "Critical", "High"])
def test_heading_guard_retains_block_without_lexical_scans(tmp_path, monkeypatch, severity):
    # Isolate the independent structural guard: zero declarations are omitted
    # from counts, and lexical checks are a separate layer of protection.
    monkeypatch.setattr(parser, "SEVERE_WORD", re.compile(r"(?!x)x"))
    monkeypatch.setattr(parser, "LABEL_WORDS", frozenset())
    path = tmp_path / "review.md"
    path.write_text(LOW + f"### [{severity}]: 0\n\nVERDICT: FAIL\n")
    assert parser.heading_counts(parser.visible_lines(path.read_text()))["total"] == 1
    assert parser.strict_clean(path) is False


def test_symlinked_repository_directory_keeps_its_three_block_receipts(tmp_path):
    def special(directory):
        target = tmp_path / "real-receipts"
        directory.rename(target)
        directory.symlink_to(target, target_is_directory=True)
    prs = [dict(pr_row(), attempt_id=str(i), verdict="BLOCK") for i in range(3)]
    result = counter(tmp_path, [], prs, special=special)
    assert result.returncode == 25
    assert "3 failed review rounds" in result.stderr
    assert "cancellation is off" in result.stderr


def test_unreadable_repository_directory_is_history_error(tmp_path):
    def special(directory):
        directory.chmod(0)
    prs = [dict(pr_row(), attempt_id=str(i), verdict="BLOCK") for i in range(3)]
    directory = tmp_path / "reviews" / "o__r"
    try:
        result = counter(tmp_path, [], prs, special=special)
    finally:
        directory.chmod(0o700)
    assert result.returncode == 26
    assert "cannot verify review round history" in result.stderr


@pytest.mark.parametrize("kind", ["symlink", "directory", "filename", "legacy"])
def test_unverifiable_binding_or_receipt_entry_preserves_failures(tmp_path, kind):
    rows = [run_row(str(i)) for i in range(3)]
    def special(directory):
        if kind == "symlink":
            (directory / "hidden.json").symlink_to(tmp_path / "missing")
        elif kind == "directory":
            (directory / "hidden.json").mkdir()
        elif kind == "filename":
            next(directory.glob("*.json")).rename(directory / ("7-" + "b" * 40 + ".json"))
    if kind == "legacy":
        rows[0].pop("head_sha")
    result = counter(tmp_path, rows, [pr_row()], special=special)
    assert result.returncode == 25
    if kind in ("symlink", "directory"):
        assert "cancellation" in result.stderr and "off" in result.stderr


@pytest.mark.parametrize("fragment", [HOSTILE[0], HOSTILE[7], None])
def test_real_writer_receipt_controls_round_count(writer, tmp_path, fragment):
    write, head = writer
    result = write(LOW + (fragment or "") + "\n\nVERDICT: FAIL\n")
    audit = subprocess.run(["bash", "-c", '''
source "$1/lib-verdict.sh"
source "$1/lib-dispatch-audit.sh"
ROLE=cross-lab-review ENGINE=claude MODEL=fixture REASONING_EFFORT=high
PRODUCER_IDENTITY=fixture-producer DISPATCH_ID=d CLAVAIN_BEAD_ID=test-1
ROUND_HEAD="$3" OUTPUT="$2" DISPATCH_RESULT_READY=true
VIA="" PROVIDER_EVENTS="" SUMMARY_FILE="" STARTED_TS=1700000000
CLAVAIN_DECISION_CONTEXT="" CLAVAIN_REQUIRE_USAGE=0 EXPERIMENT_ENTRY=""
for ATTEMPT_ID in 0 1 2; do _build_dispatch_run_receipt 0 || exit; done
''', "_", str(SCRIPTS), str(tmp_path / "review.md"), head],
                           text=True, capture_output=True, check=True)
    rows = [json.loads(line) for line in audit.stdout.splitlines()]
    assert len(rows) == 3
    assert all(row["verdict_class"] == "FAIL" and row["head_sha"] == head for row in rows)
    outcome = counter(tmp_path, rows)
    assert outcome.returncode == (25 if fragment else 0), result


@pytest.mark.parametrize("args", [[], ["extra", "args"]])
def test_strict_mode_bad_arity_fails(args):
    result = subprocess.run(["python3", str(SCRIPTS / "receipt-findings.py"), "--strict-clean", *args])
    assert result.returncode != 0
