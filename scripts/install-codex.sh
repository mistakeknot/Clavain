#!/usr/bin/env bash
# Install Clavain for Codex native skill discovery.
#
# What this script sets up:
# - ~/.agents/skills/clavain  -> <clavain>/skills
# - ~/.codex/prompts/clavain-*.md prompt wrappers generated from commands/*.md
# - ~/.codex/AGENTS.md managed Clavain Codex tool map block
# - ~/.codex/config.toml managed MCP server block synced from .claude-plugin/plugin.json
#
# Clean-break policy:
# - Removes legacy ~/.codex/skills/clavain path (symlink or directory) with backup-first safety.

set -euo pipefail

REPO_URL_DEFAULT="https://github.com/mistakeknot/Clavain.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ACTION="${1:-install}"
shift || true

SOURCE_DIR=""
SOURCE_EXPLICIT=0
CLONE_DIR="${CLAVAIN_CLONE_DIR:-$HOME/.codex/clavain}"
REPO_URL="${CLAVAIN_REPO_URL:-$REPO_URL_DEFAULT}"
INSTALL_PROMPTS=1
REMOVE_CLONE=0
DOCTOR_JSON=0

AGENTS_SKILLS_DIR="${AGENTS_SKILLS_DIR:-$HOME/.agents/skills}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
CODEX_PROMPTS_DIR="${CODEX_PROMPTS_DIR:-$CODEX_HOME/prompts}"
CODEX_SKILLS_DIR="${CODEX_SKILLS_DIR:-$CODEX_HOME/skills}"
CODEX_AGENTS_FILE="${CODEX_AGENTS_FILE:-$CODEX_HOME/AGENTS.md}"
CODEX_CONFIG_FILE="${CODEX_CONFIG_FILE:-$CODEX_HOME/config.toml}"
BACKUP_ROOT="${CLAVAIN_BACKUP_ROOT:-$CODEX_HOME/.clavain-backups}"
CONVERSION_REPORT_FILE="${CLAVAIN_CONVERSION_REPORT_FILE:-$CODEX_PROMPTS_DIR/.clavain-conversion-report.json}"

AGENTS_BLOCK_START="<!-- BEGIN CLAVAIN CODEX TOOL MAP -->"
AGENTS_BLOCK_END="<!-- END CLAVAIN CODEX TOOL MAP -->"
MCP_BLOCK_START="# BEGIN CLAVAIN MCP SERVERS"
MCP_BLOCK_END="# END CLAVAIN MCP SERVERS"

BACKUP_SESSION_ROOT=""

usage() {
  cat <<'USAGE'
Usage:
  install-codex.sh install [options]
  install-codex.sh update [options]
  install-codex.sh doctor [--json]
  install-codex.sh uninstall [--remove-clone]

Options:
  --source <path>      Use an existing Clavain checkout as source.
  --clone-dir <path>   Clone/update target (default: ~/.codex/clavain)
  --repo-url <url>     Repo URL for clone/update.
  --no-prompts         Skip generating prompt wrappers in ~/.codex/prompts.
  --remove-clone       With uninstall, delete clone dir too.
  --json               Output doctor check results as JSON.
  --codex-home <path>  Override Codex home root (default: ~/.codex).
  -h, --help           Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE_DIR="$2"
      SOURCE_EXPLICIT=1
      shift 2
      ;;
    --clone-dir)
      CLONE_DIR="$2"
      shift 2
      ;;
    --repo-url)
      REPO_URL="$2"
      shift 2
      ;;
    --no-prompts)
      INSTALL_PROMPTS=0
      shift
      ;;
    --remove-clone)
      REMOVE_CLONE=1
      shift
      ;;
    --json)
      DOCTOR_JSON=1
      shift
      ;;
    --codex-home)
      CODEX_HOME="$2"
      CODEX_PROMPTS_DIR="$CODEX_HOME/prompts"
      CODEX_SKILLS_DIR="$CODEX_HOME/skills"
      CODEX_AGENTS_FILE="$CODEX_HOME/AGENTS.md"
      CODEX_CONFIG_FILE="$CODEX_HOME/config.toml"
      BACKUP_ROOT="$CODEX_HOME/.clavain-backups"
      CONVERSION_REPORT_FILE="$CODEX_PROMPTS_DIR/.clavain-conversion-report.json"
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

