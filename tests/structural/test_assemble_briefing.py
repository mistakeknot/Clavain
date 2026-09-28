"""Tests for scripts/assemble-briefing.py (mk-42j9.44, implementing the
role-briefing template design, mk-42j9.38 /
docs/plans/2026-09-28-mk-42j9.38-role-briefing-template.md).

Focus: the provenance check must actually reject an unsourced item (not just
be described as doing so), note-prefix parsing matches doc §2, and the
acceptance gate is driven by structured state rather than substring-scanning
rendered text (a real bug found and fixed while building this: a note that
merely *mentions* the phrase "NEXT: UNKNOWN" once tripped the gate).
"""

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("assemble_briefing", SCRIPTS / "assemble-briefing.py")
ab = importlib.util.module_from_spec(SPEC)
# Register before exec: the module defines @dataclass classes, and the
# dataclass decorator resolves type hints via sys.modules[cls.__module__] --
# it must already be there when exec_module runs the class bodies.
sys.modules["assemble_briefing"] = ab
SPEC.loader.exec_module(ab)


def test_script_exists_and_is_executable():
    script = SCRIPTS / "assemble-briefing.py"
    assert script.exists()
    assert script.stat().st_mode & 0o111


class TestProvenanceCheck:
    """The assembler rejects any rendered item that has no source reference
    (doc §4) -- this is what keeps the briefing a view, not a store."""

    def test_item_with_source_is_rendered(self):
        section = ab.Section("Test")
        rejected: list[ab.RejectedItem] = []
        section.add("a sourced fact", "bd:mk-1", rejected)
        assert len(section.lines) == 1
        assert "[bd:mk-1]" in section.lines[0]
        assert rejected == []

    def test_item_with_no_source_is_rejected_not_rendered(self):
        section = ab.Section("Test")
        rejected: list[ab.RejectedItem] = []
        section.add("an unsourced claim", "", rejected)
        assert section.lines == []  # never rendered
        assert len(rejected) == 1
        assert rejected[0].text == "an unsourced claim"
        assert rejected[0].section == "Test"

    def test_item_with_whitespace_only_source_is_rejected(self):
        section = ab.Section("Test")
        rejected: list[ab.RejectedItem] = []
        section.add("another claim", "   ", rejected)
        assert section.lines == []
        assert len(rejected) == 1

    def test_item_with_none_source_is_rejected(self):
        section = ab.Section("Test")
        rejected: list[ab.RejectedItem] = []
        section.add("claim with None source", None, rejected)
        assert section.lines == []
        assert len(rejected) == 1

    def test_rejection_does_not_crash_subsequent_adds(self):
        """One unsourced item degrades one line, not the whole briefing."""
        section = ab.Section("Test")
        rejected: list[ab.RejectedItem] = []
        section.add("bad", "", rejected)
        section.add("good", "bd:mk-1", rejected)
        assert len(section.lines) == 1
        assert len(rejected) == 1

    def test_render_never_shows_an_unsourced_line(self):
        section = ab.Section("Test")
        rejected: list[ab.RejectedItem] = []
        section.add("bad", "", rejected)
        section.add("good", "bd:mk-1", rejected)
        rendered = section.render()
        assert "bad" not in rendered
        assert "good" in rendered


class TestNotePrefixParsing:
    """doc §2: NEXT:/OPEN:<key>/DECIDED:<key>/EVIDENCE:/DEAD-END:/ENV:."""

    def test_next_last_wins(self):
        notes = "NEXT: first thing\nsome plain note\nNEXT: second thing"
        parsed = ab.parse_notes(notes)
        assert parsed.next_directive == "second thing"

    def test_no_next_line_is_none_not_invented(self):
        notes = "just a plain progress note, no directive"
        parsed = ab.parse_notes(notes)
        assert parsed.next_directive is None

    def test_next_mentioned_mid_sentence_does_not_count(self):
        """A note that discusses NEXT: handling in prose must not be
        mistaken for an actual directive -- this is the same distinction
        that made the gate's substring-scan a bug (see TestGate below)."""
        notes = "Explained that NEXT: UNKNOWN is the correct output when no directive exists."
        parsed = ab.parse_notes(notes)
        assert parsed.next_directive is None

    def test_decided_supersedes_open_same_key(self):
        notes = "OPEN:placement decider=coordinator\nDECIDED:placement -- landed at abc123"
        parsed = ab.parse_notes(notes)
        assert "placement" in parsed.open_items
        assert "placement" in parsed.decided_items

    def test_evidence_and_dead_end_collected(self):
        notes = "EVIDENCE: ran tests, all green\nDEAD-END: approach X failed, see notes"
        parsed = ab.parse_notes(notes)
        assert parsed.evidence == ["ran tests, all green"]
        assert parsed.dead_ends == ["approach X failed, see notes"]

    def test_env_last_wins(self):
        notes = "ENV: STAGE=dev\nENV: STAGE=prod"
        parsed = ab.parse_notes(notes)
        assert parsed.env["STAGE"] == "prod"


