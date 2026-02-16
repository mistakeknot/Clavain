#!/usr/bin/env bash
# clavain dispatch — wraps codex exec with sensible defaults
#
# Usage:
#   bash dispatch.sh -C /path/to/project -o /tmp/output.md "prompt"
#   bash dispatch.sh -C /path --inject-docs --name vet -o /tmp/codex-{name}.md "prompt"
#   bash dispatch.sh --inject-docs=claude -C /path --prompt-file task.md -o /tmp/out.md
#   bash dispatch.sh --dry-run -C /path -o /tmp/out.md "prompt"

set -euo pipefail

# Size threshold for --inject-docs warning (bytes)
INJECT_DOCS_WARN_THRESHOLD=20000

# Defaults
SANDBOX="workspace-write"
WORKDIR=""
OUTPUT=""
MODEL=""
TIER=""
CLAVAIN_INTERSERVE_MODE=false
CLAVAIN_DISPATCH_PROFILE="${CLAVAIN_DISPATCH_PROFILE:-${CLAVAIN_INTERSERVE_PROFILE:-}}"
INJECT_DOCS=""  # empty=off, "claude" (default for bare --inject-docs), "agents", "all"
NAME=""
DRY_RUN=false
PROMPT_FILE=""
TEMPLATE_FILE=""
IMAGES=()
EXTRA_ARGS=()

show_help() {
  cat <<'HELP'
clavain dispatch — wraps codex exec with sensible defaults

Usage:
  dispatch.sh [OPTIONS] "prompt"
  dispatch.sh [OPTIONS] --prompt-file <file>

Options:
  -C, --cd <DIR>                Working directory (required for --inject-docs)
  -o, --output-last-message <FILE>  Output file ({name} replaced by --name value)
  -s, --sandbox <MODE>          Sandbox: read-only | workspace-write | danger-full-access
  -m, --model <MODEL>           Override model (default: from ~/.codex/config.toml)
  --tier <fast|deep>            Resolve model from config/dispatch/tiers.yaml
                                  Mutually exclusive with -m (use -m to override)
  -i, --image <FILE>            Attach image to prompt (repeatable)
  --inject-docs[=SCOPE]         Prepend docs from working dir to prompt
                                  (no value)  CLAUDE.md only (recommended — Codex reads AGENTS.md natively)
                                  =claude     CLAUDE.md only
                                  =agents     AGENTS.md only (usually redundant)
                                  =all        CLAUDE.md + AGENTS.md
  --name <LABEL>                Label for {name} in output path and tracking
  --prompt-file <FILE>          Read prompt from file instead of positional arg
  --template <FILE>             Assemble prompt from template + task description
                                  Task description uses KEY: sections (GOAL:, IMPLEMENT:, etc.)
                                  Template uses {{KEY}} placeholders replaced by section values
  --dry-run                     Print the codex exec command without executing
  --help                        Show this help

Examples:
  dispatch.sh -C /root/projects/Foo -o /tmp/out.md "Fix the bug in bar.go"
  dispatch.sh --inject-docs -C /root/projects/Foo --name vet -o /tmp/codex-{name}.md "Vet the signals package"
  dispatch.sh --inject-docs=claude -C /root/projects/Foo --prompt-file /tmp/task.md -o /tmp/out.md
  dispatch.sh --template megaprompt.md --prompt-file /tmp/task.md -C /root/projects/Foo -o /tmp/out.md
  dispatch.sh --dry-run --inject-docs -C /root/projects/Foo -o /tmp/out.md "Test prompt"
HELP
  exit 0
}

