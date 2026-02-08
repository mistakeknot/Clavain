# Split Mode (Fallback)

When the megaprompt approach fails (agent goes off-track, verification fails twice), fall back to split mode with separate agents for each phase:

1. **Explore agent** (read-only sandbox): Investigate the code area, identify exact files and lines, report findings
2. **Implement agent** (workspace-write sandbox): Make the change based on explore findings, run build
3. **Verify agent** (read-only sandbox): Run tests, review diff, report verdict

Claude reads each agent's output between steps and adjusts the next agent's prompt accordingly. This gives more control at the cost of 3x dispatch overhead.

## When to Use
- Megaprompt agent failed twice on the same task
- Task requires human-in-the-loop judgment between explore and implement
- Complex refactoring where explore findings may change the implementation approach
