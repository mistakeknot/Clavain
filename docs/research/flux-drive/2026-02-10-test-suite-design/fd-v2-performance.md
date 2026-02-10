# Performance Review: Clavain Test Suite Design

## Findings Index
- P1 | P1-1 | "Step 4: Tier 3 — Smoke Tests" | Smoke test cost model is absent and 15-minute timeout is likely insufficient for 8-10 sequential agent dispatches
- P1 | P1-2 | "Step 3: Tier 2 — Shell Tests" | session-start.sh bats tests will be slow due to escape_for_json control-character loop over 6KB content
- P2 | P2-1 | "Step 5: CI Workflow" | Dependency installation overhead is unmanaged and will dominate Tier 1+2 execution time
- P2 | P2-2 | "Step 2: Tier 1 — Structural Tests" | Hardcoded counts create unnecessary CI churn as plugin grows, not a perf issue per se but increases CI frequency
- IMP | IMP-1 | "Step 4: Tier 3 — Smoke Tests" | Run smoke tests on schedule rather than every push to control cost and CI queue time
- IMP | IMP-2 | "Step 5: CI Workflow" | Cache pip and bats dependencies to eliminate ~15-20s install overhead per run
- IMP | IMP-3 | "Step 3: Tier 2 — Shell Tests" | Bats tests for auto-compound.sh need a mock transcript file on disk, which the plan does not mention
Verdict: needs-changes

---

### Summary (3-5 lines)

The Tier 1 and Tier 2 time estimates (~10s combined) are achievable for test execution time alone, but they ignore dependency installation overhead which will add 15-30s on a cold runner. The critical gap is in Tier 3: the plan provides no cost model for running 8-10 Claude Code Action agent dispatches on every push. Each subagent dispatch involves a full LLM round-trip including tool use, so 8-10 dispatches will realistically take 15-30 minutes, not the estimated ~10 minutes -- and each push burns Max subscription compute. The `escape_for_json` function in `lib.sh` has an O(n*26) loop over control characters that, while fine for the current 6KB file, will cause measurable slowdown in bats tests if the skill file grows or if the function is tested with large inputs.

---

### Issues Found

#### P1-1: Smoke test cost model is absent and 15-minute timeout is likely insufficient

**Location:** Step 4 (Tier 3 -- Smoke Tests), Section 4a and 5a (CI Workflow)

**Problem:** The plan specifies `timeout-minutes: 15` for the smoke job that dispatches 8-10 Claude Code Action subagents sequentially. Each subagent dispatch via the `Task` tool involves:
1. Claude Code Action startup and plugin loading (~30-60s per invocation)
2. The orchestrating agent reading the prompt, selecting agents, and formulating each Task call (~10-20s per decision)
3. Each subagent receiving its prompt, reasoning about it, potentially using tools, and returning output (~30-90s per subagent depending on complexity)
4. The orchestrating agent validating output and moving to the next agent

For 8-10 sequential agent dispatches at ~60-120s each, plus the orchestrator overhead (~30 turns as specified in Section 4b), the realistic range is **12-25 minutes**. The 15-minute timeout will fail intermittently -- particularly when the GitHub Actions runner is under load or when Claude Code experiences any latency spikes.

Additionally, there is zero cost modeling. Running this on every `push` to `main` (trunk-based development, so every commit) means every small documentation tweak, every CLAUDE.md update, every version bump triggers 8-10 LLM subagent calls against the Max subscription. With this project's commit frequency (5 commits visible in the recent log over a short period), this could mean 30-50+ subagent dispatches per day.

**Impact:** CI will timeout intermittently, creating false failures. Subscription compute will be consumed on trivial commits where smoke tests add zero value (e.g., docs-only changes).

**Fix:**
1. Increase `timeout-minutes` to 30 for the smoke job.
2. Add a cost model to the plan: estimate subagent dispatches/day at current commit frequency, and decide if that rate is acceptable.
3. Consider running smoke tests only on a schedule (daily or weekly) rather than every push -- or gate them with a path filter that skips when only `docs/`, `README.md`, or `CLAUDE.md` change. This is detailed in IMP-1 below.

---

#### P1-2: session-start.sh bats tests will be slow due to escape_for_json performance characteristics

