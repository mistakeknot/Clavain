#!/usr/bin/env bash
# Bootstrap helper for Clavain in Codex: install/update wrappers and run health checks.
#
# Typical use:
#   scripts/codex-bootstrap.sh               # install/update + doctor
#   scripts/codex-bootstrap.sh --check-only   # doctor only (no writes)
#   scripts/codex-bootstrap.sh --json         # machine-readable output
#
# This is intended for direct invocation from user-facing commands or one-off
# maintenance flows so Codex can keep Clavain prompt wrappers and skill links
# aligned with the current checkout.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_DIR=""
CHECK_ONLY=0
DOCTOR_JSON=0

usage() {
  cat <<'EOF'
Usage:
  codex-bootstrap.sh [options]

Options:
  --source PATH     Use this Clavain checkout as source.
  --check-only      Do not run install/refresh; doctor only.
  --json            Print doctor output as JSON.
  -h, --help        Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE_DIR="${2:?missing value for --source}"
      shift 2
      ;;
    --check-only)
      CHECK_ONLY=1
      shift
      ;;
    --json)
      DOCTOR_JSON=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$SOURCE_DIR" ]]; then
  SOURCE_DIR="$DEFAULT_SOURCE_DIR"
fi
SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"

if [[ ! -d "$SOURCE_DIR/scripts" || ! -d "$SOURCE_DIR/skills" || ! -d "$SOURCE_DIR/commands" ]]; then
  echo "Invalid Clavain source directory: $SOURCE_DIR" >&2
  exit 1
fi

if [[ "$CHECK_ONLY" -eq 0 ]]; then
  bash "$SOURCE_DIR/scripts/install-codex.sh" install --source "$SOURCE_DIR"
fi

run_doctor() {
  local output status

  if [[ "$DOCTOR_JSON" -eq 1 ]]; then
    if output="$(bash "$SOURCE_DIR/scripts/install-codex.sh" doctor --source "$SOURCE_DIR" --json 2>&1)"; then
      status=0
    else
      status=$?
    fi

    if command -v jq >/dev/null 2>&1; then
      if echo "$output" | jq . >/dev/null 2>&1; then
        echo "$output" | jq \
          --arg source "$SOURCE_DIR" \
          --arg pwd "$PWD" \
          --argjson check_only "$([[ "$CHECK_ONLY" -eq 1 ]] && echo true || echo false)" \
          '{clavain_bootstrap:{source_dir:$source,project_dir:$pwd,check_only:$check_only},doctor:.}'
        return "$status"
      fi
      echo "$output"
      return "$status"
    fi

    echo "$output"
    return "$status"
  fi

  bash "$SOURCE_DIR/scripts/install-codex.sh" doctor --source "$SOURCE_DIR"
}

run_doctor
exit_code=$?

if [[ "$DOCTOR_JSON" -eq 0 && "$CHECK_ONLY" -eq 1 ]]; then
  if [[ "$exit_code" -eq 0 ]]; then
    echo "Clavain Codex bootstrap checks passed."
  else
    echo "Clavain Codex bootstrap checks found issues." >&2
  fi
fi

exit "$exit_code"
