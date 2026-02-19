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

## Disambiguation Check (F7)

Determine what exists for this agent — routing override, overlays, or both:

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
FILEPATH="${FLUX_ROUTING_OVERRIDES_PATH:-.claude/routing-overrides.json}"
FULLPATH="${ROOT}/${FILEPATH}"

HAS_OVERRIDE=false
HAS_OVERLAYS=false

# Check routing override
if jq -e --arg agent "$AGENT" '.overrides[] | select(.agent == $agent)' "$FULLPATH" >/dev/null 2>&1; then
    HAS_OVERRIDE=true
fi

# Check active overlays (using shared parser — F4)
OVERLAY_DIR="${ROOT}/.clavain/interspect/overlays/${AGENT}"
if [[ -d "$OVERLAY_DIR" ]]; then
    for overlay_file in "$OVERLAY_DIR"/*.md; do
        [[ -f "$overlay_file" ]] || continue
        if _interspect_overlay_is_active "$overlay_file"; then
            HAS_OVERLAYS=true
            break
        fi
    done
fi
```

**If NEITHER exists:** Report "No routing override or active overlays found for {agent}." and exit.

**If BOTH exist:** Ask user via AskUserQuestion:
```
Agent {agent} has both a routing override and active overlays. Which do you want to revert?

Options:
- "Routing override" — Remove the agent exclusion
- "Overlays" — Disable prompt tuning overlays
- "Both" — Remove override AND disable all overlays
```

**If only routing override:** Proceed to routing override revert (below).
**If only overlays (or user chose overlays/both):** Proceed to overlay revert section.

## Routing Override Revert

(Only runs if HAS_OVERRIDE=true AND user chose "Routing override" or "Both")

### Idempotency Check

```bash
if ! jq -e --arg agent "$AGENT" '.overrides[] | select(.agent == $agent)' "$FULLPATH" >/dev/null 2>&1; then
    echo "Override for ${AGENT} not found. Already removed or never existed."
    # Continue to overlay revert if user chose "Both"
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

## Report (Routing Override)

```
Reverted routing override for **{agent}**.
{if blacklisted: "Pattern blacklisted — interspect won't re-propose this exclusion.
Run `/interspect:unblock {agent}` to allow future proposals."}
{if not blacklisted: "Interspect may re-propose this exclusion if evidence warrants it."}
```

## Overlay Revert

(Only runs if HAS_OVERLAYS=true AND user chose "Overlays" or "Both")

### List Active Overlays

```bash
OVERLAY_DIR="${ROOT}/.clavain/interspect/overlays/${AGENT}"
ACTIVE_OVERLAYS=()
for overlay_file in "$OVERLAY_DIR"/*.md; do
    [[ -f "$overlay_file" ]] || continue
    if _interspect_overlay_is_active "$overlay_file"; then
        overlay_id=$(basename "$overlay_file" .md)
        body=$(_interspect_overlay_body "$overlay_file")
        preview=$(echo "$body" | head -c 120)
        ACTIVE_OVERLAYS+=("$overlay_id|$preview")
    fi
done
```

### Select Overlays to Disable

If only one active overlay: confirm disable directly.

If multiple active overlays: present via AskUserQuestion (multi-select):
```
Which overlays do you want to disable for {agent}?

Options:
- "{overlay_id_1} — {preview_1}"
- "{overlay_id_2} — {preview_2}"
- "All overlays" — Disable all {count} active overlays
```

### Disable Selected Overlays

For each selected overlay:
```bash
_interspect_disable_overlay "$AGENT" "$overlay_id"
```

### Blacklist Decision (Overlay)

Same flow as routing override blacklist — ask whether to allow future overlay proposals for this agent.

### Report (Overlay)

```
Disabled {count} overlay(s) for **{agent}**: {overlay_ids joined}.
{if blacklisted: "Pattern blacklisted — interspect won't re-propose overlays for this agent."}
{if not blacklisted: "Interspect may re-propose overlays if new evidence warrants it."}
Canary monitoring closed for disabled overlays.
```
