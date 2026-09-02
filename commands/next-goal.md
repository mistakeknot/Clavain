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
lighter-weight recommendation (see Step 4) rather than omitting it.

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
| `[]` | `true` | the backlog is genuinely clear | Step 4, and say the tracker is clear |
| `[]` | `false` | we could not look at all | Step 4, and say so — see the required wording |

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

### The backlog signal (`.roadmap.backlog`)

Same object, same freshness gate — `backlog` rides inside `roadmap`, so if
`.roadmap.status` is not `fresh`, this is not usable either.

- **`deferred_ids` / `deferred`** — work that was explicitly parked. **Never
  propose a deferred bead as a next goal.** Deferring was a decision; putting
  it back up for selection silently reopens it. If a candidate from `bd ready`
  appears in `deferred_ids`, drop it and say why.
- **`blocked_ids` / `blocked`** — real dependency edges, not merely items whose
  own status says blocked. A blocked candidate can still be the right goal when
  the goal is *unblocking* it, but say what it is waiting on.
- **`module_load`** — open items per module, highest first. Use it for leverage:
  a candidate in a module carrying most of the backlog compounds more than an
  equal-priority task in a module with two items.
- **`by_priority`** — P0..P4 distribution, for whether the backlog is
  top-heavy.

Derived from `roadmap.json`, not from `docs/backlog.md`. The markdown is itself
generated from the JSON — a filtered rendering with no field the JSON lacks and
no timestamp of its own — so parsing it would add a parser and lose precision.

One caveat worth carrying: `deferred` was only ever computable after
interpath#1. The generator had no `deferred` branch, so all 18 deferred beads
read as ordinary open work. A roadmap generated before that fix reports
`deferred: 0` — which is indistinguishable from a tracker with nothing parked.
If `deferred` is 0 and the roadmap predates 2026-08-07, treat it as unknown
rather than as a real zero.

Rank and select the **top 2-4** candidates. Do not just take the top 2-4 by
`bd`'s default sort — apply the leverage lens above; a `--sort hybrid` or
`--explain` pass can help surface why something is ready if the ranking
isn't obvious from the JSON fields alone.

## Step 3: Verify the shortlist at source

Ranking picked 2-4 candidates. Before any of them is written into a block,
**re-read each one at source.** This is a command, not an act of recall:

```bash
VERIFY_HELPER=""
for candidate in \
    "${CLAUDE_PLUGIN_ROOT:-}/scripts/next-goal-verify.sh" \
    "$HOME/.codex/clavain/scripts/next-goal-verify.sh" \
    "$HOME/projects/Sylveste/os/Clavain/scripts/next-goal-verify.sh"
do
    [[ -f "$candidate" ]] && { VERIFY_HELPER="$candidate"; break; }
done

# Every bead ID the block will cite. Add --path for anything a candidate
# proposes to CREATE (see below). Exits 3 if any candidate is disqualified.
VERIFY_JSON=$(bash "$VERIFY_HELPER" solwend-abcd mk-1234 \
                   --path apps/web/components/thing/ 2>/dev/null)
```

`.beads[].verdict` is per candidate, and they are not interchangeable:

