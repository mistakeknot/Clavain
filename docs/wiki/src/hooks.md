# Hooks

`hooks/hooks.json` registers hooks on **6** events: `UserPromptSubmit`,
`SessionStart`, `PreToolUse`, `PostToolUse`, `Stop` and `SessionEnd`.

Registered entries per event: `PreToolUse` 4, `PostToolUse` 6, and 1 each for
the other four. The `hooks/` directory holds **43** shell scripts; most are
libraries (`lib-*.sh`) sourced by the registered hooks.
