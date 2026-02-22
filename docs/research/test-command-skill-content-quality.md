# Clavain Content Quality Audit — Commands, Skills, Agents

**Date:** 2026-02-22
**Scope:** `/home/mk/projects/Demarch/os/clavain` — 53 commands, 16 skills, 4 agents
**Audit type:** Content quality check (not syntax)

---

## Summary Table

| Component   | Count | Stubs (<300B) | Broken Refs | Issues |
|-------------|-------|---------------|-------------|--------|
| Commands    | 53    | 9             | 4           | 3 missing skill refs, 1 stale count |
| Skills      | 16    | 0             | 0           | 1 stale count in using-clavain |
| Agents      | 4     | 0             | 0           | 0 |
| **Total**   | **73**| **9**         | **4**       | **8 distinct issues** |

---

## 1. Commands Audit (53 files)

### 1.1 All Commands by Size

| Command | Size | Lines | Notes |
|---------|------|-------|-------|
| sprint | 21400B | 417L | Largest — comprehensive workflow |
| setup | 9907B | 242L | |
| doctor | 9586B | 265L | |
| interspect-status | 8941B | 248L | |
| work | 8608B | 250L | |
| triage | 7763B | 310L | |
| interspect-propose | 7373B | 188L | |
| quality-gates | 6287B | 165L | |
| brainstorm | 5631B | 149L | |
| interspect | 5272B | 138L | |
| interspect-revert | 5213B | 176L | |
| changelog | 4918B | 144L | |
| strategy | 4782B | 163L | |
| help | 4592B | 93L | |
| review | 4573B | 131L | |
| interspect-health | 4245B | 110L | |
| generate-command | 4091B | 162L | |
| heal-skill | 3966B | 142L | |
| model-routing | 3863B | 129L | |
| debate | 3771B | 124L | |
| galiana | 3507B | 96L | |
| migration-safety | 3471B | 113L | |
| repro-first-debugging | 3384B | 100L | |
| triage-prs | 3135B | 98L | |
| interspect-correction | 3120B | 100L | |
| interspect-evidence | 3146B | 137L | |
| upstream-sync | 3100B | 83L | |
| sprint-status | 3075B | 70L | |
| codex-sprint | 2977B | 101L | |
| review-doc | 2876B | 80L | |
| smoke-test | 2768B | 81L | |
| reflect | 2751B | 54L | |
| resolve | 2636B | 72L | |
| init | 2417B | 80L | |
| fixbuild | 2329B | 74L | |
| status | 1306B | 34L | |
| codex-bootstrap | 1282B | 47L | |
| execute-plan | 1030B | 19L | |
| plan-review | 982B | 15L | |
| interspect-unblock | 977B | 32L | |
| compound | 769B | 20L | |
| interpeer | 748B | 26L | |
| clodex-toggle | 566B | 20L | |
| write-plan | 456B | 13L | |
| create-agent-skill | 280B | 8L | **Stub — refs missing skill** |
| verify | 272B | 9L | **Stub — refs missing skill** |
| tdd | 257B | 8L | **Stub — refs missing skill** |
| code-review | 242B | 9L | Thin wrapper (OK — skill exists) |
| docs | 237B | 9L | Thin wrapper (OK — skill exists) |
| refactor | 234B | 9L | Thin wrapper (OK — skill exists) |
| interserve | 227B | 9L | Thin wrapper (OK — skill exists) |
| land | 225B | 9L | Thin wrapper (OK — skill exists) |
| todos | 200B | 9L | Thin wrapper (OK — skill exists) |

### 1.2 Frontmatter Quality

All 53 commands have proper YAML frontmatter with `---` delimiters, `name:` field, and `description:` field. None use markdown headings (correct — Claude Code commands use frontmatter, not headings).

### 1.3 Thin Wrapper Pattern

9 commands are thin wrappers that delegate entirely to a skill via `Skill()`. This is a valid pattern — the command provides the `/clavain:name` entry point while the skill holds the logic. However:

**Healthy thin wrappers (6):** `code-review`, `docs`, `land`, `refactor`, `interserve`, `todos` — all reference skills that exist.

**Broken thin wrappers (3):**

| Command | References Skill | Status |
|---------|-----------------|--------|
| `tdd` | `Skill(test-driven-development)` | **No `skills/test-driven-development/` directory exists** |
| `verify` | `Skill(verification-before-completion)` | **No `skills/verification-before-completion/` directory exists** |
| `create-agent-skill` | `Skill(create-agent-skills)` | **No `skills/create-agent-skills/` directory exists** |

These commands will fail at runtime because they restrict `allowed-tools` to a skill that doesn't exist, meaning the agent cannot invoke any tool when the command runs.

### 1.4 Broken File References in Commands

