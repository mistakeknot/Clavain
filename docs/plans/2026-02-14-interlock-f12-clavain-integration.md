# F12: Interlock Clavain Integration Shims — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Wire the interlock companion plugin into Clavain's discovery, session-start, doctor, and setup infrastructure — following the exact same patterns used by interphase, interflux, interpath, and interwatch.

**Architecture:** Interlock is a multi-agent coordination companion that provides file reservation, messaging, and conflict detection for Claude Code sessions sharing the same repository. Clavain's integration is a thin shim layer: discover the plugin, report it at session start, check its health in doctor, and list it in setup. No new skills or commands are added to Clavain — all coordination logic lives in the interlock plugin itself.

**Tech Stack:** Bash (hooks/lib.sh, session-start.sh), Markdown (doctor.md, setup.md, CLAUDE.md), Python (structural tests)

**Bead:** Clavain-uxm0

**PRD:** `docs/prds/2026-02-14-interlock-multi-agent-coordination.md` (F12)

---

### Task 1: Discovery Function in hooks/lib.sh

**Files:**
- Modify: `/root/projects/Clavain/hooks/lib.sh`

**Context:** Four discovery functions already exist at lines 7-78 of `hooks/lib.sh`, each following the identical pattern: check env var, search plugin cache for marker file, return root path or empty string. The interlock function follows this exact template.

**Insertion point:** After `_discover_interwatch_plugin()` (line 78), before `escape_for_json()` (line 82).

**Steps:**

1. Add `_discover_interlock_plugin()` function after line 78, before the blank line at line 80. The function checks `INTERLOCK_ROOT` env var first, then searches the plugin cache for `*/interlock/*/scripts/interlock-register.sh` (the registration script that interlock uses for agent lifecycle management).

2. The exact code to insert between line 78 and the existing blank line 80:

```bash

# Discover the interlock companion plugin root directory.
# Checks INTERLOCK_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_interlock_plugin() {
    if [[ -n "${INTERLOCK_ROOT:-}" ]]; then
        echo "$INTERLOCK_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interlock/*/scripts/interlock-register.sh' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # interlock-register.sh is at <root>/scripts/interlock-register.sh, so strip two levels
        echo "$(dirname "$(dirname "$f")")"
        return 0
    fi
    echo ""
}
```

3. Marker file rationale: `scripts/interlock-register.sh` is the registration script specified in the PRD (F7/F8). It is the canonical entry point for agent lifecycle. This parallels the pattern used by interpath (`scripts/interpath.sh`) and interwatch (`scripts/interwatch.sh`).

**Note on marker file:** The interlock plugin does not exist yet. When it is created, it MUST have `scripts/interlock-register.sh` at that path, or this discovery function will not find it. If the interlock plugin uses a different marker file path, update the `-path` glob in this function accordingly.

**Acceptance criteria:**
- [ ] `_discover_interlock_plugin()` function exists in `hooks/lib.sh`
- [ ] Returns `INTERLOCK_ROOT` env var value when set
- [ ] Searches plugin cache for `*/interlock/*/scripts/interlock-register.sh` when env var unset
- [ ] Returns empty string when neither env var nor cache hit
- [ ] `bash -n hooks/lib.sh` passes (syntax check)

---

### Task 2: SessionStart Hook Delegation

**Files:**
- Modify: `/root/projects/Clavain/hooks/session-start.sh`

**Context:** The session-start hook discovers companions at lines 77-93 and builds a `companions` string that gets injected into the session context. Each companion follows the pattern: call discovery function, check if non-empty, append a description line.

**Insertion point:** After the interwatch detection block (lines 90-93), before the Clodex toggle detection (line 96).

**Steps:**

