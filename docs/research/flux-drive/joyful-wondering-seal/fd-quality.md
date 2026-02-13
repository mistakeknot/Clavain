# fd-quality Review: Clodex Overhaul Plan

## Findings Index
- P0 | P0-1 | "Step 1: Script Creation" | No shebang specified — will silently use /bin/bash (non-portable)
- P0 | P0-2 | "Step 5: Behavioral Contract" | Injection text says "source code" but doesn't define which extensions
- P1 | P1-1 | "Step 1: Script Creation" | Missing error handling pattern — no input validation, flag existence check
- P1 | P1-2 | "Step 5: Behavioral Contract" | Wording inconsistency: "blocked" vs "denied" between injection and current toggle
- P1 | P1-3 | "Step 6: Update behavioral-contract.md" | Removal instruction is vague — what about other PreToolUse references?
- P1 | P1-4 | "Step 2: Rewrite command" | Thin wrapper pattern not demonstrated — risk of misimplementation
- IMP | IMP-1 | "Step 1: Script Creation" | Script could output current state on error for better UX
- IMP | IMP-2 | "Step 5: Behavioral Contract" | Message could align with flag file content for debugging
- IMP | IMP-3 | "Step 7: help.md description" | Plan says "keep as-is" but description is wrong after hook removal

Verdict: needs-changes

---

## Summary

The plan removes clodex's PreToolUse deny-gate and replaces it with behavioral contract injection. Stage 1 found architectural gaps (undefined "source code", no verification). This review focuses on script quality, naming patterns, contract wording consistency, and error handling.

Found 3 P0s (portability, definition scope, error handling), 4 P1s (inconsistency, vagueness, missing demonstration), 3 improvements (UX, alignment, stale description).

---

## Issues Found

### P0-1: No shebang specified — will silently use /bin/bash (non-portable)

**Location:** Step 1 (Create `scripts/clodex-toggle.sh`)

**Issue:** The plan specifies creating a bash script but doesn't specify the shebang. Clavain's pattern is **`#!/usr/bin/env bash`** for portability, but two scripts (`bump-version.sh`, `check-versions.sh`) incorrectly use `#!/bin/bash`. The plan doesn't specify which to follow.

**Evidence from codebase:**
- 9 of 11 scripts use `#!/usr/bin/env bash` (dispatch.sh, upstream-check.sh, debate.sh, etc.)
- All hooks use `#!/usr/bin/env bash` (autopilot.sh line 1, session-start.sh line 1, lib-discovery.sh line 1)
- Only 2 outliers use `#!/bin/bash` (bump-version.sh line 1, check-versions.sh line 1)

**Why P0:** Without a shebang spec, implementer might copy the wrong pattern. This script will be invoked from a command wrapper — wrong shebang breaks portability on systems where bash is not at `/bin/bash` (common on NixOS, some BSDs).

**Fix:** Add to Step 1:
```
Start the script with:
#!/usr/bin/env bash
set -euo pipefail
```

---

### P0-2: Injection text says "source code" but doesn't define which extensions

**Location:** Step 5 (session-start.sh injection)

**Issue:** The proposed injection says "Do NOT use Edit/Write on source code" but never defines what constitutes source code. The current autopilot.sh hook (lines 48-59) has an explicit allowlist of non-code extensions (`.md`, `.json`, `.yaml`, etc.) and lets everything else fall through as "source code". The new behavioral contract doesn't include this mapping.

**Current state (autopilot.sh lines 48-52):**
```bash
case "${FILE_PATH##*.}" in
  md|json|yaml|yml|toml|txt|csv|xml|html|css|svg|lock|cfg|ini|conf|env)
    exit 0
    ;;
esac
```

**Current state (behavioral-contract.md lines 12-13):**
```
## Allowed Direct Edits (not blocked by hook)
*.md, *.json, *.yaml, *.yml, *.toml, *.txt, *.csv, *.xml, *.html, *.css, *.svg, /tmp/*, dotfiles
```

**Proposed injection (Step 5):**
```
Non-code files (.md, .json, .yaml, .toml, etc.) can still be edited directly.
```

The "etc." is vague and doesn't match the comprehensive list. Claude will have to guess whether `.txt`, `.csv`, `.svg`, `.lock` are "non-code" (they are, per the allowlist).

**Why P0:** This is the core routing contract — vague definitions cause Claude to either (a) over-restrict and dispatch trivial config edits through Codex (wasting time), or (b) under-restrict and try to Edit source files, hitting errors because the contract said it was okay.

**Fix:** Replace "etc." with the full allowlist from behavioral-contract.md line 13.

---

### P1-1: Missing error handling pattern — no input validation, flag existence check

**Location:** Step 1 (Create `scripts/clodex-toggle.sh`)

