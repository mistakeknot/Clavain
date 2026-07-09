---
name: next-goal
description: Generate a Next-goal block (2-4 leverage-ranked candidates + recommendation + ready-to-paste /goal text) — required at the end of any goal-completion message
argument-hint: "[optional: repo path or bead-prefix to scope candidates to]"
---

# Next Goal

<next_goal_args> #$ARGUMENTS </next_goal_args>

## Structural goal-cadence doctrine

Whenever a `/goal` completes or a goal-scale milestone lands, the session's
completion message to the user **must end** with a "Next goal" block: 2-4
candidate goals, each with a one-line leverage rationale, a clear
recommendation, and ready-to-paste `/goal` text for the recommended
candidate. This is a structural requirement, not a convention — the
`goal-cadence` tier in `hooks/auto-stop-actions.sh` detects goal-completion
language via `hooks/lib-signals.sh`'s `goal-completed` signal and blocks the
turn with an instruction to run this command. This command is also safe (and
encouraged) to invoke manually any time you want a fresh set of candidates.

Never skip the block because bead data is unavailable — degrade to a
lighter-weight recommendation (see Step 3) rather than omitting it.

## Step 1: Gather candidates from `bd ready`

```bash
SCOPE="${ARGUMENTS:-}"
READY_JSON=""
if command -v bd &>/dev/null; then
    if [[ -n "$SCOPE" ]]; then
        READY_JSON=$(bd ready --json --limit 20 --parent "$SCOPE" 2>/dev/null) || READY_JSON=""
    fi
    if [[ -z "$READY_JSON" || "$READY_JSON" == "[]" ]]; then
        READY_JSON=$(bd ready --json --limit 20 2>/dev/null) || READY_JSON=""
    fi
fi
```

`bd ready` already applies blocker-aware semantics (excludes in_progress,
blocked, deferred, hooked) — it is the right primitive, not `bd list
--ready`. If `bd` is not installed, or the current directory has no beads
database, `READY_JSON` stays empty — proceed to Step 3's degraded path, do
not error or block on this.

If the repo is one of several trackers relevant to the session (e.g. a
monorepo alongside a companion plugin repo, or the workstation vs. a synced
server), and you know of other reachable bead roots from this session's
context, run `bd ready --json` in each and merge results before ranking.
Don't go hunting for trackers you have no evidence of — use what's already
in context (recent `bd` invocations, CLAUDE.md pointers, session state).

## Step 2: Rank by leverage

For each candidate in `READY_JSON`, leverage signals available directly from
the `bd ready --json` schema:
- `dependent_count` — how many other issues this unblocks (higher = more leverage)
- `priority` — lower number = higher priority (bd convention: 0 is highest)
- `issue_type` — prefer `epic`/`feature` continuations of work already in
  motion this session over unrelated `task`/`bug` entries, unless a bug is
  blocking something urgent
- Proximity to what this session just shipped — candidates that share a
  label, parent epic, or title keyword with the just-completed goal are
  higher leverage (continuing momentum) than a cold-start elsewhere

Rank and select the **top 2-4** candidates. Do not just take the top 2-4 by
`bd`'s default sort — apply the leverage lens above; a `--sort hybrid` or
`--explain` pass can help surface why something is ready if the ranking
isn't obvious from the JSON fields alone.

## Step 3: Degraded path (no bd data)

If `READY_JSON` is empty (bd unavailable, no database, or zero ready
issues), do not fabricate bead IDs. Instead:
- Look at what's actually in front of you this session: open TODOs
  mentioned in conversation, a natural next phase of the epic just
  completed, obvious follow-on work visible in the repo (failing tests,
  stubbed functions, a CHANGELOG "Unreleased" item without a corresponding
  bead).
- Present 2-3 candidates in the same format, but with `/goal <free-text
  description>` instead of a bead ID, and note plainly: "(no beads tracker
  detected — describe scope in the /goal text, or run `bd init` to start
  tracking here)".

## Step 4: Emit the block

Format exactly:

```
## Next goal

1. **<title>** — <one-line leverage rationale>
2. **<title>** — <one-line leverage rationale>
3. **<title>** — <one-line leverage rationale>   (optional 4th)

**Recommendation:** <candidate N> — <why this one, one sentence>

    /goal <ready-to-paste text for the recommended candidate, including bead ID if known>
```

Keep rationales to one line each — this block closes out the message, it
does not reopen a planning discussion. If the recommended candidate has a
bead ID, the `/goal` line should reference it (e.g. `/goal Continue
sylveste-abcd — <short description>`); if degraded (Step 3), it should be a
self-contained free-text goal description.
