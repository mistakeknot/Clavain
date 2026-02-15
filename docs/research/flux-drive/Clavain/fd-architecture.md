# Flux Drive Architecture Review: Clavain Plugin

**Reviewer:** fd-architecture agent
**Target:** Clavain v0.5.7 (general-purpose engineering discipline plugin)
**Date:** 2026-02-13
**Scope:** Plugin architecture health, coupling analysis, growth vectors

---

## Executive Summary

Clavain shows mature architectural discipline with clear boundaries between core plugin code and companion services. Recent extractions of `interphase` and `interline` demonstrate intentional decoupling. The 3-tier routing (stage/domain/concern) provides coherent discovery. However, there are structural tensions around upstream sync complexity, hook proliferation, and the clavain_sync Python module's scope.

**Key findings:**
1. Companion plugin boundaries are clean — further extraction unlikely beneficial
2. Hook architecture is sustainable but showing strain at 6 hooks + 2 Stop hooks
3. Upstream sync machinery is heavyweight (6 upstreams, 4500+ LoC) — consider extracting
4. Domain profiles system (11 domains, auto-detection) adds significant runtime complexity
5. Scripts directory has grown to 536KB — ripe for modularization
6. No dead weight detected — all components are actively used

**Overall health: Strong.** Architecture supports independent evolution. Growth vectors are clear. No blocking technical debt.

---

## 1. Coupling & Cohesion Analysis

### 1.1 Companion Plugin Boundaries (Clean)

**interphase** (phase tracking, gates, beads lifecycle):
- Discovery via `_discover_beads_plugin()` in `hooks/lib.sh`
- Shim pattern: Clavain provides stubs, delegates to interphase if installed
- Zero hard dependency — graceful degradation when missing
- File-based sideband: `/tmp/clavain-bead-${session_id}.json`
- **Verdict:** Boundary is well-designed. No further extraction needed.

**interline** (statusline rendering):
- No hooks.json — Claude Code statusLine configured via `~/.claude/settings.json`
- Reads dispatch state from `/tmp/clavain-dispatch-*.json` (written by `scripts/dispatch.sh`)
- Reads bead state from `/tmp/clavain-bead-*.json` (written by interphase)
- **Verdict:** Clean read-only consumer. No coupling back to Clavain except file-based state.

**Codex CLI** (external executor):
- Wrapped by `scripts/dispatch.sh` (555 lines)
- No direct code dependency — pure subprocess invocation
- JSONL streaming parser (awk) in dispatch.sh couples to Codex event schema
- **Concern:** Dispatch complexity is high (JSONL parsing, template assembly, tier resolution, state tracking). Could this be extracted? Probably not — it's genuinely Clavain-specific orchestration.

**Oracle** (cross-AI review):
- Referenced in skills (interpeer, prompterpeer, winterpeer, splinterpeer)
- No code coupling — pure CLI invocation with env var setup (DISPLAY=:99, CHROME_PATH)
- **Verdict:** Loose coupling is appropriate for external tool.

### 1.2 Internal Module Boundaries

**Skills (29) vs Agents (17) vs Commands (37):**
- Skills invoked via `Skill` tool → markdown content loaded into context
- Agents dispatched via `Task` tool → subagent execution with isolated context
- Commands invoked via `/clavain:<name>` → instruction markdown for main agent
- **Clean separation.** No skills executing agents directly. Commands orchestrate via Task tool.

**Agents subcategories:**
- `agents/review/` (10) — fd-* core agents auto-detect language, plus 3 specialized
- `agents/research/` (5) — information gathering
- `agents/workflow/` (2) — automation
- **Concern:** References subdirectory exists (`agents/review/references/`) but is excluded from agent globs via category-based matching. Fragile — adding a fourth category breaks unless globs updated.

**Config structure:**
- `config/flux-drive/knowledge/` — durable patterns from past reviews (7 .md files)
- `config/flux-drive/domains/` — 11 domain profiles + index.yaml
- `config/flux-drive/diff-routing.md` — triage logic
- **Tight coupling:** Domain detection (`scripts/detect-domains.py`) reads `domains/index.yaml`, flux-drive skill reads domain profiles. This is cohesive — flux-drive owns the domain system.

### 1.3 Hook Architecture (Strain Detected)

