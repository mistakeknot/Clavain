# Research: F10 Git Pre-Commit Hook Generator Plan

**Date:** 2026-02-14
**Scope:** Implementation plan for interlock companion's git pre-commit hook generator (F10)
**Bead:** Clavain-ixyn

---

## Context Gathered

### 1. PRD Acceptance Criteria (F10)

From `docs/prds/2026-02-14-interlock-multi-agent-coordination.md`, F10 specifies:

- `interlock-install-hooks` script generates `.git/hooks/pre-commit`
- Hook extracts changed files from `git diff --cached --name-only`
- Hook checks each file against intermute's conflict detection API
- Hook aborts commit with clear, actionable error message
- Hook passes if no intermute agent is registered (graceful degradation)
- Hook skippable with `--no-verify` (escape hatch documented)

Error message format from PRD:
```
ERROR: Cannot commit. Reserved files detected:
  - src/router.go (reserved by claude-tmux-2: "auth refactor", expires in 8m)
Resolve: (1) /interlock:request-release claude-tmux-2, (2) wait 8m, (3) git commit --no-verify (risk: overwrite)
```

### 2. intermute API Analysis

**Reservations endpoint:** `GET /api/reservations?project=X` returns all active reservations for a project.

Response structure (from `internal/http/handlers_reservations.go`):
```json
{
  "reservations": [
    {
      "id": "uuid",
      "agent_id": "uuid",
      "project": "myproject",
      "path_pattern": "src/*.go",
      "exclusive": true,
      "reason": "auth refactor",
      "created_at": "2026-02-14T12:00:00Z",
      "expires_at": "2026-02-14T12:30:00Z",
      "released_at": null,
      "is_active": true
    }
  ]
}
```

**Agent lookup:** `GET /api/agents?project=X` returns agents with `agent_id` and `name` fields.

**No `GET /api/reservations/check` endpoint exists yet** (that's F4's atomic reserve). The hook must fetch all active reservations and match client-side. This is the same approach documented in the F6 research: "If intermute doesn't have the `GET /api/reservations/check` endpoint (returns 404), the `check_conflicts` tool falls back to `GET /api/reservations?project=X` and filters client-side by pattern match."

### 3. Glob Pattern Matching

intermute uses `filepath.Match`-compatible glob patterns in `path_pattern` fields (`internal/glob/overlap.go`). The pre-commit hook needs to check whether a changed file matches any active reservation's `path_pattern` where the reservation's `agent_id` differs from the committing agent.

For the bash hook, Go's `filepath.Match` semantics map to bash's `[[ file == pattern ]]` extglob or `case` statement for simple patterns. However, intermute supports `*`, `?`, and `[...]` character classes. The safest approach is to use `case "$file" in $pattern)` which uses the same glob semantics.

**Key insight:** The hook should match exact file paths against reservation patterns, not overlap between patterns. A reservation pattern like `src/*.go` should match the committed file `src/router.go`.

### 4. Connection Strategy

From the F8 research (`write-f8-commands-plan.md`):
```bash
INTERMUTE_SOCKET="${INTERMUTE_SOCKET:-/var/run/intermute.sock}"
INTERMUTE_URL="${INTERMUTE_URL:-http://localhost:7890}"

# Try socket first, fall back to TCP
if [ -S "$INTERMUTE_SOCKET" ]; then
    CURL_ARGS="--unix-socket $INTERMUTE_SOCKET http://localhost"
else
    CURL_ARGS="$INTERMUTE_URL"
fi
```

The hook uses `curl` to query intermute. This is the standard pattern across all interlock scripts.

### 5. Installer Design Decisions

**Existing pre-commit hook handling:**

Three scenarios when `.git/hooks/pre-commit` exists:
1. **No file** -- create new hook
2. **File exists, is interlock** -- replace it (idempotent)
3. **File exists, is NOT interlock** -- wrap existing hook by renaming to `.pre-commit.orig` and creating a new hook that calls both

Detection: use a marker comment `# INTERLOCK_HOOK_MARKER` in the generated hook. If the marker is present, it's ours; replace. If absent, it's a third-party hook; wrap.

**Wrapper approach:** The safest option when an existing hook exists is to:
1. Rename `.git/hooks/pre-commit` to `.git/hooks/pre-commit.interlock-backup`
2. Create new `.git/hooks/pre-commit` that runs the backup first (abort if it fails), then runs interlock checks

This preserves any existing hooks (husky, lint-staged, etc.) while adding interlock enforcement.

### 6. Batch Conflict Check Design

Instead of N individual API calls (one per changed file), the hook:
1. Calls `GET /api/reservations?project=<PROJECT>` once to get all active reservations
2. For each changed file, tests locally against each reservation's `path_pattern`
3. Filters out reservations held by the current agent (`INTERMUTE_AGENT_ID`)
4. Collects all conflicts, then reports them all at once

This is O(files * reservations) locally but only 1 HTTP request. For the expected scale (tens of files, single-digit reservations), this is optimal.

