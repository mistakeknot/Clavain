## Summary
- Adds a `full-stop` skill: say "full stop" and the thread owns the change to a merge-ready PR, then stops. It verifies, opens the PR ready, registers the watcher, runs the cross-lab review loop under the existing caps, fixes CI, escalates, and never merges.
- `/describe-pr` gains a mandatory Review footer (rounds, reviewer model, per-round verdicts, final verdict at head) so a BLOCK cannot be hidden.

## Changes
- `skills/full-stop/SKILL.md` and `SKILL-compact.md`; registered in `plugin.json`; catalog and counts regenerated (27 to 28 skills).
- `commands/describe-pr.md`: Review block plus footer rules.
- `tests/structural/test_full_stop.py`: registration, hard limits and footer fields.

## Testing
Targeted structural tests (skills, commands, catalog freshness, native skill selection, new test): 507 passed. `gen-catalog.py --check` fresh. The full structural suite was not completed on this loaded host.

## Notes
Plan review (cross-lab) returned FAIL on the first draft; its findings are folded in: the PR opens before review so the receipt can key on it, per-round verdicts are listed, the two-failure escalation from the routing canon is stated, CI fixes require a re-review at the final head, and the never-merge limit covers auto-merge and delegated merging. The footer is an instruction, not an enforcement mechanism.

## Merge Danger
- Door: two-way: revert the commit; no data, message or deploy effect.
- Blast Radius: adds one skill and one command footer; no hooks or scripts change.
- Evidence: structural tests before -> after: 504 -> 507 passed with the new test file.

## Review
- Rounds: 1 (plan only; code review pending)
- Reviewer model: cross-lab reviewer (plan)
- Verdicts by round: 1 (plan): FAIL
- Final verdict: none run on the code yet

🤖 Generated with [Claude Code](https://claude.com/claude-code)
