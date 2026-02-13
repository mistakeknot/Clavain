# PostToolUse Hook Patterns for Git Push Detection

Research findings on Claude Code's PostToolUse hook system for detecting and responding to specific Bash commands (particularly `git push`).

## Overview

PostToolUse hooks receive JSON on stdin after a tool executes successfully. The hook can inspect `tool_input` and `tool_response` to determine what happened and provide feedback to Claude or take automated actions.

## 1. PostToolUse JSON Schema

### Common Fields (All Tools)

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/conversation.jsonl",
  "cwd": "/current/working/directory",
  "hook_event_name": "PostToolUse",
  "tool_name": "ToolName",
  "tool_input": { /* tool-specific */ },
  "tool_response": { /* tool-specific */ }
}
```

### Bash Tool Specifics

For `tool_name: "Bash"`, the JSON structure is:

```json
{
  "session_id": "abc123",
  "transcript_path": "...",
  "cwd": "...",
  "hook_event_name": "PostToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "git push origin main",
    "description": "Push commits to remote main branch"
  },
  "tool_response": {
    // Response structure varies - typically contains stdout/stderr
    // Exact schema not documented in reference materials
  }
}
```

**Key Discovery:** `tool_input.command` contains the full Bash command string that was executed.

## 2. Matcher Configuration

The `matcher` field in hooks.json uses **case-sensitive regex patterns**:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",  // Matches only the Bash tool
        "hooks": [...]
      }
    ]
  }
}
```

**Yes, PostToolUse can match "Bash"** - confirmed by:
- Official docs: "Recognizes the same matcher values as PreToolUse" (line 167 of hooks.md)
- Common matchers list includes `Bash` explicitly (line 155)
- Example validation hook shows `tool_name != "Bash"` check (line 575)

## 3. Detecting Specific Commands

Pattern from existing hooks (auto-compound.sh, session-handoff.sh):

### Method 1: Parse JSON with jq (Preferred)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Read hook input
INPUT=$(cat)

# Extract tool name and command
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Guard: only process Bash tools
if [[ "$TOOL_NAME" != "Bash" ]]; then
    exit 0
fi

# Check for git push
if echo "$COMMAND" | grep -q '^git push'; then
    # Do something when git push is detected
    echo "Detected git push: $COMMAND"
fi

exit 0
```

### Method 2: Inline jq (Compact)

From clodex-audit.sh (lines 16-18):

```bash
file_path="$(jq -r '(.tool_input.file_path // .tool_input.notebook_path // empty)' \
  <<<"$payload" 2>/dev/null || true)"
```

### Method 3: Transcript Analysis (Indirect)

From auto-compound.sh (lines 79-82) - detects git commands by scanning the transcript:

```bash
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')
RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)

if echo "$RECENT" | grep -q '"git commit\|"git add.*&&.*git commit'; then
    # Detected git commit in transcript
fi
```

**Note:** Transcript method is indirect - it searches for JSON-escaped command strings in the conversation log, not the hook's direct input.

## 4. Hook Output Control

PostToolUse hooks can return JSON to control Claude's behavior:

### Basic: Exit Code Only

```bash
#!/usr/bin/env bash
# Exit 0 = success (stdout shown in transcript mode)
# Exit 2 = blocking error (stderr fed to Claude automatically)
# Other = non-blocking error (stderr shown to user)

echo "Hook executed successfully"
exit 0
```

### Advanced: JSON Output

```json
{
  "decision": "block",  // or undefined
  "reason": "Explanation fed to Claude",
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "Extra context for Claude"
  },
  "suppressOutput": true,  // Hide stdout from transcript
  "systemMessage": "Warning shown to user"
}
```

**Key Behaviors:**
- `decision: "block"` - Prompts Claude with `reason` (tool already ran, can't prevent execution)
- `additionalContext` - Adds information for Claude to consider
- `suppressOutput: true` - Hides hook stdout from transcript mode (Ctrl-R)

## 5. Existing Git Command Detection Patterns

### auto-compound.sh (Stop Hook)

Detects git commits indirectly via transcript:

```bash
if echo "$RECENT" | grep -q '"git commit\|"git add.*&&.*git commit'; then
    SIGNALS="${SIGNALS}commit,"
    WEIGHT=$((WEIGHT + 1))
fi
```

**Why transcript instead of PostToolUse?**
- Stop hooks don't have access to individual tool calls
- They receive only `session_id`, `transcript_path`, and `stop_hook_active`
- Must scan conversation history to detect what happened

### clodex-audit.sh (PostToolUse Hook)

Detects file edits (not git-specific):

```bash
payload="$(cat || true)"
file_path="$(jq -r '(.tool_input.file_path // .tool_input.notebook_path // empty)' \
  <<<"$payload" 2>/dev/null || true)"

