# Research: Interlock F8 Commands Plan

## Context Gathered

### Command Format Conventions (from existing plugins)

**Frontmatter:** All commands use YAML frontmatter with `name`, `description`, and optional `argument-hint`.

**Companion plugin commands** (interpath, interwatch) are simple markdown docs that either:
1. Delegate to a skill via `Use the Skill tool to invoke ...` (interpath pattern)
2. Run bash scripts and display results (interwatch pattern)

**Clavain commands** (setup.md, init.md, doctor.md) are more detailed with multi-step execution instructions including inline bash.

For interlock commands, the pattern should follow Clavain's `init.md` / `doctor.md` style since they involve bash script execution, flag file management, and formatted output.

### Key Design Decisions

1. **Flag file:** `~/.config/clavain/intermute-joined` — controls whether SessionStart hook registers agent
2. **Agent name file:** `~/.config/clavain/intermute-agent-name` — persists chosen name
3. **Name precedence:** `--name <label>` > tmux pane title > `claude-${CLAUDE_SESSION_ID:0:8}`
4. **Scripts:** Commands delegate to `scripts/interlock-register.sh`, `scripts/interlock-cleanup.sh`
5. **intermute API:** `/api/agents` (GET/POST), `/api/reservations` (GET), `/health` (GET)
6. **Connection:** Unix socket at `/var/run/intermute.sock` (fallback to TCP)
7. **systemd unit:** `intermute.service`
8. **Binary location:** TBD (likely `/usr/local/bin/intermute` or `~/.local/bin/intermute`)

### PRD Acceptance Criteria (F8)
- `/interlock:join [--name <label>]` -- registers agent, sets onboarding flag, shows active agents
- `/interlock:leave` -- releases all reservations, deregisters, removes onboarding flag
- `/interlock:status` -- lists active agents with reservations, heartbeat, human-readable names
- `/interlock:setup` -- self-installing: checks/downloads intermute binary, creates systemd unit, starts service
- Agent name precedence: user-provided `--name` label > tmux pane title > `claude-{session:0:8}` fallback
- `/interlock:join` creates `~/.config/clavain/intermute-joined` flag; `/interlock:leave` removes it
- `/interlock:status` shows `(name, agent-id)` pairs to disambiguate name collisions

### File Locations (target repo: /root/projects/interlock/)
- `commands/join.md`
- `commands/leave.md`
- `commands/status.md`
- `commands/setup.md`

### Scripts Referenced by Commands
- `scripts/interlock-register.sh` — handles agent registration with intermute API
- `scripts/interlock-cleanup.sh` — handles reservation release and deregistration

### Connection Logic Pattern
Commands need to detect intermute connectivity. Pattern from brainstorm:
```bash
INTERMUTE_SOCKET="${INTERMUTE_SOCKET:-/var/run/intermute.sock}"
INTERMUTE_URL="${INTERMUTE_URL:-http://localhost:7890}"

# Try socket first, fall back to TCP
if [ -S "$INTERMUTE_SOCKET" ]; then
    CURL_ARGS="--unix-socket $INTERMUTE_SOCKET http://localhost"
else
    CURL_ARGS="$INTERMUTE_URL"
fi
```

### Existing Plan Format
From `2026-02-14-interlock-f1-circuit-breaker.md`:
- Header with goal, architecture, tech stack, bead reference
- Numbered tasks with file paths, steps, and acceptance criteria checkboxes
- Pre-flight and post-execution checklists

F8 is simpler (markdown docs, not Go code) so the plan should be more concise.

## Key Findings

1. **4 command files needed**, each following the YAML frontmatter + markdown instruction pattern seen in existing companions
2. **join.md is the most complex** — name resolution logic, script delegation, flag file creation, agent listing
3. **setup.md is self-contained** — binary download, systemd unit creation, service start, health verification
4. **Commands delegate to scripts** (`interlock-register.sh`, `interlock-cleanup.sh`) for actual API interaction — commands describe the workflow Claude should follow
5. **Graceful degradation** throughout — commands should handle intermute being unavailable
