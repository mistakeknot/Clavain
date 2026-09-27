import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "receipt-findings.py"


def findings(tmp_path: Path, body: str) -> dict:
    output = tmp_path / "output.md"
    output.write_text(body)
    result = subprocess.run(
        ["python3", str(SCRIPT), str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_verdict_block_takes_precedence_over_body_headings(tmp_path):
    body = """1. **P0 — body heading that must not win**

--- VERDICT ---
STATUS: revise
FINDINGS: 3 (P0: 0, P1: 2, P2: 1)
SUMMARY: Changes requested.
---
"""
    assert findings(tmp_path, body) == {
        "source": "verdict",
        "P0": 0,
        "P1": 2,
        "P2": 1,
        "P3": 0,
        "total": 3,
    }


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("1. **P1 — incorrect fallback attribution**", "P1"),
        ("2. **High — missing receipt field**", "P1"),
    ],
)
def test_counts_severity_tagged_headings(tmp_path, heading, expected):
    result = findings(tmp_path, heading + "\n")
    assert result == {
        "source": "body",
        "P0": 0,
        "P1": 1 if expected == "P1" else 0,
        "P2": 0,
        "P3": 0,
        "total": 1,
    }


def test_ignores_fenced_code_findings(tmp_path):
    body = """```markdown
### P0: example only
- [P2] also example only
```
VERDICT: CLEAN
"""
    assert findings(tmp_path, body) == {
        "source": "body",
        "P0": 0,
        "P1": 0,
        "P2": 0,
        "P3": 0,
        "total": 0,
    }


def test_ignores_prose_severity_mentions(tmp_path):
    result = findings(tmp_path, "There are no P1 issues in this section.\n")
    assert result == {
        "source": "unknown",
        "P0": None,
        "P1": None,
        "P2": None,
        "P3": None,
        "total": None,
    }


@pytest.mark.parametrize(
    "clean_line",
    ["STATUS: pass", "VERDICT: CLEAN", "APPROVE", "pass"],
)
def test_clean_body_reports_observed_zeros(tmp_path, clean_line):
    assert findings(tmp_path, clean_line + "\n") == {
        "source": "body",
        "P0": 0,
        "P1": 0,
        "P2": 0,
        "P3": 0,
        "total": 0,
    }


def test_revise_without_headings_is_unknown(tmp_path):
    result = findings(tmp_path, "VERDICT: REVISE\nPlease address the review.\n")
    assert result == {
        "source": "unknown",
        "P0": None,
        "P1": None,
        "P2": None,
        "P3": None,
        "total": None,
    }


def test_missing_file_is_unknown(tmp_path):
    result = subprocess.run(
        ["python3", str(SCRIPT), str(tmp_path / "missing.md")],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "source": "unknown",
        "P0": None,
        "P1": None,
        "P2": None,
        "P3": None,
        "total": None,
    }


@pytest.mark.parametrize("body", [
    "VERDICT: REVISE\n    pass",
    "VERDICT: FAIL\nAPPROVE",
    "VERDICT: PASS WITH-CHANGES",
    "VERDICT: CLEAN-WITH-CHANGES",
    "VERDICT: REVISE\nSTATUS: pass",
    "reject\nVERDICT: CLEAN",
    "UNRUN\nVERDICT: PASS",
    "needs_attention\nSTATUS: pass",
    "VERDICT: PASS pending edits",
    "pass\nStill reviewing.",
    "APPROVE\nStill reviewing.",
])
def test_non_clean_body_never_fabricates_zero(tmp_path, body):
    result = findings(tmp_path, body)
    assert result["source"] == "unknown"
    assert all(result[key] is None for key in ("P0", "P1", "P2", "P3", "total"))


@pytest.mark.parametrize("body", [
    "Verdict: needs-changes\n- fix x\n\nAPPROVE",
    "STATUS: needs-attention\n\npass",
    "Verdict: PASS WITH CHANGES\npass",
    "CHANGES_REQUESTED\nSTATUS: pass",
])
def test_repo_verdict_vocabulary_never_fabricates_zero(tmp_path, body):
    result = findings(tmp_path, body)
    assert result["source"] == "unknown"
    assert all(result[key] is None for key in ("P0", "P1", "P2", "P3", "total"))


def test_tagged_heading_followed_by_another_finding_still_counts(tmp_path):
    result = findings(tmp_path, "### [P1] leak\n### [P2] race")
    assert result["P1"] == 1
    assert result["P2"] == 1
    assert result["total"] == 2


def test_tagged_heading_followed_by_bullet_finding_still_counts(tmp_path):
    result = findings(tmp_path, "### [P0] SQL injection\n- [P1] also in admin path")
    assert result["P0"] == 1
    assert result["P1"] == 1
    assert result["total"] == 2


@pytest.mark.parametrize("heading", [
    "### Findings: 3 (2 High, 1 Low)",
    "## High-risk items reviewed",
    "## High-level summary",
    "- Low-risk change",
    "- Medium-term plan",
    "## Critical path",
    "- P0: 0",
    "- P1: none",
    "- [P2]: N/A",
    "- **High: none**",
    "- [Low]: na",
])
def test_summary_and_empty_tags_are_not_findings(tmp_path, heading):
    assert findings(tmp_path, heading)["source"] == "unknown"


@pytest.mark.parametrize("tag", ["[High]", "**[High]**:", "**High —", "**High:", "P1:"])
def test_word_severity_tags_still_count(tmp_path, tag):
    result = findings(tmp_path, f"- {tag} connection leak")
    assert result["P1"] == result["total"] == 1


def test_severity_section_counts_only_tagged_children(tmp_path):
    result = findings(tmp_path, "### P1 findings\n\n  - [P1] leak\n  - [P1] race\n  - [P1] crash\n")
    assert result["P1"] == result["total"] == 3


def test_untagged_parent_counts_tagged_children(tmp_path):
    result = findings(tmp_path, "- Connection problems\n  - [P1] leak\n  - [P2] race\n")
    assert result["P1"] == result["P2"] == 1
    assert result["total"] == 2


def test_one_heading_remains_one_finding(tmp_path):
    result = findings(tmp_path, "### P1: connection leak and race\nTwo symptoms described in prose.\n")
    assert result["P1"] == result["total"] == 1


@pytest.mark.parametrize("p3, total", [("", 3), (", P3: 0", 3), (", P3: 2", 5)])
def test_verdict_total_uses_severity_sum(tmp_path, p3, total):
    result = findings(tmp_path, f"--- VERDICT ---\nFINDINGS: 4 (P0: 0, P1: 2, P2: 1{p3})\n---\n")
    assert result["source"] == "verdict"
    assert result["total"] == total
    assert result["P3"] == (2 if p3 == ", P3: 2" else 0)
