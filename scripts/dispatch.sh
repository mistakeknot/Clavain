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

# Execute
exec "${CMD[@]}"
