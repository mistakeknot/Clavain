---
agent: concurrency-reviewer
tier: adaptive
issues:
  - id: P0-1
    severity: P0
    section: "Phase 2 Step 2.3 / Phase 3 Step 3.0"
    title: "No completeness signal — synthesis can read partially-written agent output files"
  - id: P0-2
    severity: P0
    section: "Phase 2 Step 2.3"
    title: "Race between retry and stub creation — no state machine guards agent lifecycle"
  - id: P1-1
    severity: P1
    section: "Phase 2 Step 2.2 / Phase 2 Step 2.3"
    title: "Oracle completion is invisible to the polling loop — Bash background and Task background use different signaling"
  - id: P1-2
    severity: P1
    section: "Phase 2 Step 2.3"
    title: "Foreground retry has no timeout — a single hung agent blocks the entire pipeline indefinitely"
  - id: P1-3
    severity: P1
    section: "Phase 2 (Codex dispatch) / dispatch.sh"
    title: "Parallel Codex processes contend for Anthropic API rate limits with no backpressure"
  - id: P1-4
    severity: P1
    section: "Phase 2 Step 2.2"
    title: "Agent name collision — no uniqueness enforcement on output file paths"
  - id: P2-1
    severity: P2
    section: "Phase 3 Step 3.1"
    title: "Synthesis reads files without flock or content-length check — vulnerable to torn reads on slow NFS or FUSE mounts"
  - id: P2-2
    severity: P2
    section: "Phase 2 (Codex dispatch)"
    title: "Temp directory cleanup races with late-finishing Codex agents that still reference prompt files"
improvements:
  - id: IMP-1
    title: "Introduce atomic write-then-rename for all agent output files"
    section: "Phase 2 Step 2.2"
  - id: IMP-2
    title: "Add an explicit agent state machine: PENDING -> RUNNING -> DONE | RETRYING -> DONE | FAILED"
    section: "Phase 2 Step 2.3"
  - id: IMP-3
    title: "Add a timeout to foreground retry (5 minute cap with context cancellation)"
    section: "Phase 2 Step 2.3"
  - id: IMP-4
    title: "Stagger Codex dispatch with 2-3 second intervals to avoid API rate limit thundering herd"
    section: "Phase 2 (Codex dispatch)"
  - id: IMP-5
    title: "Use a sentinel marker at end-of-file as a completeness signal"
    section: "Phase 2 Step 2.2"
verdict: needs-changes
---

### Summary (3-5 lines)

Flux-drive's parallel dispatch architecture has a fundamental coordination gap: it launches up to 8 agents via two distinct mechanisms (Task tool background mode and Bash background mode) but relies on file existence as the sole completion signal. File existence does not imply file completeness. The retry path has no timeout and no guard against racing with stub creation. Oracle's Bash-based lifecycle is invisible to the Task-based polling logic, creating a window where synthesis begins while Oracle is still writing. These are not theoretical concerns — they are the kind of bugs that work perfectly in demos with 3 agents and blow up under production load with 8 agents, API latency spikes, and a Codex process that decides to take its time.

### Issues Found

**P0-1: No completeness signal — synthesis can read partially-written agent output files**

Severity: P0 | Section: Phase 2 Step 2.3 / Phase 3 Step 3.0

The entire coordination model rests on a single predicate: "does `{OUTPUT_DIR}/{agent-name}.md` exist?" (launch.md Step 2.3: "check via TaskOutput or output file existence"). But file existence is not file completeness. Here is what happens:

1. Agent begins writing its findings file via the Write tool.
2. The Write tool creates the file and begins flushing content.
3. The orchestrator polls the directory, sees the file exists, and proceeds to Phase 3.
4. Phase 3 Step 3.1 reads the file. It finds YAML frontmatter that cuts off mid-line: `verdict: nee` — because the agent was still writing when the orchestrator read.
5. Synthesis either crashes on malformed YAML or, worse, silently classifies the agent as "malformed" and falls back to prose-based reading of a half-written file.

This is a classic check-then-act (TOCTOU) race. The file's existence is the check; reading its content is the act. Between those two operations, the file's content can change.

