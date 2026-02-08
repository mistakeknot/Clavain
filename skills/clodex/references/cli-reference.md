# Codex CLI Quick Reference

| Flag | Purpose |
|------|---------|
| `-C <DIR>` | Working directory (required) |
| `-s <MODE>` | `read-only`, `workspace-write`, `danger-full-access` |
| `-o <FILE>` | Save agent's final message |
| `-m <MODEL>` | Override model |
| `-i <FILE>` | Attach image (repeatable) |
| `--add-dir <DIR>` | Write access to additional directories |
| `--full-auto` | Shortcut for `-s workspace-write` |

**Resume**: `codex exec resume --last "follow-up"` or `codex exec resume <SESSION_ID> "follow-up"`
