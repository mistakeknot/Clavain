#!/usr/bin/env bash
# One-time migration: existing sprint beads → ic runs
# Idempotent: skips beads that already have an ic_run_id.
# Usage: bash os/clavain/scripts/migrate-sprints-to-ic.sh [--dry-run]
set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

if ! command -v bd &>/dev/null; then
    echo "Error: bd (beads) not found" >&2
    exit 1
fi

if ! command -v ic &>/dev/null; then
    echo "Error: ic (intercore) not found" >&2
    exit 1
fi

if ! command -v jq &>/dev/null; then
    echo "Error: jq not found" >&2
    exit 1
fi

MIGRATED=0
SKIPPED=0
ERRORS=0

echo "=== Sprint Migration: beads → ic runs ==="
echo "Dry run: $DRY_RUN"
echo ""

# Find all in-progress beads
ip_list=$(bd list --status=in_progress --json 2>/dev/null) || ip_list="[]"
count=$(echo "$ip_list" | jq 'length' 2>/dev/null) || count=0

for (( i=0; i<count; i++ )); do
    bead_id=$(echo "$ip_list" | jq -r ".[$i].id // empty")
    [[ -z "$bead_id" ]] && continue

    # Check if it's a sprint
    is_sprint=$(bd state "$bead_id" sprint 2>/dev/null) || is_sprint=""
    [[ "$is_sprint" != "true" ]] && continue

    title=$(echo "$ip_list" | jq -r ".[$i].title // \"Untitled\"")

    # Check if already migrated
    existing_run=$(bd state "$bead_id" ic_run_id 2>/dev/null) || existing_run=""
    if [[ -n "$existing_run" && "$existing_run" != "null" ]]; then
        echo "SKIP $bead_id — already has ic_run_id=$existing_run"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    # Read current phase
    phase=$(bd state "$bead_id" phase 2>/dev/null) || phase="brainstorm"
    [[ -z "$phase" || "$phase" == "null" ]] && phase="brainstorm"

    echo "MIGRATE $bead_id — $title (phase: $phase)"

    if [[ "$DRY_RUN" == "true" ]]; then
        MIGRATED=$((MIGRATED + 1))
        continue
    fi

    # Crash recovery: cancel any orphaned ic runs for this bead from a previous failed migration
    existing_json=$(ic run list --active --scope="$bead_id" --json 2>/dev/null) || existing_json="[]"
    orphan_count=$(echo "$existing_json" | jq 'length' 2>/dev/null) || orphan_count=0
    if [[ "$orphan_count" -gt 0 ]]; then
        echo "  WARN: Found $orphan_count orphaned ic run(s) for $bead_id, cancelling"
        orphan_ids=""
        orphan_ids=$(echo "$existing_json" | jq -r '.[].id' 2>/dev/null) || orphan_ids=""
        while read -r orphan_id; do
            [[ -z "$orphan_id" ]] && continue
            ic run cancel "$orphan_id" 2>/dev/null || true
        done <<< "$orphan_ids"
    fi

    # Create ic run (no --phases: sprint chain matches DefaultPhaseChain)
    run_id=$(ic run create --project="$(pwd)" --goal="$title" --scope-id="$bead_id" 2>/dev/null) || run_id=""
    if [[ -z "$run_id" ]]; then
        echo "  ERROR: ic run create failed"
        ERRORS=$((ERRORS + 1))
        continue
    fi

    # Align ic run to match current phase using skip (NOT advance).
    # CRITICAL: ic run advance triggers SpawnHandler on "executing" phase,
    # which would launch real agents for historical sprints. ic run skip
    # writes to the audit trail without firing phase callbacks.
    # (Per correctness review Finding 5)
    current_ic_phase="brainstorm"
    phases_array=("brainstorm" "brainstorm-reviewed" "strategized" "planned" "plan-reviewed" "executing" "shipping" "done")
    skip_failed=false
    for p in "${phases_array[@]}"; do
        [[ "$p" == "$phase" ]] && break
        [[ "$p" == "$current_ic_phase" ]] || continue
        ic run skip "$run_id" "$p" --reason="historical-migration" 2>/dev/null || { skip_failed=true; break; }
        # Find the next phase in the array (bounds-checked)
        for (( j=0; j<${#phases_array[@]}; j++ )); do
            if [[ "${phases_array[$j]}" == "$p" ]]; then
                if (( j+1 < ${#phases_array[@]} )); then
                    current_ic_phase="${phases_array[$((j+1))]}"
                else
                    current_ic_phase="done"
                fi
                break
            fi
        done
    done

    # Verify phase alignment BEFORE writing ic_run_id to bead.
    # If alignment failed, cancel the run — don't leave a misaligned run linked.
    # (Per safety review Finding 3 + architecture review Finding 1d)
    actual_ic_phase=$(ic run phase "$run_id" 2>/dev/null) || actual_ic_phase=""
    if [[ "$actual_ic_phase" != "$phase" ]] || [[ "$skip_failed" == "true" ]]; then
        echo "  ERROR: Phase alignment failed (ic at '${actual_ic_phase}', target: '$phase')"
        ic run cancel "$run_id" 2>/dev/null || true
        ERRORS=$((ERRORS + 1))
        continue
    fi

    # Store run_id on bead — only after verified alignment
    bd set-state "$bead_id" "ic_run_id=$run_id" 2>/dev/null || true

    # Migrate artifacts
    artifacts_json=$(bd state "$bead_id" sprint_artifacts 2>/dev/null) || artifacts_json="{}"
    echo "$artifacts_json" | jq empty 2>/dev/null || artifacts_json="{}"
    if [[ "$artifacts_json" != "{}" ]]; then
        echo "$artifacts_json" | jq -r 'to_entries[] | "\(.key)\t\(.value)"' | \
            while IFS=$'\t' read -r art_type art_path; do
                ic run artifact add "$run_id" --phase="$phase" --path="$art_path" --type="$art_type" 2>/dev/null || true
            done
    fi

    echo "  → Created run $run_id (phase: $current_ic_phase)"
    MIGRATED=$((MIGRATED + 1))
done

echo ""
echo "=== Results ==="
echo "Migrated: $MIGRATED"
echo "Skipped:  $SKIPPED"
echo "Errors:   $ERRORS"

# Exit non-zero if any errors occurred so callers can detect partial failure
if [[ "$ERRORS" -gt 0 ]]; then
    echo "WARNING: $ERRORS sprint(s) failed migration. Re-run after fixing." >&2
    exit 1
fi
