---
name: doctor
description: Quick health check — verifies MCP servers, external tools, beads, and plugin configuration without making changes
argument-hint: "[optional: --scope=clavain|interpath|interwatch|interlock|notion|all, --check-only]"
---

# Clavain Doctor

Run a quick diagnostic to verify everything Clavain depends on is healthy. Unlike `/setup` (which bootstraps), `/doctor` only checks — it never makes changes.

## Scope

- `clavain` (default): run full Clavain system checks only.
- `interlock`: run interlock coordination checks.
- `interwatch`: check doc drift companion health.
- `interpath`: check artifact workflow companion health.
- `notion`: run Notion-specific health checks via `interkasten`.
- `all`: run every scope in sequence.

You can pass multiple scopes in one run (space-separated), or use `--check-only` in all scopes.

Run all checks in parallel where possible, then present results.

## Checks

### 1. MCP Servers

Test each MCP server with a lightweight call:

- **context7**: Call `resolve-library-id` with `libraryName: "react"` and `query: "test"`. Pass = response received. Fail = timeout or error.
- **qmd**: Call `status`. Pass = response with collection info. Fail = error or not configured.

### 2. External Tools

Check presence of optional companion tools:

```bash
echo "oracle: $(command -v oracle >/dev/null 2>&1 && echo 'installed' || echo 'not found')"
echo "codex: $(command -v codex >/dev/null 2>&1 && echo 'installed' || echo 'not found')"
echo "bd: $(command -v bd >/dev/null 2>&1 && echo 'installed' || echo 'not found')"
echo "qmd: $(command -v qmd >/dev/null 2>&1 && echo 'installed' || echo 'not found')"
```

### 2b. Soft Dependencies

Check optional tools that affect feature availability:

```bash
# Python 3 + PyYAML (needed for spec loader)
if python3 -c "import yaml" 2>/dev/null; then
  echo "python3+pyyaml: PASS"
else
  echo "python3+pyyaml: WARN (spec loader will use hardcoded defaults)"
  echo "  Fix: pip install pyyaml"
fi

# yq v4 (needed for fleet registry queries)
if command -v yq >/dev/null 2>&1 && yq --version 2>/dev/null | grep -q 'v4'; then
  echo "yq: PASS"
else
  echo "yq: WARN (fleet registry queries unavailable)"
  echo "  Fix: https://github.com/mikefarah/yq#install"
fi

# Node.js (needed for JS-based MCP plugins)
if command -v node >/dev/null 2>&1; then
  echo "node: PASS ($(node --version 2>/dev/null))"
else
  echo "node: WARN (JS-based MCP plugins won't start)"
  echo "  Fix: https://nodejs.org/"
fi

# PATH includes ~/.local/bin (needed for ic kernel)
if echo "$PATH" | grep -q "$HOME/.local/bin"; then
  echo "PATH: PASS"
else
  echo "PATH: WARN (~/.local/bin not on PATH — ic kernel may not be found)"
  echo "  Fix: export PATH=\"\$HOME/.local/bin:\$PATH\" in your shell profile"
fi
```

### 2c. Config Validation

Validate critical YAML config files are parseable:

```bash
_config_dir="os/clavain/config"
for cfg in agency-spec.yaml fleet-registry.yaml routing.yaml; do
  _cfg_path="${_config_dir}/${cfg}"
  if [ ! -f "$_cfg_path" ]; then
    echo "${cfg}: SKIP (not found)"
    continue
  fi
  if python3 -c "import yaml; yaml.safe_load(open('${_cfg_path}'))" 2>/dev/null; then
    echo "${cfg}: PASS"
  elif yq '.' "${_cfg_path}" >/dev/null 2>&1; then
    echo "${cfg}: PASS"
  else
    echo "${cfg}: FAIL (malformed YAML — features using this config will silently degrade)"
  fi
done
```

### 2d. Plugin Hook Syntax

Fast syntax check on all installed plugin hooks:

