"""Tests for namespace.py — text replacement and blocklist checking."""
from clavain_sync.namespace import apply_replacements, has_blocklist_term


def test_apply_replacements_single():
    text = "Use /compound-engineering:review for reviews"
    replacements = {"/compound-engineering:": "/clavain:"}
    result = apply_replacements(text, replacements)
    assert result == "Use /clavain:review for reviews"


def test_apply_replacements_multiple():
    text = "Run /workflows:plan then /workflows:work"
    replacements = {
        "/workflows:plan": "/clavain:write-plan",
        "/workflows:work": "/clavain:work",
    }
    result = apply_replacements(text, replacements)
    assert "/clavain:write-plan" in result
    assert "/clavain:work" in result
    assert "/workflows:" not in result


def test_apply_replacements_no_match():
    text = "No replacements needed here"
    result = apply_replacements(text, {"/old:": "/new:"})
    assert result == text


def test_apply_replacements_empty_text():
    assert apply_replacements("", {"/a:": "/b:"}) == ""


def test_apply_replacements_empty_replacements():
    assert apply_replacements("hello", {}) == "hello"


def test_apply_replacements_overlapping_patterns():
    """Longest match wins regardless of dict order."""
    text = "Run /workflows:plan then /workflows:work"
    replacements = {
        "/workflows:": "/clavain:",
        "/workflows:plan": "/clavain:write-plan",
    }
    result = apply_replacements(text, replacements)
    assert result == "Run /clavain:write-plan then /clavain:work"


def test_has_blocklist_term_found():
    text = "This mentions rails_model in context"
    blocklist = ["rails_model", "Every.to"]
    found = has_blocklist_term(text, blocklist)
    assert found == "rails_model"


def test_has_blocklist_term_not_found():
    text = "Clean text with no banned terms"
    blocklist = ["rails_model", "Every.to"]
    found = has_blocklist_term(text, blocklist)
    assert found is None


def test_has_blocklist_term_empty_blocklist():
    assert has_blocklist_term("anything", []) is None
