# Architecture Review: Clavain Test Suite Implementation Plan

**Reviewer**: fd-v2-architecture
**Document**: `/root/projects/Clavain/docs/plans/2026-02-10-test-suite-design.md`
**Date**: 2026-02-10

### Findings Index
- P1 | P1-1 | "CI Workflow" | Smoke test job uses claude-code-action incorrectly — missing API key config and unclear authentication model
- P1 | P1-2 | "Architecture" | Agent count in test_agent_count assertion (35 = 27+5+3) does not account for nested reference files in agents/review/references/
- P1 | P1-3 | "CI Workflow" | bats-core/bats-action@2.0.0 used as a setup step but not verified to exist at that version; bats invocation after it may fail
- P1 | P1-4 | "Step 3" | Shell test for auto-compound references `auto_compound.bats` but the actual hook file is `auto-compound.sh` — naming mismatch suggests confusion about how stdin is fed to Stop hooks
- P2 | P2-1 | "Step 2b" | Hardcoded agent count (35) and breakdown (27+5+3) already stale — AGENTS.md says 29 agents, plugin.json description says 29, CLAUDE.md says 29; only the filesystem has 35
- P2 | P2-2 | "Step 3a" | session-start.sh test `test_no_stderr_pollution` is too strict — the hook runs `find`, `curl`, `pgrep`, and `stat` which may emit stderr on missing tools
- P2 | P2-3 | "Step 4" | Smoke test section has no fallback or skip strategy when Claude Code Action is unavailable or subscription lapses
- P2 | P2-4 | "Step 3b" | autopilot.bats test `test_deny_with_flag` asserts `permissionDecision: "deny"` but the actual hook outputs nested JSON under `hookSpecificOutput` — test must match the real output structure
- IMP | IMP-1 | "Architecture" | Missing test tier for hook protocol compliance — no test verifies that SessionStart hooks output the exact `hookSpecificOutput.additionalContext` JSON structure
- IMP | IMP-2 | "Step 2e" | Cross-reference tests should also verify that `using-clavain/SKILL.md` routing table references match actual skills and commands
- IMP | IMP-3 | "CI Workflow" | No caching strategy for pip or bats dependencies — every run reinstalls from scratch
- IMP | IMP-4 | "Step 3" | Missing bats tests for `agent-mail-register.sh` and `dotfiles-sync.sh` — two of the four registered hook scripts are untested
- IMP | IMP-5 | "Architecture" | Test directory structure has no `__init__.py` files — pytest may not discover tests depending on the rootdir configuration
Verdict: needs-changes

---

### Summary (3-5 lines)

The three-tier architecture (structural/pytest, shell/bats, smoke/Claude Code Action) is a solid design that matches the plugin's component types well. The biggest risks are in the CI Workflow section (thin on smoke test authentication mechanics) and in several hardcoded counts that are already inconsistent with the plugin manifest and AGENTS.md. The shell test tier has good coverage of the four hooks registered in `hooks.json`, but misses the two remaining hook scripts (`agent-mail-register.sh`, `dotfiles-sync.sh`) and has a structural misunderstanding of the autopilot hook's JSON output format. The plan is implementable but needs corrections before coding begins.

---

### Issues Found

#### P1-1: Smoke test job uses claude-code-action incorrectly — missing API key config and unclear authentication model
**Severity**: P1
**Location**: "CI Workflow" section, Step 5a

The plan's smoke job configuration (lines 275-280) says:
```yaml
- name: Smoke tests via Claude Code
  uses: anthropics/claude-code-action@v1
  with:
    prompt_file: tests/smoke/smoke-prompt.md
    # Uses Max subscription, no API key needed
```

The comment "Uses Max subscription, no API key needed" is incorrect. The `anthropics/claude-code-action` GitHub Action requires an `ANTHROPIC_API_KEY` secret to authenticate API calls. There is no "Max subscription" mode for GitHub Actions — that is a local Claude Code desktop feature. The action needs either `anthropic_api_key` input or `ANTHROPIC_API_KEY` environment variable.

