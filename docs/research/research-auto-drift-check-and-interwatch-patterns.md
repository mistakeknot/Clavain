# Auto-Drift-Check Hook Research — Patterns from auto-compound.sh and interwatch

**Research Date:** 2026-02-14  
**Scope:** Extract patterns from `auto-compound.sh` Stop hook and interwatch drift detection system to inform a new `auto-drift-check` Stop hook that monitors doc freshness automatically.

---

## 1. Auto-Compound Hook Analysis (hooks/auto-compound.sh)

### 1.1 Core Architecture

**Hook Type:** Stop  
**Event:** Fires after each conversation turn (when Claude finishes responding)  
**Purpose:** Detect compoundable problem-solving signals and auto-trigger `/compound` command  
**Lines:** 151 total

### 1.2 Signal Detection Pattern

Auto-compound uses **weighted signal scoring**:

```bash
# Weighted signal detection
SIGNALS=""
WEIGHT=0

# Example signals:
# 1. Git commit detected (Claude ran git commit) — weight 1
if echo "$RECENT" | grep -q '"git commit\|"git add.*&&.*git commit'; then
    SIGNALS="${SIGNALS}commit,"
    WEIGHT=$((WEIGHT + 1))
fi

# 2. Debugging resolution phrases — weight 2 (strong signal)
if echo "$RECENT" | grep -iq '"that worked\|"it'\''s fixed\|"working now\|"problem solved'; then
    SIGNALS="${SIGNALS}resolution,"
    WEIGHT=$((WEIGHT + 2))
fi
```

**Key pattern:** Each signal has a weight (1-2), and the total must reach threshold (3) to trigger. This prevents firing on trivial commits alone (weight 1), but fires on commit + resolution (weight 3).

**All 6 signals:**
1. Git commit — weight 1
2. Debugging resolution ("that worked", "it's fixed") — weight 2
3. Investigation language ("root cause", "the issue was") — weight 2
4. Bead closed — weight 1
5. Insight block (★ Insight marker) — weight 1
6. Build/test recovery (failure → pass) — weight 2

**Threshold:** `WEIGHT >= 3` to trigger

### 1.3 Sentinel and Throttle Mechanism

**Three-tier guard system:**

```bash
# 1. Stop hook re-entry guard (prevent infinite loop)
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_ACTIVE" == "true" ]]; then
    exit 0
fi

# 2. Cross-hook sentinel (one Stop hook per cycle)
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
touch "$STOP_SENTINEL"  # Write BEFORE analysis to minimize TOCTOU

# 3. Throttle — at most once per 5 minutes
THROTTLE_SENTINEL="/tmp/clavain-compound-last-${SESSION_ID}"
if [[ -f "$THROTTLE_SENTINEL" ]]; then
    THROTTLE_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || date +%s)
    THROTTLE_NOW=$(date +%s)
    if [[ $((THROTTLE_NOW - THROTTLE_MTIME)) -lt 300 ]]; then
        exit 0
    fi
fi
```

**Critical insight:** The cross-hook sentinel is written BEFORE transcript analysis (line 52), not after, to minimize time-of-check-to-time-of-use (TOCTOU) race conditions.

### 1.4 Block + Reason JSON Output

When signals exceed threshold, hook outputs JSON with `decision:"block"` + `reason:` prompt:

```bash
REASON="Auto-compound check: detected compoundable signals [${SIGNALS}] (weight ${WEIGHT}) in this turn. Evaluate whether the work just completed contains non-trivial problem-solving worth documenting. If YES (multiple investigation steps, non-obvious solution, or reusable insight): briefly tell the user what you are documenting (one sentence), then immediately run /clavain:compound using the Skill tool. If NO (trivial fix, routine commit, or already documented), say nothing and stop."

# Write throttle sentinel
touch "$THROTTLE_SENTINEL"

# Return block decision to inject the evaluation prompt
if command -v jq &>/dev/null; then
    jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'
else
    # Fallback: REASON contains only hardcoded strings, safe for interpolation
    cat <<ENDJSON
{
  "decision": "block",
  "reason": "${REASON}"
}
ENDJSON
fi
```

**Key pattern:** The `reason` field becomes a system prompt injection. Claude sees it and decides whether to execute `/compound`. This is NOT auto-execution — it's **auto-evaluation with manual gate**.

