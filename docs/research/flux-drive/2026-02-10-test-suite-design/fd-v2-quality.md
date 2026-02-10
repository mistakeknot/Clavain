# Quality & Style Review: Clavain Test Suite Implementation Plan

**Reviewed:** `/root/projects/Clavain/docs/plans/2026-02-10-test-suite-design.md`
**Reviewer:** fd-v2-quality
**Date:** 2026-02-10

### Findings Index
- P0 | P0-1 | "Step 2b: test_agents.py" | Agent count hardcoded to 35 but actual count is 35 with a references/ subdirectory that will break the test
- P0 | P0-2 | "Step 2b: test_agents.py" | test_agent_subdirectories_valid will fail — agents/review/references/ exists as a fourth subdirectory
- P1 | P1-1 | "Step 2b: test_agents.py" | Agent count says "27 review + 5 research + 3 workflow = 35" but actual review count is 27 only if references/ .md files are excluded
- P1 | P1-2 | "Step 2: Tier 1" | Inconsistent counts across plan vs. AGENTS.md vs. plugin.json — plan says 35 agents, AGENTS.md says 29, CLAUDE.md says 29
- P1 | P1-3 | "Step 2e: test_cross_references.py" | test_flux_drive_roster_agents_exist assumes all roster agents are in agents/review/ — duplicates validate-roster.sh without matching its logic
- P1 | P1-4 | "Step 2a: test_plugin_manifest.py" | test_hooks_json_event_types uses wrong allowed set — missing "SessionEnd", includes "SessionEnd" variant issues
- P1 | P1-5 | "Step 3b: autopilot.bats" | Missing test for the jq-unavailable fallback path — autopilot.sh has two distinct JSON output branches
- P1 | P1-6 | "Step 3d: auto_compound.bats" | Test descriptions reference wrong input format — auto-compound.sh reads JSON with jq, not flat text fields
- P1 | P1-7 | "Step 3a: session_start.bats" | test_handles_missing_skill_file is the only negative test — missing tests for companion detection branches and upstream staleness warning
- P2 | P2-1 | "Step 1c: conftest.py" | Fixture naming uses ALL_CAPS module constants mixed with function-style fixtures — inconsistent pytest idiom
- P2 | P2-2 | "Step 2d: test_commands.py" | test_command_count hardcodes 24 but actual count is 24 — correct now but plan header says "24 commands" while AGENTS.md says "27 commands"
- P2 | P2-3 | "Step 3c: lib.bats" | test_source_no_side_effects does not test for stderr pollution (lib.sh has a loop with printf that could warn)
- P2 | P2-4 | "Step 4: Tier 3 — Smoke Tests" | No validation that smoke-prompt.md itself is syntactically valid or that selected agents still exist
- IMP | IMP-1 | "Step 1d: test_helper.bash" | Should load bats-support and bats-assert for idiomatic assertion style
- IMP | IMP-2 | "Step 2: Tier 1" | Missing parametrize decorators — every agent/skill/command test should use @pytest.mark.parametrize for clear per-file failure messages
- IMP | IMP-3 | "Step 3: Tier 2" | Bats tests should use setup_file/teardown_file for expensive operations (mock transcript creation, temp dirs)
- IMP | IMP-4 | "Step 5a: CI Workflow" | pip install in CI instead of uv run — project convention says use uv run for Python dependencies
- IMP | IMP-5 | "Step 2f: test_scripts.py" | test_hooks_have_set_euo_pipefail will not catch auto-compound.sh which uses set -euo pipefail but may break for hooks that source lib.sh differently
- IMP | IMP-6 | "Architecture" | No __init__.py or pytest.ini/pyproject.toml configuration — test discovery may fail without explicit configuration
Verdict: needs-changes

---

### Summary (3-5 lines)

The plan is well-structured with a sound three-tier architecture (structural/shell/smoke). However, it has two P0 issues: the hardcoded agent count and subdirectory assertions are wrong because `agents/review/references/` exists as a non-agent subdirectory containing `concurrency-patterns.md`, and the count arithmetic (27+5+3=35) does not account for the fact that AGENTS.md says 29 agents. The plan also has several count inconsistencies between the plan text, AGENTS.md, CLAUDE.md, and plugin.json that will cause tests to fail immediately on first run. The shell test section has good coverage of the happy paths but misses several important branching paths in the actual hook scripts, particularly autopilot.sh's jq-unavailable fallback and session-start.sh's companion detection logic.

