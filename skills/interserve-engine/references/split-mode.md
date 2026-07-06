# Split Mode (Fallback)

When the megaprompt approach fails (agent goes off-track, verification fails twice), fall back to split mode with separate agents for each phase:

1. **Explore agent** (`--tier fast` + `-s read-only`): Investigate the code area, identify exact files and lines, report findings
2. **Implement agent** (`--tier deep` + `-s workspace-write`): Make the change based on explore findings, run build
3. **Verify agent** (`--tier fast` + `-s read-only`): Run tests, review diff, report verdict

When Clavain interserve mode is enabled (`.claude/clodex-toggle.flag` exists) and `CLAVAIN_DISPATCH_PROFILE=interserve` is set, fast/deep map to `-xhigh` variants in `config/routing.yaml` (dispatch section).

Claude reads each agent's output between steps and adjusts the next agent's prompt accordingly. This gives more control at the cost of 3x dispatch overhead — but the fast tier on explore/verify phases significantly reduces wall-clock time.

## When to Use
- Megaprompt agent failed twice on the same task
- Task requires human-in-the-loop judgment between explore and implement
- Complex refactoring where explore findings may change the implementation approach
