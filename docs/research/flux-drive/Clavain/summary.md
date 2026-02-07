# Flux Drive Review Summary — Clavain

Reviewed by **6 agents** (4 codebase-aware T1, 2 generic T3) on 2026-02-07.

**All 6 agents returned verdict: needs-changes.**

The core architecture is sound — 3-layer routing (skills/agents/commands), SessionStart hook injection, and agent categorization (review/research/workflow) are well-designed. The primary issues stem from **stale documentation counts**, **broken upstream sync file mappings**, and **incomplete routing table coverage** after recent additions.

## Convergence Map

| Finding | fd-arch | fd-quality | fd-security | fd-ux | patterns | simplicity | Agents |
|---------|---------|------------|-------------|-------|----------|------------|--------|
| Stale component counts (32/24 vs documented 31/22) | P0 | P0+P0 | — | P0 | P1 | P1 | **5/6** |
| Routing table missing 7+ commands | P1 | P2 | — | P0 | P1 | — | **4/6** |
| Rails content in general-purpose agents | P2 | P1 | — | — | P1 | P1 | **4/6** |
| Three resolve-* commands near-identical | — | — | — | P1 | P1 | P1 | **3/6** |
| upstreams.json broken underscore filenames | — | P0 | — | — | — | P0 | **2/6** |
| create-agent-skills / writing-skills overlap | — | — | — | — | P1 | P0 | **2/6** |
| Dual upstream sync systems undocumented | P1 | — | — | — | — | P2 | **2/6** |
| gurgeh-plugin cross-plugin dependency | P1 | — | — | — | — | — | **1/6** |
| Agent Mail MCP no authentication | — | — | P1 | — | — | — | **1/6** |
| Supply chain risk in upstream sync | — | — | P1 | — | — | — | **1/6** |

## Key Findings (Top 8)

1. **Stale component counts everywhere** (5/6 agents). AGENTS.md, CLAUDE.md, using-clavain/SKILL.md, and plugin.json each report different numbers. Actual: 32 skills, 23 agents, 24 commands. Most docs say 31/22.

2. **Routing table missing commands** (4/6 agents). 7 of 24 commands are absent from the using-clavain routing table — users cannot discover them. Also missing 2 skills.

3. **Rails content violates general-purpose policy** (4/6 agents). `deployment-verification-agent`, `framework-docs-researcher`, `engineering-docs`, and `work.md` contain Rails-specific content despite CLAUDE.md banning it.

4. **upstreams.json has 5 broken file mappings** (2/6 agents). The compound-engineering fileMap entries use underscore filenames (`generate_command.md`) but local files use kebab-case (`generate-command.md`). Sync silently broken.

5. **agent-native-audit uses invalid skill invocation** (1/6 agents, P0). Uses `/clavain:agent-native-architecture` which is slash-command syntax on a skill — not valid.

6. **Supply chain risk in upstream sync** (1/6 agents). `sync.yml` fetches from external repos and merges via AI without adversarial content filtering. Also requests unnecessary `id-token:write` permission.

7. **~2,200 lines of redundancy** (1/6 agents, deep analysis). `create-agent-skills` + `writing-skills` = 955 lines for same topic. 3 resolve commands share 90% text. `/brainstorm` replicates skill logic instead of being a thin shim.

8. **Agent Mail MCP declared without auth** (1/6 agents). `plugin.json` hardcodes `localhost:8765` over plaintext HTTP with no bearer token.

## Issues to Address

### P0 — Critical (3 issues)

- [ ] **Stale component counts**: Update all docs to 32 skills / 23 agents / 24 commands (fd-arch P0, fd-quality P0+P0, fd-ux P0, patterns P1, simplicity P1 — 5/6)
- [ ] **Broken upstreams.json fileMap**: Fix 5 compound-engineering entries from `snake_case` to `kebab-case` (fd-quality P0, simplicity P0 — 2/6)
- [ ] **agent-native-audit broken skill invocation**: `/clavain:agent-native-architecture` is not valid syntax — fix to use Skill tool or correct reference (patterns P0 — 1/6)

### P1 — Important (11 issues)