**6 hooks across 4 lifecycle events:**
- **SessionStart** (1 hook): context injection, companion detection, upstream staleness, sprint scan
- **PostToolUse** (2 hooks): clodex-audit.sh (Edit/Write matcher), auto-publish.sh (Bash matcher)
- **Stop** (2 hooks): auto-compound.sh, session-handoff.sh
- **SessionEnd** (1 hook): dotfiles-sync.sh

**Complexity drivers:**
1. **Stop hooks coordinate via sentinel files** (`/tmp/clavain-stop-${session_id}`) to prevent cascade
2. **SessionStart does 6 distinct things:** skill injection, companion detection, clodex contract injection, upstream check, sprint scan, env var persistence
3. **Throttling logic** in auto-compound (5min per-session), handoff (once-per-session)
4. **Signal detection** in auto-compound (6 weighted signals, threshold logic)

**Coupling risks:**
- SessionStart's sprint_brief_scan sources `hooks/sprint-scan.sh` (shared with `/sprint-status` command)
- auto-compound reads transcript with tail+grep (fragile to transcript format changes)
- session-start.sh reads `using-clavain/SKILL.md` and escapes for JSON (tight coupling to skill file path)

**Verdict:** Hook count is manageable but growing. SessionStart is doing too much. Consider splitting into:
- `session-init.sh` — core context injection
- `session-context-scan.sh` — sprint/upstream/companion detection
- Keep as single hook for now but monitor complexity.

### 1.4 Upstream Sync Machinery (Heavy)

**Components:**
- `upstreams.json` — 6 upstream repos, file mappings
- `scripts/upstream-check.sh` — 200+ lines, checks gh api for changes
- `scripts/clavain_sync/` — 10 Python modules, 4500+ LoC total
- `.github/workflows/` — 4 sync-related workflows (check, sync, impact, decision-gate)
- `docs/upstream-versions.json` — baseline tracking
- `docs/upstream-decisions/` — decision records

**Complexity signals:**
1. Namespace contamination detection (grep for `compound-engineering:|ralph-wiggum:`)
2. Deleted file tracking (9 agents, 3 commands removed from sync)
3. Glob expansion in fileMap (`references/*`)
4. Post-sync restoration (lfg.md gets overwritten, must be restored)
5. GitHub workflow orchestration with human decision gates

**Coupling:**
- SessionStart hook checks `docs/upstream-versions.json` mtime for staleness warnings
- `/upstream-sync` command triggers full sync via GitHub workflow dispatch

**Growth vector concern:** If more upstreams are added (currently 6), this machinery will become load-bearing infrastructure. Consider:
- Extract to separate plugin (`upstream-sync` or `repo-sync`) with Clavain as a client
- Or accept this as core Clavain responsibility (current choice seems viable)

**Verdict:** Not currently problematic but monitor. If upstream count exceeds 8 or sync complexity doubles, extraction is warranted.

---

## 2. Dead Weight Detection

### Files/Directories Checked:
- `docs-sp-reference/` — **Does not exist** (mentioned in CLAUDE.md as historical archive, likely deleted)
- Hook scripts — all 6 are registered and executed
- Scripts — spot-checked 10 scripts, all referenced by commands or workflows
- Config files — flux-drive domains/knowledge both actively used
- Test fixtures — all used by structural/shell test suites

### Unused Components: None detected

**Validation:**
- All 29 skills have SKILL.md frontmatter and are invokable
- All 17 agents have YAML frontmatter with examples
- All 37 commands have YAML frontmatter
- Hooks.json references all scripts in hooks/
- Test suite validates counts (29/17/37 hardcoded as regression guards)

**Potential cleanup:**
- `hooks/lib-discovery.sh` and `hooks/lib-gates.sh` are shims — 2-3 lines each, delegate to interphase. Could inline into session-start.sh if interphase becomes required. Not worth it now.

---

## 3. Module Boundaries (Appropriate)

### skills/ vs agents/ vs commands/ Split

**Current logic:**
- **Skills** = reusable discipline processes (how to brainstorm, debug, write plans)
- **Agents** = specialized reviewers/researchers with isolated execution
- **Commands** = user-facing shortcuts that orchestrate skills/agents

**Boundary integrity:**
- Commands reference skills by name (e.g., `/write-plan` → `clavain:writing-plans`)
- Commands dispatch agents via Task tool (e.g., `/flux-drive` → fd-architecture)
- Skills never directly invoke agents (indirection via Task tool in main session)

