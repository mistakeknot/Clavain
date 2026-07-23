#!/usr/bin/env bash
# Install Clavain for Kimi Code CLI.
#
# What this script sets up:
# - ~/.agents/skills/clavain  -> <clavain>/skills   (Kimi scans ~/.agents/skills natively)
# - kimi.plugin.json manifests via scripts/gen-kimi-manifests.py (warn + skip if absent)
# - $KIMI_CODE_HOME/mcp.json merged Clavain MCP servers (context7, qmd) from agent-rig.json
# - $KIMI_CODE_HOME/config.toml managed hooks block (via scripts/kimi-hook-bridge.sh)
# - $KIMI_CODE_HOME/AGENTS.md managed Kimi tool map block
#
# Mirrors os/Clavain/scripts/install-codex.sh structure and idioms.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Script lives at <repo>/os/Clavain/scripts/install-kimi.sh — repo root is three levels up.
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

ACTION="${1:-install}"
shift || true

SOURCE_DIR=""
DOCTOR_JSON=0

AGENTS_SKILLS_DIR="${AGENTS_SKILLS_DIR:-$HOME/.agents/skills}"
KIMI_CODE_HOME="${KIMI_CODE_HOME:-$HOME/.kimi-code}"
KIMI_CONFIG_FILE="${KIMI_CONFIG_FILE:-$KIMI_CODE_HOME/config.toml}"
KIMI_AGENTS_FILE="${KIMI_AGENTS_FILE:-$KIMI_CODE_HOME/AGENTS.md}"
KIMI_MCP_FILE="${KIMI_MCP_FILE:-$KIMI_CODE_HOME/mcp.json}"
BACKUP_ROOT="${CLAVAIN_KIMI_BACKUP_ROOT:-$KIMI_CODE_HOME/.clavain-backups}"

HOOKS_BLOCK_START="# BEGIN CLAVAIN KIMI HOOKS"
HOOKS_BLOCK_END="# END CLAVAIN KIMI HOOKS"
AGENTS_BLOCK_START="<!-- BEGIN CLAVAIN KIMI TOOL MAP -->"
AGENTS_BLOCK_END="<!-- END CLAVAIN KIMI TOOL MAP -->"

KIMI_HOOK_BRIDGE="${KIMI_HOOK_BRIDGE:-$REPO_ROOT/scripts/kimi-hook-bridge.sh}"
MANIFEST_GENERATOR="${MANIFEST_GENERATOR:-$REPO_ROOT/scripts/gen-kimi-manifests.py}"

BACKUP_SESSION_ROOT=""

usage() {
  cat <<'USAGE'
Usage:
  install-kimi.sh install [options]
  install-kimi.sh update [options]
  install-kimi.sh doctor [--json]
  install-kimi.sh uninstall [options]

Options:
  --source <path>      Use an existing Clavain checkout as source.
  --json               Output doctor check results as JSON.
  --kimi-home <path>   Override Kimi Code home root (default: ~/.kimi-code).
  -h, --help           Show this help.

Environment overrides:
  KIMI_CODE_HOME           Kimi Code home (default: ~/.kimi-code)
  AGENTS_SKILLS_DIR        Shared skills dir (default: ~/.agents/skills)
  CLAVAIN_KIMI_BACKUP_ROOT Backup root (default: $KIMI_CODE_HOME/.clavain-backups)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --json)
      DOCTOR_JSON=1
      shift
      ;;
    --kimi-home)
      KIMI_CODE_HOME="$2"
      KIMI_CONFIG_FILE="$KIMI_CODE_HOME/config.toml"
      KIMI_AGENTS_FILE="$KIMI_CODE_HOME/AGENTS.md"
      KIMI_MCP_FILE="$KIMI_CODE_HOME/mcp.json"
      BACKUP_ROOT="$KIMI_CODE_HOME/.clavain-backups"
      shift 2
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