The mitigation is straightforward: agents should write to a temporary file (e.g., `{agent-name}.tmp.md`) and atomically rename to the final path on completion. The orchestrator polls for the final filename. A file that exists at the final path is, by construction, complete. Alternatively, agents can append a sentinel line (e.g., `<!-- flux-drive-complete -->`) and the orchestrator checks for its presence before reading.

The current spec says "check via TaskOutput or output file existence" — TaskOutput is safer because it implies the Task has finished, but the "or" allows the file-existence path, and that path is where the race lives.

**P0-2: Race between retry and stub creation — no state machine guards agent lifecycle**

Severity: P0 | Section: Phase 2 Step 2.3

Step 2.3 describes a three-stage sequence for a failed agent:
1. Detect missing file after 5 minutes.
2. Retry once in foreground (`run_in_background: false`).
3. If retry fails, create a stub file with `verdict: error`.

But there is no state machine protecting this sequence. Consider:

- The orchestrator checks for missing files. Agent X's file is absent. The orchestrator launches a foreground retry.
- While the retry is running, the *original* background Task finally completes (it was slow, not dead) and writes `{agent-name}.md`.
- The foreground retry also completes and overwrites `{agent-name}.md` with its own output.
- Or: the foreground retry fails, and the orchestrator writes a `verdict: error` stub — overwriting the original agent's valid output that arrived 2 seconds ago.

The spec has no guard against this. There is no "mark agent as retrying" state. There is no check-before-overwrite. The original background task is never cancelled before the retry launches. You now have two concurrent writers targeting the same file with no coordination.

The fix: introduce an explicit per-agent state machine (`PENDING -> RUNNING -> DONE | RETRYING -> DONE | FAILED`). Before retrying, check if the file appeared in the interim. Before writing a stub, check again. Better yet: cancel the original background task before retrying — if the Task tool supports cancellation. If it does not, at minimum check for the file immediately before each write.

**P1-1: Oracle completion is invisible to the polling loop**

Severity: P1 | Section: Phase 2 Step 2.2 / Phase 2 Step 2.3

Oracle runs via `Bash(run_in_background: true)` with output redirected to `{OUTPUT_DIR}/oracle-council.md`. Task-dispatched agents run via the Task tool with `run_in_background: true`. These are two fundamentally different completion mechanisms:

- Task agents: completion is detectable via `TaskOutput` (the orchestrator is notified when the task finishes).
- Oracle: completion is detectable only by file existence or by checking the background Bash job's exit status.

Step 2.3 says "After all background tasks complete (check via TaskOutput or output file existence)." But the orchestrator receives no `TaskOutput` notification for Bash background jobs. If the orchestrator waits only for Task completions and then checks file existence, there is a window where all Task agents are done but Oracle's `timeout 480` Bash command is still running, still writing to `oracle-council.md`.

The spec's own error handling for Oracle (SKILL.md line 228) writes to the output file on failure, but the *happy path* is a progressive write via shell redirection (`> {OUTPUT_DIR}/oracle-council.md`). The shell redirects stdout as it arrives — meaning the file exists from the moment Oracle emits its first byte, but Oracle may still be running. Checking file existence here is actively misleading.

Mitigation: Oracle's Bash command should write to a temp file and rename on completion, or append a sentinel. The orchestrator should explicitly wait for the Bash background job to complete (or time out) before proceeding to synthesis.

**P1-2: Foreground retry has no timeout**

Severity: P1 | Section: Phase 2 Step 2.3

Step 2.3b says: "Re-launch the agent with the same prompt (use `run_in_background: false` so you get direct output)." A foreground task with no timeout is a task that can block forever.

If the original agent failed because of an API rate limit, the retry will likely hit the same rate limit. If it failed because the agent's prompt is malformed and causes an infinite loop, the retry will reproduce the same loop. The orchestrator is now blocked on a single agent's foreground retry while 7 other agents' results sit unprocessed.

