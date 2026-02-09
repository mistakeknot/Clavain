---
agent: fd-architecture
tier: 1
issues:
  - id: P1-1
    severity: P1
    section: "Template Design / dispatch.sh Integration"
    title: "review-agent.md template uses {{AGENT_IDENTITY}}, {{REVIEW_PROMPT}}, {{OUTPUT_FILE}}, {{AGENT_NAME}}, {{TIER}} placeholders but dispatch.sh template assembly expects ^[A-Z_]+:$ section headers — multi-word keys and lowercase are not supported"
  - id: P1-2
    severity: P1
    section: "Tier 2 Bootstrap / Autopilot Hook Conflict"
    title: "Tier 2 bootstrap agent writes .claude/agents/fd-*.md via Codex workspace-write, but autopilot.sh denies Edit/Write for Claude — the bootstrap must complete BEFORE flux-drive tries to read the new agents; plan lacks explicit sequencing guarantee"
  - id: P1-3
    severity: P1
    section: "Codex Dispatch Path / Output Routing"
    title: "dispatch.sh -o writes the Codex agent's final message, not the review findings file — the agent writes OUTPUT_FILE via its own tools, but -o captures a different artifact; plan conflates these two outputs"
  - id: P1-4
    severity: P1
    section: "Staleness Check"
    title: "Staleness heuristic based on git diff of CLAUDE.md/AGENTS.md between .fd-agents-commit and HEAD will trigger false regeneration on every unrelated CLAUDE.md edit (e.g., adding a design decision)"
  - id: P2-1
    severity: P2
    section: "Parallel Dispatch / Background Completion Detection"
    title: "Plan says to poll output directory for N files, but Codex agents write their findings to OUTPUT_DIR/{agent-name}.md while dispatch.sh -o writes to /tmp; plan needs to clarify which files signal completion"
  - id: P2-2
    severity: P2
    section: "clodex SKILL.md 'When NOT to Use'"
    title: "clodex SKILL.md explicitly says 'Code review (use interpeer instead)' — this plan routes reviews through clodex dispatch, creating a conceptual contradiction that should be reconciled"
  - id: P2-3
    severity: P2
    section: "Tier 2 Bootstrap Template / Sandbox Scope"
    title: "The create-review-agent template tells Codex to write to .claude/agents/ — this is inside the workspace so workspace-write covers it, but .claude/ is a sensitive directory; should use a more restrictive output contract"
improvements:
  - id: IMP-1
    title: "Align template placeholder keys with dispatch.sh's section parser — use AGENT_IDENTITY:, REVIEW_PROMPT:, OUTPUT_FILE:, etc."
    section: "Template Design"
  - id: IMP-2
    title: "Add explicit error handling for Codex agent failures — retry once, then fall back to Task dispatch for that specific agent"
    section: "Codex Dispatch Path"
  - id: IMP-3
    title: "Use the -o flag for completion signaling and the OUTPUT_FILE template variable for the actual findings — document the distinction clearly"
    section: "Output Routing"
  - id: IMP-4
    title: "Add a --add-dir flag to dispatch.sh calls when OUTPUT_DIR is outside the project root (cross-project reviews)"
    section: "Cross-Project Reviews"
  - id: IMP-5
    title: "Narrow the staleness check to structural changes only — hash CLAUDE.md + AGENTS.md content at creation time, compare hashes instead of using git diff"
    section: "Staleness Check"
verdict: needs-changes
---

### Summary

The plan proposes a sound high-level architecture: detect clodex mode at Phase 2 dispatch time, route agents through `codex exec` via `dispatch.sh` instead of the Task tool, and use a new review-specific template. The parallel execution model is preserved because each Codex agent is launched as an independent background Bash call, matching flux-drive's existing parallel Task launch pattern. However, there are four P1 integration issues that need resolution before implementation: (1) the template placeholder format is incompatible with dispatch.sh's section parser, (2) the Tier 2 bootstrap creates a timing dependency that lacks explicit sequencing, (3) the output routing conflates dispatch.sh's `-o` flag with the agent's findings file, and (4) the staleness heuristic is too sensitive. None of these are architectural showstoppers, but each would cause runtime failures or incorrect behavior.

