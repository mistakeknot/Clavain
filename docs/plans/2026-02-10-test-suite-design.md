# Clavain Test Suite — Implementation Plan

> Brainstormed 2026-02-10. Three-tier test suite: structural (pytest), shell (bats-core), smoke (local Claude Code subagents). CI on every push for Tiers 1+2; smoke tests run locally or on schedule.
>
> **Revised** after flux-drive review (3 agents: architecture, quality, performance) and live smoke test validation (8/8 agents passed).

## Prerequisite: Reconcile Component Counts

Before writing any tests, reconcile the agent/command counts across all documentation sources. Current state:

| Source | Agents | Skills | Commands |
|--------|--------|--------|----------|
| Filesystem (actual) | 35 (27 review + 5 research + 3 workflow) | 34 | 24 |
| CLAUDE.md | 29 | 34 | 24 |
| AGENTS.md | 29 | 34 | 27 |
| plugin.json description | 29 | 34 | 24 |

**Action**: Update CLAUDE.md, AGENTS.md, and plugin.json to reflect 35 agents and 24 commands. The 6 fd-v2 agents were added without updating documentation.

**Also note**: `agents/review/references/` exists as a non-agent subdirectory containing `concurrency-patterns.md`. All globs and count assertions must exclude `references/` subdirectories.

---

## Architecture

```
tests/
├── structural/              # Tier 1: Python/pytest — cross-reference validation
│   ├── conftest.py          # Shared fixtures (project root, file inventories)
│   ├── test_plugin_manifest.py
│   ├── test_hooks_json.py   # Separate from manifest — different file, different concerns
│   ├── test_agents.py
│   ├── test_skills.py
│   ├── test_commands.py
│   ├── test_cross_references.py
│   └── test_scripts.py
├── shell/                   # Tier 2: bats-core — hook correctness
│   ├── test_helper.bash     # Shared setup: env vars, stubs, bats-support/bats-assert
│   ├── session_start.bats
│   ├── autopilot.bats
│   ├── lib.bats
│   ├── auto_compound.bats
│   ├── agent_mail_register.bats
│   ├── dotfiles_sync.bats
│   └── hooks_json.bats
├── smoke/                   # Tier 3: Local Claude Code subagents
│   └── run-smoke-tests.sh   # Dispatches agents via claude CLI
├── fixtures/                # Shared test data
│   ├── minimal_tool_input.json
│   ├── transcript_with_commit.jsonl
│   ├── transcript_with_insight.jsonl
│   ├── transcript_clean.jsonl
│   └── stop_hook_stdin.json
├── pyproject.toml           # pytest configuration
└── run-tests.sh             # Local test runner (tiers 1+2, optionally +3)
```

## CI Workflow

```
.github/workflows/test.yml

Tier 1+2 (every push + PR):
  structural-and-shell:  ubuntu-latest, ~30-45s cold / ~15-25s warm, no secrets

Tier 3 — Smoke (schedule + manual dispatch + path-filtered push):
  smoke:  ubuntu-latest, ~30 min timeout, ANTHROPIC_API_KEY required
  Triggers: daily cron, workflow_dispatch, push only when hooks/agents/skills/.claude-plugin change
  Skip condition: if: secrets.ANTHROPIC_API_KEY != '' (allows forks to pass)
```

---

## Step 0: Prerequisite — Update Documentation Counts

Update these files to reflect actual filesystem counts (35 agents, 34 skills, 24 commands):
- `CLAUDE.md` — quick reference counts
- `AGENTS.md` — quick reference and validation section
- `.claude-plugin/plugin.json` — description field

---

## Step 1: Infrastructure Setup

### 1a. Install test dependencies
- `bats-core` via npm (`npm install -g bats`) — simpler than the bats-action (which is a runner, not an installer)
- `bats-support` and `bats-assert` via npm for idiomatic assertions
- `pytest` + `pyyaml` via `uv run` (project convention — not pip)
- Create `tests/pyproject.toml`:
  ```toml
  [project]
  name = "clavain-tests"
  requires-python = ">=3.12"
  dependencies = ["pytest>=8.0", "pyyaml>=6.0"]

  [tool.pytest.ini_options]
  testpaths = ["structural"]
  ```