**Location:** Step 3a (session_start.bats), hooks/lib.sh

**Problem:** The `escape_for_json` function in `hooks/lib.sh` (lines 6-24) performs bash parameter substitution for standard escapes (quotes, backslash, newlines, tabs) which is fast, but then iterates over control characters 1-31 (skipping 5 already handled) with a `for i in {1..31}` loop. For each of the remaining 26 control characters, it runs two `printf` calls and a parameter substitution over the entire string.

The `session-start.sh` hook calls `escape_for_json` on the entire content of `skills/using-clavain/SKILL.md` (currently 6,118 bytes). Each bats test case for `session_start.bats` (6 tests per Section 3a) invokes the hook from scratch, meaning the escape function runs 6 times during the bats suite.

Current cost: 6 invocations x 26 iterations x 6KB string = ~936 parameter substitutions. This is on the order of 1-3 seconds total on a GitHub Actions runner, which is noticeable but not critical. However, if `using-clavain/SKILL.md` grows (it is the routing table for 34 skills, 35 agents, and 24 commands -- growth is expected) or if more tests are added, this scales linearly.

The `session-start.sh` hook also calls `curl` to check Agent Mail (line 33), calls `find` for dispatch.sh (line 22), and checks for `.beads/` directory. In CI, the `curl` call will timeout after 1 second per invocation (connect-timeout 1), adding 1 second per test case if Agent Mail is unreachable (which it will be in CI -- there is no Agent Mail server on ubuntu-latest).

Total for session_start.bats: 6 tests x (~0.5s escape + ~1s curl timeout + ~0.2s other I/O) = approximately 10 seconds just for this one bats file.

**Impact:** The `session_start.bats` file alone may consume most of the ~5s Tier 2 budget. The overall Tier 2 estimate of ~5s is likely closer to 12-18 seconds when accounting for all 5 bats files plus the curl timeout in each session-start test.

**Fix:**
1. In `test_helper.bash`, stub out external commands (`curl`, `find`) that will always fail/timeout in CI. Bats supports function overriding -- define `curl() { return 1; }` in the helper so session-start tests skip the Agent Mail check instantly.
2. Alternatively, set `AGENT_MAIL_URL` to a non-routable address with `--connect-timeout 0` in the test environment to avoid the 1-second wait.
3. Update the Tier 2 time estimate from ~5s to ~15-20s to be realistic, or implement the stubs to keep it under 10s.

---

#### P2-1: Dependency installation overhead is unmanaged

**Location:** Step 5a (CI Workflow, `.github/workflows/test.yml`)

**Problem:** The `structural-and-shell` job installs dependencies on every run:
- `actions/setup-python@v5` + `pip install -r tests/requirements-dev.txt` -- Python setup ~5-10s, pip install ~5-10s
- `bats-core/bats-action@2.0.0` -- This action installs bats from source, typically ~5-10s

These run before any test executes. Combined with checkout (~2-5s), the overhead is 15-30 seconds before the first test starts. The actual test execution (pytest ~2s, bats ~15s with the issues noted above) is potentially less than the setup time.

This overhead does not scale with test count but does mean every push pays a fixed 30-45s tax. With trunk-based development producing frequent pushes, this adds up.

**Impact:** Low individually but compounds. The "~10s" estimate in the CI Workflow section header is unrealistic -- actual wall time for the `structural-and-shell` job will be 40-60 seconds including setup and teardown.

**Fix:** Add pip caching to the workflow:
```yaml
- uses: actions/setup-python@v5
  with:
    python-version: '3.12'
    cache: 'pip'
    cache-dependency-path: tests/requirements-dev.txt
```
This brings repeat-run pip install down to ~1-2s. For bats, the `bats-core/bats-action` handles its own setup; verify it caches or consider using `npm install -g bats` with Node.js caching instead. Update the time estimate in the plan from ~10s to ~30-45s (cold) / ~15-25s (warm with caching).

---

#### P2-2: Hardcoded counts increase CI trigger frequency indirectly

**Location:** Step 2a-2d (test_agent_count, test_skill_count, test_command_count), Design Decisions #1

