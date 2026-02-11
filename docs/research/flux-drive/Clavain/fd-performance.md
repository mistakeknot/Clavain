### Findings Index
- P1 | P1-1 | "Test Suite" | Bats autopilot test creates symlinks for all system binaries, costing 6.8s out of 10s total
- P1 | P1-2 | "Flux-Drive Token Budget" | Full flux-drive orchestrator consumes ~14k tokens of context before any agent work begins
- P2 | P2-1 | "SessionStart Hook" | escape_for_json control-character loop runs 26 iterations for chars unlikely to appear in markdown
- P2 | P2-2 | "Auto-Compound Hook" | Five separate echo-pipe-grep subshells for signal detection could be a single grep pass
- IMP | IMP-1 | "Test Suite" | Bats test files run serially; parallel execution would cut wall time from 10s to ~3s
- IMP | IMP-2 | "Flux-Drive Phases" | Scoring examples in SKILL.md cost ~477 tokens per session but are reference material, not instructions
- IMP | IMP-3 | "Knowledge Retrieval" | qmd vsearch calls are serial per-agent; pipelining all 6 queries would save 200-1000ms
- IMP | IMP-4 | "Flux-Drive Agent Prompts" | Each agent independently reads CLAUDE.md and AGENTS.md; orchestrator could pre-read and inject once
Verdict: needs-changes

### Summary

The Clavain plugin has a disciplined performance profile for a markdown/bash plugin. Hook execution is fast (session-start.sh: 99ms, autopilot.sh: 4-12ms, auto-compound.sh: 12-23ms). The real performance costs are in token budget consumption during flux-drive workflows (~59k input tokens for a 6-agent review) and a specific test bottleneck that inflates CI time. The SessionStart injection of using-clavain content (~1,700 tokens every session) is well-sized and justified by the routing value it provides. The most impactful fix is the bats test suite, where one test case accounts for 67% of all shell test execution time.

### Issues Found

#### P1-1: Bats autopilot test creates symlinks for all system binaries (6.8s / 67% of shell test time)

**File:** `/root/projects/Clavain/tests/shell/autopilot.bats`, lines 33-55

The test "autopilot: deny with flag, jq unavailable (fallback branch)" creates a temporary directory and symlinks every binary in `/usr/bin` and `/bin` except `jq` to simulate jq being unavailable. This takes 6.8 seconds (67% of the total 10.1s bats suite), while all other 26 tests combined take 3.3 seconds.

Measured breakdown:
- `autopilot.bats`: 6.8s (5 tests, dominated by this one)
- `lib.bats`: 0.85s (7 tests)
- `auto_compound.bats`: 0.74s (6 tests)
- `session_start.bats`: 0.70s (4 tests)
- `agent_mail_register.bats`: 0.51s (3 tests)
- `hooks_json.bats`: 0.43s (4 tests)
- `dotfiles_sync.bats`: ~0.1s (2 tests)

The current approach:
```bash
tmpbin=$(mktemp -d)
for cmd in /usr/bin/* /bin/*; do
    bn=$(basename "$cmd")
    if [ "$bn" != "jq" ]; then
        ln -sf "$cmd" "$tmpbin/$bn" 2>/dev/null || true
    fi
done
export PATH="$tmpbin"
```

**Fix:** Replace symlink creation with a simpler PATH manipulation. Create a minimal PATH with only the binaries the script actually needs (bash, cat, curl, stat, date, pgrep, command, grep, find) rather than symlinking everything minus jq. Alternatively, create a wrapper script that shadows `jq` with `exit 1` and prepend it to PATH:

```bash
tmpbin=$(mktemp -d)
cat > "$tmpbin/jq" << 'SH'
#!/bin/sh
exit 1
SH
chmod +x "$tmpbin/jq"
export PATH="$tmpbin:$PATH"
```

This would reduce the test from ~6s to <50ms.

**Who feels it:** Anyone running the test suite during development or CI. The total bats suite would drop from 10s to ~3.5s.

#### P1-2: Flux-drive orchestrator consumes ~14k tokens of context before any agent work begins

