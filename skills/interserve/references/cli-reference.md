# Codex CLI Quick Reference

**IMPORTANT**: Always use `codex exec`, never bare `codex`. The top-level `codex` command launches interactive mode and does not accept exec flags.

## Codex CLI Flags

| Flag | Purpose |
|------|---------|
| `-C <DIR>` | Working directory (required) |
| `-s <MODE>` | `read-only`, `workspace-write`, `danger-full-access` |
| `-o <FILE>` | Save agent's final message |
| `-m <MODEL>` | Override model |
| `-i <FILE>` | Attach image (repeatable) |
| `--add-dir <DIR>` | Write access to additional directories |
| `--full-auto` | Convenience flag: sets `-s workspace-write` (boolean, no value) |
| `-c key=value` | Override config values (e.g., `-c model="o3"`) |

## dispatch.sh Flags (on top of Codex CLI)

| Flag | Purpose |
|------|---------|
| `--tier <fast\|deep>` | Resolve model from `config/routing.yaml` dispatch section (mutually exclusive with `-m`) |
| `--phase <NAME>` | Sprint phase context (for future phase-aware dispatch) |
| `--inject-docs[=SCOPE]` | Prepend CLAUDE.md/AGENTS.md to prompt |
| `--name <LABEL>` | Label for `{name}` substitution in output path |
| `--prompt-file <FILE>` | Read prompt from file instead of positional arg |
| `--template <FILE>` | Assemble prompt from template + task description |
| `--dry-run` | Print command without executing |

**Resume**: `codex exec resume --last "follow-up"` or `codex exec resume <SESSION_ID> "follow-up"`

## Deprecated / Invalid Flags

These flags do NOT exist in the current Codex CLI and will cause errors:

| Wrong | Correct |
|-------|---------|
| `codex --approval-mode full-auto` | `codex exec --full-auto` |
| `codex --approval-mode ...` | Flag removed entirely — use `--full-auto` or `-s <MODE>` |
| `codex -q` / `codex --quiet` | No quiet flag exists — Codex writes to stderr by default |
| `codex --file <FILE>` | Use `--prompt-file` (dispatch.sh) or pass prompt as positional arg |
