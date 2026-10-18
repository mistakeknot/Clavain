# Scheduled /correct pass: design

Status: proposal, not built. Bead mk-ubr9o covers the commands; a build bead is filed from this document if approved.

## Goal

Turn repeated operator corrections into barriers (a test, a hook, a lint rule, a
changed default) instead of notes that agents may or may not read. `/correct`
does this for one repo on demand. This design runs it on a schedule over the
sources where repeats are already recorded.

## Inputs

1. Papercut log (`papercut -m ... "..."` entries): friction an agent hit.
2. Feedback memories (auto-memory entries of type `feedback`): corrections mk gave.
3. Recent PR review comments that asked for the same change twice.

A class is a "repeat" only when at least three independent entries (distinct
threads or days) describe the same mistake. One-off entries are left alone.

## Pass

1. Cluster entries into candidate classes (cheap model, read-only).
2. For each class above the threshold, pick the highest barrier level that works,
   in order: structural test or type, pre-commit/pre-push hook, lint rule,
   script default, router or skill text, memory note (last resort).
3. Prove the barrier: it must fail on a reproduction of the mistake and pass on the fix.
4. Write the barrier on a work branch and open a PR. One class per PR. The PR body
   names the entries, the barrier level chosen and why a higher level was not possible.

## Limits (design choices)

- Opens PRs only; never merges, never edits settings, hooks installed on the host
  or instruction files in place. Barriers that are themselves instruction files,
  hooks, settings or CI go to the instruction-file steward as a proposal, not a PR.
- At most two PRs per run, one run per week, one suite per repo, niced and capped.
- A class whose barrier PR was closed unmerged is not retried for 30 days.
- Reads memories but never writes them; deleting a note once its barrier merges is a
  separate human-approved step.
- Cost: clustering on a small model, barrier authoring on the execution seat,
  independent cross-lab review of every PR before it is offered.

## Open questions for mk

- Which repos start in scope (suggest Clavain only).
- Whether memory-derived classes may name mk's wording in public repos (default: no,
  cite the bead only).
- Whether the pass runs under independently scheduled automation (suggested) or on demand.
