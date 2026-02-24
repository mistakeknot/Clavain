---
name: interspect-enable-autonomy
description: Enable autonomous mode — low/medium-risk overrides auto-apply with canary monitoring
argument-hint: ""
---

# Interspect: Enable Autonomy

Enable autonomous mode for Interspect. When enabled, routing overrides (Type 2) that meet all confidence thresholds will auto-apply with canary monitoring instead of requiring explicit `/interspect:approve`.

Prompt tuning overlays (Type 3) always require propose mode regardless of this flag.

## Locate Library

```bash
INTERSPECT_LIB=$(find ~/.claude/plugins/cache -path '*/clavain/*/hooks/lib-interspect.sh' 2>/dev/null | head -1)
[[ -z "$INTERSPECT_LIB" ]] && INTERSPECT_LIB=$(find ~/projects -path '*/os/clavain/hooks/lib-interspect.sh' 2>/dev/null | head -1)
if [[ -z "$INTERSPECT_LIB" ]]; then
    echo "Error: Could not locate hooks/lib-interspect.sh" >&2
    exit 1
fi
source "$INTERSPECT_LIB"
_interspect_ensure_db
```

## Check Current State

```bash
_interspect_load_confidence
CURRENT_STATE="${_INTERSPECT_AUTONOMY:-false}"
```

If already enabled:
> "Autonomous mode is already enabled. Routing overrides auto-apply with canary monitoring. Run `/interspect:disable-autonomy` to switch back to propose mode."

## Confirm

Present via **AskUserQuestion**:

```
Enable autonomous mode for Interspect?

When enabled:
- Routing overrides (agent exclusions) auto-apply when evidence thresholds are met
- Each auto-applied override gets canary monitoring (20 uses / 14 days)
- Circuit breaker: if an override is reverted 3 times in 30 days, that agent reverts to propose mode
- Prompt tuning overlays always require explicit approval (never auto-applied)

Options:
- "Enable" (Recommended) — Trust the evidence pipeline
- "Cancel" — Stay in propose mode (default)
```

## Apply

```bash
_interspect_set_autonomy "true"
```

## Report

```
Autonomous mode **enabled**.

What changes:
- `/interspect:propose` will auto-apply routing overrides that meet all confidence thresholds
- Canary monitoring protects against quality regression
- Circuit breaker prevents repeated bad overrides
- Prompt tuning overlays still require `/interspect:approve`

Safety controls:
- Run `/interspect:status` to monitor active canaries
- Run `/interspect:revert <agent>` to undo any override
- Run `/interspect:disable-autonomy` to return to propose mode
```
