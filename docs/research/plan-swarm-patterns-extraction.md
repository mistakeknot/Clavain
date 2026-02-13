# Swarm Parallelization Patterns Extraction Plan
**Date:** 2026-02-11  
**Status:** Research & Planning  
**Scope:** Extract parallel patterns from upstream compound-engineering and plan integration with Clavain /lfg workflow

---

## Executive Summary

Upstream compound-engineering's `orchestrating-swarms` skill defines a mature multi-agent coordination system with 6 core patterns (Parallel Specialists, Pipeline, Swarm, Research+Implementation, Plan Approval, Coordinated Refactoring). Clavain's `/lfg` workflow (9 sequential steps) and `/quality-gates` command already **successfully use parallel Task execution** without explicit "swarm mode." The research identifies:

1. **Upstream patterns available natively in Claude Code** (no custom implementation needed)
2. **Which /lfg steps can realistically parallelize** (5 out of 9)
3. **Simplest path to a "parallel mode" flag** (extend /lfg with conditional step routing)

---

## Part 1: Upstream Swarm Patterns & Architecture

### Source: `orchestrating-swarms/SKILL.md` (1718 lines)
**Location:** `/root/projects/upstreams/compound-engineering/plugins/compound-engineering/skills/orchestrating-swarms/SKILL.md`

#### Core Primitives
Upstream defines 7 persistent structures:
- **Agent** — Claude instance (you or spawned subagent)
- **Team** — Named group working together (~/.claude/teams/{name}/config.json)
- **Teammate** — Persistent agent in team (inbox + task list access)
- **Leader** — Team creator (approves plans, shutdown, receives messages)
- **Task** — Work item with subject, description, status, owner, dependencies
- **Inbox** — JSON messaging channel per teammate
- **Message** — Structured JSON (shutdown_request, task_completed, idle_notification, etc.)

#### Two Spawning Methods
1. **Subagent (Task only)** — Short-lived, returns result synchronously/async, no team membership needed
2. **Teammate (Task + team_name + name)** — Persistent, accesses shared Task list, communicates via inbox, stays until shutdown

#### 6 Core Orchestration Patterns (Lines 700-1000)

| Pattern | Use Case | Parallelization | Dependency Model |
|---------|----------|-----------------|------------------|
| **Parallel Specialists** | Multiple reviewers analyze same code simultaneously | Full parallelism (N agents) | Independent (no dependencies) |
| **Pipeline** | Research → Plan → Implement → Test → Review | Sequential (dependencies block downstream) | Strict sequential (each stage depends on prior) |
| **Swarm** | N workers grab tasks from pool, work independently | Full parallelism (self-load-balancing) | Independent task queue (workers race to claim) |
| **Research + Implementation** | Research phase (sync) feeds into implementation | Sync research, then async implementation | One-way (research result input to impl) |
| **Plan Approval** | Architect creates plan, leader approves, then implementation | Sequential (plan must be approved before work) | Strict sequential (approval gates implementation) |
| **Coordinated Multi-File Refactoring** | Multiple files refactored in parallel with file-level boundaries | Partial parallelism (coordinated boundaries) | Independent per file (but coordinated) |

**Key insight:** Upstream's "swarm" is an architecture pattern, not a command flag. It uses **Task + TaskCreate + TaskUpdate** (all native Claude Code features).

#### Native Claude Code Support
- ✅ Task tool (spawn subagents or teammates)
- ✅ TaskCreate / TaskUpdate / TaskList (dependency tracking)
- ✅ Teammate tool operations (message inbox, shutdown, plan approval)
- ✅ Message routing (JSON inbox files)
- ✅ Spawning backends: in-process (default), tmux (persistent), iterm2 (macOS)

**No custom implementation needed** — all primitives exist in Claude Code natively.

---

## Part 2: Clavain's Current Parallelization

### Current /lfg Command
**Location:** `/root/projects/Clavain/commands/lfg.md`

9 sequential steps:
1. **Brainstorm** — `/clavain:brainstorm`
2. **Strategize** — `/clavain:strategy`
3. **Write Plan** — `/clavain:write-plan`
4. **Review Plan** — `/clavain:flux-drive` (gates execution)
5. **Execute** — `/clavain:work`
6. **Test & Verify** — (manual test command)
7. **Quality Gates** — `/clavain:quality-gates`
8. **Resolve Issues** — `/clavain:resolve`
9. **Ship** — `clavain:landing-a-change`

