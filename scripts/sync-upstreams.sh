#!/usr/bin/env bash
set -euo pipefail

# DEPRECATED: This script has been replaced by the Python package clavain_sync.
# Use: python3 -m clavain_sync sync [--dry-run] [--auto] [--upstream NAME]
# Or:  pull-upstreams.sh --sync (defaults to Python version)
# To use this legacy version: pull-upstreams.sh --sync --legacy

# sync-upstreams.sh — Smart upstream sync with three-way classification and
# AI-assisted conflict resolution.
#
# Uses lastSyncedCommit as ancestor to classify files:
#   COPY       — content identical (namespace-replaced upstream matches local)
#   AUTO       — only upstream changed, safe to auto-apply
#   KEEP-LOCAL — only local changed, safe to preserve
#   CONFLICT   — both changed, uses AI analysis for resolution
#   SKIP       — protected, deleted, or absent locally
#   REVIEW     — new upstream file, blocklist detected, or unexpected divergence
#
# Usage:
#   ./scripts/sync-upstreams.sh                              # Interactive
#   ./scripts/sync-upstreams.sh --dry-run                    # Preview only
#   ./scripts/sync-upstreams.sh --auto                       # Non-interactive (CI)
#   ./scripts/sync-upstreams.sh --auto --report              # CI with report
#   ./scripts/sync-upstreams.sh --auto --no-ai               # CI without AI
#   ./scripts/sync-upstreams.sh --upstream beads             # Single upstream

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
UPSTREAMS_JSON="$PROJECT_ROOT/upstreams.json"

# Default upstreams dir; CI uses .upstream-work/ relative to project root
if [[ -d "$PROJECT_ROOT/.upstream-work" ]]; then
  UPSTREAMS_DIR="$PROJECT_ROOT/.upstream-work"
else
  UPSTREAMS_DIR="/root/projects/upstreams"
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Parse arguments
MODE="interactive"
FILTER_UPSTREAM=""
USE_AI=true
GENERATE_REPORT=false
REPORT_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)  MODE="dry-run"; shift ;;
    --auto)     MODE="auto"; shift ;;
    --upstream) FILTER_UPSTREAM="$2"; shift 2 ;;
    --no-ai)    USE_AI=false; shift ;;
    --report)
      GENERATE_REPORT=true
      if [[ $# -gt 1 ]] && [[ "$2" != --* ]]; then
        REPORT_FILE="$2"; shift 2
      else
        shift
      fi
      ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--auto] [--upstream NAME] [--no-ai] [--report [FILE]]"
      echo ""
      echo "Modes:"
      echo "  (default)    Interactive — prompts for divergent files"
      echo "  --dry-run    Preview classification, no file changes"
      echo "  --auto       Non-interactive — applies COPY/AUTO, AI-resolves conflicts"
      echo "  --upstream   Sync a single upstream by name"
      echo ""
      echo "Options:"
      echo "  --no-ai      Disable AI conflict analysis (skip conflicts in auto, raw diff in interactive)"
      echo "  --report     Generate markdown sync report (optionally to FILE, otherwise stdout)"
      exit 0
      ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# Validate prerequisites
if [[ ! -f "$UPSTREAMS_JSON" ]]; then
  echo "ERROR: $UPSTREAMS_JSON not found."
  exit 1
fi

if [[ ! -d "$UPSTREAMS_DIR" ]]; then
  echo "ERROR: $UPSTREAMS_DIR does not exist."
  echo "Run scripts/clone-upstreams.sh first, or ensure .upstream-work/ exists (CI)."
  exit 1
fi

# ─────────────────────────────────────────────
# Load syncConfig from upstreams.json via Python
# ─────────────────────────────────────────────

load_sync_config() {
  python3 - "$UPSTREAMS_JSON" <<'PY'
import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)

cfg = data.get("syncConfig", {})

# Print protected files
for p in cfg.get("protectedFiles", []):
    print(f"PROTECTED:{p}")

# Print deleted files
for d in cfg.get("deletedLocally", []):
    print(f"DELETED:{d}")

# Print namespace replacements
for old, new in cfg.get("namespaceReplacements", {}).items():
    print(f"NSREPLACE:{old}\t{new}")

# Print content blocklist
for term in cfg.get("contentBlocklist", []):
    print(f"BLOCKLIST:{term}")
PY
}

declare -A PROTECTED_FILES
declare -A DELETED_FILES
declare -A NS_REPLACEMENTS
BLOCKLIST_TERMS=()

while IFS= read -r line; do
  case "$line" in
    PROTECTED:*) PROTECTED_FILES["${line#PROTECTED:}"]=1 ;;
    DELETED:*)   DELETED_FILES["${line#DELETED:}"]=1 ;;
    NSREPLACE:*)
      payload="${line#NSREPLACE:}"
      old="${payload%%	*}"
      new="${payload#*	}"
      NS_REPLACEMENTS["$old"]="$new"
      ;;
    BLOCKLIST:*) BLOCKLIST_TERMS+=("${line#BLOCKLIST:}") ;;
  esac
