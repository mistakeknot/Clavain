# mcp-agent-mail Changes Since Last Sync

**Last Sync Commit:** 2026-02-05 20:34:32 UTC-5  
**Current HEAD:** 061435c (2026-02-10 11:06:00 UTC-6)  
**Commits Since Last Sync:** 21  
**Changed Mapped Files:** 1 (codex.mcp.json)

## Changed Files Summary

### Critical: codex.mcp.json
**Status:** ✅ REQUIRES IMMEDIATE ATTENTION  
**Change:** Bearer token hardcoded in config file

**Before:**
```json
"headers": {        "Authorization": "Bearer YOUR_BEARER_TOKEN"}
```

**After:**
```json
"headers": {        "Authorization": "Bearer dc5029ac32a9f350508a565af683205cf99f25c896b07c07bc53a9517877ce8c"}
```

**Risk Assessment:**
- **SECURITY CRITICAL:** Bare authentication token exposed in version control
- Token format suggests SHA256 or similar hash-based token
- If this is a real secret, it's now compromised in git history
- Should never be committed — belongs in environment variables or secrets management

**Recommended Action:**
1. Rotate the token immediately in mcp-agent-mail service
2. Remove from git history (rebase/force-push needed if already on remote)
3. Update .gitignore to exclude codex.mcp.json if it's environment-specific
4. Update integration docs to use `$MCP_AGENT_MAIL_TOKEN` or similar env var pattern
5. Do NOT sync this change to Clavain production deployment

## Unmapped Files (Not in Clavain Sync Scope)

The following mapped files had **no changes**:
- SKILL.md
- README.md
- scripts/integrate_codex_cli.sh
- scripts/hooks/check_inbox.sh
- scripts/hooks/codex_notify.sh
- docs/GUIDE_TO_OPTIMAL_MCP_SERVER_DESIGN.md
- docs/observability.md
- docs/operations_alignment_checklist.md
- docs/adr/* (all ADRs)
- docs/deployment_samples/* (all samples)

## Commit Log (21 Total)

1. 061435c - fix(cli): default to serve-http when no subcommand given
2. 2dec7d0 - chore(beads): close bd-1v5 — actionable community features implemented
3. 8682140 - chore(beads): close bd-p6n after ruff quality gate completion
4. 130e3cd - style: apply ruff auto-fixes (collapsed nested if, unused var, import sort)
5. 3e7a88b - chore(beads): close bd-14z after implementation
6. b1c2051 - feat(reservations): add virtual namespace support for tool/resource reservations (bd-14z)
7. 5069b3e - chore(beads): sync issue tracker state
8. f248e64 - chore(beads): close bd-1ia after implementation
9. ee53048 - feat(summarization): add on-demand project-wide message summarization (bd-1ia)
10. 2acd89a - chore(beads): mark bd-1ia (on-demand message summarization) as in_progress
11. e6fad41 - chore(beads): close bd-26w after implementation
12. b4ad9fc - feat(messaging): add broadcast + topic threads for all-agent visibility (bd-26w)
13. e9424be - fix(identity): race condition and redundant DB lookups in window identity
14. 0db6b1b - chore(beads): close bd-1tz after implementation
15. 32afeab - feat(identity): add persistent window-based agent identity system (bd-1tz)
16. a188fdd - chore(beads): track tool reservation namespace and Discord community features
17. 542995c - fix(http): return 404 for OAuth well-known endpoints when OAuth disabled
18. ec318e1 - chore(beads): refine all 3 feature beads with deps, logging, and migration
19. e3dbc6b - chore(beads): sync issue tracker
20. 1764d2d - chore(beads): sync issue tracker
21. (final commit before 999224409f...)

## Impact on Clavain Sync

### ⚠️ BLOCKING SYNC ISSUE

**Do not merge codex.mcp.json changes into Clavain deployment without:**

1. **Token Rotation**
   - The exposed token in upstream commit must be rotated
   - Request mcp-agent-mail maintainer to rebase/force-push if this was accidental

2. **Secret Management Pattern**
   - Update upstream to use environment variable substitution in codex.mcp.json
   - Pattern: `"Authorization": "Bearer ${MCP_AGENT_MAIL_TOKEN}"`
   - Document in integration guide how to set env var at runtime

3. **Clavain Deployment**
   - If syncing this file, ensure deployment injects actual token via:
     - Systemd EnvironmentFile
     - Docker secrets mount
     - .env file (gitignored)
   - Never commit real tokens to Clavain repo

### Non-Blocking Changes

- 3 feature commits (reservations, summarization, broadcast+threads)
- 1 identity system implementation
- 3 bug fixes (CLI default, identity race condition, OAuth endpoint)
- Multiple quality/style improvements via ruff auto-fixes
- All in internal services — no mapped files changed except codex.mcp.json

## Recommendation

**HOLD sync of mcp-agent-mail until upstream codex.mcp.json is fixed.**

Wait for upstream to:
1. Rotate the exposed token
2. Rebase/amend the commit to use env var pattern
3. Update integration docs

Then re-run sync diff to verify clean state before pulling changes into Clavain.

**Current Clavain deployment is safe** — no token secrets have been pushed yet.
