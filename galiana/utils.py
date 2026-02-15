#!/usr/bin/env python3
"""Shared utilities for Galiana analysis modules."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL records; skip blank and invalid lines."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def normalize_title(title: str) -> set[str]:
    """Normalize finding title to word set (lowercase, no punctuation)."""
    cleaned = re.sub(r'[^\w\s]', ' ', title.lower())
    return {word for word in cleaned.split() if word}


def titles_match(t1: str, t2: str, threshold: float = 0.6) -> bool:
    """Check if two titles match via word overlap.

    Compares normalized word sets. Match if overlap / min(len) > threshold.
    Used for fuzzy comparison of finding titles across eval runs.

    Args:
        t1: First title
        t2: Second title
        threshold: Minimum overlap ratio (default 0.6)

    Returns:
        True if titles match
    """
    words1 = normalize_title(t1)
    words2 = normalize_title(t2)

    if not words1 or not words2:
        return False

    overlap = len(words1 & words2)
    min_len = min(len(words1), len(words2))

    return (overlap / min_len) > threshold if min_len > 0 else False
