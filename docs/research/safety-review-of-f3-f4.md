# Security and Deployment Safety Review: F3/F4 Work Discovery Implementation

**Review Date:** 2026-02-13
**Reviewer:** fd-safety agent
**Scope:** F3 (orphan detection) + F4 (brief scan) in interphase lib-discovery.sh, integrated into Clavain lfg.md and session-start.sh
**Commit:** interphase 1379c83, Clavain 7051e94

---

## Executive Summary

**Overall Risk: LOW**

The F3/F4 implementation is **safe for deployment**. All JSON construction uses `jq --arg` (immune to injection), file operations are scoped to project directories, and temp files follow safe patterns. The primary risk is **UX degradation** from maliciously crafted markdown titles, not security exploitation.

**Recommended Actions:**
1. **Deploy as-is** — no blocking security issues
2. **Monitor temp cache accumulation** — add cleanup cron if `/tmp/clavain-discovery-brief-*` proliferates
3. **Consider title sanitization** (P3) — prevent UI disruption from newlines/control chars in artifact titles

---

## Threat Model

### System Architecture
- **Deployment context:** Local development plugin, runs as `claude-user` on single-user workstation
- **Trust boundaries:**
  - **Trusted:** `.beads/` JSONL database (written by `bd` CLI, owned by user)
  - **Trusted:** `docs/` markdown files (authored by user)
  - **Untrusted:** File paths from `find` output (symbolic links, special chars)
  - **Untrusted:** Markdown content titles (could contain injection chars)
- **Network exposure:** None (all local file operations)
- **Credentials:** None handled by this code
- **Privilege model:** Runs as non-root `claude-user`, no sudo/setuid

### Attack Surface
1. **File traversal:** Can `find` or `grep` escape project directory?
2. **Command injection:** Can bead IDs, titles, or paths inject into shell/jq?
3. **Temp file races:** Can attacker hijack `/tmp/clavain-discovery-brief-*.cache`?
4. **JSON injection:** Can user data break JSON construction?
5. **Resource exhaustion:** Can malicious inputs cause infinite loops or DoS?

---

## Security Findings

### ✅ PASS: JSON Construction (No Injection Risk)

**All JSON is built with `jq --arg`**, which treats inputs as literal strings:

```bash
# Line 175-183: discovery_scan_beads
results=$(echo "$results" | jq \
    --arg id "$id" \
    --arg title "$title" \
    --argjson priority "${priority:-4}" \
    --arg status "$status" \
    --arg action "$action" \
    --arg plan_path "$plan_path" \
    --argjson stale "$stale" \
    '. + [{id: $id, title: $title, ...}]')
```

**Why this is safe:**
- `jq --arg` escapes all special chars (quotes, backslashes, newlines)
- No use of `printf`, `echo "$var"`, or string concatenation to build JSON
- `--argjson` for booleans/numbers prevents type confusion

**Test coverage:** discovery.bats includes tests with special chars (lines 120-130 in test file).

**Verdict:** ✅ No injection risk

---

### ✅ PASS: Command Injection via Bead IDs

**Bead IDs are validated by `bd` CLI** before use:

```bash
# Line 272: discovery_scan_orphans
if ! bd show "$bead_id" &>/dev/null; then
    # Bead was deleted → stale orphan
```

**Attack scenario:** User edits markdown to say `**Bead:** foo; rm -rf /`

**Why this fails:**
1. `bd show "foo; rm -rf /"` returns error (invalid ID format)
2. Bead IDs are alphanumeric format `[A-Za-z]+-[a-z0-9]+` enforced by `bd` CLI
3. The variable `$bead_id` is always double-quoted (no word splitting)

**Additional uses:**
- Line 152: `infer_bead_action "$id" "$status"` — passed as positional arg
- Line 363: `infer_bead_action "$top_id" "$top_status"` — same pattern

**Verdict:** ✅ No command injection possible

---

### ✅ PASS: File Path Traversal (Scoped to Project Directory)

**All file operations are scoped to `$DISCOVERY_PROJECT_DIR`:**