```bash
_hook_errors=0
for hook in ~/.claude/plugins/cache/*/*/hooks/*.sh; do
  [ -f "$hook" ] || continue
  if ! bash -n "$hook" 2>/dev/null; then
    echo "  WARN: syntax error in $(basename "$(dirname "$(dirname "$hook")")")/$(basename "$hook")"
    _hook_errors=$((_hook_errors + 1))
  fi
done
if [ "$_hook_errors" -eq 0 ]; then
  echo "hook syntax: PASS"
else
  echo "hook syntax: WARN ($_hook_errors hooks have syntax errors)"
fi
```

### 2e. Routing Activation Status

Check routing.yaml feature modes for shadow/off configs that may be ready to activate:

```bash
_routing_yaml="os/clavain/config/routing.yaml"
if [ -f "$_routing_yaml" ]; then
  _shadow_count=0
  for _section in complexity calibration delegation; do
    _mode=$(awk -v sec="${_section}:" '
      $0 == sec { found=1; next }
      found && /^[a-z]/ { exit }
      found && /^[[:space:]]+mode:/ { sub(/.*mode:[[:space:]]*/, ""); sub(/[[:space:]]*#.*/, ""); print; exit }
    ' "$_routing_yaml" 2>/dev/null)
    if [ -z "$_mode" ]; then
      echo "  $_section: SKIP (not found)"
    elif [ "$_mode" = "off" ] || [ "$_mode" = "shadow" ]; then
      echo "  $_section: $_mode  WARN (not enforcing)"
      _shadow_count=$((_shadow_count + 1))
    else
      echo "  $_section: $_mode  PASS"
    fi
  done
  if [ "$_shadow_count" -gt 0 ]; then
    echo "  Recommendation: Review shadow-mode features — they may be ready to activate"
  fi
else
  echo "routing.yaml: SKIP (not found)"
fi
```

### 2f. Plugin Cache Verification

Verify installed companion plugins have files (catches empty-cache deployment gaps):

```bash
_cache_dir="${HOME}/.claude/plugins/cache/interagency-marketplace"
_cache_warns=0
for _plugin in interphase interline interspect interflux interpath interwatch interlock; do
  _plugin_dir=$(find "$_cache_dir" -maxdepth 1 -name "$_plugin" -type d 2>/dev/null | head -1)
  if [ -z "$_plugin_dir" ]; then
    continue  # Not installed — companion checks (section 3b) handle this
  fi
  _latest=$(ls -d "$_plugin_dir"/*/ 2>/dev/null | sort -V | tail -1)
  if [ -z "$_latest" ]; then
    echo "  $_plugin: WARN (installed but no version directory)"
    _cache_warns=$((_cache_warns + 1))
    continue
  fi
  _file_count=$(find "$_latest" -type f 2>/dev/null | wc -l)
  if [ "$_file_count" -le 2 ]; then
    echo "  $_plugin: WARN (only $_file_count files — likely empty cache, reinstall)"
    _cache_warns=$((_cache_warns + 1))
  else
    echo "  $_plugin: $_file_count files  PASS"
  fi
done
if [ "$_cache_warns" -eq 0 ]; then
  echo "plugin caches: PASS"
fi
```

### 3. Beads

```bash
if [ -d .beads ]; then
  if timeout 5 bd stats 2>&1 | head -5; then
    true
  else
    echo "beads: FAIL (Dolt server hung or unresponsive)"
    echo "  Fix: bash .beads/recover.sh"
  fi
else
  echo "not initialized (run 'bd init' to set up)"
fi
```

### 3a. Zombie Bead Detection (auto-fix)

Finds open beads that are actually done. Two detection patterns:

1. **Phase-done zombies**: Open/in-progress beads with `phase=done` state
2. **Orphaned children**: Open beads whose parent bead is closed

This check auto-closes zombies it finds (doctor is read-only for most checks, but zombie closure is safe and high-value — leaving them open pollutes the ready queue and causes duplicate work).