### 1b. Create `tests/run-tests.sh`
- Local runner that executes Tier 1 + Tier 2 (+ optionally Tier 3 with `--smoke`)
- Installs bats if not present (checks `command -v bats`)
- Runs `uv run pytest tests/structural/ -v --tb=short`
- Runs `bats tests/shell/ --recursive`
- Optionally runs `tests/smoke/run-smoke-tests.sh` if `--smoke` flag passed
- Exit code: nonzero if any tier fails

### 1c. Create `tests/structural/conftest.py`
Shared pytest fixtures (all lowercase, `@pytest.fixture(scope="session")`):
```python
project_root    # Path to repo root (resolved from conftest location)
agents_dir      # agents/ directory
skills_dir      # skills/ directory
commands_dir    # commands/ directory
hooks_dir       # hooks/ directory

# Inventory fixtures (computed once per session)
all_agent_files()     # List[Path] — .md files in agents/{review,research,workflow}/
                      #   EXCLUDES references/ subdirectories
all_skill_dirs()      # List[Path] — all dirs in skills/ containing SKILL.md
all_command_files()   # List[Path] — all .md files in commands/
all_hook_scripts()    # List[Path] — all .sh files in hooks/ (entry points only, not lib.sh)
plugin_json()         # dict — parsed plugin.json
hooks_json()          # dict — parsed hooks.json
```

**Important**: `all_agent_files()` must use explicit category dirs, not recursive glob:
```python
agent_files = []
for category in ["review", "research", "workflow"]:
    agent_files.extend((agents_dir / category).glob("*.md"))
```
This naturally excludes `agents/review/references/concurrency-patterns.md`.

### 1d. Create `tests/shell/test_helper.bash`
Shared bats setup:
```bash
HOOKS_DIR="$BATS_TEST_DIRNAME/../../hooks"
FIXTURES_DIR="$BATS_TEST_DIRNAME/../fixtures"
export CLAUDE_PLUGIN_ROOT="$BATS_TEST_DIRNAME/../.."

# Load bats-support and bats-assert for idiomatic assertions
load 'bats-support/load'
load 'bats-assert/load'

# Stub external commands to avoid network calls and timeouts in CI
curl() { return 1; }
pgrep() { return 1; }
export -f curl pgrep
```

### 1e. Create test fixtures
- `fixtures/stop_hook_stdin.json` — minimal JSON with `stop_hook_active` and `transcript_path` fields
- `fixtures/transcript_with_commit.jsonl` — JSONL with a "git commit" line (triggers auto-compound)
- `fixtures/transcript_with_insight.jsonl` — JSONL with "insight" marker
- `fixtures/transcript_clean.jsonl` — JSONL with no signal patterns
- `fixtures/minimal_tool_input.json` — minimal PreToolUse stdin JSON

---

## Step 2: Tier 1 — Structural Tests (pytest)

**Convention**: Use `@pytest.mark.parametrize` with `ids=lambda p: p.stem` for all per-file tests. This gives one test result per file with clear failure messages.

### 2a. `test_plugin_manifest.py`
| Test | Assertion |
|------|-----------|
| `test_plugin_json_valid` | plugin.json parses as JSON |
| `test_plugin_json_required_fields` | Has `name`, `version`, `description`, `author` |
| `test_plugin_json_version_format` | Version matches `\d+\.\d+\.\d+` |
| `test_mcp_servers_valid` | Each mcpServer has `type` in (`stdio`, `http`) |