**Problem:** The plan hardcodes exact counts (35 agents, 34 skills, 24 commands) as regression guards. This is intentional per Design Decision #1, but it means every time a component is added, someone must update the test as well. If they forget, CI fails on every subsequent push until fixed -- potentially causing multiple fix-commit cycles. This is not a runtime performance issue but a CI pipeline throughput concern: hardcoded counts will generate more CI runs (failed push -> fix -> push -> pass) compared to a range-based or minimum-count test.

Note: The counts in the plan already disagree with reality. The plan says 35 agents in `test_agent_count`, but the glob shows 35 agent files. The AGENTS.md says "29 agents" while the actual count is 35 (including the fd-v2-* agents added recently). The CLAUDE.md says "35 agents, 34 skills, 24 commands" but `test_commands.py` says 24 while there are also 24 actual command files. These mismatches will cause immediate test failures if implemented as specified without reconciling the numbers.

**Impact:** Low. Developers will learn to update counts, but the mismatch between plan and reality means the tests will fail on first run and need correction.

**Fix:** Reconcile the counts before implementation. Current actuals: 35 agents, 34 skills, 24 commands. Update `test_agent_count` from "35 agent .md files total (27 review + 5 research + 3 workflow)" to the correct breakdown: 27 review + 5 research + 3 workflow = 35, which matches the current count. The parenthetical breakdown should be updated to "27 review" (there are actually 27 files in review/ based on the glob results -- let me count: there are 21 original + 6 fd-v2-* = 27 in review/, 5 in research/, 3 in workflow/ = 35 total).

---

### Improvements Suggested

#### IMP-1: Run smoke tests on schedule, not every push

**Rationale:** Tier 3 smoke tests dispatch 8-10 LLM subagents, each consuming Max subscription compute. With trunk-based development producing multiple pushes per day, running these on every push is wasteful. A markdown-only change to CLAUDE.md does not need 8-10 agent dispatches to validate.

**Suggested approach:**
- Run smoke tests on a daily schedule (e.g., `cron: "0 6 * * *"`) and on manual `workflow_dispatch`
- Optionally trigger on push only when `hooks/`, `agents/`, `skills/`, or `.claude-plugin/` files change (using `paths` filter in the workflow trigger)
- Keep the `structural-and-shell` job on every push -- it is cheap and catches real regressions

This preserves safety while reducing compute consumption by 80-90%.

#### IMP-2: Cache CI dependencies

**Rationale:** The `actions/setup-python@v5` action supports a `cache` parameter. Adding `cache: 'pip'` with `cache-dependency-path: tests/requirements-dev.txt` avoids re-downloading pytest and pyyaml on every run. This brings cold-start overhead (~15s) down to warm-cache overhead (~3s) for repeat runs.

Similarly, if bats is installed via npm instead of the bats-action, `actions/setup-node@v4` with `cache: 'npm'` can cache the bats binary. This is a one-line change that saves 5-10s per run.

#### IMP-3: Bats test plan for auto-compound.sh is missing fixture details

**Rationale:** The `auto_compound.bats` tests in Section 3d reference concepts like "transcript contains 'git commit'" and "transcript contains 'insight' marker", but `auto-compound.sh` reads a `transcript_path` from JSON stdin and then runs `tail -40` on that file (line 36 of auto-compound.sh). The bats tests need a fixture transcript file on disk for these tests to work. The plan's `fixtures/` directory only mentions `minimal_tool_input.json`.

This is a correctness gap, but it has a performance implication: if the tests create large transcript fixtures at runtime (e.g., writing them in `setup()` per test), that I/O adds time. The plan should specify that a static fixture transcript file (a few KB of sample JSONL) goes in `tests/fixtures/` and is referenced by the bats tests.

---

### Overall Assessment

The plan is solid for Tier 1 and Tier 2 with minor time estimate corrections. The critical performance gap is in Tier 3: the absence of a cost model for running 8-10 LLM agent dispatches on every push, combined with a timeout that is likely too short. Running smoke tests on every push to main in a trunk-based workflow will consume significant subscription compute for minimal incremental safety over a daily schedule. The Tier 2 time estimate needs revision upward to account for the `curl` timeout in session-start.sh tests unless stubs are added.

<!-- flux-drive:complete -->
