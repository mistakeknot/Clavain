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

Extract the bead id (required) from context. Optional flags: `--role=<role>` (routing role for `ic route dispatch`), `--bd-cwd=<path>` (the directory whose `.beads` binds the tracker that actually holds this bead — **not necessarily the repo root**; bd resolves its tracker from cwd, and a code checkout can have a different tracker binding than the hub tracker the bead lives in), `--policy=<path>` (routing.yaml for `--role` resolution; only meaningful together with `--role`). If the bead id is missing, ask the user. If `--role` is given without `--policy`, don't invent one here — the script itself falls back to `$CLAVAIN_ROUTING_POLICY`, then `<repo>/config/routing.yaml`, and reports `UNKNOWN` in §2 if neither resolves; just pass through whatever `--policy` the caller gave, or nothing.

### 2. Run the deterministic assembler

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/assemble-briefing.py" \
  --bead "<bead-id>" \
  --repo "$(pwd)" \
  ${BD_CWD:+--bd-cwd "$BD_CWD"} \
  ${ROLE:+--role "$ROLE"} \
  ${POLICY:+--policy "$POLICY"} \
  ${CLAVAIN_DECISION_CONTEXT:+--decision-context "$CLAVAIN_DECISION_CONTEXT"} \
  --target-host claude \
  --out /tmp/brief-<bead-id>.md
```

`--decision-context` is handed to `ic route dispatch --context-file`, so §2 resolves the same route the dispatcher does. `--target-host` selects whose instruction chain supplies the §3a gate headings (`claude`: AGENTS.md + CLAUDE.md up the tree and `~/.claude/CLAUDE.md`; `codex`: AGENTS.md up the tree and `~/.codex/AGENTS.md`; default `any`: both). `--tasks-project` widens the §5 card search to another bb project; cards reachable only through an attached thread are not enumerated, and §5 says so.

Without `--policy`, `--role` resolution is not inert — the script tries `$CLAVAIN_ROUTING_POLICY` and `<repo>/config/routing.yaml` before giving up and reporting `UNKNOWN` in §2 Authority.

Exit code `0` means the §4 acceptance gate passed. Exit code `2` means it failed — the script prints the specific problems (`NEXT: UNKNOWN`, `mandatory coverage: partial`, `UNKNOWN in open decisions`, `N UNKNOWN item(s)`) to stderr. **A failing gate is not a bug to paper over** — it means the bead genuinely lacks a next-action directive, a lane is unreachable, or an open decision has no recorded resolution. Surface the gate result to the user as-is; do not invent a NEXT: line or mark a lane reachable to force a pass.

Read the rendered file at `/tmp/brief-<bead-id>.md`. It already contains sections 1 (Objective), 2 (Authority — role/routing resolution, standing gate headings, DECIDED rulings scoped to a decider), 3a (Invariants, mandatory and uncapped, with a `coverage: complete|partial` line), 4 (Sources and versions — git/bead/file/query-set fingerprints), 5 (Open decisions — OPEN items, open children/deps, pending mk/vizier cards, proposed CanonGraph decisions with `decider: UNKNOWN`, since CanonGraph records no decider), 6 (Verification evidence — EVIDENCE/DEAD-END notes, gate results, run artifacts, and the unconditional freshness rule), 7 (Expiry — when to regenerate). A dropped, unsourced item is logged to stderr with `--json-debug`, not rendered as its own section.

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
