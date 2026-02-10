## Flux Drive Enhancement Summary

Reviewed by 3 agents on 2026-02-10 (2 completed, 1 failed — Oracle ECONNREFUSED).
Early stop after Stage 1: 1 agent (fd-v2-performance) skipped as unnecessary.

### Key Findings
- **P0**: launch.md still references v1 agent names in dispatch instructions, monitoring examples, and category heading — orchestrator would dispatch wrong agents (1/2 agents, architecture)
- **P1**: All 6 fd-v2-*.md agents missing required `<example>` blocks in description frontmatter (1/2 agents, quality)
- **P1**: using-clavain/SKILL.md routing table not updated for v2 agents — still references all 19 v1 agents (1/2 agents, architecture)
- **P1**: "Adaptive Reviewer" terminology persists in SKILL.md and synthesize.md despite rename to "Plugin Agents" (1/2 agents, architecture)
- **P1**: Compounding agent architecture doc says "YAML frontmatter" but actual format is Findings Index markdown (1/2 agents, architecture)
- **P1**: validate-roster.sh dropped subagent_type cross-reference from v1 (2/2 agents, convergent)
- **P1**: Decay "10 reviews" threshold has no review counter — date-based 60-day approximation is unreliable (2/2 agents, convergent)

### Issues to Address
- [ ] **P0-1**: Fix stale v1 agent names in launch.md line 107-108 (example subagent_type), lines 238-248 (monitoring examples), line 107 heading — from fd-v2-architecture (P0, 1/2 agents)
- [ ] **P1-1**: Add `<example>` blocks to all 6 fd-v2-*.md agent description fields — from fd-v2-quality (P1, 1/2 agents)
- [ ] **P1-2**: Fix fd-v2-correctness persona inconsistency ("Julik" name and editorial voice) — from fd-v2-quality (P1, 1/2 agents)
- [ ] **P1-3**: Fix fd-v2-quality.md heading hierarchy (## → ###) — from fd-v2-quality (P1, 1/2 agents)
- [ ] **P1-4**: Update using-clavain/SKILL.md routing table for v2 agents — from fd-v2-architecture (P1, 1/2 agents)
- [ ] **P1-5**: Replace "Adaptive Reviewer(s)" with "Plugin Agent(s)" in SKILL.md line 253 and synthesize.md lines 39, 43 — from fd-v2-architecture (P1, 1/2 agents)
- [ ] **P1-6**: Fix stale v1 agent names in synthesize.md findings.json example (lines 117, 126) — from fd-v2-architecture (P1, 1/2 agents)
- [ ] **P1-7**: Fix compounding agent architecture doc "YAML frontmatter" → "Findings Index" — from fd-v2-architecture (P1, 1/2 agents)
- [ ] **P1-8**: Add data-migration-expert and strategic-reviewer to v2 merge mapping table — from fd-v2-architecture (P1, 1/2 agents)
- [ ] **P1-9**: Replace aspirational "pipelining" instruction in launch.md Step 2.1a with realistic serial model — from fd-v2-architecture (P1, 1/2 agents)
- [ ] **P2-1**: Fix fd-v2-performance "First Step" text inconsistency ("in this order:") — from fd-v2-quality (P2, 1/2 agents)
- [ ] **P2-2**: Use $EXPECTED_COUNT in validate-roster.sh success message — from fd-v2-architecture + fd-v2-quality (P2, 2/2 agents)

### Improvements Suggested
1. Add subagent_type cross-reference to validate-roster.sh (5-10 lines of awk) — fd-v2-architecture IMP-1 + fd-v2-quality P2-2 (2/2 agents)
2. Commit to date-based decay or add review counter — not dual-metric — fd-v2-architecture IMP-2 + fd-v2-quality IMP-1 (2/2 agents)
3. Fix knowledge README example to not contradict sanitization rules — fd-v2-architecture IMP-3 + fd-v2-quality IMP-3 (2/2 agents)
4. Consider using ### headings inside compounding agent prompt for readability — fd-v2-quality IMP-2 (1/2 agents)

### Individual Agent Reports
- [fd-v2-architecture](./fd-v2-architecture.md) — needs-changes: 1 P0 (stale v1 refs in launch.md), 7 P1s, 3 improvements
- [fd-v2-quality](./fd-v2-quality.md) — needs-changes: 3 P1s (missing examples, persona inconsistency, heading hierarchy), 3 P2s, 3 improvements
- [oracle-council](./oracle-council.md) — error: ECONNREFUSED (browser automation not running)