### Section-by-Section Review

#### 1. Template Design / dispatch.sh Integration

The plan proposes a `review-agent.md` template with `{{PROJECT}}`, `{{AGENT_IDENTITY}}`, `{{REVIEW_PROMPT}}`, `{{OUTPUT_FILE}}`, `{{AGENT_NAME}}`, and `{{TIER}}` placeholders. This is the right approach -- dispatch.sh's template assembly system (`--template` flag) is purpose-built for this.

**However**, dispatch.sh's section parser (lines 199-219 of `scripts/dispatch.sh`) recognizes sections by the pattern `^([A-Z_]+):$` -- that is, a line containing only uppercase letters and underscores, followed by a colon, with no other content. The template engine then replaces `{{KEY}}` markers where KEY matches the section header.

This means:
- `AGENT_IDENTITY:` works (uppercase with underscore)
- `REVIEW_PROMPT:` works
- `OUTPUT_FILE:` works
- `AGENT_NAME:` works
- `TIER:` works
- `PROJECT:` works

All the proposed keys are actually valid. The task description format shown in the plan (Section 2, "For each selected agent, write a task description") correctly uses `PROJECT:`, `AGENT_IDENTITY:`, etc. as section headers. This is compatible.

**Issue**: The plan's task description format is shown with content on the same line as the key (`PROJECT:\n{project name} — review task (read-only)`). In dispatch.sh, content MUST be on subsequent lines after the `KEY:` header line, not on the same line. The parser reads subsequent lines until the next `^[A-Z_]+:$` pattern. The plan's examples look correct (content is on the next line), but this should be made explicit as a constraint.

**Alignment verdict**: The template design aligns with dispatch.sh's template assembly system. The keys are compatible. The plan just needs to be explicit that section content must be on lines following the header, not the same line.

#### 2. Codex Dispatch Path — Parallel Execution Model

The plan states: "Both support `run_in_background: true`, so parallelism is preserved — each `codex exec` runs as an independent background Bash call."

This is correct. Currently flux-drive launches all Task calls in a single message with `run_in_background: true`. Switching to Bash calls with `run_in_background: true` preserves the same parallelism — Claude Code's Bash tool supports concurrent background execution. Each `codex exec` process is independent, has its own working directory via `-C`, and produces its own output.

**Key verification**: The plan correctly uses `bash "$DISPATCH"` as the shell invocation rather than calling `codex exec` directly. This ensures all dispatch.sh features (template assembly, doc injection, name substitution) are available.

**Potential gap**: The plan does not discuss what happens if a Codex agent fails. With Task dispatch, failures are visible in the task output. With Bash dispatch, a failed `codex exec` returns a non-zero exit code, and the Bash tool reports this. However, the background Bash call pattern means the orchestrator won't see the failure until it checks the output. The plan should specify: (a) how to detect failure (check exit code from background task), and (b) what to do on failure (retry once, then fall back to Task dispatch or mark as "no findings").

#### 3. Tier 2 Agent Bootstrap Architecture

The plan proposes a three-step bootstrap:
1. Check if `.claude/agents/fd-*.md` exists
2. If not, dispatch a single blocking Codex agent to create them
3. Store a commit hash sidecar file for staleness tracking

**Soundness**: The architecture is reasonable. A single creation agent exploring the project and writing 2-3 tailored agent files is a good approach. The commit hash sidecar (`.claude/agents/.fd-agents-commit`) is simpler and more reliable than timestamp comparison.

