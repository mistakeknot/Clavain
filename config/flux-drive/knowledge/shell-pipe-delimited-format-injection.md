---
lastConfirmed: 2026-02-12
provenance: independent
---
Shell scripts using pipe-delimited output (e.g., `title|action|path`) are vulnerable to field injection when any field contains the delimiter character. Titles, user descriptions, and file paths commonly contain `|`.

Fix: Use JSON output with `jq --arg` for safe field construction instead of pipe/tab-delimited text formats. The `jq -n -c --arg key "$value"` pattern prevents injection from any user-controlled data.

Evidence: hooks/lib-discovery.sh — originally designed with pipe-delimited output, changed to JSON before implementation after fd-correctness plan review caught the risk.
Verify: grep for `IFS='|'` or `cut -d'|'` in hooks/*.sh and scripts/*.sh.