| Reference | Where Referenced | Status | Severity |
|-----------|-----------------|--------|----------|
| `scripts/statusline.sh` | `commands/setup.md:217`, `commands/doctor.md:69` | Not in Clavain — expected in `interline` companion plugin | **Low** (references companion plugin cache path, not local) |
| `scripts/interlock-register.sh` | `commands/setup.md:219`, `commands/doctor.md:144` | Not in Clavain — expected in `interlock` companion plugin | **Low** (same — companion cache path) |
| `scripts/interpath.sh` | `commands/doctor.md:80` | Not in Clavain — expected in `interpath` companion plugin | **Low** (same) |
| `scripts/interwatch.sh` | `commands/doctor.md:91` | Not in Clavain — expected in `interwatch` companion plugin | **Low** (same) |
| `hooks/YOUR_WEBHOOK_ID` | `commands/changelog.md:109` | Placeholder in Discord webhook URL | **None** (template/example) |
| `scripts/codex-bootstrap.sh.` | Various | Trailing period in grep match | **None** (false positive) |

**Verdict on file references:** The "broken" references to companion plugin scripts (`statusline.sh`, `interlock-register.sh`, `interpath.sh`, `interwatch.sh`) are actually correct — the commands look for these files in `~/.claude/plugins/cache/` at runtime, not in Clavain's local tree. The grep matched the basename but missed the full glob path. No actual broken local file references found.

---

## 2. Skills Audit (16 skills)

### 2.1 All Skills by Size

| Skill | SKILL.md Size | References Dir | Ref Count |
|-------|--------------|----------------|-----------|
| engineering-docs | 11968B | Yes | 1 (yaml-schema.md) |
| subagent-driven-development | 10044B | No | — |
| dispatching-parallel-agents | 8444B | No | — |
| interserve | 8037B | Yes | 6 files |
| file-todos | 7626B | No | — |
| writing-plans | 6378B | No | — |
| upstream-sync | 6049B | No | — |
| code-review-discipline | 5485B | No | — |
| using-tmux-for-interactive-commands | 5074B | No | — |
| landing-a-change | 4557B | No | — |
| executing-plans | 4428B | No | — |
| refactor-safely | 3826B | No | — |
| galiana | 3726B | No | — |
| lane | 3310B | No | — |
| brainstorming | 2488B | No | — |
| using-clavain | 1492B | Yes | 4 files |

### 2.2 SKILL.md Structure Quality

