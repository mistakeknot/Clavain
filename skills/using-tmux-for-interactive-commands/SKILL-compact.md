# Using tmux for Interactive Commands (compact)

Run interactive CLI tools through detached tmux sessions so they can be controlled programmatically.

## Use Cases

Use for editors, REPLs, interactive git, and full-screen terminal tools.
Do not use for normal one-shot commands or stdin-friendly commands.

## Core Workflow

1. Start a detached session with the interactive command.
2. Wait briefly for startup (usually 100-500ms).
3. Send input with `tmux send-keys`.
4. Capture visible output with `tmux capture-pane -p`.
5. Repeat send/capture until complete.
6. Kill the session to avoid orphans.

## Quick Commands

```bash
tmux new-session -d -s <name> <command>
tmux new-session -d -s <name> -c <workdir> <command>
tmux send-keys -t <name> 'text' Enter
tmux send-keys -t <name> Escape
tmux capture-pane -t <name> -p
tmux list-sessions
tmux kill-session -t <name>
```

## Key Rules

- Use tmux key names (`Enter`, `Escape`, `C-c`), not escape sequences like `\n`.
- Separate text and key presses into distinct `send-keys` arguments.
- Capture after each major action to confirm current state before continuing.
- Always clean up sessions with `kill-session`.
- If startup output is blank, increase initial wait time.

---

*For full examples (vim, Python REPL, interactive rebase), special-key details, and troubleshooting, read SKILL.md.*
