# Research: Upstream Repo States

**Date:** 2026-02-10  
**Purpose:** Assess current state of all upstream repos Clavain integrates with, identify sync gaps, and flag action items.

---

## Summary

Clavain tracks **7 upstream repos** via `upstreams.json`. Three are fully synced (superpowers, superpowers-lab, superpowers-dev), while four have new upstream commits not yet pulled into Clavain. The most significant gaps are in **beads** (258 commits behind — but most are core app changes, not plugin-relevant), **mcp-agent-mail** (21 commits with substantial new features), and **oracle** (17 commits with important bug fixes).

No upstream repos exist as local clones under `/root/projects/`. The sync system relies on GitHub API + the `upstreams.json` state file.

---

## Upstream Repo Status

### 1. superpowers (obra/superpowers)

| Field | Value |
|-------|-------|
| **URL** | https://github.com/obra/superpowers.git |
| **Last synced commit** | `a98c5df` |
| **Commits behind** | **0** (fully synced) |
| **Local clone** | None |
| **Latest upstream commits** | Release v4.2.0: Windows fixes, Codex native skill discovery |

**Status:** Fully synced. No action needed.

---

### 2. superpowers-lab (obra/superpowers-lab)

| Field | Value |
|-------|-------|
| **URL** | https://github.com/obra/superpowers-lab.git |
| **Last synced commit** | `897eebf` |
| **Commits behind** | **0** (fully synced) |
| **Local clone** | None |
| **Latest upstream commits** | Bump version to 0.3.0, Add slack-messaging skill |

**Status:** Fully synced. No action needed.

---

### 3. superpowers-dev (obra/superpowers-developing-for-claude-code)

| Field | Value |
|-------|-------|
| **URL** | https://github.com/obra/superpowers-developing-for-claude-code.git |
| **Last synced commit** | `74afe93` |
| **Commits behind** | **0** (fully synced) |
| **Local clone** | None |
| **Latest upstream commits** | Release v0.3.1: Fix POSIX compatibility in polyglot wrapper |

**Status:** Fully synced. No action needed.

---

### 4. compound-engineering (EveryInc/compound-engineering-plugin)

| Field | Value |
|-------|-------|
| **URL** | https://github.com/EveryInc/compound-engineering-plugin.git |
| **Last synced commit** | `04ee7e4` |
| **Commits behind** | **4** |
| **Local clone** | None |
| **basePath** | `plugins/compound-engineering` |

**New commits since last sync:**
```
4f4873f Update create-agent-skills to match 2026 official docs, add /triage-prs command
f744b79 Reduce context token usage by 79% — fix silent component exclusion (#161)
f3b7d11 Merge branch 'main' of compound-engineering-plugin
e8f3bbc refactor(skills): update dspy-ruby skill to DSPy.rb v0.34.3 API (#162)
```

**Relevance to Clavain:**
- `4f4873f` — Updates `create-agent-skills` skill (mapped to Clavain) and adds `/triage-prs` command (new, not in fileMap)
- `f744b79` — Context token reduction may affect mapped skills/agents
- `e8f3bbc` — dspy-ruby skill update (NOT mapped to Clavain — no action)

**Action:** Sync needed. The `create-agent-skills` update and potential `/triage-prs` command are relevant.

---

### 5. beads (steveyegge/beads)

| Field | Value |
|-------|-------|
| **URL** | https://github.com/steveyegge/beads.git |
| **Last synced commit** | `eb1049b` |
| **Commits behind** | **258** |
| **Local clone** | None |
| **Repo description** | "Beads - A memory upgrade for your coding agent" |
| **Last pushed** | 2026-02-10 (today, very active) |

**Latest upstream commits (sample):**
```
d6040bd Remove dead MarkIssueDirty from compact test stubs
ac0d53d Fix routing tests: close rig store before routing opens it
331d9be Add issue existence checks to Dolt AddDependency
b7c5dfd Add cycle detection to Dolt AddDependency
3ef2845 Remove dead dirty_issues tracking from Dolt storage layer
```

**Relevance to Clavain:**
The beads repo is very actively developed (258 commits in ~4 days). However, the vast majority of these commits are to the core beads application (Go code, Dolt storage, routing, tests). Clavain only maps from `claude-plugin/skills/beads/` which contains:
- `SKILL.md`
- `README.md`
- `CLAUDE.md`
- `resources/*`
- `adr/*`

**The key question is whether the `claude-plugin/skills/beads/` directory changed in those 258 commits.** Given the commit messages are all about core app internals (Dolt storage, routing tests, compact stubs), it is likely that few or none of the 258 commits touched the plugin skill files.

**Action:** Sync check needed, but likely low-impact. Should verify whether `claude-plugin/skills/beads/` files changed using `gh api` diff.

---

### 6. oracle (steipete/oracle)

| Field | Value |
|-------|-------|
| **URL** | https://github.com/steipete/oracle.git |
| **Last synced commit** | `5c053e2` |
| **Commits behind** | **17** |
| **Local clone** | None |

**New commits since last sync:**
```
886e339 fix: prevent unbounded growth of OpenRouter catalog cache
75d0974 fix: abort polling loop when evaluation wins race condition
d5cec98 fix: ensure browser-side observer/interval cleanup on all exit paths
6e48e1e fix: close browser tabs after successful response capture
a3a7dc7 chore(deps): update dependencies
ff81f46 Add browser auto-reattach and shared Chrome safety
8f20497 fix: harden browser auto-reattach (#87)
45901a0 fix(browser): resolve TDZ crash in markdown fallback extractor
89bbc41 fix: avoid TDZ in markdown fallback extractor (#90)
f18f827 fix: make browser response poller abort-safe
1b88d6d fix: cap OpenRouter catalog cache size
1df6385 Merge pull request #77 from bindscha/main
b0008e8 what
aa61556 fix: honor --no-wait for Commander --no- flags (#84)
445f590 docs: align changelog for 0.8.6
d08d7fd chore(release): 0.8.6
5f3aef5 docs: prep changelog for 0.8.7
```

