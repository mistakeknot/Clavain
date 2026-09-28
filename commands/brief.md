---
name: brief
description: Assemble a role briefing for a bead — deterministic core (bd/git/ic/CanonGraph/memory, provenance-checked) plus a scoped ranked-context pass
argument-hint: "<bead-id> [--role=<role>] [--bd-cwd=<path>]"
disable-model-invocation: false
---

# /brief

Produces a self-contained briefing for a bead: enough for a fresh worker to continue representative work from the briefing alone, with zero missing-material events and no transcript read. Implements `docs/plans/2026-09-28-mk-42j9.38-role-briefing-template.md` (mk-42j9.38, landed f590fdf). Every rendered line carries a `[source]` reference back to bd/git/ic/CanonGraph/interknow/auto-memory; anything without a real source is dropped, not guessed.

## Context

<context> #$ARGUMENTS </context>

## Division of labor

Sections 1, 2, 3a, 4, 5, 6, 7 are assembled by `scripts/assemble-briefing.py` — a **deterministic script, no model in the loop**. That is the trust boundary: everything in those sections traces to a tool-verified record, not to inference. The one place a model participates is **§3b, ranked context** — the doc's sanctioned exception (§3.3b) for a scoped `/recall` fan-out, which is inherently a ranking judgment, not a fact lookup.

## Execution

### 1. Parse arguments

Extract the bead id (required) from context. Optional flags: `--role=<role>` (routing role for `ic route dispatch`), `--bd-cwd=<path>` (the directory whose `.beads` binds the tracker that actually holds this bead — **not necessarily the repo root**; bd resolves its tracker from cwd, and a code checkout can have a different tracker binding than the hub tracker the bead lives in). If the bead id is missing, ask the user.

### 2. Run the deterministic assembler

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/assemble-briefing.py" \
  --bead "<bead-id>" \
  --repo "$(pwd)" \
  ${BD_CWD:+--bd-cwd "$BD_CWD"} \
  ${ROLE:+--role "$ROLE"} \
  --out /tmp/brief-<bead-id>.md
```

Exit code `0` means the §4 acceptance gate passed. Exit code `2` means it failed — the script prints the specific problems (`NEXT: UNKNOWN`, `mandatory coverage: partial`, `UNKNOWN in open decisions`) to stderr. **A failing gate is not a bug to paper over** — it means the bead genuinely lacks a next-action directive, a lane is unreachable, or an open decision has no recorded resolution. Surface the gate result to the user as-is; do not invent a NEXT: line or mark a lane reachable to force a pass.

Read the rendered file at `/tmp/brief-<bead-id>.md`. It already contains sections 1 (Objective), 2 (Constraints), 3a (Invariants, with mandatory-coverage status), 4 (acceptance criteria), 5 (Open Decisions), 6 (lane reachability map), 7 (rejected-item log, if any items were dropped for missing provenance).

### 3. Populate §3b — ranked context (the one model-in-loop step)

The rendered file leaves a "## 3b. Ranked context" placeholder. Fill it using the same retrieval steps `/recall` uses (steps 1.5–5: CanonGraph entity graph, `docs/solutions/`, auto-memory, legacy knowledge, bd memories), scoped and budget-cut for this purpose:

- **Query**: the bead's title plus the component/path it touches (both are in §1 of the rendered file already).
- **Scope**: only what's relevant to *this* bead's work — this is a targeted lookup, not a general `/recall` sweep.
- **Budget**: cap at 5 results total (vs. `/recall`'s 10), advisory-only — each item still needs a `[source]` tag in the same style as the deterministic sections. Skip a source lane silently if its backing service is unavailable, exactly as `/recall` does.
- **Rank**: same priority order as `/recall` §5 (graph → semantic → provenance quality → recency).

Append the results under §3b in the same `- text [source]` format as the rest of the document, replacing the placeholder. If nothing relevant turns up, leave `- (none)` rather than padding with weak matches.

### 4. Present the briefing

Show the assembled file's full contents to the user (or the calling context), followed by a one-line gate summary:

```
Gate: PASS
```

or

```
Gate: FAIL — <problems, comma-separated>
```

Do not silently continue past a FAIL as though it were a PASS — report it and let the caller decide (a rotation successor or lane spawn should treat a FAIL the same way a human reading it would: as a bead that isn't ready to hand off cleanly).