### 1.5 Per-Repo Opt-Out

```bash
# Guard: per-repo opt-out
if [[ -f ".claude/clavain.no-autocompound" ]]; then
    exit 0
fi
```

Allows projects to disable the hook without uninstalling the plugin.

### 1.6 Cleanup Pattern

```bash
# Clean up stale sentinels from previous sessions
find /tmp -maxdepth 1 -name 'clavain-stop-*' -mmin +60 -delete 2>/dev/null || true
```

Run at end of hook to prevent `/tmp` bloat.

---

## 2. Session-Handoff Hook Comparison (hooks/session-handoff.sh)

**Similarities to auto-compound:**
- Same sentinel pattern (`STOP_SENTINEL`, `HANDOFF_SENTINEL`)
- Same `stop_hook_active` guard
- Same block + reason JSON output
- Same cleanup pattern

**Differences:**
- Detects different signals (uncommitted changes, in-progress beads)
- No weighted scoring — binary decision (signals present or not)
- Longer reason prompt (4-step checklist, not 1-sentence)
- No throttle (once per session is enough)

**Sentinel coordination note:** Both hooks check the shared `STOP_SENTINEL` (lines 35-38 in auto-compound, lines 34-38 in session-handoff). This prevents cascade: if session-handoff writes handoff.md and commits, auto-compound won't fire on that commit signal because the sentinel is already set.

---

## 3. Hooks.json Registration

**File:** `/root/projects/Clavain/hooks/hooks.json`

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/auto-compound.sh",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-handoff.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Pattern:** Multiple Stop hooks in same array. They run sequentially. First hook to write `STOP_SENTINEL` blocks subsequent hooks via the shared sentinel check.

**Other hook events in Clavain:**
- `SessionStart` — session-start.sh (async)
- `PostToolUse` — clodex-audit.sh (Edit/Write/MultiEdit), auto-publish.sh (Bash), catalog-reminder.sh (Write)
- `SessionEnd` — dotfiles-sync.sh (async)

**No hooks in plugin.json:** `python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['hooks'])"` returns `[]`. All hooks are in `hooks/hooks.json`, not plugin.json manifest. This is intentional — hooks are implementation details, not API surface.

---

## 4. interwatch Discovery and Integration

### 4.1 Discovery Pattern (hooks/lib.sh)

```bash
# Discover the interwatch companion plugin root directory.
# Checks INTERWATCH_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_interwatch_plugin() {
    if [[ -n "${INTERWATCH_ROOT:-}" ]]; then
        echo "$INTERWATCH_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interwatch/*/scripts/interwatch.sh' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # interwatch.sh is at <root>/scripts/interwatch.sh, so strip two levels
        echo "$(dirname "$(dirname "$f")")"
        return 0
    fi
    echo ""
}
```

**Pattern:** Two-tier discovery:
1. Check env var `INTERWATCH_ROOT` (for dev/testing)
2. Find marker file in plugin cache (`scripts/interwatch.sh`)

**Marker file content:** `/root/projects/interwatch/scripts/interwatch.sh` is a 4-line stub:

```bash
#!/usr/bin/env bash
# Marker file for Clavain companion discovery.
# Presence of this file signals that interwatch is installed.
echo "interwatch marker"
```

It's not functional — it's just a discovery sentinel.

### 4.2 Session-Start Integration (hooks/session-start.sh)

```bash
# interwatch — doc freshness monitoring companion
interwatch_root=$(_discover_interwatch_plugin)
if [[ -n "$interwatch_root" ]]; then
    companions="${companions}\\n- **interwatch**: doc freshness monitoring"
fi
```

interwatch is discovered and reported in the SessionStart context injection, but **NOT automatically invoked**. It's purely informational.

---

## 5. interwatch CLI Usage Patterns

### 5.1 Commands (from using-clavain/SKILL.md)

| Purpose | Command |
|---------|---------|
| Check doc freshness | `/interwatch:watch` or `/interwatch:status` |
| Refresh a stale doc | `/interwatch:refresh` |

**Note:** These are Clavain command wrappers, not direct interwatch skill invocations. interwatch commands are NOT in `/root/projects/Clavain/commands/` — they must be in interwatch's own `commands/` directory.