done < <(load_sync_config)

# ─────────────────────────────────────────────
# Helper: apply namespace replacements to text
# ─────────────────────────────────────────────

apply_namespace_replacements() {
  local text="$1"
  for old in "${!NS_REPLACEMENTS[@]}"; do
    local new="${NS_REPLACEMENTS[$old]}"
    text="${text//"$old"/"$new"}"
  done
  echo "$text"
}

apply_namespace_replacements_to_file() {
  local file="$1"
  for old in "${!NS_REPLACEMENTS[@]}"; do
    local new="${NS_REPLACEMENTS[$old]}"
    # Use sed for in-place replacement (GNU sed)
    sed -i "s|${old}|${new}|g" "$file"
  done
}

# ─────────────────────────────────────────────
# Helper: retrieve file content at lastSyncedCommit
# ─────────────────────────────────────────────

get_ancestor_content() {
  local clone_dir="$1" last_commit="$2" base_path="$3" filepath="$4"
  local full_path="$filepath"
  [[ -n "$base_path" ]] && full_path="$base_path/$filepath"
  git -C "$clone_dir" show "$last_commit:$full_path" 2>/dev/null || true
}

# ─────────────────────────────────────────────
# Helper: expand glob mappings from fileMap
# ─────────────────────────────────────────────

# Given a fileMap entry like "references/*" -> "skills/foo/references/*",
# expand against actual files in the upstream directory and return pairs.
# Output: lines of "upstream_relative_path\tlocal_path"
expand_file_map() {
  local upstream_dir="$1" base_path="$2"
  # Read the fileMap for this upstream via Python
  python3 - "$UPSTREAMS_JSON" "$upstream_dir" "$base_path" <<'PY'
import json, sys, glob, os

upstreams_json = sys.argv[1]
upstream_name = sys.argv[2]  # name of the upstream
base_path = sys.argv[3]

with open(upstreams_json) as f:
    data = json.load(f)

upstream = None
for u in data["upstreams"]:
    if u["name"] == upstream_name:
        upstream = u
        break

if not upstream:
    sys.exit(0)

file_map = upstream.get("fileMap", {})
for src_pattern, dst_pattern in file_map.items():
    print(f"{src_pattern}\t{dst_pattern}")
PY
}

# ─────────────────────────────────────────────
# Helper: resolve a changed upstream file to its local path
# Returns empty string if not mapped.
# ─────────────────────────────────────────────

resolve_local_path() {
  local upstream_name="$1" changed_file="$2" base_path="$3" clone_dir="$4"
  python3 - "$UPSTREAMS_JSON" "$upstream_name" "$changed_file" "$base_path" "$clone_dir" <<'PY'
import json, sys, os, fnmatch

upstreams_json = sys.argv[1]
upstream_name = sys.argv[2]
changed_file = sys.argv[3]  # relative to basePath (already stripped)
base_path = sys.argv[4]
clone_dir = sys.argv[5]

with open(upstreams_json) as f:
    data = json.load(f)

upstream = None
for u in data["upstreams"]:
    if u["name"] == upstream_name:
        upstream = u
        break

if not upstream:
    sys.exit(0)

file_map = upstream.get("fileMap", {})

# Try exact match first
if changed_file in file_map:
    print(file_map[changed_file])
    sys.exit(0)

# Try glob match
for src_pattern, dst_pattern in file_map.items():
    if "*" not in src_pattern and "?" not in src_pattern:
        continue
    if fnmatch.fnmatch(changed_file, src_pattern):
        # Replace the glob part: e.g., "references/*" matching "references/foo.md"
        # with dst "skills/x/references/*" -> "skills/x/references/foo.md"
        src_prefix = src_pattern.split("*")[0]
        dst_prefix = dst_pattern.split("*")[0]
        suffix = changed_file[len(src_prefix):]
        print(dst_prefix + suffix)
        sys.exit(0)

# No mapping found
PY
}

# ─────────────────────────────────────────────
# Helper: check content for blocklist terms
# Returns 0 (true) if blocklist term found
# ─────────────────────────────────────────────

content_has_blocklist() {
  local content="$1"
  for term in "${BLOCKLIST_TERMS[@]}"; do
    if [[ "$content" == *"$term"* ]]; then
      echo "$term"
      return 0
    fi
  done
  return 1
}

# ─────────────────────────────────────────────
# Helper: classify a file using three-way comparison
# Returns: SKIP:reason, COPY, AUTO, KEEP-LOCAL, CONFLICT, REVIEW:reason
# ─────────────────────────────────────────────