### 2b. `test_hooks_json.py` (separate file — hooks.json is a different concern from plugin.json)
| Test | Assertion |
|------|-----------|
| `test_hooks_json_valid` | hooks.json parses as JSON |
| `test_hooks_json_event_types` | All keys in `hooks` are in valid set: `PreToolUse`, `PostToolUse`, `Notification`, `SessionStart`, `SessionEnd`, `Stop`. Source of truth: Claude Code plugin hooks documentation. |
| `test_hooks_json_commands_exist` | Every `.sh` path in hooks.json resolves to a real file (after stripping `${CLAUDE_PLUGIN_ROOT}`) |
| `test_hooks_json_timeouts_reasonable` | All timeout values ≤ 30 |
| `test_hooks_json_matchers_valid` | All `matcher` values compile as valid regex |

### 2c. `test_agents.py`
| Test | Assertion |
|------|-----------|
| `test_agent_count` | 35 agent .md files total (27 review + 5 research + 3 workflow), excluding `references/` subdirs |
| `test_agent_has_frontmatter[{name}]` | Each agent .md has YAML frontmatter between `---` markers (parametrized) |
| `test_agent_frontmatter_required_fields[{name}]` | Frontmatter has `name` and `description` (parametrized) |
| `test_agent_name_matches_filename[{name}]` | Frontmatter `name` == filename without `.md` (parametrized) |
| `test_agent_filenames_kebab_case[{name}]` | All filenames match `[a-z0-9]+(-[a-z0-9]+)*\.md` (parametrized) |
| `test_agent_model_valid[{name}]` | If `model` is present, it's `inherit` or `haiku` (parametrized) |
| `test_agent_body_nonempty[{name}]` | Body after frontmatter is ≥ 50 chars (parametrized) |
| `test_agent_top_level_subdirectories_valid` | Only `review/`, `research/`, `workflow/` as top-level subdirs of `agents/`. Nested subdirs like `review/references/` are allowed. |

### 2d. `test_skills.py`
| Test | Assertion |
|------|-----------|
| `test_skill_count` | 34 skill directories with SKILL.md |
| `test_skill_has_skillmd[{name}]` | Every dir in `skills/` contains `SKILL.md` (parametrized) |
| `test_skill_has_frontmatter[{name}]` | Each SKILL.md has YAML frontmatter (parametrized) |
| `test_skill_frontmatter_required_fields[{name}]` | Frontmatter has `name` and `description` (parametrized) |
| `test_skill_dirname_kebab_case[{name}]` | Directory names match `[a-z0-9]+(-[a-z0-9]+)*` (parametrized) |
| `test_skill_body_nonempty[{name}]` | Body after frontmatter is ≥ 50 chars (parametrized) |
| `test_no_orphan_skill_dirs` | No empty directories in skills/ |

### 2e. `test_commands.py`
| Test | Assertion |
|------|-----------|
| `test_command_count` | 24 command .md files |
| `test_command_has_frontmatter[{name}]` | Each command .md has YAML frontmatter (parametrized) |
| `test_command_frontmatter_required_fields[{name}]` | Frontmatter has `name` and `description` (parametrized) |
| `test_command_filenames_kebab_case[{name}]` | All filenames match `[a-z0-9]+(-[a-z0-9]+)*\.md` (parametrized) |
| `test_command_body_nonempty[{name}]` | Body after frontmatter is ≥ 10 chars (parametrized) |

### 2f. `test_cross_references.py`
| Test | Assertion |
|------|-----------|
| `test_flux_drive_roster_valid` | Call `scripts/validate-roster.sh` via subprocess — exits 0 (DRY: reuse existing script) |
| `test_hooks_json_scripts_exist` | Every .sh referenced in hooks.json exists |
| `test_lib_sourced_by_hooks` | Hooks that `source` lib.sh — lib.sh exists |
| `test_skill_agent_references` | Skills mentioning `subagent_type` values reference real agents (best-effort regex scan) |
| `test_routing_table_references` | Parse `skills/using-clavain/SKILL.md` for all `clavain:` references and verify each resolves to a real skill directory or command file |

