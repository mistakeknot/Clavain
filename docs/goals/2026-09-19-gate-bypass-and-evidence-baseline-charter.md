# Close the ship-class review bypass, and explain the empty vetting evidence

**Date:** 2026-09-19 · **Complexity:** C3 · **Epic:** `Sylveste-ymp2` · **Repo:** mistakeknot/Clavain

## Why (leverage)

`Sylveste-ymp2` asks that each governance loop be proven reached before anything is extended. Three plan revisions and two independent frontier rejections (Astra, Fable) converged on the same ordering: two items must land before any repair touches behaviour, and both are cheap.

The first is urgent. `commands/quality-gates.md` takes a shortcut for any diff under 20 lines touching one file — it runs a single `fd-quality` agent and skips Phases 2–3, including the ship-class `fd-safety` review that `interflux` declares mandatory. Astra reproduced selection with an 8-line single-file hook edit. A hook script is executable platform code, so this is an unreviewed-RCE path, and it sits inside the code the epic is repairing.

The second reframes everything after it. The consumer-side audit on zklw — one read-only command, absent from all three plan revisions until now — shows **`vetted_sha` empty in 20 of 20 recorded bead-closes, 8 of which auto-proceeded**, against a policy requiring `vetted_sha_matches_head: true`; and **44 of 44 patch publications auto-proceeded**. Three explanations are possible: the rule is never evaluated, an empty SHA satisfies the match, or the signal arrives inherited and is never recorded. The remaining `ymp2` stages are aimed differently depending on which holds, so establishing it is worth more than any of them.

## Scope

**In:** exclude ship-class diffs from the small-change shortcut; a regression test that fails against current code; determine and record which explanation accounts for the audit rows; file the bypass as its own bead; apply the three verified corrections to `Sylveste-zfz8` and `Sylveste-0ru1`.

**Out:** freezing automatic authorization; moving the vetting decision into an executable; the reviewer manifest and its cross-repo publish order; `Sylveste-smw4`; `Sylveste-ywqs`; `Sylveste-c53i`. Each is a later `ymp2` stage that must land behind the freeze, which this goal does not build.

## User rulings carried in

- 2026-09-19: exclude ship-class from the shortcut rather than removing the shortcut or making it opt-in — the cost saving on ordinary small edits is worth keeping.

## Acceptance criteria

1. A single-file ship-class diff under 20 lines takes the full review path; a single-file non-ship-class diff of the same size still takes the shortcut.
2. The regression test fails against `589c3a3` and passes after the change.
3. The audit rows have a written explanation naming the operative cause, with the evaluator path traced, recorded where the epic can consume it.
4. Existing structural and shell suites stay green.

## Completion condition

Handed to `/goal` verbatim; see the accompanying condition extract.

## Successor obligations

Stage C of plan revision 3 — freeze review-derived automatic authorization, in shadow first, designed against the seven named callers. Its design should be reviewed before it lands; this goal's Gate 1 answer determines whether a freeze is even the right instrument.
