#!/usr/bin/env bash
# clavain debate — structured 2-round Claude↔Codex debate
#
# Usage:
#   debate.sh -C <dir> -t <topic> --claude-position <file> -o <output> [--rounds 1|2]
#   debate.sh --dry-run -C <dir> -t <topic> --claude-position <file> -o <output>
#
# Round 1: Codex reads Claude's position and produces independent analysis
# Round 2: Codex reads both positions and produces rebuttal + final recommendation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISPATCH="$SCRIPT_DIR/dispatch.sh"

# Defaults
WORKDIR=""
TOPIC=""
CLAUDE_POSITION=""
OUTPUT=""
ROUNDS=2
DRY_RUN=false
MODEL=""

show_help() {
  cat <<'HELP'
clavain debate — structured 2-round Claude↔Codex debate

Usage:
  debate.sh -C <dir> -t <topic> --claude-position <file> -o <output> [OPTIONS]

Options:
  -C, --cd <DIR>                 Working directory (project root)
  -t, --topic <SLUG>             Topic slug (kebab-case, used in temp file names)
  --claude-position <FILE>       File containing Claude's position statement
  -o, --output <FILE>            Output file for debate result
  --rounds <1|2>                 Number of rounds (default: 2)
  -m, --model <MODEL>            Override Codex model
  --dry-run                      Print commands without executing
  --help                         Show this help

Round 1 — Independent Analysis:
  Codex reads Claude's position and the codebase, then produces its own
  independent analysis with agreements, disagreements, and alternatives.

Round 2 — Rebuttal:
  Codex reads both positions and produces a rebuttal with final recommendation.
  This round is skipped if --rounds 1 is specified.

Examples:
  debate.sh -C /root/projects/Foo -t auth-strategy \
    --claude-position /tmp/debate-claude-position-auth-strategy.md \
    -o /tmp/debate-output-auth-strategy.md

  debate.sh --dry-run -C /root/projects/Foo -t cache-design \
    --claude-position /tmp/pos.md -o /tmp/out.md --rounds 1
HELP
  exit 0
}

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
    -t|--topic)
      require_arg "$1" "${2:-}"
      TOPIC="$2"
      shift 2
      ;;
    --claude-position)
      require_arg "$1" "${2:-}"
      CLAUDE_POSITION="$2"
      shift 2
      ;;
    -o|--output)
      require_arg "$1" "${2:-}"
      OUTPUT="$2"
      shift 2
      ;;
    --rounds)
      require_arg "$1" "${2:-}"
      ROUNDS="$2"
      shift 2
      ;;
    -m|--model)
      require_arg "$1" "${2:-}"
      MODEL="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Error: Unknown option: $1" >&2
      echo "Use --help for usage information" >&2
      exit 1
      ;;
  esac
done

# Validate required args
if [[ -z "$WORKDIR" ]]; then
  echo "Error: -C <dir> is required" >&2
  exit 1
fi
if [[ -z "$TOPIC" ]]; then
  echo "Error: -t <topic> is required" >&2
  exit 1
fi
if [[ -z "$CLAUDE_POSITION" ]]; then
  echo "Error: --claude-position <file> is required" >&2
  exit 1
fi
if [[ -z "$OUTPUT" ]]; then
  echo "Error: -o <output> is required" >&2
  exit 1
fi
if [[ ! -f "$CLAUDE_POSITION" ]]; then
  echo "Error: Claude position file not found: $CLAUDE_POSITION" >&2
  exit 1
fi
if [[ "$ROUNDS" != "1" && "$ROUNDS" != "2" ]]; then
  echo "Error: --rounds must be 1 or 2 (got '$ROUNDS')" >&2
  exit 1
fi

# Check dispatch.sh exists
if [[ ! -f "$DISPATCH" ]]; then
  echo "Error: dispatch.sh not found at $DISPATCH" >&2
  exit 1
fi

# Read Claude's position
CLAUDE_POS_CONTENT="$(cat "$CLAUDE_POSITION")"

# Temp files for intermediate results
ROUND1_PROMPT="/tmp/debate-r1-prompt-${TOPIC}.md"
ROUND1_OUTPUT="/tmp/debate-r1-output-${TOPIC}.md"
ROUND2_PROMPT="/tmp/debate-r2-prompt-${TOPIC}.md"

# Build model args
MODEL_ARGS=()
if [[ -n "$MODEL" ]]; then
  MODEL_ARGS+=(-m "$MODEL")
