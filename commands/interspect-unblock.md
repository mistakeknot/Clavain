---
name: interspect-unblock
description: Remove a pattern from the routing override blacklist
argument-hint: "<agent-name>"
---

# Interspect Unblock

Remove a pattern from the blacklist so interspect can propose it again.

<unblock_target> #$ARGUMENTS </unblock_target>

## Execute

```bash
INTERSPECT_LIB=$(find ~/.claude/plugins/cache -path '*/clavain/*/hooks/lib-interspect.sh' 2>/dev/null | head -1)
[[ -z "$INTERSPECT_LIB" ]] && INTERSPECT_LIB=$(find ~/projects -path '*/os/clavain/hooks/lib-interspect.sh' 2>/dev/null | head -1)
if [[ -z "$INTERSPECT_LIB" ]]; then
    echo "Error: Could not locate hooks/lib-interspect.sh" >&2
    exit 1
fi
source "$INTERSPECT_LIB"
_interspect_ensure_db
DB=$(_interspect_db_path)

if ! _interspect_validate_agent_name "$AGENT"; then
    exit 1
fi
_interspect_unblacklist_pattern "$AGENT"
```

Report: "Unblocked {agent}. Interspect may propose this exclusion again if evidence warrants it." or "No blacklist entry found for {agent}."
