#!/bin/bash
#
# Clavain post-bump hook — called by interbump before git commit.
# Refreshes skill/agent/command catalog counts in plugin.json description.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_VERSION="${1:-}"

if command -v python3 &>/dev/null && [ -f "$REPO_ROOT/scripts/gen-catalog.py" ]; then
    if [[ "${1:-}" == "--check" ]] || [[ "${DRY_RUN:-}" == "true" ]]; then
        python3 "$REPO_ROOT/scripts/gen-catalog.py" --check || true
    else
        python3 "$REPO_ROOT/scripts/gen-catalog.py"
    fi
fi

# Sync agent-rig plugin lists into setup.md and doctor.md
if command -v python3 &>/dev/null && [ -f "$REPO_ROOT/scripts/gen-rig-sync.py" ]; then
    if [[ "${1:-}" == "--check" ]] || [[ "${DRY_RUN:-}" == "true" ]]; then
        python3 "$REPO_ROOT/scripts/gen-rig-sync.py" --check || true
    else
        python3 "$REPO_ROOT/scripts/gen-rig-sync.py"
    fi
fi

# Kimi has its own manifest outside Intercore's standard version surfaces.
# Keep its release metadata synchronized after the catalog generators run.
KIMI_MANIFEST="$REPO_ROOT/kimi.plugin.json"
CLAUDE_MANIFEST="$REPO_ROOT/.claude-plugin/plugin.json"
if [[ -n "$TARGET_VERSION" && "$TARGET_VERSION" != "--check" \
    && "${DRY_RUN:-}" != "true" && -f "$KIMI_MANIFEST" \
    && -f "$CLAUDE_MANIFEST" ]]; then
    python3 - "$KIMI_MANIFEST" "$CLAUDE_MANIFEST" "$TARGET_VERSION" <<'PY'
import json
import os
from pathlib import Path
import sys
import tempfile

kimi_path = Path(sys.argv[1])
claude = json.loads(Path(sys.argv[2]).read_text())
kimi = json.loads(kimi_path.read_text())
kimi["version"] = sys.argv[3]
if claude.get("description"):
    kimi["description"] = claude["description"]
author = claude.get("author")
if isinstance(author, dict):
    author = author.get("name")
if author:
    kimi["author"] = author
interface = kimi.setdefault("interface", {})
interface.setdefault("displayName", kimi.get("name", "clavain"))
description = kimi.get("description", "")
interface["shortDescription"] = (
    description if len(description) <= 120 else description[:117].rstrip() + "..."
)
fd, temporary = tempfile.mkstemp(prefix=".kimi-plugin-", dir=kimi_path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(kimi, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temporary, kimi_path)
except BaseException:
    try:
        os.unlink(temporary)
    except OSError:
        pass
    raise
PY
fi

# Intercore invokes this hook before writing plugin.json, but passes the target
# version as argv[1]. Apply it after generators that still read the current
# plugin.json so they cannot overwrite the target with the old version.
if [[ -n "$TARGET_VERSION" && "$TARGET_VERSION" != "--check" && "${DRY_RUN:-}" != "true" ]]; then
    PRD="$REPO_ROOT/docs/PRD.md"
    if [[ -f "$PRD" ]]; then
        TMP="${PRD}.tmp.$$"
        trap 'rm -f "$TMP"' EXIT
        sed -E "s/^\*\*Version:\*\*[[:space:]]+[^[:space:]]+/**Version:** ${TARGET_VERSION}/" "$PRD" > "$TMP"
        mv -f "$TMP" "$PRD"
        trap - EXIT
    fi
fi
