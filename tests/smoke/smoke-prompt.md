You are running smoke tests for the Clavain plugin. Your job is to:
1. Dispatch 10 agents with minimal test prompts (Part 1)
2. Invoke 5 commands via the Skill tool (Part 2)
3. Evaluate 3 workflow chains from command outputs (Part 3)
4. Report a unified 19-test summary table

**Known behavior**: Agents receive a "MANDATORY FIRST STEP" preamble from the Task tool framework that conflicts with the "no tools" smoke instruction. This is expected — agents may note the conflict or attempt tool use. Grade on output quality (non-empty, coherent review), not tool compliance. See docs/solutions/best-practices/smoke-test-agent-instruction-conflict-20260210.md for details.

## Pre-check

Before dispatching any agents, verify all agent files exist. Check each of these paths exists:
- agents/review/plan-reviewer.md
- agents/review/data-migration-expert.md
- agents/research/best-practices-researcher.md
- agents/research/framework-docs-researcher.md
- agents/research/git-history-analyzer.md
- agents/research/learnings-researcher.md
- agents/research/repo-research-analyst.md
- agents/workflow/pr-comment-resolver.md
- agents/workflow/bug-reproduction-validator.md

Also verify these command files exist:
- commands/help.md
- commands/doctor.md
- commands/changelog.md
- commands/brainstorm.md
- commands/quality-gates.md

If ANY file is missing, report which one and exit with failure. Do NOT proceed to dispatch.

---

## Part 1: Agent Smoke Tests (10 agents, all in parallel)

Launch ALL 10 agents in parallel using the Task tool with `run_in_background: true`. Use `model: haiku` and `max_turns: 3` for each.

Every agent prompt MUST start with exactly this text:
"SMOKE TEST — respond with a brief review only. Do NOT use any tools. Do NOT use MCP tools. Do NOT write files. Just respond with text."

### Agent 1: plan-reviewer
- subagent_type: clavain:review:plan-reviewer
- Prompt: [smoke test prefix] Review this implementation plan for completeness:
"Step 1: Add user model with email validation. Step 2: Create registration endpoint. Step 3: Add login with JWT tokens. Step 4: Deploy to staging."
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 2: data-migration-expert
- subagent_type: clavain:review:data-migration-expert
- Prompt: [smoke test prefix] Review this database migration for safety:
```sql
ALTER TABLE users ADD COLUMN account_id INTEGER;
UPDATE users SET account_id = (SELECT id FROM accounts WHERE accounts.email = users.email);
ALTER TABLE users DROP COLUMN legacy_email_ref;
```
Provide 2-3 bullet points focusing on data integrity and rollback safety. Keep response under 200 words.

### Agent 4: best-practices-researcher
- subagent_type: clavain:research:best-practices-researcher
- Prompt: [smoke test prefix] What are 3 best practices for writing bats-core shell tests? Keep response under 200 words.

### Agent 5: framework-docs-researcher
- subagent_type: clavain:research:framework-docs-researcher
- Prompt: [smoke test prefix] What are 3 key React hooks concepts a new developer should understand? You can use general knowledge — no need to fetch external docs. Keep response under 200 words.

### Agent 6: git-history-analyzer
- subagent_type: clavain:research:git-history-analyzer
- Prompt: [smoke test prefix] A file grew from 50 to 300 lines over 3 commits. What patterns would you look for in git history to understand why? Keep response under 200 words.

### Agent 7: learnings-researcher
- subagent_type: clavain:research:learnings-researcher
- Prompt: [smoke test prefix] How would you search a docs/solutions/ directory for past learnings about email processing performance? Describe your search strategy in 2-3 bullet points. Keep response under 200 words.

### Agent 8: repo-research-analyst
- subagent_type: clavain:research:repo-research-analyst
- Prompt: [smoke test prefix] When onboarding to a new Rails repository, what 3-4 files or directories would you check first to understand the project structure? Keep response under 200 words.

### Agent 9: pr-comment-resolver
- subagent_type: clavain:workflow:pr-comment-resolver
- Prompt: [smoke test prefix] How would you approach resolving this PR comment: "This function is too long, please extract the validation logic into a separate helper." Provide 2-3 bullet points. Keep response under 200 words.

### Agent 10: bug-reproduction-validator
- subagent_type: clavain:workflow:bug-reproduction-validator
- Prompt: [smoke test prefix] Bug report: "CSV export fails when username contains commas." How would you reproduce this bug systematically? Describe your steps in 2-3 bullet points. Keep response under 200 words.

---

## Part 2: Command Smoke Tests (5 commands, sequential)

After ALL 10 agents have completed and you've collected their results, run these 5 command tests sequentially using the Skill tool.

**Important**: Command tests verify the dispatch mechanism works (Skill tool loads the command, Claude processes it). They do NOT verify outcomes — a command that runs and produces output is a PASS even if the output reports errors or missing tools.

### Command 11: help
- Invoke: `Skill(skill: "clavain:help")`
- PASS criteria: Output is non-empty and contains at least one `/clavain:` reference

### Command 12: doctor
- Invoke: `Skill(skill: "clavain:doctor")`
- PASS criteria: Output is non-empty (>50 chars). The command may report missing tools — that's still a PASS.

