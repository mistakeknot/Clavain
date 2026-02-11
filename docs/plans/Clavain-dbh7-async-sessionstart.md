# Plan: Add async: true to SessionStart hook (Clavain-dbh7)

## Goal
Prevent TUI blocking on session startup by making the SessionStart hook async.

## Steps

### Step 1: Update hooks.json
In `hooks/hooks.json`, add `"async": true` to the SessionStart hook entry:

```json
"SessionStart": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh\"",
        "timeout": 10,
        "async": true
      }
    ]
  }
]
```

### Step 2: Run shell tests
```bash
bats tests/shell/
```
Verify hooks.json validation still passes.

### Step 3: Commit
Commit message: `perf: make SessionStart hook async to prevent TUI blocking`

## Verification
- Session startup should feel snappier (no blocking on skill content injection)
- `using-clavain` context should still appear in conversation after a brief delay