classify_file() {
  local local_path="$1" upstream_file="$2" clone_dir="$3" last_commit="$4" base_path="$5" filepath="$6"
  local local_full="$PROJECT_ROOT/$local_path"

  # Check protected
  if [[ -n "${PROTECTED_FILES[$local_path]+x}" ]]; then
    echo "SKIP:protected"
    return
  fi

  # Check deleted locally
  if [[ -n "${DELETED_FILES[$local_path]+x}" ]]; then
    echo "SKIP:deleted-locally"
    return
  fi

  # If local file doesn't exist, it may have been intentionally removed
  if [[ ! -f "$local_full" ]]; then
    echo "SKIP:not-present-locally"
    return
  fi

  # Compare content: apply namespace replacements to upstream, then diff
  local upstream_content upstream_transformed local_content
  upstream_content=$(cat "$upstream_file")
  upstream_transformed=$(apply_namespace_replacements "$upstream_content")
  local_content=$(cat "$local_full")

  # If content matches after namespace replacement, it's a safe copy
  if [[ "$upstream_transformed" == "$local_content" ]]; then
    echo "COPY"
    return
  fi

  # Three-way classification: get ancestor content at lastSyncedCommit
  local ancestor_raw
  ancestor_raw=$(get_ancestor_content "$clone_dir" "$last_commit" "$base_path" "$filepath")

  # If ancestor is empty, this is a new upstream file we haven't seen before
  if [[ -z "$ancestor_raw" ]]; then
    echo "REVIEW:new-upstream-file"
    return
  fi

  local ancestor_transformed
  ancestor_transformed=$(apply_namespace_replacements "$ancestor_raw")

  # Determine who changed what
  local upstream_changed=false local_changed=false
  if [[ "$upstream_transformed" != "$ancestor_transformed" ]]; then
    upstream_changed=true
  fi
  if [[ "$local_content" != "$ancestor_transformed" ]]; then
    local_changed=true
  fi

  if [[ "$upstream_changed" == true ]] && [[ "$local_changed" == false ]]; then
    # Only upstream changed — check for blocklist contamination
    local bad_term
    if bad_term=$(content_has_blocklist "$upstream_transformed"); then
      echo "REVIEW:blocklist-in-upstream:$bad_term"
      return
    fi
    echo "AUTO"
    return
  fi

  if [[ "$upstream_changed" == false ]] && [[ "$local_changed" == true ]]; then
    echo "KEEP-LOCAL"
    return
  fi

  if [[ "$upstream_changed" == true ]] && [[ "$local_changed" == true ]]; then
    echo "CONFLICT"
    return
  fi

  # Both unchanged but content differs (shouldn't happen, but be safe)
  echo "REVIEW:unexpected-divergence"
}

# ─────────────────────────────────────────────
# Helper: AI-powered conflict analysis
# Invokes claude -p with structured JSON output
# ─────────────────────────────────────────────