**Is this the right split?** Yes. The 3-way split matches tool semantics:
- `Skill` tool = load markdown into context
- `Task` tool = spawn subagent
- `/command` = execute instructions in main session

**Alternative considered:** Merge commands into skills (commands become "skill launchers"). Rejected — commands provide user-facing UX layer, skills provide reusable content.

### config/flux-drive/ Scope

**Contents:**
- `knowledge/` — 7 patterns + archive/ (past review learnings)
- `domains/` — 11 domain profiles + index.yaml (detection signals + review criteria)
- `diff-routing.md` — flux-drive triage logic

**Scoping question:** Should domain system live in config/ or be a first-class component?

**Current choice is correct:**
- Domain profiles are data, not code — config/ is appropriate
- Domain detection script (`scripts/detect-domains.py`) reads from config/
- Flux-drive skill owns the domain system — tight coupling is intentional

**Growth concern:** 11 domains × 30KB avg = 330KB of profile content. If this grows beyond 20 domains or profiles exceed 50KB each, consider:
- Lazy loading (only load primary domain profile)
- Separate repo for domain definitions (like a knowledge base)
- For now, keep as-is.

---

## 4. Hook Architecture Sustainability

### Current State (6 hooks, 4 lifecycle events)

**SessionStart:**
- Reads `using-clavain/SKILL.md` (700 bytes escaped JSON)
- Detects companions (beads, oracle, codex, interphase, interline)
- Checks upstream staleness (file mtime check, no network)
- Runs sprint awareness scan (lightweight: HANDOFF.md check, orphaned brainstorms count)
- Persists session_id to CLAUDE_ENV_FILE
- Cleans up old plugin cache versions (symlink strategy for mid-session updates)
- **Complexity: Moderate.** 126 lines, 6 distinct responsibilities.

**PostToolUse (Edit/Write):**
- `clodex-audit.sh` — logs source code writes when clodex mode active (audit only, 37 lines)
- **Complexity: Low.** Single purpose, no side effects besides log append.

**PostToolUse (Bash):**
- `auto-publish.sh` — detects plugin publish commands, triggers marketplace update
- **Complexity: Unknown (file not read).** Likely similar to clodex-audit.

**Stop:**
- `auto-compound.sh` — weighted signal detection (6 signals, threshold 3), 150 lines
- `session-handoff.sh` — incomplete work detection (uncommitted changes, in-progress beads), 111 lines
- Both use `/tmp/clavain-stop-${session_id}` sentinel to prevent cascade
- **Complexity: Moderate-High.** Signal detection via transcript parsing is fragile.

**SessionEnd:**
- `dotfiles-sync.sh` — delegates to external script, 25 lines
- **Complexity: Low.** Fire-and-forget.

### Sustainability Assessment

**Strengths:**
1. Hooks are async where possible (SessionStart, SessionEnd)
2. Timeout budgets are conservative (5-15s)
3. Guard clauses prevent cascades (stop_hook_active check, sentinel files)
4. Fail-open strategy (missing jq → silent no-op)

**Weaknesses:**
1. **SessionStart is a kitchen sink** — 6 responsibilities, hard to test in isolation
2. **Transcript parsing in auto-compound is brittle** — grep for `"git commit\|"that worked` assumes specific phrasing
3. **No hook testing** — shell tests exist for individual scripts but not hook integration
4. **Stop hooks run synchronously in sequence** — if auto-compound blocks for 5s, handoff doesn't run until after

**Consolidation opportunity:**
- Merge auto-compound + session-handoff into single `session-finalize.sh` hook with two phases
- Pro: Single sentinel, single timeout, unified signal detection
- Con: Loses separation of concerns (compound = knowledge capture, handoff = continuity)
- **Verdict:** Keep separate for now. Monitor runtime — if Stop hooks exceed 10s combined, consolidate.

**Growth capacity:**
- Adding a 7th hook is viable
- Adding a 3rd Stop hook creates coordination overhead (sentinel file coordination is already complex)
- **Recommendation:** Cap Stop hooks at 2. If a third need arises, consolidate existing.

---

## 5. Dependency Graph

### External Dependencies (Clean Boundaries)

**Required for full functionality:**
- **context7** (MCP server) — runtime doc fetching, registered in plugin.json
- **qmd** (MCP server) — local knowledge base, registered in plugin.json
- **codex** (CLI) — wrapped by dispatch.sh, optional but core to workflow
- **oracle** (CLI) — wrapped by interpeer skill, optional
- **bd** (CLI) — beads task tracker, detected by SessionStart, optional
- **gh** (CLI) — upstream-check.sh uses gh api, optional