ensure_clone() {
  mkdir -p "$(dirname "$CLONE_DIR")"
  if [[ -d "$CLONE_DIR/.git" ]]; then
    echo "Updating clone at $CLONE_DIR"
    git -C "$CLONE_DIR" pull --ff-only
  else
    if [[ -e "$CLONE_DIR" ]]; then
      echo "Refusing to clone into existing non-git path: $CLONE_DIR" >&2
      exit 1
    fi
    echo "Cloning $REPO_URL -> $CLONE_DIR"
    git clone "$REPO_URL" "$CLONE_DIR"
  fi
}

resolve_source_dir() {
  if [[ -n "$SOURCE_DIR" ]]; then
    SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"
    if ! is_clavain_root "$SOURCE_DIR"; then
      echo "Invalid --source path (not a Clavain root): $SOURCE_DIR" >&2
      exit 1
    fi
    return
  fi

  local script_root
  script_root="$(cd "$SCRIPT_DIR/.." && pwd)"
  if is_clavain_root "$script_root"; then
    SOURCE_DIR="$script_root"
    return
  fi

  ensure_clone
  SOURCE_DIR="$CLONE_DIR"
}

safe_link() {
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
    echo "Skip non-symlink path (manual cleanup needed): $link_path" >&2
    return 1
  fi

  ln -s "$target" "$link_path"
  echo "Linked: $link_path -> $target"
}

regex_escape() {
  printf '%s' "$1" | sed -e 's/[.[\*^$()+?{|\\]/\\&/g'
}

toml_key() {
  local key="$1"
  if [[ "$key" =~ ^[A-Za-z0-9_-]+$ ]]; then
    printf '%s' "$key"
  else
    printf '%s' "\"$(json_escape "$key")\""
  fi
}

toml_string() {
  local value="$1"
  if command -v jq >/dev/null 2>&1; then
    jq -Rn --arg v "$value" -r '$v|@json'
  else
    printf '"%s"' "$(json_escape "$value")"
  fi
}

strip_frontmatter() {
  local file="$1"
  awk '
    NR == 1 && $0 == "---" { in_fm = 1; next }
    in_fm == 1 && $0 == "---" { in_fm = 0; next }
    in_fm == 0 { print }
  ' "$file"
}