fi

DRY_RUN_ARG=""
if [[ "$DRY_RUN" == true ]]; then
  DRY_RUN_ARG="--dry-run"
fi

# ──────────────────────────────────────────────
# Round 1: Independent Analysis
# ──────────────────────────────────────────────

echo "=== Round 1: Independent Analysis ===" >&2

cat > "$ROUND1_PROMPT" <<PROMPT
You are participating in a structured technical debate. Another AI (Claude) has analyzed a technical decision and written a position statement. Your job is to:

1. Read the codebase independently
2. Read Claude's position
3. Produce your OWN independent analysis

## Topic
${TOPIC}

## Claude's Position
${CLAUDE_POS_CONTENT}

## Your Task

Write a structured response with these sections:

### Codex's Independent Analysis
[Your own analysis of the problem, developed independently from reading the code]

### Areas of Agreement
[Where you agree with Claude's position and why]

### Areas of Disagreement
[Where you disagree and why, with specific technical reasoning]

### Alternative Approaches
[Any approaches Claude didn't consider]

### Risks and Concerns
[Technical risks you see with any approach]

Do NOT make any file changes. This is a read-only analysis task.
PROMPT

echo "Dispatching Codex for Round 1 analysis..." >&2

bash "$DISPATCH" \
  --inject-docs -C "$WORKDIR" \
  --name "debate-r1-${TOPIC}" \
  -o "$ROUND1_OUTPUT" \
  -s read-only \
  ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
  ${DRY_RUN_ARG:+"$DRY_RUN_ARG"} \
  --prompt-file "$ROUND1_PROMPT"

if [[ "$DRY_RUN" == true ]]; then
  echo "" >&2
  echo "Round 1 prompt written to: $ROUND1_PROMPT" >&2
  if [[ "$ROUNDS" == "1" ]]; then
    echo "=== Dry run complete (1 round) ===" >&2
    exit 0
  fi
  # Fall through to Round 2 dry run
fi

# ──────────────────────────────────────────────
# Round 2: Rebuttal (if requested)
# ──────────────────────────────────────────────

if [[ "$ROUNDS" == "1" ]]; then
  # Single round — copy Round 1 output as final output
  cp "$ROUND1_OUTPUT" "$OUTPUT"
  echo "=== Debate complete (1 round) ===" >&2
  echo "Output: $OUTPUT" >&2
  exit 0
fi

echo "" >&2
echo "=== Round 2: Rebuttal ===" >&2

# Read Round 1 output
if [[ "$DRY_RUN" != true ]]; then
  ROUND1_CONTENT="$(cat "$ROUND1_OUTPUT")"
else
  ROUND1_CONTENT="[Round 1 output would appear here]"
fi

cat > "$ROUND2_PROMPT" <<PROMPT
You are in Round 2 of a structured technical debate. You've already provided your independent analysis in Round 1. Now review both positions and produce a final synthesis.

## Topic
${TOPIC}

## Claude's Position (Round 1)
${CLAUDE_POS_CONTENT}

## Codex's Analysis (Round 1)
${ROUND1_CONTENT}

## Your Task (Round 2 — Rebuttal)

Write a final synthesis with these sections:

### Strongest Arguments from Each Side
[What each position got right]

### Remaining Disagreements
[Points where the positions are irreconcilable and why]

### Codex's Final Recommendation
[Your recommended approach, incorporating the best ideas from both sides]

### Implementation Notes
[Practical considerations for whichever approach is chosen]

### Risk Mitigations
[How to address the risks identified by both sides]

Do NOT make any file changes. This is a read-only analysis task.
PROMPT

echo "Dispatching Codex for Round 2 rebuttal..." >&2

bash "$DISPATCH" \
  --inject-docs -C "$WORKDIR" \
  --name "debate-r2-${TOPIC}" \
  -o "$OUTPUT" \
  -s read-only \
  ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
  ${DRY_RUN_ARG:+"$DRY_RUN_ARG"} \
  --prompt-file "$ROUND2_PROMPT"

if [[ "$DRY_RUN" == true ]]; then
  echo "" >&2
  echo "Round 2 prompt written to: $ROUND2_PROMPT" >&2
  echo "=== Dry run complete (2 rounds) ===" >&2
  exit 0
fi

echo "" >&2
echo "=== Debate complete (2 rounds) ===" >&2
echo "Output: $OUTPUT" >&2