### 2g. `test_scripts.py`
| Test | Assertion |
|------|-----------|
| `test_shell_scripts_syntax[{name}]` | All `.sh` files in `scripts/` and `hooks/` pass `bash -n` (parametrized) |
| `test_python_scripts_syntax[{name}]` | All `.py` files in `scripts/` pass `python3 -m py_compile` (parametrized) |
| `test_scripts_have_shebang[{name}]` | All `.sh` files start with `#!/` (parametrized) |
| `test_hook_entry_points_have_set_euo_pipefail` | Hook entry-point `.sh` files (those in hooks.json) contain `set -euo pipefail`. Excludes `lib.sh` which is a library, not an entry point. |

### 2h. `test_hook_protocol.py` (NEW — contract tests)
| Test | Assertion |
|------|-----------|
| `test_session_start_output_schema` | `session-start.sh` output matches `{"hookSpecificOutput": {"additionalContext": ...}}` schema |
| `test_autopilot_deny_output_schema` | `autopilot.sh` deny output matches `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}` schema |
| `test_auto_compound_block_output_schema` | `auto-compound.sh` block output matches `{"decision": "block", ...}` schema |

---

## Step 3: Tier 2 — Shell Tests (bats-core)

**Convention**: Use `setup_file`/`teardown_file` for expensive fixture creation (temp dirs, transcript files). Use `assert_success`, `assert_output`, `assert_line` from bats-assert.

### 3a. `session_start.bats`
| Test | Assertion |
|------|-----------|
| `test_outputs_valid_json` | stdout is valid JSON (pipe through `jq .`) |
| `test_has_additional_context` | JSON output has `.hookSpecificOutput.additionalContext` key via `jq -e` |
| `test_additional_context_nonempty` | `.hookSpecificOutput.additionalContext` length > 0 |
| `test_exits_zero` | Exit code is 0 |
| `test_handles_missing_skill_file` | Exits 0 even if `skills/using-clavain/SKILL.md` is moved/renamed |
| `test_handles_missing_lib` | Exits nonzero if `lib.sh` cannot be sourced (validates dependency) |
| `test_json_hostile_skill_content` | Skill file with quotes, backslashes, newlines produces valid JSON output |
| `test_no_debug_stderr` | stderr does not contain `+ set`, `DEBUG:`, or variable name leaks (allows platform noise) |

### 3b. `autopilot.bats`
| Test | Assertion |
|------|-----------|
| `test_passthrough_without_flag` | When `.claude/autopilot.flag` doesn't exist, exits 0 with empty/passthrough output |
| `test_deny_with_flag_jq_available` | When flag exists, outputs JSON with `jq -e '.hookSpecificOutput.permissionDecision == "deny"'` |
| `test_deny_with_flag_jq_unavailable` | When flag exists and jq not in PATH, outputs static deny JSON (fallback branch) |
| `test_handles_missing_project_dir` | When `CLAUDE_PROJECT_DIR` is unset, exits 0 |
| `test_handles_malformed_stdin` | When stdin is not valid JSON, exits 0 (no crash) |

### 3c. `lib.bats`
| Test | Assertion |
|------|-----------|
| `test_escape_for_json_basic` | `escape_for_json 'hello'` → `hello` |
| `test_escape_for_json_quotes` | `escape_for_json 'say "hi"'` → `say \"hi\"` |
| `test_escape_for_json_backslash` | `escape_for_json 'a\b'` → `a\\b` |
| `test_escape_for_json_newlines` | `escape_for_json $'line1\nline2'` → `line1\nline2` |
| `test_escape_for_json_tabs` | `escape_for_json $'col1\tcol2'` → `col1\tcol2` |
| `test_escape_for_json_empty` | `escape_for_json ''` → `` (empty) |
| `test_source_no_side_effects` | `bash -c 'source lib.sh 2>&1'` produces empty stdout and stderr |

### 3d. `auto_compound.bats`