**Confirmed:** No `interwatch-*.md` files in `/root/projects/Clavain/commands/` (checked via `ls`). The commands are registered by interwatch plugin itself.

### 5.2 Manual Invocation Only

From `docs/research/trace-integration-points.md`:

> **Issue:** interwatch is discovered and reported in session-start, but **no hook automatically runs interwatch checks** or triggers doc refreshes.

**Current state:**
- interwatch exists and can be manually invoked (`/interwatch:watch`)
- Watchables config is complete (roadmap, prd, vision, agents-md)
- Staleness thresholds are set (7-30 days)

**Missing:**
- No scheduled checks (e.g., on `/lfg` completion, on upstream-sync)
- No auto-refresh hook (e.g., when PRD is stale, auto-regenerate with interpath)

**Opportunity identified in trace doc:** Add PostToolUse hook that:
1. Runs `interwatch status` after major workflows (`lfg`, `upstream-sync`)
2. Reports staleness to user
3. Optionally auto-triggers interpath regeneration for stale product docs

**This is the gap that auto-drift-check would fill.**

---

## 6. Watchables Configuration (interwatch/config/watchables.yaml)

### 6.1 Schema

```yaml
watchables:
  - name: roadmap
    path: docs/roadmap.md
    generator: interpath:artifact-gen
    generator_args: { type: roadmap }
    signals:
      - type: bead_closed
        weight: 2
        description: "Closed bead may affect roadmap phasing"
      - type: version_bump
        weight: 3
        description: "Version bump likely means shipped work"
    staleness_days: 7
```

**4 watchables defined:**
1. **roadmap** — `docs/roadmap.md`, generator: `interpath:artifact-gen`, staleness: 7 days
2. **prd** — `docs/PRD.md`, generator: `interpath:artifact-gen`, staleness: 14 days
3. **vision** — `docs/vision.md`, generator: `interpath:artifact-gen`, staleness: 30 days
4. **agents-md** — `AGENTS.md`, generator: `interdoc:interdoc`, staleness: 14 days

### 6.2 Signal Types

**Deterministic signals** (Certain confidence):
- `version_bump` (weight 2-3)
- `component_count_changed` (weight 3)

**Probabilistic signals** (contribute to weighted score):
- `bead_closed` (weight 2)
- `bead_created` (weight 1)
- `file_renamed` (weight 3)
- `file_deleted` (weight 3)
- `file_created` (weight 2)
- `commits_since_update` (weight 1, threshold: 20)
- `brainstorm_created` (weight 1)
- `companion_extracted` (weight 2-3)
- `research_completed` (weight 1)

**Total unique signal types:** 11

---

## 7. interwatch Confidence Tiers (skills/doc-watch/phases/assess.md)

### 7.1 Tier Definitions

| Score | Staleness | Confidence | Color | Action |
|-------|-----------|------------|-------|--------|
| 0 | < threshold | **Green** — current | Green | None |
| 1-2 | < threshold | **Low** — minor drift | Blue | Report only |
| 3-5 | any | **Medium** — moderate drift | Yellow | Suggest refresh (ask user) |
| 6+ | any | **High** — significant drift | Orange | Auto-refresh + notify user |
| any | > threshold | **High** — stale | Orange | Auto-refresh + notify user |
| deterministic signal fired | any | **Certain** — version/count mismatch | Red | Auto-fix silently |

### 7.2 Deterministic vs Probabilistic

**Deterministic signals** produce **Certain** confidence when they fire:
- `version_bump` with mismatch detected (plugin.json version ≠ doc header version)
- `component_count_changed` with mismatch detected (actual count ≠ doc claim)

These are factual contradictions — the doc is objectively wrong.

**Probabilistic signals** contribute to weighted score but don't guarantee drift.

### 7.3 Scoring Model

```
drift_score = sum(signal_weight * signal_count for each signal)
```

**Example:**
- 3 beads closed (weight 2 each) = 6 points
- 1 version bump (weight 3) = 3 points
- 1 brainstorm created (weight 1) = 1 point
- **Total:** 10 points → **High confidence**

Plus staleness check: if `days_since_update > staleness_threshold`, confidence is at least **High**.

---

## 8. interwatch Detection Phase (skills/doc-watch/phases/detect.md)

### 8.1 Signal Evaluation Functions

