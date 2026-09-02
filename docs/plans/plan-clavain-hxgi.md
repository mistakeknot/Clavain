# Plan: repair the Next-goal audit chain (mk-hxgi)

Goal entity: intercore goal `fbac1a4f`. Bead: `mk-hxgi` (workspace tracker).
Branches: Clavain `fix/mk-hxgi-next-goal-audit` (worktree `.claude/worktrees/next-goal-audit`),
intercore `fix/mk-hxgi-goal-lint` (worktree `.claude/worktrees/goal-lint`).
Baseline on `origin/main`: 61 bats pass across the four next-goal/goal-shape suites; `go test ./internal/goal/` ok.

## Why (one paragraph)

Five layers guard the Next-goal block. Three have not been running since 2026-08-14 and a fourth
discards the evidence it reads. The block detector in `hooks/lib-next-goal-provenance.sh` requires
the literal `OUTCOME:`, which only 5 of 24 recorded goals carry, so real blocks (which carry the
`/goal` paste line) are invisible to both audits. Receipts are keyed on `CLAUDE_SESSION_ID`, which
is empty in the Bash tool unless `hooks/session-start.sh` ran (Claude Code 2.1.258 exports
`CLAUDE_CODE_SESSION_ID`), so a detected block would be flagged as improvised. Receipts have no
freshness bound although sessions live for months. `scripts/next-goal-verify.sh` reads `notes` and
`updated_at` from `bd show --json` and emits neither, which is how mk-ud80 ("CLEARED MOST OF THIS",
untouched since 2026-07-29) was ranked #2 off its title. Nothing compares the IDs a block cites to
the IDs the verifier saw. The intercore lint has no rule for the canonical form or for landing-only
goals. Full evidence: `bd show mk-hxgi`.

## Assumptions (open gates carried as assumptions, both reversible in one line)

- GATE 1 (form): the canonical-form rule is a **warning**, not an error. Promote later if measured.
- GATE 2 (chore): the landing-first / merge-is-not-the-agent's rules are **warnings**.
- Freshness bound: a receipt vouches only if written at or after the most recent human prompt in
  the transcript window. Fail-open when either timestamp is absent.
- Bead-ID grammar: `<prefix>-<slug>` with optional `.<n>` child suffix; prefix starts with a letter
  and has no dash. Only IDs whose prefix is known from a receipt are checked (fail-open otherwise).

## Constraints the executor must respect

- The Stop hook is capped at 5s and silently drops the whole waterfall past it. Nothing added to
  the hook path may call `bd`. `jq` over the 80-line window is acceptable (measured under 50ms).
- jq 1.7 (Debian/CI) rejects `key: a == b` inside object literals; parenthesise. No `grep -P`;
  no `\b` in grep (BSD grep); use `(^|[^A-Za-z0-9_])` and strip.
- Every fix ships with a test that FAILS on the current code and PASSES after. Record both runs.
- Do not touch `auto-stop-actions.sh` control flow. Do not widen the 80-line window.
- Clavain CI on `main` is red at the structural tier (mk-7zuk). The Clavain PR is gated on the
  bats suites passing locally (macOS) and on zklw (Linux), not on CI, until mk-7zuk lands.

## Work items

### W1 — receipts keyed on the variable Claude Code actually sets
Files: `scripts/next-goal-candidates.sh` (`PROVENANCE_SESSION=`), `scripts/next-goal-verify.sh`
(`RECEIPT_SESSION=`). Change both to
`"${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-unknown}}"`. `CLAUDE_SESSION_ID` keeps precedence
because `session-start.sh` writes it from the hook's stdin when it runs.
Tests: `next_goal_verify.bats` — "with CLAUDE_SESSION_ID unset the receipt is keyed on
CLAUDE_CODE_SESSION_ID" (unset the first, set the second to `alt-session`, assert
`$RECEIPTS/alt-session.json` exists) and "CLAUDE_SESSION_ID wins when both are set".
`next_goal_candidates.bats` — same first case for the candidates receipt.
Acceptance: the new tests fail on `origin/main` (receipt lands as `unknown.json`) and pass after.
Out of scope, filed separately: the 20 other `CLAUDE_SESSION_ID` readers in hooks/ and commands/.

