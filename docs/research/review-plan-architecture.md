# Flux-Drive Architecture Review: Token-Efficient Skill Loading Plan

**Reviewer:** Claude Opus 4.6 (Flux-Drive Architecture)
**Date:** 2026-02-15
**Target:** [`docs/plans/2026-02-15-token-efficient-skill-loading.md`](../../../docs/plans/2026-02-15-token-efficient-skill-loading.md)
**PRD:** [`docs/prds/2026-02-15-token-efficient-skill-loading.md`](../../../docs/prds/2026-02-15-token-efficient-skill-loading.md)

---

## Summary

This plan introduces a dual-strategy token optimization: **compact skill files** (tiered loading) + **pre-computation scripts** (move deterministic work out of LLM context). The design distributes new artifacts across 3 plugin repos while centralizing generation tooling in the monorepo's `scripts/` directory.

**Architectural Verdict:** **APPROVED with P0 fix required**

The module boundary design is sound but has one critical coupling issue: `gen-compact.sh` hard-codes the CLI invocation method (`claude -p`), creating cross-layer dependency on a specific runtime environment.

**Core strengths:**
- Boundary placement is correct: compact files live alongside SKILL.md (discoverability, atomicity)
- Convention-based loader is appropriate for this context (agents are cooperative, not adversarial)
- Cross-plugin consistency is enforced through shared tooling (good DRY)
- Freshness tracking via `.compact-manifest` prevents drift

**Critical fixes:**
- P0: Abstract LLM invocation from `gen-compact.sh` to support multiple execution contexts (clavain, MCP, CI/CD, standalone)

**Optional improvements:**
- Consider extracting `gen-compact.sh` prompt template to a separate file
- Add semantic versioning to compact file format for future migrations
- Clarify ownership of `scripts/gen-compact.sh` — is this Interverse-wide or interflux-specific?

---

## 1. Boundaries & Coupling

### 1.1 Module Boundary Design (APPROVED)

**Decision:** Compact files (`SKILL-compact.md`) live **alongside** their source (`SKILL.md`) in each plugin's skill directory.

**Analysis:**

This is the right boundary for these reasons:

1. **Discoverability** — No special paths or configuration. If `SKILL.md` exists, `SKILL-compact.md` is either next to it or doesn't exist. Zero magic.

2. **Atomic commits** — Editing a skill and regenerating its compact version are logically coupled (same PR, same commit). Co-location makes this natural. Alternative designs (centralizing all compact files) would split logically atomic changes across repos.

3. **Plugin independence** — Each plugin owns its own compact representations. No shared state, no cross-plugin dependencies on compact file locations.

4. **Skill structure already heterogeneous** — Some skills are single-file (brainstorming: 53 lines), others are multi-file with phase dirs (flux-drive: 1,985 lines across 9 files). Compact files are just another structural variant in this design space.

**Trade-off acknowledged:** This creates 3 copies of the compact file pattern (interwatch, interpath, interflux), but the duplication is **intentional** — each plugin's compact file evolves independently based on its own complexity profile. The pattern is shared via tooling (`gen-compact.sh`), not via a shared artifact location.

**Comparison to alternatives:**

| Boundary | Pros | Cons | Verdict |
|----------|------|------|---------|
| **Alongside SKILL.md (chosen)** | Discoverable, atomic commits, plugin-independent | Pattern duplicated 3x (mitigated by shared tooling) | ✅ Correct |
| Centralized in Interverse/compact/ | Single source of truth | Breaks plugin independence, non-atomic commits, requires path config | ❌ Violates plugin boundary |
| One shared compact file for all plugins | Maximum DRY | Destroys modularity, all plugins couple to one file | ❌ Anti-pattern |

### 1.2 Loader Mechanism (APPROVED)

**Decision:** Convention-based loader via HTML comment preamble in `SKILL.md`:

```markdown
<!-- compact: SKILL-compact.md -->
```

The agent reads this hint and chooses to load the compact file instead of following multi-file read chains.

**Analysis:**

This is appropriate for this context because:

1. **Agents are cooperative, not adversarial** — Claude Code's skill loader is designed to follow instructions in SKILL.md. This isn't a security boundary; it's a performance optimization for a cooperating system.