```bash
if [ -d .beads ] && command -v bd >/dev/null 2>&1; then
  _zombie_count=0

  # Collect open + in_progress IDs (bd doesn't combine --status flags)
  _open_ids=$( (bd list --status=open --json 2>/dev/null; bd list --status=in_progress --json 2>/dev/null) | jq -r '.[].id' 2>/dev/null | sort -u) || _open_ids=""

  # Pattern 1: phase=done but bead still open/in_progress
  for _id in $_open_ids; do
    _phase=$(bd state "$_id" phase 2>/dev/null) || _phase=""
    if [ "$_phase" = "done" ]; then
      echo "  ZOMBIE: $_id (phase=done but still open)"
      bd close "$_id" --reason="Zombie sweep: phase=done but bead was left open" 2>/dev/null || true
      _zombie_count=$((_zombie_count + 1))
    fi
  done

  # Pattern 2: dot-children (iv-xxx.N) whose parent is closed
  # Only targets dot-notation children (e.g., iv-abc.1, iv-abc.2) — these are
  # definitionally part of their parent epic. A closed dependency is NOT the same
  # as a closed parent — dependencies just mean "blocker removed."
  for _id in $_open_ids; do
    # Only match dot-children: <parent-id>.<number>
    _parent_id=$(echo "$_id" | grep -oE '^[A-Za-z]+-[a-z0-9]+' 2>/dev/null) || continue
    echo "$_id" | grep -qE '\.[0-9]+$' || continue
    [ "$_parent_id" = "$_id" ] && continue

    # Skip if already closed by Pattern 1
    _cur=$(bd show "$_id" 2>/dev/null | head -1) || continue
    echo "$_cur" | grep -qE 'CLOSED|DEFERRED' && continue

    # Check if parent is closed
    _par_line=$(bd show "$_parent_id" 2>/dev/null | head -1) || continue
    if echo "$_par_line" | grep -q "CLOSED"; then
      _par_title=$(echo "$_par_line" | sed 's/.*· //;s/   \[.*//')
      echo "  ZOMBIE: $_id (parent $_parent_id closed)"
      bd close "$_id" --reason="Zombie sweep: parent $_parent_id is closed" 2>/dev/null || true
      _zombie_count=$((_zombie_count + 1))
    fi
  done

  if [ "$_zombie_count" -eq 0 ]; then
    echo "zombie beads: PASS (none found)"
  else
    echo "zombie beads: FIXED (auto-closed $_zombie_count zombies)"
  fi
fi
```

<!-- agent-rig:begin:companion-checks -->
### 3b. Beads Lifecycle Companion

```bash
if ls "$HOME/.claude/plugins/cache"/*/interphase/*/hooks/lib-gates.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interphase: installed"
else
  echo "interphase: not installed (phase tracking disabled)"
  echo "  Install: claude plugin install interphase@interagency-marketplace"
fi
```

### 3c. Statusline Companion

```bash
if ls "$HOME/.claude/plugins/cache"/*/interline/*/scripts/statusline.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interline: installed"
else
  echo "interline: not installed (statusline rendering unavailable)"
  echo "  Install: claude plugin install interline@interagency-marketplace"
fi
```

### 3d. Artifact Generation Companion

```bash
if ls "$HOME/.claude/plugins/cache"/*/interpath/*/scripts/interpath.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interpath: installed"
else
  echo "interpath: not installed (product artifact generation unavailable)"
  echo "  Install: claude plugin install interpath@interagency-marketplace"
fi
```

### 3e. Doc Freshness Companion

```bash
if ls "$HOME/.claude/plugins/cache"/*/interwatch/*/scripts/interwatch.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interwatch: installed"
else
  echo "interwatch: not installed (doc drift detection unavailable)"
  echo "  Install: claude plugin install interwatch@interagency-marketplace"
fi
```
<!-- agent-rig:end:companion-checks -->

### 3f. Agent Memory