**Fixture setup** (in `setup_file`): Create temp transcript JSONL files in `$BATS_FILE_TMPDIR`:
- `transcript_commit.jsonl` — contains a line with "git commit" text
- `transcript_insight.jsonl` — contains a line with "insight" marker
- `transcript_clean.jsonl` — no signal patterns

Each test pipes JSON to stdin with `stop_hook_active` and `transcript_path` pointing to the fixture:
```bash
echo '{"stop_hook_active": false, "transcript_path": "'$BATS_FILE_TMPDIR'/transcript_commit.jsonl"}' | bash "$HOOKS_DIR/auto-compound.sh"
```

| Test | Assertion |
|------|-----------|
| `test_noop_when_stop_hook_active` | When stdin JSON has `"stop_hook_active": true`, exits 0 with no block |
| `test_detects_commit_signal` | When transcript file contains "git commit" line, outputs block decision |
| `test_detects_insight_signal` | When transcript file contains "insight" marker, outputs block decision |
| `test_no_signal_passthrough` | When transcript file has no signals, exits 0 without blocking |
| `test_exits_zero_always` | Exit code is always 0 regardless of input |
| `test_handles_missing_transcript` | When `transcript_path` points to nonexistent file, exits 0 |

### 3e. `agent_mail_register.bats` (NEW — was missing)
| Test | Assertion |
|------|-----------|
| `test_exits_zero_when_agent_mail_down` | Exits 0 when `AGENT_MAIL_URL` is unreachable (graceful degradation) |
| `test_exits_zero_with_empty_stdin` | Exits 0 when stdin is empty |
| `test_outputs_valid_json_on_success` | When Agent Mail is reachable (mock curl), output is valid JSON |

### 3f. `dotfiles_sync.bats` (NEW — was missing)
| Test | Assertion |
|------|-----------|
| `test_exits_zero_when_sync_script_missing` | Exits 0 when sync script path doesn't exist |
| `test_exits_zero_always` | Exit code is always 0 regardless of outcome |

### 3g. `hooks_json.bats`
| Test | Assertion |
|------|-----------|
| `test_valid_json` | `jq . hooks/hooks.json` succeeds |
| `test_all_hook_types_valid` | All keys under `.hooks` are in allowed set |
| `test_matchers_valid_regex` | All `matcher` values compile as valid regex |
| `test_command_paths_use_plugin_root_var` | Commands use `${CLAUDE_PLUGIN_ROOT}` prefix |

---

## Step 4: Tier 3 — Smoke Tests (Local Claude Code Subagents)

> **Key learning from live smoke test (2026-02-10)**: All 8 tested agents passed in 7-29s each when dispatched with `model: haiku`, `max_turns: 3`, `run_in_background: true`. Review and research agents are fast and reliable. Workflow agents work but can be slow if they hit MCP tool permission denials.

### 4a. Create `tests/smoke/run-smoke-tests.sh`
A shell script that invokes `claude` CLI to run smoke tests locally. Uses Max subscription (no API key cost).

```bash
#!/usr/bin/env bash
set -euo pipefail
# Smoke test runner — dispatches agents via claude CLI
# Uses Max subscription, not API credits
# Usage: ./tests/smoke/run-smoke-tests.sh [--all | --review-only]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

claude --print --plugin-dir "$PROJECT_ROOT" -p "$(cat "$SCRIPT_DIR/smoke-prompt.md")"
```

### 4b. Create `tests/smoke/smoke-prompt.md`
The prompt dispatches agents with these constraints learned from live testing:
- `model: haiku` — fast, cheap, sufficient for smoke validation
- `max_turns: 3` — prevents runaway tool use chains
- `run_in_background: true` — parallel dispatch for speed
- Prompt includes: "SMOKE TEST — respond with a brief review only, **no tool use needed, do NOT use MCP tools**"
- Clean up any artifact files agents write to `docs/research/`

**Agent roster for smoke tests** (8 agents, validated 2026-02-10):

