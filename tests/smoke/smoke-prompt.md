You are running smoke tests for the Clavain plugin. Your job is to:
1. Dispatch 17 agents with minimal test prompts (Part 1)
2. Invoke 5 commands via the Skill tool (Part 2)
3. Evaluate 3 workflow chains from command outputs (Part 3)
4. Report a unified 25-test summary table

**Known behavior**: Agents receive a "MANDATORY FIRST STEP" preamble from the Task tool framework that conflicts with the "no tools" smoke instruction. This is expected — agents may note the conflict or attempt tool use. Grade on output quality (non-empty, coherent review), not tool compliance. See docs/solutions/best-practices/smoke-test-agent-instruction-conflict-20260210.md for details.

## Pre-check

Before dispatching any agents, verify all agent files exist. Check each of these paths exists:
- agents/review/fd-quality.md
- agents/review/fd-architecture.md
- agents/review/fd-performance.md
- agents/review/fd-safety.md
- agents/review/fd-correctness.md
- agents/review/fd-user-product.md
- agents/review/plan-reviewer.md
- agents/review/agent-native-reviewer.md
- agents/review/data-migration-expert.md
- agents/review/fd-game-design.md
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

## Part 1: Agent Smoke Tests (17 agents, all in parallel)

Launch ALL 17 agents in parallel using the Task tool with `run_in_background: true`. Use `model: haiku` and `max_turns: 3` for each.

Every agent prompt MUST start with exactly this text:
"SMOKE TEST — respond with a brief review only. Do NOT use any tools. Do NOT use MCP tools. Do NOT write files. Just respond with text."

### Agent 1: fd-quality
- subagent_type: clavain:review:fd-quality
- Prompt: [smoke test prefix] Review this Python code for quality issues:
```python
def get_user_emails(users):
    emails = []
    for user in users:
        if user.get('email') != None:
            emails.append(user['email'])
    return emails
```
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 2: fd-architecture
- subagent_type: clavain:review:fd-architecture
- Prompt: [smoke test prefix] Review this module boundary design:
A CLI tool has three packages: cmd/ (entrypoint), internal/engine/ (business logic), internal/output/ (formatting). The cmd/ package imports both engine and output. The output package imports engine for result types.
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 3: fd-performance
- subagent_type: clavain:review:fd-performance
- Prompt: [smoke test prefix] Review this code for performance issues:
```go
func processItems(items []string) map[string]int {
    result := map[string]int{}
    for i := 0; i < len(items); i++ {
        result[items[i]] = result[items[i]] + 1
    }
    return result
}
```
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 4: fd-safety
- subagent_type: clavain:review:fd-safety
- Prompt: [smoke test prefix] Review this endpoint for security issues:
```python
@app.route('/search')
def search():
    query = request.args.get('q', '')
    results = db.execute(f"SELECT * FROM items WHERE name LIKE '%{query}%'")
    return render_template('results.html', results=results, query=query)
```
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 5: fd-correctness
- subagent_type: clavain:review:fd-correctness
- Prompt: [smoke test prefix] Review this Python function for correctness issues:
```python
def transfer_funds(from_acct, to_acct, amount):
    balance = get_balance(from_acct)
    if balance >= amount:
        set_balance(from_acct, balance - amount)
        to_balance = get_balance(to_acct)
        set_balance(to_acct, to_balance + amount)
    return balance >= amount
```
Provide 2-3 bullet points focusing on race conditions and data consistency. Keep response under 200 words.

