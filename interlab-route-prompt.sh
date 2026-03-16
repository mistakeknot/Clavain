#!/usr/bin/env bash
# Benchmark: measure route.md prompt size while validating behavioral fidelity.
# Autoresearch target: compress route.md without breaking routing behavior.
set -euo pipefail

FILE="commands/route.md"

if [[ ! -f "$FILE" ]]; then
    echo "ERROR: $FILE not found"
    exit 1
fi

content=$(cat "$FILE")
total_chars=${#content}

# Token approximation: ~3.3 chars/token for this kind of structured markdown+code content
approx_tokens=$(( total_chars * 10 / 33 ))

errors=0
warnings=0

check() {
    local label="$1" pattern="$2"
    if ! grep -qE "$pattern" "$FILE"; then
        echo "FAIL: missing $label"
        errors=$((errors + 1))
    fi
}

check_count() {
    local label="$1" pattern="$2" min="$3"
    local count
    count=$(grep -cE "$pattern" "$FILE" 2>/dev/null || echo 0)
    if [[ "$count" -lt "$min" ]]; then
        echo "FAIL: $label — expected >=$min matches, got $count"
        errors=$((errors + 1))
    fi
}

warn_check() {
    local label="$1" pattern="$2"
    if ! grep -qE "$pattern" "$FILE"; then
        echo "WARN: missing $label"
        warnings=$((warnings + 1))
    fi
}

# === Structural checks ===

# Frontmatter
check "frontmatter-name" "^name: route$"
check "frontmatter-description" "^description:"
check "frontmatter-argument-hint" "^argument-hint:"

# Required steps (the core routing logic)
check "step1-sprint-resume" "sprint.*resume|active sprint|sprint-find-active"
check "step2-parse-args" "[Pp]arse.*[Aa]rg|bead ID.*format|route_mode"
check "step3-discovery" "[Dd]iscovery.*[Ss]can|discovery_scan_beads|discovery mode"
check "step4-classify" "[Cc]lassify.*[Dd]ispatch|[Ff]ast.*[Pp]ath.*[Hh]euristic|4a.*heuristic"

# === Behavioral fidelity: heuristic table ===
# These are the routing rules from Step 4a — if any are missing, routing changes behavior

# Artifact-based heuristics (highest confidence)
check "heuristic-has-plan" "has.*plan.*plan-reviewed|plan.*reviewed.*work"
check "heuristic-bead-action" "bead_action.*execute|continue.*work"
check "heuristic-complexity-1" "complexity.*1.*trivial|trivial.*work"

# Type-based heuristics
check "heuristic-bug" "bug.*work|issue_type.*bug"
check "heuristic-task" "task.*complexity.*3|task.*moderate"
check "heuristic-epic" "epic.*child|child_count.*0.*sprint"
check "heuristic-decision" "decision.*sprint"

# Complexity-based heuristics
check "heuristic-complexity-5" "[Cc]omplexity.*5.*research|research.*sprint"
check "heuristic-complexity-2" "[Cc]omplexity.*=.*2|[Cc]omplexity.*2.*work|[Cc]omplexity.*2.*direct"
check "heuristic-complexity-4" "[Cc]omplexity.*=.*4|[Cc]omplexity.*4.*sprint|[Cc]omplexity.*4.*lifecycle"

# Feature+complexity
check "heuristic-feature-c3" "feature.*complexity.*3.*sprint|feature.*3.*sprint"

# === Key code blocks ===
# These bash snippets must be present (they're executed by the agent)
check "code-sprint-find-active" "sprint-find-active"
check "code-bd-show" "bd show"
check "code-bd-update-claim" "bd update.*--claim"
check "code-classify-complexity" "classify-complexity"
check "code-set-state-claimed" "set-state.*claimed_by|claimed_by.*CLAUDE_SESSION_ID"

# === Dispatch targets ===
check "dispatch-sprint" "/clavain:sprint"
check "dispatch-work" "/clavain:work"
check "dispatch-quality-gates" "/clavain:quality-gates"
check "dispatch-strategy" "/clavain:strategy"
check "dispatch-write-plan" "/clavain:write-plan"

# === Key behavioral patterns ===
check "staleness-check" "stale|already.*implement|possibly_done"
check "claim-failure-handling" "claim.*fail|already claimed|lock.*timeout"
check "haiku-fallback" "haiku|LLM.*[Cc]lassification|4b.*fallback"
check "shedding-not-present" "AskUserQuestion|discovery.*option"

# === Discovery flow ===
check "discovery-scan-beads" "discovery_scan_beads|lib-discovery"
check "discovery-options" "AskUserQuestion|present.*option"
check "discovery-orphan" "orphan|create_bead"
check "discovery-interject" "interject|review_discovery"

# Count heuristic table rows (lines starting with | that contain /clavain:sprint or /clavain:work)
table_rows=$(grep -cE '^\|.*/clavain:(sprint|work)' "$FILE" 2>/dev/null || true)
table_rows=${table_rows:-0}
if [[ "$table_rows" -lt 10 ]]; then
    echo "FAIL: heuristic table has $table_rows rows (need >=10)"
    errors=$((errors + 1))
fi

# Output metrics
echo "METRIC total_chars=$total_chars"
echo "METRIC approx_tokens=$approx_tokens"
echo "METRIC errors=$errors"
echo "METRIC warnings=$warnings"
echo "METRIC heuristic_table_rows=$table_rows"

# Quality gate: errors must be 0
if [[ "$errors" -gt 0 ]]; then
    echo "QUALITY: FAIL ($errors errors)"
else
    echo "QUALITY: PASS"
fi