is_clavain_root() {
  local dir="$1"
  [[ -f "$dir/README.md" && -d "$dir/skills" && -d "$dir/commands" && -d "$dir/scripts" ]]
}

json_escape() {
  local input="$1"
  input="${input//\\/\\\\}"
  input="${input//\"/\\\"}"
  input="${input//$'\n'/\\n}"
  input="${input//$'\r'/}"
  input="${input//$'\t'/\\t}"
  printf '%s' "$input"
}

start_backup_session() {
  if [[ -n "$BACKUP_SESSION_ROOT" ]]; then
    return 0
  fi
  local ts
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP_SESSION_ROOT="$BACKUP_ROOT/$ts"
  mkdir -p "$BACKUP_SESSION_ROOT"
}

backup_copy_file() {
  local src="$1"
  [[ -f "$src" ]] || return 0
  start_backup_session
  local dest="$BACKUP_SESSION_ROOT/${src#/}"
  mkdir -p "$(dirname "$dest")"
  cp -a "$src" "$dest"
}

backup_move_path() {
  local src="$1"
  [[ -e "$src" || -L "$src" ]] || return 0
  start_backup_session
  local dest="$BACKUP_SESSION_ROOT/${src#/}"
  mkdir -p "$(dirname "$dest")"
  mv "$src" "$dest"
  echo "Moved to backup: $src -> $dest"
}

resolve_source_dir() {
  if [[ -n "$SOURCE_DIR" ]]; then
    SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd -P)"
    if ! is_clavain_root "$SOURCE_DIR"; then
      echo "Invalid --source path (not a Clavain root): $SOURCE_DIR" >&2
      exit 1
    fi
    return
  fi

  # Infer from existing install: if the skills symlink points to a valid
  # Clavain root, use that.
  local agents_link="$AGENTS_SKILLS_DIR/clavain"
  if [[ -L "$agents_link" ]]; then
    local link_target
    link_target="$(readlink -f "$agents_link" 2>/dev/null || readlink "$agents_link")"
    # link_target is <clavain-root>/skills — parent should be the root
    local inferred_root="${link_target%/skills}"
    if [[ "$inferred_root" != "$link_target" ]] && is_clavain_root "$inferred_root"; then
      SOURCE_DIR="$inferred_root"
      return
    fi
  fi

  local script_root
  script_root="$(cd "$SCRIPT_DIR/.." && pwd)"
  if is_clavain_root "$script_root"; then
    SOURCE_DIR="$script_root"
    return
  fi

  echo "Cannot resolve Clavain source; pass --source <path>." >&2
  exit 1
}

safe_link_skills() {
  local target="$1"
  local link_path="$2"
  mkdir -p "$(dirname "$link_path")"

  if [[ -L "$link_path" ]]; then
    local current
    current="$(readlink "$link_path")"
    if [[ "$current" == "$target" ]]; then
      echo "OK symlink: $link_path -> $target"
      return 0
    fi
    rm -f "$link_path"
  elif [[ -e "$link_path" ]]; then
    # Non-symlink dir/file in the shared skills dir: back up before replacing.
    backup_move_path "$link_path"
  fi

  ln -s "$target" "$link_path"
  echo "Linked: $link_path -> $target"
}

update_file_with_block() {
  local file="$1"
  local start_marker="$2"
  local end_marker="$3"
  local block_content="$4"

  local candidate
  candidate="$(mktemp)"

  # Write block content to temp file — BSD awk (macOS) doesn't allow newlines in -v values
  local block_file
  block_file="$(mktemp)"
  printf '%s\n' "$block_content" > "$block_file"

  if [[ ! -f "$file" ]]; then
    cp "$block_file" "$candidate"
  else
    awk -v start="$start_marker" -v end="$end_marker" -v blockfile="$block_file" '
      BEGIN { in_block = 0; replaced = 0 }
      index($0, start) {
        if (!replaced) { while ((getline line < blockfile) > 0) print line; close(blockfile); replaced = 1 }
        in_block = 1; next
      }
      index($0, end)   { in_block = 0; next }
      !in_block        { print }
      END {
        if (!replaced) {
          if (NR > 0) print ""
          while ((getline line < blockfile) > 0) print line; close(blockfile)
        }
      }
    ' "$file" > "$candidate"
  fi
  rm -f "$block_file"

  if [[ -f "$file" ]] && cmp -s "$file" "$candidate"; then
    rm -f "$candidate"
    return 1
  fi

  if [[ -f "$file" ]]; then
    backup_copy_file "$file"
  fi

  mkdir -p "$(dirname "$file")"
  mv "$candidate" "$file"
  return 0
}