# Require that a flag has a value argument following it
require_arg() {
  if [[ $# -lt 2 || -z "${2:-}" ]]; then
    echo "Error: $1 requires a value" >&2
    exit 1
  fi
}

# Resolve a tier name to a model string from tiers.yaml
resolve_tier_model() {
  local tier="$1"
  local config_file=""
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local source_dir="${CLAVAIN_SOURCE_DIR:-${CLAVAIN_DIR:-}}"
  local config_root=""
  local resolved_tier="$tier"
  local target_tier
  local fallback_tier="$tier"

  if [[ "$CLAVAIN_INTERSERVE_MODE" == true && "$tier" == "fast" ]]; then
    target_tier="fast-clavain"
  elif [[ "$CLAVAIN_INTERSERVE_MODE" == true && "$tier" == "deep" ]]; then
    target_tier="deep-clavain"
  else
    target_tier="$tier"
  fi

  # Find tiers.yaml relative to dispatch script first, then optional source override,
  # then cached plugin installs.
  if [[ -f "$script_dir/../config/dispatch/tiers.yaml" ]]; then
    config_file="$script_dir/../config/dispatch/tiers.yaml"
  elif [[ -n "$source_dir" && -d "$source_dir" && -f "$source_dir/config/dispatch/tiers.yaml" ]]; then
    config_file="$source_dir/config/dispatch/tiers.yaml"
  else
    config_root="$(find ~/.claude/plugins/cache -path '*/clavain/*/config/dispatch/tiers.yaml' 2>/dev/null | head -1)"
    [[ -n "$config_root" ]] && config_file="$config_root"
  fi

  if [[ -z "$config_file" ]]; then
    echo "Warning: tiers.yaml not found — --tier ignored, using default model" >&2
    return 1
  fi

  # Parse YAML: find tier block under "tiers:", then read its "model:" value.
  # For Clavain interserve mode, prefer fast-clavain/deep-clavain and fall back to fast/deep.
  local candidate_tiers=("$target_tier")
  if [[ "$target_tier" != "$fallback_tier" ]]; then
    candidate_tiers+=("$fallback_tier")
  fi
  local model=""
  local found=""
  local tier_lookup

  for tier_lookup in "${candidate_tiers[@]}"; do
    # Parse every candidate from scratch to keep this function easy to audit.
    local in_tiers=false
    local in_tier=false
    local current_model=""
    while IFS= read -r line; do
      # Detect top-level "tiers:" section
      if [[ "$line" =~ ^tiers: ]]; then
        in_tiers=true
        continue
      fi
      # Exit tiers section on next top-level key
      if [[ "$in_tiers" == true && "$line" =~ ^[a-z] ]]; then
        break
      fi
      # Match the requested tier (e.g. "  fast:")
      if [[ "$in_tiers" == true && "$line" =~ ^[[:space:]]+${tier_lookup}:[[:space:]]*$ ]]; then
        in_tier=true
        continue
      fi
      # Read model value from within the tier block
      if [[ "$in_tier" == true && "$line" =~ ^[[:space:]]+model:[[:space:]]*(.+) ]]; then
        current_model="${BASH_REMATCH[1]}"
        break
      fi
      # Hit a sibling tier key — stop
      if [[ "$in_tier" == true && "$line" =~ ^[[:space:]]+[a-z][a-z0-9_-]*:[[:space:]]*$ ]]; then
        break
      fi
    done < "$config_file"

    if [[ -n "$current_model" ]]; then
      model="$current_model"
      found="$tier_lookup"
      break
    fi

    if [[ "$tier_lookup" != "$fallback_tier" ]]; then
      echo "Note: tier '$tier_lookup' not found in $config_file. Trying '$fallback_tier'." >&2
    fi
  done

  if [[ -n "$found" && "$found" != "$tier" ]]; then
    echo "Note: tier '$tier' mapped to '$found' for Clavain interserve mode." >&2
  fi

  if [[ -z "$model" ]]; then
    echo "Warning: tier '$tier' not found in $config_file" >&2
    return 1
  fi

  echo "$model"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      show_help
      ;;
    -C|--cd)
      require_arg "$1" "${2:-}"
      WORKDIR="$2"
      shift 2
      ;;
    -o|--output-last-message)
      require_arg "$1" "${2:-}"
      OUTPUT="$2"
      shift 2
      ;;
    -s|--sandbox)
      require_arg "$1" "${2:-}"
      SANDBOX="$2"
      shift 2
      ;;
    -m|--model)
      require_arg "$1" "${2:-}"
      MODEL="$2"
      shift 2
      ;;
    --tier)
      require_arg "$1" "${2:-}"
      TIER="$2"
      shift 2
      ;;
    -i|--image)
      require_arg "$1" "${2:-}"
      IMAGES+=("$2")
      shift 2
      ;;
    --inject-docs)
      INJECT_DOCS="claude"
      shift
      ;;
    --inject-docs=*)
      INJECT_DOCS="${1#--inject-docs=}"
      shift
      ;;
    --name)
      require_arg "$1" "${2:-}"
      NAME="$2"
      shift 2
      ;;
    --prompt-file)
      require_arg "$1" "${2:-}"
      PROMPT_FILE="$2"
      shift 2
      ;;
    --template)
      require_arg "$1" "${2:-}"
      TEMPLATE_FILE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --)
      # End of options — next arg is the prompt even if it starts with -
      shift
      break
      ;;
    # Known codex flags that take a value — pass through with their arg
    --add-dir|--output-schema|-p|--profile|-c|--config|--color|-a|--ask-for-approval)
      require_arg "$1" "${2:-}"
      EXTRA_ARGS+=("$1" "$2")
      shift 2
      ;;
    --dangerously-bypass-approvals-and-sandbox|--yolo)
      if [[ "${CLAVAIN_ALLOW_UNSAFE:-}" == "1" ]]; then
        EXTRA_ARGS+=("$1")
        shift
      else
        echo "Error: $1 is blocked by dispatch.sh safety policy. Set CLAVAIN_ALLOW_UNSAFE=1 to override." >&2
        exit 1
      fi
      ;;
    # Known codex flags that are boolean — pass through alone
    --json|--full-auto|--skip-git-repo-check|--oss|--search|--no-alt-screen)
      EXTRA_ARGS+=("$1")
      shift
      ;;
    --enable|--disable|--local-provider)
      require_arg "$1" "${2:-}"
      EXTRA_ARGS+=("$1" "$2")
      shift 2
      ;;
    -*)
      # Unknown flag — pass through as boolean (no value consumed)
      EXTRA_ARGS+=("$1")
      shift
      ;;
    *)
      # First non-flag positional argument is the prompt — stop parsing
      break
      ;;
  esac
