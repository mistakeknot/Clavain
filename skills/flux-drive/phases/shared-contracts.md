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

## Diff Slicing Contract

When `INPUT_TYPE = diff` and `slicing_eligible: yes` (diff >= 1000 lines), the orchestrator applies soft-prioritize slicing per `config/flux-drive/diff-routing.md`. This contract defines how slicing interacts with other phases.

### Agent Content Access

| Agent Type | Content Received |
|------------|-----------------|
| Cross-cutting (fd-architecture, fd-quality) | Full diff — no slicing |
| Domain-specific (fd-safety, fd-correctness, fd-performance, fd-user-product) | Priority hunks (full) + context summaries (one-liner per file) |
| Oracle (Cross-AI) | Full diff — external tool, no slicing control |
| Project Agents (.claude/agents/) | Full diff — cannot assume routing awareness |

### Slicing Metadata

Each sliced agent prompt includes a metadata line:
```
[Diff slicing active: P priority files (L1 lines), C context files (L2 lines summarized)]
```

The orchestrator tracks per-agent access as a mapping for use during synthesis:
```
slicing_map:
  fd-safety: {priority: [file1, file2], context: [file3, file4], mode: sliced}
  fd-architecture: {priority: all, context: none, mode: full}
  ...
```

### Synthesis Implications

- **Convergence adjustment**: When counting how many agents flagged the same issue, do NOT count agents that only received context summaries for the file in question. A finding from 2/3 agents that saw the file in full is higher confidence than 2/6 total agents.
- **Out-of-scope findings**: If an agent flags an issue in a file it received only as context summary, tag the finding as `[discovered beyond sliced scope]`. This is valuable — it means the agent inferred the issue from file name/stats alone.
- **Slicing disagreements**: Agents may note "Request full hunks: {filename}" in their findings. The orchestrator should track these requests. If 2+ agents request full hunks for the same context file, note it as a routing improvement suggestion in the synthesis report.
- **No penalty for silence**: Do NOT penalize an agent for not flagging issues in files it received only as context summaries. Silence on context files is expected, not a gap.

## Monitoring Contract

After dispatching agents, poll for completion:
- Check `{OUTPUT_DIR}/` for `.md` files every 30 seconds
- Report each completion with elapsed time
- Report running count: `[N/M agents complete]`
- Timeout: 5 minutes (Task), 10 minutes (Codex)
- After timeout, report pending agents