1. Add interlock detection block after line 93 (after the interwatch block's closing `fi`), matching the exact pattern of the other companion detections:

```bash

# Interlock — multi-agent coordination companion
interlock_root=$(_discover_interlock_plugin)
if [[ -n "$interlock_root" ]]; then
    companions="${companions}\\n- **interlock**: multi-agent coordination (file reservations, conflict detection)"
fi
```

2. This block:
   - Calls `_discover_interlock_plugin` (added in Task 1)
   - Only appends context if the plugin is actually found
   - Uses the same `\\n-` formatting as all other companion entries
   - The description is concise and focuses on the user-visible capabilities

3. There is **no additional delegation** needed (unlike interphase, which gets its `lib-discovery.sh` sourced). Interlock's hooks are self-contained in the interlock plugin — Clavain only needs to detect and report it. The interlock plugin will have its own SessionStart hook declared in its `hooks.json` that handles agent registration independently.

**Acceptance criteria:**
- [ ] SessionStart hook detects interlock via `_discover_interlock_plugin()`
- [ ] Reports "interlock: multi-agent coordination" when installed
- [ ] Skips silently when not installed (empty string check)
- [ ] `bash -n hooks/session-start.sh` passes (syntax check)

---

### Task 3: Doctor Check and Documentation Updates

**Files:**
- Modify: `/root/projects/Clavain/commands/doctor.md`
- Modify: `/root/projects/Clavain/commands/setup.md`
- Modify: `/root/projects/Clavain/CLAUDE.md`

**Context:** Doctor checks 3b-3f currently cover: interphase (3b), interline (3c), interpath (3d), interwatch (3e), and agent memory (3f). The interlock check must be inserted with the correct numbering. Since 3f is already "Agent Memory", the interlock check becomes **3g** (the next available alphanumeric slot in the companion subsection).

#### 3a. Doctor Check 3g (Multi-Agent Coordination Companion)

**Insertion point in `commands/doctor.md`:** After check 3f (Agent Memory, line 113), before check 4 (Conflicting Plugins, line 115).

**Steps:**

1. Insert the following after line 113 (after the closing triple-backtick of check 3f):

```markdown

### 3g. Multi-Agent Coordination Companion

```bash
if ls ~/.claude/plugins/cache/*/interlock/*/scripts/interlock-register.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interlock: installed"
  # Check if intermute service is running
  if curl -s --connect-timeout 2 http://127.0.0.1:7338/health >/dev/null 2>&1; then
    echo "  intermute service: running"
    # Check circuit breaker state
    cb_state=$(curl -s --connect-timeout 2 http://127.0.0.1:7338/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('circuit_breaker','unknown'))" 2>/dev/null || echo "unknown")
    echo "  circuit breaker: ${cb_state}"
    # Check if agent is registered for this session
    if ls /tmp/interlock-agent-*.json 2>/dev/null | head -1 >/dev/null; then
      echo "  agent: registered"
    else
      echo "  agent: not registered (run /interlock:join to participate)"
    fi
  else
    echo "  intermute service: not running"
    echo "  Run /interlock:setup to install and start intermute"
  fi
else
  echo "interlock: not installed (multi-agent coordination unavailable)"
  echo "  Install: claude plugin install interlock@interagency-marketplace"
fi
```
```

2. Update the doctor output table (around line 170) to include interlock. After the `interwatch` row, add:

```
interlock    [installed|not installed]
```

3. Update the Recommendations section (line 176+) to include:

```
- interlock not installed → "Install interlock for multi-agent coordination: `claude plugin install interlock@interagency-marketplace`"
- intermute not running → "Run `/interlock:setup` to install and start the intermute coordination service"
```

#### 3b. Setup.md Update

**Insertion point in `commands/setup.md`:** In the "From interagency-marketplace" section (lines 30-38), after the `interwatch` install line (line 37).

**Steps:**

1. Add the interlock install command after line 37:

```bash
claude plugin install interlock@interagency-marketplace
```

2. In the Step 6 verification section (around line 163-168), add interlock to the companions check:

```bash
echo "interlock: $(ls ~/.claude/plugins/cache/*/interlock/*/scripts/interlock-register.sh 2>/dev/null | head -1 >/dev/null && echo 'installed' || echo 'not installed')"
```

#### 3c. CLAUDE.md Update

**Insertion point in `/root/projects/Clavain/CLAUDE.md`:** Line 7, the Overview section.

**Steps:**

1. Update the companions list in the Overview line (line 7) to include all 6 companions. Current text ends with:
```
interpath` (product artifact generation), `interwatch` (doc freshness monitoring).
```
Update to:
```
interpath` (product artifact generation), `interwatch` (doc freshness monitoring), `interlock` (multi-agent coordination).
```

**Acceptance criteria:**
- [ ] Doctor check 3g tests interlock installation, intermute service health, and agent registration
- [ ] Doctor output table includes `interlock` row
- [ ] Doctor recommendations include interlock install instructions
- [ ] Setup.md includes `claude plugin install interlock@interagency-marketplace`
- [ ] Setup.md verification checks interlock installation
- [ ] CLAUDE.md Overview lists all 6 companions including interlock

---

### Task 4: Tests

**Files:**
- Modify: `/root/projects/Clavain/tests/shell/shims.bats`
- Modify: `/root/projects/Clavain/tests/shell/lib.bats` (if needed)

**Context:** The existing `tests/shell/shims.bats` tests discovery functions (lines 192-209 test `_discover_beads_plugin` with env var and empty cache). The test pattern is: source `lib.sh`, set env var, call discovery function, assert output.

**Insertion point in `tests/shell/shims.bats`:** After the `_discover_beads_plugin` tests (line 209), at the end of the file.

**Steps:**

1. Add two tests to `tests/shell/shims.bats` for `_discover_interlock_plugin`, following the exact pattern of the `_discover_beads_plugin` tests:

```bash

# ─── _discover_interlock_plugin ─────────────────────────────────────

@test "_discover_interlock_plugin: returns INTERLOCK_ROOT when set" {
    export INTERLOCK_ROOT="/custom/interlock/path"
    source "$HOOKS_DIR/lib.sh"
    run _discover_interlock_plugin
    assert_success
    assert_output "/custom/interlock/path"
    unset INTERLOCK_ROOT
}

@test "_discover_interlock_plugin: returns empty when nothing found" {
    export INTERLOCK_ROOT=""
    export HOME="$TEST_PROJECT"
    source "$HOOKS_DIR/lib.sh"
    run _discover_interlock_plugin
    assert_success
    assert_output ""
}
```

2. These tests verify:
   - The env var override path works (returns `INTERLOCK_ROOT` when set)
   - The fallback returns empty string when neither env var nor cache file exists (using the isolated `$TEST_PROJECT` home directory that has an empty plugin cache)

3. No structural Python tests are needed for the discovery function itself — the shell tests cover the discovery behavior. However, if a `test_hooks_json.py` or similar test validates hook script syntax, ensure `bash -n hooks/lib.sh` still passes (it will, since we only add a new function following existing patterns).

4. Verify the session-start syntax is clean:
```bash
bash -n hooks/session-start.sh
```

**Acceptance criteria:**
- [ ] Two new bats tests for `_discover_interlock_plugin` (env var + empty cache)
- [ ] All existing shim tests still pass
- [ ] `bash -n hooks/lib.sh` passes
- [ ] `bash -n hooks/session-start.sh` passes

---

## Pre-flight Checklist

- [ ] Verify `hooks/lib.sh` has 4 existing discovery functions: `grep -c '_discover_.*_plugin' hooks/lib.sh` should return 4
- [ ] Verify `hooks/session-start.sh` detects 3 companions (interflux, interpath, interwatch): `grep -c '_discover_' hooks/session-start.sh` should return 3
- [ ] Verify doctor has checks 3b-3f: `grep -c '### 3[b-f]' commands/doctor.md` should return 5
- [ ] Verify setup lists 7 interagency-marketplace plugins: `grep -c 'interagency-marketplace' commands/setup.md` in install section
- [ ] Verify existing tests pass: `cd /root/projects/Clavain && bats tests/shell/shims.bats`
- [ ] Verify `bash -n hooks/lib.sh` passes
- [ ] Verify `bash -n hooks/session-start.sh` passes

## Post-execution Checklist

- [ ] All 4 tasks completed
- [ ] `_discover_interlock_plugin()` function exists in `hooks/lib.sh` with `INTERLOCK_ROOT` env var support
- [ ] `hooks/session-start.sh` detects interlock and reports it in companion context
- [ ] `commands/doctor.md` has check 3g for interlock (plugin installed, intermute running, agent registered)
- [ ] `commands/setup.md` includes `claude plugin install interlock@interagency-marketplace`
- [ ] `CLAUDE.md` Overview lists interlock as 6th companion
- [ ] Two new bats tests pass for `_discover_interlock_plugin`
- [ ] All existing tests still pass (no regressions)
- [ ] `bash -n hooks/lib.sh` passes
- [ ] `bash -n hooks/session-start.sh` passes
- [ ] Bead Clavain-uxm0 updated with completion status

## Files Modified Summary

| File | Change |
|------|--------|
| `hooks/lib.sh` | Add `_discover_interlock_plugin()` (lines 80-96) |
| `hooks/session-start.sh` | Add interlock companion detection (after line 93) |
| `commands/doctor.md` | Add check 3g for interlock health (after line 113) |
| `commands/setup.md` | Add interlock install command + verification |
| `CLAUDE.md` | Add interlock to companion list in Overview |
| `tests/shell/shims.bats` | Add 2 tests for `_discover_interlock_plugin` |
