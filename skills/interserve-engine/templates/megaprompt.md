## Goal
{{GOAL}}

## Phase 1: Explore
Before making any changes, investigate the code area:
- Read {{EXPLORE_TARGETS}}
- Identify the exact file(s) and line(s) that need to change
- Check for existing tests covering this area
- Note the package name, imports, and any callers of modified code
- Print a brief exploration summary before proceeding

## Phase 2: Implement
Make the change:
{{IMPLEMENT}}

## Phase 3: Verify
After implementing, run ALL of these and report results:
1. Build: `{{BUILD_CMD}}`
2. Tests: `{{TEST_CMD}}`
3. Diff: `git diff --stat` (ensure only expected files changed)
4. If build or tests fail: fix and re-verify (up to 2 self-retries)

**CRITICAL -- Scope test commands**: Use `-run TestPattern`, `-short`, `-timeout=60s`. NEVER use broad `go test ./... -v`.

## Final Report
```
EXPLORATION: [1-2 sentence summary]
CHANGES: [files modified/created]
BUILD: PASS | FAIL
TESTS: PASS | FAIL [N passed, M failed]
VERDICT: CLEAN | NEEDS_ATTENTION [reason]
```

## Constraints
- Only modify files directly related to the goal
- Do not reformat, realign, or adjust whitespace in code you didn't functionally change
- Do not add comments, docstrings, or type annotations to unchanged code
- Do not refactor or rename anything not directly related to the task
- Keep the change minimal -- prefer 5 clean lines over 50 "proper" lines
- Do NOT commit or push any changes
- If GOCACHE permission errors occur, use: GOCACHE=/tmp/go-build-cache
