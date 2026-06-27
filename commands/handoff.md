---
name: handoff
description: Generate a concise session handoff summary as a dated markdown file, grounded in intercore run state
argument-hint: "[focus area or notes]"
---

# Session Handoff

Generate a compact, high-signal handoff file at `docs/handoffs/YYYY-MM-DD-<topic-slug>.md`. That file is the artifact — the next session reads it to resume.

**Announce:** "Generating handoff summary..."

## Step 0 — Ground in intercore (do this FIRST, before writing prose)

Intercore (`ic`) already holds the durable spine of this session: the run goal, the phase cursor, the bead scope, token spend, and the gate-checked phase history. Pull those FACTS instead of reconstructing them from the conversation. This whole step is **fail-open** — if any command errors or `ic` is absent, skip it silently and produce the plain markdown handoff (the legacy behavior). Never block on intercore.

Run this block and read the captured values:

```bash
# Resolve the active run for this project (fail-open at every step).
PROJ="$(pwd)"
RUN_ID="$(ic run current --project="$PROJ" 2>/dev/null || true)"
RUN_JSON=""; PHASE=""; PHASES=""; GOAL=""; SCOPE=""; BUDGET=""
EVENTS_JSON=""; TOKENS_JSON=""
if [[ -n "$RUN_ID" ]]; then
  RUN_JSON="$(ic --json run status "$RUN_ID" 2>/dev/null || true)"
  PHASE="$(printf '%s' "$RUN_JSON"   | jq -r '.phase      // empty' 2>/dev/null || true)"
  PHASES="$(printf '%s' "$RUN_JSON"  | jq -r '.phases | join(",") // empty' 2>/dev/null || true)"
  GOAL="$(printf '%s' "$RUN_JSON"    | jq -r '.goal       // empty' 2>/dev/null || true)"
  SCOPE="$(printf '%s' "$RUN_JSON"   | jq -r '.scope_id   // empty' 2>/dev/null || true)"
  BUDGET="$(printf '%s' "$RUN_JSON"  | jq -r '.token_budget // empty' 2>/dev/null || true)"
  EVENTS_JSON="$(ic --json run events "$RUN_ID" 2>/dev/null || true)"   # gate-checked phase transitions
  TOKENS_JSON="$(ic --json run tokens "$RUN_ID" 2>/dev/null || true)"   # input/output/total + cache_hits
fi
# Fallback when there is no run for THIS project: the unified observation layer
# lists every active run (id, phase, oodarc_role, goal). Useful for portfolio handoffs.
SITUATION_JSON="$(ic --json situation snapshot 2>/dev/null || true)"
printf 'RUN_ID=%s\nPHASE=%s/[%s]\nGOAL=%s\nSCOPE=%s\nBUDGET=%s\n' \
  "${RUN_ID:-none}" "${PHASE:-?}" "${PHASES:-?}" "${GOAL:-?}" "${SCOPE:-?}" "${BUDGET:-?}"
```

Use what you learn to make the handoff **machine-true**, not a guess:

- **Phase cursor → Directive.** If `PHASE`/`PHASES` resolved, lead the Directive with the exact resume point: `Resume run <RUN_ID> at phase '<PHASE>' (N of M: <PHASES>).` The next session knows precisely which workflow step it is on — no re-derivation.
- **Goal → topic + framing.** Prefer the run's `GOAL` for the `topic:` slug and the Directive's intent. It is the gate-authored statement of what this run is for.
- **Scope → beads.** `SCOPE` is the bead prefix for this run. Cross-check the in-progress beads you list against it so the handoff names the right tracker namespace.
- **Events → dead-end signal.** `run events` records gate results (`gate_result: pass|fail`). A recent `fail` is a real, already-recorded dead end — fold it into the Dead Ends section with its `reason`.
- **Tokens/budget → context.** If `TOKENS_JSON` shows meaningful spend against `BUDGET`, note remaining headroom in Context so the next session knows whether it can fan out.
- **No run?** `RUN_ID=none` is normal and fine — skip every intercore-derived line and write the handoff from the conversation alone, exactly as before. For a multi-project day, you may still mine `SITUATION_JSON` to list the other active runs the next session might pick up.

## What to include

Scan the full conversation and write exactly these sections, in this order. Bullets only. Absolute file paths. No padding.

