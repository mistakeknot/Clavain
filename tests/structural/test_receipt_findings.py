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
