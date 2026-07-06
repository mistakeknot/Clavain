# Upstream Sync (compact)

Keep Clavain docs and skills aligned with upstream tooling changes.

## Core Workflow

1. Check open `upstream-sync` issues (preferred path).
2. Read each checklist and mapped affected skills.
3. Inspect upstream release/changelog/README deltas.
4. Apply minimal updates to affected Clavain skills/docs.
5. Refresh baseline with `scripts/upstream-check.sh --update`.
6. Commit and close/update the issue.

## Automation Model

- Daily workflow runs upstream checks and opens/comments on sync issues.
- Session start warns when `docs/upstream-versions.json` is stale (>7 days).
- `/clavain:upstream-sync` is the manual remediation entrypoint.

## Quick Commands

```bash
gh issue list --label upstream-sync --state open
bash scripts/upstream-check.sh --json
bash scripts/upstream-check.sh --update
```

## Merge Gate Rules

- Add `docs/upstream-decisions/pr-<PR_NUMBER>.md`.
- Include `Gate: approved` and remove all `TBD`.
- Record per-upstream choice: `adopt-now`, `defer`, or `ignore`.

---

*For full upstream mapping, issue flow details, and impact/dependency notes, read SKILL.md.*