### Agent 6: fd-user-product
- subagent_type: clavain:review:fd-user-product
- Prompt: [smoke test prefix] Review this CLI design for user experience issues:
A CLI tool has 8 subcommands. To add a file to a project, users must type: `tool project add --file path/to/file --format json --validate true --dry-run false`. When a file is not found, the error says "Error code 404: resource unavailable".
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 7: plan-reviewer
- subagent_type: clavain:review:plan-reviewer
- Prompt: [smoke test prefix] Review this implementation plan for completeness:
"Step 1: Add user model with email validation. Step 2: Create registration endpoint. Step 3: Add login with JWT tokens. Step 4: Deploy to staging."
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 8: agent-native-reviewer
- subagent_type: clavain:review:agent-native-reviewer
- Prompt: [smoke test prefix] Review this feature for agent-native access:
"A new dashboard page lets users filter emails by date range and sender. Users click a calendar widget to select dates, then click Apply. Results appear in a scrollable table."
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 9: data-migration-expert
- subagent_type: clavain:review:data-migration-expert
- Prompt: [smoke test prefix] Review this database migration for safety:
```sql
ALTER TABLE users ADD COLUMN account_id INTEGER;
UPDATE users SET account_id = (SELECT id FROM accounts WHERE accounts.email = users.email);
ALTER TABLE users DROP COLUMN legacy_email_ref;
```
Provide 2-3 bullet points focusing on data integrity and rollback safety. Keep response under 200 words.

### Agent 10: fd-game-design
- subagent_type: clavain:review:fd-game-design
- Prompt: [smoke test prefix] Review this game system design for balance issues:
A survival game has a hunger system where hunger decays at 1 point per minute. Food restores 50 hunger. The player starts with 100 hunger and can carry 5 food items. Enemies drop food 30% of the time but fighting costs 10 hunger.
Provide 2-3 bullet points focusing on feedback loops and balance. Keep response under 200 words.

### Agent 11: best-practices-researcher
- subagent_type: clavain:research:best-practices-researcher
- Prompt: [smoke test prefix] What are 3 best practices for writing bats-core shell tests? Keep response under 200 words.

### Agent 12: framework-docs-researcher
- subagent_type: clavain:research:framework-docs-researcher
- Prompt: [smoke test prefix] What are 3 key React hooks concepts a new developer should understand? You can use general knowledge — no need to fetch external docs. Keep response under 200 words.

### Agent 13: git-history-analyzer
- subagent_type: clavain:research:git-history-analyzer
- Prompt: [smoke test prefix] A file grew from 50 to 300 lines over 3 commits. What patterns would you look for in git history to understand why? Keep response under 200 words.

### Agent 14: learnings-researcher
- subagent_type: clavain:research:learnings-researcher
- Prompt: [smoke test prefix] How would you search a docs/solutions/ directory for past learnings about email processing performance? Describe your search strategy in 2-3 bullet points. Keep response under 200 words.

### Agent 15: repo-research-analyst
- subagent_type: clavain:research:repo-research-analyst
- Prompt: [smoke test prefix] When onboarding to a new Rails repository, what 3-4 files or directories would you check first to understand the project structure? Keep response under 200 words.

### Agent 16: pr-comment-resolver
- subagent_type: clavain:workflow:pr-comment-resolver
- Prompt: [smoke test prefix] How would you approach resolving this PR comment: "This function is too long, please extract the validation logic into a separate helper." Provide 2-3 bullet points. Keep response under 200 words.

### Agent 17: bug-reproduction-validator
- subagent_type: clavain:workflow:bug-reproduction-validator
- Prompt: [smoke test prefix] Bug report: "CSV export fails when username contains commas." How would you reproduce this bug systematically? Describe your steps in 2-3 bullet points. Keep response under 200 words.

---

## Part 2: Command Smoke Tests (5 commands, sequential)

After ALL 17 agents have completed and you've collected their results, run these 5 command tests sequentially using the Skill tool.

**Important**: Command tests verify the dispatch mechanism works (Skill tool loads the command, Claude processes it). They do NOT verify outcomes — a command that runs and produces output is a PASS even if the output reports errors or missing tools.

### Command 18: help
- Invoke: `Skill(skill: "clavain:help")`
- PASS criteria: Output is non-empty and contains at least one `/clavain:` reference

### Command 19: doctor
- Invoke: `Skill(skill: "clavain:doctor")`
- PASS criteria: Output is non-empty (>50 chars). The command may report missing tools — that's still a PASS.

### Command 20: changelog
- Invoke: `Skill(skill: "clavain:changelog")`
- PASS criteria: Output is non-empty (>50 chars). Even "quiet day, no changes" counts as a PASS.

### Command 21: brainstorm
- Invoke: `Skill(skill: "clavain:brainstorm", args: "add a caching layer to a REST API")`
- PASS criteria: Output contains a question, assessment, or structured exploration