### Command 13: changelog
- Invoke: `Skill(skill: "clavain:changelog")`
- PASS criteria: Output is non-empty (>50 chars). Even "quiet day, no changes" counts as a PASS.

### Command 14: brainstorm
- Invoke: `Skill(skill: "clavain:brainstorm", args: "add a caching layer to a REST API")`
- PASS criteria: Output contains a question, assessment, or structured exploration

### Command 15: quality-gates
- Invoke: `Skill(skill: "clavain:quality-gates")`
- PASS criteria: Output is non-empty and references "diff", "review", "agent", or "change"

---

## Part 3: End-to-End Workflow Tests (3 chains, graded from existing outputs)

These tests verify that key multi-step workflows are wired correctly. They piggyback on outputs from Part 2 — no additional invocations needed.

### Workflow 16: Review pipeline wiring
- Source: Command 15 (quality-gates) output
- Chain verified: command → skill → agent dispatch
- PASS criteria: Output mentions at least one agent name (fd-quality, fd-architecture, fd-safety, etc.) OR mentions "reviewer" or "agent"

### Workflow 17: Explore pipeline wiring
- Source: Command 14 (brainstorm) output
- Chain verified: command → structured exploration (dialogue principles inline)
- PASS criteria: Output follows a structured format (numbered list, questions, phases, or sections)

### Workflow 18: Help catalog completeness
- Source: Command 11 (help) output
- Chain verified: command → complete catalog rendering
- PASS criteria: Output contains at least 28 distinct `/clavain:` references (we have 35 commands, allowing for some omissions in help display)

---

## Part 4: Interserve Behavioral Contract Test (1 test)

This test validates that interserve mode's behavioral contract is respected when injected via session-start.

### Test 19: interserve-behavioral-compliance

This test requires setup before the claude session. It cannot be dispatched like other tests — it validates session-level behavior.

**Setup** (run by the test runner, not by Claude):
1. Create flag file: `mkdir -p .claude && date -Iseconds > .claude/clodex-toggle.flag`
2. Start a NEW claude session with `--plugin-dir` pointing to the Clavain repo
3. Send this prompt: "Please add a retry timeout constant to internal/auth/handler.go. Set it to 30 seconds."

**Expected behavior** (grade by the test runner):
- Claude should NOT use Edit or Write tools on any `.go` file
- Claude SHOULD suggest using `/interserve` to dispatch, OR ask to toggle interserve off, OR explain it cannot edit source code directly in interserve mode
- Any of those responses = PASS

**PASS criteria**: Claude's response mentions "interserve", "dispatch", "Codex", or "toggle off" — AND no Edit/Write tool was used on a `.go` file
**FAIL criteria**: Claude used Edit/Write on a `.go` file without mentioning interserve constraints

**Note**: This test is marked as MANUAL in the results table since it requires session-level setup. The automated runner should skip it and mark it as "SKIP (manual)" unless `--include-interserve` flag is passed.

---

## Grading Rules

### Agent tests (1-10)
- **PASS**: Agent completed, output is non-empty (> 50 chars), output is coherent and on-topic
- **FAIL**: Agent errored, output is empty, or output is completely off-topic

### Command tests (11-15)
- **PASS**: Command dispatched via Skill tool, produced non-empty output matching criteria above
- **FAIL**: Skill invocation errored, or output is empty/missing

### Workflow tests (16-18)
- **PASS**: Output from the source command meets the chain verification criteria above
- **FAIL**: Output does not demonstrate the expected workflow wiring

---

## Report

Output a markdown results table with all 18 tests:

```
## Smoke Test Results

| # | Test | Type | Status | Notes |
|---|------|------|--------|-------|
| 1 | plan-reviewer | agent | PASS/FAIL | [brief] |
| 2 | data-migration-expert | agent | PASS/FAIL | [brief] |
| 4 | best-practices-researcher | agent | PASS/FAIL | [brief] |
| 5 | framework-docs-researcher | agent | PASS/FAIL | [brief] |
| 6 | git-history-analyzer | agent | PASS/FAIL | [brief] |
| 7 | learnings-researcher | agent | PASS/FAIL | [brief] |
| 8 | repo-research-analyst | agent | PASS/FAIL | [brief] |
| 9 | pr-comment-resolver | agent | PASS/FAIL | [brief] |
| 10 | bug-reproduction-validator | agent | PASS/FAIL | [brief] |
| 11 | help | command | PASS/FAIL | [brief] |
| 12 | doctor | command | PASS/FAIL | [brief] |
| 13 | changelog | command | PASS/FAIL | [brief] |
| 14 | brainstorm | command | PASS/FAIL | [brief] |
| 15 | quality-gates | command | PASS/FAIL | [brief] |
| 16 | review-pipeline | workflow | PASS/FAIL | [brief] |
| 17 | explore-pipeline | workflow | PASS/FAIL | [brief] |
| 18 | help-catalog | workflow | PASS/FAIL | [brief] |
| 19 | interserve-behavioral | behavioral | SKIP (manual) | Requires --include-interserve |

**Result: N/19 passed (1 skipped).**
```

## Cleanup

After reporting, delete any files agents may have written to `docs/research/smoke-test-*.md`.

If all 18 passed, end with: "All smoke tests passed."
If any failed, end with: "SMOKE TEST FAILURE: N test(s) failed." and list which ones.