done

# Detect whether Clavain-specific tier remapping should be used. This is opt-in via:
# - explicit CLAVAIN_DISPATCH_PROFILE=interserve (or legacy: clavain)
# - legacy alias CLAVAIN_INTERSERVE_PROFILE=interserve
# and only active when interserve mode is on.
if { [[ -n "${WORKDIR}" && -f "${WORKDIR}/.claude/interserve-toggle.flag" ]]; } || { [[ -z "${WORKDIR}" && -f ".claude/interserve-toggle.flag" ]]; }; then
  case "${CLAVAIN_DISPATCH_PROFILE,,}" in
    interserve|clavain|xhigh|codex)
      CLAVAIN_INTERSERVE_MODE=true
      ;;
  esac
fi

# Resolve --tier to a model name (mutually exclusive with -m)
if [[ -n "$TIER" ]]; then
  if [[ -n "$MODEL" ]]; then
    echo "Error: Cannot use both --tier and --model" >&2
    exit 1
  fi
  if RESOLVED_MODEL=$(resolve_tier_model "$TIER"); then
    MODEL="$RESOLVED_MODEL"
    echo "Tier '$TIER' resolved to model: $MODEL" >&2
  fi
  # If resolution fails, warning already printed — MODEL stays empty (uses config.toml default)
fi

# Resolve prompt: positional arg, --prompt-file, or error
PROMPT="${1:-}"
if [[ -n "$PROMPT_FILE" ]]; then
  if [[ -n "$PROMPT" ]]; then
    echo "Error: Cannot use both --prompt-file and a positional prompt argument" >&2
    exit 1
  fi
  if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "Error: Prompt file not found: $PROMPT_FILE" >&2
    exit 1
  fi
  PROMPT="$(cat "$PROMPT_FILE")"
  if [[ -z "$PROMPT" ]]; then
    echo "Error: Prompt file is empty: $PROMPT_FILE" >&2
    exit 1
  fi
fi

if [[ -z "$PROMPT" ]]; then
  echo "Error: No prompt provided" >&2
  echo "Usage: dispatch.sh -C <dir> -o <output> [OPTIONS] \"prompt\"" >&2
  echo "       dispatch.sh --prompt-file <file> [OPTIONS]" >&2
  echo "       dispatch.sh --help for all options" >&2
  exit 1
fi

