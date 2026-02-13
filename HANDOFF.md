# Session Handoff

## Done
- Clodex overhaul: removed PreToolUse deny-gate (deleted autopilot.sh), replaced with behavioral contract
- Created `scripts/clodex-toggle.sh` (deterministic bash, no LLM calls)
- Rewrote `commands/clodex-toggle.md` as thin script wrapper (91→20 lines)
- Strengthened session-start clodex injection (~70 token contract with extension allowlist)
- Created `hooks/clodex-audit.sh` — PostToolUse audit hook logs violations when clodex ON
- Added clodex behavioral smoke test (test #26) + `--include-clodex` flag to runner
- Domain profile agent specs rewritten noun→verb across all 11 profiles (via Codex dispatch)
- Closed beads: Clavain-xpmp, 0b32, 8mm3, yt09, ukjq, 7qpj, fg2r

## Pending
- Clavain-29cx (P1): flux-gen + flux-drive integration — not touched this session

## Next
1. Commit all changes (clodex overhaul + domain profiles + audit hook + smoke test)
2. Publish new plugin version (v0.5.1 still has old PreToolUse hook)
3. Test clodex behavioral contract in fresh session (smoke test #26 is manual)

## Context
- Published v0.5.1 still has autopilot.sh — blocks .sh edits until republished
- Hook count now 5 (SessionStart, PostToolUse, Stop, SessionEnd)
- `.claude/clodex-toggle.flag` toggled OFF at end of session