### 1. Directive
The most important section. A direct instruction to the next agent.
- If a run resolved in Step 0, lead with: `> Resume run <RUN_ID> at phase '<PHASE>' (N/M). Your job is to [X]. Start by [Y]. Verify with [Z].`
- Otherwise lead with: `> Your job is to [X]. Start by [Y]. Verify with [Z].`
- Name files to edit, tests to run, commands to verify
- If multiple possible next steps, pick the highest-priority one as primary; list alternatives as `Fallback:` items
- Include blockers or open decisions the next session must resolve
- If beads are in progress, list IDs and status (e.g., `Sylveste-abc1 — in_progress, claimed`); align the prefix with the run's `scope_id` from Step 0
- If a long-running process is active (downloads, builds), include the check/restart command

### 2. Dead ends
What was tried and didn't work. Highest-signal section for preventing wasted effort.
- Format: `[approach] — [why it failed or was abandoned]`
- Include partial approaches that were promising but dropped, and why
- Fold in any gate `fail` from `run events` (Step 0) with its recorded reason — that is an authoritative, already-logged dead end
- Omit the section entirely if nothing failed this session

### 3. Non-obvious context
Things a new session can't derive from `git log`, `git status`, or CLAUDE.md:
- Why approach A was chosen over B
- Gotchas discovered (workarounds, config quirks, tool behavior)
- In-memory state: env vars set, processes running, temporary config
- Key file paths for work in progress (absolute paths)
- Token headroom vs. budget if relevant (from Step 0)

## What to OMIT

A new session will run `git log`, `git status`, and read CLAUDE.md. Do not repeat:
- Commit hashes, branch name, last commit
- List of files changed
- What's working vs broken if obvious from running tests
- Architecture or conventions already in CLAUDE.md
- Raw intercore JSON — distill it into the prose above; the run is registered separately in Step 5

## Write the file

Create `docs/handoffs/YYYY-MM-DD-<topic-slug>.md` with frontmatter. Create the directory if missing. Add the intercore fields ONLY when they resolved in Step 0 (omit the keys entirely otherwise — never write `run: none`).

```markdown
---
date: YYYY-MM-DD
session: <first 8 chars of CLAUDE_SESSION_ID or "unknown">
topic: <2-5 word topic>
beads: [list of bead IDs touched this session]
run: <RUN_ID, only if resolved>
phase: <PHASE, only if resolved>
scope: <SCOPE, only if resolved>
---

## Session Handoff — YYYY-MM-DD <brief topic>

### Directive
> Resume run <RUN_ID> at phase '<PHASE>' (N/M). Your job is to [specific task]. Start by [first action]. Verify with [command].
- Beads: [IDs and status, if any]
- Dependency chain: [if relevant]

### Dead Ends
- [approach] — [why it failed]

### Context
- [non-obvious decision or gotcha]
- [key file paths]
```

Do NOT prune old handoffs — they serve as long-term session history.

## Step 5 — Register the handoff back into intercore (push, fail-open)

So the next session's tooling can *find* this handoff instead of relying on a human to paste it, register the file as an artifact on the run. Skip silently if there was no run or `ic` errors — this is enrichment, never required.

```bash
# Only if a run resolved in Step 0. HANDOFF_FILE = the absolute path you just wrote.
if [[ -n "$RUN_ID" && -n "$PHASE" && -n "$HANDOFF_FILE" ]]; then
  ic run artifact add "$RUN_ID" --phase="$PHASE" --path="$HANDOFF_FILE" --type=handoff 2>/dev/null || true
fi
```

This makes the handoff discoverable via `ic run status <id>` and the session-start situation snapshot, so resuming the run surfaces the handoff automatically.

After registering, print only the absolute path of the file. The next session reads the file (or finds it via the run artifact) when it resumes; no other output is needed.

## Rules

- The Directive is the lead section — a new session receiving this handoff should start working immediately without asking "what should I do?"
- Intercore is **enrichment, not a dependency.** With `ic` present, ground the handoff in real run/phase/scope/token state and register it back. With `ic` absent or no active run, fall back to the exact legacy markdown behavior — never block, never error, never write placeholder `none` values.
- Do NOT pad with pleasantries, summaries of what was done, or generic advice
- Do NOT duplicate what git or CLAUDE.md already provide
- DO include session-specific knowledge that dies when this conversation closes
- If the user provides a focus area argument, weight the summary toward that topic
- Multi-agent safe: each invocation writes a uniquely-named dated file, never a shared `latest.md` symlink or memory slot