**Files:** `/root/projects/Clavain/skills/flux-drive/SKILL.md` (17,028 bytes / ~4,257 tokens), `/root/projects/Clavain/skills/flux-drive/phases/launch.md` (14,523 bytes / ~3,630 tokens), `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md` (12,991 bytes / ~3,247 tokens), `/root/projects/Clavain/skills/flux-drive/phases/shared-contracts.md` (4,222 bytes / ~1,055 tokens)

The orchestrator reads phases progressively, which is good design. But the cumulative context growth is:

| After reading | Cumulative tokens |
|---|---|
| SessionStart injection | ~1,700 |
| flux-drive SKILL.md | ~5,955 |
| launch.md + shared-contracts.md | ~10,641 |
| synthesize.md | ~13,889 |
| cross-ai.md (if Oracle) | ~14,301 |

This means by the time the orchestrator starts synthesizing agent results, ~14k tokens of instruction material are in context. Combined with agent output files being read (5-6 agent reports at ~2-4k tokens each), the orchestrator context reaches ~30k tokens before writing the synthesis.

The full flux-drive session (orchestrator + 6 agents) consumes approximately 59k input tokens, or ~29% of the 200k context window. This is not blocking but it constrains how large a document can be reviewed before running into context limits.

**Specific concern:** The prompt template in `launch.md` (lines 177-305) is 4,630 bytes (~1,157 tokens) and is a reference template. The orchestrator carries it in context but only uses it when constructing agent prompts. The three scoring examples in `SKILL.md` (lines 175-208, ~477 tokens) serve a similar reference-only role.

**Who feels it:** Users reviewing large documents (plans over ~50k tokens) or large diffs (1000+ lines with full content). The orchestrator context becomes a meaningful fraction of the available window.

**Recommendation:** This is inherent to the progressive-loading architecture and does not require immediate action. Monitor for context overflow on large reviews. Consider moving the prompt template to a standalone file that is only read during agent prompt construction, saving ~1k tokens of persistent context.

#### P2-1: escape_for_json control-character loop iterates 26 times for chars nearly impossible in markdown

**File:** `/root/projects/Clavain/hooks/lib.sh`, lines 15-22

The function first handles the common escapes (backslash, quote, \b, \f, \n, \r, \t) with fast parameter substitution, then loops through control characters 1-31 (skipping already-handled ones) to escape them as `\uXXXX`. This means 26 iterations with `printf -v` and parameter substitution per iteration.

Measured: the entire `escape_for_json` call on the 5,939-byte using-clavain SKILL.md takes ~42ms. The control-character loop likely accounts for ~30ms of that (the initial substitutions are near-instant).

The content being escaped is a SKILL.md markdown file. Control characters (0x01-0x07, 0x0B, 0x0E-0x1F) essentially never appear in well-formed markdown.

**Impact:** 30ms added to session startup. This is below any perceptible threshold (total session-start.sh is 99ms, and the hook runs async). Not worth fixing unless you find the loop contributing to a larger bottleneck.

**Confidence:** High that it's negligible. The measurement confirms total escape time is 42ms.

#### P2-2: Auto-compound hook uses five separate echo-pipe-grep subshells

**File:** `/root/projects/Clavain/hooks/auto-compound.sh`, lines 44-67

Five signal detection patterns each create a subshell pipeline:
```bash
if echo "$RECENT" | grep -q 'pattern'; then
```

This is 5 fork+exec pairs for echo and 5 for grep. Measured total is 12-23ms depending on transcript size, which is negligible.

A single `grep -E 'pattern1|pattern2|...'` would reduce this to 1 fork+exec pair, saving ~10ms. But 10ms on a Stop hook (runs once per assistant turn, not per keystroke) is imperceptible.

**Impact:** None practical. The 5-pattern approach is more readable than a single compound regex.

### Improvements Suggested

#### IMP-1: Run bats test files in parallel (estimated 10s to 3s)

**File:** `/root/projects/Clavain/tests/run-tests.sh`, line 30

The current invocation `bats "$PROJECT_ROOT/tests/shell/" --recursive` runs all 7 bats files serially. Since bats-core supports `--jobs` for parallel execution:

```bash
bats "$PROJECT_ROOT/tests/shell/" --recursive --jobs 4
```