**Agent name resolution:** The reservations API returns `agent_id` but not agent names. To produce human-readable error messages, the hook also calls `GET /api/agents?project=<PROJECT>` and builds an agent_id-to-name lookup table. This is 2 HTTP requests total.

### 7. Graceful Degradation Behavior

The hook must pass (exit 0) in these cases:
- `INTERMUTE_AGENT_ID` is not set (agent not registered, coordination not active)
- intermute is unreachable (curl fails with connection error)
- API returns non-200 status (server error)
- No active reservations for the project (empty list)
- All reservations belong to the current agent (no conflicts)

Only exit 1 (block commit) when there are confirmed conflicts with OTHER agents' reservations.

### 8. Time Formatting for Error Messages

The PRD shows "expires in 8m" format. Given `expires_at` is ISO 8601, the hook needs to compute relative time. In bash:
```bash
expires_epoch=$(date -d "$expires_at" +%s 2>/dev/null)
now_epoch=$(date +%s)
remaining=$(( (expires_epoch - now_epoch) / 60 ))
if [ "$remaining" -le 0 ]; then
    time_str="expired"
else
    time_str="${remaining}m"
fi
```

### 9. File Structure (target repo)

Both files live in the interlock companion plugin:

```
/root/projects/interlock/
  scripts/
    interlock-install-hooks     # Installer script (Task 1)
    interlock-precommit-hook    # Template for the generated hook (Task 2)
  tests/
    structural/
      test_git_hooks.py         # Structural tests (Task 3)
```

The installer copies the template into `.git/hooks/pre-commit` and makes it executable. Keeping the template as a separate file makes it testable (shellcheck, syntax check) and versionable independent of the installer logic.

Alternative: the installer generates the hook inline (like how `husky` does it). This is simpler but harder to test. Given the hook is ~80 lines with significant logic, a separate template file is better.

**Decision:** Use a template file approach. The installer reads the template from the plugin directory and writes it to `.git/hooks/pre-commit`.

### 10. Plugin Root Discovery in the Hook

The generated hook runs from the git repo directory, NOT from the plugin directory. It needs to find the intermute connection config. Options:

1. **Hardcode connection defaults in the hook** -- simplest. The hook has `INTERMUTE_SOCKET=/var/run/intermute.sock` and `INTERMUTE_URL=http://localhost:7890` baked in. Override via env vars.
2. **Read from a config file** -- over-engineering for this use case.

**Decision:** Hardcode defaults. The env vars `INTERMUTE_SOCKET`, `INTERMUTE_URL`, `INTERMUTE_AGENT_ID`, and `INTERMUTE_PROJECT` provide overrides. The hook is self-contained bash with no dependencies beyond `curl` and `jq`.

### 11. Project Slug Detection

The hook needs to know which project to query reservations for. The standard pattern across the ecosystem is:
```bash
PROJECT=$(basename "$(git rev-parse --show-toplevel)")
```

This can be overridden via `INTERMUTE_PROJECT` env var (set by the SessionStart hook via `CLAUDE_ENV_FILE`).

### 12. Security Considerations

- The hook runs as the same user who runs `git commit` -- no privilege escalation
- `curl --unix-socket` is safe (kernel enforces socket permissions, mode 0660)
- `jq` parsing is safe against injection (no eval of API responses)
- The `--no-verify` escape hatch is a standard git feature, not something we add
- The hook MUST NOT store secrets or API keys -- intermute uses socket-level auth or project-scoped API keys already set in the environment

### 13. Test Strategy

- **Structural tests (pytest):** Script exists, is executable, contains expected patterns (marker, curl, error format)
- **Shellcheck:** Both scripts pass `shellcheck` with no warnings
- **Syntax check:** `bash -n scripts/interlock-install-hooks` and `bash -n scripts/interlock-precommit-hook` pass
- **No integration tests in this feature** -- would require a running intermute instance + git repo setup. Integration testing deferred to smoke tests.

## Key Findings

1. **2 HTTP requests per commit** -- one for reservations, one for agents (name lookup). Both cached in variables, matched locally. This is the optimal approach given no `GET /api/reservations/check` endpoint exists yet.

2. **Template file approach** for the hook -- the installer copies a template, not generates inline. The template is self-contained bash with hardcoded connection defaults and env var overrides.

3. **Wrapper pattern for existing hooks** -- if `.git/hooks/pre-commit` already exists and is not ours (no marker comment), rename to backup and chain. This preserves husky/lint-staged/etc.

4. **Graceful degradation is permissive** -- the hook only blocks when there is a confirmed conflict with another agent's reservation. All error states (no agent registered, intermute down, API errors) result in pass-through.

5. **3 tasks is the right scope:**
   - Task 1: Installer script (`interlock-install-hooks`)
   - Task 2: Pre-commit hook template (`interlock-precommit-hook`)
   - Task 3: Structural tests for both scripts
