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

# Bead lookup runs through a helper, not inline bash, because `bd ready`
# resolves from $PWD and stops at the nearest git root. Sylveste's subprojects
# are nested git repos: from interverse/tool-time bd reports "no beads database
# found" while the monorepo root has ready work and ~/projects has more. The
# helper walks past those boundaries, deduplicates by the database bd actually
# resolves to, and — critically — reports an unreachable tracker as its own
# state instead of as an empty backlog.
CANDIDATES_HELPER=""
for candidate in \
    "${CLAUDE_PLUGIN_ROOT:-}/scripts/next-goal-candidates.sh" \
    "$HOME/.codex/clavain/scripts/next-goal-candidates.sh" \
    "$HOME/projects/Sylveste/os/Clavain/scripts/next-goal-candidates.sh"
do
    if [[ -f "$candidate" ]]; then
        CANDIDATES_HELPER="$candidate"
        break
    fi
done

CANDIDATES_JSON=""
LOCAL_READY_JSON="[]"
TRACKER_REACHABLE="false"
LOOKUP_FAILURES="[]"
ROADMAP_JSON='{"status":"missing"}'
if [[ -n "$CANDIDATES_HELPER" ]]; then
    CANDIDATES_JSON=$(bash "$CANDIDATES_HELPER" "$SCOPE" 2>/dev/null) || CANDIDATES_JSON=""
fi
if [[ -n "$CANDIDATES_JSON" ]] && jq -e . >/dev/null 2>&1 <<<"$CANDIDATES_JSON"; then
    LOCAL_READY_JSON=$(jq -c '.candidates // []'      <<<"$CANDIDATES_JSON")
    TRACKER_REACHABLE=$(jq -r '.tracker_reachable'    <<<"$CANDIDATES_JSON")
    LOOKUP_FAILURES=$(jq -c '.lookup_failures // []'  <<<"$CANDIDATES_JSON")
    ROADMAP_JSON=$(jq -c '.roadmap // {status:"missing"}' <<<"$CANDIDATES_JSON")
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

Also run `ic goal audit --project="$PWD"` (fail-open if ic missing) — audit
defects (dormant goals, stuck closes, missing successors) are candidate
material and MUST be surfaced ahead of new work (f-030).

`bd ready` already applies blocker-aware semantics (excludes in_progress,
blocked, deferred, hooked) — it is the right primitive, not `bd list --ready`.
The helper applies it at every bead root it can reach and tags each candidate
with `_root` so you can tell which tracker to file against. The Remontoire
projection separately supplies ready beads labeled `remontoire-promotion` from
the agency's canonical portfolio tracker. If either source is unavailable,
continue with the other.

**`TRACKER_REACHABLE` is the field that decides whether this block may be
improvised.** An empty `LOCAL_READY_JSON` means one of two completely
different things, and they must not be treated alike:

| `candidates` | `tracker_reachable` | meaning | what to do |
|---|---|---|---|
| `[]` | `true` | the backlog is genuinely clear | Step 3, and say the tracker is clear |
| `[]` | `false` | we could not look at all | Step 3, and say so — see the required wording |

Until 2026-08-07 this command could not tell those apart: it ran `bd ready
--json 2>/dev/null || LOCAL_READY_JSON="[]"`, which turned "no beads database
found" into the same `[]` a clean tracker produces. Every improvised block then
presented as though it had consulted the trackers. Read `LOOKUP_FAILURES` for
the per-root reason; each entry carries `{root, reason}`.

This is the code half of bead `mk-fx3`, which closed on the strength of "the
goal-complete hook enriches from bd ready + open epics across trackers" while
the across-trackers part shipped as advice in this paragraph.

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

### The roadmap signal (`ROADMAP_JSON`)

`docs/roadmap.json` carries `modules`, `open_beads`, and `blocked` — portfolio
shape that `bd ready` alone does not show. Use it to break ties: a candidate in
a module the roadmap marks blocked, or one that closes out a module already
near-complete, outranks an isolated task of equal priority.

**Rank on it only when `.roadmap.status == "fresh"`.** The four states:

- `fresh` — generated within `stale_after_days` (default 7). Usable.
- `stale` — older than that. Do **not** rank on it; mention the staleness and
  the `age_days` if a candidate would otherwise have been justified by it.