2. **Graceful degradation** — If an agent ignores the hint (old Claude Code version, or an agent that doesn't understand the convention), it falls back to reading the full SKILL.md and following the multi-file read chain. No breakage.

3. **Zero tooling changes** — No Claude Code platform modifications needed. This ships today.

4. **Audit trail** — The HTML comment is visible in source control. Reviewers can see when compact mode was added and verify the compact file exists.

**Alternative considered: Enforcement via SKILL.md structure**

The plan could have proposed replacing the full instructions in `SKILL.md` with just a redirect:

```markdown
# Doc Watch

**Compact mode:** This skill loads `SKILL-compact.md` by default.
The full modular instructions are in `phases/` for reference.
```

**Why convention is better than enforcement here:**

- Enforcement would make SKILL.md unreadable as standalone documentation. The current design preserves SKILL.md as the canonical, human-readable source.
- Convention allows gradual rollout: compact files can be added to one skill at a time without breaking unmodified skills.
- Convention allows experimentation: if compact mode proves problematic for a specific skill, it can be reverted by deleting the HTML comment — no code changes needed.

**Risk acknowledged:** Agents might ignore the convention. **Mitigation:** Task 7 (freshness tests) includes a test to verify the preamble exists. If an agent consistently ignores compact mode, the team will notice via token usage metrics and can escalate to a SKILL.md structure change.

### 1.3 Cross-Plugin Dependency Graph (SOUND)

The plan introduces new dependencies between components:

```
gen-compact.sh (shared script)
├── depends on: claude CLI (implicit)
├── called by: Task 2, 3, 4 (one-time generation)
├── called by: (future) CI/CD freshness checks
└── produces: SKILL-compact.md (per-plugin)

interwatch-scan.sh (interwatch-specific)
├── depends on: bd CLI, git, jq, sqlite3
├── called by: doc-watch skill (runtime)
└── produces: JSON drift report

SKILL-compact.md (per-plugin artifact)
├── depends on: SKILL.md + phases/*.md + references/*.md (source)
├── loaded by: skill invocation (runtime)
└── validated by: test_compact_freshness.bats (CI)
```

**Dependency direction check:**

✅ `gen-compact.sh` (build-time tool) depends on source files (SKILL.md, phases/*.md) — correct direction (tools depend on data, not vice versa)

✅ `SKILL-compact.md` (derived artifact) depends on source files — correct direction (derived depends on canonical)

✅ Skills (runtime) optionally load compact files — correct direction (runtime adapts to presence/absence of optimization artifact)

❌ **P0 ISSUE:** `gen-compact.sh` hard-codes invocation of `claude -p` CLI — creates coupling to a specific execution context (see Section 1.4)

### 1.4 CLI Coupling (P0 ISSUE)

**Problem:** Task 5 specifies:

> Script that:
> 3. Calls Claude (via `claude -p`) with a summarization prompt

**Why this is a boundary violation:**

The `claude -p` CLI is a **delivery mechanism**, not a domain concept. Hardcoding it in `gen-compact.sh` couples the build system to:

1. A specific Claude Code installation location
2. A specific execution context (local dev machine with Claude Code installed)
3. A specific authentication state (assumes user is logged in)

**Impact:**

This breaks the following use cases:

- **CI/CD pipelines** — Cannot run `gen-compact.sh` in GitHub Actions without installing full Claude Code
- **MCP-based generation** — Cannot reuse the prompt template in an MCP server that generates compact files on-demand
- **Clavain agent execution** — Cannot generate compact files from within a Claude Code session (recursive invocation conflicts)
- **Standalone distribution** — Cannot ship `gen-compact.sh` as a reusable tool for external projects

**Recommended fix:**

Extract LLM invocation to an abstraction layer:

```bash
# gen-compact.sh now delegates to a pluggable backend
llm_invoke() {
  local prompt_file="$1"
  local backend="${COMPACT_GEN_BACKEND:-claude-cli}"

  case "$backend" in
    claude-cli)
      claude -p "$(cat "$prompt_file")"
      ;;
    mcp)
      # Call mcp__plugin_foo_bar__summarize tool via jq + curl to MCP server
      ;;
    api)
      # Call Anthropic API directly via curl + jq
      ;;
    *)
      echo "Unknown backend: $backend" >&2
      exit 1
      ;;
  esac
}
```

**Alternative (simpler):** Accept prompt on stdin, emit markdown on stdout. Let the caller choose the LLM:

```bash
# gen-compact.sh produces a prompt, doesn't invoke the LLM
gen_prompt() {
  cat <<EOF
Summarize this skill into a single compact instruction file (50-200 lines depending on complexity).
Keep: algorithm steps, decision points, output contracts, tables, code blocks.
Remove: examples, rationale, verbose descriptions, "why" explanations.
Add: "For edge cases or full reference, read SKILL.md" at the bottom.

Source files:
$(cat phases/*.md references/*.md)
EOF
}

# Caller chooses LLM
gen_prompt | claude -p "$(cat)" > SKILL-compact.md
gen_prompt | curl -X POST api.anthropic.com/v1/messages ... > SKILL-compact.md
gen_prompt | mcp_call summarize_skill > SKILL-compact.md
```

**Migration path:**

Phase 1 (ship blocker): Extract prompt template to `prompts/compact-skill.txt`, keep `claude -p` invocation in `gen-compact.sh`

Phase 2 (post-ship): Refactor to backend abstraction once CI/CD use case materializes

### 1.5 Ownership Boundaries (CLARIFY)

**Ambiguity:** The plan places `gen-compact.sh` in `scripts/` but doesn't specify **which** `scripts/` directory:

- `Interverse/scripts/` (monorepo-wide, like `interbump.sh`)
- `plugins/interflux/scripts/` (interflux-owned, like `detect-domains.py`)
- `hub/clavain/scripts/` (clavain-owned, like `gen-catalog.py`)

**Recommendation:**

Place in `Interverse/scripts/` for these reasons:

1. **Shared utility** — Used by 3 plugins (interwatch, interpath, interflux), not owned by any single one
2. **Precedent** — `interbump.sh` lives in `Interverse/scripts/` for the same reason (shared by all plugins)
3. **Discoverability** — Developers working in any plugin can find it via `../../scripts/`

**Implication:**

Interverse monorepo must be cloned for compact file generation to work. This is already true for version bumping (requires `interbump.sh`), so no new dependency is introduced.

**Document this explicitly** in the plan's Task 5 section:

```diff
- **Location:** `scripts/gen-compact.sh`
+ **Location:** `Interverse/scripts/gen-compact.sh` (shared utility, used by interwatch, interpath, interflux)
```

---

## 2. Pattern Analysis

### 2.1 Derived Artifact Pattern (CORRECT)

The plan treats `SKILL-compact.md` as a **derived artifact**, not a source file. This is the right pattern.

**Evidence:**

- Task 5: `.compact-manifest` tracks source file hashes (establishes source → derived relationship)
- Task 7: Tests validate compact file is up-to-date with sources
- PRD Section 5: "The full SKILL.md remains the canonical source. SKILL-compact.md is a derived artifact."

**Pattern compliance:**

✅ Single source of truth: SKILL.md + phases/*.md + references/*.md are canonical

✅ Derived artifact is regenerated from source: `gen-compact.sh` is deterministic

✅ Freshness is testable: `.compact-manifest` hash comparison

✅ Version control: Compact files are committed (not gitignored) so they're always in sync with source

**Anti-pattern avoided:** The plan does NOT propose editing `SKILL-compact.md` directly. All edits go to source files, then regeneration is triggered.

### 2.2 Convention Over Configuration (APPROPRIATE)

The plan uses convention (HTML comment) over configuration (JSON schema, loader plugin, etc.).

**When convention is correct:**

- The system is **cooperative** (agents follow instructions, not adversarial users bypassing rules)
- The pattern is **simple** (one file → another file)
- The fallback is **safe** (ignoring the hint just loads the full file)

**All three conditions hold here.** This is appropriate use of convention.

**Comparison to configuration-based alternative:**

A configuration-based approach would add a `skill.json` manifest:

```json
{
  "skill": "doc-watch",
  "loader": {
    "mode": "compact",
    "file": "SKILL-compact.md"
  }
}
```

**Why convention is better here:**

- **Simplicity:** One HTML comment vs. a new JSON schema + loader logic
- **Discoverability:** Grep for `<!-- compact:` vs. parsing JSON across all skills
- **Rollback:** Delete one line vs. editing JSON + validating schema

### 2.3 Pre-Computation Pattern (SOUND)

Task 1 (interwatch-scan.sh) applies the **pre-computation** pattern correctly:

**Pattern:** Move deterministic computation from LLM context to shell scripts. LLM reads pre-computed JSON and makes decisions.

**Before:**

```
LLM context:
1. Read signal definitions (79 lines)
2. Run bead count: bd list --status=closed | wc -l
3. Run git log: git rev-list --count
4. Run version comparison: jq vs grep
5. Compute drift score
6. Map to confidence tier
7. Decide action
```

**After:**

```
Shell script (interwatch-scan.sh):
1-6. All signal evaluation, scoring, tier mapping

LLM context:
7. Read JSON, decide action
```

**Token savings:** ~290 lines of instruction + signal evaluation → ~20 lines of JSON reading

**Correctness preserved:** The algorithm is the same, just executed in a different layer. The LLM still makes the final decision (refresh vs. suggest vs. report).

**Boundary check:**

✅ Shell script handles **deterministic** computation (counting, comparing, arithmetic)

✅ LLM handles **judgment** (should we refresh this doc given the signals?)

✅ No policy leakage: The action matrix (Certain → auto-refresh, Medium → suggest) stays in LLM context, not hardcoded in shell script

### 2.4 Cross-Plugin Consistency (ENFORCED)

The plan applies the same pattern to 3 plugins with different complexity levels:

| Plugin | Skill | Source files | Source lines | Target compact lines | Complexity |
|--------|-------|--------------|--------------|---------------------|------------|
| interwatch | doc-watch | 7 | 364 | 60-80 | Low (deterministic algorithm) |
| interpath | artifact-gen | 9 | 460 | 60-80 | Medium (5 artifact types) |
| interflux | flux-drive | 9 | 1,985 | 150-200 | High (scoring algorithm, agent roster) |

**Consistency check:**

✅ All use the same loader convention (HTML comment preamble)

✅ All use the same generation tool (`gen-compact.sh`)

✅ All use the same freshness mechanism (`.compact-manifest`)

✅ All preserve the same fallback (full SKILL.md remains readable)

**Variation is justified:** The target compact line counts scale with algorithmic complexity:

- **doc-watch (60-80 lines):** Simple 4-phase pipeline, fixed action matrix
- **artifact-gen (60-80 lines):** Shared discovery + 5 artifact-type paragraphs
- **flux-drive (150-200 lines):** Triage algorithm, scoring formula, 13-agent roster, domain detection

**No artificial homogenization:** The plan doesn't force flux-drive into 60 lines just to match the others. Compact size is driven by essential complexity, not an arbitrary target.

---

## 3. Simplicity & YAGNI

### 3.1 Scope Discipline (EXCELLENT)

The plan explicitly excludes several plausible features:

**Out of Scope (from PRD Section 3):**

- Compact files for low-overhead skills (brainstorming, writing-plans — already inline)
- Cross-session caching (requires Claude Code platform changes)
- Rewriting flux-drive scoring as Python (too complex for v1)
- Per-invocation token budgets

**Analysis:** All exclusions are justified:

1. **Low-overhead skills:** Brainstorming is 53 lines, already optimal. No win from compacting.
2. **Cross-session caching:** Platform feature, not plugin feature. Out of scope for this team.
3. **Python scoring:** Algorithmic rewrite would change behavior, not just presentation. High risk, unclear benefit.
4. **Token budgets:** Solves a different problem (hard caps vs. optimization). Separate feature.

**No YAGNI violations detected.** The plan doesn't add speculative hooks, plugin systems, or extensibility points.

### 3.2 Premature Abstraction Check (PASS)

**Question:** Is `gen-compact.sh` premature? Could Task 2/3/4 just manually write the compact files?

**Answer:** No, the script is justified because:

1. **Deterministic generation:** The same prompt + source files should always produce the same compact file. Manual editing would drift.
2. **Freshness validation:** The `.compact-manifest` pattern requires scripted generation to compute hashes.
3. **Three consumers:** Used by 3 plugins, not a one-off.

**Evidence the abstraction is needed NOW:** Task 7 (freshness tests) depends on `.compact-manifest` format, which only makes sense if generation is scripted.

### 3.3 Necessary vs. Accidental Complexity

**Necessary complexity (domain-driven, can't be removed):**

- Multi-file skill structure (flux-drive: 1,985 lines across 9 files) — driven by genuine algorithmic complexity (triage → domain detection → agent selection → synthesis → scoring)
- Hash-based freshness tracking — only reliable way to detect source drift without running LLM summarization on every CI run
- Per-plugin compact files — each plugin's complexity profile is different, can't be homogenized

**Accidental complexity (structure-driven, could be simplified):**

- ❌ **P0 issue:** `gen-compact.sh` hardcodes `claude -p` invocation (see Section 1.4)
- ⚠️ **Minor:** HTML comment convention requires agents to parse comments (could use YAML frontmatter instead)

**Verdict:** 1 P0 issue (CLI coupling), rest is necessary complexity.

### 3.4 Can Anything Be Deleted?

**Question:** Could the plan ship with fewer tasks?

**Dependency analysis:**

```
Task 1 (interwatch-scan.sh) — independent, ship separately
Task 2 (compact interwatch)  ─┐
Task 3 (compact interpath)   ─┤
Task 4 (compact interflux)   ─┴─→ Task 6 (wire loader) → Task 7 (tests)
                               │
                               └─→ Task 5 (gen-compact.sh)
```

**Minimal viable scope:** Tasks 2-3-4-5-6-7 (compact files + generator + wiring + tests)

**Excluded from minimal:** Task 1 (interwatch-scan.sh) — pre-computation is orthogonal to compact loading

**Recommendation:** Ship all 7 tasks. Task 1 is low-risk and high-value (moves deterministic work out of LLM context), and it's already scoped to a single plugin.

---

## 4. Critical Findings

### P0 (Must Fix Before Shipping)

#### P0-1: CLI Coupling in gen-compact.sh

**Issue:** Task 5 hardcodes `claude -p` invocation, coupling the build system to a specific Claude Code installation.

**Impact:** Breaks CI/CD, MCP-based generation, and standalone distribution.

**Fix:** Extract LLM invocation to a pluggable backend (see Section 1.4 for implementation).

**Location:** `Interverse/scripts/gen-compact.sh` (Task 5)

**Acceptance criteria:**

- `gen-compact.sh` accepts `--backend` flag (claude-cli, mcp, api)
- Default backend is `claude-cli` (preserves current behavior)
- Prompt template is extracted to a separate file or heredoc (reusable across backends)

---

## 5. Recommended Improvements (Optional)

### P1 (Strongly Recommended)

#### P1-1: Clarify gen-compact.sh Ownership

**Issue:** Plan doesn't specify whether `gen-compact.sh` lives in `Interverse/scripts/` vs. `plugins/interflux/scripts/` vs. `hub/clavain/scripts/`.

**Recommendation:** Place in `Interverse/scripts/` (monorepo-wide shared utility, like `interbump.sh`).

**Why:** Used by 3 plugins, not owned by any single one. Precedent exists (`interbump.sh`).

**Update required:** Revise Task 5's "Location" field to say `Interverse/scripts/gen-compact.sh`.

#### P1-2: Version Compact File Format

**Issue:** No versioning for compact file format. If the preamble convention changes (e.g., from `<!-- compact: ... -->` to YAML frontmatter), no migration path exists.

**Recommendation:** Add a version marker to compact files:

```markdown
<!-- compact-version: 1 -->
# Doc Watch (Compact)
...
```

**Why:** Enables safe evolution. If v2 compact files use a different structure, loaders can detect and handle both.

**Update required:** Add to Task 5's prompt template: "Include `<!-- compact-version: 1 -->` as the first line."

### P2 (Nice to Have)

#### P2-1: Extract Prompt Template to Separate File

**Issue:** Task 5 embeds the summarization prompt in the shell script as a heredoc. This couples the prompt design to the script implementation.

**Recommendation:** Extract to `Interverse/prompts/compact-skill.txt`:

```
Summarize this skill into a single compact instruction file (50-200 lines depending on complexity).
Keep: algorithm steps, decision points, output contracts, tables, code blocks.
Remove: examples, rationale, verbose descriptions, "why" explanations.
Add: "For edge cases or full reference, read SKILL.md" at the bottom.
```

**Why:**

- Prompt can be edited without modifying shell script
- Prompt can be reused across backends (MCP, API, standalone)
- Prompt can be versioned independently (if LLM quality improves, update prompt without touching script)

**Update required:** Add `Interverse/prompts/` directory, move prompt template there, update Task 5 to reference it.

#### P2-2: Parallel Generation in gen-compact.sh

**Issue:** If `gen-compact.sh` is extended to regenerate all compact files in the monorepo (e.g., `gen-compact.sh --all`), sequential LLM calls will be slow (3 skills × ~30s/skill = 90s).

**Recommendation:** Support parallel generation:

```bash
gen-compact.sh --all --parallel
```

Launches 3 `claude -p` subprocesses in parallel, waits for all to complete.

**Why:** CI/CD freshness checks will eventually need to regenerate all compact files. Parallel execution keeps build times reasonable.

**Update required:** Add to Task 5's acceptance criteria: "Support `--parallel` flag for batch generation."

---

## 6. Architectural Principles Applied

This review evaluated the plan against the following principles:

### 6.1 Boundaries & Coupling

✅ **Module boundaries respected:** Compact files live in their owning plugin's skill directory, not centralized

✅ **Dependency direction correct:** Tools depend on data (gen-compact.sh depends on SKILL.md), not vice versa

❌ **P0 violation:** `gen-compact.sh` couples to `claude` CLI (specific delivery mechanism)

### 6.2 Cohesion

✅ **High cohesion:** Each compact file is paired with its source (`SKILL.md` + `SKILL-compact.md` in same dir)

✅ **Single responsibility:** `gen-compact.sh` does one thing (generate compact files), `interwatch-scan.sh` does one thing (evaluate signals)

### 6.3 Abstraction Quality

✅ **Appropriate abstraction level:** HTML comment convention is simple, auditable, and reversible

⚠️ **Leaky abstraction (minor):** Agents must parse HTML comments to discover compact files (could use frontmatter instead)

✅ **No premature abstraction:** No plugin systems, no extensibility hooks, no speculative features

### 6.4 Simplicity

✅ **YAGNI compliance:** Out-of-scope list is well-justified (cross-session caching, Python scoring, token budgets)

✅ **Minimal viable scope:** 7 tasks, all necessary

✅ **Necessary complexity only:** Hash-based freshness tracking is the simplest reliable solution

### 6.5 Naming & Conventions

✅ **Consistent naming:** `SKILL-compact.md` follows existing `SKILL.md` convention

✅ **Discoverable:** HTML comment `<!-- compact: SKILL-compact.md -->` is greppable and human-readable

✅ **Conventional:** `.compact-manifest` follows existing dotfile patterns (`.git`, `.claude`, `.beads`)

---

## 7. Decision Ledger

| Decision | Rationale | Alternatives Considered | Verdict |
|----------|-----------|------------------------|---------|
| Compact files live alongside SKILL.md | Discoverability, atomic commits, plugin independence | Centralized in `Interverse/compact/` (rejected: breaks plugin boundaries) | ✅ Correct |
| Convention-based loader (HTML comment) | Agents are cooperative, graceful fallback, zero tooling changes | Enforcement via SKILL.md structure (rejected: destroys standalone readability) | ✅ Appropriate for context |
| Shared `gen-compact.sh` in `Interverse/scripts/` | Used by 3 plugins, precedent exists (`interbump.sh`) | Per-plugin scripts (rejected: unnecessary duplication) | ✅ Correct |
| LLM invocation via `claude -p` | Simple, works today | Backend abstraction (recommended: enables CI/CD, MCP, API) | ❌ P0 issue |
| Hash-based freshness tracking | Deterministic, fast, no LLM calls | Git mtime (rejected: unreliable after rebases) | ✅ Correct |
| Compact file format versioning | Enables safe evolution | No versioning (current plan) | ⚠️ P1 recommendation |

---

## 8. Recommendations Summary

### Must Fix (P0)

1. **Abstract LLM invocation in gen-compact.sh** — Extract to pluggable backend (claude-cli, mcp, api) to support CI/CD and standalone distribution.

### Strongly Recommended (P1)

1. **Clarify gen-compact.sh ownership** — Document that it lives in `Interverse/scripts/` as a monorepo-wide shared utility.
2. **Version compact file format** — Add `<!-- compact-version: 1 -->` to enable future migrations.

### Nice to Have (P2)

1. **Extract prompt template** — Move summarization prompt to `Interverse/prompts/compact-skill.txt` for reusability.
2. **Support parallel generation** — Add `--parallel` flag to `gen-compact.sh --all` for CI/CD performance.

---

## 9. Verdict

**Overall:** APPROVED with P0 fix required.

**Strengths:**

- Module boundaries are well-designed (co-location, plugin independence)
- Convention-based loader is appropriate for cooperative agents
- Cross-plugin consistency is enforced through shared tooling
- Scope discipline is excellent (no YAGNI violations)

**Critical fix:**

- P0: Abstract LLM invocation from `gen-compact.sh` to support multiple execution contexts

**When fixed, this design will:**

- Reduce token overhead by 60-70% for high-ceremony skills
- Preserve plugin modularity and independence
- Enable safe evolution via versioning and freshness tracking
- Support CI/CD, MCP, and standalone distribution

**Recommendation:** Fix P0 before implementation. Consider P1 recommendations strongly. Ship without P2 (can add post-launch).