### Issues Found

**P0-1: Agent count and references/ subdirectory will break test_agent_count and test_agent_subdirectories_valid**
- **Location:** Step 2b: `test_agents.py`, lines for `test_agent_count` and `test_agent_subdirectories_valid`
- **Convention:** The plan states: "35 agent .md files total (27 review + 5 research + 3 workflow)" and "Only `review/`, `research/`, `workflow/` subdirs exist"
- **Violation:** The actual filesystem has `agents/review/references/concurrency-patterns.md` -- a fourth subdirectory (`references/`) inside `agents/review/`. This means:
  1. `test_agent_subdirectories_valid` will fail because `references/` is a valid non-agent subdirectory
  2. A naive glob of `agents/**/*.md` will count `references/concurrency-patterns.md` as an agent file, inflating the count
  3. The actual agent .md files (excluding references/) are: 27 review + 5 research + 3 workflow = 35. But AGENTS.md says "29 agents" and plugin.json says "29 agents". The plan uses 35 which contradicts both canonical sources.
- **Fix:** (a) The conftest `all_agent_files()` fixture must explicitly exclude `references/` subdirectories or non-frontmatter .md files. (b) `test_agent_subdirectories_valid` must allow `references/` as a known non-agent subdirectory. (c) Reconcile the count: determine whether the 6 `fd-v2-*` agents and 2 `fd-*` agents are counted in the official "29" or if they were added after plugin.json was last updated. The test should match the actual intended count, documented in one canonical place.

**P0-2: agents/review/references/ will trip test_agent_subdirectories_valid**
- **Location:** Step 2b: `test_agents.py`, `test_agent_subdirectories_valid`
- **Convention:** Test asserts "Only `review/`, `research/`, `workflow/` subdirs exist"
- **Violation:** `/root/projects/Clavain/agents/review/references/` exists and contains `concurrency-patterns.md`. This is a sub-resource directory, not an agent category. The test as designed will report this as a failure.
- **Fix:** Either (a) adjust the assertion to check only top-level subdirectories of `agents/` (not nested ones), or (b) add `references/` to an allow-list of known non-agent subdirectories, or (c) restructure the test to verify that each top-level subdir is in the allowed set `{review, research, workflow}` and ignore nested structure.

**P1-1: Review agent count decomposition is ambiguous**
- **Location:** Step 2b: `test_agents.py`, `test_agent_count`
- **Convention:** AGENTS.md Quick Reference table says "29 agents". Plugin.json description says "29 agents". CLAUDE.md says "29 agents".
- **Violation:** The plan says "35 agent .md files total (27 review + 5 research + 3 workflow)". By my count of actual files: 27 review agents (excluding `references/concurrency-patterns.md`) + 5 research + 3 workflow = 35. This means 6 agents were added since the "29" count was documented. The test needs to either (a) use the actual count (35) and update AGENTS.md/plugin.json simultaneously, or (b) use 29 and exclude the fd-v2 agents from the count. Either way, the plan should acknowledge the discrepancy.
- **Fix:** Add a prerequisite step: update AGENTS.md, CLAUDE.md, and plugin.json to reflect the actual agent count before writing tests that assert on it. Alternatively, derive the expected count from a single source of truth (e.g., plugin.json) rather than hardcoding.

**P1-2: Count inconsistencies across plan, AGENTS.md, plugin.json, and CLAUDE.md**
- **Location:** Step 2 (Tier 1) broadly, and Design Decisions section
- **Convention:** Single source of truth for component counts
- **Violation:** The following counts are stated in different places:
  - Plan: 35 agents, 34 skills, 24 commands
  - CLAUDE.md: "34 skills, 29 agents, 24 commands"
  - AGENTS.md: "34 skills, 29 agents, 24 commands" but also "27 commands" in the validation section
  - Plugin.json: "29 agents, 24 commands, 34 skills"
  - Actual filesystem: 35 agent .md files (minus 1 reference = 34 agents or 35 depending on counting), 34 skills, 24 commands

  The commands count also has a discrepancy: AGENTS.md validation section says `commands/*.md` should be 27 but the plan says 24 and the actual count is 24.