```bash
if [ -d .clavain ]; then
  echo ".clavain: initialized"
  # Check scratch/ is gitignored
  if grep -qF '.clavain/scratch/' .gitignore 2>/dev/null; then
    echo "  scratch gitignore: OK"
  else
    echo "  WARN: .clavain/scratch/ not in .gitignore"
  fi
  # Check for stale handoff (portable stat with existence guard)
  # Prefer handoff-latest.md symlink, fall back to legacy handoff.md
  _handoff_file=""
  if [ -f .clavain/scratch/handoff-latest.md ]; then
    _handoff_file=".clavain/scratch/handoff-latest.md"
  elif [ -f .clavain/scratch/handoff.md ]; then
    _handoff_file=".clavain/scratch/handoff.md"
  fi
  if [ -n "$_handoff_file" ]; then
    mtime=$(stat -c %Y "$_handoff_file" 2>/dev/null || stat -f %m "$_handoff_file" 2>/dev/null || echo 0)
    if [ "$mtime" -gt 0 ]; then
      age=$(( ($(date +%s) - mtime) / 86400 ))
      if [ "$age" -gt 7 ]; then
        echo "  WARN: stale handoff (${age} days old)"
      fi
    fi
    # Count accumulated handoffs
    handoff_count=$(ls -1 .clavain/scratch/handoff-2*.md 2>/dev/null | wc -l | tr -d ' ')
    if [ "$handoff_count" -gt 0 ]; then
      echo "  OK: ${handoff_count} handoff(s) in scratch/"
    fi
  fi
  # Count learnings entries
  learnings_count=$(ls .clavain/learnings/*.md 2>/dev/null | wc -l | tr -d ' ')
  echo "  learnings: ${learnings_count} entries"
else
  echo ".clavain: not initialized (run /clavain:init to set up)"
fi
```

### 3g. Multi-Agent Coordination Companion

```bash
if ls ~/.claude/plugins/cache/*/interlock/*/scripts/interlock-register.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interlock: installed"
  # Check if intermute service is running
  if curl -s --connect-timeout 2 http://127.0.0.1:7338/health >/dev/null 2>&1; then
    echo "  intermute service: running"
    # Check if agent is registered for this session
    if ls /tmp/interlock-agent-*.json 2>/dev/null | head -1 >/dev/null; then
      echo "  agent: registered"
    else
      echo "  agent: not registered (run /interlock:join to participate)"
    fi
  else
    echo "  intermute service: not running"
    echo "  Run /clavain:setup --scope interlock to install and start intermute"
  fi
else
  echo "interlock: not installed (multi-agent coordination unavailable)"
  echo "  Install: claude plugin install interlock@interagency-marketplace"
fi
```

### 4. Conflicting Plugins

Check that known conflicting plugins are disabled:

<!-- agent-rig:begin:doctor-conflicts -->
```bash
python3 -c "
import json, os
settings = os.path.expanduser('~/.claude/settings.json')
try:
    plugins = json.load(open(settings)).get('enabledPlugins', {})
except FileNotFoundError:
    print('  settings.json not found'); exit()
conflicts = [
    'code-review@claude-plugins-official',
    'pr-review-toolkit@claude-plugins-official',
    'code-simplifier@claude-plugins-official',
    'commit-commands@claude-plugins-official',
    'feature-dev@claude-plugins-official',
    'claude-md-management@claude-plugins-official',
    'frontend-design@claude-plugins-official',
    'hookify@claude-plugins-official',
    'superpowers@superpowers-marketplace',
    'compound-engineering@every-marketplace',
]
active = [p for p in conflicts if plugins.get(p, True)]
if active:
    for p in active:
        print(f'  WARN: {p} is still enabled')
else:
    print('  All conflicts disabled')
"
```
<!-- agent-rig:end:doctor-conflicts -->

### 5. Skill Budget

