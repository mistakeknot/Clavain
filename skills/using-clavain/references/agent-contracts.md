# Agent Output Contracts

Every Clavain agent must include an Output Contract section in its .md file. The contract defines the structured header the agent outputs before its full analysis.

## Verdict Schema

Used by review agents (plan-reviewer, data-migration-expert, fd-* agents):

```
TYPE: verdict
STATUS: CLEAN | NEEDS_ATTENTION | BLOCKED | ERROR
MODEL: haiku | sonnet | opus | codex
TOKENS_SPENT: <estimated number>
FILES_CHANGED: []
FINDINGS_COUNT: <number>
SUMMARY: <one-line summary of findings>
DETAIL_PATH: .clavain/verdicts/<agent-name>.md
```

## Implementation Schema

Used by workflow agents (bug-reproduction-validator, pr-comment-resolver):

```
TYPE: implementation
STATUS: COMPLETE | PARTIAL | FAILED
MODEL: haiku | sonnet | opus | codex
TOKENS_SPENT: <estimated number>
FILES_CHANGED: [file1.go, file2.go]
FINDINGS_COUNT: 0
SUMMARY: <one-line summary of what was done>
DETAIL_PATH: .clavain/verdicts/<agent-name>.md
```

## STATUS Values

| Status | Meaning | Orchestrator Action |
|--------|---------|-------------------|
| CLEAN | No issues found | Log one-line summary, proceed |
| NEEDS_ATTENTION | Issues found, details in DETAIL_PATH | Read findings, decide action |
| BLOCKED | Cannot complete (missing deps, access) | Report blocker, skip |
| ERROR | Agent failed | Log error, retry or skip |
| COMPLETE | Implementation finished | Verify with tests |
| PARTIAL | Partial implementation | Check what's missing |
| FAILED | Implementation failed | Read detail for root cause |

## Convention

- Agents write full analysis to `DETAIL_PATH` (typically `.clavain/verdicts/<agent-name>.md`)
- The structured header is the ONLY part the orchestrator reads by default
- `DETAIL_PATH` is read only for `NEEDS_ATTENTION` or `FAILED` statuses
- `TOKENS_SPENT` is the agent's estimate — precise tracking is done by interstat
- Verdict files are git-ignored and cleaned at sprint start
