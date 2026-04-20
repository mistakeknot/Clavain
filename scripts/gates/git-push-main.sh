#!/usr/bin/env bash
# Gate wrapper for `git push` targeting main on the current remote.
#
# Usage: git-push-main.sh [remote] [refspec]
# Defaults: remote=origin, refspec=main.
#
# The wrapper does NOT protect against force-push; that decision belongs to
# an explicit policy rule (future git-force-push-main op) and/or branch
# protection on the remote.
set -euo pipefail

REMOTE="${1:-origin}"
REFSPEC="${2:-main}"

# shellcheck source=/dev/null
source "$(dirname "$0")/_common.sh"

HEAD_SHA="$(git rev-parse HEAD 2>/dev/null || echo)"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo detached)"

check_flags=( --target="${REMOTE}/${REFSPEC}" --head-sha="$HEAD_SHA" )

rc=0
gate_check git-push-main "${check_flags[@]}" >/dev/null || rc=$?
gate_decide_mode "$rc" git-push-main

git push "$REMOTE" "$REFSPEC"

gate_record git-push-main "${REMOTE}/${REFSPEC}" "" --vetted-sha="$HEAD_SHA"
gate_sign   git-push-main "${REMOTE}/${REFSPEC}" ""
echo "git-push-main: pushed ${CURRENT_BRANCH} → ${REMOTE}/${REFSPEC}"