With 4 jobs, the longest single file (autopilot.bats at 6.8s) becomes the bottleneck, but all other files run in parallel alongside it. Even without fixing P1-1, this would reduce wall time from 10.1s to approximately 7s. With P1-1 fixed, parallel execution would bring it to ~1s.

**Trade-off:** Parallel bats output can be harder to read on failure. Use `--report-formatter tap` for CI logs if needed.

#### IMP-2: Move scoring examples to a sub-file to reduce flux-drive SKILL.md by ~477 tokens

**File:** `/root/projects/Clavain/skills/flux-drive/SKILL.md`, lines 175-208

The three scoring examples (Go API, Python CLI, PRD) are valuable reference material but are read every time flux-drive is invoked. They cost ~477 tokens of context per run. Moving them to `skills/flux-drive/examples/scoring-examples.md` and referencing them with a one-line note ("See `examples/scoring-examples.md` for scoring reference") would save ~450 tokens per invocation.

**Trade-off:** The orchestrator would need an additional Read call if it encounters an ambiguous scoring decision. In practice, the examples serve as calibration and the orchestrator may not reference them at all during straightforward triage. The savings are modest (~3% of flux-drive SKILL.md).

#### IMP-3: Pipeline qmd knowledge queries instead of serial execution

**File:** `/root/projects/Clavain/skills/flux-drive/phases/launch.md`, Step 2.1a

The skill text says "Start qmd queries before agent dispatch" and "Pipelining: Start qmd queries before agent dispatch." But in practice, the orchestrator issues MCP tool calls serially (one vsearch per agent). With 6 agents, this is 6 serial network round-trips.

Each vsearch against 5 knowledge entries is fast (~50-200ms), so serial execution costs 300-1200ms. If the MCP tool interface supports parallel calls (Claude Code does support parallel tool calls in a single response), all 6 queries could execute in a single round-trip.

**Recommendation:** Update the launch.md instructions to explicitly state: "Issue all 6 qmd vsearch calls in a single tool-call batch (parallel). Do NOT issue them one at a time."

The current wording is ambiguous about whether "pipelining" means "start queries before other work" or "run queries in parallel." Making it explicit would let the orchestrator batch them.

**Trade-off:** None. This is a prompt clarification, not a code change.

#### IMP-4: Pre-read CLAUDE.md and AGENTS.md once in orchestrator and inject into agent prompts

**Files:** All 6 fd-* agent files in `/root/projects/Clavain/agents/review/`

Each fd-* agent's system prompt begins with "First Step (MANDATORY): Check for project documentation: 1. CLAUDE.md 2. AGENTS.md". This means each of the 6 agents independently reads the same 2 files at the start of their execution. For a project with AGENTS.md (like Clavain at 8.5KB), this is 6 redundant reads of the same content.

The orchestrator already reads project documentation in Phase 1, Step 1.0. It could include the relevant project documentation excerpts in each agent's prompt template (in the "Project Context" section), rather than having each agent discover and read it independently.

**Savings:** 12 Read tool calls eliminated (6 agents x 2 files). Each Read is an MCP tool round-trip, so this saves 12 x ~100ms = ~1.2s of wall time, plus it ensures all agents see identical project context.

**Trade-off:** Increases each agent's prompt size by ~2-3k tokens (CLAUDE.md + AGENTS.md content). Since agent prompts are already ~7.4k tokens, this is a ~35% increase. The prompt template in `launch.md` would need a new section for "Project Documentation" that includes pre-read content. The agent system prompts would need to be updated to say "Project documentation is provided in the prompt below" instead of "Read CLAUDE.md."

This is a design trade-off between prompt size and execution efficiency. For projects with large AGENTS.md files (10k+), the token cost may outweigh the Read savings.

### Overall Assessment

The Clavain plugin's runtime performance is well-optimized for its use case. Hook latency is negligible (all hooks under 100ms, most under 25ms). The SessionStart injection at ~1,700 tokens is compact and justified by the routing value it provides every session. The main actionable finding is the bats test bottleneck (P1-1), which is a straightforward fix that would cut test suite time by 60-70%. The flux-drive token budget (P1-2) is inherent to the multi-agent architecture and is within acceptable bounds at ~29% of context window, though it warrants monitoring for large-document reviews. All other findings are minor optimizations with modest impact.

<!-- flux-drive:complete -->