**From `interwatch/hooks/lib-watch.sh`:**

```bash
# Get file modification time as epoch seconds
_watch_file_mtime() {
    local path="$1"
    stat -c %Y "$path" 2>/dev/null || stat -f %m "$path" 2>/dev/null || echo 0
}

# Count days since file was last modified
_watch_staleness_days() {
    local mtime now
    mtime=$(_watch_file_mtime "$1")
    now=$(date +%s)
    if [[ "$mtime" -gt 0 ]]; then
        echo $(( (now - mtime) / 86400 ))
    else
        echo 999
    fi
}

# Extract version from doc header (looks for "Version: X.Y.Z" in first 10 lines)
_watch_doc_version() {
    head -10 "$1" 2>/dev/null | grep -oP 'Version:\s*\K[\d.]+' || echo "unknown"
}

# Count git commits since a given epoch timestamp
_watch_commits_since() {
    local since="$1"
    git rev-list --count HEAD --after="$since" 2>/dev/null || echo 0
}

# List files changed (renamed/deleted/created) since a doc was last modified
_watch_file_changes() {
    local doc_path="$1"
    local mtime
    mtime=$(_watch_file_mtime "$doc_path")
    local commit
    commit=$(git log -1 --format=%H --until="@$mtime" 2>/dev/null || echo "")
    if [[ -n "$commit" ]]; then
        git diff --name-status "$commit"..HEAD -- skills/ commands/ agents/ hooks/ 2>/dev/null
    fi
}

# Count brainstorms newer than a given file
_watch_newer_brainstorms() {
    find docs/brainstorms/ -name "*.md" -newer "$1" 2>/dev/null | wc -l | tr -d ' '
}
```

**Key pattern:** All functions are prefixed `_watch_` to avoid namespace collisions when sourced into skills.

### 8.2 Signal Detection Examples

**version_bump:**

```bash
plugin_version=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")
doc_version=$(head -10 "$DOC_PATH" 2>/dev/null | grep -oP 'Version:\s*\K[\d.]+' || echo "unknown")
if [ "$plugin_version" != "$doc_version" ]; then echo "DRIFT"; fi
```

**component_count_changed:**

```bash
actual_skills=$(ls skills/*/SKILL.md 2>/dev/null | wc -l | tr -d ' ')
actual_commands=$(ls commands/*.md 2>/dev/null | wc -l | tr -d ' ')
# Compare against counts parsed from doc
```

**file_renamed / file_deleted / file_created:**

```bash
doc_mtime=$(stat -c %Y "$DOC_PATH" 2>/dev/null || echo 0)
doc_commit=$(git log -1 --format=%H --until="@$doc_mtime" 2>/dev/null || echo "HEAD~20")
git diff --name-status "$doc_commit"..HEAD -- skills/ commands/ agents/ 2>/dev/null
```

Output: `A file.md` (added), `D file.md` (deleted), `R old.md -> new.md` (renamed)

---

## 9. interwatch Refresh Phase (skills/doc-watch/phases/refresh.md)

### 9.1 Confidence-Based Actions

| Confidence | Action |
|-----------|--------|
| **Certain** | Invoke generator silently. Apply result. Record in history. |
| **High** | Invoke generator. Apply result. Tell user: "Refreshed [doc] — [reason]." |
| **Medium** | Show drift summary. Use AskUserQuestion: "Drift detected in [doc] (score: N). Refresh now?" |
| **Low** | Report only: "[doc] has minor drift (score: N). No action needed." |

### 9.2 Generator Invocation

**For product docs (interpath):**

```bash
# Example: refresh roadmap
claude plugin run interpath artifact-gen --type=roadmap --output=docs/roadmap.md
```

**For code docs (interdoc):**

```bash
# Example: refresh AGENTS.md
claude plugin run interdoc interdoc --output=AGENTS.md
```

**Pattern:** interwatch doesn't contain generator logic — it dispatches to companion plugins (interpath, interdoc) via the `generator` field in watchables.yaml.

### 9.3 State Tracking

Per-project state in `.interwatch/` (gitignored):
- `drift.json` — current drift scores per watchable
- `history.json` — refresh history (when, what, confidence)
- `last-scan.json` — snapshot for change detection (bead counts, component counts, etc.)

---

## 10. Beads Database Structure