The spec sets `timeout: 600000` (10 minutes) for Codex dispatch and `timeout: 600000` for Oracle, but the Task-dispatch retry path specifies no timeout at all. This is the kind of asymmetry that is invisible in testing (retries succeed fast) and catastrophic in production (retry hangs for 10 minutes, user stares at a frozen terminal).

Fix: set an explicit timeout on the retry Task call. Five minutes is generous. If it has not produced output by then, it will not.

**P1-3: Parallel Codex processes contend for API rate limits**

Severity: P1 | Section: Phase 2 (Codex dispatch) / dispatch.sh

In Codex dispatch mode, flux-drive launches up to 8 parallel `bash "$DISPATCH" ...` calls, each of which runs `codex exec` — a separate process that makes its own API calls. There is no rate-limit coordination between these processes.

The Anthropic API has per-organization rate limits. Eight simultaneous Codex processes, each making multiple API calls for their agent prompts, will spike request volume. If the rate limit is hit:
- Some Codex processes get 429 responses.
- `codex exec` may retry internally, but its retry strategy is opaque from flux-drive's perspective.
- Multiple processes retrying simultaneously create a thundering herd.
- Some agents fail while others succeed, producing inconsistent review quality.

dispatch.sh itself has no rate-limit awareness (it calls `exec "${CMD[@]}"` and exits). The coordination burden falls entirely on flux-drive, which provides none.

Mitigation: stagger launches with 2-3 second delays between dispatch calls, or use a semaphore to limit concurrent Codex processes to 3-4. This is especially important because the API key is shared across all processes.

**P1-4: Agent name collision on output file paths**

Severity: P1 | Section: Phase 2 Step 2.2

Output files are named `{OUTPUT_DIR}/{agent-name}.md`. The agent roster includes both plugin agents (e.g., `fd-code-quality`) and Project Agents from `.claude/agents/fd-*.md`. If a Project Agent happens to be named `fd-code-quality.md` — which is plausible, since the naming convention uses the same `fd-` prefix — both agents write to the same output file.

The spec does not enforce uniqueness of agent names across categories. Step 1.2's deduplication rule says "If a Project Agent covers the same domain as an Adaptive Reviewer, prefer the Project Agent" — but this is a triage-time heuristic, not a runtime guard. If deduplication fails to catch a collision (different domain assessment, same name), the second agent to write will overwrite the first agent's findings.

Mitigation: namespace output files by category (e.g., `{agent-name}-adaptive.md` vs `{agent-name}-project.md`), or enforce name uniqueness during triage with an explicit check.

**P2-1: Synthesis reads without ensuring write completion**

Severity: P2 | Section: Phase 3 Step 3.1

Phase 3 Step 3.1 reads each agent's output file and validates its YAML frontmatter. But there is no filesystem-level synchronization between the writing agent and the reading orchestrator. On local ext4, writes are typically atomic at the page level, but on network filesystems (NFS, FUSE-mounted cloud storage), partial reads are possible.

This is a lower-severity variant of P0-1. On local disk it is unlikely to manifest; on network mounts it will manifest intermittently and be extremely difficult to debug. Worth noting because Codex dispatch mode runs agents as separate OS processes, and process-level write buffering adds another layer of non-atomicity.

**P2-2: Temp directory cleanup races with late-finishing Codex agents**

Severity: P2 | Section: Phase 2 (Codex dispatch)

launch-codex.md's cleanup step says: "After Phase 3 synthesis completes, remove the temp directory: `rm -rf "$FLUX_TMPDIR"`." But FLUX_TMPDIR contains the prompt files that Codex agents read via `--prompt-file`. If a Codex agent is still running when cleanup fires (because it was slow, not because it failed), it loses access to its prompt file.

This scenario arises when:
1. Seven agents complete.
2. The eighth agent is still running but has already read its prompt file into memory (so the `rm` does not affect it) — OR has not yet read it (so the `rm` causes a failure).
3. Synthesis runs on the seven completed agents.
4. Cleanup fires.
5. The eighth agent tries to read its prompt file — gone.

The mitigation is simple: wait for all background Bash jobs to complete (or be confirmed failed) before cleaning up. The spec currently ties cleanup to "after Phase 3 synthesis completes," not "after all agents have terminated."

