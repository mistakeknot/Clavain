# Research: Write Full Setup Guide

## Task
Create `/home/mk/projects/Demarch/docs/guide-full-setup.md` — a complete setup guide for users who want the full Demarch platform including Go services and TUI tools.

## Analysis

### Target Audience
Users who want the complete Demarch platform: Clavain agent rig, Interverse plugins, Go core services (Intercore, Intermute), Autarch TUI apps, and optional Oracle cross-AI review.

### Structure Decisions
The guide follows a progressive installation sequence:
1. **Clavain + Interverse** (core agent rig + plugins) — the foundation everything else builds on
2. **Beads CLI** — git-native issue tracker, powers work discovery
3. **Intercore** — orchestration kernel (`ic` binary), required for runs/dispatch/gates
4. **Intermute** (optional) — multi-agent coordination, only needed for concurrent sessions
5. **Autarch** (optional) — TUI interfaces (Bigend, Gurgeh, Coldwine, Pollard)
6. **Oracle** (optional) — cross-AI review via GPT-5.2 Pro

### Key Findings
1. **Prerequisites are realistic**: Go 1.24+, Node.js 20+, Python 3.10+, jq, and optionally tmux. These match what the actual build systems require based on project AGENTS.md and go.mod files.
2. **Verification via `/clavain:doctor`**: The health check command validates the entire stack — plugin loading, MCP connections, Beads availability, companion plugins, and hooks.
3. **Progressive complexity**: Steps 1-3 are required, steps 4-6 are optional, letting users choose their depth of investment.

### Cross-References
- Links to `guide-power-user.md` and `guide-contributing.md` for next steps
- Oracle setup defers to the external oracle-cli repo for detailed instructions
- Beads initialization is per-project (`bd init`)

## Output
Written to `/home/mk/projects/Demarch/docs/guide-full-setup.md` — 6 setup steps, verification section, and next-steps links.
