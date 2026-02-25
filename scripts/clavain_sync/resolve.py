"""Conflict resolution with deterministic pre-filter and LLM fallback.

Most conflicts are one-sided (only local or only upstream changed) and can be
resolved deterministically. The LLM is only called when both sides diverge.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class ConflictDecision:
    """Result from AI conflict analysis."""
    decision: str  # accept_upstream | keep_local | needs_human
    risk: str  # low | medium | high
    rationale: str
    blocklist_found: list[str]


_FALLBACK = ConflictDecision(
    decision="needs_human",
    risk="high",
    rationale="AI analysis failed",
    blocklist_found=[],
)

_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["accept_upstream", "keep_local", "needs_human"]},
        "rationale": {"type": "string"},
        "blocklist_found": {"type": "array", "items": {"type": "string"}},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["decision", "rationale", "risk"],
})


def _check_blocklist(content: str, blocklist: list[str]) -> list[str]:
    """Return blocklist terms found in content (case-insensitive)."""
    content_lower = content.lower()
    return [term for term in blocklist if term.lower() in content_lower]


def _try_deterministic(
    *,
    local_content: str,
    upstream_content: str,
    ancestor_content: str,
    blocklist: list[str],
) -> ConflictDecision | None:
    """Try to resolve the conflict without an LLM call.

    Returns a decision if the case is clear-cut, None if LLM analysis needed.
    """
    # Guard 1: Blocklist terms in upstream → reject upstream.
    if blocklist:
        found = _check_blocklist(upstream_content, blocklist)
        if found:
            return ConflictDecision(
                decision="keep_local",
                risk="low",
                rationale=f"Upstream contains blocklist terms: {', '.join(found)}",
                blocklist_found=found,
            )

    # Guard 2: Only upstream changed (local == ancestor) → accept upstream.
    if local_content == ancestor_content:
        return ConflictDecision(
            decision="accept_upstream",
            risk="low",
            rationale="Only upstream changed (local matches ancestor)",
            blocklist_found=[],
        )

    # Guard 3: Only local changed (upstream == ancestor) → keep local.
    if upstream_content == ancestor_content:
        return ConflictDecision(
            decision="keep_local",
            risk="low",
            rationale="Only local changed (upstream matches ancestor)",
            blocklist_found=[],
        )

    # Both sides changed → need semantic analysis.
    return None


def analyze_conflict(
    *,
    local_path: str,
    local_content: str,
    upstream_content: str,
    ancestor_content: str,
    blocklist: list[str],
) -> ConflictDecision:
    """Analyze a conflict, using deterministic checks first, LLM fallback second.

    Deterministic pre-filter handles ~70-80% of cases:
    - Blocklist terms in upstream → keep_local
    - Only upstream changed → accept_upstream
    - Only local changed → keep_local

    LLM (Claude Haiku) is only called when both sides diverged.
    """
    # Try deterministic resolution first.
    deterministic = _try_deterministic(
        local_content=local_content,
        upstream_content=upstream_content,
        ancestor_content=ancestor_content,
        blocklist=blocklist,
    )
    if deterministic is not None:
        return deterministic

    # Both sides changed — need LLM for semantic merge analysis.
    if not shutil.which("claude"):
        return _FALLBACK

    blocklist_str = ", ".join(blocklist) if blocklist else "(none)"

    prompt = f"""You are analyzing a file conflict during an upstream sync for the Clavain plugin.
Three versions exist: ancestor (at last sync), local (Clavain's version), upstream (new).

Context:
- Clavain is a general-purpose engineering plugin (no Rails/Ruby/Every.to)
- Namespace: /clavain: (not /compound-engineering: or /workflows:)
- Blocklist terms that should NOT appear: {blocklist_str}

File: {local_path}

ANCESTOR (at last sync):
{ancestor_content}

LOCAL (Clavain's current version):
{local_content}

UPSTREAM (new version, after namespace replacement):
{upstream_content}

Analyze: What did each side change? Are the changes orthogonal or conflicting?
Should Clavain accept upstream, keep local, or does this need human review?
Check for blocklist terms in the upstream changes."""

    try:
        result = subprocess.run(
            [
                "claude", "-p",
                "--output-format", "json",
                "--json-schema", _SCHEMA,
                "--model", "haiku",
                "--max-turns", "1",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
        data = json.loads(result.stdout)
        return ConflictDecision(
            decision=data.get("decision", "needs_human"),
            risk=data.get("risk", "high"),
            rationale=data.get("rationale", ""),
            blocklist_found=data.get("blocklist_found", []),
        )
    except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, ValueError, OSError):
        return _FALLBACK