### W2 — detect a block by its `/goal` paste line
File: `hooks/lib-next-goal-provenance.sh`. Add:
- `next_goal_turn_started_at <transcript>`: timestamp of the last user line whose content is a
  string or an array with no `tool_result` block (jq `-R` + `fromjson?`). Empty if none.
- `next_goal_assistant_text <transcript>`: concatenated `text` blocks of assistant lines with
  `timestamp >= turn start` (all assistant lines when turn start is empty). Real newlines.
- `next_goal_block_emitted <transcript>` (same signature as today) now: assistant text non-empty,
  contains `next[ -]goal` (case-insensitive), and contains a line matching
  `^[[:space:]]*/goal[[:space:]]+[^[:space:]]`. The `OUTCOME:` requirement is removed.
Tests (`next_goal_provenance.bats`): "detects a block that carries a /goal line and no OUTCOME:
(the 2026-09-01 shape)" — must FAIL today; "the hook's own wording 'ready-to-paste /goal text'
mid-sentence is not a block"; "a block emitted before this turn's prompt is not this turn's block"
(user line with timestamp T, assistant block with timestamp < T → not detected).
Existing fixtures keep passing (they contain `\n\n/goal Ship it.`).

### W3 — a receipt vouches only for the turn it was written in
File: `hooks/lib-next-goal-provenance.sh`. In `next_goal_provenance_warning` when state is
`reachable`, and in `next_goal_verification_warning` when state is `clean`: read `recorded_at` /
`verified_at`; if turn start and the stamp are both non-empty and `stamp[0:19] < turn_start[0:19]`,
emit a STALE message naming both stamps and asking for a re-run. Both fail-open on absence.
Tests: "a receipt older than this turn's prompt does not vouch (provenance)" and "(verification)";
"a receipt written during this turn vouches"; "no timestamps anywhere → freshness is not judged".
Acceptance: first two FAIL today (a stale receipt currently vouches).

### W4 — the verifier surfaces the evidence it reads
File: `scripts/next-goal-verify.sh`, the per-bead jq. Emit additionally: `updated_at`, `age_days`
(floor of (now − updated_at)/86400 via `fromdateiso8601`, null on parse failure), `comment_count`,
`has_notes`, `notes_excerpt` (notes with whitespace collapsed, first 200 chars). After the status
mapping: if verdict is `ok` and `has_notes` → verdict `warn`, reason
`"has notes (updated <date>) that may supersede the title — read them before citing: <excerpt>"`;
else if verdict is `ok` and `age_days > $stale` (env `CLAVAIN_NEXT_GOAL_STALE_DAYS`, default 30) →
verdict `warn`, reason `"untouched for N days — re-verify that the condition it describes still holds"`.
Status-based `warn`/`disqualified` verdicts are unchanged and take precedence.
Tests (`next_goal_verify.bats`): "a bead with notes warns and carries the excerpt — the mk-ud80
case" (FAILS today: returns ok, no excerpt); "an open bead untouched for 60 days warns as stale";
"the stale threshold is configurable"; "a fresh note-free open bead is still ok" (control);
"an unparseable updated_at yields age_days null and no stale warning".

### W5 — cited must be a subset of verified; candidates carry IDs
File: `hooks/lib-next-goal-provenance.sh`, inside `next_goal_verification_warning` after the
freshness check (state `clean`, receipt fresh):
- Block region = assistant text from the last `next[ -]goal` line to the first `/goal` line.
- Known prefixes = `roots_ok[]` of the provenance receipt that contain no `/`, plus the prefix
  (text before the first `-`) of every `beads[].id` in the verify receipt.
- Cited IDs = matches of `(^|[^A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*-[a-z0-9]{2,8}(\.[0-9]+)*` in the
  region, leading char stripped, filtered to known prefixes, de-duplicated.
- Any cited ID absent from `beads[].id` → warning naming it: "cited but never verified — re-run
  next-goal-verify.sh with every ID the block cites".