collect_command_names() {
  local commands_dir="$1"
  local out_file="$2"
  : > "$out_file"
  local src name
  for src in "$commands_dir"/*.md; do
    [[ -f "$src" ]] || continue
    name="$(basename "$src" .md)"
    echo "$name" >> "$out_file"
  done
}

collect_skill_names() {
  local skills_dir="$1"
  local out_file="$2"
  : > "$out_file"
  local skill_dir
  for skill_dir in "$skills_dir"/*; do
    [[ -d "$skill_dir" ]] || continue
    [[ -f "$skill_dir/SKILL.md" ]] || continue
    basename "$skill_dir" >> "$out_file"
  done
}

build_command_regex() {
  local names_file="$1"
  local regex=""
  local name escaped
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    escaped="$(regex_escape "$name")"
    regex+="${regex:+|}$escaped"
  done < "$names_file"
  printf '%s' "$regex"
}

convert_body_for_codex() {
  local input_file="$1"
  local output_file="$2"
  local stats_file="$3"
  local command_regex="$4"

  CLAVAIN_COMMAND_REGEX="$command_regex" perl -0777 - "$input_file" >"$output_file" 2>"$stats_file" <<'PERL'
use strict;
use warnings;

my $re = $ENV{CLAVAIN_COMMAND_REGEX} // '';
local $/;
my $content = <>;
my ($namespaced, $bare, $path, $elicitation) = (0, 0, 0, 0);

if ($re ne '') {
  $namespaced += ($content =~ s{(?<![A-Za-z0-9_./:-])/clavain:($re)(?=(?:$|[\s\)\]\}\.,;:\!\?\'\"`]))}{"/prompts:clavain-$1"}ge);
  $bare += ($content =~ s{(?<![A-Za-z0-9_./:-])/(?!prompts:)(($re))(?=(?:$|[\s\)\]\}\.,;:\!\?\'\"`]))}{"/prompts:clavain-$1"}ge);
}

$path += ($content =~ s{\Q~/.claude/\E}{~/.codex/}g);
$path += ($content =~ s{(?<!~)\Q.claude/\E}{.codex/}g);

# AskUserQuestion is Claude-specific. Normalize to a Codex elicitation adapter contract.
$elicitation += ($content =~ s/\bAskUserQuestion tool\b/Codex elicitation adapter/g);
$elicitation += ($content =~ s/\bAskUserQuestion\b/Codex elicitation adapter/g);

print $content;
print STDERR "namespaced=$namespaced bare=$bare path=$path elicitation=$elicitation\n";
PERL
}

update_file_with_block() {
  local file="$1"
  local start_marker="$2"
  local end_marker="$3"
  local block_content="$4"

  local candidate
  candidate="$(mktemp)"

  if [[ ! -f "$file" ]]; then
    printf '%s\n' "$block_content" > "$candidate"
  else
    awk -v start="$start_marker" -v end="$end_marker" -v block="$block_content" '
      BEGIN { in_block = 0; replaced = 0 }
      index($0, start) { if (!replaced) { print block; replaced = 1 } in_block = 1; next }
      index($0, end)   { in_block = 0; next }
      !in_block        { print }
      END {
        if (!replaced) {
          if (NR > 0) print ""
          print block
        }
      }
    ' "$file" > "$candidate"
  fi

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

build_agents_block() {
  cat <<'BLOCK'
<!-- BEGIN CLAVAIN CODEX TOOL MAP -->
## Clavain Codex Tool Mapping

This block is managed automatically by `install-codex.sh`.

Tool mapping:
- `Read`: use shell reads (`cat`, `sed`) or `rg`
- `Write`: shell redirection or `apply_patch`
- `Edit`/`MultiEdit`: `apply_patch`
- `Bash`: shell command execution
- `Grep`: `rg`
- `Glob`: `rg --files` or `find`
- `Task`/`Subagent`: run in main thread; parallelize independent tool calls
- `TodoWrite`/`TodoRead`: file-based todos in `todos/`
- `Skill`: open referenced `SKILL.md`
- `AskUserQuestion`: use `request_user_input` if available; otherwise ask in chat with numbered options and pause for response

Bootstrap:
- Run `~/.codex/clavain/.codex/clavain-codex bootstrap` for a Codex-native quickstart.
<!-- END CLAVAIN CODEX TOOL MAP -->
BLOCK
}

render_mcp_block() {
  local manifest="$1"
  local output_file="$2"

  {
    echo "$MCP_BLOCK_START"
    echo "# Managed by Clavain install-codex.sh"
    echo ""
  } > "$output_file"

  if ! command -v jq >/dev/null 2>&1; then
    {
      echo "# jq not found; unable to sync MCP servers"
      echo "$MCP_BLOCK_END"
    } >> "$output_file"
    return 0
  fi

  local server_count
  server_count="$(jq -r '(.mcpServers // {}) | length' "$manifest" 2>/dev/null || echo 0)"
  if [[ "$server_count" == "0" ]]; then
    {
      echo "# No MCP servers declared in plugin manifest"
      echo "$MCP_BLOCK_END"
    } >> "$output_file"
    return 0
  fi

  local server_name
  while IFS= read -r server_name; do
    [[ -n "$server_name" ]] || continue

    local server_json
    server_json="$(jq -c --arg n "$server_name" '.mcpServers[$n]' "$manifest")"

    local table_key
    table_key="$(toml_key "$server_name")"

    echo "[mcp.servers.$table_key]" >> "$output_file"

    local command_val url_val args_line headers_line
    command_val="$(jq -r '.command // empty' <<<"$server_json")"
    url_val="$(jq -r '.url // empty' <<<"$server_json")"

    if [[ -n "$command_val" ]]; then
      echo "command = $(toml_string "$command_val")" >> "$output_file"
    fi

    args_line="$(jq -r 'if (.args|type=="array" and (.args|length)>0) then "args = [" + (.args|map(@json)|join(", ")) + "]" else empty end' <<<"$server_json")"
    if [[ -n "$args_line" ]]; then
      echo "$args_line" >> "$output_file"
    fi

    if [[ -n "$url_val" ]]; then
      echo "url = $(toml_string "$url_val")" >> "$output_file"
    fi

    headers_line="$(jq -r '
      if (.headers|type=="object" and (.headers|length)>0) then
        "http_headers = { " + (
          .headers
          | to_entries
          | map(
              ((if (.key|test("^[A-Za-z0-9_-]+$")) then .key else (.key|@json) end)
               + " = " + (.value|@json))
            )
          | join(", ")
        ) + " }"
      else
        empty
      end
    ' <<<"$server_json")"
    if [[ -n "$headers_line" ]]; then
      echo "$headers_line" >> "$output_file"
    fi

    local env_count
    env_count="$(jq -r 'if (.env|type=="object") then (.env|length) else 0 end' <<<"$server_json")"
    if [[ "$env_count" != "0" ]]; then
      echo "" >> "$output_file"
      echo "[mcp.servers.$table_key.env]" >> "$output_file"
      while IFS= read -r kv; do
        [[ -n "$kv" ]] || continue
        local k v
        k="$(jq -r '.key' <<<"$kv")"
        v="$(jq -r '.value' <<<"$kv")"
        echo "$(toml_key "$k") = $(toml_string "$v")" >> "$output_file"
      done < <(jq -c '.env | to_entries[]' <<<"$server_json")
    fi

    echo "" >> "$output_file"
  done < <(jq -r '.mcpServers // {} | keys[]' "$manifest")

  echo "$MCP_BLOCK_END" >> "$output_file"
}

remove_legacy_codex_skills_path() {
  local legacy_path="$CODEX_SKILLS_DIR/clavain"
  if [[ -L "$legacy_path" || -d "$legacy_path" || -f "$legacy_path" ]]; then
    backup_move_path "$legacy_path"
  fi
}

cleanup_known_legacy_wrappers() {
  local prompts_dir="$CODEX_PROMPTS_DIR"
  [[ -d "$prompts_dir" ]] || return 0

  local pf base cleaned=0
  for pf in "$prompts_dir"/*.md; do
    [[ -f "$pf" ]] || continue
    base="$(basename "$pf")"
    case "$base" in
      clavain-*)
        continue
        ;;
      workflows-compound.md|workflows-brainstorm.md|workflows-plan.md|workflows-review.md|workflows-work.md)
        backup_move_path "$pf"
        cleaned=$((cleaned + 1))
        ;;
      agent-native-audit.md|changelog.md|create-agent-skill.md|deepen-plan.md|deploy-docs.md|feature-video.md|generate_command.md|heal-skill.md|lfg.md|plan_review.md|release-docs.md|report-bug.md|reproduce-bug.md|resolve_parallel.md|resolve_pr_parallel.md|resolve_todo_parallel.md|test-browser.md|triage.md|xcode-test.md)
        backup_move_path "$pf"
        cleaned=$((cleaned + 1))
        ;;
    esac
  done

  if [[ "$cleaned" -gt 0 ]]; then
    echo "Removed $cleaned legacy prompt wrappers (backup-first)."
  fi
}

generate_prompts() {
  local commands_dir="$SOURCE_DIR/commands"

  mkdir -p "$CODEX_PROMPTS_DIR"

  local expected
  expected="$(mktemp)"
  local command_names
  command_names="$(mktemp)"
  local skill_names
  skill_names="$(mktemp)"
  local unresolved_refs
  unresolved_refs="$(mktemp)"

  collect_command_names "$commands_dir" "$command_names"
  collect_skill_names "$SOURCE_DIR/skills" "$skill_names"

  local command_regex
  command_regex="$(build_command_regex "$command_names")"

  local count=0
  local removed=0
  local namespaced_rewrites=0
  local bare_rewrites=0
  local path_rewrites=0
  local elicitation_rewrites=0

  local src
  for src in "$commands_dir"/*.md; do
    [[ -f "$src" ]] || continue

    local name out body_tmp converted_tmp stats_tmp
    name="$(basename "$src" .md)"
    out="$CODEX_PROMPTS_DIR/clavain-$name.md"
    echo "$name" >> "$expected"

    body_tmp="$(mktemp)"
    converted_tmp="$(mktemp)"
    stats_tmp="$(mktemp)"

    strip_frontmatter "$src" > "$body_tmp"
    convert_body_for_codex "$body_tmp" "$converted_tmp" "$stats_tmp" "$command_regex"

    local ns_count bare_count path_count elicit_count
    ns_count="$(sed -n 's/.*namespaced=\([0-9][0-9]*\).*/\1/p' "$stats_tmp" | head -1)"
    bare_count="$(sed -n 's/.*bare=\([0-9][0-9]*\).*/\1/p' "$stats_tmp" | head -1)"
    path_count="$(sed -n 's/.*path=\([0-9][0-9]*\).*/\1/p' "$stats_tmp" | head -1)"
    elicit_count="$(sed -n 's/.*elicitation=\([0-9][0-9]*\).*/\1/p' "$stats_tmp" | head -1)"
    ns_count="${ns_count:-0}"
    bare_count="${bare_count:-0}"
    path_count="${path_count:-0}"
    elicit_count="${elicit_count:-0}"

    namespaced_rewrites=$((namespaced_rewrites + ns_count))
    bare_rewrites=$((bare_rewrites + bare_count))
    path_rewrites=$((path_rewrites + path_count))
    elicitation_rewrites=$((elicitation_rewrites + elicit_count))

    local unresolved_token ref_name
    while IFS= read -r unresolved_token; do
      [[ -n "$unresolved_token" ]] || continue
      ref_name="${unresolved_token#/clavain:}"

      # Skill references are expected to remain /clavain:<skill>.
      if grep -Fxq "$ref_name" "$skill_names" 2>/dev/null; then
        continue
      fi

      # Anything else remaining as /clavain:<name> is unresolved for Codex wrappers.
      echo "$name|$unresolved_token" >> "$unresolved_refs"
    done < <(grep -oE '/clavain:[A-Za-z0-9_.-]+' "$converted_tmp" 2>/dev/null || true)

    {
      echo "# Clavain Command: /clavain:$name"
      echo
      echo "Codex prompt wrapper generated from Clavain command source."
      echo
      echo "- Source: \`$SOURCE_DIR/commands/$name.md\`"
      echo "- Rule: if this command references a skill, load that Clavain skill first."
      echo "- Compatibility: slash-command and .claude path references normalized for Codex."
      echo "- Elicitation adapter: if a prompt calls for AskUserQuestion, try future plan-mode escalation if host supports it, else use \`request_user_input\` when available, else ask in chat with numbered options and wait."
      echo
      echo "---"
      echo
      echo "## Codex Elicitation Adapter"
      echo
      echo "When instructions below mention the Codex elicitation adapter:"
      echo "1. If a host capability exists to switch from Default -> Plan mode, try once (non-fatal)."
      echo "2. If \`request_user_input\` is available, use it for structured elicitation."
      echo "3. Otherwise, ask in chat using a single concise question plus numbered options, then pause for user choice."
      echo "4. Normalize the answer, echo the resolved selection, and continue."
      echo
      cat "$converted_tmp"
    } > "$out"

    rm -f "$body_tmp" "$converted_tmp" "$stats_tmp"
    count=$((count + 1))
  done

  local wrapper_file wrapper_name command_name
  for wrapper_file in "$CODEX_PROMPTS_DIR"/clavain-*.md; do
    [[ -f "$wrapper_file" ]] || continue
    wrapper_name="$(basename "$wrapper_file" .md)"
    command_name="${wrapper_name#clavain-}"
    if [[ -n "$command_name" ]] && ! grep -Fxq "$command_name" "$expected" 2>/dev/null; then
      rm -f "$wrapper_file"
      removed=$((removed + 1))
    fi
  done

  local unresolved_unique unresolved_json unresolved_count
  unresolved_unique="$(mktemp)"
  sort -u "$unresolved_refs" > "$unresolved_unique" || true
  unresolved_count="$(grep -c . "$unresolved_unique" 2>/dev/null || true)"
  unresolved_count="${unresolved_count:-0}"

  unresolved_json='[]'
  if [[ "$unresolved_count" != "0" ]] && command -v jq >/dev/null 2>&1; then
    unresolved_json="$(jq -R -s 'split("\n") | map(select(length > 0))' "$unresolved_unique")"
  fi

  if command -v jq >/dev/null 2>&1; then
    jq -n \
      --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg source_dir "$SOURCE_DIR" \
      --arg prompts_dir "$CODEX_PROMPTS_DIR" \
      --argjson command_count "$count" \
      --argjson wrappers_generated "$count" \
      --argjson stale_removed "$removed" \
      --argjson namespaced_rewrites "$namespaced_rewrites" \
      --argjson bare_rewrites "$bare_rewrites" \
      --argjson path_rewrites "$path_rewrites" \
      --argjson elicitation_rewrites "$elicitation_rewrites" \
      --argjson unresolved "$unresolved_json" \
      '{
        generated_at: $generated_at,
        source_dir: $source_dir,
        prompts_dir: $prompts_dir,
        command_count: $command_count,
        wrappers_generated: $wrappers_generated,
        stale_removed: $stale_removed,
        rewrites: {
          namespaced: $namespaced_rewrites,
          bare: $bare_rewrites,
          path: $path_rewrites,
          elicitation: $elicitation_rewrites
        },
        unresolved_refs: $unresolved,
        unresolved_count: ($unresolved | length),
        status: (if (($unresolved | length) == 0) then "ok" else "warn" end)
      }' > "$CONVERSION_REPORT_FILE"
  else
    cat > "$CONVERSION_REPORT_FILE" <<REPORT
{
  "generated_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source_dir":"$(json_escape "$SOURCE_DIR")",
  "prompts_dir":"$(json_escape "$CODEX_PROMPTS_DIR")",
  "command_count":$count,
  "wrappers_generated":$count,
  "stale_removed":$removed,
  "rewrites":{"namespaced":$namespaced_rewrites,"bare":$bare_rewrites,"path":$path_rewrites,"elicitation":$elicitation_rewrites},
  "unresolved_refs":[],
  "unresolved_count":$unresolved_count,
  "status":"$( [[ "$unresolved_count" == "0" ]] && echo ok || echo warn )"
}
REPORT
  fi

  rm -f "$expected" "$command_names" "$skill_names" "$unresolved_refs" "$unresolved_unique"

  echo "Generated $count prompt wrappers in $CODEX_PROMPTS_DIR"
  echo "Removed $removed stale prompt wrappers in $CODEX_PROMPTS_DIR"
  echo "Wrote conversion report: $CONVERSION_REPORT_FILE"
  if [[ "$unresolved_count" != "0" ]]; then
    echo "WARN: conversion report has $unresolved_count unresolved reference(s)."
  fi
}

