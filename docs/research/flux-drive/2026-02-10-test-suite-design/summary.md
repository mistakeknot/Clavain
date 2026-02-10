## Flux Drive Enhancement Summary

Reviewed by 3 agents on 2026-02-10.

### Key Findings
- **Agent count is wrong and will break tests immediately** — plan says 35 agents but `agents/review/references/` subdirectory will inflate glob counts, and all canonical docs (AGENTS.md, CLAUDE.md, plugin.json) say 29 agents (3/3 agents)
- **Claude Code Action authentication model is wrong** — plan says "no API key needed" but the GitHub Action requires `ANTHROPIC_API_KEY`; there is no "Max subscription" mode for CI (1/3 agents)
- **Shell test fixtures are unspecified** — auto-compound.sh reads a transcript file from a path in JSON stdin, but the plan doesn't describe creating fixture files (2/3 agents)
- **Smoke test timeout too short and cost model absent** — 8-10 sequential agent dispatches will take 15-30 min, not the estimated 10 min; no cost analysis for running on every push (2/3 agents)
- **bats-core/bats-action@2.0.0 used incorrectly** — it's a runner, not an installer; using it as setup before a separate `bats` command may cause double-execution or missing binary (1/3 agents)

### Issues to Address
- [ ] P0-1: Reconcile agent count across plan/AGENTS.md/CLAUDE.md/plugin.json — determine canonical count and update all sources (3/3 agents: architecture, quality, performance)
- [ ] P0-2: Fix `test_agent_subdirectories_valid` — `agents/review/references/` exists as a non-agent subdirectory, glob must exclude it (2/3 agents: architecture, quality)
- [ ] P1-1: Fix Claude Code Action config — add `anthropic_api_key` input, set `max_turns: 30`, add `if:` condition for forks without the secret (1/3 agents: architecture)
- [ ] P1-2: Fix bats-core installation — either use `bats-action` as the runner directly (replacing separate `bats` step) or install bats via npm/apt (1/3 agents: architecture)
- [ ] P1-3: Specify auto-compound.sh test fixtures — tests need temp transcript JSONL files on disk, JSON stdin with `transcript_path` pointing to them (2/3 agents: architecture, quality)
- [ ] P1-4: Add autopilot.sh jq-unavailable fallback test — hook has two distinct output branches depending on jq availability (1/3 agents: quality)
- [ ] P1-5: Fix autopilot.bats JSON structure assertion — must assert `.hookSpecificOutput.permissionDecision`, not flat `permissionDecision` (1/3 agents: architecture)
- [ ] P1-6: Add `test_hooks_json_event_types` source of truth — document where the valid event type list comes from (1/3 agents: quality)
- [ ] P1-7: Expand session_start.bats — add tests for missing lib.sh, stale upstream-versions.json, JSON-hostile chars in skill content (1/3 agents: quality)
- [ ] P1-8: Smoke test timeout too short — increase from 15 to 30 minutes for 8-10 sequential dispatches (1/3 agents: performance)
- [ ] P1-9: session-start.sh tests will be slow due to curl timeout — stub out `curl` in test_helper.bash to avoid 1s wait per test (1/3 agents: performance)
- [ ] P2-1: Add CI dependency caching — `cache: 'pip'` in setup-python, consider npm cache for bats (2/3 agents: architecture, performance)
- [ ] P2-2: Fix conftest.py fixture naming — use lowercase `project_root` not `PROJECT_ROOT` (1/3 agents: quality)
- [ ] P2-3: Use `uv run` instead of `pip install` per project convention (1/3 agents: quality)
- [ ] P2-4: Add pytest configuration — `pyproject.toml` with `testpaths` and `rootdir` (2/3 agents: architecture, quality)
- [ ] P2-5: Add smoke test pre-check — verify agent files named in smoke-prompt.md exist before running expensive dispatches (1/3 agents: quality)
- [ ] P2-6: Consider path-filtered smoke triggers — only run smoke on push when hooks/, agents/, skills/, or .claude-plugin/ change (1/3 agents: performance)

### Improvements Suggested
1. **Add hook protocol compliance tests** — verify all hooks output correct `hookSpecificOutput` JSON structure as a contract test (architecture)
2. **Cross-reference the routing table** — parse `using-clavain/SKILL.md` for all `clavain:` references and verify they resolve to real files (architecture)
3. **Use @pytest.mark.parametrize** — per-file test results instead of one test iterating a collection; clearer failure messages (quality)
4. **Load bats-support/bats-assert** — idiomatic assertion helpers instead of raw `[ "$status" -eq 0 ]` checks (quality)
5. **Use setup_file/teardown_file** — expensive fixture creation (transcript files, temp dirs) should be per-file, not per-test (quality)
6. **Add missing hook tests** — `agent-mail-register.sh` and `dotfiles-sync.sh` are registered hooks with no bats tests planned (architecture)
7. **Schedule smoke tests** — daily cron + manual dispatch instead of every push to control subscription compute (performance)
8. **Stub external commands in bats** — override `curl`, `pgrep` in test_helper.bash to avoid network calls and timeouts in CI (performance)
9. **Call validate-roster.sh from pytest** — avoid duplicating its logic in `test_cross_references.py`; DRY (quality)

### Individual Agent Reports
- [fd-v2-architecture](./fd-v2-architecture.md) — needs-changes: 4 P1s on CI config, agent counts, bats setup, and hook fixture gaps
- [fd-v2-quality](./fd-v2-quality.md) — needs-changes: 2 P0s + 7 P1s on agent count inconsistencies, missing test branches, and naming conventions
- [fd-v2-performance](./fd-v2-performance.md) — needs-changes: 2 P1s on smoke timeout/cost model and session-start curl latency