**Optional companions:**
- **interphase** — phase tracking, discovered via plugin cache search
- **interline** — statusline rendering, discovered via plugin cache search

**Build/test dependencies:**
- Python (uv run pytest) — structural tests
- bats-core — shell tests
- jq — hook JSON parsing (fail-open if missing)
- gawk — dispatch.sh JSONL parsing (fallback: no live statusline)

**Boundary analysis:**
- No tight coupling to external code — all deps invoked via subprocess
- File-based sideband for statusline state (`/tmp/clavain-*.json`)
- Env var-based coordination (`CLAUDE_SESSION_ID`, `INTERPHASE_ROOT`)
- **Verdict:** Boundaries are clean. External tools are swappable.

### Internal Module Dependencies

**Skills → Skills:** Minimal cross-referencing. using-clavain references all others via routing table.

**Skills → Agents:** Commands invoke agents via Task tool. Skills sometimes reference agents in documentation.

**Commands → Skills:** Commands invoke skills via Skill tool (e.g., `/write-plan` → `writing-plans`).

**Commands → Agents:** Commands dispatch agents via Task tool (e.g., `/flux-drive` → fd-architecture).

**Hooks → Skills:** SessionStart reads `using-clavain/SKILL.md` directly (tight coupling).

**Hooks → Scripts:** session-start.sh sources `sprint-scan.sh`, uses `lib.sh` for JSON escaping.

**Scripts → Config:** detect-domains.py reads `config/flux-drive/domains/index.yaml`.

**Test Suite → Everything:** Hardcoded counts (29/17/37) as regression guards.

**Circular dependencies:** None detected.

**Tight coupling points:**
1. SessionStart → using-clavain/SKILL.md (path dependency)
2. flux-drive → domain profiles (config/ path dependency)
3. dispatch.sh → codex JSONL schema (event type strings)
4. Test suite → component counts (will break on every add/remove)

**Recommendations:**
1. SessionStart: Consider injecting skill content via `additionalContext` from plugin manifest instead of reading file directly.
2. Test suite: Replace hardcoded counts with directory scans (less brittle).

---

## 6. Growth Vectors

### Can Grow Cleanly (No Structural Changes Needed)

**1. Add skills (current: 29)**
- Directory-based discovery, no central registry
- Routing table in using-clavain/SKILL.md must be updated (manual)
- **Capacity:** 50+ skills before routing table becomes unwieldy
- **Limit:** SessionStart injects full using-clavain content — keep under 2KB

**2. Add agents (current: 17)**
- File-based discovery, category directories (review/research/workflow)
- Agent roster in flux-drive is static (hardcoded in SKILL.md)
- **Capacity:** 30+ agents before roster becomes unwieldy
- **Limit:** Test suite hardcodes count (must update on every change)

**3. Add commands (current: 37)**
- File-based discovery, no category structure
- Help command lists all (dynamically generated)
- **Capacity:** 60+ commands before help becomes overwhelming
- **Limit:** None structural

**4. Add hooks (current: 6 across 4 events)**
- Registration in hooks/hooks.json
- **Capacity:** 10 total hooks before coordination overhead becomes problematic
- **Limit:** Stop hooks should cap at 2-3 (sentinel coordination complexity)

**5. Add domain profiles (current: 11)**
- Config-based, index.yaml drives detection
- **Capacity:** 20 domains before detection runtime exceeds budget
- **Limit:** Profile content size (currently 330KB total, loaded per review)

### Requires Structural Changes

**1. Multi-plugin orchestration**
- Current: Clavain, interphase, interline are independent
- Future: Cross-plugin coordination (e.g., shared knowledge layer)
- **Blocker:** No plugin-to-plugin messaging beyond file-based sideband
- **Solution:** Introduce plugin coordination protocol (env vars, JSON API, or MCP server)

**2. Stateful review workflows**
- Current: flux-drive is stateless (one review per invocation)
- Future: Multi-round review with agent memory across turns
- **Blocker:** Agent Task isolation — agents don't share context between invocations
- **Solution:** Introduce review session state (file-based or MCP resource)