- **Fix:** Before implementing the test suite, reconcile all count sources. The structural tests should ideally read the expected count from a single canonical location (e.g., plugin.json) or from a dedicated test-constants file, rather than scattering magic numbers across test files.

**P1-3: test_flux_drive_roster_agents_exist duplicates validate-roster.sh but with different assumptions**
- **Location:** Step 2e: `test_cross_references.py`
- **Convention:** `scripts/validate-roster.sh` already validates the flux-drive roster. It parses the "Plugin Agents (clavain)" table from `skills/flux-drive/SKILL.md`.
- **Violation:** The plan's `test_flux_drive_roster_agents_exist` says "Every agent name in the flux-drive roster table has a corresponding `agents/review/{name}.md`". This duplicates `validate-roster.sh` but the plan doesn't reference or reuse that script. Worse, the plan doesn't specify which file contains the roster table -- `validate-roster.sh` reads from `skills/flux-drive/SKILL.md`, but the plan just says "the flux-drive roster table" without specifying. If the implementation guesses wrong, it will parse the wrong file.
- **Fix:** Either (a) call `validate-roster.sh` from the pytest test (via subprocess) to avoid duplication, or (b) replicate the exact same parsing logic with an explicit reference to `skills/flux-drive/SKILL.md`. Option (a) is preferred for DRY.

**P1-4: test_hooks_json_event_types allowed set may be wrong**
- **Location:** Step 2a: `test_plugin_manifest.py`
- **Convention:** The actual `hooks.json` uses event types: `PreToolUse`, `SessionStart`, `Stop`, `SessionEnd`
- **Violation:** The plan says the allowed set is: `PreToolUse`, `PostToolUse`, `Notification`, `SessionStart`, `SessionEnd`, `Stop`. While including extras (PostToolUse, Notification) is fine as forward-compatible, the real risk is that the test is in `test_plugin_manifest.py` -- but hooks.json is a separate file from plugin.json. Conceptually this test belongs in a `test_hooks_json.py` or at minimum the naming is misleading. More importantly, the plan doesn't specify where the canonical list of valid event types comes from. If Claude Code adds new event types, this test will false-positive.
- **Fix:** (a) Move hooks.json tests to their own file or clearly document that `test_plugin_manifest.py` covers both plugin.json and hooks.json. (b) Document the source of truth for valid event types (Claude Code documentation) and add a comment in the test.

**P1-5: autopilot.bats missing test for jq-unavailable fallback**
- **Location:** Step 3b: `autopilot.bats`
- **Convention:** `autopilot.sh` has two distinct output paths: one using `jq -n` (lines 43-50) and one using a heredoc fallback (lines 52-61) when jq is not available.
- **Violation:** The plan only tests the happy path (jq available). The jq-unavailable path produces a different, static deny reason that omits the file path. This is a meaningful behavioral difference that should be tested.
- **Fix:** Add a test case that temporarily removes jq from PATH (e.g., `PATH=/usr/bin:/bin`) or mocks `command -v jq` to fail, then verifies the fallback JSON output contains the static deny reason.

**P1-6: auto_compound.bats test descriptions reference wrong input format**
- **Location:** Step 3d: `auto_compound.bats`
- **Convention:** `auto-compound.sh` reads JSON from stdin via `cat` and parses it with `jq -r '.stop_hook_active // false'` and `jq -r '.transcript_path // empty'`.
- **Violation:** The plan says `test_noop_when_stop_hook_active` checks "When stdin has `stop_hook_active: true`" -- this is correct, but the plan description for `test_detects_commit_signal` says "When transcript contains 'git commit'" which requires a real transcript *file* at the path specified in the JSON input, not just piped text. The test will need to create a temporary transcript JSONL file, write content with the signal patterns into it, then pass `{"stop_hook_active": false, "transcript_path": "/tmp/test-transcript.jsonl"}` as stdin. The plan doesn't describe this fixture setup at all.
- **Fix:** Add fixture creation details: each signal-detection test needs (a) a temp file with JSONL content containing the signal pattern, (b) JSON stdin pointing to that file. This is non-trivial setup that should be in `setup()` or described in `test_helper.bash`.

