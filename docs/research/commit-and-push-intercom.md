# Commit and Push: Intercom

**Date:** 2026-02-23
**Repo:** `/home/mk/projects/Demarch/apps/intercom`
**Remote pushed to:** `intercom` (https://github.com/mistakeknot/Intercom.git)

## Summary

Created 6 logically grouped commits for all pending changes in the Intercom repo and pushed to the `intercom` remote on `main`.

## Git Status Before

```
 M .clavain/interspect/interspect.db
 M AGENTS.md
 M container/agent-runner/src/index.ts
 M container/codex-runner/src/index.ts
 M container/gemini-runner/src/index.ts
 M container/shared/executor.ts
 M container/shared/ipc-input.ts
 M container/shared/ipc-tools.ts
 M container/shared/protocol.ts
 M container/shared/session-base.ts
 M container/shared/system-prompt.ts
 D docs/intercom-roadmap.md
 M src/channels/telegram.ts
 M src/channels/whatsapp.ts
 M src/config.ts
 M src/container-runner.ts
 M src/container-runtime.ts
 M src/db.ts
 M src/index.ts
 M src/mount-security.ts
 M src/router.ts
 M src/types.ts
 M src/whatsapp-auth.ts
?? docs/roadmap.md
?? src/stream-accumulator.ts
?? src/summarizer.ts
```

## Commits Created

| # | SHA | Message | Files |
|---|-----|---------|-------|
| 1 | `6d192be` | feat: update shared protocol, executor, and IPC modules | 6 files (container/shared/*) |
| 2 | `f2759be` | feat: update agent, codex, and gemini runners | 3 files (container/*/src/index.ts) |
| 3 | `3e01d1f` | feat: update host-side channels, runtime, and routing | 11 files (src/*) |
| 4 | `6ba9366` | feat: add stream accumulator and summarizer modules | 2 files (new: src/stream-accumulator.ts, src/summarizer.ts) |
| 5 | `caf05a4` | docs: update AGENTS.md and interspect data | 2 files (AGENTS.md, .clavain/interspect/interspect.db) |
| 6 | `363144b` | docs: update roadmap docs | 2 files (deleted docs/intercom-roadmap.md, new docs/roadmap.md) |

## Push Details

- **Initial attempt:** `git push origin main` failed with 403 — `origin` points to upstream `qwibitai/nanoclaw.git` which `mistakeknot` doesn't have write access to.
- **Resolution:** Pushed to `intercom` remote instead (`mistakeknot/Intercom.git`), which succeeded.
- **Result:** `8671dd3..363144b  main -> main` — all 6 commits pushed successfully.

## Remotes

```
intercom  https://github.com/mistakeknot/Intercom.git (fetch/push)  <- fork, writable
origin    https://github.com/qwibitai/nanoclaw.git (fetch/push)     <- upstream, read-only
```

## Change Statistics

- **Commit 1 (shared):** 15 insertions, 6 deletions
- **Commit 2 (runners):** 78 insertions, 6 deletions
- **Commit 3 (host-side):** 333 insertions, 54 deletions
- **Commit 4 (new modules):** 287 insertions (new files)
- **Commit 5 (docs/data):** 2 insertions
- **Commit 6 (roadmap):** 11 insertions, 36 deletions

**Total:** ~726 insertions, ~102 deletions across 26 files.
