"""Shared helpers for Clavain structural tests."""

import yaml


def parse_frontmatter(path):
    """Parse YAML frontmatter from a markdown file.

    Returns (frontmatter_dict, body_text) or (None, full_text) if no frontmatter.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    fm = yaml.safe_load(parts[1])
    body = parts[2]
    return fm, body