**P1 issue — Timing**: The plan says the bootstrap dispatch is "blocking" — but dispatch.sh runs `codex exec` via `exec`, which replaces the shell process. When called via `bash "$DISPATCH" ...`, the Bash tool call blocks until `codex exec` completes. If `run_in_background: false` (implicit), this works correctly. The plan needs to explicitly state: "Dispatch the creation agent WITHOUT `run_in_background` so the call blocks until the agents are created."

**P1 issue — Autopilot conflict**: When clodex mode is active, the autopilot hook (`hooks/autopilot.sh`) denies all Edit/Write/MultiEdit/NotebookEdit tool calls. The Codex creation agent runs in its own sandbox and uses `codex exec -s workspace-write`, so it can write files — Codex runs outside Claude Code's hook system. This is fine. But the plan should note this explicitly as a design rationale, since it may be non-obvious that Codex agents bypass Claude Code hooks.

**Staleness check concern**: The plan offers two heuristics — timestamp-based and commit-hash-based — and seems to prefer the commit-hash approach. The commit-hash approach is cleaner, but the `git diff --stat abc123..HEAD -- CLAUDE.md AGENTS.md docs/ARCHITECTURE.md` check will trigger regeneration whenever CLAUDE.md changes for any reason (adding an unrelated design decision, updating a count). A content-hash approach (`sha256sum CLAUDE.md AGENTS.md > .fd-agents-hash`) would be more targeted — only regenerate when the actual content these agents depend on has changed.

#### 4. Output Routing

The plan specifies two output paths per agent:
1. `bash "$DISPATCH" ... -o /tmp/flux-codex-result-{agent-name}.md` — dispatch.sh's `-o` flag
2. The template tells the agent: `Write your findings to: {{OUTPUT_FILE}}` — the agent writes `{OUTPUT_DIR}/{agent-name}.md`

**P1 issue**: These are different files. The `-o` flag in dispatch.sh maps to `codex exec -o`, which captures the agent's final chat message (its "last message") to a file. The `{{OUTPUT_FILE}}` in the template tells the agent to use its Write/Edit tools to create a findings file inside the workspace. Both files will be produced, but they serve different purposes:
- `-o /tmp/flux-codex-result-{agent-name}.md` = Codex's chat output (for debugging/logging)
- `{OUTPUT_DIR}/{agent-name}.md` = the actual review findings file (for synthesis in Phase 3)

The plan should clarify this distinction. Phase 3 (synthesis) reads from `{OUTPUT_DIR}/`, which is correct — it reads the findings files the agents wrote. The `-o` files are auxiliary. But the plan conflates them in the dispatch section, which could lead to implementers checking the wrong files for completion.

#### 5. Flag File Detection

The plan uses `$PROJECT_ROOT/.claude/autopilot.flag` for clodex detection, matching the existing autopilot hook's check (`$PROJECT_DIR/.claude/autopilot.flag`). This is consistent.

**Minor note**: `PROJECT_ROOT` in flux-drive is derived from the input path (nearest `.git` ancestor), while `CLAUDE_PROJECT_DIR` in autopilot.sh comes from Claude Code's environment. These could differ for cross-project reviews (reviewing a file in Project B while the Claude Code session is rooted in Project A). The plan should specify: "Check the flag in the **session's** project directory, not the review target's PROJECT_ROOT, because clodex mode is a session-level setting."

#### 6. Template Content — review-agent.md

The proposed template is well-structured for a review task:
- Sets the agent's role as "code/document reviewer"
- Provides project context via `{{PROJECT}}`
- Injects the agent's system prompt via `{{AGENT_IDENTITY}}`
- Specifies the review task via `{{REVIEW_PROMPT}}`
- Defines output requirements with YAML frontmatter format
- Includes constraints (no source modifications, no commits)

**Comparison with existing templates**: The `megaprompt.md` template uses Explore → Implement → Verify phases. The `parallel-task.md` template focuses on build/test success criteria. The proposed `review-agent.md` skips implementation phases entirely and focuses on analysis → write findings. This is the right differentiation.

