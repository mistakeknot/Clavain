"""Namespace replacement and content blocklist checking."""
from __future__ import annotations


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    """Apply all namespace replacements to text. Longest match first."""
    sorted_items = sorted(replacements.items(), key=lambda x: len(x[0]), reverse=True)
    for old, new in sorted_items:
        text = text.replace(old, new)
    return text


def has_blocklist_term(text: str, blocklist: list[str]) -> str | None:
    """Return the first blocklist term found in text, or None."""
    for term in blocklist:
        if term in text:
            return term
    return None