Additionally, the smoke prompt (Step 4a) instructs Claude Code to dispatch 8-10 `Task` tool calls as subagents. Each subagent consumes its own API calls. With `max_turns` set to ~30, this could cost significant API credits per CI run. The plan should specify:
1. The `anthropic_api_key` input parameter (referencing a GitHub secret)
2. A `max_turns` value (the plan mentions needing ~30 but does not set it in the YAML)
3. Whether this job should run on every push or only on explicit triggers (given cost)

**Suggestion**: Fix the YAML to include `anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}` and `max_turns: 30`. Consider making the smoke job trigger-conditional (`workflow_dispatch` or `schedule`) rather than on every push, given it takes 10+ minutes and costs real money.

---

#### P1-2: Agent count assertion does not account for nested reference files
**Severity**: P1
**Location**: "Step 2b" section, `test_agent_count`

The test asserts "35 agent .md files total (27 review + 5 research + 3 workflow)." The glob `agents/**/*.md` returns 36 results because `agents/review/references/concurrency-patterns.md` exists — a reference sub-file, not an agent definition. If the test uses a recursive glob like `agents/**/*.md`, it will count 36 and fail. If it uses a single-level glob like `agents/*/*.md`, it will get 35 but would still include any future reference files added to other subdirectories.

The plan's `conftest.py` fixture `all_agent_files()` is described as "all .md files in agents/**/" which is ambiguous. The test needs an explicit exclusion for known non-agent paths like `references/`.

**Suggestion**: Define `all_agent_files()` as `.md` files in `agents/{review,research,workflow}/` matching only direct children (not recursive), or add an explicit filter excluding `references/` subdirectory. Update the `test_agent_subdirectories_valid` test to also validate that `references/` (if present) is not counted as an agent category.

---

#### P1-3: bats-core/bats-action@2.0.0 usage is unverified
**Severity**: P1
**Location**: "CI Workflow" section, Step 5a

The workflow uses `bats-core/bats-action@2.0.0` as a setup step (line 264):
```yaml
- uses: bats-core/bats-action@2.0.0
```

This action is designed to **run** bats tests (it has its own test invocation logic), not just install bats. Using it as a setup step before a separate `bats` invocation may result in bats running twice or the second invocation not finding the binary. The action's interface expects inputs like `tests` (path to test files) rather than being used as a pure installer.

**Suggestion**: Either use `bats-core/bats-action@2.0.0` directly with its `tests` input to run the shell tests (replacing the separate `bats` step), or install bats-core manually via `npm install -g bats` or `sudo apt-get install -y bats` and then use the standalone `bats` command. The plan's `run-tests.sh` already handles bats invocation, so installing bats separately and calling the local runner is cleaner.

---

#### P1-4: auto-compound bats test naming and Stop hook input/output model needs clarification
**Severity**: P1
**Location**: "Step 3d" section, `auto_compound.bats`

The plan names the bats file `auto_compound.bats` but the actual hook script is `/root/projects/Clavain/hooks/auto-compound.sh`. More importantly, the test descriptions suggest passing JSON via stdin (e.g., "When stdin has `stop_hook_active: true`"), but the plan does not describe how this mocking works in bats.

The actual `auto-compound.sh` reads `$INPUT` from stdin, parses it with `jq`, extracts `transcript_path`, and reads a file at that path. The tests need to:
1. Create a mock transcript file (JSONL format) with appropriate signal patterns
2. Pipe valid JSON with `stop_hook_active` and `transcript_path` fields to stdin

The `test_detects_commit_signal` test says "When transcript contains 'git commit'" — but the hook reads a transcript **file** pointed to by JSON on stdin, not the stdin itself. The test fixtures setup is completely unspecified.