### Current Parallelization in /quality-gates
**Location:** `/root/projects/Clavain/commands/quality-gates.md`

Already uses **Parallel Specialists pattern**:
- **Phase 2:** Analyzes changed files by language and risk domain
- **Phase 4:** "Launch selected agents using the Task tool with `run_in_background: true`"
- **Agents:** fd-architecture, fd-quality, fd-safety (always), + risk-based agents (fd-correctness, fd-user-product, fd-performance)
- **Max parallel:** Up to 5 agents
- **Synchronization:** Implicit (waits for all background tasks to complete in Phase 5)

### Current Parallelization in /resolve
**Location:** `/root/projects/Clavain/commands/resolve.md`

Uses **parallel processing** for independent findings:
- **Phase 3:** "Spawn a `pr-comment-resolver` agent for each independent item in parallel"
- **Sequential dependencies:** Respects task order if one fix requires another to land first
- **Implicit wait:** Waits for all parallel agents before Phase 4 (commit)

### Current Parallelization in /work
**Location:** `/root/projects/Clavain/commands/work.md`

**No parallelization currently** — executes tasks sequentially in Phase 2 (Task Execution Loop). Each task marked in_progress, completed, then next task starts.

---

## Part 3: Upstream /slfg Command vs. Clavain /lfg

### Upstream /slfg (Swarm-enabled LFG)
**Location:** `/root/projects/upstreams/compound-engineering/plugins/compound-engineering/commands/slfg.md`

Structure:
1. **Sequential Phase** (Steps 1-3): ralph-loop → plan → deepen-plan
2. **Parallel Phase (Step 4 - SWARM MODE)**:
   - `/workflows:work` — "Make a Task list and launch an army of agent swarm subagents"
   - Parallel swarm subagents execute work tasks independently
3. **Parallel Phase (Steps 5-6)**:
   - `/workflows:review` — background Task agent
   - `/compound-engineering:test-browser` — background Task agent
   - Both run in parallel (only need code to be written)
4. **Finalize Phase** (Steps 7-9): resolve_todo_parallel → feature-video → DONE promise

**Key difference from Clavain /lfg:** Upstream explicitly uses **swarm mode** for Step 4 (work execution) and steps 5-6 (parallel review+test). Clavain /lfg runs work sequentially.

---

## Part 4: Parallelizable /lfg Steps

### Analysis: Which Steps Can Parallelize?

