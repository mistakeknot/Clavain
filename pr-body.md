## Summary
- Adds a `full-stop` skill: say "full stop" and the thread owns the change to a merge-ready PR, then stops. It verifies, opens the PR ready, registers the watcher, runs the cross-lab review loop under the existing caps, fixes CI, escalates, and never merges.
- `/describe-pr` gains a mandatory Review footer (rounds, reviewer model, per-round verdicts, final verdict at head) so a BLOCK cannot be hidden.

## Changes
- `skills/full-stop/SKILL.md` and `SKILL-compact.md`; registered in `plugin.json`; catalog and counts regenerated (27 to 28 skills).
- `commands/describe-pr.md`: Review block plus footer rules.
- `tests/structural/test_full_stop.py`: registration, hard limits and footer fields.

## Testing
Targeted structural tests (skills, commands, catalog freshness, native skill selection, new test): 507 passed at the first commit; 174 passed in the targeted rerun after the fix. `gen-catalog.py --check` fresh. The full structural suite was not completed on this loaded host.

## Notes
Plan review (cross-lab) returned FAIL on the first draft; its findings are folded in: the PR opens before review so the receipt can key on it, per-round verdicts are listed, the two-failure escalation from the routing canon is stated, CI fixes require a re-review at the final head, and the never-merge limit covers auto-merge and delegated merging. The footer is an instruction, not an enforcement mechanism.

## Merge Danger
- Door: two-way: revert the commit; no data, message or deploy effect.
- Blast Radius: adds one skill and one command footer; no hooks or scripts change.
- Evidence: structural tests before -> after: 504 -> 507 passed with the new test file.

## Review
- Rounds: 3 (plan 1, code 2)
- Reviewer model: cross-lab reviewer via packaged dispatch (producer: claude-sonnet-5-5)
- Verdicts by round: plan 1: FAIL (BLOCK), folded into the implementation; code 1: FAIL (BLOCK, 3 findings), fixed; code 2 (scoped re-review): PASS, all three ADDRESSED
- Final verdict: PASS at head 6bddeb1f4577dddafd07e08404a84a260e9ee8e6

🤖 Generated with [Claude Code](https://claude.com/claude-code)