analyze_conflict() {
  local local_path="$1" upstream_file="$2" clone_dir="$3" last_commit="$4" base_path="$5" filepath="$6"
  local prompt_file ancestor_file tmp_upstream

  prompt_file=$(mktemp)
  ancestor_file=$(mktemp)
  tmp_upstream=$(mktemp)

  # Prepare ancestor content (with namespace replacement)
  get_ancestor_content "$clone_dir" "$last_commit" "$base_path" "$filepath" > "$ancestor_file"
  local ancestor_transformed
  ancestor_transformed=$(apply_namespace_replacements "$(cat "$ancestor_file")")
  echo "$ancestor_transformed" > "$ancestor_file"

  # Prepare upstream content (with namespace replacement)
  cp "$upstream_file" "$tmp_upstream"
  apply_namespace_replacements_to_file "$tmp_upstream"

  local blocklist_str="${BLOCKLIST_TERMS[*]}"

  # Build analysis prompt
  cat > "$prompt_file" <<PROMPT
You are analyzing a file conflict during an upstream sync for the Clavain plugin.
Three versions exist: ancestor (at last sync), local (Clavain's version), upstream (new).

Context:
- Clavain is a general-purpose engineering plugin (no Rails/Ruby/Every.to)
- Namespace: /clavain: (not /compound-engineering: or /workflows:)
- Blocklist terms that should NOT appear: $blocklist_str

File: $local_path

ANCESTOR (at last sync):
$(cat "$ancestor_file")

LOCAL (Clavain's current version):
$(cat "$PROJECT_ROOT/$local_path")

UPSTREAM (new version, after namespace replacement):
$(cat "$tmp_upstream")

Analyze: What did each side change? Are the changes orthogonal or conflicting?
Should Clavain accept upstream, keep local, or does this need human review?
Check for blocklist terms in the upstream changes.
PROMPT

  local schema='{"type":"object","properties":{"decision":{"type":"string","enum":["accept_upstream","keep_local","needs_human"]},"rationale":{"type":"string"},"blocklist_found":{"type":"array","items":{"type":"string"}},"risk":{"type":"string","enum":["low","medium","high"]}},"required":["decision","rationale","risk"]}'

  local result
  result=$(claude -p --output-format json --json-schema "$schema" \
      --model haiku \
      --max-turns 1 \
      < "$prompt_file" 2>/dev/null) || result='{"decision":"needs_human","rationale":"AI analysis failed","risk":"high"}'

  rm -f "$prompt_file" "$ancestor_file" "$tmp_upstream"
  echo "$result"
}

# ─────────────────────────────────────────────
# Helper: interactive conflict display with AI recommendation
# ─────────────────────────────────────────────

handle_conflict_interactive() {
  local local_path="$1" upstream_file="$2" clone_dir="$3" last_commit="$4" base_path="$5" filepath="$6" ai_json="$7"
  local local_full="$PROJECT_ROOT/$local_path"

  # All UI output goes to stderr so stdout is clean for the return value
  # Prepare namespace-replaced upstream for display
  local tmp_upstream tmp_ancestor
  tmp_upstream=$(mktemp)
  tmp_ancestor=$(mktemp)
  cp "$upstream_file" "$tmp_upstream"
  apply_namespace_replacements_to_file "$tmp_upstream"

  # Prepare ancestor for three-way view
  get_ancestor_content "$clone_dir" "$last_commit" "$base_path" "$filepath" > "$tmp_ancestor"
  local ancestor_transformed
  ancestor_transformed=$(apply_namespace_replacements "$(cat "$tmp_ancestor")")
  echo "$ancestor_transformed" > "$tmp_ancestor"

  echo "" >&2

  # Show AI recommendation if available
  local ai_decision=""
  if [[ -n "$ai_json" ]] && [[ "$ai_json" != "null" ]]; then
    local ai_rationale ai_risk
    ai_decision=$(echo "$ai_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('decision','needs_human'))" 2>/dev/null || echo "needs_human")
    ai_rationale=$(echo "$ai_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('rationale',''))" 2>/dev/null || echo "")
    ai_risk=$(echo "$ai_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('risk','high'))" 2>/dev/null || echo "high")

    local rec_color="$YELLOW"
    [[ "$ai_risk" == "low" ]] && rec_color="$GREEN"
    [[ "$ai_risk" == "high" ]] && rec_color="$RED"

    echo -e "  ${BOLD}AI Recommendation:${NC} ${rec_color}$ai_decision${NC} (risk: $ai_risk)" >&2
    echo -e "  ${ai_rationale}" >&2
    echo "" >&2
  fi

  # Show diff: local vs upstream (after namespace replacement)
  echo -e "  ${BOLD}Local vs upstream (after namespace replacement):${NC}" >&2
  diff --color=always "$local_full" "$tmp_upstream" | head -80 >&2 || true
  echo "" >&2

  while true; do
    if [[ -n "$ai_json" ]] && [[ "$ai_json" != "null" ]]; then
      echo -en "  ${BOLD}(r)${NC}ecommended [$ai_decision] | ${BOLD}(a)${NC}ccept upstream | ${BOLD}(k)${NC}eep local | ${BOLD}(3)${NC}-way view | ${BOLD}(s)${NC}kip: " >&2
    else
      echo -en "  ${BOLD}(a)${NC}ccept upstream | ${BOLD}(k)${NC}eep local | ${BOLD}(3)${NC}-way view | ${BOLD}(s)${NC}kip: " >&2
    fi
    read -r choice </dev/tty
    case "$choice" in
      r|recommended)
        if [[ "$ai_decision" == "accept_upstream" ]]; then
          cp "$tmp_upstream" "$local_full"
          echo -e "  ${GREEN}→ Accepted upstream (AI recommended)${NC}" >&2
        elif [[ "$ai_decision" == "keep_local" ]]; then
          echo -e "  ${YELLOW}→ Kept local (AI recommended)${NC}" >&2
        else
          echo -e "  ${YELLOW}→ Skipped (AI unsure — needs human)${NC}" >&2
        fi
        rm -f "$tmp_upstream" "$tmp_ancestor"
        echo "$ai_decision"
        return
        ;;
      a|accept)
        cp "$tmp_upstream" "$local_full"
        echo -e "  ${GREEN}→ Accepted upstream${NC}" >&2
        rm -f "$tmp_upstream" "$tmp_ancestor"
        echo "accept_upstream"
        return
        ;;
      k|keep)
        echo -e "  ${YELLOW}→ Kept local${NC}" >&2
        rm -f "$tmp_upstream" "$tmp_ancestor"
        echo "keep_local"
        return
        ;;
      3|three-way)
        echo "" >&2
        echo -e "  ${BOLD}Ancestor → Local changes:${NC}" >&2
        diff --color=always "$tmp_ancestor" "$local_full" | head -60 >&2 || true
        echo "" >&2
        echo -e "  ${BOLD}Ancestor → Upstream changes:${NC}" >&2
        diff --color=always "$tmp_ancestor" "$tmp_upstream" | head -60 >&2 || true
        echo "" >&2
        ;;
      s|skip)
        echo -e "  ${YELLOW}→ Skipped${NC}" >&2
        rm -f "$tmp_upstream" "$tmp_ancestor"
        echo "skip"
        return
        ;;
      *)
        if [[ -n "$ai_json" ]] && [[ "$ai_json" != "null" ]]; then
          echo "  Invalid choice. Use r/a/k/3/s." >&2
        else
          echo "  Invalid choice. Use a/k/3/s." >&2
        fi
        ;;
    esac
  done
}

