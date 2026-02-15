---
name: interspect-revert
description: Revert a routing override and optionally blacklist the pattern
argument-hint: "<agent-name or commit-sha>"
---

# Interspect Revert

Remove a routing override and optionally blacklist the pattern so it won't re-propose.

<revert_target> #$ARGUMENTS </revert_target>

## Locate Library

```bash
INTERSPECT_LIB=$(find ~/.claude/plugins/cache -path '*/clavain/*/hooks/lib-interspect.sh' 2>/dev/null | head -1)
[[ -z "$INTERSPECT_LIB" ]] && INTERSPECT_LIB=$(find ~/projects -path '*/hub/clavain/hooks/lib-interspect.sh' 2>/dev/null | head -1)
if [[ -z "$INTERSPECT_LIB" ]]; then
    echo "Error: Could not locate hooks/lib-interspect.sh" >&2
    exit 1
fi
source "$INTERSPECT_LIB"
_interspect_ensure_db
DB=$(_interspect_db_path)
```

## Parse Target

If argument looks like a git SHA (7+ hex chars), target by commit. Otherwise, target by agent name.

## Idempotency Check

Read routing-overrides.json and check if the target override exists:

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
FILEPATH="${FLUX_ROUTING_OVERRIDES_PATH:-.claude/routing-overrides.json}"
FULLPATH="${ROOT}/${FILEPATH}"

if ! jq -e --arg agent "$AGENT" '.overrides[] | select(.agent == $agent)' "$FULLPATH" >/dev/null 2>&1; then
    echo "Override for ${AGENT} not found. Already removed or never existed."
    exit 0
fi
```

## Remove Override

Validate agent name, then run removal inside flock using a named function:

```bash
# Validate agent name
if ! _interspect_validate_agent_name "$AGENT"; then
    exit 1
fi

# Write commit message to temp file (no shell injection)
COMMIT_MSG_FILE=$(mktemp)
printf '[interspect] Revert routing override for %s\n\nReason: User requested revert via /interspect:revert\n' "$AGENT" > "$COMMIT_MSG_FILE"

_interspect_flock_git _interspect_revert_override_locked \
    "$ROOT" "$FILEPATH" "$FULLPATH" "$AGENT" "$COMMIT_MSG_FILE" "$DB"
REVERT_EXIT=$?
rm -f "$COMMIT_MSG_FILE"
```

The locked revert function (defined in lib-interspect.sh or inline):
```bash
_interspect_revert_override_locked() {
    set -e
    local root="$1" filepath="$2" fullpath="$3" agent="$4"
    local commit_msg_file="$5" db="$6"

    CURRENT=$(jq '.' "$fullpath")
    UPDATED=$(echo "$CURRENT" | jq --arg agent "$agent" 'del(.overrides[] | select(.agent == $agent))')
    echo "$UPDATED" | jq '.' > "$fullpath"

    cd "$root"
    git add "$filepath"
    if ! git commit --no-verify -F "$commit_msg_file"; then
        # Rollback: unstage + restore
        git reset HEAD -- "$filepath" 2>/dev/null || true
        git restore "$filepath" 2>/dev/null || git checkout -- "$filepath" 2>/dev/null || true
        echo "ERROR: Git commit failed. Revert not applied." >&2
        return 1
    fi

    # Close canary and update DB INSIDE flock
    local escaped_agent
    escaped_agent=$(_interspect_sql_escape "$agent")
    sqlite3 "$db" "UPDATE canary SET status = 'reverted' WHERE group_id = '${escaped_agent}' AND status = 'active';"
}
```

## Blacklist Decision

After successful revert, ask the user whether to blacklist:

```
Override for {agent} has been removed. Should interspect re-propose this if evidence accumulates?

Options:
- "Allow future proposals" (Recommended) — Agent can be proposed again if evidence warrants it
- "Blacklist permanently" — Never re-propose this exclusion
```

If "Blacklist permanently":
```bash
local escaped_agent
escaped_agent=$(_interspect_sql_escape "$AGENT")
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
sqlite3 "$DB" "INSERT OR REPLACE INTO blacklist (pattern_key, blacklisted_at, reason) VALUES ('${escaped_agent}', '${TS}', 'User reverted via /interspect:revert');"
```

## Report

```
Reverted routing override for **{agent}**.
{if blacklisted: "Pattern blacklisted — interspect won't re-propose this exclusion.
Run `/interspect:unblock {agent}` to allow future proposals."}
{if not blacklisted: "Interspect may re-propose this exclusion if evidence warrants it."}
```