remove_prompts() {
  local removed=0
  if [[ -d "$CODEX_PROMPTS_DIR" ]]; then
    local file
    for file in "$CODEX_PROMPTS_DIR"/clavain-*.md; do
      [[ -f "$file" ]] || continue
      rm -f "$file"
      removed=$((removed + 1))
    done
    rm -f "$CONVERSION_REPORT_FILE"
  fi
  echo "Removed $removed prompt wrappers from $CODEX_PROMPTS_DIR"
}

install_managed_agents_block() {
  local block
  block="$(build_agents_block)"
  if update_file_with_block "$CODEX_AGENTS_FILE" "$AGENTS_BLOCK_START" "$AGENTS_BLOCK_END" "$block"; then
    echo "Updated managed AGENTS block: $CODEX_AGENTS_FILE"
  else
    echo "Managed AGENTS block already up to date: $CODEX_AGENTS_FILE"
  fi
}

sync_mcp_servers() {
  local manifest="$SOURCE_DIR/.claude-plugin/plugin.json"
  if [[ ! -f "$manifest" ]]; then
    echo "WARN: plugin manifest missing, skipping MCP sync: $manifest" >&2
    return 0
  fi

  local block_file
  block_file="$(mktemp)"
  render_mcp_block "$manifest" "$block_file"

  local block
  block="$(cat "$block_file")"
  rm -f "$block_file"

  if update_file_with_block "$CODEX_CONFIG_FILE" "$MCP_BLOCK_START" "$MCP_BLOCK_END" "$block"; then
    echo "Updated managed MCP config block: $CODEX_CONFIG_FILE"
  else
    echo "Managed MCP config block already up to date: $CODEX_CONFIG_FILE"
  fi
}