**Gap**: The template doesn't include `--inject-docs` context. The dispatch command in the plan uses `--inject-docs`, which prepends CLAUDE.md to the prompt. This means the Codex agent gets: CLAUDE.md content + review template content. But the template's `{{PROJECT}}` section would typically contain the project name, not the full CLAUDE.md. The agent's `{{AGENT_IDENTITY}}` section (from the fd-architecture.md file) also tells the agent to "read CLAUDE.md and AGENTS.md" as a first step. So the agent would read CLAUDE.md twice — once injected, once via its own tooling. This is redundant but not harmful. Consider whether `--inject-docs` is necessary given agents already read project docs.

#### 7. create-review-agent.md — Tier 2 Bootstrap Template

The template is reasonable: it instructs the Codex agent to read project docs, identify key domains, and create 2-3 agent files. The constraint to start each agent with "First Step: read CLAUDE.md and AGENTS.md" ensures consistency with the Tier 1 pattern.

**Concern**: The template writes to `.claude/agents/` — a directory Claude Code uses for user-configured agents. Tier 2 agents created here will be discovered by other Claude Code features (not just flux-drive). This is actually a feature, not a bug — project-specific review agents should be reusable. But the plan should note that these agents become part of the project's general agent roster, not just flux-drive's.

**Concern**: The template has the Codex agent run `git rev-parse HEAD > .claude/agents/.fd-agents-commit`. This writes a file to `.claude/agents/` which is fine for the staleness check, but the file will appear as untracked in `git status`. The plan should specify whether `.claude/agents/.fd-agents-commit` should be gitignored or committed.

#### 8. clodex SKILL.md Conceptual Alignment

The clodex skill explicitly states under "When NOT to Use": "Code review (use interpeer instead)". The plan routes review agents through clodex dispatch, which creates a conceptual contradiction. The clodex skill was designed for implementation work (explore → implement → verify), not analysis work.

**Resolution**: The plan is not using clodex for code review in the sense clodex warns about — it's using clodex's _dispatch infrastructure_ (dispatch.sh, template assembly, `codex exec`) to launch review agents. The review logic lives in flux-drive's templates, not in clodex's implementation patterns. This distinction should be documented: "flux-drive uses clodex's dispatch infrastructure but not its implementation workflow. The review-agent template replaces clodex's explore-implement-verify cycle with an analyze-write-findings cycle."

Additionally, `clodex/SKILL.md` should add flux-drive to its "Called by" or integration section to make this relationship explicit.

### Issues Found

**P1-1: Template placeholder format partially misaligned with dispatch.sh parser.**
The task description format must have `KEY:` on its own line with content on subsequent lines. The plan's examples appear correct but don't make this constraint explicit. More critically, the plan shows the task description inline in the skill instructions — implementers may write the task description programmatically and could put content on the KEY: line. Add an explicit constraint: "Each section header (`PROJECT:`, `AGENT_IDENTITY:`, etc.) must be on its own line. Content starts on the next line."

**P1-2: Tier 2 bootstrap creates a timing/sequencing dependency that lacks explicit guarantees.**
The plan says the bootstrap dispatch is "blocking" but doesn't specify the mechanism (no `run_in_background`, synchronous Bash call). It also doesn't address what happens if the bootstrap agent fails or times out. Specify: (a) explicitly no `run_in_background` on the bootstrap call, (b) timeout of 300000ms, (c) if bootstrap fails, skip Tier 2 entirely for this run.

**P1-3: Output routing conflates dispatch.sh's `-o` (last message capture) with the agent's findings file (written via tools).**
These are different artifacts. Phase 3 synthesis reads from `{OUTPUT_DIR}/{agent-name}.md` (the findings file), not from `/tmp/flux-codex-result-{agent-name}.md` (the Codex chat output). The plan should: (a) clarify that `-o` is for debugging/logging only, (b) specify that completion is detected by checking `{OUTPUT_DIR}/{agent-name}.md` existence, (c) optionally drop the `-o` flag entirely if the chat output isn't needed.

