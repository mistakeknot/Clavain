# Oracle Mapped File Changes Analysis

**Date:** 2026-02-10  
**Sync Point:** `5c053e24965d9995ea81691acac60ecbc5f4eca3..HEAD`  
**Source:** `/root/projects/upstreams/oracle`

## Summary

3 mapped files changed since last Clavain sync:
1. **README.md** — New browser auto-reattach feature, updated session commands
2. **docs/browser-mode.md** — New delay/timeout options, recheck behavior docs
3. **docs/configuration.md** — New config options for parallel runs and auto-reattach

**Impact:** Upgrade recommendations for Clavain's oracle SKILL documentation and configuration examples.

---

## Changed Files

### 1. README.md

**Changes:**
- Added `oracle restart <id>` command to session replay examples (line 45)
- New section: "Browser auto-reattach (long Pro runs)" with 3-flag configuration
  - `--browser-auto-reattach-delay` — delay before first retry
  - `--browser-auto-reattach-interval` — retry frequency
  - `--browser-auto-reattach-timeout` — per-attempt budget
- Flags table updated with 3 new browser recheck/reuse/lock options
  - `--browser-recheck-delay`, `--browser-recheck-timeout`
  - `--browser-reuse-wait`
  - `--browser-profile-lock-timeout`

**Key Feature:** Auto-reattach lets Oracle keep polling a finished Pro response without manual session replay commands. Solves timeout issue where long GPT-5.x Pro responses exceed browser timeout but finish later.

---

### 2. docs/browser-mode.md

**Changes:**
- Updated `--browser-input-timeout` default: `30s` → `60s` (line 56)
- Added 5 new option descriptions:
  - `--browser-recheck-delay`, `--browser-recheck-timeout`: Retry capture after timeout
  - `--browser-reuse-wait`: Share Chrome profile across parallel runs
  - `--browser-profile-lock-timeout`: Serialize parallel runs on shared profile
  - `--browser-auto-reattach-*`: Periodic polling for long Pro responses
- Changed "reruns" → "restarts" terminology (session reuse via `oracle restart <id>`)
- Added context: "If an assistant response still times out... session stays running for reattach"

**Details:**
```
--browser-timeout, --browser-input-timeout: 1200s (20m) / 60s defaults (was 30s)
--browser-recheck-delay, --browser-recheck-timeout: after timeout, wait, revisit, retry capture
--browser-reuse-wait: wait for shared Chrome profile before launching
--browser-profile-lock-timeout: wait for manual-login profile lock, serialize parallel runs
--browser-auto-reattach-delay/interval/timeout: periodic polling for long Pro runs
```

---

### 3. docs/configuration.md

**Changes:**
- Added 6 new config fields to `~/.oracle/config.json` template (browser section):
  ```json
  assistantRecheckDelayMs: 0,        // recheck after timeout (0 = disabled)
  assistantRecheckTimeoutMs: 120000, // recheck attempt budget (2m)
  reuseChromeWaitMs: 10000,          // wait for shared profile (parallel runs)
  profileLockTimeoutMs: 300000,      // wait for manual-login lock (parallel runs, 5m)
  autoReattachDelayMs: 0,            // delay before periodic polling (0 = disabled)
  autoReattachIntervalMs: 0,         // polling frequency (0 = disabled)
  autoReattachTimeoutMs: 120000      // per-attempt budget (2m)
  ```

**Context:** Enables persistent session reuse and parallel Chrome profile sharing without command-line flags.

---

## Unmapped Files (No Changes)

These files had no changes since the sync point:
- skills/oracle/SKILL.md
- docs/debug/remote-chrome.md
- docs/gemini.md
- docs/linux.md
- docs/mcp.md
- docs/multimodel.md
- docs/openai-endpoints.md
- docs/openrouter.md
- docs/testing/mcp-smoke.md

---

## Integration Recommendations for Clavain

### Immediate (High Priority)
1. **Update `using-clavain/SKILL.md`** — Add references to auto-reattach and timeout options for long-running reviews
2. **Update example commands** in skills/oracle or documentation — showcase `--browser-auto-reattach-*` flags for Pro model runs
3. **Add note to configuration guide** — mention new `assistantRecheckDelayMs` and `autoReattachDelayMs` settings

### Optional (Low Priority)
- Document parallel run scenario (multiple agents using `--browser-reuse-wait`)
- Add default config template with new browser options
- Update session replay examples to use `oracle restart <id>` instead of older terminology

### Testing
- Verify long Pro runs with auto-reattach enabled
- Test parallel browser runs with profile locking
- Confirm `oracle restart <id>` compatibility with current workflows

---

## Diff Details (Raw)

### README.md
```diff
@@ -45,0 +46,1 @@
+npx -y @steipete/oracle restart <id>

@@ -100,0 +101,24 @@
+## Browser auto-reattach (long Pro runs)
+
+When browser runs time out (common with long GPT‑5.x Pro responses), Oracle can keep polling...
```

### docs/browser-mode.md
```diff
--browser-timeout, --browser-input-timeout: 1200s (20m)/30s defaults
+--browser-timeout, --browser-input-timeout: 1200s (20m)/60s defaults
+
+--browser-recheck-delay, --browser-recheck-timeout: after timeout, wait, revisit, retry
+--browser-reuse-wait: shared Chrome profile (parallel)
+--browser-profile-lock-timeout: serialize parallel runs
+--browser-auto-reattach-*: periodic polling for long Pro runs
```

### docs/configuration.md
```diff
+assistantRecheckDelayMs: 0
+assistantRecheckTimeoutMs: 120000
+reuseChromeWaitMs: 10000
+profileLockTimeoutMs: 300000
+autoReattachDelayMs: 0
+autoReattachIntervalMs: 0
+autoReattachTimeoutMs: 120000
```

---

## Related Clavain Issues

**See:** `/root/.claude/projects/-root-projects-Clavain/memory/MEMORY.md` — Oracle service deployed at `/root/mcp_agent_mail` (separate from upstream clone). Configuration updates may affect MCP server instances.

