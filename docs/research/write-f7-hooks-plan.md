# F7 Hooks Plan -- Research Analysis

**Date:** 2026-02-14
**Scope:** Pre-implementation research for interlock F7 hooks plan

## Sources Analyzed

### Clavain Hook Patterns
- `hooks/session-start.sh` (169 lines) -- SessionStart pattern: read stdin JSON first, source lib.sh, extract session_id, persist to CLAUDE_ENV_FILE, inject additionalContext via JSON stdout
- `hooks/auto-compound.sh` (150 lines) -- Stop hook pattern: stop_hook_active guard, sentinel files for throttling and cross-hook dedup, weighted signal detection, jq fail-open guard
- `hooks/session-handoff.sh` (119 lines) -- Stop hook pattern: stop_hook_active guard, sentinel for once-per-session, signal detection, block decision output
- `hooks/clodex-audit.sh` (37 lines) -- PostToolUse pattern: read stdin, extract tool_input.file_path via jq, case-match on extension, fast exit for non-matching
- `hooks/auto-publish.sh` (146 lines) -- PostToolUse pattern: extract tool_input.command, sentinel with TTL for loop prevention
- `hooks/catalog-reminder.sh` (31 lines) -- PostToolUse pattern: extract file_path, case-match on path patterns, per-session sentinel
- `hooks/hooks.json` (75 lines) -- Declarative registration: SessionStart (async:true), PostToolUse (matcher, timeout:5-15), Stop (timeout:5), SessionEnd (async:true)
- `hooks/lib.sh` (100 lines) -- Shared utilities: 4 discovery functions (env var + find), escape_for_json helper
- `hooks/lib-gates.sh` (31 lines) -- Shim delegation pattern: source lib.sh, discover companion, source real or provide no-op stubs

### Companion Plugin Structures
- interphase: hooks/ dir with lib files only (no hooks.json -- libs are sourced by Clavain's shims)
- interpath: scripts/ dir with marker file, commands/, skills/ -- no hooks
- interwatch: scripts/ dir with marker file, commands/, skills/ -- no hooks
- None of the existing 5 companions have their own hooks.json -- interlock will be the first companion with independent hooks

### intermute API (Target)
- `POST /api/agents` -- register with {name, project, capabilities, metadata, status}, returns {agent_id, session_id, name, cursor}
- `GET /api/agents` -- list agents, supports ?project= filter
- `GET /api/reservations` -- list reservations, supports ?project= and ?agent= filters
- `POST /api/reservations` -- create with {agent_id, project, path_pattern, exclusive, reason, ttl_minutes}
- `DELETE /api/reservations/{id}` -- release reservation, requires {agent_id} in body

### PRD (F7 Acceptance Criteria)
- 8 acceptance criteria mapped to 5 tasks
- Key design constraints: join-flag gating, advisory-only PreToolUse, graceful degradation, script delegation, one-time connectivity loss warning

## Key Design Decisions

1. **Interlock is the first companion with independent hooks** -- all existing companions (interphase, interflux, interpath, interwatch, interline) either have no hooks or use library files sourced by Clavain's shims. Interlock needs its own hooks.json because its lifecycle is independent of Clavain's session-start (it gates on join-flag, not plugin discovery).

2. **Join-flag gating vs. plugin discovery** -- Clavain discovers companions via env var + find in plugin cache. Interlock hooks check `~/.config/clavain/intermute-joined` instead. This is because interlock being installed doesn't mean coordination is active -- the user must explicitly join via `/interlock:join`.

3. **Async SessionStart** -- Registration involves a network call to intermute. Setting `async: true` prevents blocking session startup if intermute is slow or down.

4. **PreToolUse timeout: 5s** -- Matches Clavain's PostToolUse timeout for lightweight checks. The check script does 1-2 curl calls (reservations list + optional agent name lookup).

5. **Stop timeout: 10s** -- Higher than Clavain's 5s because cleanup may need to release multiple reservations (one DELETE per reservation).

6. **Connectivity tracking via flag file** -- `/tmp/interlock-connected-${SESSION_ID}` is set on successful registration, removed on first unreachable detection. This gives the one-time warning behavior the PRD requires without persistent state.

7. **No CLAUDE_ENV_FILE in PreToolUse/Stop** -- Only SessionStart has access to CLAUDE_ENV_FILE. PreToolUse and Stop read INTERMUTE_AGENT_ID from the environment (which SessionStart exported).

## Risk Assessment

- **Low risk:** Bash scripts with jq -- well-understood, extensively tested pattern in Clavain
- **Medium risk:** Network calls to intermute in hooks -- mitigated by timeouts, async, and graceful degradation
- **Low risk:** Temp file management -- standard `/tmp/` patterns with cleanup in Stop hook and stale file sweep