| Agent | subagent_type | Category | Test Input |
|-------|--------------|----------|------------|
| go-reviewer | `clavain:review:go-reviewer` | review/language | 10-line Go snippet |
| python-reviewer | `clavain:review:python-reviewer` | review/language | 10-line Python snippet |
| typescript-reviewer | `clavain:review:typescript-reviewer` | review/language | 10-line TypeScript snippet |
| architecture-strategist | `clavain:review:architecture-strategist` | review/domain | 3-package module description |
| security-sentinel | `clavain:review:security-sentinel` | review/domain | Endpoint with SQL injection |
| shell-reviewer | `clavain:review:shell-reviewer` | review/language | Bash script with quoting issues |
| best-practices-researcher | `clavain:research:best-practices-researcher` | research | "3 best practices for X" |
| spec-flow-analyzer | `clavain:workflow:spec-flow-analyzer` | workflow | 2-sentence feature spec |

**Validation criteria per agent**:
- Task completes without error
- Output is non-empty (> 50 chars)
- Output does not contain error traces or "permission denied"

**Pre-check**: Before dispatching, verify all agent files in the roster exist on disk. Fail fast if any are missing (avoids burning 10+ minutes on a renamed agent).

### 4c. Smoke test output
Results reported as markdown table:
```
| Agent | Category | Status | Time (s) | Notes |
|-------|----------|--------|----------|-------|
```

### 4d. CI integration for smoke tests
In `.github/workflows/test.yml`, the smoke job:
- Requires `ANTHROPIC_API_KEY` secret
- Uses `anthropics/claude-code-action@v1` with `anthropic_api_key` input
- Triggers on: daily cron (`0 6 * * *`), `workflow_dispatch`, and push only when relevant files change
- `timeout-minutes: 30` (8 agents at ~30s each plus overhead)
- `if: ${{ secrets.ANTHROPIC_API_KEY != '' }}` — allows forks without the secret to skip gracefully
- `continue-on-error: true` — smoke failures don't block merges (informational)

---

## Step 5: CI Workflow

### 5a. Create `.github/workflows/test.yml`

```yaml
name: Plugin Tests

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "0 6 * * *"  # Daily smoke tests
  workflow_dispatch:
    inputs:
      run_smoke:
        description: "Run smoke tests"
        type: boolean
        default: false

jobs:
  structural-and-shell:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
          cache-dependency-path: tests/pyproject.toml
      - uses: astral-sh/setup-uv@v4
      - name: Install bats-core
        run: |
          sudo apt-get update && sudo apt-get install -y bats
          npm install -g bats-support bats-assert
      - name: Structural tests (pytest)
        run: cd tests && uv run pytest structural/ -v --tb=short
      - name: Shell tests (bats)
        run: bats tests/shell/ --recursive --tap

  smoke:
    if: >-
      (github.event_name == 'schedule') ||
      (github.event_name == 'workflow_dispatch' && inputs.run_smoke) ||
      (github.event_name == 'push' && contains(github.event.head_commit.modified, 'hooks/')) ||
      (github.event_name == 'push' && contains(github.event.head_commit.modified, 'agents/')) ||
      (github.event_name == 'push' && contains(github.event.head_commit.modified, 'skills/'))
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - name: Smoke tests via Claude Code
        if: ${{ secrets.ANTHROPIC_API_KEY != '' }}
        uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          prompt_file: tests/smoke/smoke-prompt.md
          max_turns: 30
```

### 5b. Update CLAUDE.md
Replace the manual smoke-check section with reference to `tests/run-tests.sh`.

---

## Step 6: Local Runner & Documentation

### 6a. `tests/run-tests.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
# Run Tier 1 + Tier 2 locally (no API keys needed)
# Usage: ./tests/run-tests.sh [--structural-only | --shell-only | --smoke]

cd "$(dirname "${BASH_SOURCE[0]}")/.."

