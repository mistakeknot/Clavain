Codex tool adaptation: read skills/files with available file or shell tools;
search with `rg`; edit with `apply_patch`; run checks with the available terminal.
Claude slash commands are not shell commands or Codex APIs. Use installed skill
paths and callable tools, verifying command support before execution. Track work
with the repository's tracker; outside a project keep lightweight in-session state.
Delegate only when authorized and supported; otherwise execute in the main thread
and batch independent tool calls. Use the runtime's question tools only for missing
information or required approval, honoring existing user authorization.