# ─────────────────────────────────────────────
# Report data collection
# ─────────────────────────────────────────────

declare -a REPORT_ENTRIES=()
declare -a AI_DECISIONS=()

add_report_entry() {
  local file="$1" classification="$2"
  REPORT_ENTRIES+=("$file|$classification")
}

add_ai_decision() {
  local file="$1" decision="$2" risk="$3" rationale="$4"
  AI_DECISIONS+=("$file|$decision|$risk|$rationale")
}

generate_report() {
  local copy_n=0 auto_n=0 keep_n=0 conflict_n=0 skip_n=0 review_n=0 ai_resolved_n=0

  if [[ ${#REPORT_ENTRIES[@]} -gt 0 ]]; then
    for entry in "${REPORT_ENTRIES[@]}"; do
      local cls="${entry#*|}"
      case "$cls" in
        COPY) copy_n=$((copy_n + 1)) ;;
        AUTO) auto_n=$((auto_n + 1)) ;;
        KEEP-LOCAL) keep_n=$((keep_n + 1)) ;;
        CONFLICT*) conflict_n=$((conflict_n + 1)) ;;
        SKIP*) skip_n=$((skip_n + 1)) ;;
        REVIEW*) review_n=$((review_n + 1)) ;;
      esac
    done
  fi

  if [[ ${#AI_DECISIONS[@]} -gt 0 ]]; then
    for entry in "${AI_DECISIONS[@]}"; do
      local dec
      dec=$(echo "$entry" | cut -d'|' -f2)
      [[ "$dec" != "needs_human" ]] && ai_resolved_n=$((ai_resolved_n + 1))
    done
  fi

  echo ""
  echo "═══ Clavain Upstream Sync Report ═══"
  echo ""
  echo "## Classification Summary"
  echo "| Category    | Count | Description                      |"
  echo "|-------------|-------|----------------------------------|"
  echo "| COPY        | $copy_n     | Content identical                 |"
  echo "| AUTO        | $auto_n     | Upstream-only, auto-applied       |"
  echo "| KEEP-LOCAL  | $keep_n     | Local-only, preserved             |"
  echo "| CONFLICT    | $conflict_n     | Both changed — $ai_resolved_n AI-resolved       |"
  echo "| SKIP        | $skip_n    | Protected/deleted                 |"
  echo "| REVIEW      | $review_n     | Needs manual review               |"
  echo ""

  if [[ ${#AI_DECISIONS[@]} -gt 0 ]]; then
    echo "## AI Decisions"
    for entry in "${AI_DECISIONS[@]}"; do
      local file dec risk rationale
      file=$(echo "$entry" | cut -d'|' -f1)
      dec=$(echo "$entry" | cut -d'|' -f2)
      risk=$(echo "$entry" | cut -d'|' -f3)
      rationale=$(echo "$entry" | cut -d'|' -f4-)
      echo "- $file: **$dec** (risk: $risk)"
      [[ -n "$rationale" ]] && echo "  \"$rationale\""
    done
    echo ""
  fi
}

# ─────────────────────────────────────────────
# Main sync loop
# ─────────────────────────────────────────────

echo ""
echo -e "${BOLD}═══ Clavain Upstream Sync ═══${NC}"
echo -e "Mode: ${CYAN}$MODE${NC}  AI: ${USE_AI}  Report: ${GENERATE_REPORT}"
echo -e "Upstreams dir: $UPSTREAMS_DIR"
echo ""

# Counters
total_skipped=0
total_copied=0
total_auto=0
total_keep=0
total_conflicts=0
total_ai_resolved=0
total_reviewed=0
total_errors=0
modified_files=()

# Read upstreams list
upstream_names=()
while IFS= read -r name; do
  upstream_names+=("$name")
done < <(python3 -c "
import json
with open('$UPSTREAMS_JSON') as f:
    data = json.load(f)
for u in data['upstreams']:
    print(u['name'])
")

for upstream_name in "${upstream_names[@]}"; do
  # Filter if --upstream specified
  if [[ -n "$FILTER_UPSTREAM" ]] && [[ "$upstream_name" != "$FILTER_UPSTREAM" ]]; then
    continue
  fi

  echo -e "${BOLD}─── $upstream_name ───${NC}"

  # Read upstream config (pipe-delimited to handle empty basePath)
  IFS='|' read -r branch base_path last_commit < <(python3 -c "
import json
with open('$UPSTREAMS_JSON') as f:
    data = json.load(f)
for u in data['upstreams']:
    if u['name'] == '$upstream_name':
        bp = u.get('basePath') or '_NONE_'
        print(u.get('branch','main') + '|' + bp + '|' + u['lastSyncedCommit'])
        break
")
  [[ "$base_path" == "_NONE_" ]] && base_path=""

  clone_dir="$UPSTREAMS_DIR/$upstream_name"
  if [[ ! -d "$clone_dir/.git" ]]; then
    echo -e "  ${RED}Clone not found at $clone_dir${NC}"
    total_errors=$((total_errors + 1))
    echo ""
    continue
  fi

  # Fetch and reset to latest
  git -C "$clone_dir" fetch origin --quiet 2>/dev/null || true
  git -C "$clone_dir" reset --hard "origin/$branch" --quiet 2>/dev/null || true

  head_commit=$(git -C "$clone_dir" rev-parse HEAD)
  head_short=$(git -C "$clone_dir" rev-parse --short HEAD)

  if [[ "$head_commit" == "$last_commit" ]]; then
    echo -e "  ${GREEN}No new commits (HEAD: $head_short)${NC}"
    echo ""
    continue
  fi

  # Verify last synced commit is reachable
  if ! git -C "$clone_dir" cat-file -e "$last_commit" 2>/dev/null; then
    echo -e "  ${RED}Last synced commit $last_commit not reachable — skipping${NC}"
    total_errors=$((total_errors + 1))
    echo ""
    continue
  fi

  new_count=$(git -C "$clone_dir" rev-list --count "${last_commit}..HEAD")
  echo -e "  ${CYAN}$new_count new commits${NC} (${last_commit:0:7} → $head_short)"

  # Get changed files since last sync
  diff_path="."
  if [[ -n "$base_path" ]]; then
    diff_path="$base_path"
  fi

  changed_files=()
  while IFS=$'\t' read -r status filepath; do
    [[ -z "$filepath" ]] && continue
    # Strip basePath prefix if present
    if [[ -n "$base_path" ]] && [[ "$filepath" == "$base_path/"* ]]; then
      filepath="${filepath#"$base_path/"}"
    fi
    changed_files+=("$status:$filepath")
  done < <(git -C "$clone_dir" diff --name-status "$last_commit" HEAD -- "$diff_path" 2>/dev/null || true)

  if [[ ${#changed_files[@]} -eq 0 ]]; then
    echo -e "  No mapped files changed"
    # Still update commit hash
    if [[ "$MODE" != "dry-run" ]]; then
      python3 -c "
import json
with open('$UPSTREAMS_JSON', 'r+') as f:
    data = json.load(f)
    for u in data['upstreams']:
        if u['name'] == '$upstream_name':
            u['lastSyncedCommit'] = '$head_commit'
    f.seek(0); json.dump(data, f, indent=2); f.write('\n'); f.truncate()
"
    fi
    echo ""
    continue
  fi

  skip_count=0
  copy_count=0
  auto_count=0
  keep_count=0
  conflict_count=0
  review_count=0

  for entry in "${changed_files[@]}"; do
    status="${entry%%:*}"
    filepath="${entry#*:}"

    # Skip deleted upstream files (just log)
    if [[ "$status" == "D" ]]; then
      continue
    fi

    # Resolve to local path via fileMap
    local_path=$(resolve_local_path "$upstream_name" "$filepath" "$base_path" "$clone_dir")
    if [[ -z "$local_path" ]]; then
      # Not in fileMap — skip silently
      continue
    fi

    # Build full upstream file path
    upstream_file="$clone_dir"
    if [[ -n "$base_path" ]]; then
      upstream_file="$upstream_file/$base_path/$filepath"
    else
      upstream_file="$upstream_file/$filepath"
    fi

    if [[ ! -f "$upstream_file" ]]; then
      continue
    fi

    # Classify (three-way)
    classification=$(classify_file "$local_path" "$upstream_file" "$clone_dir" "$last_commit" "$base_path" "$filepath")

    case "$classification" in
      SKIP:*)
        reason="${classification#SKIP:}"
        printf "  ${YELLOW}SKIP${NC}  %-50s (%s)\n" "$local_path" "$reason"
        skip_count=$((skip_count + 1))
        total_skipped=$((total_skipped + 1))
        add_report_entry "$local_path" "$classification"
        ;;

      COPY)
        printf "  ${GREEN}COPY${NC}  %s\n" "$local_path"
        copy_count=$((copy_count + 1))
        total_copied=$((total_copied + 1))
        add_report_entry "$local_path" "COPY"

        if [[ "$MODE" != "dry-run" ]]; then
          mkdir -p "$(dirname "$PROJECT_ROOT/$local_path")"
          cp "$upstream_file" "$PROJECT_ROOT/$local_path"
          apply_namespace_replacements_to_file "$PROJECT_ROOT/$local_path"
          modified_files+=("$local_path")
        fi
        ;;

      AUTO)
        printf "  ${GREEN}AUTO${NC}  %-50s (upstream-only change)\n" "$local_path"
        auto_count=$((auto_count + 1))
        total_auto=$((total_auto + 1))
        add_report_entry "$local_path" "AUTO"

        if [[ "$MODE" != "dry-run" ]]; then
          mkdir -p "$(dirname "$PROJECT_ROOT/$local_path")"
          cp "$upstream_file" "$PROJECT_ROOT/$local_path"
          apply_namespace_replacements_to_file "$PROJECT_ROOT/$local_path"
          modified_files+=("$local_path")
        fi
        ;;

      KEEP-LOCAL)
        printf "  ${GREEN}KEEP${NC}  %-50s (local-only changes)\n" "$local_path"
        keep_count=$((keep_count + 1))
        total_keep=$((total_keep + 1))
        add_report_entry "$local_path" "KEEP-LOCAL"
        # No action needed — local version preserved
        ;;

      CONFLICT)
        printf "  ${RED}CONFLICT${NC} %s\n" "$local_path"
        conflict_count=$((conflict_count + 1))
        total_conflicts=$((total_conflicts + 1))

        if [[ "$MODE" == "dry-run" ]]; then
          # Classify only, no AI calls or file changes
          add_report_entry "$local_path" "CONFLICT"

        elif [[ "$MODE" == "auto" ]]; then
          if [[ "$USE_AI" == true ]]; then
            printf "           Analyzing with AI...\n"
            ai_result=$(analyze_conflict "$local_path" "$upstream_file" "$clone_dir" "$last_commit" "$base_path" "$filepath")

            # Parse AI response
            ai_decision=$(echo "$ai_result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('decision','needs_human'))" 2>/dev/null || echo "needs_human")
            ai_risk=$(echo "$ai_result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('risk','high'))" 2>/dev/null || echo "high")
            ai_rationale=$(echo "$ai_result" | python3 -c "import json,sys; print(json.load(sys.stdin).get('rationale',''))" 2>/dev/null || echo "")

            add_ai_decision "$local_path" "$ai_decision" "$ai_risk" "$ai_rationale"

            if [[ "$ai_decision" == "accept_upstream" ]] && [[ "$ai_risk" == "low" ]]; then
              # Auto-apply upstream
              tmp_upstream=$(mktemp)
              cp "$upstream_file" "$tmp_upstream"
              apply_namespace_replacements_to_file "$tmp_upstream"
              cp "$tmp_upstream" "$PROJECT_ROOT/$local_path"
              rm -f "$tmp_upstream"
              modified_files+=("$local_path")
              total_ai_resolved=$((total_ai_resolved + 1))
              printf "           ${GREEN}AI: accept_upstream (risk: low) — auto-applied${NC}\n"
              add_report_entry "$local_path" "CONFLICT:ai-resolved"
            elif [[ "$ai_decision" == "keep_local" ]] && [[ "$ai_risk" == "low" ]]; then
              # Keep local, no action
              total_ai_resolved=$((total_ai_resolved + 1))
              printf "           ${GREEN}AI: keep_local (risk: low) — preserved${NC}\n"
              add_report_entry "$local_path" "CONFLICT:ai-resolved"
            else
              # High risk or needs_human — skip
              printf "           ${YELLOW}AI: $ai_decision (risk: $ai_risk) — skipped for human review${NC}\n"
              add_report_entry "$local_path" "CONFLICT:needs-human"
            fi
          else
            # --no-ai: skip conflicts in auto mode
            printf "           ${YELLOW}(skipped in --auto --no-ai mode)${NC}\n"
            add_report_entry "$local_path" "CONFLICT:no-ai"
          fi

        elif [[ "$MODE" == "interactive" ]]; then
          local ai_json="null"
          if [[ "$USE_AI" == true ]]; then
            printf "           Analyzing with AI...\n"
            ai_json=$(analyze_conflict "$local_path" "$upstream_file" "$clone_dir" "$last_commit" "$base_path" "$filepath")

            # Record AI decision for report
            local int_decision int_risk int_rationale
            int_decision=$(echo "$ai_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('decision','needs_human'))" 2>/dev/null || echo "needs_human")
            int_risk=$(echo "$ai_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('risk','high'))" 2>/dev/null || echo "high")
            int_rationale=$(echo "$ai_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('rationale',''))" 2>/dev/null || echo "")
            add_ai_decision "$local_path" "$int_decision" "$int_risk" "$int_rationale"
          fi

          user_choice=$(handle_conflict_interactive "$local_path" "$upstream_file" "$clone_dir" "$last_commit" "$base_path" "$filepath" "$ai_json")

          if [[ "$user_choice" == "accept_upstream" ]]; then
            modified_files+=("$local_path")
            total_ai_resolved=$((total_ai_resolved + 1))
            add_report_entry "$local_path" "CONFLICT:user-accepted"
          elif [[ "$user_choice" == "keep_local" ]]; then
            add_report_entry "$local_path" "CONFLICT:user-kept"
          else
            add_report_entry "$local_path" "CONFLICT:user-skipped"
          fi
          echo ""
        fi
        ;;

      REVIEW:*)
        reason="${classification#REVIEW:}"
        printf "  ${CYAN}REVIEW${NC} %-50s (%s)\n" "$local_path" "$reason"
        review_count=$((review_count + 1))
        total_reviewed=$((total_reviewed + 1))
        add_report_entry "$local_path" "$classification"

        if [[ "$MODE" == "interactive" ]]; then
          echo ""
          echo -e "  ${BOLD}Local vs upstream (after namespace replacement):${NC}"
          tmp_upstream=$(mktemp)
          cp "$upstream_file" "$tmp_upstream"
          apply_namespace_replacements_to_file "$tmp_upstream"
          diff --color=always "$PROJECT_ROOT/$local_path" "$tmp_upstream" | head -80 || true
          echo ""

          while true; do
            echo -en "  ${BOLD}(a)${NC}ccept upstream | ${BOLD}(k)${NC}eep local | ${BOLD}(d)${NC}iff again | ${BOLD}(s)${NC}kip: "
            read -r choice
            case "$choice" in
              a|accept)
                cp "$tmp_upstream" "$PROJECT_ROOT/$local_path"
                modified_files+=("$local_path")
                echo -e "  ${GREEN}→ Accepted upstream${NC}"
                break
                ;;
              k|keep)
                echo -e "  ${YELLOW}→ Kept local${NC}"
                break
                ;;
              d|diff)
                diff --color=always "$PROJECT_ROOT/$local_path" "$tmp_upstream" || true
                ;;
              s|skip)
                echo -e "  ${YELLOW}→ Skipped${NC}"
                break
                ;;
              *)
                echo "  Invalid choice. Use a/k/d/s."
                ;;
            esac
          done
          rm -f "$tmp_upstream"
          echo ""

        elif [[ "$MODE" == "auto" ]]; then
          printf "           ${YELLOW}(skipped in --auto mode)${NC}\n"
        fi
        ;;
    esac
  done

  echo -e "  Summary: ${GREEN}$copy_count copied${NC}, ${GREEN}$auto_count auto${NC}, ${GREEN}$keep_count kept${NC}, ${RED}$conflict_count conflict${NC}, ${YELLOW}$skip_count skipped${NC}, ${CYAN}$review_count review${NC}"

  # Update lastSyncedCommit
  if [[ "$MODE" != "dry-run" ]]; then
    python3 -c "