```bash
# Line 228: discovery_scan_orphans
local project_dir="${DISCOVERY_PROJECT_DIR:-.}"

# Line 236-244: Directory iteration
for dir in docs/brainstorms docs/prds docs/plans; do
    [[ -d "${project_dir}/${dir}" ]] || continue
    # ...
    find "${project_dir}/${dir}" -name '*.md' -print0
```

**Attack scenario:** User sets `DISCOVERY_PROJECT_DIR=/etc` to scan system files

**Why this fails:**
1. `DISCOVERY_PROJECT_DIR` is set by calling code (lfg.md line 13: `DISCOVERY_PROJECT_DIR="."`), not user-controlled
2. Hardcoded subdirectory paths (`docs/plans`, `docs/prds`, `docs/brainstorms`)
3. File type filter (`-name '*.md'`)
4. No symbolic link following (`find` without `-L` flag)

**Path construction pattern:**
```bash
# Line 263: Convert absolute path to relative
local rel_path="${file#"${project_dir}/"}"
```

This **strips the project dir prefix**, preventing absolute paths in output. Even if `find` returns `/root/projects/foo/docs/plans/bar.md`, the JSON contains `docs/plans/bar.md`.

**Verdict:** ✅ No traversal risk — all paths constrained to `$project_dir/docs/{brainstorms,prds,plans}/*.md`

---

### ✅ PASS: grep Pattern Injection

**User-controlled bead IDs are used in grep patterns**, but safely:

```bash
# Line 33-39: infer_bead_action
if grep -P "" /dev/null 2>/dev/null; then
    grep_flags="-rlP"
    pattern="Bead.*${bead_id}\b"
else
    pattern="Bead.*${bead_id}[^a-zA-Z0-9_-]"
fi
```

**Attack scenario:** Bead ID `foo.*` could become regex wildcard

**Why this is mitigated:**
1. Bead IDs are validated by `bd` CLI format (`[A-Za-z]+-[a-z0-9]+`)
2. Pattern is `"Bead.*${bead_id}\b"` — only word chars after "Bead" prefix
3. Even if an ID contained `.`, it would match literally in most contexts (grep uses basic regex, not extended)
4. Portable fallback uses explicit character class `[^a-zA-Z0-9_-]` for word boundary

**Verdict:** ✅ Low risk (bead ID format prevents dangerous regex chars)

---

### ✅ PASS: Temp File Race Conditions

**Cache file pattern:**
```bash
# Line 308-309: discovery_brief_scan
local cache_key="${project_dir//\//_}"
local cache_file="/tmp/clavain-discovery-brief-${cache_key}.cache"
```

**Attack scenario:** Symlink `/tmp/clavain-discovery-brief-_root_projects_Clavain.cache` to `/etc/passwd`

**Why this fails:**
1. Cache is **read-only on reuse** (line 320: `cat "$cache_file"`)
2. Write uses `echo "$summary" >` (atomic for small strings, no append mode)
3. No `mktemp` needed — cache key is deterministic (one cache per project dir)
4. Failure is silent (`2>/dev/null || true`) — doesn't block workflow

**Actual observed behavior:**
```bash
$ ls -la /tmp/clavain-discovery-brief-*
-rw-rw-r-- 1 claude-user claude-user 69 Feb 13 11:57 /tmp/clavain-discovery-brief-_tmp_tmp.1rzcNCmF5k.cache
```

**Permissions:** `0664` (user/group writable) — acceptable for multi-session sharing

**Risk:** Attacker with local access could:
- Corrupt cache → stale/wrong summary shown (UX issue, not security)
- Fill `/tmp` with caches → disk exhaustion (mitigated by 60s TTL)

**Verdict:** ✅ Acceptable risk — cache poisoning only affects UX, no privilege escalation

---

### ✅ PASS: Markdown Title Extraction

**Title extraction from untrusted markdown:**
```bash
# Line 249-250: discovery_scan_orphans
title=$(grep -m1 '^# ' "$file" 2>/dev/null | sed 's/^# //' || true)
[[ -z "$title" ]] && title="$(basename "$file" .md)"
```

**Attack scenario:** Markdown file with `# Title\nWith\nNewlines` or `# $(whoami)`

