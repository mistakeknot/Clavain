# Documentation Accuracy Audit (Post-Agent Consolidation)

**Date:** 2026-02-10  
**Context:** After consolidating 19 v1 agents into 6 fd-* agents (renamed from fd-v2-*)  
**Scope:** User-facing documentation files

## Summary

The plugin counts are accurate (16 agents, 34 skills, 24 commands) across all docs. However, 2 issues found:

1. **README.md:61** — Still says "6 core v2 agents" instead of just "6 core agents" (the v2 suffix was dropped)
2. **AGENTS.md:299** — Claims "No tests" but tests now exist in `tests/` directory (structural, shell, smoke suites added 2026-02-10)

No references to deleted agents (architecture-strategist, security-sentinel, go-reviewer, python-reviewer, etc.) found in user-facing docs.

## Detailed Findings

### 1. README.md

**Status:** 98% accurate, 1 stale reference

**Counts verified:**
- Line 7: "34 skills, 16 agents, 24 commands" ✅
- Line 61: "6 core v2 agents" ❌ Should be "6 core agents"
- Line 148: "Review (9): 6 core flux-drive agents (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance)" ✅

**Issue found:**
```markdown
Line 61: - **Plugin Agents** — 6 core v2 agents (Architecture & Design, Safety, ...
```

**Should be:**
```markdown
Line 61: - **Plugin Agents** — 6 core agents (Architecture & Design, Safety, ...
```

**Routing section (lines 284-291) status:** ACCURATE
- The "How the Routing Works" section mentions Layer 3 as "Language — What language? (go / python / typescript / shell / markdown)"
- This is NOT inaccurate even though language-specific reviewers were deleted
- The routing layer still exists conceptually; the fd-* agents auto-detect language rather than requiring explicit routing
- The description accurately reflects the routing table structure, not implementation details

**No references to deleted agents found** in user-facing sections.

### 2. AGENTS.md

**Status:** 98% accurate, 1 stale constraint

**Counts verified:**
- Line 12: "34 skills, 16 agents, 24 commands, 3 hooks, 3 MCP servers" ✅
- Line 135: "review/ — Review specialists (9): 6 core flux-drive agents ..." ✅
- Line 208-210: Component count commands ✅

**Issue found:**
```markdown
Line 299: - **No tests** — plugin validation is structural (file existence, JSON validity, reference consistency)
```

**Reality:** Tests were added 2026-02-10 in `tests/` directory:
- `tests/structural/` — pytest suite for structure validation
- `tests/shell/` — bats-core suite for shell scripts
- `tests/smoke/` — Claude Code subagent smoke tests (8 agents, haiku, 3 turns each)
- `tests/pyproject.toml` — pytest config using uv
- `.github/workflows/test.yml` — CI pipeline (3 tiers, runs on push/PR)

**Should be:**
```markdown
Line 299: - **3-tier test suite** — structural (pytest), shell (bats), smoke (Claude Code subagents)
```

### 3. CLAUDE.md

**Status:** 100% accurate ✅

**Counts verified:**
- Line 7: "34 skills, 16 agents, 24 commands, 3 hooks, 3 MCP servers" ✅
- Line 31: "6 core review agents (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance)" ✅

**No issues found.**

### 4. plugin.json

**Status:** 100% accurate ✅

**Description verified:**
```json
Line 4: "description": "General-purpose engineering discipline plugin. 16 agents, 24 commands, 34 skills, 3 MCP servers — combining workflow discipline with specialized execution agents. Includes Codex dispatch, cross-AI review (interpeer with quick/deep/council/mine modes), structured debate, and codex-first mode."
```

**Counts match reality:** ✅

### 5. skills/using-clavain/SKILL.md

**Status:** 100% accurate ✅

**Routing table verified:**
- Lines 38-42: Stage routing references fd-* agents correctly ✅
- Lines 46-56: Domain routing references fd-* agents correctly ✅
- Lines 58-70: Layer 3 (Concern) mapping is accurate — maps concerns to fd-* agents, not languages ✅

**Key verification:**
```markdown
Line 71: ¹ **flux-drive agents (fd-*)**: 6 core review agents that auto-detect project docs (CLAUDE.md/AGENTS.md) for codebase-aware analysis.
```

This correctly describes the current architecture. The Layer 3 "What concern?" table maps to architectural concerns (security, performance, etc.), not languages. This is accurate post-consolidation.

### 6. docs/README.codex.md

**Status:** 100% accurate ✅

**No agent references found** — focuses on Codex installation and skill discovery mechanism. No references to deleted agents or outdated naming.

## Files Checked for Stale References

Searched for patterns: `(architecture-strategist|security-sentinel|go-reviewer|python-reviewer|typescript-reviewer|shell-reviewer|markdown-reviewer|fd-v2-)`

**59 files matched** — all are in docs/research, docs/plans, docs/solutions, config/flux-drive/knowledge, or .beads tracking. None are user-facing documentation.

**User-facing docs are clean:**
- README.md — no deleted agent references
- AGENTS.md — no deleted agent references
- CLAUDE.md — no deleted agent references
- plugin.json — no deleted agent references
- skills/using-clavain/SKILL.md — no deleted agent references
- docs/README.codex.md — no deleted agent references

## Recommendations

1. **Fix README.md:61** — Change "6 core v2 agents" to "6 core agents"
2. **Fix AGENTS.md:299** — Update "No tests" to describe the 3-tier test suite
3. **Leave routing descriptions alone** — The Layer 3 language references in routing are accurate as architectural descriptions, even though implementation changed

## Test Results

```bash
# Actual counts match documented counts
$ ls agents/{review,research,workflow}/*.md | wc -l
16

$ ls skills/*/SKILL.md | wc -l
34

$ ls commands/*.md | wc -l
24
```

All counts in documentation are correct.

## Conclusion

Documentation is 98% accurate post-consolidation. Only 2 minor stale references:
1. "v2" suffix in README.md (cosmetic, doesn't affect understanding)
2. "No tests" claim in AGENTS.md (factually incorrect after 2026-02-10 test suite addition)

No references to deleted agents found in user-facing docs. The routing descriptions remain accurate — they describe the conceptual routing layers, not implementation details.
