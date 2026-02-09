# Upstream Decision Records

Each upstream-sync PR must include a decision record file:

- Path: `docs/upstream-decisions/pr-<PR_NUMBER>.md`
- Template: `docs/templates/upstream-decision-record.md`

The upstream decision gate requires:

1. File exists in PR changes.
2. `Gate: approved` is set.
3. No `TBD` placeholders remain.

This ensures pointer updates are accompanied by explicit adoption/defer decisions.