### Command 22: quality-gates
- Invoke: `Skill(skill: "clavain:quality-gates")`
- PASS criteria: Output is non-empty and references "diff", "review", "agent", or "change"

---

## Part 3: End-to-End Workflow Tests (3 chains, graded from existing outputs)

These tests verify that key multi-step workflows are wired correctly. They piggyback on outputs from Part 2 — no additional invocations needed.

### Workflow 23: Review pipeline wiring
- Source: Command 22 (quality-gates) output
- Chain verified: command → skill → agent dispatch
- PASS criteria: Output mentions at least one fd-* agent name (fd-quality, fd-architecture, fd-safety, etc.) OR mentions "reviewer" or "agent"

### Workflow 24: Explore pipeline wiring
- Source: Command 21 (brainstorm) output
- Chain verified: command → brainstorming skill → structured exploration
- PASS criteria: Output follows a structured format (numbered list, questions, phases, or sections)

### Workflow 25: Help catalog completeness
- Source: Command 18 (help) output
- Chain verified: command → complete catalog rendering
- PASS criteria: Output contains at least 30 distinct `/clavain:` references (we have 36 commands, allowing for some omissions in help display)

---

## Grading Rules

### Agent tests (1-17)
- **PASS**: Agent completed, output is non-empty (> 50 chars), output is coherent and on-topic
- **FAIL**: Agent errored, output is empty, or output is completely off-topic

### Command tests (18-22)
- **PASS**: Command dispatched via Skill tool, produced non-empty output matching criteria above
- **FAIL**: Skill invocation errored, or output is empty/missing

### Workflow tests (23-25)
- **PASS**: Output from the source command meets the chain verification criteria above
- **FAIL**: Output does not demonstrate the expected workflow wiring

---

## Report

Output a markdown results table with all 25 tests:

```
## Smoke Test Results

| # | Test | Type | Status | Notes |
|---|------|------|--------|-------|
| 1 | fd-quality | agent | PASS/FAIL | [brief] |
| 2 | fd-architecture | agent | PASS/FAIL | [brief] |
| 3 | fd-performance | agent | PASS/FAIL | [brief] |
| 4 | fd-safety | agent | PASS/FAIL | [brief] |
| 5 | fd-correctness | agent | PASS/FAIL | [brief] |
| 6 | fd-user-product | agent | PASS/FAIL | [brief] |
| 7 | plan-reviewer | agent | PASS/FAIL | [brief] |
| 8 | agent-native-reviewer | agent | PASS/FAIL | [brief] |
| 9 | data-migration-expert | agent | PASS/FAIL | [brief] |
| 10 | fd-game-design | agent | PASS/FAIL | [brief] |
| 11 | best-practices-researcher | agent | PASS/FAIL | [brief] |
| 12 | framework-docs-researcher | agent | PASS/FAIL | [brief] |
| 13 | git-history-analyzer | agent | PASS/FAIL | [brief] |
| 14 | learnings-researcher | agent | PASS/FAIL | [brief] |
| 15 | repo-research-analyst | agent | PASS/FAIL | [brief] |
| 16 | pr-comment-resolver | agent | PASS/FAIL | [brief] |
| 17 | bug-reproduction-validator | agent | PASS/FAIL | [brief] |
| 18 | help | command | PASS/FAIL | [brief] |
| 19 | doctor | command | PASS/FAIL | [brief] |
| 20 | changelog | command | PASS/FAIL | [brief] |
| 21 | brainstorm | command | PASS/FAIL | [brief] |
| 22 | quality-gates | command | PASS/FAIL | [brief] |
| 23 | review-pipeline | workflow | PASS/FAIL | [brief] |
| 24 | explore-pipeline | workflow | PASS/FAIL | [brief] |
| 25 | help-catalog | workflow | PASS/FAIL | [brief] |

**Result: N/25 passed.**
```

## Cleanup

After reporting, delete any files agents may have written to `docs/research/smoke-test-*.md`.

If all 25 passed, end with: "All smoke tests passed."
If any failed, end with: "SMOKE TEST FAILURE: N test(s) failed." and list which ones.