**Suggestion**: Add a fixture specification for Stop hook tests: (a) a minimal JSONL transcript file with git commit signal, (b) a minimal JSONL transcript with insight signal, (c) a minimal JSON stdin payload with transcript_path pointing to the fixture. Document the exact stdin→file→detection chain so the bats tests actually exercise the right code path.

---

#### P2-1: Hardcoded counts are already inconsistent across project documentation
**Severity**: P2
**Location**: "Step 2b" section, "Design Decisions" section

The plan hardcodes 35 agents, matching the filesystem. But:
- `AGENTS.md` Quick Reference says "29 agents"
- `.claude-plugin/plugin.json` description says "29 agents"
- `CLAUDE.md` says "29 agents"
- `AGENTS.md` review category says "21 review agents"

The filesystem has 27 review + 5 research + 3 workflow = 35. The documentation was not updated when the fd-v2 agents were added (6 agents: fd-v2-architecture, fd-v2-safety, fd-v2-correctness, fd-v2-quality, fd-v2-user-product, fd-v2-performance) plus fd-code-quality and fd-user-experience (2 more).

This means the test will pass against the filesystem but conflict with every documentation reference. The plan should either:
1. Fix the documentation as a prerequisite step, or
2. Note the inconsistency and make the test the source of truth

**Suggestion**: Add a Step 0 that updates AGENTS.md, CLAUDE.md, and plugin.json description to reflect the actual 35-agent count before writing tests that assert it. Alternatively, add a cross-reference test that verifies documentation counts match filesystem counts (turning this inconsistency into a test failure rather than a manual audit).

---

#### P2-2: session-start.sh stderr assertion is too strict
**Severity**: P2
**Location**: "Step 3a" section, `test_no_stderr_pollution`

The test asserts "stderr is empty (no debug output leaking into hook response)." However, examining `session-start.sh` at `/root/projects/Clavain/hooks/session-start.sh`, the script runs:
- `find` (line 22) — may emit "permission denied" on certain directory layouts
- `curl` (line 33) — emits connection errors if agent-mail is down (stderr suppressed with `2>/dev/null`, but edge cases exist)
- `pgrep` (line 38) — may write to stderr if `/proc` is restricted
- `stat` (line 55) — may emit errors on missing files

All of these have `2>/dev/null` redirections, but in a CI container environment, some may behave differently. The test should assert "stderr does not contain hook-specific debug output" rather than "stderr is empty."