```bash
# Check skill sizes against budget thresholds
CLAVAIN_LIB=$(find ~/.claude/plugins/cache -path '*/clavain/*/hooks/lib.sh' 2>/dev/null | sort -V | tail -1)
if [[ -n "$CLAVAIN_LIB" ]]; then
    source "$CLAVAIN_LIB"
    SKILLS_DIR="$(dirname "$CLAVAIN_LIB")/../skills"
    budget_status=0
    budget_output=$(skill_check_budget "$SKILLS_DIR" 16000 32000 2>/dev/null) || budget_status=$?
    warns=$(echo "$budget_output" | grep -c "^WARN" || true)
    errors=$(echo "$budget_output" | grep -c "^ERROR" || true)
    if [[ $errors -gt 0 ]]; then
        echo "skill budget: ERROR ($errors skills over 32K)"
        echo "$budget_output" | grep "^ERROR"
    elif [[ $warns -gt 0 ]]; then
        echo "skill budget: WARN ($warns skills over 16K)"
        echo "$budget_output" | grep "^WARN"
    else
        echo "skill budget: PASS (all skills under 16K)"
    fi
fi
```

### 6. Plugin Version

```bash
# Compare installed vs published
INSTALLED=$(cat ~/.claude/plugins/cache/interagency-marketplace/clavain/*/plugin.json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])" 2>/dev/null || echo "unknown")
echo "installed: v${INSTALLED}"
```

## Output

Present results as a table:

<!-- agent-rig:begin:doctor-output -->
```
Clavain Doctor
──────────────────────────────────
context7      [PASS|FAIL]
qmd           [PASS|WARN: not installed]
oracle        [installed|not found]
codex         [installed|not found]
beads         [OK (N open, M closed)|not initialized]
zombies       [PASS|FIXED: N auto-closed]
interphase    [installed|not installed]
interline     [installed|not installed]
interpath     [installed|not installed]
interwatch    [installed|not installed]
interlock     [installed|not installed]
.clavain      [initialized|not set up]
conflicts     [clear|WARN: N active]
skill budget  [PASS|WARN: N over 16K|ERROR: N over 32K]
version       v0.X.Y
──────────────────────────────────
```
<!-- agent-rig:end:doctor-output -->

If any check shows FAIL or WARN, add a **Recommendations** section with one-line fixes:
- context7 fail → "Restart Claude Code session — context7 is bundled with Clavain"
- qmd not installed → "Install qmd for semantic doc search: https://github.com/tobi/qmd"
- conflicts active → "Run `/clavain:setup` to disable conflicting plugins"
- beads not initialized → "Run `bd init` to enable issue tracking"
- interlock not installed → "Install interlock for multi-agent coordination: `claude plugin install interlock@interagency-marketplace`"
- intermute not running → "Run `/clavain:setup --scope interlock` to install and start the intermute coordination service"
- python3+pyyaml WARN → "Install PyYAML: `pip install pyyaml` (spec loader falls back to hardcoded defaults without it)"
- yq WARN → "Install yq v4: https://github.com/mikefarah/yq#install (fleet registry queries unavailable without it)"
- node WARN → "Install Node.js 20+: https://nodejs.org/ (JS-based MCP plugins won't start without it)"
- PATH WARN → "Add `export PATH=\"$HOME/.local/bin:$PATH\"` to your shell profile"
- config FAIL → "Fix the YAML syntax error in the named config file — features using it will silently degrade"
- hook syntax WARN → "Check the named hook files for bash syntax errors"
- beads FAIL (hung) → "Run `bash .beads/recover.sh` to recover from a stuck Dolt server"
- zombies FIXED → "Auto-closed N zombie beads. Root cause: prior sessions completed work but didn't run the close protocol. Run `bd list --status=closed` to review."
- .clavain not initialized → "Run `/clavain:init` to set up agent memory"
- .clavain scratch not gitignored → "Run `/clavain:init` to fix gitignore"
- skill budget WARN/ERROR → "Trim skills over 16K chars by moving verbose sections to references/ subdirectory"
- routing shadow mode → "Review shadow-mode features in routing.yaml — they may be ready to activate with `mode: enforce`"
- plugin cache empty → "Reinstall the plugin: `claude plugin install <name>@interagency-marketplace`"