# Template assembly: parse task description sections, substitute into template
if [[ -n "$TEMPLATE_FILE" ]]; then
  if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "Error: Template file not found: $TEMPLATE_FILE" >&2
    exit 1
  fi

  TEMPLATE="$(cat "$TEMPLATE_FILE")"

  # Parse task description into associative array keyed by ^[A-Z_]+:$ headers
  declare -A SECTIONS
  CURRENT_KEY=""
  CURRENT_VAL=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^([A-Z_]+):$ ]]; then
      # Save previous section
      if [[ -n "$CURRENT_KEY" ]]; then
        # Trim leading/trailing blank lines
        SECTIONS["$CURRENT_KEY"]="$(echo "$CURRENT_VAL" | sed -e '/./,$!d' -e :a -e '/^\n*$/{$d;N;ba;}')"
      fi
      CURRENT_KEY="${BASH_REMATCH[1]}"
      CURRENT_VAL=""
    else
      CURRENT_VAL+="$line"$'\n'
    fi
  done <<< "$PROMPT"
  # Save last section
  if [[ -n "$CURRENT_KEY" ]]; then
    SECTIONS["$CURRENT_KEY"]="$(echo "$CURRENT_VAL" | sed -e '/./,$!d' -e :a -e '/^\n*$/{$d;N;ba;}')"
  fi

  # Replace {{KEY}} placeholders in template using perl for safe multi-line handling
  ASSEMBLED="$TEMPLATE"
  # Find all {{MARKER}} placeholders in template
  MARKERS=()
  while IFS= read -r marker; do
    [[ -n "$marker" ]] && MARKERS+=("$marker")
  done < <(grep -oP '\{\{[A-Z_]+\}\}' <<< "$ASSEMBLED" | sort -u)

  for marker in "${MARKERS[@]}"; do
    key="${marker#\{\{}"
    key="${key%\}\}}"
    if [[ -v "SECTIONS[$key]" ]]; then
      value="${SECTIONS[$key]}"
    else
      echo "Warning: Template marker $marker has no matching section in task description" >&2
      value=""
    fi
    # Use perl for safe multi-line replacement (handles backticks, quotes, dollar signs)
    ASSEMBLED="$(perl -0777 -e '
      my $tmpl = $ARGV[0];
      my $marker = $ARGV[1];
      my $value = $ARGV[2];
      $tmpl =~ s/\Q$marker\E/$value/g;
      print $tmpl;
    ' "$ASSEMBLED" "$marker" "$value")"
  done

  PROMPT="$ASSEMBLED"
fi

# Apply --name substitution to output path
if [[ -n "$NAME" && -n "$OUTPUT" ]]; then
  OUTPUT="${OUTPUT//\{name\}/$NAME}"
fi

# Warn if {name} still present in output path (--name not provided)
if [[ -n "$OUTPUT" && "$OUTPUT" == *'{name}'* ]]; then
  echo "Warning: Output path contains {name} but --name was not provided. Use --name <label> to substitute it." >&2
fi