**P1-7: session_start.bats has minimal negative testing**
- **Location:** Step 3a: `session_start.bats`
- **Convention:** `session-start.sh` has multiple branches: companion detection (codex dispatch, beads, agent-mail, oracle), upstream staleness warning, and the core skill injection.
- **Violation:** The plan only tests: valid JSON output, has additionalContext, context is non-empty, exits zero, handles missing skill file, no stderr. It misses:
  - What happens when `lib.sh` is missing (source will fail with `set -e`)
  - The upstream staleness warning branch (when `docs/upstream-versions.json` is older than 7 days)
  - Companion detection branches (these call external tools like `curl`, `pgrep`, `command -v` -- should be mocked)
  - Output when skill file content contains JSON-hostile characters (quotes, backslashes, newlines)
- **Fix:** Add tests for: (a) missing lib.sh produces an error exit (or graceful fallback), (b) stale upstream-versions.json triggers warning text in output, (c) skill content with special characters is properly escaped in output JSON. The companion detection branches can be deferred but should be noted in the "Deferred" section.

**P2-1: conftest.py fixture naming mixes styles**
- **Location:** Step 1c: `conftest.py`
- **Convention:** Standard pytest convention uses lowercase function-style fixtures: `project_root`, `agents_dir`. Module-level constants are `UPPER_CASE`.
- **Violation:** The plan lists `PROJECT_ROOT`, `AGENTS_DIR` etc. as fixtures alongside `all_agent_files()`, `plugin_json()`. The capitalized names suggest module constants, but the parenthesized names suggest fixture functions. This mixed naming will confuse implementers.
- **Fix:** Use consistent pytest fixture style: `project_root`, `agents_dir`, `skills_dir`, `commands_dir`, `hooks_dir` as `@pytest.fixture(scope="session")` functions. Reserve UPPER_CASE for true module constants (if any).

**P2-2: Command count discrepancy between AGENTS.md and plan**
- **Location:** Step 2d: `test_commands.py`
- **Convention:** AGENTS.md validation section says `ls commands/*.md` should be 27. Plan says 24. Actual filesystem shows 24.
- **Violation:** AGENTS.md is stale (says 27 commands but there are 24). The plan's count of 24 is correct for the filesystem, but this means AGENTS.md will fail its own documented validation. The test suite should trigger an update to AGENTS.md.
- **Fix:** Note in the plan that AGENTS.md needs its command count updated from 27 to 24 as a prerequisite to implementing tests, otherwise the documentation and tests will contradict each other.

**P2-3: lib.bats test_source_no_side_effects incomplete**
- **Location:** Step 3c: `lib.bats`
- **Convention:** `lib.sh` contains a `for` loop with `printf` inside `escape_for_json`. Sourcing the file should only define the function, not execute it.
- **Violation:** The plan says "Sourcing lib.sh doesn't produce stdout or change directory" but doesn't check stderr. While `lib.sh` is clean today, a future change could add a diagnostic message. Checking stderr is cheap insurance.
- **Fix:** Extend the test: `run bash -c 'source lib.sh 2>&1'` and assert both stdout and stderr are empty.

**P2-4: Smoke test section lacks self-validation**
- **Location:** Step 4: Tier 3 — Smoke Tests
- **Convention:** Smoke tests depend on specific agent names existing (`go-reviewer`, `architecture-strategist`, etc.)
- **Violation:** The plan hardcodes 8 agent names in `smoke-prompt.md` but has no mechanism to verify those agents still exist before running the expensive smoke test. If an agent is renamed, the smoke test will burn 10+ minutes of Claude Code Action time before failing.
- **Fix:** Add a lightweight pre-check in the CI workflow: before the smoke job runs, verify that all agents named in `smoke-prompt.md` have corresponding files in `agents/`. This can be a simple grep + file-existence check in the `structural-and-shell` job, with the smoke job depending on it.

### Improvements Suggested

