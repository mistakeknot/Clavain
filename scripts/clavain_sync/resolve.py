"""AI-powered conflict resolution via claude -p subprocess."""
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


def analyze_conflict(
    *,
    local_path: str,
    local_content: str,
    upstream_content: str,
    ancestor_content: str,
    blocklist: list[str],
) -> ConflictDecision:
    """Analyze a conflict using Claude AI.

    Shells out to `claude -p` with structured JSON output.
    Falls back to needs_human on any failure.
    """
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
    except Exception:
        return _FALLBACK
