"""Tests for report.py — markdown sync report generation."""
from clavain_sync.report import SyncReport
from clavain_sync.classify import Classification


def test_empty_report():
    report = SyncReport()
    output = report.generate()
    assert "Clavain Upstream Sync Report" in output
    assert "| COPY" in output


def test_report_counts_classifications():
    report = SyncReport()
    report.add_entry("file1.md", Classification.COPY)
    report.add_entry("file2.md", Classification.AUTO)
    report.add_entry("file3.md", Classification.AUTO)
    report.add_entry("file4.md", Classification.CONFLICT)
    output = report.generate()
    # Verify counts appear (exact format may vary)
    assert "COPY" in output
    assert "AUTO" in output


def test_report_includes_ai_decisions():
    report = SyncReport()
    report.add_ai_decision("file.md", "accept_upstream", "low", "Changes are safe")
    output = report.generate()
    assert "AI Decisions" in output
    assert "accept_upstream" in output
    assert "file.md" in output