remove_block_from_file() {
  local file="$1"
  local start_marker="$2"
  local end_marker="$3"

  [[ -f "$file" ]] || return 1
  if ! grep -Fq "$start_marker" "$file" || ! grep -Fq "$end_marker" "$file"; then
    return 1
  fi

  local candidate
  candidate="$(mktemp)"

  awk -v start="$start_marker" -v end="$end_marker" '
    BEGIN { in_block = 0 }
    index($0, start) { in_block = 1; next }
    index($0, end)   { in_block = 0; next }
    !in_block        { print }
  ' "$file" > "$candidate"

  if cmp -s "$file" "$candidate"; then
    rm -f "$candidate"
    return 1
  fi

  backup_copy_file "$file"
  mv "$candidate" "$file"
  return 0
}

toml_literal() {
  # TOML literal string (single-quoted, no escapes). Refuse single quotes.
  local value="$1"
  if [[ "$value" == *"'"* ]]; then
    echo "Path contains a single quote, cannot render as TOML literal: $value" >&2
    exit 1
  fi
  printf "'%s'" "$value"
}

build_hooks_block() {
  local bridge="$KIMI_HOOK_BRIDGE"
  local hooks_dir="$SOURCE_DIR/hooks"

  # Small high-value subset of hooks/hooks.json, following the Codex adapter's
  # graceful-degradation precedent. Absolute paths baked at install time; the
  # bridge sets CLAUDE_PLUGIN_ROOT so the scripts run unmodified.
  cat <<BLOCK
$HOOKS_BLOCK_START
# Managed by Clavain install-kimi.sh — do not edit between the markers.
# Kimi hook entries allow exactly: event, matcher, command, timeout (1-600s).

[[hooks]]
event = "UserPromptSubmit"
command = $(toml_literal "env CLAVAIN_CONTEXT_GATEWAY_HARNESS=kimi $bridge $hooks_dir/context-gateway.sh")
timeout = 30

[[hooks]]
event = "SessionStart"
matcher = "startup|resume"
command = $(toml_literal "$bridge $hooks_dir/session-start.sh")
timeout = 30

[[hooks]]
event = "SessionStart"
matcher = "startup|resume"
command = $(toml_literal "$bridge $hooks_dir/peer-telemetry.sh")
timeout = 3

[[hooks]]
event = "PreToolUse"
matcher = "Edit|Write"
command = $(toml_literal "$bridge $hooks_dir/guard-plugin-cache.sh")
timeout = 5

[[hooks]]
event = "PostToolUse"
matcher = "Bash"
command = $(toml_literal "$bridge $hooks_dir/auto-publish.sh")
timeout = 15

[[hooks]]
event = "PostToolUse"
matcher = "Bash"
command = $(toml_literal "$bridge $hooks_dir/bead-agent-bind.sh")
timeout = 5

[[hooks]]
event = "Stop"
command = $(toml_literal "$bridge $hooks_dir/auto-stop-actions.sh")
timeout = 5
$HOOKS_BLOCK_END
BLOCK
}