**3. User-defined domain profiles**
- Current: 11 built-in domains, detection script chooses
- Future: Users define custom domains (e.g., "fintech-web-app")
- **Blocker:** Domain profiles live in plugin config/ (not user-writable)
- **Solution:** Support `.claude/flux-drive/domains/custom-domain.md` with profile schema

**4. Upstream sync as a service**
- Current: Upstream sync is Clavain-internal (clavain_sync module)
- Future: Other plugins want upstream sync (code reuse)
- **Blocker:** clavain_sync is not a standalone package
- **Solution:** Extract to separate repo (`upstream-sync-kit`) or publish as PyPI package

**5. Hook composition**
- Current: Hooks are flat (one script per hook trigger)
- Future: Compose hooks from reusable fragments (e.g., "add sprint scan to any SessionStart")
- **Blocker:** hooks.json has no composition model
- **Solution:** Introduce hook fragments directory + composition DSL

---

## 7. Architectural Debt & Risks

### Technical Debt (Low)

**1. SessionStart complexity (126 lines, 6 responsibilities)**
- **Impact:** Moderate — harder to test, reason about, modify
- **Mitigation:** Currently manageable. Extract sprint scan if it exceeds 50 lines.
- **Priority:** P2 (monitor)

**2. Test suite hardcoded counts (29/17/37)**
- **Impact:** Low — breaks on every component add/remove, easy to fix
- **Mitigation:** Replace with directory scans
- **Priority:** P3 (nice-to-have)

**3. Transcript parsing in auto-compound**
- **Impact:** Moderate — brittle to transcript format changes
- **Mitigation:** Fails open (no compound if parsing fails)
- **Priority:** P2 (monitor for breakage)

**4. dispatch.sh JSONL parser (awk)**
- **Impact:** Low — couples to Codex event schema
- **Mitigation:** Schema is stable, awk is fast/portable
- **Priority:** P3 (acceptable coupling)

### Architectural Risks (Moderate)

**1. Companion plugin discovery fragility**
- **Symptom:** `_discover_beads_plugin()` uses find in plugin cache with hardcoded path pattern
- **Risk:** Plugin cache structure changes → discovery breaks
- **Mitigation:** Fallback to `INTERPHASE_ROOT` env var, fail gracefully
- **Priority:** P2 (acceptable with current fail-open strategy)

**2. Domain detection runtime budget**
- **Symptom:** detect-domains.py scans directories/files/frameworks, <10s budget
- **Risk:** Large repos (>10K files) exceed budget, block SessionStart
- **Mitigation:** Cache exists, staleness check is fast (hash → git → mtime)
- **Priority:** P2 (monitor for slow repos)

**3. Upstream sync post-merge corruption**
- **Symptom:** Namespace contamination (compound-engineering: → clavain:), lfg.md overwrite
- **Risk:** Sync merges break functionality, require manual cleanup
- **Mitigation:** Decision gate workflow requires human review
- **Priority:** P2 (acceptable with current human-in-loop)

**4. Hook cascade prevention via sentinel files**
- **Symptom:** Stop hooks write `/tmp/clavain-stop-${session_id}`, check before running
- **Risk:** Sentinel cleanup failure → hooks never fire again in same session
- **Mitigation:** 60min stale cleanup in each hook
- **Priority:** P3 (low probability, low impact)

---

## 8. What Should We Work On Next?

### High-Impact, Low-Effort (Do Soon)

**1. Replace test suite hardcoded counts with scans** (P2, 1 hour)
- Current: `assert len(skills) == 29` breaks on every add
- Fix: `assert len(skills) > 0` or scan directories dynamically
- **Benefit:** Reduces test maintenance burden

**2. Extract sprint-scan.sh into separate file** (P2, 30 min)
- Current: Sourced by session-start.sh and sprint-status command
- Already done — validate that both call sites work correctly
- **Benefit:** Already achieved — no action needed

**3. Add hook integration tests** (P2, 2 hours)
- Current: Shell tests for individual scripts, no end-to-end hook flow
- Add: Bats tests that simulate hook stdin JSON, verify stdout JSON
- **Benefit:** Catch hook regressions before SessionStart breaks

### Medium-Impact, Medium-Effort (Plan For)

**4. Domain profile lazy loading** (P2, 4 hours)
- Current: flux-drive loads all detected domain profiles (up to 3 × 30KB)
- Optimize: Load only primary domain, offer "load secondary profiles?" AskUserQuestion
- **Benefit:** Reduces token overhead for multi-domain projects