All 16 skills have:
- Valid YAML frontmatter with `description:` field
- Substantive content (smallest is `using-clavain` at 1492B — but it's a router/index, so conciseness is appropriate)
- No stubs detected

**Content section coverage:**

| Skill | Has Description | Has When/Trigger | Has Process/Steps |
|-------|----------------|------------------|-------------------|
| brainstorming | Yes | No | Yes |
| code-review-discipline | Yes | Yes | Yes |
| dispatching-parallel-agents | Yes | Yes | No |
| engineering-docs | Yes | Yes | Yes |
| executing-plans | Yes | Yes | Yes |
| file-todos | Yes | Yes | Yes |
| galiana | Yes | No | Yes |
| interserve | Yes | Yes | No |
| landing-a-change | Yes | No | Yes |
| lane | Yes | No | No |
| refactor-safely | Yes | Yes | Yes |
| subagent-driven-development | Yes | Yes | Yes |
| upstream-sync | Yes | No | Yes |
| using-clavain | Yes | No | Yes |
| using-tmux-for-interactive-commands | Yes | Yes | Yes |
| writing-plans | Yes | No | Yes |

Skills without "When to Use" sections: `brainstorming`, `galiana`, `landing-a-change`, `lane`, `upstream-sync`, `using-clavain`, `writing-plans`. Most of these have trigger context embedded in the `description:` frontmatter field (e.g., "Use when..."), so this is acceptable for most. `lane` and `galiana` lack explicit trigger guidance in both the description and body.

### 2.3 References Directories

| Skill | References | Content |
|-------|-----------|---------|
| engineering-docs | 1 file | `yaml-schema.md` — schema reference |
| interserve | 6 files | `behavioral-contract.md`, `cli-reference.md`, `debate-mode.md`, `oracle-escalation.md`, `split-mode.md`, `troubleshooting.md` |
| using-clavain | 4 files | `agent-contracts.md`, `dispatch-patterns.md`, `routing-tables.md`, `skill-discipline.md` |

All reference files are present and contain substantive content (not stubs).

### 2.4 Stale Count

`skills/using-clavain/SKILL.md` line 8 says:
```
# Quick Router — 15 skills, 4 agents, and 52 commands
```

Actual counts: **16 skills**, **4 agents** (correct), **53 commands**. The skill count is off by 1 and the command count is off by 1.

---

## 3. Agents Audit (4 agents)

| Agent | Location | Size | Lines |
|-------|----------|------|-------|
| data-migration-expert | agents/review/ | 5351B | 128L |
| bug-reproduction-validator | agents/workflow/ | 5237B | 98L |
| pr-comment-resolver | agents/workflow/ | 4261B | 100L |
| plan-reviewer | agents/review/ | 4247B | 63L |

All 4 agents:
- Have proper YAML frontmatter with `name:` field
- Are substantive (4200-5400 bytes each)
- Organized in appropriate subdirectories (`review/`, `workflow/`)
- No stubs, no broken references detected

---

## 4. Cross-Reference Integrity

### 4.1 CLAUDE.md Accuracy

CLAUDE.md states: "16 skills, 4 agents, 53 commands, 12 hooks"

- Skills: 16 actual directories — **correct**
- Agents: 4 actual files — **correct**
- Commands: 53 actual files — **correct**
- Hooks: 20 files in hooks/ (but some are libraries, not hook bindings) — the 12 count likely refers to hook bindings in `hooks.json`, not total files. Would need to verify `hooks.json` to confirm.

### 4.2 Commands → Skills Mapping

| Command | Allowed Skill | Skill Exists? |
|---------|--------------|---------------|
| code-review | code-review-discipline | Yes |
| create-agent-skill | create-agent-skills | **NO** |
| docs | engineering-docs | Yes |
| interserve | interserve | Yes |
| land | landing-a-change | Yes |
| refactor | refactor-safely | Yes |
| tdd | test-driven-development | **NO** |
| todos | file-todos | Yes |
| verify | verification-before-completion | **NO** |

### 4.3 Companion Plugin References

Commands `setup.md` and `doctor.md` reference scripts from companion plugins (`interline`, `interlock`, `interpath`, `interwatch`) using glob paths into the plugin cache. These are runtime lookups and are not expected to exist locally in Clavain.

---

## 5. Issues Found

### Critical (Will break at runtime)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | `/clavain:tdd` references `Skill(test-driven-development)` which doesn't exist | `commands/tdd.md` | Command fails — no tools available |
| 2 | `/clavain:verify` references `Skill(verification-before-completion)` which doesn't exist | `commands/verify.md` | Command fails — no tools available |
| 3 | `/clavain:create-agent-skill` references `Skill(create-agent-skills)` which doesn't exist | `commands/create-agent-skill.md` | Command fails — no tools available |

### Low (Cosmetic / Stale metadata)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 4 | Stale count: "15 skills" should be "16 skills" | `skills/using-clavain/SKILL.md:8` | Misleading router table |
| 5 | Stale count: "52 commands" should be "53 commands" | `skills/using-clavain/SKILL.md:8` | Misleading router table |

### Informational (Not broken, but notable)

| # | Issue | Location | Notes |
|---|-------|----------|-------|
| 6 | 9 commands under 300 bytes | Various | 6 are healthy thin wrappers; 3 are broken (issues 1-3 above) |
| 7 | `galiana` and `lane` skills lack explicit trigger guidance | `skills/galiana/SKILL.md`, `skills/lane/SKILL.md` | No "When to Use" section and no "Use when..." in description |
| 8 | `galiana` command references `Skill("galiana")` with quotes in inline text | `commands/galiana.md:12` | Not in `allowed-tools`, so not a runtime issue — just instructional text |

---

## 6. Recommendations

### Fix immediately (3 critical issues)

1. **Create `skills/test-driven-development/SKILL.md`** — or rename the `tdd` command's `allowed-tools` to reference an existing skill (perhaps from `intertest` companion plugin).

2. **Create `skills/verification-before-completion/SKILL.md`** — or rename the `verify` command's `allowed-tools` to reference an existing skill.

3. **Create `skills/create-agent-skills/SKILL.md`** — or rename the `create-agent-skill` command's `allowed-tools` to reference an existing skill (perhaps from `interdev` companion plugin).

### Fix soon (2 low issues)

4. **Update `skills/using-clavain/SKILL.md` line 8** — change "15 skills" to "16 skills" and "52 commands" to "53 commands".

### Consider (2 informational)

5. Add "When to Use" triggers to `galiana` and `lane` skill descriptions.
6. Review whether the 3 broken commands should be removed entirely or have their skills created.

---

## 7. Overall Assessment

**Quality: Good.** 50 of 53 commands (94%) are complete and functional. All 16 skills are substantive with proper structure. All 4 agents are well-formed. The 3 broken command-to-skill references are the only runtime-affecting issues, and they appear to be commands that were created anticipating skills that were never added (or were moved to companion plugins like `intertest` and `interdev`).

The thin-wrapper pattern (command delegates to skill) is used consistently and appropriately. Substantive commands (like `sprint`, `doctor`, `setup`, `work`) have thorough inline documentation. The overall content quality is high — no placeholder text, no lorem ipsum, no obviously AI-generated filler was found.
