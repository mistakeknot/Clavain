#!/usr/bin/env bash
# context-reset-pre.sh — PreToolUse, observe-mode context-reset telemetry (mk-42j9.40).
#
# NOT A SECURITY BOUNDARY. Records whether an approval-gated action (push, PR,
# release, publication, destructive override) runs while the context epoch is
# exposed to untrusted content or its exposure is unknown. The verdict is always
# "allow". This hook prints nothing on stdout, so normal permission prompts are
# untouched. It never blocks and never performs or requests a reset. It fails
# open: any internal error exits 0. Rollback: `mode: off` in
# config/context-reset.yaml.
set -uo pipefail
trap 'exit 0' ERR

payload=$(cat 2>/dev/null) || payload=""
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0
# shellcheck source=hooks/lib-context-reset.sh
source "$script_dir/lib-context-reset.sh" 2>/dev/null || exit 0

cr_should_record_for "$payload" || exit 0
cr_handle_pre "$payload" >/dev/null || true
exit 0