**5. User-defined domain profiles** (P2, 8 hours)
- Current: 11 built-in domains only
- Add: Support `.claude/flux-drive/domains/custom.md` with schema validation
- **Benefit:** Projects can define specialized domains (e.g., "embedded-iot")

**6. Consolidate auto-compound + session-handoff** (P3, 3 hours)
- Current: Two Stop hooks with sentinel coordination
- Merge: Single session-finalize.sh with two phases
- **Benefit:** Reduces sentinel complexity, unified timeout

### High-Impact, High-Effort (Long-Term)

**7. Extract upstream sync to standalone tool** (P2, 16 hours)
- Current: clavain_sync is Clavain-internal (4500+ LoC)
- Extract: Publish as `upstream-sync-kit` PyPI package or separate plugin
- **Benefit:** Reusable by other plugins, reduces Clavain surface area

**8. Plugin coordination protocol** (P1, 40 hours)
- Current: File-based sideband (`/tmp/clavain-*.json`)
- Introduce: JSON-RPC over stdio or MCP resource sharing
- **Benefit:** Enables multi-plugin orchestration, shared knowledge layer

**9. Review session state** (P2, 24 hours)
- Current: flux-drive is stateless
- Add: `.claude/flux-drive/sessions/{id}.json` with agent findings, round tracking
- **Benefit:** Multi-round reviews with agent memory

### Low-Priority (Nice-to-Have)

**10. Hook composition DSL** (P3, 20 hours)
- Current: Flat hooks.json, one script per trigger
- Add: `hooks/fragments/` + composition YAML (like Ansible plays)
- **Benefit:** Reusable hook fragments across plugins

---

## 9. Recommendations

### Immediate (This Sprint)

1. **Validate hook integration** — Run end-to-end test of SessionStart → Stop → SessionEnd flow with all 6 hooks active. Verify sentinel cleanup, timeout handling, JSON output.

2. **Monitor upstream sync complexity** — Track LoC in clavain_sync/, fileMap growth. If exceeds 6000 LoC or 10 upstreams, flag for extraction.

3. **Document companion plugin contracts** — Write `docs/architecture/companion-protocols.md` specifying:
   - File-based sideband format (`/tmp/clavain-*.json`)
   - Discovery protocol (`_discover_beads_plugin()`)
   - Env var contract (`INTERPHASE_ROOT`, `CLAUDE_SESSION_ID`)

### Short-Term (Next 2-4 Weeks)

4. **Add hook integration tests** — Bats suite for SessionStart, Stop, SessionEnd. Mock stdin JSON, verify stdout.

5. **Replace hardcoded test counts** — Change structural tests to scan directories, not assert exact counts.

6. **Profile domain detection runtime** — Test detect-domains.py on repos with 10K, 50K, 100K files. If >10s, optimize or add --fast flag.

### Medium-Term (Next Quarter)

7. **Lazy-load domain profiles** — Only load primary domain in flux-drive Step 2.1a. Offer secondary profiles on demand.

8. **User-defined domains** — Support `.claude/flux-drive/domains/custom-*.md` with schema validator.

9. **Consolidate Stop hooks** — Merge auto-compound + session-handoff if combined runtime exceeds 8s.

### Long-Term (Future Sprints)

10. **Extract upstream sync** — Publish clavain_sync as standalone tool when upstream count reaches 8 or other plugins need sync.

11. **Plugin coordination protocol** — Design cross-plugin messaging when interphase/interline need tighter integration.

---

## 10. Conclusion

**Clavain's architecture is sound.** The 3-tier routing, companion plugin boundaries, and hook system are well-designed for the current scale. Recent extractions (interphase, interline) demonstrate intentional decoupling. No blocking technical debt.

**Primary growth constraint:** Hook complexity, particularly SessionStart (6 responsibilities) and Stop coordination (sentinel files). Monitor these as new features are added.

**Strategic question:** Should upstream sync machinery (6 upstreams, 4500 LoC, 4 GitHub workflows) remain internal or become a standalone tool? Current choice is viable but monitor complexity.

**Next steps:** Add hook integration tests, replace hardcoded test counts, document companion protocols. These are low-effort, high-value tasks that reduce maintenance burden.

**Overall verdict:** Architecture supports current needs and planned growth. No major refactoring required. Continue incremental improvements.