| verdict | when | what to do |
|---|---|---|
| `ok` | open | usable |
| `warn` | `in_progress` / `blocked` | usable only if the goal is to FINISH or UNBLOCK it — and the block must say which, and name what it waits on |
| `warn` | open, but `has_notes` | **read `notes_excerpt` before citing.** A note may supersede the title (mk-ud80's notes opened "CLEARED MOST OF THIS" and it was ranked #2 off its title). Cite what the notes say the bead is now, or drop it |
| `warn` | open, `age_days` past `CLAVAIN_NEXT_GOAL_STALE_DAYS` (30) | re-verify that the condition the title describes still holds; say the age in the rationale |
| `disqualified` | `closed`, `deferred`, or no such bead | **drop it.** Do not cite it, not even with a caveat |

Every entry also carries `updated_at`, `comment_count`, `has_notes` and
`notes_excerpt`: the evidence the verifier read, surfaced so the reader can
read it too.

**Every candidate line cites a verified bead ID.** The Stop hook checks that
the IDs the block cites are a subset of the IDs in the verify receipt, and
that every numbered candidate carries an ID whose tracker the receipts know.
A candidate with no ID ("Merge PR #26") cannot be verified now and cannot be
re-found next session: file it and cite the ID, or write the degraded block
(Step 4), which discloses that the candidates are improvised.

**Any candidate whose verb is build / create / add must assert the artifact's
absence** with `--path`. A bead's status cannot catch this: an epic can be
legitimately open while the thing you propose building is already on disk.

### Why this exists, and why provenance did not already cover it

Step 1's receipt answers *did a tracker answer at all*. On 2026-08-14 a block
passed that check and was still wrong: it cited `solwend-w46q` — a real ID, from
a reachable tracker, correctly formed — and recommended continuing it. The epic
had been **CLOSED as "all steps complete" for two weeks**, and the deliverables
it proposed building were already on disk: eight components, a 337-line token
sheet, a `/plan` page. The recommendation was to build what existed.

Provenance asks whether you looked. This asks whether what you cited is still
true. A stale ID and a live one are byte-identical in a block, so the reader
cannot tell them apart either — which is the same argument that put the
provenance receipt here, one level in.

The failure is context-RICH, not context-poor. The longer a session runs, the
more fluently it can name a bead from memory, and the likelier that memory
predates the close. Continuity is what makes it convincing. That is why the
check is mechanical rather than a reminder to be careful: it must not depend on
the judgement of the thing whose judgement is compromised.

### Assertions in the /goal text are claims until verified

The same discipline applies to the prose you draft. On 2026-08-14 a `/goal` also
asserted a "compounding rebase cost" across a PR stack and that its versions
"conflicted"; the stack was strictly linear and the version ladder already
consistent. One command each would have settled it. Anything phrased as a fact
about repo state — *X does not exist*, *these conflict*, *no rebase is needed* —
must either be checked before emission or rewritten as an instruction to check.
A wrong fact in a `/goal` is worse than a missing one: it arrives pre-approved
and the next session builds on it.

### This is checked, not merely requested

`scripts/next-goal-verify.sh` leaves a receipt at
`~/.cache/clavain/next-goal-verify/$CLAUDE_SESSION_ID.json`, and the Stop hook
reads it (`next_goal_verification_warning` in
`hooks/lib-next-goal-provenance.sh`). A block emitted with no receipt is flagged
as unverified; a block emitted while the receipt lists disqualified candidates
is flagged with their names. It runs only when the provenance audit is already
clean, so a session that skipped the lookup entirely gets one warning, not two.

If bd is unreachable the helper reports `ok: null`, never `true` — an unrun
check is not a passed one, and the block is then required to say the candidates
are unverified.

## Step 4: Degraded path — and which degradation it is

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

## Step 5: Emit the block

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

**The `/goal` line is what the hook keys on.** A block is detected by a line
that begins with `/goal ` and real text, within 40 lines of a "Next goal"
heading, in this turn's assistant output. Indent it as shown, put it last, and
never emit the template's `/goal <placeholder>` form as if it were a goal. The
text follows goal-shape (`docs/guide-goal-shape.md`): `OUTCOME:` first, open
calls under `GATE`, `DONE WHEN:` naming the observable condition. A goal that
opens with merge / install / deploy / ship, or that asks the agent to merge a
PR, is a landing chore or an mk-step, not a successor; the lint warns on both.

Receipts are keyed on `CLAUDE_SESSION_ID`, falling back to
`CLAUDE_CODE_SESSION_ID` (which the Bash tool exports). Run the helpers in
the turn that emits the block: a receipt is a per-turn fact, and the hook
flags a receipt older than this turn's prompt as STALE.

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
