"""Markdown sync report generation."""
from __future__ import annotations

from dataclasses import dataclass, field

from .classify import Classification


@dataclass
class _AiEntry:
    file: str
    decision: str
    risk: str
    rationale: str


@dataclass
class SyncReport:
    """Collects sync results and generates a markdown report."""
    entries: list[tuple[str, Classification]] = field(default_factory=list)
    ai_decisions: list[_AiEntry] = field(default_factory=list)

    def add_entry(self, file: str, classification: Classification) -> None:
        self.entries.append((file, classification))

    def add_ai_decision(self, file: str, decision: str, risk: str, rationale: str) -> None:
        self.ai_decisions.append(_AiEntry(file, decision, risk, rationale))

    def generate(self) -> str:
        """Generate the markdown report string."""
        counts: dict[str, int] = {
            "COPY": 0, "AUTO": 0, "KEEP-LOCAL": 0,
            "CONFLICT": 0, "SKIP": 0, "REVIEW": 0,
        }
        ai_resolved = 0

        for _, cls in self.entries:
            val = cls.value
            if val.startswith("SKIP"):
                counts["SKIP"] += 1
            elif val.startswith("REVIEW"):
                counts["REVIEW"] += 1
            elif val.startswith("CONFLICT"):
                counts["CONFLICT"] += 1
            elif val in counts:
                counts[val] += 1

        for entry in self.ai_decisions:
            if entry.decision != "needs_human":
                ai_resolved += 1

        lines = [
            "",
            "═══ Clavain Upstream Sync Report ═══",
            "",
            "## Classification Summary",
            "| Category    | Count | Description                      |",
            "|-------------|-------|----------------------------------|",
            f"| COPY        | {counts['COPY']}     | Content identical                 |",
            f"| AUTO        | {counts['AUTO']}     | Upstream-only, auto-applied       |",
            f"| KEEP-LOCAL  | {counts['KEEP-LOCAL']}     | Local-only, preserved             |",
            f"| CONFLICT    | {counts['CONFLICT']}     | Both changed — {ai_resolved} AI-resolved       |",
            f"| SKIP        | {counts['SKIP']}    | Protected/deleted                 |",
            f"| REVIEW      | {counts['REVIEW']}     | Needs manual review               |",
            "",
        ]

        if self.ai_decisions:
            lines.append("## AI Decisions")
            for entry in self.ai_decisions:
                lines.append(f"- {entry.file}: **{entry.decision}** (risk: {entry.risk})")
                if entry.rationale:
                    lines.append(f'  "{entry.rationale}"')
            lines.append("")

        return "\n".join(lines)