- `undated` — no `generated_at` field, so freshness is unknowable. Treat as
  stale. Unknown is not healthy.
- `missing` / `unreadable` — no roadmap at this root. Rank without it.

Freshness comes from the embedded `generated_at`, never the file's mtime. On
2026-08-07 Sylveste's roadmap.json had an mtime of 2026-07-21 and a
`generated_at` of 2026-07-13: a rebase had touched the file without
regenerating it, and any mtime-based check would have called a 25-day-old
artifact eight days fresher than it was. Regeneration is
`scripts/sync-roadmap-json.sh`, scheduled daily by the
`com.arouth.sylveste-roadmap` LaunchAgent; a `stale` verdict therefore usually
means that scheduler has been down, which is worth saying out loud.

Rank and select the **top 2-4** candidates. Do not just take the top 2-4 by
`bd`'s default sort — apply the leverage lens above; a `--sort hybrid` or
`--explain` pass can help surface why something is ready if the ranking
isn't obvious from the JSON fields alone.

## Step 3: Degraded path — and which degradation it is

If `READY_JSON` is empty, do not fabricate bead IDs. Build candidates from what
is actually in front of you this session: open TODOs mentioned in conversation,
the natural next phase of the epic just completed, obvious follow-on work
visible in the repo (failing tests, stubbed functions, a CHANGELOG "Unreleased"
item without a corresponding bead). Present 2-3 in the same format with
`/goal <free-text description>` instead of a bead ID.

Then state which degradation produced them. This is not optional garnish — it
is the whole reason the caller can trust or distrust the block:

**`TRACKER_REACHABLE == "false"`** — the block **must** contain the literal
string `no tracker reachable`, followed by the failing root and its reason from
`LOOKUP_FAILURES`. For example:

```
(no tracker reachable — /Users/sma/projects/Sylveste/interverse/tool-time:
no beads database found. Candidates below are improvised from this session,
not ranked from the backlog.)
```

**`TRACKER_REACHABLE == "true"` with zero candidates** — the trackers answered
and there is genuinely nothing ready. Say that instead; it is a real and useful
fact, not a failure:

```
(trackers reachable, nothing ready — candidates below are new work, not
existing beads.)
```

Never emit an improvised block that reads as though it were tracker-ranked. A
reader cannot audit the difference after the fact, which is exactly how five
consecutive goals went out unlinted from this path.

### This is checked, not merely requested

`scripts/next-goal-candidates.sh` leaves a receipt at
`~/.cache/clavain/next-goal-provenance/$CLAUDE_SESSION_ID.json` recording
whether any tracker answered. The Stop hook reads it
(`hooks/lib-next-goal-provenance.sh`) and compares it against what you actually
emitted. A block that omits the degradation disclosure is taken as claiming
tracker provenance, so it needs a receipt saying a tracker was reached.

Two things follow, and the second is the one worth internalising:

1. Emitting the disclosure when it applies is enforced, not trusted.
2. **Skipping this command does not skip the check.** No run means no receipt,
   and a Next-goal block with no receipt is flagged as improvised — which it
   is. Writing the block from session context to save a tool call produces a
   warning on the next turn, not a shortcut.

Set `CLAVAIN_PROVENANCE_AUDIT_DISABLE=1` to silence the audit, or
`.claude/clavain.no-goalcadence` to opt a repo out of the whole tier.

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

Frame each candidate as a DRAFT CHARTER seed: the recommendation's /goal text
must be lint-clean (`ic goal lint-condition`) and the block should note that
`/clavain:goal-form` turns a candidate into a ratified charter (KD 7).

**Lint-clean is a command you RUN, not a property you assert.** Pipe the
drafted text through `ic goal lint-condition --text="..."` before emitting the
block. Five consecutive goals shipped unlinted from this path because the
requirement read as advice; the shape rules it now checks (ventriloquism,
plan detail, pre-ruled calls) are exactly the defects that got through.

The /goal text follows `docs/guide-goal-shape.md`. The rule that bites most
often here: you are drafting for the user to paste, so a ruling written in
their voice arrives pre-approved as canon. State open calls as questions and
keep your recommendation in the prose above the block, where it reads as your
recommendation.