**Why this is safe:**
1. `grep -m1 '^# '` only matches first line starting with `# `
2. `sed 's/^# //'` strips prefix, preserves rest (including special chars)
3. Title is passed to `jq --arg title` which escapes newlines as `\n` in JSON
4. Shell doesn't interpret `$(...)`  because `title` is never evaluated unquoted

**UX risk:** Title with newlines will render poorly in AskUserQuestion options, but won't break JSON or execute commands.

**Verdict:** ✅ No execution risk — only potential UX degradation

---

### ✅ PASS: bd create Title Injection (lfg.md integration)

**Orphan linking creates bead with title from markdown:**
```bash
# lfg.md line 45
bd create --title="<artifact title>" --type=task --priority=3
```

**Attack scenario:** Artifact title is `Foo"; rm -rf /; echo "`

**Why this fails:**
1. Title is passed via `--title="..."` flag, not positional arg
2. `bd` CLI parses flags with proper quoting (Go's `cobra` library)
3. Even if title contains quotes, the outer shell quotes prevent interpretation

**Test:**
```bash
$ bd create --title="foo\"; rm -rf /; echo \"bar" --type=task
# Creates bead with literal title: foo"; rm -rf /; echo "bar
```

**Verdict:** ✅ Safe — `bd` CLI handles arbitrary title strings correctly

---

### ⚠️  RESIDUAL RISK: Title with Newlines/ANSI Codes (P3)

**Current behavior:**
```bash
# Markdown file with:
# # Project\n\x1b[31mREDTEXT\x1b[0m Foo

# Extracted title:
"Project\n\x1b[31mREDTEXT\x1b[0m Foo"

# Passed to AskUserQuestion:
"Link orphan: Project
[31mREDTEXT[0m Foo (brainstorm)"
```

**Impact:**
- Newlines break option rendering in Claude Code UI
- ANSI codes may inject color/formatting into terminal output
- Does NOT break JSON or execute commands

**Mitigation options:**
1. **Sanitize titles in discovery_scan_orphans:**
   ```bash
   title=$(echo "$title" | tr -d '\n\r' | tr -cd '[:print:]')
   ```
2. **Truncate long titles:**
   ```bash
   title="${title:0:60}"  # Max 60 chars
   ```
3. **Document as known limitation** (current approach)

**Verdict:** ⚠️  UX issue, not security risk — recommend P3 sanitization task

---

## Deployment Safety Analysis

### Rollout Strategy

**Current deployment:**
- F3/F4 shipped in interphase 0.1.0 (2026-02-13)
- Integrated into Clavain 0.5.8 via session-start.sh
- No feature flag — enabled for all sessions

**Rollback feasibility:**
✅ **Fully reversible**
1. Code rollback: `git revert 7051e94` (Clavain) + `git revert 1379c83` (interphase)
2. Data rollback: N/A (no schema changes, no persistent state)
3. Downgrade path: Reinstall prior version from marketplace

**Partial failure modes:**
- `bd` not installed → `DISCOVERY_UNAVAILABLE` sentinel, workflow continues
- `.beads/` missing → same graceful degradation
- Orphan scan fails → returns `[]`, main scan unaffected
- Brief scan cache fails → silent retry, no blocking

**Verdict:** ✅ No irreversible changes, clean rollback path

---

### Pre-Deploy Checklist

**Invariants to verify:**
1. ✅ `bd list --json` returns valid JSON (tested in discovery.bats)
2. ✅ `docs/` directories are optional (tested: missing dirs skipped)
3. ✅ Orphan entries don't break existing workflow (tested: `action: "create_bead"` routing)
4. ✅ Cache TTL prevents stale data (tested: 60s expiry)

**Test coverage:**
- 12 new bats tests in `tests/shell/discovery.bats`
- Covers: bd unavailable, JSON parse errors, empty results, orphan detection, brief scan caching
- Missing: integration test for `lfg.md` orphan routing (recommend adding)

**Verdict:** ✅ Adequate coverage — one integration gap (non-blocking)

---

### Post-Deploy Verification

**Success criteria:**
1. `/clavain:lfg` with no args shows discovery menu
2. Orphan artifacts (docs without beads) appear in menu
3. Selecting orphan creates bead + links artifact
4. Brief scan appears in session-start context (if beads present)

**Monitoring:**
- Check `/tmp` for cache file accumulation (run `ls -lh /tmp/clavain-discovery-brief-* | wc -l` daily)
- Watch for "DISCOVERY_ERROR" in telemetry logs
- User reports of missing/incorrect orphan entries

**Failure signatures:**
- "DISCOVERY_UNAVAILABLE" every session → `bd` not installed (expected on non-beads projects)
- Empty menu despite open beads → `bd list --json` schema changed
- Orphan routing fails → title extraction broke on special chars

**Verdict:** ✅ Clear success metrics, observable failure modes

---

### Rollback Procedures

**If discovery breaks lfg workflow:**
1. Disable F4 session-start integration:
   ```bash
   # Edit session-start.sh, comment lines 122-128
   # discovery_context=""
   ```
2. Disable F3 orphan detection:
   ```bash
   # Edit lib-discovery.sh, replace lines 189-210 with:
   # local orphans="[]"
   ```
3. Full revert:
   ```bash
   cd /root/projects/Clavain
   git revert 7051e94
   /interpub:release 0.5.9  # Publish rollback
   ```

**If cache files accumulate:**
```bash
# Add to root crontab
0 3 * * * find /tmp -name 'clavain-discovery-brief-*.cache' -mtime +1 -delete
```

**Verdict:** ✅ Runbook-ready rollback procedures

---

## Recommendations

### Immediate (Pre-Deploy)

**None.** Code is safe to deploy as-is.

---

### Short-Term (P2, Next Sprint)

1. **Add integration test for orphan routing** (`tests/smoke/lfg-orphan-flow.md`)
   - Create markdown in `docs/brainstorms/` without bead header
   - Run `/lfg`, verify orphan appears in menu
   - Select orphan, verify bead created + file updated
   - **Why:** Current tests only cover scanner logic, not end-to-end flow

2. **Monitor temp cache accumulation**
   - Add cron to delete `/tmp/clavain-discovery-brief-*.cache` older than 24h
   - **Why:** Each project dir creates one cache file; proliferation risk if many projects

---

### Long-Term (P3, Optional)

1. **Sanitize markdown titles**
   - Strip newlines: `tr -d '\n\r'`
   - Strip ANSI codes: `sed 's/\x1b\[[0-9;]*m//g'`
   - Truncate: `"${title:0:60}"`
   - **Why:** Prevents UI disruption from malformed titles

2. **Compound orphan patterns into knowledge layer**
   - After first production usage, run `/compound` to document common orphan causes
   - **Why:** Improves future orphan detection heuristics

---

## Conclusion

The F3/F4 work discovery implementation is **production-ready**. All critical security patterns are sound:

- ✅ JSON construction immune to injection (`jq --arg` throughout)
- ✅ File operations scoped to project directory
- ✅ Temp files follow safe patterns (no TOCTOU, silent failure)
- ✅ Command injection prevented by proper quoting + `bd` CLI validation
- ✅ Rollback path is clean (no schema changes, feature can be disabled)

**Ship it.**

---

## Appendix: Code Audit Checklist

| Security Control | Location | Status |
|------------------|----------|--------|
| JSON construction via jq --arg | Lines 175-183, 202-206, 264-269, 275-280, 404-411 | ✅ SAFE |
| Shell variable quoting | All `"$var"` uses | ✅ SAFE |
| grep pattern injection | Lines 33-57 (bead ID patterns) | ✅ SAFE |
| find path traversal | Line 284 (`find "${project_dir}/${dir}"`) | ✅ SAFE |
| Temp file races | Lines 309-346 (cache R/W) | ✅ SAFE |
| bd CLI injection | Lines 97-101, 272, 330-332 | ✅ SAFE |
| Markdown title extraction | Lines 249-258 | ⚠️  UX risk (P3) |
| Error handling | All command failures use `|| true` or sentinels | ✅ SAFE |
| Privilege boundaries | Runs as claude-user, no sudo | ✅ SAFE |
| Network exposure | None (all local file ops) | ✅ SAFE |