# Inject docs from working directory into prompt
if [[ -n "$INJECT_DOCS" ]]; then
  if [[ -z "$WORKDIR" ]]; then
    echo "Error: --inject-docs requires -C <dir>" >&2
    exit 1
  fi

  case "$INJECT_DOCS" in
    all|claude|agents) ;;
    *)
      echo "Error: --inject-docs value must be 'all', 'claude', or 'agents' (got '$INJECT_DOCS')" >&2
      exit 1
      ;;
  esac

  DOCS_PREFIX=""

  if [[ "$INJECT_DOCS" == "all" || "$INJECT_DOCS" == "claude" ]]; then
    if [[ -f "$WORKDIR/CLAUDE.md" ]]; then
      DOCS_PREFIX+="$(cat "$WORKDIR/CLAUDE.md")"
      DOCS_PREFIX+=$'\n\n'
    fi
  fi

  if [[ "$INJECT_DOCS" == "all" || "$INJECT_DOCS" == "agents" ]]; then
    if [[ -f "$WORKDIR/AGENTS.md" ]]; then
      echo "Note: Codex reads AGENTS.md natively from the -C directory. Injecting it into the prompt is usually redundant." >&2
      DOCS_PREFIX+="$(cat "$WORKDIR/AGENTS.md")"
      DOCS_PREFIX+=$'\n\n'
    fi
  fi

  if [[ -z "$DOCS_PREFIX" ]]; then
    echo "Note: --inject-docs found no docs to inject in $WORKDIR" >&2
  else
    PREFIX_SIZE=${#DOCS_PREFIX}
    if [[ $PREFIX_SIZE -gt $INJECT_DOCS_WARN_THRESHOLD ]]; then
      echo "Warning: --inject-docs prepending ${PREFIX_SIZE} bytes of context. Consider --inject-docs=claude for smaller prompts." >&2
    fi
    PROMPT="${DOCS_PREFIX}---

${PROMPT}"
  fi
fi

# Build codex exec command
CMD=(codex exec)
CMD+=(-s "$SANDBOX")

if [[ -n "$WORKDIR" ]]; then
  CMD+=(-C "$WORKDIR")
fi

if [[ -n "$OUTPUT" ]]; then
  CMD+=(-o "$OUTPUT")
fi

if [[ -n "$MODEL" ]]; then
  CMD+=(-m "$MODEL")
fi

for img in "${IMAGES[@]+"${IMAGES[@]}"}"; do
  CMD+=(-i "$img")
done

if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  CMD+=("${EXTRA_ARGS[@]}")
fi

CMD+=("$PROMPT")

# Dry run: print command and exit
if [[ "$DRY_RUN" == true ]]; then
  if [[ -n "$TIER" ]]; then
    echo "# Tier: $TIER → model: ${MODEL:-<default>}" >&2
  fi
  echo "# Would execute:" >&2
  # Print command with prompt truncated for readability
  PROMPT_PREVIEW="${PROMPT:0:200}"
  if [[ ${#PROMPT} -gt 200 ]]; then
    PROMPT_PREVIEW+="... (${#PROMPT} bytes total)"
  fi
  # Reconstruct display command
  DISPLAY_CMD=(codex exec -s "$SANDBOX")
  if [[ -n "$WORKDIR" ]]; then DISPLAY_CMD+=(-C "$WORKDIR"); fi
  if [[ -n "$OUTPUT" ]]; then DISPLAY_CMD+=(-o "$OUTPUT"); fi
  if [[ -n "$MODEL" ]]; then DISPLAY_CMD+=(-m "$MODEL"); fi
  for img in "${IMAGES[@]+"${IMAGES[@]}"}"; do DISPLAY_CMD+=(-i "$img"); done
  if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then DISPLAY_CMD+=("${EXTRA_ARGS[@]}"); fi
  printf '%q ' "${DISPLAY_CMD[@]}"
  echo ""
  echo ""
  if [[ -n "$TEMPLATE_FILE" ]]; then
    echo "# Template: $TEMPLATE_FILE"
  fi
  echo "# Prompt (${#PROMPT} bytes):"
  echo "$PROMPT_PREVIEW"
  exit 0
fi

# Write dispatch state file for statusline visibility
STATE_FILE="/tmp/clavain-dispatch-$$.json"
SUMMARY_FILE=""
if [[ -n "$OUTPUT" ]]; then
  SUMMARY_FILE="${OUTPUT}.summary"
fi
trap 'rm -f "$STATE_FILE" "${STATE_FILE}.tmp"' EXIT INT TERM

# Validate state file path is writable
if ! touch "$STATE_FILE" 2>/dev/null; then
  echo "Error: Cannot write to $STATE_FILE (check /tmp permissions and disk space)" >&2
  exit 1
fi

STARTED_TS="$(date +%s)"

# Initial state
printf '{"name":"%s","workdir":"%s","started":%d,"activity":"starting","turns":0,"commands":0,"messages":0}\n' \
  "${NAME:-codex}" "${WORKDIR:-.}" "$STARTED_TS" > "$STATE_FILE"

# Check if gawk is available for JSONL streaming (match() with capture groups + systime() are gawk extensions)
HAS_GAWK=false
if awk --version 2>&1 | grep -q 'GNU Awk'; then
  HAS_GAWK=true
fi

# Awk JSONL parser: reads events from codex --json stdout, updates state file with
# activity type and counters, accumulates stats for summary.
# Skips non-JSON lines (Codex emits WARNING/ERROR lines to stdout when --json is used).
# Uses simple gawk regex matching — no JSON library needed for top-level fields.
# Assumes Codex JSONL uses unescaped enum strings for "type" field (safe per Codex schema).
_jsonl_parser() {
  local state_file="$1" name="$2" workdir="$3" started="$4" summary_file="$5"
  awk -v sf="$state_file" -v name="$name" -v wd="$workdir" -v st="$started" -v smf="$summary_file" '
    BEGIN { turns=0; cmds=0; msgs=0; in_tok=0; out_tok=0; activity="starting" }

    # Skip non-JSON lines (stderr noise from Codex)
    !/^\{/ { next }

    {
      line = $0
      # Extract top-level "type" value
      ev = ""; match(line, /"type":"([^"]+)"/, a); if (RSTART) ev = a[1]

      if (ev == "turn.started") {
        turns++; activity = "thinking"
      }
      else if (ev == "item.started") {
        # Check item.type with field-boundary matching to avoid false positives
        if (match(line, /"item":\{[^}]*"type":"command_execution"/)) activity = "running command"
      }
      else if (ev == "item.completed") {
        if (match(line, /"item":\{[^}]*"type":"command_execution"/)) cmds++
        else if (match(line, /"item":\{[^}]*"type":"agent_message"/)) { msgs++; activity = "writing" }
      }
      else if (ev == "turn.completed") {
        # Extract token counts
        match(line, /"input_tokens":([0-9]+)/, t); if (RSTART) in_tok += t[1]+0
        match(line, /"output_tokens":([0-9]+)/, t); if (RSTART) out_tok += t[1]+0
        activity = "thinking"
      }

      # Atomic state file update: write to temp, then rename
      tmp = sf ".tmp"
      printf "{\"name\":\"%s\",\"workdir\":\"%s\",\"started\":%d,\"activity\":\"%s\",\"turns\":%d,\"commands\":%d,\"messages\":%d}\n", \
        name, wd, st, activity, turns, cmds, msgs > tmp
      close(tmp)
      system("mv " tmp " " sf)
    }

    END {
      if (smf != "") {
        elapsed = systime() - st
        mins = int(elapsed / 60)
        secs = elapsed % 60
        printf "Dispatch: %s\nDuration: %dm %ds\nTurns: %d | Commands: %d | Messages: %d\nTokens: %d in / %d out\n", \
          name, mins, secs, turns, cmds, msgs, in_tok, out_tok > smf
        close(smf)
      }
    }
  '
}

# Extract verdict header from agent output and write .verdict sidecar.
# The verdict is the last block delimited by "--- VERDICT ---" ... "---".
# If no verdict block found, synthesize one from the output's last lines.
_extract_verdict() {
    local output_file="$1"
    [[ -z "$output_file" || ! -f "$output_file" ]] && return 0

    local verdict_file="${output_file}.verdict"

    # Try to extract existing verdict block (last 7 lines)
    local last_lines
    last_lines=$(tail -7 "$output_file" 2>/dev/null) || return 0

    if echo "$last_lines" | head -1 | grep -q "^--- VERDICT ---$"; then
        echo "$last_lines" > "$verdict_file"
        return 0
    fi

    # No verdict block — synthesize from output
    local verdict_line
    verdict_line=$(grep -m1 "^VERDICT:" "$output_file" 2>/dev/null) || verdict_line=""

    local status="pass"
    local summary="No structured verdict found."
    if [[ "$verdict_line" == *"NEEDS_ATTENTION"* ]]; then
        status="warn"
        summary="${verdict_line#VERDICT: }"
    elif [[ "$verdict_line" == *"CLEAN"* ]]; then
        status="pass"
        summary="Agent reports clean completion."
    elif [[ -z "$verdict_line" ]]; then
        status="warn"
        summary="No verdict line in agent output."
    fi

    cat > "$verdict_file" <<VERDICT
--- VERDICT ---
STATUS: $status
FILES: 0 changed
FINDINGS: 0 (P0: 0, P1: 0, P2: 0)
SUMMARY: $summary
---
VERDICT
}

if [[ "$HAS_GAWK" == true ]]; then
  # Add --json to capture JSONL stream, pipe through parser
  CMD+=(--json)

  # Execute: pipe stdout through parser, capture exit code immediately
  "${CMD[@]}" | _jsonl_parser "$STATE_FILE" "${NAME:-codex}" "${WORKDIR:-.}" "$STARTED_TS" "$SUMMARY_FILE"
  CODEX_EXIT="${PIPESTATUS[0]}"

  # Write summary from bash if awk didn't (fallback for short/failed runs)
  if [[ -n "$SUMMARY_FILE" && ! -f "$SUMMARY_FILE" ]]; then
    ELAPSED=$(( $(date +%s) - STARTED_TS ))
    MINS=$(( ELAPSED / 60 ))
    SECS=$(( ELAPSED % 60 ))
    printf 'Dispatch: %s\nDuration: %dm %ds\n' "${NAME:-codex}" "$MINS" "$SECS" > "$SUMMARY_FILE"
  fi

  # Extract verdict sidecar from output
  [[ -n "$OUTPUT" ]] && _extract_verdict "$OUTPUT"

  exit "$CODEX_EXIT"
else
  # Fallback: no gawk, run without JSONL parsing (no live statusline updates)
  echo "Note: gawk not found — running without live statusline updates" >&2
  "${CMD[@]}"

  # Extract verdict sidecar from output
  [[ -n "$OUTPUT" ]] && _extract_verdict "$OUTPUT"
fi