class TestConstraintExtraction:
    def test_extracts_must_not_sentence(self):
        text = "Do the normal thing. You must not push to main directly."
        constraints = ab.extract_constraints(text)
        assert any("must not push to main" in c for c in constraints)

    def test_ignores_sentences_without_constraint_words(self):
        text = "This is just background information with no imperative content here."
        assert ab.extract_constraints(text) == []


class TestGate:
    """§4: a briefing does NOT meet acceptance if it shows NEXT: UNKNOWN,
    mandatory coverage: partial, or UNKNOWN in §5 -- driven by structured
    state, not rendered-text scanning."""

    def _base_assembled(self):
        s3a = ab.Section("Invariants")
        s3a.coverage = "complete"
        return {
            "sections": {"1": ab.Section("Objective"), "3a": s3a, "5": ab.Section("Open")},
            "next_unknown": False,
            "open_unknown": False,
        }

    def test_passes_when_all_structured_flags_clean(self):
        ok, problems = ab.gate_ok(self._base_assembled())
        assert ok
        assert problems == []

    def test_fails_on_next_unknown_flag(self):
        assembled = self._base_assembled()
        assembled["next_unknown"] = True
        ok, problems = ab.gate_ok(assembled)
        assert not ok
        assert "NEXT: UNKNOWN" in problems

    def test_fails_on_partial_coverage(self):
        assembled = self._base_assembled()
        assembled["sections"]["3a"].coverage = "partial: canongraph unavailable (test)"
        ok, problems = ab.gate_ok(assembled)
        assert not ok
        assert any("partial" in p for p in problems)

    def test_fails_on_open_unknown_flag(self):
        assembled = self._base_assembled()
        assembled["open_unknown"] = True
        ok, problems = ab.gate_ok(assembled)
        assert not ok
        assert any("UNKNOWN in open decisions" in p for p in problems)

    def test_a_note_merely_mentioning_the_phrase_does_not_fail_the_gate(self):
        """Regression test for the bug found assembling a real briefing for
        mk-42j9.44: its own notes read '...correctly gates FAILED on NEXT:
        UNKNOWN + mandatory coverage: partial...', and a naive
        '"NEXT: UNKNOWN" in line' scan over rendered §1 text tripped on that
        mention even though a real NEXT: directive was present and parsed
        correctly. The gate must only consult next_unknown/open_unknown/
        coverage, never re-derive them by scanning rendered prose."""
        assembled = self._base_assembled()
        assembled["sections"]["1"].add(
            "Recent note: ...correctly gates FAILED on NEXT: UNKNOWN + mandatory coverage: partial...",
            "bd:mk-1#notes",
            [],
        )
        assembled["next_unknown"] = False  # a real NEXT: line was present
        ok, problems = ab.gate_ok(assembled)
        assert ok, f"gate must not trip on a mention in prose: {problems}"


def test_bd_cwd_flag_present_in_cli():
    """--bd-cwd must exist: bd resolves its tracker from cwd, which is not
    necessarily --repo (e.g. zklw's hub tracker at /home/mk/hub vs. a code
    checkout's own .beads)."""
    text = (SCRIPTS / "assemble-briefing.py").read_text()
    assert "--bd-cwd" in text
    assert "CLAVAIN_BD_CWD" in text