**Relevance to Clavain:**
Clavain maps several oracle files including `skills/oracle/SKILL.md`, `README.md`, and various docs files. The 17 commits include:
- Important bug fixes (TDZ crashes, cache unbounded growth, polling race conditions)
- Browser reliability improvements (auto-reattach, tab cleanup)
- Updated docs/changelogs (directly mapped files)
- Version bumps (0.8.6, 0.8.7)

**Action:** Sync recommended. The doc changes and SKILL.md updates will improve Clavain's interpeer reference material.

---

### 7. mcp-agent-mail (Dicklesworthstone/mcp_agent_mail)

| Field | Value |
|-------|-------|
| **URL** | https://github.com/Dicklesworthstone/mcp_agent_mail.git |
| **Last synced commit** | `9992244` |
| **Commits behind** | **21** |
| **Local clone** | `/root/mcp_agent_mail` (systemd service working dir, very old — at `18fa27f`) |

**New commits since last sync:**
```
d9ed724 chore(beads): add beads for issue #80 feature ideas
1764d2d chore(beads): sync issue tracker
e3dbc6b chore(beads): sync issue tracker
ec318e1 chore(beads): refine all 3 feature beads with deps, logging, and migration
542995c fix(http): return 404 for OAuth well-known endpoints when OAuth disabled
a188fdd chore(beads): track tool reservation namespace and Discord community features
32afeab feat(identity): add persistent window-based agent identity system (bd-1tz)
0db6b1b chore(beads): close bd-1tz after implementation
e9424be fix(identity): race condition and redundant DB lookups in window identity
b4ad9fc feat(messaging): add broadcast + topic threads for all-agent visibility (bd-26w)
e6fad41 chore(beads): close bd-26w after implementation
2acd89a chore(beads): mark bd-1ia as in_progress
ee53048 feat(summarization): add on-demand project-wide message summarization (bd-1ia)
f248e64 chore(beads): close bd-1ia after implementation
5069b3e chore(beads): sync issue tracker state
b1c2051 feat(reservations): add virtual namespace support for tool/resource reservations (bd-14z)
3e7a88b chore(beads): close bd-14z after implementation
130e3cd style: apply ruff auto-fixes
8682140 chore(beads): close bd-p6n after ruff quality gate completion
2dec7d0 chore(beads): close bd-1v5 — actionable community features implemented
061435c fix(cli): default to serve-http when no subcommand given
```

**Relevance to Clavain:**
Significant new features that may have updated SKILL.md or docs:
- **Agent identity system** — persistent window-based identities
- **Broadcast + topic threads** — all-agent visibility messaging
- **On-demand summarization** — project-wide message summaries
- **Virtual namespace reservations** — tool/resource reservation system
- **CLI fix** — default to serve-http

Many commits are beads issue tracker housekeeping, but the feature commits are substantial and likely updated the mapped docs.

**Action:** Sync strongly recommended. Major new features likely changed SKILL.md and reference docs.

**Additional note:** The local mcp-agent-mail service at `/root/mcp_agent_mail` is running (systemd active since Feb 5) but is on a very old commit (`18fa27f`). It should be updated independently of the Clavain sync.

---

## mcp-agent-mail Service Status

| Field | Value |
|-------|-------|
| **systemd unit** | `mcp-agent-mail.service` |
| **Status** | Active (running) since 2026-02-05 |
| **Working dir** | `/root/mcp_agent_mail` |
| **Command** | `uv run python -m mcp_agent_mail.cli serve-http` |
| **Health endpoint** | `http://127.0.0.1:8765/health` returns `{"detail":"Not Found"}` (no `/health` route, but server is up) |
| **Local git state** | At commit `18fa27f` — extremely far behind upstream |

---

## Sync Infrastructure

### GitHub Workflows
Clavain has extensive sync-related workflows:
- `.github/workflows/sync.yml` — Main sync workflow
- `.github/workflows/upstream-check.yml` — Check for upstream changes
- `.github/workflows/upstream-decision-gate.yml` — Approval gate
- `.github/workflows/upstream-impact.yml` — Impact analysis
- `.github/workflows/upstream-sync-issue-command.yml` — Issue-driven sync

### Local Scripts
- `scripts/upstream-check.sh` — Local upstream check
- `scripts/upstream-impact-report.py` — Impact analysis
- No `sync-upstreams.sh` found (referenced in MEMORY.md but missing)

### State File
`upstreams.json` tracks 7 upstreams with commit hashes and file mappings.

---

## Cross-Project References

Files referencing Clavain:
- `/root/projects/agent-rig/CLAUDE.md` — agent-rig has a `examples/clavain/` reference manifest
- `/root/projects/Clavain/CLAUDE.md` — self-reference
- `/root/projects/Clavain/.claude-plugin/plugin.json` — plugin manifest

---

## Action Items (Priority Order)

1. **Sync mcp-agent-mail** (21 commits, major new features) — highest priority, new capabilities for agent coordination
2. **Sync oracle** (17 commits, bug fixes + docs) — important for interpeer reliability
3. **Sync compound-engineering** (4 commits, skill updates) — moderate priority, updated skill docs
4. **Check beads diff** (258 commits but likely few plugin-relevant changes) — verify before syncing
5. **Update local mcp-agent-mail service** (`/root/mcp_agent_mail`) — running very old code
6. **Investigate missing `sync-upstreams.sh`** — MEMORY.md references it but it does not exist in `scripts/`