**Path:** `/root/projects/Clavain/.beads/`

```
beads.db            # SQLite database (1.2 MB)
beads.db-shm        # Shared memory file (WAL mode)
beads.db-wal        # Write-ahead log
bd.sock             # Unix socket for daemon
daemon.lock         # PID file
config.yaml         # Beads config
```

**Relevant for drift detection:** Beads state is in SQLite, accessible via `bd` CLI. Signals like `bead_closed` and `bead_created` compare current `bd stats` against snapshot in `.interwatch/last-scan.json`.

---

## 11. Auto-Drift-Check Hook Design Implications

### 11.1 Recommended Pattern (Based on auto-compound)

**Hook type:** Stop  
**Event:** After each turn  
**Purpose:** Detect drift signals and suggest `/interwatch:watch` or auto-invoke refresh for Certain confidence

**Signal sources:**
1. Git commits since last watch run (probabilistic, weight 1)
2. Beads closed since last watch run (probabilistic, weight 2)
3. File changes in `skills/`, `commands/`, `agents/` (deterministic if component count changed)
4. Version bump detected (deterministic if version ≠ doc header)

**Weighted scoring:** Use same threshold model as auto-compound (weight >= 3 triggers evaluation).

**Block + reason output:** Inject prompt asking Claude to evaluate and run `/interwatch:watch`.

**Sentinel and throttle:**
- Shared `STOP_SENTINEL` (coordinate with auto-compound, session-handoff)
- Drift-specific throttle: at most once per 10 minutes (longer than compound's 5 min)
- Per-repo opt-out: `.claude/clavain.no-autodrift`

### 11.2 Integration with interwatch

**Discovery:** Use `_discover_interwatch_plugin()` from `hooks/lib.sh` to check if interwatch is installed. If not installed, hook should exit cleanly (no-op).

**State management:**
- Read `.interwatch/last-scan.json` to get baseline (bead counts, component counts, last watch timestamp)
- Compare against current state (via `bd stats`, `ls skills/*/SKILL.md | wc -l`, etc.)
- If no last-scan file exists, create initial snapshot and exit (first run)

**Confidence tiers:**
- **Certain:** `version_bump` or `component_count_changed` detected → auto-block with prompt to run `/interwatch:refresh <watchable>`
- **High/Medium:** weighted score >= 3 → block with prompt to run `/interwatch:watch`
- **Low:** no action

### 11.3 Transcript Analysis vs Direct State Check

**Auto-compound pattern:** Parses transcript for command strings and resolution phrases (lines 69-116).

**Auto-drift-check pattern:** Should NOT parse transcript — instead, check actual state:
- Beads: `bd stats --json`
- Git: `git rev-list --count HEAD --since=<last_watch_timestamp>`
- Files: `git diff --name-status <last_commit>..HEAD -- skills/ commands/ agents/`
- Version: compare plugin.json vs doc headers

**Why?** Drift is a state-based signal, not a conversational signal. We care about what changed in the repo, not what Claude said.

### 11.4 Output Format

**When drift detected:**

```bash
REASON="Auto-drift check: detected drift signals [${SIGNALS}] (score ${SCORE}, confidence ${CONFIDENCE}). Documentation may be stale. Run /interwatch:watch to scan all watchables, or /interwatch:status for quick summary. If Certain confidence: run /interwatch:refresh <watchable> to auto-regenerate."

jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'
```

**Claude's behavior:** Sees the prompt, decides whether to run the command. This preserves human oversight for Medium/High confidence, while making Certain confidence more urgent.

---

## 12. Cross-Hook Coordination

**Current Stop hooks:**
1. auto-compound.sh (timeout 5s)
2. session-handoff.sh (timeout 5s)

**Adding auto-drift-check.sh:**
- Same timeout: 5s
- Same sentinel check: `STOP_SENTINEL`
- Execution order: defined by array order in hooks.json

**Recommendation:** Add auto-drift-check THIRD in the array (after auto-compound and session-handoff), so it doesn't block the more critical hooks. If any hook writes the sentinel, drift-check skips.

**Alternative:** Make drift-check run on SessionEnd instead of Stop, so it doesn't compete for the Stop sentinel. But SessionEnd runs AFTER session termination, so Claude can't act on the prompt — making it less useful.

**Conclusion:** Use Stop event, coordinate with existing hooks via shared sentinel.

---

## 13. Files Requiring Modification for Auto-Drift-Check

### 13.1 New Files

1. **`hooks/auto-drift-check.sh`** — new Stop hook script (150-200 lines)
2. **`hooks/lib-drift.sh`** — drift detection utilities (optional, could inline into auto-drift-check.sh)

### 13.2 Modified Files

1. **`hooks/hooks.json`** — add auto-drift-check to Stop array
2. **`hooks/lib.sh`** — already has `_discover_interwatch_plugin()`, no changes needed
3. **`tests/structural/test_hooks.py`** — update hook count assertion
4. **`tests/shell/hooks.bats`** — add syntax check for auto-drift-check.sh
5. **`MEMORY.md`** — document auto-drift-check pattern

### 13.3 Documentation Updates

1. **`CLAUDE.md`** — mention auto-drift-check in Quick Commands or Design Decisions
2. **`AGENTS.md`** — add hook to architecture section
3. **`docs/PRD.md`** — add feature to PRD if not already covered

---

## 14. Recommendations

### 14.1 Use Weighted Scoring

Follow auto-compound's model: each signal has a weight, total must exceed threshold (3) to trigger. This prevents noisy single-signal fires (e.g., one commit alone won't fire, but commit + bead-close will).

