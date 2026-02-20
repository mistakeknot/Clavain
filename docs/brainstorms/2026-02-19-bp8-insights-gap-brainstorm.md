# bp8 Insights-Gap Epic — Brainstorm

**Bead:** Clavain-bp8
**Phase:** brainstorm (as of 2026-02-20T06:54:26Z)
**Date:** 2026-02-19

## What Happened

The bp8 epic was created from usage data showing Clavain's daily workflow doesn't match its aspirational pipeline. Seven children were scoped. Upon verification, **5 of 7 are already shipped**:

| Item | Status | Evidence |
|------|--------|----------|
| bp8.1 /fixbuild | **Closed** | commands/fixbuild.md — build loop with auto-detect |
| bp8.3 Model routing | **Closed** | commands/model-routing.md — economy/quality toggle |
| bp8.4 /strategy | **Closed** | commands/strategy.md — brainstorm→PRD pipeline |
| bp8.5 Auto-compound tuning | **Closed** | hooks/auto-compound.sh — weight≥3, 7 signals, 5-min throttle |
| bp8.6 /smoke-test | **Closed** | commands/smoke-test.md — port detect, user journeys |

Two items have remaining work:

## bp8.2: SessionEnd Backup Handoff

### Current State
- `session-handoff.sh` fires on **Stop** event (blockable). Detects uncommitted changes, in-progress beads, in-flight agents. Prompts Claude to write HANDOFF.md, update beads, commit.
- `SessionEnd` event only has `dotfiles-sync.sh` (async).
- `session-start.sh` reads `.clavain/scratch/handoff-latest.md` on startup.

### Gap
The Stop hook does the job when it fires, but it can be skipped (e.g., session killed, network drop, user closes terminal). A lightweight SessionEnd backup ensures *something* is saved even when the Stop hook didn't execute.

### Design Decision
**Belt-and-suspenders.** Keep Stop hook as primary (it can block Claude and get a thoughtful handoff). Add a lightweight SessionEnd hook as backup that:

1. Checks if Stop hook already fired this session (sentinel file exists → exit)
2. If Stop didn't fire: write a minimal machine-generated handoff:
   - `git diff --stat` → what files changed
   - `bd list --status=in_progress` → what beads are active
   - `git log --oneline -5` → recent commits
   - Write to `.clavain/scratch/handoff-<timestamp>-<session>.md`
   - Update `handoff-latest.md` symlink
3. Run `bd sync` (if available)

This is a ~50-line bash script. No Claude interaction needed (SessionEnd is async/fire-and-forget). The handoff is less useful than the Stop version (no "what I was thinking" narrative) but infinitely better than nothing.

### Implementation Notes
- New file: `hooks/session-end-handoff.sh`
- Add to `hooks.json` under `SessionEnd` array
- Check for existing handoff sentinel: `/tmp/clavain-handoff-${SESSION_ID}` (written by session-handoff.sh)
- Async execution (SessionEnd hooks don't block)

## bp8.7: Make Codex Dispatch the Default

### Current State
- `executing-plans` skill Step 2 checks for `.claude/clodex-toggle.flag`
- If flag exists → Codex dispatch (Step 2A): classify tasks, batch, dispatch via interserve
- If no flag → Direct execution (Step 2B): sequential within session

### Gap
The flag gate makes Codex dispatch opt-in. Users must know about `/clodex-toggle` and explicitly enable it. The capability exists but isn't discovered.

### Design Decision
**Make Codex dispatch the default** when independent tasks are detected. Remove the flag gate. The skill should:

1. Analyze tasks from the plan for independence (already does this in Step 2A)
2. If ≥2 independent tasks detected → dispatch via Codex (no flag needed)
3. If all tasks are sequential → direct execution (no change)
4. Keep `/clodex-toggle` as an override to *disable* Codex dispatch (inverse of current behavior)

### Implementation Notes
- Edit `skills/executing-plans/SKILL.md` Step 2:
  - Remove flag check
  - Instead: analyze plan tasks for independence
  - If independent tasks found AND Codex CLI available (`command -v codex`) → Step 2A
  - If Codex CLI not available → fall back to Step 2B with a note
- Edit `scripts/clodex-toggle.sh` to invert semantics: flag now *disables* rather than enables
- Update `commands/clodex-toggle.md` description accordingly

### Risk
Codex dispatch has a higher failure surface (network, API limits, verdict parsing). The skill already handles failures with retry/direct/skip options. The main risk is unexpected Codex invocations for users who don't have Codex CLI installed — mitigated by the `command -v codex` check.

## Open Questions

None — both items are well-scoped.

## Key Decisions

1. 5/7 bp8 items already shipped — closed with verification
2. bp8.2: Belt-and-suspenders — lightweight SessionEnd backup, not replacement
3. bp8.7: Codex dispatch becomes default when independent tasks detected + Codex available
