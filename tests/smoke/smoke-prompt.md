You are running smoke tests for the Clavain plugin. Your job is to dispatch 8 agents with minimal test prompts, collect pass/fail results, and report a summary table.

**Known behavior**: Agents receive a "MANDATORY FIRST STEP" preamble from the Task tool framework that conflicts with the "no tools" smoke instruction. This is expected — agents may note the conflict or attempt tool use. Grade on output quality (non-empty, coherent review), not tool compliance. See docs/solutions/best-practices/smoke-test-agent-instruction-conflict-20260210.md for details.

## Pre-check

Before dispatching any agents, verify all agent files exist. Check each of these paths exists:
- agents/review/fd-quality.md
- agents/review/fd-architecture.md
- agents/review/fd-performance.md
- agents/review/fd-safety.md
- agents/review/plan-reviewer.md
- agents/review/agent-native-reviewer.md
- agents/research/best-practices-researcher.md
- agents/workflow/pr-comment-resolver.md

If ANY file is missing, report which one and exit with failure. Do NOT proceed to dispatch.

## Dispatch

Launch ALL 8 agents in parallel using the Task tool with `run_in_background: true`. Use `model: haiku` and `max_turns: 3` for each.

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

### Agent 5: plan-reviewer
- subagent_type: clavain:review:plan-reviewer
- Prompt: [smoke test prefix] Review this implementation plan for completeness:
"Step 1: Add user model with email validation. Step 2: Create registration endpoint. Step 3: Add login with JWT tokens. Step 4: Deploy to staging."
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 6: agent-native-reviewer
- subagent_type: clavain:review:agent-native-reviewer
- Prompt: [smoke test prefix] Review this feature for agent-native access:
"A new dashboard page lets users filter emails by date range and sender. Users click a calendar widget to select dates, then click Apply. Results appear in a scrollable table."
Provide 2-3 bullet points. Keep response under 200 words.

### Agent 7: best-practices-researcher
- subagent_type: clavain:research:best-practices-researcher
- Prompt: [smoke test prefix] What are 3 best practices for writing bats-core shell tests? Keep response under 200 words.

### Agent 8: pr-comment-resolver
- subagent_type: clavain:workflow:pr-comment-resolver
- Prompt: [smoke test prefix] How would you approach resolving this PR comment: "This function is too long, please extract the validation logic into a separate helper." Provide 2-3 bullet points. Keep response under 200 words.

## Collect Results

Wait for all 8 agents to complete. For each agent, determine:
- **PASS**: Agent completed, output is non-empty (> 50 chars), output does not contain "error" stack traces
- **FAIL**: Agent errored, output is empty, or output contains error traces

## Report

Output a markdown results table:

```
## Smoke Test Results

| # | Agent | Category | Status | Notes |
|---|-------|----------|--------|-------|
| 1 | fd-quality | review/quality | PASS/FAIL | [brief note] |
| 2 | fd-architecture | review/architecture | PASS/FAIL | [brief note] |
| 3 | fd-performance | review/performance | PASS/FAIL | [brief note] |
| 4 | fd-safety | review/safety | PASS/FAIL | [brief note] |
| 5 | plan-reviewer | review/plan | PASS/FAIL | [brief note] |
| 6 | agent-native-reviewer | review/agent-native | PASS/FAIL | [brief note] |
| 7 | best-practices-researcher | research | PASS/FAIL | [brief note] |
| 8 | pr-comment-resolver | workflow | PASS/FAIL | [brief note] |

**Result: N/8 passed.**
```

## Cleanup

After reporting, delete any files agents may have written to `docs/research/smoke-test-*.md`.

If all 8 passed, end with: "All smoke tests passed."
If any failed, end with: "SMOKE TEST FAILURE: N agents failed." and list which ones.