case "${1:-all}" in
  --structural-only)
    echo "=== Tier 1: Structural Tests (pytest) ==="
    cd tests && uv run pytest structural/ -v --tb=short
    ;;
  --shell-only)
    echo "=== Tier 2: Shell Tests (bats) ==="
    bats tests/shell/ --recursive
    ;;
  --smoke)
    echo "=== Tier 3: Smoke Tests (claude subagents) ==="
    tests/smoke/run-smoke-tests.sh
    ;;
  all)
    echo "=== Tier 1: Structural Tests (pytest) ==="
    cd tests && uv run pytest structural/ -v --tb=short
    cd ..
    echo "=== Tier 2: Shell Tests (bats) ==="
    bats tests/shell/ --recursive
    echo ""
    echo "Tiers 1+2 passed. Run with --smoke for Tier 3 (requires claude CLI)."
    ;;
esac
```

### 6b. Update CLAUDE.md quick commands
Replace manual checks with:
```bash
# Run all local tests (Tier 1+2)
./tests/run-tests.sh

# Run structural only
./tests/run-tests.sh --structural-only

# Run shell only
./tests/run-tests.sh --shell-only

# Run smoke tests (uses Max subscription)
./tests/run-tests.sh --smoke
```

---

## Implementation Order

| Step | What | Files Created | Est. Effort |
|------|------|---------------|-------------|
| 0 | Update doc counts | CLAUDE.md, AGENTS.md, plugin.json edits | Small |
| 1a-e | Infrastructure | conftest.py, test_helper.bash, pyproject.toml, run-tests.sh, fixtures | Medium |
| 2a | Plugin manifest tests | test_plugin_manifest.py | Small |
| 2b | Hooks JSON tests | test_hooks_json.py | Small |
| 2c | Agent tests | test_agents.py | Medium |
| 2d | Skill tests | test_skills.py | Small |
| 2e | Command tests | test_commands.py | Small |
| 2f | Cross-reference tests | test_cross_references.py | Medium |
| 2g | Script syntax tests | test_scripts.py | Small |
| 2h | Hook protocol tests | test_hook_protocol.py | Medium |
| 3a | session-start hook tests | session_start.bats | Medium |
| 3b | autopilot hook tests | autopilot.bats | Medium |
| 3c | lib.sh tests | lib.bats | Small |
| 3d | auto-compound tests | auto_compound.bats | Medium |
| 3e | agent-mail-register tests | agent_mail_register.bats | Small |
| 3f | dotfiles-sync tests | dotfiles_sync.bats | Small |
| 3g | hooks.json tests | hooks_json.bats | Small |
| 4a-d | Smoke test script + prompt | run-smoke-tests.sh, smoke-prompt.md | Medium |
| 5a-b | CI workflow | test.yml, CLAUDE.md update | Small |
| 6a-b | Local runner + docs | run-tests.sh, CLAUDE.md | Small |

**Total: ~25 files (22 new + 3 edited)**

---

## Design Decisions

1. **Hardcoded counts (35 agents, 34 skills, 24 commands, 6 roster)**: Intentional regression guards. When you add a new agent, you update the count. Catches accidental deletions. Must reconcile with docs first (Step 0).
2. **YAML frontmatter validation via Python**: More robust than regex. We use `yaml.safe_load()` on the frontmatter block.
3. **bats-core installed via apt/npm, not bats-action**: The `bats-core/bats-action@2.0.0` is a test *runner*, not just an installer. Using it as a setup step before a separate `bats` command may cause double execution or missing binary. Install bats separately, run separately.
4. **bats-support + bats-assert**: Standard companion libraries for idiomatic assertions (`assert_success`, `assert_output`, `assert_line`). Much better failure messages than raw `[ "$status" -eq 0 ]`.
5. **Smoke test subset (8 agents)**: Validated 2026-02-10 — all 8 passed in 7-29s each with haiku + max_turns:3. Representative subset covers review (5), research (1), workflow (1), domain (1).
6. **Smoke tests local-first, CI on schedule**: Local runs use Max subscription (free). CI requires `ANTHROPIC_API_KEY` secret. Daily cron + path-filtered push + manual dispatch. Forks skip gracefully.
7. **No behavioral assertions in smoke tests**: We check "didn't crash, produced output" — not "gave a good review." LLM output quality is not testable this way.
8. **Stub external commands in bats**: `curl` and `pgrep` are stubbed in `test_helper.bash` to avoid 1s+ timeouts per test in CI where Agent Mail and Xvfb aren't running.
9. **Separate test_hooks_json.py**: hooks.json is a different file from plugin.json with different concerns. Testing them together in `test_plugin_manifest.py` was misleading.
10. **Parametrized tests**: All per-file tests use `@pytest.mark.parametrize` with `ids` for clear per-file failure messages. A failure in agent #3 doesn't mask failures in agents #4-35.
11. **Fixture files for auto-compound**: Tests need real JSONL transcript files on disk because `auto-compound.sh` reads `transcript_path` from JSON stdin, then `tail -40` on that file. This is documented in the fixture setup section.
12. **Exclude lib.sh from set -euo pipefail check**: `lib.sh` is a sourced library, not an entry point. Only hook entry points (those referenced in hooks.json) need the strict mode check.
13. **validate-roster.sh reused via subprocess**: `test_cross_references.py` calls the existing script instead of reimplementing the AWK parsing logic. DRY.
14. **uv run, not pip install**: Project convention per CLAUDE.md. CI uses `astral-sh/setup-uv@v4`.

## Deferred (Future Iterations)

- **Version consistency test**: Compare plugin.json version against agent-rig.json (currently mismatched: 0.4.19 vs 0.4.18)
- **Marketplace version test**: Compare plugin.json against marketplace.json (requires cross-repo access)
- **Skill cross-reference graph**: Build a dependency graph of skills referencing other skills, validate no cycles
- **Agent prompt quality linting**: Check agents for common prompt issues (vague instructions, missing examples)
- **Hook performance benchmarks**: Measure hook execution time, flag regressions
- **Upstream staleness test**: Verify session-start.sh warns when `docs/upstream-versions.json` is older than 7 days
- **Companion detection branch tests**: Mock `command -v codex`, `test -d .beads`, etc. in session-start.sh tests
- **Expanded smoke roster**: Add remaining untested agents (rust-reviewer, concurrency-reviewer, etc.) once initial 8 are stable

## Appendix: Flux Drive Review Results (2026-02-10)

Three agents reviewed this plan. Full reports in `docs/research/flux-drive/2026-02-10-test-suite-design/`.

**Key findings incorporated**:
- P0: Agent count wrong (35 vs documented 29) — added Step 0 prerequisite
- P0: `agents/review/references/` breaks glob — fixed conftest fixture
- P1: Claude Code Action needs API key — fixed CI config, added schedule/path triggers
- P1: bats-action is a runner not installer — switched to apt/npm install
- P1: auto-compound fixture setup missing — added fixture section
- P1: autopilot jq fallback untested — added test case
- P1: autopilot JSON structure wrong — fixed to use `.hookSpecificOutput.permissionDecision`
- P1: session-start minimal negative testing — added 3 new test cases
- P1: Smoke timeout too short — increased to 30 min
- P1: curl timeout in bats — added stub in test_helper.bash
- IMP: Added hook protocol compliance tests (test_hook_protocol.py)
- IMP: Added routing table cross-reference test
- IMP: Added missing bats tests for agent-mail-register.sh and dotfiles-sync.sh
- IMP: Parametrized all per-file tests
- IMP: bats-support/bats-assert loaded in test_helper
- IMP: setup_file/teardown_file for expensive fixtures
- IMP: uv run instead of pip install
- IMP: pytest config via pyproject.toml
- IMP: validate-roster.sh reused via subprocess (DRY)
