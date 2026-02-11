# UX & Product Review: Clavain v0.4.29

**Reviewer:** Flux-Drive User & Product Reviewer (fd-user-product agent)
**Date:** 2026-02-11
**Plugin version:** 0.4.29
**Components reviewed:** 33 skills, 16 agents, 25 commands, 5 hooks, 2 MCP servers

---

## Primary User & Job-to-be-Done

**Primary user:** A solo developer or small-team lead who uses Claude Code daily as their primary coding interface. They have moderate familiarity with Claude Code's plugin system and want an opinionated engineering workflow that imposes discipline (plan before code, review before ship, document before forget) without requiring them to remember which tool to invoke for each situation.

**Job:** "Help me build, review, and ship software with engineering discipline while I focus on product decisions -- without me having to remember 33 skill names."

**Secondary users:**
- **New installer:** Someone who heard about Clavain and wants to try it. Needs to understand what they are getting and whether it fits their workflow.
- **Codex/multi-agent user:** Someone who wants to dispatch work to Codex CLI agents and have Claude orchestrate.

---

## Executive Summary

Clavain is an ambitious and deeply thought-out engineering discipline system. Its core value proposition -- an opinionated workflow pipeline from brainstorm to ship, with multi-agent review at every stage -- is genuinely powerful. The `/lfg` command alone is a compelling demo of what agent-orchestrated development can look like.

However, Clavain has a discoverability and cognitive load problem. With 33 skills, 25 commands, and 16 agents, a new user faces a wall of options that the 3-layer routing table partially but not fully addresses. Several components are vestigial redirects, naming is inconsistent across the skill/command boundary, and the relationship between overlapping commands (review vs quality-gates vs flux-drive) requires reading documentation to untangle.

The Stop hooks (auto-compound, session-handoff) are a polarizing design choice that adds genuine value but will annoy power users who want tight control over when their session pauses.

**Bottom line:** Clavain is an excellent power-user tool that could become a great general-purpose plugin with targeted simplification. The core pipeline is sound; the surface area needs pruning.

---

## 1. Discoverability

### 1.1 The Routing Table Works -- But Only After You Read It

The `using-clavain/SKILL.md` routing table is the plugin's primary navigation mechanism, injected into every session via the SessionStart hook. It uses a 3-layer model (Stage / Domain / Concern) that is conceptually clean. In practice:

**What works:**
- The "Which review command?" table is the single most useful piece of navigation in the plugin. It directly answers "I want to review something, which command do I use?"
- The routing heuristic (detect stage from request, detect domain from context) gives Claude Code a clear decision procedure.
- The "Skill Priority" section (process > domain > meta) prevents the agent from loading 5 skills simultaneously.

**What does not work:**