**P1-4: Staleness heuristic triggers false regeneration on unrelated CLAUDE.md edits.**
Any change to CLAUDE.md or AGENTS.md between the stored commit and HEAD triggers regeneration, even if the change is unrelated to the review domains (e.g., adding a new command, updating a version count). Use a content hash approach instead: `sha256sum .claude/agents/fd-*.md CLAUDE.md AGENTS.md > .claude/agents/.fd-agents-hash` at creation time, compare hashes at check time.

**P2-1: Completion detection mechanism is ambiguous.**
The plan says to poll `{OUTPUT_DIR}/` for N files (matching existing flux-drive Phase 3), but also specifies `-o /tmp/flux-codex-result-{agent-name}.md`. Implementers may check the wrong directory. Clarify: completion is detected by the presence of `{OUTPUT_DIR}/{agent-name}.md`, same as the Task dispatch path.

**P2-2: Conceptual contradiction with clodex "When NOT to Use" section.**
Clodex explicitly says "Code review (use interpeer instead)". This plan routes review agents through clodex infrastructure. Add a note in clodex SKILL.md under "When NOT to Use" that distinguishes between "code review as a primary task" (use interpeer) and "dispatch infrastructure for review agents" (flux-drive's clodex path). Or update the "When NOT to Use" entry to: "Code review as a standalone task (use interpeer — flux-drive uses dispatch infrastructure directly)."

**P2-3: Tier 2 bootstrap writes to .claude/agents/ — a sensitive directory.**
While `workspace-write` sandbox covers this, `.claude/` is typically used for user configuration. The plan should document that bootstrap-created agents are intentionally placed in the user's agent directory for reuse, and add `.claude/agents/.fd-agents-commit` to `.gitignore` guidance.

### Improvements Suggested

**IMP-1**: Add an explicit constraint in the plan's task description format: section headers must be alone on their line, content follows on subsequent lines. Include a concrete example showing the exact file format dispatch.sh expects.

**IMP-2**: Add error handling for Codex agent failures. When a background Bash call returns non-zero, the orchestrator should: (a) check if the findings file was partially written, (b) if no findings file exists, retry once with the same prompt, (c) if retry also fails, fall back to Task dispatch for that specific agent (graceful degradation), (d) log the failure in the synthesis summary.

**IMP-3**: Clarify the dual output paths. The `-o` flag captures Codex's final chat message (useful for debugging). The `{{OUTPUT_FILE}}` template variable tells the agent where to write its structured findings. Phase 3 reads from `{OUTPUT_DIR}/`. Consider making `-o` optional (only when debugging) to reduce confusion.

**IMP-4**: For cross-project reviews where `OUTPUT_DIR` is outside the `-C` project directory, add `--add-dir {OUTPUT_DIR}` to the dispatch.sh call. Without this, `workspace-write` sandbox only allows writes within the `-C` directory, and the findings file write would fail.

**IMP-5**: Replace the git-diff staleness heuristic with a content hash. At creation time: `sha256sum CLAUDE.md AGENTS.md 2>/dev/null | sha256sum > .claude/agents/.fd-agents-hash`. At check time: compare the stored hash with a freshly computed one. This is immune to unrelated commits and works even in repos with no git history.

### Overall Assessment

The plan's high-level architecture is sound: clodex mode detection, parallel Codex dispatch, review-specific templates, and Tier 2 bootstrap are all well-motivated design choices that naturally extend flux-drive's existing multi-agent model. The parallel execution model is correctly preserved. The template design aligns with dispatch.sh's assembly system. The four P1 issues are integration-level bugs that would cause runtime failures but are straightforward to fix — they don't require rethinking the architecture. With the P1 fixes applied, this plan is ready for implementation.