- [ ] Add 7+ missing commands and 2 skills to using-clavain routing table (fd-arch P1, fd-quality P2, fd-ux P0, patterns P1 — 4/6)
- [ ] Scrub Rails/Ruby content from deployment-verification-agent, framework-docs-researcher, engineering-docs, work.md (fd-arch P2, fd-quality P1, patterns P1, simplicity P1 — 4/6)
- [ ] Fix duplicate brainstorming/SKILL.md mapping in upstreams.json (superpowers + compound-engineering both claim it) (fd-arch P1 — 1/6)
- [ ] Document relationship between upstream-check.sh and sync.yml or unify them (fd-arch P1, simplicity P2 — 2/6)
- [ ] Fix engineering-docs XML enforcement tags that contradict create-agent-skills guidance (patterns P1 — 1/6)
- [ ] Add authentication to Agent Mail MCP server declaration (fd-security P1 — 1/6)
- [ ] Remove unnecessary `id-token:write` from sync.yml permissions (fd-security P1 — 1/6)
- [ ] Add adversarial content filtering to upstream sync (fd-security P1 — 1/6)
- [ ] Normalize skill descriptions to "Use when" pattern (fd-quality P1, patterns P2 — 2/6)
- [ ] Fix "liek this" typo and "type.Make" spacing in resolve commands (fd-quality P1, fd-ux P2, patterns P1 — 3/6)
- [ ] Differentiate or merge work vs execute-plan commands (fd-ux P1, simplicity P1 — 2/6)

### P2 — Nice-to-have (15 issues)

- [ ] Consolidate 3 resolve-* commands into 1 with target argument (fd-ux P1, patterns P1, simplicity P1 — 3/6)
- [ ] Merge create-agent-skills + writing-skills into single skill (patterns P1, simplicity P0 — 2/6)
- [ ] Reduce oversized commands: review 454→~200 lines, work 274→~80, brainstorm 115→~7 (simplicity P1-P2 — 1/6)
- [ ] Simplify learnings command — 6 parallel subagents is over-engineered (simplicity P1 — 1/6)
- [ ] Replace SessionStart hook heredoc with jq JSON construction (fd-security P2, fd-arch P2 — 2/6)
- [ ] Add `.env` patterns to `.gitignore` (fd-security P2 — 1/6)
- [ ] Remove work.md feature-branch references (trunk-based-only) (fd-arch P2 — 1/6)
- [ ] Remove review.md worktree prerequisites (trunk-based-only) (fd-arch P2 — 1/6)
- [ ] Fix plan-reviewer YAML block scalar to inline string (fd-quality P1, patterns P2 — 2/6)
- [ ] Remove pr-comment-resolver 'color: blue' remnant field (fd-quality P2, patterns P2 — 2/6)
- [ ] Add argument-hint to write-plan and execute-plan (fd-quality P2 — 1/6)
- [ ] Fix YAML quoting inconsistencies in argument-hint values (patterns P2 — 1/6)
- [ ] Ship Clavain-native T1 agents instead of depending on gurgeh-plugin (fd-arch P1 IMP — 1/6)
- [ ] Document threat model and trust boundaries (fd-security IMP — 1/6)
- [ ] Add Quick Start section for new users showing 5 core commands (fd-ux IMP — 1/6)

## Agent Reports

| Agent | Tier | P0 | P1 | P2 | Verdict | Report |
|-------|------|----|----|-----|---------|--------|
| fd-architecture | T1 (codebase-aware) | 1 | 4 | 6 | needs-changes | [fd-architecture.md](fd-architecture.md) |
| fd-code-quality | T1 (codebase-aware) | 3 | 4 | 3 | needs-changes | [fd-code-quality.md](fd-code-quality.md) |
| fd-security | T1 (codebase-aware) | 0 | 3 | 7 | needs-changes | [fd-security.md](fd-security.md) |
| fd-user-experience | T1 (codebase-aware) | 2 | 4 | 3 | needs-changes | [fd-user-experience.md](fd-user-experience.md) |
| pattern-recognition-specialist | T3 (generic) | 1 | 5 | 7 | needs-changes | [pattern-recognition-specialist.md](pattern-recognition-specialist.md) |
| code-simplicity-reviewer | T3 (generic) | 2 | 9 | 5 | needs-changes | [code-simplicity-reviewer.md](code-simplicity-reviewer.md) |

## Recommended Priority

1. **Fix component counts + routing table** — prevents user confusion and discovery failures (~30 min)
2. **Fix upstreams.json broken mappings** — unblocks upstream sync for compound-engineering commands (~10 min)
3. **Scrub Rails/upstream remnants** — aligns with stated general-purpose policy (~1 hr)
4. **Add validation script** — prevents count/reference drift from recurring
5. **Consider simplification pass** — ~2,200 LOC reduction potential across resolve commands, skill overlaps, and thick commands