**Issue:** The plan specifies check-and-toggle logic but doesn't mention error handling. What if:
- `$PROJECT_DIR` is unset (script called outside Claude Code context)?
- `.claude/` directory creation fails (permissions)?
- Flag file removal fails (permissions, race condition)?

Clavain scripts use defensive patterns. Examples:
- `dispatch.sh` line 70: `require_arg()` validates all flag inputs
- `upstream-check.sh` lines 40-44: loads existing JSON with fallback to empty object
- `bump-version.sh` lines 39-42: validates version format with error message before proceeding

The toggle script should validate `$PROJECT_DIR` exists and is writable before attempting changes.

**Why P1 (not P0):** The script will be invoked from a command wrapper in Claude Code's controlled environment where `$PROJECT_DIR` is usually set. However, if the script is run manually (e.g., user testing, automation), silent failures or confusing errors hurt UX.

**Fix:** Add to Step 1:
```bash
# Validate environment
if [[ -z "${PROJECT_DIR:-}" ]]; then
  echo "Error: PROJECT_DIR not set. Run from Claude Code or set manually." >&2
  exit 1
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Error: PROJECT_DIR does not exist: $PROJECT_DIR" >&2
  exit 1
fi
```

---

### P1-2: Wording inconsistency between injection and current toggle output

**Location:** Step 5 (session-start.sh injection) vs current command output (clodex-toggle.md lines 35-44)

**Issue:** The proposed injection says Claude's writes will be "blocked" but uses passive voice and doesn't specify by what mechanism. Current toggle output (line 37) says "will be blocked by the PreToolUse hook" which is accurate but will be outdated after this change.

**Current session-start.sh line 68:**
```
clodex: ON — source code edits are routed through Codex agents. Direct Edit/Write to source files will be blocked by the PreToolUse hook.
```

**Proposed injection (Step 5):**
```
**CLODEX MODE: ON** — Route ALL implementation through Codex.

You are an orchestrator. Do NOT use Edit/Write on source code. Instead:
[...]
```

The "Do NOT" is imperative but behavioral, not enforcement. The current line 68 explicitly says "will be blocked" which sets expectation of enforcement. After the hook is removed, there's no enforcement — only the behavioral contract.

**Consistency gap:**
- Injection uses "Do NOT" (imperative behavioral)
- Current toggle output uses "will be blocked" (enforcement)
- Both will be active after the change, but with conflicting framings

**Why P1:** This affects Claude's mental model. "Will be blocked" implies attempting Edit will fail with an error. "Do NOT" implies it's a guideline. After hook removal, Edit WILL succeed (no block), so "will be blocked" becomes a lie. The injection should acknowledge this is behavioral, not enforced.

**Fix:** Change Step 5 injection to match reality:
```
**CLODEX MODE: ON** — Route ALL implementation through Codex.

You are an orchestrator. Behavioral contract: do NOT use Edit/Write on source code (tool calls will succeed, but you are expected to dispatch instead).
```

Also update Step 2's toggle output messages to remove "will be blocked" phrasing.

---

### P1-3: Removal instruction is vague — what about other PreToolUse references?

**Location:** Step 6 (Update `behavioral-contract.md`)

**Issue:** Step 6 says "Remove references to 'PreToolUse hook', 'blocked by hook', 'denied with dispatch instructions'." But there are 15+ PreToolUse references across the codebase:

From skills directory grep (above):
- `skills/executing-plans/SKILL.md` (2 references to "clodex mode")
- `skills/flux-drive/SKILL.md` (2 references to "clodex mode")
- `skills/developing-claude-code-plugins/references/polyglot-hooks.md`
- `skills/working-with-claude-code/references/hooks.md` (10+ references)

The plan only specifies updating `behavioral-contract.md` (one file). What about:
- Commands: `clodex-toggle.md` lines 37, 68, 79-83 explicitly reference PreToolUse hook enforcement
- Skills: References to clodex behavior in `executing-plans`, `flux-drive`
- Docs: `docs/solutions/workflow-issues/settings-heredoc-permission-bloat-20260210.md` line 1 mentions PreToolUse errors

**Why P1 (not P0):** The core change (removal from hooks.json, behavioral-contract.md update) is specified. These other files are documentation/reference and won't break functionality if stale. But stale docs cause confusion and future implementers might re-introduce the hook thinking it's required.

**Fix:** Add to Step 6:
```
After updating behavioral-contract.md, grep for remaining PreToolUse references:
  grep -r "PreToolUse\|blocked by hook\|clodex.*blocked" skills/ commands/ --include="*.md"

For each match:
- If it explains the OLD system (hook enforcement), add a deprecation note or remove
- If it's in working-with-claude-code/references/hooks.md (general hook docs), leave as-is
- If it's in clodex-toggle.md, update to match new behavioral contract framing
```