| Step | Sequential Reason | Can Parallelize? | How |
|------|------------------|------------------|-----|
| 1. Brainstorm | Input-dependent (user's feature description) | ❌ No | Depends on user input |
| 2. Strategize | Depends on brainstorm output (PRD, beads) | ❌ No | Gates on brainstorm completion |
| 3. Write Plan | Depends on strategy (PRD exists) | ❌ No | Gates on strategy completion |
| 4. Review Plan (flux-drive) | Dependency check — gates execution | ⚠️ Maybe | Could run review in background, but blocks step 5 anyway |
| 5. Execute (/work) | Depends on plan (step 3 artifact) | ⚠️ Limited | Could parallelize **within** work (multiple subplans), not adjacent steps |
| 6. Test & Verify | Depends on execute output (code exists) | ❌ No | Can't test code that doesn't exist |
| 7. Quality Gates | Depends on execute output (diff exists) | ❌ No | Must review what was actually built |
| 8. Resolve Issues | Depends on quality gates findings | ❌ No | Must resolve issues found in step 7 |
| 9. Ship | Depends on all prior steps | ❌ No | Final step (no parallelization possible) |

**Realistic Parallelization Opportunities:**

1. **Within Step 5 (Execute):** If plan has independent modules/components, spawn multiple agents to implement them in parallel
   - Requires: Plan to be structured with clear module boundaries
   - Upstream /slfg does this explicitly ("Make a Task list and launch an army")
   
2. **Steps 5 + 6 (in theory):** Execute code + Run tests in parallel
   - **Reality:** Tests run on code produced by step 5, so true parallel breaks down
   - **Better approach:** Run tests incrementally during execute, not as separate step
   - Upstream /slfg sidesteps this by having separate test-browser command
   
3. **Steps 7 + 8 (in theory):** Quality gates + Resolve in parallel
   - **Reality:** Resolve depends on quality gates findings, so sequential
   - Could parallelize within resolve (multiple fixes), which it already does

**Verdict:** Only **Step 5 (Execute work plan)** has significant parallelization opportunity, and **only if the plan is structured with independent components.**

---

## Part 5: Simplest Implementation Path — "Parallel Mode" Flag

### Current Architecture
- `/lfg` is a **command** (shell, not a skill, no agent autonomy)
- It returns step-by-step instructions to the user
- User manually runs each command (though description suggests auto-execution)

### Three Approaches to Add Parallel Mode

#### Approach A: Conditional Step Routing (SIMPLEST)
**Effort:** ~10 lines of text  
**Where:** lfg.md, new section at top

```markdown
## Modes

**Default mode (Sequential):** Run steps 1-9 in order
**Parallel mode:** `--parallel` flag

Run with: `/clavain:lfg [feature description] --parallel`

## Step 1: Brainstorm
...
[if parallel mode]
**NOTE:** In parallel mode, after writing plan (step 3), 
execute (/clavain:work) will spawn multiple agents to 
implement independent plan modules simultaneously.
**[Steps 4-9 unchanged]
```

**Pros:**
- Zero code changes
- Documents intent clearly
- Work.md already has subagent spawning capability
- Leverages existing capabilities

**Cons:**
- Relies on work.md understanding what "parallel means" (not implemented)
- Minimal tangible difference in workflow

#### Approach B: Create /slfg (Swarm LFG) Command
**Effort:** ~50 lines (adapted from upstream)  
**Where:** Create commands/slfg.md

```markdown
---
name: slfg
description: Full autonomous engineering workflow using swarm mode for parallel execution
argument-hint: "[feature description]"
---

Swarm-enabled LFG...

## Sequential Phase
1. /clavain:brainstorm $ARGUMENTS
2. /clavain:strategy
3. /clavain:write-plan
4. /clavain:flux-drive <plan-file>

## Parallel Execution Phase
5. /clavain:work-swarm <plan-file> — spawn multiple agents to parallelize independent modules
6. /clavain:quality-gates (runs in parallel with step 5 once code exists)

## Finalize Phase
7. /clavain:resolve
8. /clavain:landing-a-change
```

**Pros:**
- Explicitly separate from sequential /lfg
- Clear intent (swarm = parallel)
- Matches upstream naming convention
- No confusion about what parallel means

**Cons:**
- Requires creating work-swarm command
- More work to implement fully

#### Approach C: Extend /lfg with Run Mode Parameter
**Effort:** ~20 lines  
**Where:** lfg.md, add parameter handling

```markdown
---
name: lfg
description: Full autonomous engineering workflow — brainstorm, strategize, plan, execute, review, ship
argument-hint: "[feature description] [--parallel]"
---

Run these steps in order. Pass `--parallel` to use swarm execution for the work phase.

If $ARGUMENTS contains `--parallel`:
  - Step 5 will dispatch multiple agents to parallelize plan modules
  - Steps 6-7 can run partially in parallel with step 5 (once code starts appearing)
Otherwise:
  - Default sequential behavior

## Step 1: Brainstorm
...
```

**Pros:**
- Uses the same command (/lfg)
- Extensible to future modes
- Minimal documentation burden

**Cons:**
- Requires parsing $ARGUMENTS in skill to set a flag
- Still relies on work.md implementing parallel execution

### **Recommendation: Approach A (Simplest) + Future Enhancement to Approach C**

**Immediate (1-2 lines):**
1. Add a note at top of `/lfg` documenting that parallel execution is possible if plan has independent modules
2. Reference the `/clavain:dispatching-parallel-agents` skill for how parallel agents work

**Future (when work.md is enhanced):**
1. Implement `--parallel` flag parsing in a skill wrapper
2. Pass flag to work.md (not yet implemented, but documented intent)
3. Rename or alias to `/slfg` if adoption is high

---

## Part 6: What's Already Available in /work Command

### Current /work Capabilities (commands/work.md)

**Phase 2: Execute loop — Sequential by default**
```
for each task in priority order:
  - Mark task as in_progress
  - Implement
  - Mark task as completed
  - Commit incrementally
```

**Not currently parallelized.**

### Parallelization Opportunity: /work Internal Enhancement
**Where:** commands/work.md, Phase 2 (Task Execution Loop)

**Current flow:**
```
task1 (sequential) → task2 (sequential) → task3 (sequential)
```

**Parallel flow (Upstream /slfg pattern):**
```
Read plan → Identify independent components
  ↓
Launch Task for component1 (background)
Launch Task for component2 (background)
Launch Task for component3 (background)
  ↓
Wait for all to complete
```

**Implementation sketch:**
```markdown
## Phase 2b: Parallel Execution (if enabled)

If plan clearly identifies independent components (modules, microservices, features):

1. Parse plan and identify boundaries between independent components
2. For each component, spawn a general-purpose agent:
   ```
   Task({
     subagent_type: "general-purpose",
     description: "Implement component X",
     prompt: "Implement this component from the plan: [component spec]",
     run_in_background: true
   })
   ```
3. Wait for all agents to complete
4. Merge changes and verify no conflicts
5. Commit merged work
```

**This matches Upstream Pattern #1: Parallel Specialists (each agent owns one component)**

---

## Part 7: Integration Points

### Skills That Support Parallelization

1. **dispatching-parallel-agents** (already exists!)
   - **Location:** `/root/projects/Clavain/skills/dispatching-parallel-agents/SKILL.md`
   - **Patterns:** Independent domain dispatch, focused agent prompts, integration strategy
   - **Applicability:** Document this as the reference for how /lfg --parallel works

2. **orchestrating-swarms** (upstream)
   - **Location:** `/root/projects/upstreams/compound-engineering/.../orchestrating-swarms/SKILL.md`
   - **Patterns:** 6 patterns (we use Parallel Specialists)
   - **Applicability:** Document as reference for team-based coordination (not needed for simple parallel agents)

### Commands That Support Parallelization

1. **quality-gates** — Already uses parallel agents (Phase 4)
2. **resolve** — Already uses parallel agents (Phase 3)
3. **work** — Could use parallel agents (not yet implemented, but documented intent)

### Skills to Reference in /lfg Documentation

```markdown
## Parallel Execution

For detailed patterns on dispatching multiple agents in parallel, see:
- `/clavain:dispatching-parallel-agents` — When facing 2+ independent tasks
- Upstream `/compound-engineering:orchestrating-swarms` — Full multi-agent coordination (teams, dependencies, messaging)

When /lfg runs in parallel mode, it uses the "Parallel Specialists" pattern:
1. Identify independent components/modules in plan
2. Spawn one agent per component
3. Wait for all to complete
4. Merge and verify
```

---

## Part 8: Key Gotchas & Constraints

### Gotcha 1: Plans Must Be Structured for Parallelization
Upstream /slfg explicitly notes: `Make a Task list and launch an army of agent swarm subagents`

This requires:
- Plan with clear module/component boundaries
- Independent implementation paths
- No cross-module dependencies or shared resources

If plan is "build feature A," agents work fast. If plan is "refactor auth system + add OAuth," agents might interfere.

### Gotcha 2: /work Already Commits Incrementally
Current /work.md does incremental commits after each task:
```
Task1 → Commit1 → Task2 → Commit2 → Task3 → Commit3
```

In parallel mode, we need:
```
Task1 (background) → Merge → Single Commit
Task2 (background) ↗
Task3 (background) ↗
```

Or accept multiple commits from parallel agents (race conditions on `git add .`).

**Solution:** In parallel mode, do NOT commit during execution. Wait for all agents to complete, then merge and single commit.

### Gotcha 3: "Swarm" Means Self-Organizing Task Queue
Upstream's "swarm" pattern involves:
- Shared task list (TaskCreate/TaskList)
- Workers poll and claim tasks dynamically
- Load balancing happens naturally

Clavain's current approach is:
- Dispatch N agents upfront (Leader decides split)
- Each agent owns one component (Specialist pattern)

Different approaches, both valid. We're using **Parallel Specialists** (upstream pattern #1), not **Swarm** (upstream pattern #3).

### Gotcha 4: Tests Must Respect Parallel Execution
Current /lfg step 6: `Test & Verify` runs **after** execute.

In parallel mode, if agents commit independently, we might test partial code. Solution:
- Run tests only **after all agents complete**
- Or run tests per-agent (component-level tests)
- Or run integration tests once after merge

---

## Part 9: Simplest Immediate Action

### Add Note to /lfg (1-2 minutes, 5 lines)

**File:** `/root/projects/Clavain/commands/lfg.md`

**Add after step 5 (Execute):**

```markdown
### Parallel Execution (Advanced)

If your plan has independent components/modules, you can parallelize step 5:

- See `/clavain:dispatching-parallel-agents` for how to spawn multiple implementation agents
- Upstream `/compound-engineering:orchestrating-swarms` documents full swarm coordination patterns
- Multiple agents will race to implement components in parallel — merge and verify before proceeding to step 6

For a dedicated swarm-enabled workflow, consider creating a `/clavain:slfg` command (swarm LFG).
```

**Result:** Documents the capability, no code changes needed.

---

## Part 10: Planning the Feature

### What We Learned
1. ✅ Upstream swarm patterns exist and are production-ready in compound-engineering
2. ✅ Claude Code natively supports all primitives (Task, TaskCreate, TaskUpdate, Teammate, etc.)
3. ✅ Clavain already uses parallel agents in quality-gates and resolve
4. ✅ /work doesn't yet use parallel, but could with minor restructuring
5. ✅ Only step 5 of /lfg has real parallelization potential (within execute, not adjacent steps)

### Minimal Implementation (Approach A: Conditional Routing)
1. Add 5-line note to /lfg documenting parallel option
2. Reference dispatching-parallel-agents skill
3. Link to upstream orchestrating-swarms skill

**Effort:** 10 minutes  
**Benefit:** Clarifies what's possible, unblocks users who want to parallelize

### Medium Implementation (Approach C: --parallel Flag)
1. Add --parallel flag parsing to /lfg skill (not yet created — lfg.md is a command)
2. Extend /work to detect flag and spawn agents in parallel mode
3. Document in /lfg and /work

**Effort:** 1-2 hours  
**Benefit:** Integrated, discoverable feature

### Future Implementation (Approach B: /slfg Command)
1. Create /clavain:slfg command (explicit swarm workflow)
2. Implement work-swarm subcommand or skill
3. Add team-based coordination if needed (probably overkill for simple parallelization)

**Effort:** 2-3 hours  
**Benefit:** Matches upstream naming, explicit intent

---

## Recommendations

### For This Sprint
1. **Document the capability** — Add a "Parallel Execution" section to /lfg noting that step 5 can parallelize independent plan components
2. **Cross-reference skills** — Link to dispatching-parallel-agents and orchestrating-swarms
3. **No code changes needed** — All infrastructure already exists

### For Next Sprint (if High Demand)
1. **Create work-swarm skill** — Wraps /work and enables parallel module execution
2. **Implement --parallel flag** — Add to /lfg for automatic swarm detection
3. **Test with real plans** — Verify no conflicts, test framework, merge strategy

### For Future Consideration
1. **Upstream sync** — Decide if /clavain:slfg should mirror /compound-engineering:slfg
2. **Team-based workflows** — Consider adopting Upstream Pattern #3 (self-organizing swarms) for larger projects
3. **Conditional parallelization** — Auto-detect plan structure and offer --parallel suggestion to user

---

## Files Reviewed

- `/root/projects/upstreams/compound-engineering/plugins/compound-engineering/skills/orchestrating-swarms/SKILL.md` (1718 lines, read ~600)
- `/root/projects/upstreams/compound-engineering/plugins/compound-engineering/commands/slfg.md` (swarm-enabled workflow)
- `/root/projects/Clavain/commands/lfg.md` (sequential workflow, 9 steps)
- `/root/projects/Clavain/commands/quality-gates.md` (already uses parallel agents)
- `/root/projects/Clavain/commands/resolve.md` (already uses parallel agents)
- `/root/projects/Clavain/commands/work.md` (sequential execution, parallelization opportunity)
- `/root/projects/Clavain/skills/dispatching-parallel-agents/SKILL.md` (reference for parallel patterns)

---

## Appendix: Pattern Comparison Matrix

| Aspect | Upstream /slfg | Clavain /lfg | Clavain /quality-gates | Clavain /resolve |
|--------|----------------|-------------|----------------------|------------------|
| **Parallel execution** | ✅ Step 4 (work swarm) | ❌ Sequential | ✅ Phase 4 (agents) | ✅ Phase 3 (agents) |
| **Pattern used** | Swarm (self-org) | N/A | Parallel Specialists | Parallel Specialists |
| **Task coordination** | Shared task list | N/A | Implicit wait | Implicit wait |
| **Communication** | Inbox messages | N/A | Return values | Return values |
| **Agent type** | general-purpose | N/A | fd-* agents | pr-comment-resolver |
| **Max parallelism** | Unlimited | N/A | 5 agents | N tasks |
| **Dependency handling** | Complex (tasks block each other) | N/A | None (all independent) | Respects task order |

