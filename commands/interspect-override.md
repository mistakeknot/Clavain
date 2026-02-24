---
name: interspect-override
description: Manually exclude an agent from flux-drive triage — bypasses evidence requirements
argument-hint: "<agent-name> [reason]"
---

# Interspect Manual Override

Directly exclude an agent from flux-drive reviews without going through the propose/approve flow. Use this when you know an agent is consistently unhelpful for this project.

<override_args> #$ARGUMENTS </override_args>

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
DB=$(_interspect_db_path)
```

## Parse Arguments

Extract agent name and optional reason from `<override_args>`. The first word is the agent name, the rest is the reason.

```bash
AGENT=$(echo "$ARGS" | awk '{print $1}')
REASON=$(echo "$ARGS" | sed 's/^[^ ]* *//')
[[ "$REASON" == "$AGENT" ]] && REASON=""
```

## No Argument: Show Available Agents

If `<override_args>` is empty, present the agent roster for selection:

```bash
# Known flux-drive review agents
AGENTS=(fd-architecture fd-safety fd-correctness fd-quality fd-user-product fd-performance fd-game-design fd-systems fd-decisions fd-people fd-resilience fd-perception)
```

Check which agents are already overridden:

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
FILEPATH="${FLUX_ROUTING_OVERRIDES_PATH:-.claude/routing-overrides.json}"
FULLPATH="${ROOT}/${FILEPATH}"

EXCLUDED=()
if [[ -f "$FULLPATH" ]]; then
    while IFS= read -r a; do
        EXCLUDED+=("$a")
    done < <(jq -r '.overrides[] | select(.action == "exclude") | .agent' "$FULLPATH" 2>/dev/null)
fi
```

Build the available list (agents not already excluded):

```bash
AVAILABLE=()
for a in "${AGENTS[@]}"; do
    local is_excluded=false
    for e in "${EXCLUDED[@]}"; do
        [[ "$a" == "$e" ]] && is_excluded=true && break
    done
    $is_excluded || AVAILABLE+=("$a")
done
```

If all agents are already excluded:
> "All review agents are already excluded. Run `/interspect:status` to review overrides."

Present via **AskUserQuestion**:

```
Which agent do you want to exclude from reviews?

Options (show each available agent as an option):
- "{agent}" for each agent in AVAILABLE
```

## Validate Agent

```bash
if ! _interspect_validate_agent_name "$AGENT"; then
    echo "Invalid agent name: ${AGENT}. Expected format: fd-<name>"
    # Stop here
fi
```

Check if already excluded:

```bash
if _interspect_override_exists "$AGENT"; then
    echo "${AGENT} is already excluded. Run /interspect:status to see overrides."
    # Stop here
fi
```

## Get Reason

If no reason was provided in arguments, ask:

Present via **AskUserQuestion**:
```
Why exclude {AGENT}? (This is recorded for audit trail)

Options:
- "Not relevant to this project" — Project domain doesn't match agent's focus
- "Consistently wrong findings" — Agent produces false positives for this codebase
- "Redundant with another agent" — Another agent covers the same concerns better
```

## Scope Decision

Present via **AskUserQuestion**:
```
Should this override apply globally or only to specific files/domains?

Options:
- "Global" (Recommended) — Exclude {AGENT} from all reviews in this project
- "Scoped to files" — Only exclude when reviewing specific file patterns
- "Scoped to domain" — Only exclude for specific detected domains
```

### If scoped to files:

Ask via **AskUserQuestion**:
```
Enter file glob pattern(s) for this override scope.
Examples: "interverse/**", "*.md", "tests/**"
```

Build scope JSON:
```bash
SCOPE_JSON=$(jq -n --argjson patterns "$FILE_PATTERNS_ARRAY" '{"file_patterns": $patterns}')
```

### If scoped to domain:

```bash
# Detect available domains from flux-drive cache
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
DOMAIN_CACHE="${ROOT}/.clavain/flux-drive/domain-cache.json"
DETECTED_DOMAINS=()
if [[ -f "$DOMAIN_CACHE" ]]; then
    while IFS= read -r d; do
        DETECTED_DOMAINS+=("$d")
    done < <(jq -r '.domains[]' "$DOMAIN_CACHE" 2>/dev/null)
fi
```

Present via **AskUserQuestion** with detected domains as options.

## Apply Override

```bash
_interspect_apply_routing_override "$AGENT" "$REASON" '[]' "human"
```

Note: `evidence_ids` is empty (`[]`) for manual overrides. `created_by` is `"human"`.

## Report

```
Excluded **{AGENT}** from flux-drive reviews.
- Reason: {REASON}
- Scope: {global | file patterns | domain}
- Created by: human (manual override)

Canary monitoring active. Run `/interspect:status` after 5-10 sessions to verify.
To undo: `/interspect:revert {AGENT}`

> Manual overrides bypass evidence requirements. Interspect will still collect evidence for this agent — if the evidence later shows the agent is useful, `/interspect:status` will note the discrepancy.
```