### Improvements Suggested

**IMP-1: Atomic write-then-rename for agent output**

Every agent — Task-dispatched, Codex-dispatched, and Oracle — should write to a temporary file (`{agent-name}.tmp.md`) and rename to the final path (`{agent-name}.md`) only after the write is complete. The orchestrator polls for the final filename. This single change eliminates P0-1, mitigates P1-1, and reduces P2-1 to a non-issue.

In the prompt template, add:
```
Write your findings to {OUTPUT_DIR}/{agent-name}.tmp.md first.
After writing is complete, rename it:
  mv {OUTPUT_DIR}/{agent-name}.tmp.md {OUTPUT_DIR}/{agent-name}.md
```

For Oracle, modify the Bash command:
```bash
timeout 480 env DISPLAY=:99 ... oracle --wait ... > {OUTPUT_DIR}/oracle-council.tmp.md 2>&1 \
  && mv {OUTPUT_DIR}/oracle-council.tmp.md {OUTPUT_DIR}/oracle-council.md \
  || { echo "Oracle failed (exit $?)" >> {OUTPUT_DIR}/oracle-council.tmp.md; \
       mv {OUTPUT_DIR}/oracle-council.tmp.md {OUTPUT_DIR}/oracle-council.md; }
```

**IMP-2: Explicit agent state machine**

Track each agent's lifecycle in the orchestrator's state:

```
PENDING   — selected in triage, not yet launched
RUNNING   — background task dispatched
DONE      — output file exists at final path (post-rename)
RETRYING  — original task timed out, foreground retry in progress
FAILED    — retry failed, stub written
```

Before retrying: verify state is RUNNING and file does not exist. Before writing stub: verify state is RETRYING and file still does not exist. This eliminates the retry-vs-late-completion race in P0-2.

Since flux-drive is a prompt-driven skill (not compiled code), this state machine would be maintained as a markdown table or mental model instruction in the orchestrator's context. Add to Step 2.3:

```
Maintain a status table for each agent:
| Agent | Status | Notes |
Before retrying, re-check if the output file appeared.
Before writing a stub, re-check if the output file appeared.
Never overwrite an existing output file with a stub.
```

**IMP-3: Timeout on foreground retry**

Add to Step 2.3b: "Re-launch with `run_in_background: false` and `timeout: 300000` (5 minutes). If the retry does not complete within 5 minutes, proceed to stub creation."

This caps the worst-case pipeline duration. Without it, a single misbehaving agent can block synthesis indefinitely.

**IMP-4: Stagger Codex dispatch**

In launch-codex.md, instead of launching all agents in a single parallel burst, stagger launches:

```
Launch agents in batches of 3, with 3-second delays between batches.
Batch 1: agents 1-3 (parallel Bash calls)
Wait 3 seconds.
Batch 2: agents 4-6 (parallel Bash calls)
Wait 3 seconds.
Batch 3: agents 7-8 (parallel Bash calls)
```

This reduces API rate-limit contention without significantly increasing total wall time (agents take minutes; a 6-second stagger is noise).

**IMP-5: End-of-file sentinel as completeness signal**

As a defense-in-depth complement to IMP-1, add a sentinel line to the prompt template:

```
The LAST line of your output file MUST be exactly:
<!-- flux-drive-complete -->
```

The orchestrator checks for this sentinel before reading. A file without the sentinel is either still being written or was truncated. This works even without atomic rename, as a belt-and-suspenders measure.

### Overall Assessment

Flux-drive's parallel dispatch is architecturally sound — the idea of launching background agents and collecting their output files is a reasonable coordination pattern. But the implementation skips the hard part: ensuring that "file exists" means "file is complete and nobody else is about to overwrite it." The two P0 issues (partial reads and retry races) will manifest under real-world conditions: API latency spikes, slow agents, and the orchestrator's eagerness to proceed. The fixes are not complex — atomic rename, a state table, and a retry timeout — but they are non-optional. Concurrent code that works when everything goes right is not concurrent code; it is sequential code wearing a disguise.