---

### P1-4: Thin wrapper pattern not demonstrated — risk of misimplementation

**Location:** Step 2 (Rewrite `commands/clodex-toggle.md`)

**Issue:** Step 2 says "Replace the 90-line markdown instructions with a ~10-line command that just calls the script" and shows a 4-line YAML frontmatter example, but doesn't show the body. Clavain has two patterns for script-wrapping commands:

**Pattern 1: Direct Bash execution (most common)**
From `upstream-sync.md` lines 1-18: frontmatter declares `allowed-tools: [Bash, Read, ...]`, body gives multi-step instructions using Bash tool.

**Pattern 2: Skill delegation**
From `create-agent-skill.md` line 1: `allowed-tools: Skill(create-agent-skills)`, body just says "Use the skill."

The plan's proposed frontmatter (Step 2) lists `allowed-tools: [Bash]` which suggests Pattern 1, but doesn't demonstrate the body. Without a concrete example, implementer might:
- Write verbose instructions (defeats the "thin wrapper" goal)
- Forget to pass through script output (loses clean markdown UX)
- Not handle script errors (user sees raw exit code)

**Why P1:** The script itself (Step 1) outputs markdown. A thin wrapper just needs to call it and pass through output. But without demonstrating this, there's implementation variance risk.

**Fix:** Add to Step 2:
```markdown
Body should be:
---
# Clodex Mode Toggle

Run the toggle script and display its output:

```bash
SCRIPT_DIR=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/clodex-toggle.sh' 2>/dev/null | head -1)
[[ -z "$SCRIPT_DIR" ]] && SCRIPT_DIR=$(find ~/projects/Clavain -name clodex-toggle.sh -path '*/scripts/*' 2>/dev/null | head -1)

if [[ -z "$SCRIPT_DIR" ]]; then
  echo "Error: Could not locate clodex-toggle.sh" >&2
  exit 1
fi

bash "$SCRIPT_DIR"
```
```

(This follows the pattern from `clodex/SKILL.md` lines 66-68 for resolving plugin paths.)

---

## Improvements Suggested

### IMP-1: Script could output current state on error for better UX

**Location:** Step 1 (Create `scripts/clodex-toggle.sh`)

**Enhancement:** If the script encounters an error (e.g., permissions failure on flag file creation), it currently would just exit. Better UX: print current state before exiting so user knows whether mode is ON or OFF despite the error.

**Pattern from bump-version.sh lines 16-18:**
```bash
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
fi
```
Then use `${RED}Error:${NC}` for colored error messages.

**Suggested addition:**
```bash
# Before exit on error, show current state
current_state="OFF"
[[ -f "$FLAG_FILE" ]] && current_state="ON"
echo "Current clodex mode: $current_state" >&2
```

---

### IMP-2: Message could align with flag file content for debugging

**Location:** Step 1 (script output messages)

**Enhancement:** Current toggle command (line 31) writes a timestamp to the flag file (`date -Iseconds > flag`). The proposed script doesn't specify what to write. For debugging, the timestamp is useful (when was clodex enabled?). Script output could include this.

**Suggested ON message:**
```
Clodex mode: **ON** (enabled at $(cat "$FLAG_FILE"))

[rest of message]
```

This helps users debug "why is clodex on?" questions without opening the flag file.

---

### IMP-3: Plan says "keep as-is" but help.md description is wrong after hook removal

**Location:** Step 7 (help.md description)

**Issue:** Step 7 says "Update `commands/help.md` description — keep as-is." But the current description (help.md line 78):
```
| `/clavain:clodex-toggle` | Toggle Codex delegation mode |
```

After this change, the description is still accurate ("Toggle Codex delegation mode"), but the help text should clarify it's behavioral, not enforced. Current users might expect the old hook behavior.

**Suggested improvement:** Change help.md line 78 to:
```
| `/clavain:clodex-toggle` | Toggle Codex delegation mode (behavioral contract, no longer hook-enforced) |
```

Or add a footnote after the Meta section explaining the clodex mode change.

This is low-priority (help.md is brief by design), but worth considering for user expectations.

---

## Overall Assessment

The plan's core mechanics are sound (remove hook, strengthen injection), but execution details are underspecified. P0s affect portability and contract clarity — must be fixed. P1s affect consistency and documentation hygiene — should be fixed to prevent future confusion.

The script creation (Step 1) needs defensive patterns and a shebang spec. The behavioral contract (Step 5) needs complete extension lists and honest framing ("behavioral, not enforced"). The documentation sweep (Step 6) needs explicit grep instructions to catch stale references.

After P0/P1 fixes, this plan will produce a cleaner, lower-friction clodex system that aligns with Clavain's quality standards.

<!-- flux-drive:complete -->
