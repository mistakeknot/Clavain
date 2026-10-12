# Hooks

`hooks/hooks.json` registers hooks on **6** events: `UserPromptSubmit`,
`SessionStart`, `PreToolUse`, `PostToolUse`, `Stop` and `SessionEnd`.

Registered entries per event: `UserPromptSubmit` 1, `SessionStart` 1,
`PreToolUse` 4, `PostToolUse` 6, `Stop` 1, `SessionEnd` 1. The `hooks/` directory holds **43** shell scripts; some are
libraries (`lib-*.sh`) sourced by the registered hooks.