import json
with open('$UPSTREAMS_JSON', 'r+') as f:
    data = json.load(f)
    for u in data['upstreams']:
        if u['name'] == '$upstream_name':
            u['lastSyncedCommit'] = '$head_commit'
    f.seek(0); json.dump(data, f, indent=2); f.write('\n'); f.truncate()
"
  fi
  echo ""
done

# ─────────────────────────────────────────────
# Contamination check
# ─────────────────────────────────────────────

if [[ ${#modified_files[@]} -gt 0 ]]; then
  echo -e "${BOLD}─── Contamination Check ───${NC}"
  contamination_found=0

  for file in "${modified_files[@]}"; do
    full_path="$PROJECT_ROOT/$file"
    [[ ! -f "$full_path" ]] && continue

    # Check blocklist terms
    for term in "${BLOCKLIST_TERMS[@]}"; do
      if grep -q "$term" "$full_path" 2>/dev/null; then
        echo -e "  ${RED}WARN${NC} $file contains blocklisted term: ${BOLD}$term${NC}"
        contamination_found=$((contamination_found + 1))
      fi
    done

    # Check for raw namespace patterns that should have been replaced
    for old in "${!NS_REPLACEMENTS[@]}"; do
      if grep -q "$old" "$full_path" 2>/dev/null; then
        echo -e "  ${RED}WARN${NC} $file still contains raw namespace: ${BOLD}$old${NC}"
        contamination_found=$((contamination_found + 1))
      fi
    done
  done

  if [[ $contamination_found -eq 0 ]]; then
    echo -e "  ${GREEN}No contamination detected${NC}"
  else
    echo -e "  ${RED}$contamination_found contamination warning(s)${NC}"
  fi
  echo ""
fi

# ─────────────────────────────────────────────
# Final summary
# ─────────────────────────────────────────────

echo -e "${BOLD}═══ Summary ═══${NC}"
echo -e "  Copied:       ${GREEN}$total_copied${NC}"
echo -e "  Auto-applied: ${GREEN}$total_auto${NC}"
echo -e "  Kept local:   ${GREEN}$total_keep${NC}"
echo -e "  Conflicts:    ${RED}$total_conflicts${NC} ($total_ai_resolved AI-resolved)"
echo -e "  Skipped:      ${YELLOW}$total_skipped${NC}"
echo -e "  Review:       ${CYAN}$total_reviewed${NC}"
if [[ $total_errors -gt 0 ]]; then
  echo -e "  Errors:       ${RED}$total_errors${NC}"
fi
if [[ "$MODE" == "dry-run" ]]; then
  echo -e "  ${YELLOW}(dry-run — no files were modified)${NC}"
fi

# ─────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────

if [[ "$GENERATE_REPORT" == true ]]; then
  if [[ -n "$REPORT_FILE" ]]; then
    generate_report > "$REPORT_FILE"
    echo -e "\n  Report written to: ${CYAN}$REPORT_FILE${NC}"
  else
    generate_report
  fi
fi
