---
name: agent-mail-coordination
description: Use when multiple agents work on the same codebase, when you need file reservations to avoid conflicts, or when coordinating work across sessions or repositories via MCP Agent Mail
---

# Agent Mail Coordination

## Overview

MCP Agent Mail provides messaging, file reservations, and coordination between AI agents working on the same or related codebases. Use it when multiple agents are active, when you need to signal file edit intent, or when coordinating across repositories.

**Core principle:** Reserve before editing, communicate through threads, link conversations to beads issues.

## When to Use

| Use Agent Mail when... | Don't bother when... |
|------------------------|----------------------|
| Multiple agents are active on a project | Solo agent, single session |
| Editing shared files others might touch | Working on isolated files |
| Coordinating cross-repo work (frontend + backend) | Single repo, single agent |
| Need audit trail of agent decisions | Decisions are ephemeral |
| Parallel agents dispatched via `dispatching-parallel-agents` | Sequential single-agent work |

## Session Startup

**Automatic**: Clavain's SessionStart hook auto-registers with Agent Mail when the server is running. No manual setup needed.

**Manual** (if auto-registration didn't run):
```
macro_start_session(
  project_path="/path/to/project",
  program="claude-code",
  model="claude-opus-4-6",
  initial_message="Starting work on [task description]"
)
```

## Beads Integration

When working on a beads issue, use the issue ID as the Agent Mail `thread_id`. This links messages and file reservations to the issue tracker:

```
# When claiming an issue: reserve files and announce
bd update <issue-id> --status=in_progress
file_reservation_paths(paths=["affected/files"], ttl=3600, exclusive=true)
send_message(to=["*"], subject="Claiming <issue-id>", thread_id="<issue-id>")

# When done: release and close
release_file_reservations()
bd close <issue-id>
```

## File Reservations

**Reserve before editing shared files.** Reservations are advisory leases that signal edit intent.

```
file_reservation_paths(
  paths=["src/auth/*.go", "pkg/tui/app.go"],
  ttl=3600,
  exclusive=true
)
```

- **TTL**: How long the reservation lasts (seconds, default 3600)
- **Exclusive**: Whether conflicts should be reported (default true)
- **Stale cleanup**: Auto-released after 1800s of inactivity
- **Advisory**: Conflicts are reported but reservations still granted — the system trusts agents to coordinate

**Release when done:**
```
release_file_reservations()
```

**Pre-commit guard** (optional): Install a git hook that blocks commits conflicting with another agent's exclusive reservation:
```
install_precommit_guard()
```

## Messaging

### Sending Messages

```
send_message(
  to=["AgentName"],
  subject="Completed auth refactor",
  body="Refactored auth middleware. Changed signature of `Authenticate()` — you'll need to update callers in your handler code.",
  importance="normal",
  thread_id="bd-a1b2"
)
```

**Link threads to beads issues:** Use the beads issue ID (e.g., `bd-a1b2`) as `thread_id` to connect conversations to tracked work.

### Checking Inbox

```
fetch_inbox(limit=10, urgent_only=false)
```

Check inbox at session start and periodically during long work.

### Thread Summaries

For long threads, get an AI summary of decisions and action items:
```
summarize_thread(thread_id="bd-a1b2")
```

## Coordination Patterns

### Same Repository, Multiple Agents

1. Both agents call `macro_start_session` with the same project path
2. Each reserves their file paths before editing
3. Communicate via threaded messages with shared `thread_id`
4. Release reservations when done with each file group

### Cross-Repository (Frontend + Backend)

1. Register under separate project paths
2. Establish contact: `macro_contact_handshake`
3. Share a `thread_id` (beads issue ID) for the feature
4. Message each other about API contract changes

### Parallel Subagent Dispatch

When using `clavain:dispatching-parallel-agents`:
1. Controller reserves files for each subagent's work area
2. Dispatch subagents with instructions to check inbox first
3. Subagents message controller when done or blocked
4. Controller releases reservations after collecting results

## Contact Policies

Each agent has a contact policy controlling who can message them:

| Policy | Behavior |
|--------|----------|
| `open` | Accept any message |
| `auto` (default) | Auto-allow with shared context, otherwise require contact request |
| `contacts_only` | Require approved contact first |
| `block_all` | Reject all new contacts |

For most workflows, leave at `auto`. Use `contacts_only` for agents with focused responsibilities that shouldn't be interrupted.

## Integration

**Pairs with:**
- `beads-workflow` — Use beads issue IDs as Agent Mail `thread_id` values
- `dispatching-parallel-agents` — File reservations prevent parallel agent conflicts
- `subagent-driven-development` — Coordinate implementer/reviewer subagent handoffs
- `oracle-review` — Share Oracle results across agents via Agent Mail messages

## Red Flags

- **Editing without reserving** when other agents are active
- **Ignoring inbox** at session start — check for messages from other agents
- **Orphaned reservations** — always release when done or session ends
- **Skipping thread_id** — unthreaded messages become impossible to follow