1. **The routing table uses 34 skills, but the actual skill count is 33.** The routing table header says "34 skills" while CLAUDE.md says 33. This inconsistency erodes trust in the documentation's accuracy.
   - File: `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 24 says "34 skills"
   - File: `/root/projects/Clavain/CLAUDE.md` line 12 says "33 skills"

2. **The routing table does not distinguish commands from skills.** The "Primary Commands" column lists slash commands (brainstorm, write-plan) alongside the "Primary Skills" column, but a user cannot tell at a glance whether they should type `/clavain:brainstorm` or invoke the `brainstorming` skill. The difference matters: commands have arguments and structured phases; skills are process guidance.

3. **The EXTREMELY-IMPORTANT block at the top is counterproductive.** Lines 6-12 of `using-clavain/SKILL.md` use an aggressive, all-caps directive:
   ```
   <EXTREMELY-IMPORTANT>
   If you think there is even a 1% chance a skill might apply...
   This is not negotiable. This is not optional.
   </EXTREMELY-IMPORTANT>
   ```
   This is aimed at the *agent*, not the user. The user sees this injected context and encounters a scolding tone that does not build confidence. It also encourages over-invocation of skills, which burns tokens and time. A well-designed routing heuristic should not need to shout.

4. **No "quick start" path.** A new user's first exposure to Clavain is the full routing table injected at session start. There is no progressive disclosure -- no "here are the 5 most common things you will use" before the full 33-skill taxonomy. The README addresses this by describing the `/lfg` lifecycle, but that context is not available inside the session.

### 1.2 Naming: Can a User Guess What to Type?

| Component | Name | User would guess? | Issue |
|-----------|------|-------------------|-------|
| Command | `/clavain:flux-drive` | No | "Flux drive" evokes sci-fi propulsion, not "document review." The README explains it's named after the Flux Review newsletter, but in-session there is no indication of this etymology. |
| Command | `/clavain:lfg` | No | Slang ("let's f***ing go") -- memorable once learned but utterly opaque to someone encountering it cold. |
| Command | `/clavain:compound` | Maybe | "Compound knowledge" is a reasonable term but could also mean "compound interest" or "compound sentence." |
| Command | `/clavain:resolve` | Yes | Clear, verb-based, action-oriented. Good name. |
| Command | `/clavain:quality-gates` | Yes | Standard engineering term. Good name. |
| Command | `/clavain:interpeer` | No | "Inter-peer" could mean many things. A user wanting cross-AI review would not guess this name. |
| Skill | `brainstorming` | Yes | Clear. But the *command* is `/clavain:brainstorm` (without "ing"). The skill description even says "For freeform brainstorming without phases, use /brainstorm instead" -- the wrong direction. The command `/brainstorm` is the structured one; the skill `brainstorming` is freeform. This naming is backwards. |
| Skill | `receiving-code-review` | Yes | Clear, action-oriented. |
| Skill | `verification-before-completion` | Yes | But wordy. Could be `verify-before-shipping` or just `verify`. |
| Skill | `prompterpeer`, `winterpeer`, `splinterpeer` | No | These are vestigial redirects (all point to `interpeer`). They add 3 entries to the skill count while providing zero unique functionality. |

**Key finding:** The most important commands (flux-drive, lfg, interpeer) have the least guessable names. This is a significant discoverability barrier for new users.

### 1.3 Skill vs Command Confusion

Clavain uses both skills and commands, but the distinction is not obvious to users:

- **brainstorming** (skill, freeform) vs **/clavain:brainstorm** (command, structured 4-phase)
- **executing-plans** (skill) vs **/clavain:execute-plan** (command that just invokes the skill)
- **flux-drive** (skill) vs **/clavain:flux-drive** (command that just invokes the skill)
- **interpeer** (skill) vs **/clavain:interpeer** (command that just invokes the skill)

Several commands are thin wrappers that do nothing but invoke a skill:
- `/clavain:execute-plan` -> "Invoke the clavain:executing-plans skill"
- `/clavain:flux-drive` -> "Use the clavain:flux-drive skill"
- `/clavain:create-agent-skill` -> invokes create-agent-skills skill

This means users have two ways to trigger the same behavior, with slightly different names. The distinction only matters for the agent's internal routing, not for the user.

---

## 2. Workflow Friction

### 2.1 The `/lfg` Pipeline: Excellent but Rigid

The `/lfg` command chains 8 steps: brainstorm -> write-plan -> flux-drive (plan review) -> work -> test -> quality-gates -> resolve -> ship. This is the plugin's showcase feature and it works well for greenfield feature development.

**Friction points:**

1. **No resume from failure.** If step 4 (work) fails and the session crashes, there is no built-in way to resume from step 4. The error recovery section says "re-invoke /clavain:lfg and manually skip completed steps by running their slash commands directly" -- this requires the user to remember which step they were on and manually reconstruct state.

2. **No partial pipeline.** If a user has already brainstormed and planned, they cannot run `/lfg` starting from step 4. They must run the individual commands. This is fine for power users who know the command names, but defeats the purpose of `/lfg` as a one-command workflow.

3. **Brainstorm -> Plan handoff is smooth; Plan -> Work handoff requires a file path.** The brainstorm command writes to `docs/brainstorms/` and the plan command writes to `docs/plans/`. The `/work` command requires a plan file path as input. If the user runs `/lfg`, the pipeline handles this automatically. But if they run commands individually, they must remember and pass the path.

### 2.2 Review Command Proliferation

There are 4 review-related commands plus the interpeer family:

| Command | Input | Output |
|---------|-------|--------|
| `/clavain:flux-drive` | File, directory, or diff | Multi-agent scored triage, up to 8 agents |
| `/clavain:quality-gates` | Git diff (auto-detected) | Risk-based agent selection, 2-5 agents |
| `/clavain:review` | PR number/URL/branch | 5+ agents, creates beads issues |
| `/clavain:plan-review` | Plan file | 3-agent lightweight review |
| `/clavain:interpeer` | Files or description | Cross-AI (Claude <-> Codex) |

The routing table's "Which review command?" section helps, but the overlap between `flux-drive` and `quality-gates` is significant. Both analyze changes and select agents. The primary difference is that `flux-drive` takes an explicit input path and does scored triage with user confirmation, while `quality-gates` auto-detects from git diff without user confirmation. A user who just wants "review my changes" has to choose between them.

**Recommendation:** Make `quality-gates` the default for "review what I just changed" and `flux-drive` for "deeply review this specific thing." The current situation where both commands exist with overlapping scope creates decision paralysis for the exactly the moment (shipping time) when users want simplicity.

### 2.3 The brainstorming/brainstorm Naming Confusion

This is the most confusing naming in the plugin:

- **Skill `brainstorming`**: "Freeform brainstorming mode... For a guided workflow with repo research, use /brainstorm instead."
- **Command `/clavain:brainstorm`**: "Structured brainstorm workflow... For freeform brainstorming without phases, use /brainstorming instead."

These cross-reference each other in their descriptions, creating a circular redirect where both say "for the other thing, use the other one." A user who types "brainstorm" will match either, and the agent must decide which to invoke. The naming convention (noun form = freeform, verb form = structured) is not intuitive.

### 2.4 `/work` vs `/execute-plan` vs `subagent-driven-development` vs `executing-plans`

Four components cover "execute an implementation plan":

1. **`/clavain:work`** -- Autonomous feature shipping, quality checks, phases
2. **`/clavain:execute-plan`** -- Batch execution with architect review checkpoints (thin wrapper for skill)
3. **Skill `executing-plans`** -- Same as execute-plan command
4. **Skill `subagent-driven-development`** -- Fresh subagent per task with two-stage review

The `/work` command explains "When to use this vs /execute-plan" inline, which is helpful. But having 4 ways to execute a plan is excessive. The decision tree in `subagent-driven-development` (Have plan? -> Tasks independent? -> Stay in session?) is well designed but buried inside a skill that users must already know to invoke.

---

## 3. Missing Workflows

### 3.1 No "Explain This Code" Workflow

Clavain covers brainstorm/plan/execute/review/ship but has no skill for "help me understand this unfamiliar codebase" beyond the repo-research-analyst agent. A `codebase-walkthrough` or `explain-architecture` skill that reads project docs, traces key paths, and explains how components fit together would be high value for onboarding to new codebases.

### 3.2 No Dependency Update Workflow

There is no skill for managing dependency updates (checking for outdated packages, evaluating breaking changes, testing updates). This is a common engineering task that benefits from the structured approach Clavain provides elsewhere.

### 3.3 No Rollback/Recovery Workflow

The `landing-a-change` skill covers shipping, but there is no corresponding skill for "this change broke things in production, help me revert safely." A `revert-safely` skill that mirrors `refactor-safely` would complete the deployment lifecycle.

### 3.4 No PR Description Generation

While `/clavain:changelog` generates changelogs and `/clavain:review` does PR reviews, there is no command to *generate* a PR description from the current branch's changes. This is a common "last mile" task before shipping.

### 3.5 No Quick Diff Summary

There is no lightweight "what did I change and why" command. `/clavain:quality-gates` runs full agent review; sometimes a user just wants a plain-language summary of their uncommitted changes.

---

## 4. Skill Bloat Analysis

### 4.1 Vestigial Skills (3 skills, should be removed)

These skills exist only as redirects to `interpeer`:

| Skill | Content | Recommendation |
|-------|---------|----------------|
| `prompterpeer` | 3-line redirect to interpeer (deep mode) | Remove. Keep as search keyword in interpeer's description only. |
| `winterpeer` | 3-line redirect to interpeer (council mode) | Remove. Keep as search keyword in interpeer's description only. |
| `splinterpeer` | 3-line redirect to interpeer (mine mode) | Remove. Keep as search keyword in interpeer's description only. |

These inflate the skill count from 30 to 33 without adding functionality. They exist for backward compatibility, but since they just redirect, they waste a skill invocation (loading the redirect, then loading interpeer).

### 4.2 Near-Duplicate Skills (2 pairs, candidates for merging)

**Pair 1: `requesting-code-review` + `receiving-code-review`**
- Both are about code review behavior
- `requesting` teaches when/how to dispatch review agents
- `receiving` teaches how to handle feedback without performative agreement
- These are two sides of the same workflow and could be one skill with two sections

**Pair 2: `verification-before-completion` + `landing-a-change`**
- `verification-before-completion` says "evidence before claims"
- `landing-a-change` says "verify -> review -> document -> commit"
- `landing-a-change` already references `verification-before-completion` as a sub-skill
- The verification skill could be inlined into landing-a-change rather than existing separately

### 4.3 Specialty Skills That May Not Justify Their Weight

| Skill | Monthly use estimate | Consider |
|-------|---------------------|----------|
| `slack-messaging` | Low | Very niche. Only useful if the user has slack CLI configured. |
| `mcp-cli` | Low | MCP CLI is a power-user tool; most users interact with MCP via plugins. |
| `finding-duplicate-functions` | Low | Useful but narrow. Could be a section in `refactor-safely`. |
| `file-todos` | Medium | The file-based todo system is a full workflow. Justified if the user adopts it. |
| `upstream-sync` | Low | Only relevant to Clavain developers, not Clavain users. Should this be bundled? |

### 4.4 Recommended Skill Count After Pruning

| Action | Skills removed |
|--------|---------------|
| Remove 3 vestigial redirects (prompterpeer, winterpeer, splinterpeer) | -3 |
| Merge requesting + receiving code review | -1 |
| Inline verification-before-completion into landing-a-change | -1 |
| (Optional) Move upstream-sync to Clavain-developer-only | -1 |
| **Result** | 27-28 skills (from 33) |

This brings the count below 30, which is a meaningful cognitive load reduction for the routing table.

---

## 5. Command Bloat Analysis

### 5.1 Commands That Are Thin Skill Wrappers

These commands do nothing but invoke a skill with the user's arguments:

| Command | Body | Skill invoked |
|---------|------|---------------|
| `/clavain:execute-plan` | 2 lines | executing-plans |
| `/clavain:flux-drive` | 1 line | flux-drive |
| `/clavain:create-agent-skill` | 1 line | create-agent-skills |
| `/clavain:heal-skill` | implied | heal-skill (no explicit skill) |

These wrappers serve as discoverability entry points (users can type `/clavain:` and see autocomplete), but they also mean the same action has two names. This is acceptable if the command name is more guessable than the skill name. For `flux-drive`, where neither name is guessable, the wrapper adds no discoverability value.

### 5.2 Commands With Very Narrow Scope

| Command | Scope | Users |
|---------|-------|-------|
| `/clavain:upstream-sync` | Check Clavain's own upstream repos | Only Clavain maintainer |
| `/clavain:generate-command` | Create a new slash command | Only plugin developers |
| `/clavain:heal-skill` | Fix broken SKILL.md files | Only plugin developers |
| `/clavain:agent-native-audit` | Agent architecture review | Very narrow domain |
| `/clavain:migration-safety` | Database migration safety | Narrow domain |
| `/clavain:changelog` | Generate team changelog | Narrow use case |

The meta/developer commands (upstream-sync, generate-command, heal-skill) are useful for plugin development but add noise for end users. They could be moved to a sub-namespace or documented as "developer tools."

### 5.3 Recommended Command Simplification

Rather than removing commands (which would break user muscle memory), consider:

1. **Group commands in the routing table** by frequency: "daily" (lfg, brainstorm, work, review, quality-gates, resolve, flux-drive) vs "weekly" (interpeer, debate, compound, setup) vs "developer" (upstream-sync, generate-command, heal-skill, create-agent-skill).

2. **Add aliases for the least guessable commands:** `/clavain:review-doc` -> flux-drive, `/clavain:ship` -> quality-gates + landing-a-change.

---

## 6. Hook UX

### 6.1 Stop Hooks: Blocking Is the Right Default

Clavain registers two Stop hooks that fire when Claude is about to stop responding:

**auto-compound.sh:**
- Detects compoundable signals (git commits, debugging resolutions, bead closures, insight markers)
- Blocks the stop and asks Claude to evaluate whether to run `/compound`
- Guards against infinite re-triggering with `stop_hook_active` check

**session-handoff.sh:**
- Detects uncommitted changes or in-progress beads
- Blocks the stop and asks Claude to write HANDOFF.md
- Only fires once per session (sentinel file in /tmp)

**Analysis:**

The auto-compound hook is the more controversial of the two. It fires after every turn that contains a commit, resolution phrase, or insight marker. For a productive session with many commits, this means the hook fires repeatedly. Each trigger adds a pause where Claude evaluates whether to compound. Even when Claude decides "no, this is trivial," the evaluation itself costs ~200-500ms of thinking time and produces output.

The session-handoff hook is well-designed: it only fires once, only when there is genuinely incomplete work, and produces a concrete artifact (HANDOFF.md). This is net positive.

**Specific concerns:**

1. **auto-compound fires too broadly.** The signal detection greps for "git commit" in the last 40 lines of the JSONL transcript. Every `git commit` triggers it, including routine commits during `/work` execution. The filter should be narrower -- perhaps only triggering when the commit follows a debugging session (resolution + commit together) rather than on every commit.

2. **No user opt-out for auto-compound.** There is no `.claude/clavain-disable-compound` flag or similar mechanism for users who find it annoying. The only way to disable it is to edit hooks.json, which is in the plugin cache and gets overwritten on update.

3. **Stop hooks block ALL stops, including user-initiated.** If a user types "stop" or hits Ctrl+C and Claude is about to stop, the hook fires. For session-handoff this is appropriate (the user is leaving, so generating handoff context is helpful). For auto-compound, being prompted to document a trivial fix when you are trying to stop the session is frustrating.

4. **Error handling is solid.** Both hooks have proper guards (stop_hook_active, sentinel file, graceful fallback when jq is missing, `exit 0` always). They will not crash the session.

### 6.2 SessionStart Hook: Good but Heavy

The SessionStart hook injects the full `using-clavain/SKILL.md` content (approximately 3,000 tokens) into every session's context. This is the right design choice -- it ensures the routing table is always available. However:

1. **The injected content is raw markdown including the EXTREMELY-IMPORTANT block.** This means every session starts with 8 lines of aggressive instructions aimed at the agent. Users see this in transcript/debug views and it creates a poor first impression.

2. **Companion detection is helpful.** The hook checks for beads and Oracle availability and reports status. This is good UX -- the user knows what tools are available without checking manually.

3. **Upstream staleness warning is clever.** Checking the file modification time of `docs/upstream-versions.json` (local check, no network) and warning if >7 days old is a smart low-cost signal.

### 6.3 PreToolUse Hook (Clodex Gate): Well-Designed

The autopilot.sh hook blocks source code writes when clodex mode is active and routes them through Codex agents. The allowlist (non-code files, /tmp, dotfiles) is comprehensive. The error message clearly explains what happened and what to do instead. This is a good example of hook UX: clear deny reason, clear recovery path.

### 6.4 SessionEnd Hook (Dotfiles Sync): Invisible and Correct

The dotfiles-sync hook runs async, no-ops silently if infrastructure is missing, and logs to a file. This is the gold standard for background hooks -- do useful work without bothering the user.

---

## 7. Onboarding Experience

### 7.1 First-Use Flow

1. User installs Clavain: `claude plugin install clavain@interagency-marketplace`
2. User starts a session. SessionStart hook fires, injecting the routing table.
3. User sees ~3,000 tokens of routing information including the EXTREMELY-IMPORTANT block.
4. User is expected to know to run `/clavain:setup` for full modpack installation.

**Problem:** Step 4 has no prompt. The routing table does not mention `/setup` at the top. A new user who does not read the README will miss the setup command entirely. They will have Clavain loaded but not the companion plugins (context7, serena, etc.) that make it fully functional.

### 7.2 `/clavain:setup` Is Good but Long

The setup command is thorough: it installs required plugins, disables conflicts, verifies MCP servers, initializes beads, and runs a verification check. The "next steps" section at the bottom suggests trying `/clavain:brainstorm` for a quick demo -- this is good onboarding.

**Issues:**

1. **No idempotency guarantee.** Running `/clavain:setup` twice should be safe (it checks for existing plugins before installing), but this is not stated explicitly. Users may be afraid to re-run it.

2. **8 conflicting plugins are disabled without confirmation.** If a user has `code-review` or `feature-dev` installed and configured for their workflow, `/setup` disables them. The user is not asked whether they want to keep any of these. This is aggressive for a first-run experience.

3. **Language server selection is interactive.** The setup command uses AskUserQuestion to ask which languages to enable, which is good. But the rest of the setup runs without confirmation, creating an inconsistent interaction pattern.

### 7.3 Missing Onboarding Elements

- **No "what is Clavain?" explanation in-session.** The README explains the philosophy; the in-session experience does not.
- **No skill glossary command.** `/clavain:help` or `/clavain:list` does not exist. Users cannot get a quick list of available commands with descriptions.
- **No guided first task.** After setup, the user is told to try `/brainstorm` or `/lfg` but not walked through a specific example with their own project.

---

## 8. Error States

### 8.1 Missing MCP Servers

Clavain declares two MCP servers in plugin.json: `context7` (HTTP) and `qmd` (stdio, requires local binary).

**context7:** If the HTTP endpoint is down, tools like `resolve-library-id` and `query-docs` will fail. Clavain does not check for context7 availability at session start. The flux-drive skill uses qmd as a supplement but does not handle context7 failures explicitly.

**qmd:** If `qmd` binary is not installed, the MCP server fails to start. The setup command checks for qmd and tells the user to install it, but sessions between install and setup will have a broken MCP server with no user-facing error. Claude Code may surface this as an MCP error, but Clavain does not provide a graceful fallback message.

**Recommendation:** The SessionStart hook should check for MCP server health and warn if either is unavailable, similar to how it checks for Oracle.

### 8.2 Missing Codex CLI

The `/clavain:interpeer` (quick mode) and `/clavain:debate` commands depend on Codex CLI being installed. If Codex is not available:

- `interpeer` has explicit error handling: "1. Retry, 2. Check install, 3. Escalate to deep, 4. Self-review"
- `debate` attempts to resolve `debate.sh` from two paths and has no explicit fallback if neither exists

### 8.3 Hook Failure Modes

All hooks use `set -euo pipefail` and `exit 0` at the end, which means:
- If any command in the hook fails, the hook exits with 0 (due to the final `exit 0`)
- Wait -- this is actually incorrect. With `set -e`, the script exits immediately on error, but the final `exit 0` is unreachable if an earlier command fails. However, most hooks have `|| true` fallbacks on fragile commands.

**Specific risk:** In `auto-compound.sh`, the `jq` command at line 24 (`echo "$INPUT" | jq -r '.stop_hook_active // false'`) will fail with exit code 1 if stdin is empty or malformed JSON. With `set -e`, this kills the script before reaching the guard logic. The fallback jq-less path only applies to the *output* JSON, not the *input* parsing.

**Recommendation:** Add `|| echo "false"` after the jq input parsing in both Stop hooks to prevent malformed input from crashing the hook.

### 8.4 Agent Dispatch Failures

When `/clavain:quality-gates` or `/clavain:flux-drive` launches subagents in background, there is no explicit timeout or error-collection mechanism described in the commands. The flux-drive skill has Oracle timeout handling (480s) but plugin agents launched via Task tool have no documented timeout behavior.

If an agent hangs or fails silently, the synthesis phase will wait indefinitely or produce incomplete results. The flux-drive skill's `phases/launch.md` may address this (it is loaded progressively), but the user-facing command does not mention what happens when agents fail.

---

## 9. Terminology Consistency

Several terms are used inconsistently:

| Concept | Term 1 | Term 2 | Where |
|---------|--------|--------|-------|
| The person using Claude | "user" | "your human partner" | Most skills say "user"; receiving-code-review says "your human partner" |
| The execution plan | "plan" | "spec" | /work accepts "plan file, specification, or todo file" |
| Review agents | "fd-* agents" | "reviewer agents" | Used interchangeably |
| Knowledge capture | "compound" | "document" | /compound vs engineering-docs |
| Cross-AI review | "interpeer" | "cross-AI" | Used interchangeably in routing table |

The "your human partner" language in `receiving-code-review` is distinctive and personal but inconsistent with every other skill. This came from the compound-engineering upstream and should be normalized.

---

## 10. Token Budget Concerns

The SessionStart hook injects ~3,000 tokens of routing table content into every session. This is justified because it enables skill routing without manual invocation. However, the combined weight of:

1. SessionStart injection (~3,000 tokens)
2. First skill invocation (1,500-2,000 tokens per skill)
3. Agent system prompts (varies, but fd-* agents are substantial)

means a typical Clavain-mediated task starts with 5,000-8,000 tokens of skill/routing content before any user interaction. For a 200k context window this is acceptable; for shorter-context models or Codex CLI with tighter limits, this is significant.

---

## 11. Recommendations (Prioritized)

### P0: Fix Before Next Release

1. **Remove the 3 vestigial redirect skills** (prompterpeer, winterpeer, splinterpeer). Add their names as keywords in interpeer's description for backward discovery.

2. **Fix the skill count inconsistency** -- using-clavain says "34 skills" while CLAUDE.md says "33 skills." After removing the 3 redirects, update all references to "30 skills."

3. **Add jq error guards** to Stop hooks' input parsing (lines 24-26 of auto-compound.sh and session-handoff.sh). `STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo "false")`.

4. **Add `/clavain:setup` mention to the SessionStart injection** so new users discover it. One line: "First time? Run /clavain:setup to install companion plugins."

### P1: Address in Next Development Cycle

5. **Rename the brainstorming/brainstorm pair.** Suggestion: rename the skill to `freeform-brainstorming` and keep the command as `/clavain:brainstorm`. The description of each should not cross-reference the other in confusing circular fashion.

6. **Add a disable mechanism for auto-compound.** Check for `$PROJECT_DIR/.claude/clavain-no-autocompound` flag file. Power users who find the hook annoying need an escape hatch that survives plugin updates.

7. **Narrow auto-compound trigger conditions.** Only fire when (resolution + commit) or (investigation + commit) signals co-occur, not on every commit. A routine commit during `/work` execution is not a compounding event.

8. **Add MCP health check to SessionStart.** Test context7 reachability and qmd availability; warn if either is missing (similar to Oracle detection).

9. **Group commands in the routing table by frequency.** Top 7 commands that cover 80% of use cases should be visually separated from the remaining 18.

### P2: Improve When Opportunity Arises

10. **Merge `requesting-code-review` + `receiving-code-review`** into one `code-review-discipline` skill with "requesting" and "receiving" sections.

11. **Inline `verification-before-completion` into `landing-a-change`.** The verification skill is always invoked from landing-a-change; making it standalone inflates the skill count without adding routing value.

12. **Add a `/clavain:summarize-changes` lightweight command** that generates a plain-language summary of uncommitted changes without launching review agents. Fast, lightweight, daily utility.

13. **Add a `/clavain:describe-pr` command** that generates a PR title + description from the current branch's commits.

14. **Soften the EXTREMELY-IMPORTANT block.** Replace with a factual statement: "Clavain skills are designed to be invoked proactively. When a skill matches the current task, invoke it before responding." Same effect, professional tone.

15. **Remove `upstream-sync` skill from the user-facing routing table.** It is only relevant to Clavain maintainers. Keep the command but mark it as "developer tool" in documentation.

### P3: Consider for Future Versions

16. **Add a `codebase-walkthrough` skill** for understanding unfamiliar codebases.
17. **Add a `revert-safely` skill** that mirrors refactor-safely for rollback scenarios.
18. **Add `/lfg` resume support** with a state file that tracks which step was last completed.
19. **Consider sub-namespaces** for developer-only commands: `/clavain:dev:generate-command`, `/clavain:dev:heal-skill`, etc.
20. **Add an optional "quiet mode"** that suppresses auto-compound and upstream staleness warnings for focused coding sessions.

---

## 12. Strengths Worth Preserving

1. **The `/lfg` pipeline is the killer feature.** One command to go from idea to shipped code with review at every stage. This is genuinely differentiated.

2. **The fd-* agent roster with scored triage is well-engineered.** Pre-filtering agents by relevance, scoring them, staging them, and asking for user confirmation before launch -- this is a model for how multi-agent orchestration should work.

3. **The interpeer escalation model (quick -> deep -> council -> mine) is clever.** Progressive escalation from fast/cheap to slow/expensive gives users control over the cost/depth tradeoff.

4. **Skills are genuinely opinionated.** `receiving-code-review` teaches "no performative agreement" and YAGNI enforcement. `verification-before-completion` teaches "evidence before claims." These are real engineering values, not generic platitudes.

5. **Hook error handling is robust.** Guards against re-triggering, sentinel files, graceful fallbacks when jq is missing, and `exit 0` patterns demonstrate mature hook development.

6. **The modpack concept is correct.** Clavain positions itself as an integration layer that configures companion plugins rather than duplicating them. This is the right architecture for a meta-plugin.

---

## Appendix: Component Inventory

### Skills (33 -> recommended 28-30)

| # | Skill | Keep/Remove/Merge | Rationale |
|---|-------|-------------------|-----------|
| 1 | agent-native-architecture | Keep | Unique domain |
| 2 | beads-workflow | Keep | Core workflow integration |
| 3 | brainstorming | Rename | Rename to freeform-brainstorming |
| 4 | clodex | Keep | Core Codex dispatch |
| 5 | create-agent-skills | Keep | Meta/developer |
| 6 | developing-claude-code-plugins | Keep | Meta/developer |
| 7 | dispatching-parallel-agents | Keep | Core execution pattern |
| 8 | distinctive-design | Keep | Unique domain |
| 9 | engineering-docs | Keep | Knowledge capture |
| 10 | executing-plans | Keep | Core execution |
| 11 | file-todos | Keep | Workflow integration |
| 12 | finding-duplicate-functions | Keep (consider merge with refactor-safely) | Narrow but useful |
| 13 | flux-drive | Keep | Core review |
| 14 | interpeer | Keep | Core cross-AI |
| 15 | landing-a-change | Keep (absorb verification-before-completion) | Core shipping |
| 16 | mcp-cli | Keep | Power-user tool |
| 17 | prompterpeer | Remove | Vestigial redirect |
| 18 | receiving-code-review | Merge with requesting | Both sides of one workflow |
| 19 | refactor-safely | Keep | Core refactoring |
| 20 | requesting-code-review | Merge with receiving | Both sides of one workflow |
| 21 | slack-messaging | Keep (flag as niche) | Useful when configured |
| 22 | splinterpeer | Remove | Vestigial redirect |
| 23 | subagent-driven-development | Keep | Core execution pattern |
| 24 | systematic-debugging | Keep | Core debugging |
| 25 | test-driven-development | Keep | Core TDD |
| 26 | upstream-sync | Keep (developer-only) | Clavain maintenance |
| 27 | using-clavain | Keep | Bootstrap routing |
| 28 | using-tmux-for-interactive-commands | Keep | Infrastructure |
| 29 | verification-before-completion | Merge into landing-a-change | Sub-skill, not standalone |
| 30 | winterpeer | Remove | Vestigial redirect |
| 31 | working-with-claude-code | Keep | Reference docs |
| 32 | writing-plans | Keep | Core planning |
| 33 | writing-skills | Keep | Meta/developer |

### Commands (25)

All commands are justified as user entry points. Thin wrappers (execute-plan, flux-drive, create-agent-skill) serve as discoverability aids even if they just invoke skills. No commands recommended for removal, but grouping by frequency in documentation would reduce perceived complexity.

### Agents (16)

The agent roster is lean and well-structured after the v1->fd-* consolidation. No changes recommended.

---

## Summary Metrics

| Metric | Current | Recommended |
|--------|---------|-------------|
| Skills | 33 | 28-30 |
| Commands | 25 | 25 (regroup, don't remove) |
| Agents | 16 | 16 |
| Hooks | 5 | 5 (improve 2) |
| MCP Servers | 2 | 2 |
| Routing table injection | ~3,000 tokens | ~2,500 tokens (after removing redirect skills from references) |
| New user time-to-first-value | Unknown (no guided onboarding) | Add /setup mention to SessionStart |

---

*Review conducted against Clavain v0.4.29 on 2026-02-11. All file paths are relative to `/root/projects/Clavain/`.*
