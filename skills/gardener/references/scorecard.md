# Measured scorecard for coordinator rounds

A scorecard is an optional section a coordinator adds to a status round. It makes the round say what was measured, not what was believed. Adapted from the rat-stack hill-climb prompt; source: bead mk-w2s2i.

This is a one-round technique. It does **not** authorize a standing hill-climb thread per repository: a long-running thread that wakes on a schedule is a spend (quota) and process decision for the owner. Run the scorecard inside a round you were already running.

## Rules

1. **Every number comes from a command you ran this round.** Record the command beside the number. A figure read by eye, remembered from an earlier round, or copied from a document is not a measurement; write "not measured" instead.
2. **One gap per PR.** Rank the gaps (user harm first, then distance from the repository's own standard, then size), take the top one, and give it one PR. Two reasons means two PRs.
3. **Add the lint rule first** when the bad pattern can come back, and watch it fail before the fix (see the gardener skill).
4. **Never loosen a rule to pass.** No bypassed hooks, no `--no-verify`, no widened ignore, no weakened diagnostic or test, no raised baseline.
5. **Owner sign-off** is required for: dependency version bumps, deleting or replacing cloud resources, and anything deployed to production. List such gaps for the owner; do not pick them.
6. **Prove, then report.** Run the repository's full gate (through the registered CI where there is one) and measure again the same way before claiming the gap closed.

## Scorecard template

Fill in only the lines that apply to the repository. Each row names the command. `SKILL_DIR` is the gardener skill directory (see its docs-pins section).

```
Scorecard — <repo> @ <short sha> — <UTC date>
| Item | Command run | Value |
|------|-------------|-------|
| Gate passes (and duration) | <repo check entry point> | pass/fail, <seconds> |
| Lint findings / baseline | <lint command> | <n> / <baseline n> |
| Escape hatches (type assertions, ignores) | <count command> | <n> |
| Tests that assert nothing / example tests that should be properties | <command> | <n> |
| Docs-pins drift | python3 -I "$SKILL_DIR/scripts/docs-pins.py" --root . | <n> warnings |
| Production signal (errors, latency) vs last round | <observability query> | <values> or not measured |
| Needs owner sign-off (listed, not started) | — | <list> |
```

## PR body for the chosen gap

```
Problem:  what was wrong, with the evidence (command and output).
Solution: what changed, and why this way.
Before:   the scorecard numbers, each with its command.
After:    the same numbers, measured the same way.
```

## Putting it in a status round

Keep the scorecard table in a file in the coordinator's thread storage and refer to it from the round. In the thread's `status.json`, express the chosen gap as an ordinary `in_flight` line (bead plus a one-line summary with the before and after numbers), and list owner sign-off items as `asks`. Do not add new top-level keys to `status.json` unless the status-file spec allows them.