**Suggestion**: Change the assertion to verify that stderr does not contain known debug patterns (e.g., `+ set`, `DEBUG:`, or the hook's own variable names) rather than requiring empty stderr. This makes the test resilient to platform-specific noise.

---

#### P2-3: No skip/fallback strategy for smoke tests
**Severity**: P2
**Location**: "Step 4" section

The smoke test tier has no strategy for when:
- The `ANTHROPIC_API_KEY` secret is not configured (e.g., forks, new contributors)
- The Claude Code Action itself fails to start
- The subscription/quota is exhausted mid-run

The plan should specify whether the smoke job is `continue-on-error: true` or whether it uses a conditional like `if: secrets.ANTHROPIC_API_KEY != ''` to skip gracefully.

**Suggestion**: Add `if: ${{ secrets.ANTHROPIC_API_KEY != '' }}` to the smoke job to allow forks to run structural+shell tests without failing on the smoke tier. Add `continue-on-error: true` if smoke failures should not block merges.

---

#### P2-4: autopilot.bats test asserts wrong JSON structure
**Severity**: P2
**Location**: "Step 3b" section, `test_deny_with_flag`

The test says: "When flag file exists and tool is Edit, outputs JSON with `permissionDecision: 'deny'`." The actual `autopilot.sh` output (lines 44-50 of `/root/projects/Clavain/hooks/autopilot.sh`) wraps the decision in `hookSpecificOutput`:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "..."
  }
}
```

The test description is ambiguous — it might mean "the JSON contains a `permissionDecision` key somewhere" or it might mean a flat `{"permissionDecision": "deny"}`. The implementer needs to know the exact jq path to assert: `.hookSpecificOutput.permissionDecision`.

**Suggestion**: Specify the exact jq assertion in the test description: `jq -e '.hookSpecificOutput.permissionDecision == "deny"'`. This removes ambiguity for the implementer.

---

### Improvements Suggested

#### IMP-1: Add hook protocol compliance tests
**Rationale**: The plan tests individual hook behaviors but never verifies the protocol contract. All SessionStart hooks must output `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}`. All PreToolUse hooks must output `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "..."}}`. A protocol compliance test in Tier 2 would catch format regressions before they break Claude Code.

Add a `hook_protocol.bats` file that runs each hook with minimal valid input and validates the output JSON matches the Claude Code hook protocol schema. This is different from testing individual behavior — it is a contract test.

#### IMP-2: Cross-reference tests should cover the routing table
**Rationale**: The `using-clavain/SKILL.md` routing table is the most important cross-reference in the entire plugin — it maps stage/domain/language triples to specific skills, agents, and commands. A dead reference in this table means Claude Code cannot route to that component. The plan's `test_cross_references.py` covers flux-drive roster references and hook script references, but not the routing table itself.

Add a test that parses `skills/using-clavain/SKILL.md` for all `clavain:` references and verifies each one resolves to an existing skill directory or command file. This catches the most impactful class of reference rot.

#### IMP-3: Add CI dependency caching
**Rationale**: The workflow installs `pytest` + `pyyaml` and bats-core on every run. For a job that runs on every push, this adds unnecessary latency and network dependency.

Add `actions/cache@v4` for pip dependencies (keyed on `tests/requirements-dev.txt` hash) and use the built-in caching in `actions/setup-python@v5` via `cache: 'pip'`.

#### IMP-4: Missing bats tests for agent-mail-register.sh and dotfiles-sync.sh
**Rationale**: The `hooks.json` registers four hook scripts: `session-start.sh`, `autopilot.sh`, `auto-compound.sh`, and `agent-mail-register.sh`, plus `dotfiles-sync.sh` on SessionEnd. The plan provides bats tests for three of these (`session_start.bats`, `autopilot.bats`, `auto_compound.bats`) but omits `agent-mail-register.sh` and `dotfiles-sync.sh`.

`agent-mail-register.sh` has testable behavior: it should exit 0 when Agent Mail is unreachable (graceful degradation), and it reads stdin JSON to extract `session_id`. `dotfiles-sync.sh` should exit 0 when the sync script does not exist. Both are simple tests that would improve coverage of the hook surface.

#### IMP-5: Pytest discovery may need rootdir configuration
**Rationale**: The `tests/structural/` directory has no `__init__.py` files mentioned in the plan. While pytest can discover tests without them (using `rootdir` auto-detection), the plan's `conftest.py` uses fixtures that reference `PROJECT_ROOT` as "Path to repo root." If `conftest.py` computes this relative to its own location, it must be two directories up (`tests/structural/../../`). Without explicit `rootdir` or `pyproject.toml` `[tool.pytest]` configuration, pytest may resolve paths incorrectly when run from different working directories (e.g., from the CI checkout root vs. from `tests/`).

Add a `pyproject.toml` section or `pytest.ini` with `testpaths = ["tests/structural"]` and `rootdir = .` to ensure consistent behavior regardless of invocation directory.

---

### Overall Assessment

The plan is well-structured with a clear tier separation that matches the plugin's architecture: static validation (pytest) for cross-reference integrity, behavioral testing (bats) for hook correctness, and integration testing (Claude Code Action) for agent dispatch. The primary architectural concern is the CI Workflow section, which is underspecified for the smoke tier (wrong authentication model, no skip strategy, no cost controls) and has a likely-broken bats-core installation step. The hardcoded counts being already stale is a P2 risk that will cause immediate test failures if not addressed first. With the changes outlined above, this plan is ready for implementation.

<!-- flux-drive:complete -->