# Skip temp files, dotfiles, and non-source files
[[ "$file_path" == /tmp/* ]] && exit 0
[[ "$base" == .* ]] && exit 0
```

**Pattern:** Extract relevant fields, apply filters, log violations.

## 6. Complete Example: Git Push Hook

```bash
#!/usr/bin/env bash
# PostToolUse hook: detect git push and trigger actions
set -euo pipefail

# Guard: require jq
if ! command -v jq &>/dev/null; then
    exit 0
fi

# Read hook input
INPUT=$(cat)

# Extract tool name and command
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Guard: only process Bash tools
if [[ "$TOOL_NAME" != "Bash" ]]; then
    exit 0
fi

# Detect git push (various forms)
if ! echo "$COMMAND" | grep -qE '^git push|&&.*git push|\|\|.*git push'; then
    exit 0
fi

# Extract branch/remote if needed
REMOTE=$(echo "$COMMAND" | grep -oP 'git push\s+\K\S+' || echo "origin")
BRANCH=$(echo "$COMMAND" | grep -oP 'git push\s+\S+\s+\K\S+' || echo "current")

# Take action (example: log the push)
echo "[$(date -Iseconds)] git push detected: $REMOTE/$BRANCH" >> ~/.claude/git-push.log

# Optionally provide feedback to Claude
if echo "$COMMAND" | grep -q 'push --force'; then
    # Warn about force push
    jq -n --arg msg "⚠️  Force push detected" '{
      "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": $msg
      }
    }'
else
    # Silent success
    exit 0
fi
```

### hooks.json Configuration

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/git-push-detector.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## 7. Reference Documentation Locations

- **Primary hook reference:** `/root/projects/Clavain/skills/working-with-claude-code/references/hooks.md`
- **Quickstart guide:** `/root/projects/Clavain/skills/working-with-claude-code/references/hooks-guide.md`
- **Existing implementations:**
  - `hooks/clodex-audit.sh` - PostToolUse for Edit/Write
  - `hooks/auto-compound.sh` - Stop hook with transcript analysis
  - `hooks/session-handoff.sh` - Stop hook detecting git status

## 8. Key Findings Summary

1. **PostToolUse receives full command** - `tool_input.command` contains the exact Bash command string
2. **Matcher works for Bash** - Use `"matcher": "Bash"` in hooks.json
3. **Tool response schema undefined** - Official docs say "depends on the tool", no Bash-specific schema documented
4. **Pattern detection via grep** - Extract command with jq, match with grep/regex
5. **JSON output for feedback** - Use `hookSpecificOutput.additionalContext` to inform Claude
6. **Sentinel pattern for guards** - Existing hooks use `/tmp/clavain-*-${SESSION_ID}` files to prevent re-triggering
7. **Fail-open design** - All hooks check for jq availability and exit 0 if missing

## 9. Limitations and Gotchas

- **PostToolUse runs AFTER execution** - Can't prevent git push, only react to it
- **Use PreToolUse to block** - If prevention is needed, use PreToolUse with `permissionDecision: "deny"`
- **tool_response is opaque** - No documented schema for Bash tool responses
- **Timeout is critical** - Default 60s, but network operations (git push) may take longer - set explicit timeout
- **No access to exit code** - Hook receives tool_response but docs don't specify if it includes the command's exit status
- **Parallel execution** - Multiple hooks matching same event run in parallel, use sentinel files to coordinate

## 10. Recommended Patterns

### For Detection Only (Logging, Notifications)

Use PostToolUse with:
- Simple grep on `tool_input.command`
- Log to file or trigger external notification
- Exit 0 for silent success

### For Feedback to Claude

Use PostToolUse with:
- JSON output with `additionalContext`
- `decision: "block"` if Claude needs to take corrective action
- `suppressOutput: true` to hide log noise from transcript

### For Prevention

Use PreToolUse with:
- `permissionDecision: "deny"` to block the tool call
- `permissionDecisionReason` to explain why to Claude
- Command pattern validation before execution

## References

- Claude Code hooks reference: `/root/projects/Clavain/skills/working-with-claude-code/references/hooks.md`
- Clavain plugin hooks: `/root/projects/Clavain/hooks/hooks.json`
- Example PostToolUse hook: `hooks/clodex-audit.sh`
- Example Stop hook with git detection: `hooks/auto-compound.sh`