install_all() {
  resolve_source_dir
  if [[ "$SOURCE_EXPLICIT" -eq 0 ]]; then
    ensure_clone
  fi

  local skills_target="$SOURCE_DIR/skills"
  if [[ ! -d "$skills_target" ]]; then
    echo "Missing skills directory: $skills_target" >&2
    exit 1
  fi

  mkdir -p "$CODEX_HOME"
  safe_link "$skills_target" "$AGENTS_SKILLS_DIR/clavain" || true

  remove_legacy_codex_skills_path
  cleanup_known_legacy_wrappers

  install_managed_agents_block
  sync_mcp_servers

  if [[ "$INSTALL_PROMPTS" -eq 1 ]]; then
    generate_prompts
  else
    echo "Skipping prompt generation (--no-prompts)."
  fi

  echo
  echo "Install complete."
  echo "Restart Codex so it reloads discovered skills/prompts."
}

doctor() {
  resolve_source_dir

  local skills_target="$SOURCE_DIR/skills"
  local commands_dir="$SOURCE_DIR/commands"
  local scripts_dir="$SOURCE_DIR/scripts"
  local agents_link="$AGENTS_SKILLS_DIR/clavain"
  local legacy_link="$CODEX_SKILLS_DIR/clavain"

  local status=0
  local issues=()

  local root_ok="false"
  local agents_link_ok="false"
  local agents_link_match="false"
  local source_agents_link=""
  local legacy_path_absent="true"
  local helper_dispatch_status="missing"
  local helper_debate_status="missing"
  local codex_present="false"
  local command_dir_ok="false"
  local prompts_dir_ok="false"
  local agents_block_ok="false"
  local mcp_block_ok="false"
  local conversion_report_ok="false"

  local skill_dir_count=0
  local command_count=0
  local expected_wrappers=0
  local present_wrappers=0
  local missing_wrappers=0
  local stale_wrappers=0
  local wrapper_count=0
  local conversion_unresolved=0

  if [[ "$DOCTOR_JSON" -eq 0 ]]; then
    echo "== Clavain Codex Doctor =="
    echo "Source dir: $SOURCE_DIR"
    echo
  fi

  if ! is_clavain_root "$SOURCE_DIR"; then
    issues+=("Source dir missing required Clavain structure: $SOURCE_DIR")
    status=1
  else
    root_ok="true"
  fi

  if [[ -L "$agents_link" ]]; then
    agents_link_ok="true"
    source_agents_link="$(readlink -f "$agents_link" 2>/dev/null || readlink "$agents_link")"
    if [[ "$source_agents_link" == "$skills_target" ]]; then
      agents_link_match="true"
      if [[ "$DOCTOR_JSON" -eq 0 ]]; then
        echo "agents skills link: $agents_link -> $source_agents_link"
      fi
    else
      issues+=("agents skills link target mismatch: $agents_link -> $source_agents_link (expected $skills_target)")
      status=1
    fi
  else
    issues+=("agents skills link missing: $agents_link")
    status=1
  fi

  if [[ -e "$legacy_link" || -L "$legacy_link" ]]; then
    legacy_path_absent="false"
    issues+=("legacy codex skills path present (clean break expects removal): $legacy_link")
    status=1
  fi

  local required_helper
  for required_helper in dispatch.sh debate.sh; do
    if [[ ! -f "$scripts_dir/$required_helper" ]]; then
      issues+=("required helper missing: $scripts_dir/$required_helper")
      status=1
    else
      if [[ "$required_helper" == "dispatch.sh" ]]; then
        helper_dispatch_status="present"
      else
        helper_debate_status="present"
      fi
    fi
  done

  if command -v codex >/dev/null 2>&1; then
    codex_present="true"
  fi

  if [[ "$DOCTOR_JSON" -eq 0 ]]; then
    if [[ "$codex_present" == "true" ]]; then
      echo "codex CLI:            present"
    else
      echo "codex CLI:            missing"
    fi
  fi

  if [[ -d "$skills_target" ]]; then
    skill_dir_count="$(find "$skills_target" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
  fi

  if [[ -d "$commands_dir" ]]; then
    command_dir_ok="true"
    local command_file command_name
    while IFS= read -r command_file; do
      [[ -f "$command_file" ]] || continue
      command_name="$(basename "$command_file" .md)"
      command_count=$((command_count + 1))
      expected_wrappers=$((expected_wrappers + 1))
      if [[ -f "$CODEX_PROMPTS_DIR/clavain-$command_name.md" ]]; then
        present_wrappers=$((present_wrappers + 1))
      else
        missing_wrappers=$((missing_wrappers + 1))
        issues+=("missing wrapper: $CODEX_PROMPTS_DIR/clavain-$command_name.md")
        status=1
      fi
    done < <(find "$commands_dir" -maxdepth 1 -type f -name '*.md')
  else
    issues+=("commands dir missing: $commands_dir")
    status=1
  fi

  if [[ -d "$CODEX_PROMPTS_DIR" ]]; then
    prompts_dir_ok="true"
    wrapper_count="$(find "$CODEX_PROMPTS_DIR" -maxdepth 1 -type f -name 'clavain-*.md' | wc -l | tr -d ' ')"

    local wrapper_file wrapper_name command_name
    while IFS= read -r wrapper_file; do
      [[ -f "$wrapper_file" ]] || continue
      wrapper_name="$(basename "$wrapper_file" .md)"
      command_name="${wrapper_name#clavain-}"
      if [[ ! -f "$commands_dir/$command_name.md" ]]; then
        stale_wrappers=$((stale_wrappers + 1))
        issues+=("stale wrapper: $wrapper_file")
        status=1
      fi
    done < <(find "$CODEX_PROMPTS_DIR" -maxdepth 1 -type f -name 'clavain-*.md')
  fi

  if [[ -f "$CODEX_AGENTS_FILE" ]] \
    && grep -Fq "$AGENTS_BLOCK_START" "$CODEX_AGENTS_FILE" \
    && grep -Fq "$AGENTS_BLOCK_END" "$CODEX_AGENTS_FILE"; then
    agents_block_ok="true"
  else
    issues+=("managed AGENTS block missing or malformed: $CODEX_AGENTS_FILE")
    status=1
  fi

  if [[ -f "$CODEX_CONFIG_FILE" ]] \
    && grep -Fq "$MCP_BLOCK_START" "$CODEX_CONFIG_FILE" \
    && grep -Fq "$MCP_BLOCK_END" "$CODEX_CONFIG_FILE"; then
    mcp_block_ok="true"
    if grep -qE '^\[mcp_servers\.' "$CODEX_CONFIG_FILE"; then
      issues+=("managed MCP block uses legacy [mcp_servers.*] tables; rerun install to rewrite as [mcp.servers.*]")
      status=1
      mcp_block_ok="false"
    fi
  else
    issues+=("managed MCP block missing or malformed: $CODEX_CONFIG_FILE")
    status=1
  fi

  if [[ -f "$CONVERSION_REPORT_FILE" ]]; then
    conversion_report_ok="true"
    if command -v jq >/dev/null 2>&1; then
      conversion_unresolved="$(jq -r '.unresolved_count // 0' "$CONVERSION_REPORT_FILE" 2>/dev/null || echo 0)"
      conversion_unresolved="${conversion_unresolved:-0}"
      if [[ "$conversion_unresolved" != "0" ]]; then
        issues+=("conversion report has unresolved refs: $conversion_unresolved ($CONVERSION_REPORT_FILE)")
        status=1
      fi
    fi
  else
    issues+=("conversion report missing: $CONVERSION_REPORT_FILE")
    status=1
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
    printf '    "agents_skills_link_exists":%s,\n' "$agents_link_ok"
    printf '    "agents_skills_link_match":%s,\n' "$agents_link_match"
    printf '    "agents_skills_link_target":"%s",\n' "$(json_escape "$source_agents_link")"
    printf '    "legacy_codex_skills_path_absent":%s,\n' "$legacy_path_absent"
    printf '    "helpers":{\n'
    printf '      "dispatch.sh":"%s",\n' "$helper_dispatch_status"
    printf '      "debate.sh":"%s"\n' "$helper_debate_status"
    printf '    },\n'
    printf '    "codex_cli_present":%s,\n' "$codex_present"
    printf '    "commands_dir_exists":%s,\n' "$command_dir_ok"
    printf '    "prompts_dir_exists":%s,\n' "$prompts_dir_ok"
    printf '    "managed_agents_block_present":%s,\n' "$agents_block_ok"
    printf '    "managed_mcp_block_present":%s,\n' "$mcp_block_ok"
    printf '    "conversion_report_present":%s\n' "$conversion_report_ok"
    printf '  },\n'
    printf '  "counts":{\n'
    printf '    "skill_dirs":%s,\n' "$skill_dir_count"
    printf '    "command_count":%s,\n' "$command_count"
    printf '    "expected_wrappers":%s,\n' "$expected_wrappers"
    printf '    "present_wrappers":%s,\n' "$present_wrappers"
    printf '    "missing_wrappers":%s,\n' "$missing_wrappers"
    printf '    "stale_wrappers":%s,\n' "$stale_wrappers"
    printf '    "prompt_wrapper_total":%s,\n' "$wrapper_count"
    printf '    "conversion_unresolved_refs":%s\n' "$conversion_unresolved"
    printf '  },\n'
    printf '  "paths":{\n'
    printf '    "codex_home":"%s",\n' "$(json_escape "$CODEX_HOME")"
    printf '    "agents_file":"%s",\n' "$(json_escape "$CODEX_AGENTS_FILE")"
    printf '    "config_file":"%s",\n' "$(json_escape "$CODEX_CONFIG_FILE")"
    printf '    "conversion_report":"%s"\n' "$(json_escape "$CONVERSION_REPORT_FILE")"
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
  echo "commands in source:     $command_count"
  echo "prompt wrappers:        $present_wrappers/$expected_wrappers present; $missing_wrappers missing; $stale_wrappers stale; $wrapper_count total"
  echo "conversion unresolved:  $conversion_unresolved"
  echo

  if [[ "$status" -eq 0 ]]; then
    echo "Doctor checks passed."
    return 0
  fi

  echo "Doctor checks completed with issues." >&2
  return 1
}

uninstall_all() {
  rm -f "$AGENTS_SKILLS_DIR/clavain"
  remove_legacy_codex_skills_path || true
  remove_prompts
  remove_block_from_file "$CODEX_AGENTS_FILE" "$AGENTS_BLOCK_START" "$AGENTS_BLOCK_END" || true
  remove_block_from_file "$CODEX_CONFIG_FILE" "$MCP_BLOCK_START" "$MCP_BLOCK_END" || true

  if [[ "$REMOVE_CLONE" -eq 1 ]]; then
    rm -rf "$CLONE_DIR"
    echo "Removed clone: $CLONE_DIR"
  fi

  echo "Uninstall complete."
}

case "$ACTION" in
  install)
    install_all
    ;;
  update)
    ensure_clone
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
