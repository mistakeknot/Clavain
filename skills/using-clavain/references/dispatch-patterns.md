# Agent Dispatch Patterns

## Concurrent Agent Budget

Launch at most **3-4 background agents concurrently** (stability limit — sessions freeze beyond this). For larger batches, dispatch in rounds of 3, wait for completion, then dispatch the next round.

## File Indirection (Context Optimization)

Full agent prompts inlined in `Task()` calls consume ~3K chars each in parent context. For multi-agent dispatch, write prompts to files first:

```
# Write prompt file (doesn't enter LLM context as tool_use content)
Write /tmp/flux-dispatch-{ts}/fd-architecture.md: [full prompt]

# Task call is minimal (~200 chars vs ~3K)
Task(fd-architecture, run_in_background=true):
  "Read and execute /tmp/flux-dispatch-{ts}/fd-architecture.md"
```

### Shared + Delta Pattern

For agents sharing boilerplate (output format, document reference, domain context):

```
Write /tmp/flux-dispatch-{ts}/shared-context.md:
  - Output format contract
  - Document reference path
  - Project domain context

Write /tmp/flux-dispatch-{ts}/fd-architecture-delta.md:
  "Focus: architecture boundaries, coupling, module design"
```

Task prompt: `"Read /tmp/.../shared-context.md then /tmp/.../fd-architecture-delta.md. Execute."`

This drops total dispatch context for 7 agents from ~28K to ~4K chars.

## In-Flight Agent Detection

When starting a session, Clavain automatically detects background agents from previous sessions that may still be running. Check the session context for "In-flight agents" warnings before launching similar work.

To manually check for running agents:
- Look for `system-reminder` messages mentioning agent progress
- Read first line of agent output files to identify their task

## Dispatch Checklist

1. Check for in-flight agents from previous sessions
2. Write prompts to temp files (file indirection)
3. Dispatch in rounds of 3-4 agents max
4. Wait for round completion before next round
5. Collect and synthesize results