**IMP-1: Load bats-support and bats-assert in test_helper.bash**
- The plan's `test_helper.bash` only sets environment variables. Idiomatic bats testing uses the `bats-support` and `bats-assert` libraries for `assert_success`, `assert_output`, `assert_line`, and `refute_output` helpers. Without these, every test will use raw `[ "$status" -eq 0 ]` checks that produce poor failure messages.
- **Rationale:** bats-support/bats-assert are the standard companion libraries listed in the bats-core documentation. The `bats-core/bats-action@2.0.0` GitHub Action already makes them available. Adding `load 'bats-support/load'` and `load 'bats-assert/load'` to `test_helper.bash` is trivial and dramatically improves assertion readability and failure diagnostics.

**IMP-2: Use @pytest.mark.parametrize for per-file structural tests**
- Tests like `test_agent_has_frontmatter`, `test_skill_has_skillmd`, `test_command_filenames_kebab_case` operate on collections of files. If implemented as a single test iterating over all files, a failure in agent #3 will mask failures in agents #4-35.
- **Rationale:** `@pytest.mark.parametrize` with an `ids` parameter (using the filename) gives one test result per file. Failures show exactly which files are broken. This is standard pytest practice for data-driven validation. Example:
  ```python
  @pytest.mark.parametrize("agent_file", all_agents, ids=lambda p: p.stem)
  def test_agent_has_frontmatter(agent_file):
      ...
  ```

**IMP-3: Use setup_file/teardown_file in bats tests for expensive fixtures**
- The `auto_compound.bats` tests need temporary transcript files (JSONL format). Creating these in `setup()` (per-test) is wasteful if the same fixture serves multiple tests.
- **Rationale:** `setup_file` runs once per .bats file, while `setup` runs before every `@test`. Transcript fixture files that are read-only across tests should be created in `setup_file` and cleaned up in `teardown_file`. This is idiomatic bats-core for shared test data.

**IMP-4: Use uv run instead of pip install in CI**
- **Location:** Step 5a: CI Workflow
- **Convention:** CLAUDE.md global instructions state "Use `uv run` for Python dependencies, not `pip install`"
- **Rationale:** The plan's CI workflow uses `pip install -r tests/requirements-dev.txt`. This contradicts the project's established convention. Replace with:
  ```yaml
  - uses: astral-sh/setup-uv@v4
  - run: uv run pytest tests/structural/ -v --tb=short
  ```
  `uv run` auto-resolves dependencies from a `pyproject.toml` or inline script metadata without a separate install step.

**IMP-5: test_hooks_have_set_euo_pipefail edge case**
- **Location:** Step 2f: `test_scripts.py`
- **Convention:** AGENTS.md says "Use `set -euo pipefail` in all hook scripts"
- **Rationale:** The test checks for the string `set -euo pipefail` in hook scripts. However, `lib.sh` does NOT contain `set -euo pipefail` -- it is a library sourced by other scripts, not an entry point. The test should either (a) only check entry-point hook scripts (those referenced in hooks.json), not library files, or (b) explicitly exclude `lib.sh` from this check. As written, `lib.sh` will fail this test.

**IMP-6: Missing pytest configuration**
- **Location:** Architecture section
- **Convention:** Standard pytest projects include either `pyproject.toml` with `[tool.pytest.ini_options]` or a standalone `pytest.ini`/`setup.cfg`
- **Rationale:** Without `testpaths = ["tests/structural"]` configured somewhere, pytest may not discover tests correctly, especially if run from a non-root directory. The plan creates `requirements-dev.txt` but no `pyproject.toml` or `pytest.ini`. Adding a minimal `pyproject.toml` in the `tests/` directory (or project root) with pytest configuration would prevent discovery issues and allow configuring options like `--tb=short` as defaults.

### Overall Assessment

The plan is architecturally sound -- the three-tier approach (structural/shell/smoke) is well-matched to Clavain's component types, and the choice of pytest + bats-core is appropriate. However, it needs changes before implementation. The two P0 issues (agent count mismatch with canonical documentation, and the `references/` subdirectory breaking assumptions) will cause immediate test failures. The multiple P1 issues around count inconsistencies, missing test fixture setup for auto-compound.bats, and the absent jq-fallback test path mean the shell tests will be incomplete on first implementation. Reconciling the agent/command counts across AGENTS.md, CLAUDE.md, plugin.json, and the test plan should be a prerequisite step before any test code is written.

<!-- flux-drive:complete -->