build_agents_block() {
  cat <<BLOCK
$AGENTS_BLOCK_START
## Clavain Kimi Code Tool Mapping

This block is managed automatically by \`install-kimi.sh\`.

Kimi Code reads AGENTS.md natively, so Clavain's instructions apply as-is.
Only the tool surface differs from Claude Code:

Tool mapping deltas:
- \`MultiEdit\` -> \`Edit\` (Kimi has no MultiEdit; apply edits sequentially)
- \`TodoWrite\` -> \`TodoList\`
- \`Task\` -> \`Agent\` tool (built-in coder/explore/plan subagent types only).
  Clavain's custom \`agents/*.md\` definitions are NOT loadable in Kimi;
  use skills + Agent dispatch instead.
- Slash commands \`/clavain:<cmd>\` are available when Clavain is installed as
  a Kimi plugin; otherwise open \`commands/<cmd>.md\` directly and follow it.
- \`AskUserQuestion\` and \`Skill\` exist natively — use them unchanged.
$AGENTS_BLOCK_END
BLOCK
}

install_skills_link() {
  local skills_target="$SOURCE_DIR/skills"
  if [[ ! -d "$skills_target" ]]; then
    echo "Missing skills directory: $skills_target" >&2
    exit 1
  fi
  safe_link_skills "$skills_target" "$AGENTS_SKILLS_DIR/clavain"
}

run_manifest_generator() {
  if [[ ! -f "$MANIFEST_GENERATOR" ]]; then
    echo "WARN: Kimi manifest generator not found, skipping: $MANIFEST_GENERATOR" >&2
    return 0
  fi
  if python3 "$MANIFEST_GENERATOR" --root "$REPO_ROOT" --plugin clavain; then
    echo "Generated Kimi plugin manifests (kimi.plugin.json)."
  else
    echo "WARN: Kimi manifest generator failed (non-fatal, continuing): $MANIFEST_GENERATOR" >&2
  fi
}

sync_kimi_mcp() {
  if ! command -v jq >/dev/null 2>&1; then
    echo "WARN: jq not found; skipping MCP merge into $KIMI_MCP_FILE" >&2
    return 0
  fi

  local rig="$SOURCE_DIR/agent-rig.json"
  if [[ ! -f "$rig" ]]; then
    echo "WARN: agent-rig.json missing, skipping MCP sync: $rig" >&2
    return 0
  fi

  local server_count
  server_count="$(jq -r '(.mcpServers // {}) | length' "$rig" 2>/dev/null || echo 0)"
  if [[ "$server_count" == "0" ]]; then
    echo "No MCP servers declared in agent-rig.json; skipping MCP sync."
    return 0
  fi

  local source_file
  source_file="$(mktemp)"
  if [[ -f "$KIMI_MCP_FILE" ]]; then
    if ! jq -e 'type == "object"' "$KIMI_MCP_FILE" >/dev/null 2>&1; then
      rm -f "$source_file"
      echo "WARN: malformed mcp.json, refusing to merge: $KIMI_MCP_FILE" >&2
      return 0
    fi
    cp -f "$KIMI_MCP_FILE" "$source_file"
  else
    printf '{"mcpServers":{}}\n' > "$source_file"
  fi

  local candidate
  candidate="$(mktemp)"
  # Preserve existing entries; add/refresh Clavain's entries from agent-rig.json.
  # Strip Claude-ism fields (type, description) — Kimi's mcp.json infers
  # transport from command vs url and ignores extra metadata.
  jq -s '
    .[0] as $base | .[1] as $rig
    | $base + {mcpServers: (($base.mcpServers // {}) + (($rig.mcpServers // {})
        | with_entries(.value |= del(.type, .description))))}
  ' "$source_file" "$rig" > "$candidate"
  rm -f "$source_file"

  if [[ -f "$KIMI_MCP_FILE" ]] && cmp -s "$KIMI_MCP_FILE" "$candidate"; then
    rm -f "$candidate"
    echo "Kimi MCP config already up to date: $KIMI_MCP_FILE"
    return 0
  fi

  backup_copy_file "$KIMI_MCP_FILE"
  mkdir -p "$(dirname "$KIMI_MCP_FILE")"
  mv -f "$candidate" "$KIMI_MCP_FILE"
  echo "Merged Clavain MCP servers into: $KIMI_MCP_FILE"
}

remove_kimi_mcp() {
  [[ -f "$KIMI_MCP_FILE" ]] || return 0
  if ! command -v jq >/dev/null 2>&1; then
    echo "WARN: jq not found; cannot remove merged MCP entries from $KIMI_MCP_FILE" >&2
    return 0
  fi

  local rig="$SOURCE_DIR/agent-rig.json"
  [[ -f "$rig" ]] || return 0

  if ! jq -e 'type == "object"' "$KIMI_MCP_FILE" >/dev/null 2>&1; then
    echo "WARN: malformed mcp.json, skipping MCP cleanup: $KIMI_MCP_FILE" >&2
    return 0
  fi

  local candidate
  candidate="$(mktemp)"
  # Remove only the keys Clavain contributed; keep everything else.
  jq -s '
    .[0] as $base | .[1] as $rig
    | $base + {mcpServers: (
        ($base.mcpServers // {})
        | with_entries(select(.key as $k | (($rig.mcpServers // {}) | has($k)) | not))
      )}
  ' "$KIMI_MCP_FILE" "$rig" > "$candidate"

  if cmp -s "$KIMI_MCP_FILE" "$candidate"; then
    rm -f "$candidate"
    return 0
  fi

  backup_copy_file "$KIMI_MCP_FILE"
  mv -f "$candidate" "$KIMI_MCP_FILE"
  echo "Removed Clavain MCP servers from: $KIMI_MCP_FILE"
}

# Returns 0 when the clavain plugin is installed and enabled in Kimi's own
# plugin manager. In that state the plugin's kimi.plugin.json already carries
# the full hook set, so the config.toml hooks block must NOT be installed —
# otherwise every hook fires twice.
clavain_plugin_enabled() {
  local installed_json="$KIMI_CODE_HOME/plugins/installed.json"
  [[ -f "$installed_json" ]] || return 1
  python3 - "$installed_json" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
for plugin in data.get("plugins", []):
    if plugin.get("id") == "clavain" and plugin.get("enabled"):
        sys.exit(0)
sys.exit(1)
PY
}

install_managed_hooks_block() {
  if clavain_plugin_enabled; then
    remove_block_from_file "$KIMI_CONFIG_FILE" "$HOOKS_BLOCK_START" "$HOOKS_BLOCK_END" || true
    echo "clavain plugin is installed and enabled; skipping config.toml hooks block (plugin manifest owns the hooks)."
    return 0
  fi
  local block
  block="$(build_hooks_block)"
  if update_file_with_block "$KIMI_CONFIG_FILE" "$HOOKS_BLOCK_START" "$HOOKS_BLOCK_END" "$block"; then
    echo "Updated managed hooks block: $KIMI_CONFIG_FILE"
  else
    echo "Managed hooks block already up to date: $KIMI_CONFIG_FILE"
  fi
}

install_managed_agents_block() {
  local block
  block="$(build_agents_block)"
  if update_file_with_block "$KIMI_AGENTS_FILE" "$AGENTS_BLOCK_START" "$AGENTS_BLOCK_END" "$block"; then
    echo "Updated managed AGENTS block: $KIMI_AGENTS_FILE"
  else
    echo "Managed AGENTS block already up to date: $KIMI_AGENTS_FILE"
  fi
}

install_all() {
  resolve_source_dir

  mkdir -p "$KIMI_CODE_HOME"

  install_skills_link
  run_manifest_generator
  sync_kimi_mcp
  install_managed_hooks_block
  install_managed_agents_block

  echo
  echo "Install complete."
  echo "Restart Kimi Code so it reloads skills/MCP/hooks."
}

doctor() {
  resolve_source_dir

  local skills_target="$SOURCE_DIR/skills"
  local agents_link="$AGENTS_SKILLS_DIR/clavain"

  local status=0
  local issues=()

  local root_ok="false"
  local kimi_present="false"
  local agents_link_ok="false"
  local agents_link_match="false"
  local source_agents_link=""
  local mcp_file_ok="false"
  local mcp_entries_ok="false"
  local hooks_block_ok="false"
  local agents_block_ok="false"
  local bridge_ok="false"
  local manifest_generator_present="false"
  local context_gateway_hook_present="false"
  local context_gateway_tldrs_executable="false"
  local context_gateway_packet_schema="false"
  local context_gateway_receipt_directory="false"

  local skill_dir_count=0
  local mcp_server_count=0

  if [[ "$DOCTOR_JSON" -eq 0 ]]; then
    echo "== Clavain Kimi Doctor =="
    echo "Source dir: $SOURCE_DIR"
    echo
  fi

  if ! is_clavain_root "$SOURCE_DIR"; then
    issues+=("Source dir missing required Clavain structure: $SOURCE_DIR")
    status=1
  else
    root_ok="true"
  fi

  if command -v kimi >/dev/null 2>&1; then
    kimi_present="true"
  fi

  if [[ "$DOCTOR_JSON" -eq 0 ]]; then
    if [[ "$kimi_present" == "true" ]]; then
      echo "kimi CLI:             present"
    else
      echo "kimi CLI:             missing (informational)"
    fi
  fi

  if [[ -L "$agents_link" ]]; then
    agents_link_ok="true"
    source_agents_link="$(readlink -f "$agents_link" 2>/dev/null || readlink "$agents_link")"
    if [[ "$source_agents_link" == "$skills_target" && -d "$agents_link" ]]; then
      agents_link_match="true"
      if [[ "$DOCTOR_JSON" -eq 0 ]]; then
        echo "agents skills link:   $agents_link -> $source_agents_link"
      fi
    else
      issues+=("agents skills link broken or target mismatch: $agents_link -> $source_agents_link (expected $skills_target)")
      status=1
    fi
  else
    issues+=("agents skills link missing: $agents_link")
    status=1
  fi

  if [[ -f "$KIMI_MCP_FILE" ]] && command -v jq >/dev/null 2>&1; then
    if jq -e 'type == "object"' "$KIMI_MCP_FILE" >/dev/null 2>&1; then
      mcp_file_ok="true"
      mcp_server_count="$(jq -r '(.mcpServers // {}) | length' "$KIMI_MCP_FILE")"
      local rig="$SOURCE_DIR/agent-rig.json"
      if [[ -f "$rig" ]]; then
        local missing
        missing="$(jq -s -r '
          .[0] as $kimi | .[1] as $rig
          | [($rig.mcpServers // {}) | keys[]
             | select(. as $k | (($kimi.mcpServers // {}) | has($k)) | not)]
          | .[]
        ' "$KIMI_MCP_FILE" "$rig")"
        if [[ -z "$missing" ]]; then
          mcp_entries_ok="true"
        else
          issues+=("mcp.json missing Clavain MCP entries: $(echo "$missing" | tr '\n' ' ')($KIMI_MCP_FILE)")
          status=1
        fi
      fi
    else
      issues+=("mcp.json does not parse as a JSON object: $KIMI_MCP_FILE")
      status=1
    fi
  else
    issues+=("mcp.json missing (or jq unavailable): $KIMI_MCP_FILE")
    status=1
  fi

  if [[ -f "$KIMI_CONFIG_FILE" ]] \
    && grep -Fq "$HOOKS_BLOCK_START" "$KIMI_CONFIG_FILE" \
    && grep -Fq "$HOOKS_BLOCK_END" "$KIMI_CONFIG_FILE"; then
    hooks_block_ok="true"
    if grep -Fq 'event = "UserPromptSubmit"' "$KIMI_CONFIG_FILE" \
      && grep -Fq "CLAVAIN_CONTEXT_GATEWAY_HARNESS=kimi" "$KIMI_CONFIG_FILE" \
      && grep -Fq "context-gateway.sh" "$KIMI_CONFIG_FILE"; then
      context_gateway_hook_present="true"
    else
      issues+=("managed Kimi UserPromptSubmit context gateway hook missing: $KIMI_CONFIG_FILE")
      status=1
    fi
  elif clavain_plugin_enabled; then
    # Plugin route: kimi.plugin.json owns the hooks; config block intentionally absent.
    hooks_block_ok="true"
    if [[ -f "$SOURCE_DIR/kimi.plugin.json" ]] \
      && jq -e '
        [.hooks[]?
         | select(.event == "UserPromptSubmit")
         | select((.command // "") | contains("context-gateway.sh"))]
        | length == 1
      ' "$SOURCE_DIR/kimi.plugin.json" >/dev/null 2>&1; then
      context_gateway_hook_present="true"
    else
      issues+=("Kimi plugin UserPromptSubmit context gateway hook missing: $SOURCE_DIR/kimi.plugin.json")
      status=1
    fi
  else
    issues+=("managed hooks block missing or malformed: $KIMI_CONFIG_FILE")
    status=1
  fi

  if [[ -f "$KIMI_AGENTS_FILE" ]] \
    && grep -Fq "$AGENTS_BLOCK_START" "$KIMI_AGENTS_FILE" \
    && grep -Fq "$AGENTS_BLOCK_END" "$KIMI_AGENTS_FILE"; then
    agents_block_ok="true"
  else
    issues+=("managed AGENTS block missing or malformed: $KIMI_AGENTS_FILE")
    status=1
  fi

  if [[ -x "$KIMI_HOOK_BRIDGE" ]]; then
    bridge_ok="true"
  else
    issues+=("kimi-hook-bridge.sh missing or not executable: $KIMI_HOOK_BRIDGE")
    status=1
  fi

  if [[ -f "$MANIFEST_GENERATOR" ]]; then
    manifest_generator_present="true"
  fi

  local gateway_doctor="$SOURCE_DIR/scripts/context-gateway.py"
  local gateway_report=""
  if [[ -x "$gateway_doctor" ]]; then
    gateway_report="$("$gateway_doctor" doctor --project "$SOURCE_DIR" --json 2>/dev/null)" || true
    if [[ -n "$gateway_report" ]] && jq -e '.checks.tldrs_executable.ok == true' <<<"$gateway_report" >/dev/null 2>&1; then
      context_gateway_tldrs_executable="true"
    else
      issues+=("context gateway cannot resolve tldrs executable")
      status=1
    fi
    if [[ -n "$gateway_report" ]] && jq -e '.checks.packet_schema.ok == true' <<<"$gateway_report" >/dev/null 2>&1; then
      context_gateway_packet_schema="true"
    else
      issues+=("context gateway tldrs packet schema check failed")
      status=1
    fi
    if [[ -n "$gateway_report" ]] && jq -e '.checks.receipt_directory.ok == true' <<<"$gateway_report" >/dev/null 2>&1; then
      context_gateway_receipt_directory="true"
    else
      issues+=("context gateway receipt directory is not writable")
      status=1
    fi
  else
    issues+=("context gateway missing or not executable: $gateway_doctor")
    status=1
  fi

  if [[ -d "$skills_target" ]]; then
    skill_dir_count="$(find "$skills_target" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
  fi

  if [[ "$DOCTOR_JSON" -eq 1 ]]; then
    local status_text="fail"
    if [[ "$status" -eq 0 ]]; then
      status_text="ok"
    fi

    printf '{\n'
    printf '  "status":"%s",\n' "$status_text"
    printf '  "source_dir":"%s",\n' "$(json_escape "$SOURCE_DIR")"
    printf '  "issues_count":%s,\n' "${#issues[@]}"
    printf '  "checks":{\n'
    printf '    "clavain_root":%s,\n' "$root_ok"
    printf '    "kimi_cli_present":%s,\n' "$kimi_present"
    printf '    "agents_skills_link_exists":%s,\n' "$agents_link_ok"
    printf '    "agents_skills_link_match":%s,\n' "$agents_link_match"
    printf '    "agents_skills_link_target":"%s",\n' "$(json_escape "$source_agents_link")"
    printf '    "mcp_file_present_and_parses":%s,\n' "$mcp_file_ok"
    printf '    "mcp_clavain_entries_present":%s,\n' "$mcp_entries_ok"
    printf '    "managed_hooks_block_present":%s,\n' "$hooks_block_ok"
    printf '    "managed_agents_block_present":%s,\n' "$agents_block_ok"
    printf '    "hook_bridge_executable":%s,\n' "$bridge_ok"
    printf '    "manifest_generator_present":%s,\n' "$manifest_generator_present"
    printf '    "context_gateway_hook_present":%s,\n' "$context_gateway_hook_present"
    printf '    "context_gateway_tldrs_executable":%s,\n' "$context_gateway_tldrs_executable"
    printf '    "context_gateway_packet_schema":%s,\n' "$context_gateway_packet_schema"
    printf '    "context_gateway_receipt_directory":%s\n' "$context_gateway_receipt_directory"
    printf '  },\n'
    printf '  "counts":{\n'
    printf '    "skill_dirs":%s,\n' "$skill_dir_count"
    printf '    "mcp_servers":%s\n' "$mcp_server_count"
    printf '  },\n'
    printf '  "paths":{\n'
    printf '    "kimi_code_home":"%s",\n' "$(json_escape "$KIMI_CODE_HOME")"
    printf '    "config_file":"%s",\n' "$(json_escape "$KIMI_CONFIG_FILE")"
    printf '    "agents_file":"%s",\n' "$(json_escape "$KIMI_AGENTS_FILE")"
    printf '    "mcp_file":"%s",\n' "$(json_escape "$KIMI_MCP_FILE")"
    printf '    "hook_bridge":"%s",\n' "$(json_escape "$KIMI_HOOK_BRIDGE")"
    printf '    "backup_root":"%s"\n' "$(json_escape "$BACKUP_ROOT")"
    printf '  },\n'
    printf '  "issues":['

    local comma="" issue
    for issue in "${issues[@]}"; do
      printf '%s\n    "%s"' "$comma" "$(json_escape "$issue")"
      comma=","
    done
    printf '\n  ]\n'
    printf '}\n'

    if [[ "$status" -eq 0 ]]; then
      return 0
    fi
    return 1
  fi

  echo
  echo "skill dirs in source:   $skill_dir_count"
  echo "mcp servers configured: $mcp_server_count"
  echo "managed hooks block:    present=$hooks_block_ok"
  echo "managed AGENTS block:   present=$agents_block_ok"
  echo "hook bridge executable: $bridge_ok"
  echo

  if [[ "$status" -eq 0 ]]; then
    echo "Doctor checks passed."
    return 0
  fi

  echo "Doctor checks completed with issues." >&2
  return 1
}

uninstall_all() {
  resolve_source_dir

  local agents_link="$AGENTS_SKILLS_DIR/clavain"
  if [[ -L "$agents_link" ]]; then
    rm -f "$agents_link"
    echo "Removed skills symlink: $agents_link"
  fi

  remove_kimi_mcp || true
  remove_block_from_file "$KIMI_CONFIG_FILE" "$HOOKS_BLOCK_START" "$HOOKS_BLOCK_END" || true
  remove_block_from_file "$KIMI_AGENTS_FILE" "$AGENTS_BLOCK_START" "$AGENTS_BLOCK_END" || true

  echo "Uninstall complete. Backups preserved under: $BACKUP_ROOT"
}

case "$ACTION" in
  install)
    install_all
    ;;
  update)
    install_all
    ;;
  doctor)
    doctor
    ;;
  uninstall)
    uninstall_all
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    usage >&2
    exit 1
    ;;
esac
