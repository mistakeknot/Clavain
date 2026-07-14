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

## Step 1: Gather ready and promoted candidates

```bash
SCOPE="${ARGUMENTS:-}"
LOCAL_READY_JSON="[]"
if command -v bd &>/dev/null; then
    if [[ -n "$SCOPE" ]]; then
        LOCAL_READY_JSON=$(bd ready --json --limit 20 --parent "$SCOPE" 2>/dev/null) || LOCAL_READY_JSON="[]"
    fi
    if [[ -z "$LOCAL_READY_JSON" || "$LOCAL_READY_JSON" == "[]" ]]; then
        LOCAL_READY_JSON=$(bd ready --json --limit 20 2>/dev/null) || LOCAL_READY_JSON="[]"
    fi
fi

# Remontoire owns canonical promotion discovery. Its helper is read-only and
# fails silent when the agency or zklw is unavailable.
REMONTOIRE_HELPER=""
for candidate in \
    "${CLAUDE_PLUGIN_ROOT:-}/scripts/remontoire-attention.sh" \
    "$HOME/.codex/clavain/scripts/remontoire-attention.sh" \
    "$HOME/projects/Sylveste/os/Clavain/scripts/remontoire-attention.sh"
do
    if [[ -f "$candidate" ]]; then
        REMONTOIRE_HELPER="$candidate"
        break
    fi
done

PROMOTIONS_JSON="[]"
if [[ -n "$REMONTOIRE_HELPER" ]] && command -v jq &>/dev/null; then
    REMONTOIRE_JSON=$(bash "$REMONTOIRE_HELPER" --format=json 2>/dev/null) || REMONTOIRE_JSON=""
    PROMOTIONS_JSON=$(jq -ce '
      select(.schema_version == "clavain.remontoire-attention/v1")
      | if .available == true then
          [(.promotions // [])[]
           | select((.labels // []) | index("remontoire-promotion"))]
        else [] end
    ' <<<"$REMONTOIRE_JSON" 2>/dev/null) || PROMOTIONS_JSON="[]"
fi

READY_JSON=$(jq -cn \
    --argjson local "${LOCAL_READY_JSON:-[]}" \
    --argjson promoted "${PROMOTIONS_JSON:-[]}" \
    '$local + $promoted | unique_by(.id)' 2>/dev/null) || READY_JSON="$LOCAL_READY_JSON"
```

`bd ready` already applies blocker-aware semantics (excludes in_progress,
blocked, deferred, hooked) — it is the right primitive, not `bd list
--ready`. If `bd` is not installed, or the current directory has no beads
database, `LOCAL_READY_JSON` stays empty. The Remontoire projection supplies
ready beads labeled `remontoire-promotion` from the agency's canonical
portfolio tracker. If either source is unavailable, continue with the other;
if both are empty, proceed to Step 3's degraded path without error.

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
- `remontoire-promotion` provenance — a bounded experiment produced evidence
  that this item is worth considering. That evidence is a positive leverage
  signal, but the promotion **must not automatically win**: compare it with
  priority, blocker impact, `dependent_count`, risk, and session continuity.

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
self-contained free-text goal description. When the recommendation is a
Remontoire promotion, identify it as coming from the canonical portfolio
backlog in the `/goal` text so the next session does not assume the bead is
stored in the current repository's tracker.
