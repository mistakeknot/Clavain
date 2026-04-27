---
name: using-tmux-for-interactive-commands
description: Use for interactive CLI tools (vim, git rebase -i, REPLs) that need a real terminal — drives tmux detached sessions via send-keys/capture-pane.
---

# Using tmux for Interactive Commands

Interactive CLI tools (vim, REPLs, interactive git, etc.) require a real terminal — use tmux detached sessions controlled via `send-keys`/`capture-pane`.

## When to use

**Use:** vim/nano, REPLs (Python, Node), `git rebase -i`, `git add -p`, full-screen TUIs, readline-dependent commands.
**Don't use:** non-interactive commands, commands accepting stdin redirection.

## Quick Reference

| Task | Command |
|------|---------|
| Start | `tmux new-session -d -s <name> <cmd>` |
| Send input | `tmux send-keys -t <name> 'text' Enter` |
| Capture | `tmux capture-pane -t <name> -p` |
| Stop | `tmux kill-session -t <name>` |

## Core Pattern

```bash
tmux new-session -d -s edit vim file.txt
sleep 0.3  # wait for init
tmux send-keys -t edit 'i' 'Hello World' Escape ':wq' Enter
tmux capture-pane -t edit -p
tmux kill-session -t edit
```

## Special Keys

`Enter`, `Escape`, `C-c`, `C-x`, `Up`, `Down`, `Left`, `Right`, `Space`, `BSpace`

## With working directory

```bash
tmux new-session -d -s rebase -c /repo/path git rebase -i HEAD~3
```

## Common Patterns

**Python REPL:**
```bash
tmux new-session -d -s py python3 -i
tmux send-keys -t py 'import math' Enter
tmux send-keys -t py 'print(math.pi)' Enter
tmux capture-pane -t py -p
tmux kill-session -t py
```

**Interactive git rebase:**
```bash
tmux new-session -d -s rebase -c /repo git rebase -i HEAD~3
sleep 0.5
tmux capture-pane -t rebase -p
tmux send-keys -t rebase ':wq' Enter
```

## Gotchas

- **Blank capture:** Add `sleep 0.3` after `new-session` before first capture
- **Command not executed:** Must send `Enter` explicitly as a separate argument
- **Wrong key names:** Use `Enter` not `\n`; `Escape` not `\e`
- **Orphaned sessions:** Always `tmux kill-session -t <name>` when done