### 14.2 Coordinate via Shared Sentinel

Use the existing `STOP_SENTINEL` pattern to prevent cascade loops. Write sentinel BEFORE analysis (minimize TOCTOU).

### 14.3 Throttle Aggressively

Drift detection is slower than compound detection (requires git/beads queries). Use 10-minute throttle (vs compound's 5 min).

### 14.4 Graceful Degradation Without interwatch

If interwatch is not installed, hook should exit cleanly (no-op). This allows Clavain to ship auto-drift-check without requiring interwatch as a hard dependency.

### 14.5 Preserve Human Oversight for Medium/High

Don't auto-execute refresh commands — inject prompt asking Claude to evaluate. Only suggest auto-refresh for **Certain** confidence (version mismatch, component count mismatch).

### 14.6 State Snapshot in .interwatch/

Store last-scan snapshot in `.interwatch/last-scan.json` (managed by interwatch skill). Hook reads this to determine what changed since last scan. If file doesn't exist, create initial snapshot and exit (bootstrap mode).

---

## 15. Open Questions

1. **Should auto-drift-check create .interwatch/ state if it doesn't exist?**  
   **Answer:** No — let interwatch skill manage its own state. Hook should exit cleanly if `.interwatch/` is absent. This keeps concerns separated.

2. **Should hook check all 4 watchables or just high-priority ones?**  
   **Answer:** Check all 4, but weight them differently. AGENTS.md and PRD are higher priority than vision (staleness: 14 days vs 30 days). Weight signals accordingly.

3. **Should hook block on Low confidence?**  
   **Answer:** No — only block on Medium+ (score >= 3). Report Low confidence in hook output but don't inject prompt.

4. **Should hook trigger on every Stop event or just on session close?**  
   **Answer:** Every Stop (like auto-compound). This catches drift incrementally. Use throttle to prevent spam.

5. **How to handle concurrent sessions in same repo?**  
   **Answer:** Sentinel files are session-scoped (`/tmp/clavain-drift-${SESSION_ID}`). Each session gets its own throttle. `.interwatch/last-scan.json` is shared, so last session to write wins — acceptable because drift state converges.

---

## 16. Conclusion

Auto-compound provides a solid template for auto-drift-check:
- Weighted signal scoring (threshold-based triggering)
- Sentinel coordination (shared `STOP_SENTINEL`)
- Throttle mechanism (time-based de-duplication)
- Block + reason prompt (preserve human oversight)
- Per-repo opt-out (`.claude/clavain.no-autodrift`)

interwatch provides the domain model:
- Watchables registry (declarative config)
- Signal types (deterministic vs probabilistic)
- Confidence tiers (Certain/High/Medium/Low/Green)
- Generator dispatch (interpath, interdoc)
- State tracking (`.interwatch/` directory)

**Next step:** Implement `hooks/auto-drift-check.sh` following the pattern above, test with `/claude --plugin-dir`, validate via structural tests, then integrate into hooks.json.