- Numbered candidate lines (`^[[:space:]]*[0-9]+\.[[:space:]]`) in the region with no known-prefix
  ID, when the block does not disclose degradation → warning: "candidate carries no tracker ID in
  a tracker-ranked block — file it, then cite it, or disclose that it is improvised".
Receipt fixtures in tests gain `beads` and `verified_at`; the verify script already writes both.
Tests: "flags a cited ID the verifier never saw"; "silent when every cited ID is in the receipt";
"flags an ID-less candidate in a non-degraded block (the merge-PR-#26 case)"; "an ID-less
candidate is fine when the block discloses degradation"; "IDs mentioned outside the block region
are not cited". First and third FAIL today.

### W6 — intercore lint: canonical form and landing-only goals (warnings)
File: `internal/goal/lint.go`, new `formProblems(text)` appended by `LintCondition` after
`shapeProblems`:
- missing `OUTCOME:` or `DONE WHEN:` → warning `canonical form: ...` pointing at
  `docs/guide-goal-shape.md`.
- text (after optional leading `/goal`) begins with merge|rebuild|reinstall|install|bump|tag|
  publish|deploy|push → warning `landing-first: ...` ("an mk-step or the tail of the current goal,
  not a successor; if it is a gate, put it under GATE and name who does it").
- `merge` within three words of `PR`/`pull request`/`#<n>` → warning `merge is not the agent's:
  ...` ("state it as a GATE with who merges").
Tests (`lint_test.go`, `TestFormRules`): the 2026-09-01 #1 text yields all three warnings and no
error (FAILS today: none); the mk-hxgi goal text yields none of the three; `TestShapeRules`'
good goal still lints clean; `TestLintCondition` unchanged.

### W7 — prose follows code
`commands/next-goal.md`: Step 3 verdict table gains the notes/stale `warn` rows and the rule that
every candidate line carries a verified bead ID unless the block discloses degradation; Step 5
says the `/goal` line is what the hook keys on and the text follows goal-shape (OUTCOME/DONE WHEN);
a note that receipts key on `CLAUDE_SESSION_ID` with `CLAUDE_CODE_SESSION_ID` fallback.
`CHANGELOG.md`: one Unreleased entry. `docs/guide-goal-shape.md`: mention the two new lint warnings.

## Sequencing

W1 and W2 in one commit (fixing W2 alone would flag every block as improvised because of W1).
Then W3, W4, W5 as separate commits, each test-first. W7 last. Push the Clavain branch, open a
draft PR. W6 on the intercore branch, its own PR. Rebase Clavain onto main after mk-7zuk lands and
confirm CI, then hand both PRs to mk to merge; publish is a separate step from zklw.

## Verification matrix

| what | where | command |
|---|---|---|
| the four bats suites + full `tests/shell` | macOS (this Mac) | `bats tests/shell/ --recursive` |
| the same | zklw (Linux, jq 1.7, GNU grep) | same, via ssh in a scratch clone of the branch |
| `internal/goal` | intercore worktree | `go test -race ./internal/goal/` |
| red-then-green | both | each new test run once before its fix (expect `not ok`) and once after |
| live smoke | this session | run candidates + verify without exporting `CLAUDE_SESSION_ID`; receipt lands under this session's `CLAUDE_CODE_SESSION_ID` |

## Out of scope

The Mac plugin-cache symlink loop (mk-i3u8); the every-substantive-response cadence rule; the
other 20 `CLAUDE_SESSION_ID` readers (follow-up bead); the script-ranked shortlist redesign
(revisit only if W1–W6 fail to hold); widening the hook's transcript window.

## Questions for review

1. Is "receipt newer than the last human prompt" the right freshness bound, or should it be the
   timestamp of the block's own assistant line minus a budget?
2. Should a `warn` verdict from W4 (notes / stale) block in the hook, or stay advisory as planned?
3. Is restricting W5's ID check to receipt-known prefixes too permissive (a bead from an unvisited
   tracker slips through)?
4. Are the W6 heuristics narrow enough to be warnings that people will not learn to ignore?
