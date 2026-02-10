# Shared Contracts (referenced by launch.md and launch-codex.md)

## Output Format: Findings Index

All agents (Task-dispatched or Codex-dispatched) produce the same output format:

### Agent Output File Structure

Each agent writes to `{OUTPUT_DIR}/{agent-name}.md` with this structure:

1. **Findings Index** (first block):
   ```
   ### Findings Index
   - SEVERITY | ID | "Section Name" | Title
   - ...
   Verdict: safe|needs-changes|risky
   ```

2. **Prose sections** (after Findings Index):
   - Summary (3-5 lines)
   - Issues Found (numbered, with severity)
   - Improvements Suggested (numbered, with rationale)
   - Overall Assessment (1-2 sentences)

3. **Zero-findings case**: Empty Findings Index with just header + Verdict line.

## Completion Signal

- Agents write to `{OUTPUT_DIR}/{agent-name}.md.partial` during work
- Add `<!-- flux-drive:complete -->` as the last line
- Rename `.md.partial` to `.md` as the final action
- Orchestrator detects completion by checking for `.md` files (not `.partial`)

## Error Stub Format

When an agent fails after retry:
```
### Findings Index
Verdict: error

Agent failed to produce findings after retry. Error: {error message}
```

## Prompt Trimming Rules

Before including an agent's system prompt in the task prompt, strip:
1. All `<example>...</example>` blocks (including nested `<commentary>`)
2. Output Format sections (titled "Output Format", "Output", "Response Format")
3. Style/personality sections (tone, humor, directness)

Keep: role definition, review approach/checklist, pattern libraries, language-specific checks.

**Scope**: Trimming applies to Project Agents (manual paste) and Codex AGENT_IDENTITY sections. Plugin Agents load system prompts via `subagent_type` — the orchestrator cannot strip those.

## Monitoring Contract

After dispatching agents, poll for completion:
- Check `{OUTPUT_DIR}/` for `.md` files every 30 seconds
- Report each completion with elapsed time
- Report running count: `[N/M agents complete]`
- Timeout: 5 minutes (Task), 10 minutes (Codex)
- After timeout, report pending agents
