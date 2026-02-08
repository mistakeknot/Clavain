---
agent: fd-code-quality
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Skill Conventions"
    title: "agent-native-architecture/SKILL.md uses 9 XML tags instead of markdown headings"
  - id: P1-1
    severity: P1
    section: "Skill Conventions"
    title: "engineering-docs/SKILL.md has duplicate heading pairs from XML-to-markdown conversion"
  - id: P2-1
    severity: P2
    section: "Command Conventions"
    title: "Inconsistent argument-hint quoting across commands"
  - id: P2-2
    severity: P2
    section: "Agent Conventions"
    title: "pr-comment-resolver.md has undocumented 'color: blue' frontmatter field"
improvements:
  - id: IMP-1
    title: "AGENTS.md convention says 'third-person' but canonical example uses second-person imperative"
    section: "AGENTS.md Conventions"
  - id: IMP-2
    title: "using-clavain/SKILL.md uses EXTREMELY-IMPORTANT XML tag — consider markdown alternative"
    section: "Skill Conventions"
  - id: IMP-3
    title: "file-todos/SKILL.md example data uses 'rails' tag — could confuse Rails-content scanners"
    section: "Skill Content"
verdict: needs-changes
---

# Code Quality Review: Post-Cleanup Convention Adherence

## Summary

Systematic review of all 32 skills, 23 agents, and 24 commands in the Clavain plugin following the 13-issue flux-drive cleanup. The cleanup was largely successful: all 32 skill descriptions now follow the "Use when/before" pattern, all 23 agents have proper `<example>` blocks with `<commentary>`, all namespace references (`superpowers:`, `compound-engineering:`) have been scrubbed, and the `work`/`execute-plan` cross-references are in place. However, one skill (`agent-native-architecture`) was missed in the XML-to-markdown conversion, and `engineering-docs` has residual duplicate headings from its conversion.

## Section-by-Section Review

### 1. Skill Descriptions (32/32)

**Convention (AGENTS.md line 88, 92, 98):** Description should start with trigger phrases; canonical example uses "Use when..." pattern.

**Result: PASS -- all 32 skills conform.**

Every skill description starts with either "Use when" (31 skills) or "Use before" (1 skill: `brainstorming`). The 9 skills noted as normalized in the cleanup are verified clean. No stragglers remain.

Full list verified against files at `/root/projects/Clavain/skills/*/SKILL.md` line 3.

### 2. Skill Name-to-Directory Match (32/32)

**Convention (AGENTS.md line 87):** `name` in frontmatter must match directory name.

**Result: PASS -- all 32 match exactly.**

Cross-referenced all `name:` lines from `/root/projects/Clavain/skills/*/SKILL.md` line 2 against their parent directory names.

### 3. XML Tags in Skill Bodies

**Convention (create-agent-skills/SKILL.md line 19, 269):** "No XML tags -- use standard markdown headings."

**Result: FAIL -- 1 skill uses XML tags extensively.**

`/root/projects/Clavain/skills/agent-native-architecture/SKILL.md` contains 9 XML tag pairs:

| Line | Opening Tag | Closing Tag |
|------|------------|-------------|
| 6 | `<why_now>` | `</why_now>` (line 16) |
| 18 | `<core_principles>` | `</core_principles>` (line 154) |
| 156 | `<intake>` | `</intake>` (line 174) |
| 176 | `<routing>` | `</routing>` (line 194) |
| 196 | `<architecture_checklist>` | `</architecture_checklist>` (line 239) |
| 241 | `<quick_start>` | `</quick_start>` (line 276) |
| 278 | `<reference_index>` | `</reference_index>` (line 302) |
| 304 | `<anti_patterns>` | `</anti_patterns>` (line 388) |
| 390 | `<success_criteria>` | `</success_criteria>` (line 435) |

Each XML tag wraps a section that already has a markdown `##` heading immediately inside it, making the XML tags redundant. The `engineering-docs` skill had the same issue and was cleaned up successfully; `agent-native-architecture` was missed.

Additionally, `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 6 uses `<EXTREMELY-IMPORTANT>` / `</EXTREMELY-IMPORTANT>`. This is a different case -- it's an emphasis construct in the bootstrap routing skill, not a section wrapper. Flagged as improvement rather than issue.

### 4. Skill Line Counts

**Convention (create-agent-skills/SKILL.md line 203, AGENTS.md line 90):** SKILL.md under 500 lines.

**Result: PASS -- all 32 skills are under 500 lines.**

Largest files checked: `writing-skills` (469 lines), `engineering-docs` (336 lines), `agent-native-architecture` (318 lines), `mcp-cli` (281 lines), `flux-drive` (261 lines).

### 5. Agent Descriptions with Example Blocks (23/23)

**Convention (AGENTS.md line 106):** Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger.

**Result: PASS -- all 23 agents have both `<example>` and `<commentary>` tags.**

Verified via Grep: exactly 23 files contain `<example>` and exactly 23 files contain `<commentary>`, with a 1:1 match (every agent has at least one of each).

### 6. Agent Category Distribution

**Convention (AGENTS.md lines 111-113):** review/ (15), research/ (5), workflow/ (3).

**Result: PASS -- counts match exactly.**

- `/root/projects/Clavain/agents/review/` -- 15 files
- `/root/projects/Clavain/agents/research/` -- 5 files
- `/root/projects/Clavain/agents/workflow/` -- 3 files

### 7. Agent Model Field

**Convention (AGENTS.md line 105):** `model` field, "usually `inherit`".

**Result: PASS -- 22 agents use `inherit`, 1 uses `haiku`.**

`/root/projects/Clavain/agents/research/learnings-researcher.md` uses `model: haiku`. This appears intentional -- the learnings-researcher is a lightweight metadata-search agent where Haiku is sufficient and cost-effective. Not flagged as a violation.

### 8. Command Naming (24/24)

**Convention (AGENTS.md line 117):** Flat `.md` files in `commands/`, kebab-case names.

**Result: PASS -- all 24 commands are kebab-case, and all `name` fields match filenames.**

Verified: `heal-skill`, `clodex`, `upstream-sync`, `resolve-todo-parallel`, `lfg`, `changelog`, `repro-first-debugging`, `triage`, `create-agent-skill`, `agent-native-audit`, `quality-gates`, `generate-command`, `migration-safety`, `learnings`, `codex-first`, `execute-plan`, `write-plan`, `resolve-pr-parallel`, `work`, `plan-review`, `brainstorm`, `review`, `resolve-parallel`, `flux-drive`.

### 9. Command Descriptions

**Convention (AGENTS.md line 118):** Frontmatter includes `name`, `description`, `argument-hint` (optional).

**Result: PARTIAL PASS -- descriptions are accurate, but `argument-hint` formatting is inconsistent.**

5 commands lack `argument-hint` entirely: `clodex`, `codex-first`, `upstream-sync`, `execute-plan`, `write-plan`. These are toggle commands or skill-delegation commands that legitimately take no arguments, so missing `argument-hint` is appropriate.

However, among commands that DO have `argument-hint`, quoting is inconsistent:
- **Unquoted:** `heal-skill.md` (`[optional: specific issue to fix]`), `create-agent-skill.md` (`[skill description or requirements]`)
- **Quoted:** All other 19 commands use `"[...]"` format

### 10. Cross-References (work / execute-plan)

**Convention:** Cleanup added symmetric cross-references between `/work` and `/execute-plan`.

**Result: PASS -- cross-references are present and symmetric.**

- `/root/projects/Clavain/commands/work.md` line 15: `> **When to use this vs /execute-plan:** Use /work for autonomous feature shipping...`
- `/root/projects/Clavain/commands/execute-plan.md` line 7: `> **When to use this vs /work:** Use /execute-plan for detailed, multi-step implementation plans...`

### 11. Namespace Scrubbing

**Convention (CLAUDE.md, AGENTS.md line 170-171):** No references to dropped namespaces.

**Result: PASS -- clean.**

Grep for `superpowers:` and `compound-engineering:` across all skills, agents, and commands returned zero matches.

### 12. Domain-Specific Content Removal

**Convention (CLAUDE.md line 26):** No Rails, Ruby gems, Every.to, Figma, Xcode content.

**Result: PASS -- no domain-specific content.**

Three grep matches for "rails" are all false positives:
- `/root/projects/Clavain/skills/file-todos/SKILL.md` line 64: `tags: [rails, performance, database]` -- example data in a todo template
- `/root/projects/Clavain/skills/file-todos/SKILL.md` line 224: `grep -l "tags:.*rails" todos/*.md` -- example search command
- `/root/projects/Clavain/skills/agent-native-architecture/SKILL.md` line 149: "safety rails" -- the word "rails" as guardrails, not Ruby on Rails

### 13. Routing Table Accuracy

**Convention (AGENTS.md line 172):** Routing table in `using-clavain/SKILL.md` must be consistent with actual components.

**Result: PASS -- routing table is accurate.**

Cross-referenced all skills, agents, and commands listed in the routing table (`/root/projects/Clavain/skills/using-clavain/SKILL.md` lines 32-66) against actual files. All referenced components exist. Component counts in the header (line 22: "32 skills, 23 agents, and 24 commands") match actual counts.

### 14. AGENTS.md Conventions Accuracy

**Convention section (AGENTS.md lines 83-130):** Documents component conventions.

**Result: MOSTLY ACCURATE -- one minor wording inconsistency.**

Line 88 says descriptions should be "third-person, with trigger phrases" but the canonical example on line 98 uses "Use when encountering any bug..." which is second-person imperative. All 32 actual skill descriptions follow the second-person "Use when/before" pattern, matching the example but not the prose description. The example should be authoritative since it matches actual practice.

### 15. Duplicate Headings in engineering-docs

**Result: FAIL -- residual duplicate headings from XML-to-markdown conversion.**

`/root/projects/Clavain/skills/engineering-docs/SKILL.md` has three pairs of duplicate/redundant headings:

| Lines | Issue |
|-------|-------|
| 26, 28 | `## Documentation Capture Sequence` immediately followed by `## 7-Step Process` |
| 326, 328 | `## Integration Protocol` immediately followed by `## Integration Points` |
| 344, 346 | `## Success Criteria` repeated on consecutive lines |

These appear to be artifacts from XML-to-markdown conversion where the XML tag name became one heading and the markdown heading inside it became another.

### 16. Undocumented Frontmatter Fields

**Result: Minor inconsistency -- `color` field not documented.**

`/root/projects/Clavain/agents/workflow/pr-comment-resolver.md` line 4 has `color: blue`. No other agent uses this field, and it is not documented in AGENTS.md conventions. This may be a Claude Code API feature that was added for visual differentiation, or it could be a leftover from the compound-engineering source.

---

## Issues Found

### P0-1: agent-native-architecture/SKILL.md uses XML tags [P0 -- Convention Violation]

**Location:** `/root/projects/Clavain/skills/agent-native-architecture/SKILL.md`
**Convention:** `create-agent-skills/SKILL.md` line 19: "No XML tags -- use standard markdown headings"; line 269: anti-pattern "XML tags in body"
**Violation:** 9 XML tag pairs (`<why_now>`, `<core_principles>`, `<intake>`, `<routing>`, `<architecture_checklist>`, `<quick_start>`, `<reference_index>`, `<anti_patterns>`, `<success_criteria>`) wrap sections that already have markdown `##` headings inside them.
**Fix:** Remove all 9 opening and closing XML tags. The `##` headings inside them already provide the same structure. This is the same conversion that was successfully applied to `engineering-docs/SKILL.md`.

### P1-1: engineering-docs/SKILL.md has duplicate heading pairs [P1 -- Cleanup Residue]

**Location:** `/root/projects/Clavain/skills/engineering-docs/SKILL.md` lines 26/28, 326/328, 344/346
**Convention:** Standard markdown structure; each section should have one heading.
**Violation:** Three pairs of redundant headings exist where the XML-to-markdown conversion produced two headings per section.
**Fix:** For each pair, keep the more descriptive heading and remove the other:
- Lines 26-28: Keep `## 7-Step Process`, remove `## Documentation Capture Sequence` (or merge them)
- Lines 326-328: Keep `## Integration Points`, remove `## Integration Protocol` (or merge them)
- Lines 344-346: Remove one of the two `## Success Criteria` headings

### P2-1: Inconsistent argument-hint quoting [P2 -- Minor Formatting]

**Location:** `/root/projects/Clavain/commands/heal-skill.md` line 4, `commands/create-agent-skill.md` line 5
**Convention:** 19 of 21 commands with `argument-hint` use `"[...]"` quoted format.
**Violation:** 2 commands use unquoted `[...]` format.
**Fix:** Add quotes around the `argument-hint` values:
- `heal-skill.md`: `argument-hint: "[optional: specific issue to fix]"`
- `create-agent-skill.md`: `argument-hint: "[skill description or requirements]"`

### P2-2: Undocumented 'color' field in pr-comment-resolver [P2 -- Minor Inconsistency]

**Location:** `/root/projects/Clavain/agents/workflow/pr-comment-resolver.md` line 4
**Convention:** AGENTS.md line 105 documents agent frontmatter fields as `name`, `description`, `model`. No mention of `color`.
**Violation:** `color: blue` is present in one agent and absent from all others.
**Fix:** Either document `color` as an optional field in AGENTS.md conventions, or remove it from `pr-comment-resolver.md` if it has no functional effect.

---

## Improvements Suggested

### IMP-1: AGENTS.md convention wording contradicts canonical example

**Location:** `/root/projects/Clavain/AGENTS.md` line 88
**Current:** "description (third-person, with trigger phrases)"
**Actual practice:** All 32 skills use second-person imperative "Use when..." which matches the example on line 98 but contradicts "third-person."
**Suggestion:** Change line 88 to: "description (imperative `Use when...` pattern, with trigger phrases)" to match actual convention.

### IMP-2: using-clavain/SKILL.md EXTREMELY-IMPORTANT XML tag

**Location:** `/root/projects/Clavain/skills/using-clavain/SKILL.md` lines 6-12
**Current:** Uses `<EXTREMELY-IMPORTANT>` / `</EXTREMELY-IMPORTANT>` XML tags for emphasis.
**Context:** This skill is special -- it's injected via SessionStart hook as system context, not loaded via the Skill tool. The XML emphasis may be intentionally directing model attention.
**Suggestion:** Consider replacing with markdown emphasis (bold heading + blockquote) for consistency with the "no XML tags" convention. However, if the XML tag produces measurably better compliance in the session-start context, keeping it is justified. Flag for A/B testing rather than immediate removal.

### IMP-3: file-todos example data uses 'rails' tag

**Location:** `/root/projects/Clavain/skills/file-todos/SKILL.md` lines 64, 224
**Current:** Example todo template includes `tags: [rails, performance, database]` and a grep example searching for `tags:.*rails`.
**Context:** This is example data, not actual Rails content. However, it could trigger false positives in future Rails-content scans (as it did in this review).
**Suggestion:** Replace `rails` with a domain-neutral example tag like `api` or `backend` to prevent future scanner noise: `tags: [api, performance, database]`.

---

## Overall Assessment

**Verdict: needs-changes**

The 13-issue flux-drive cleanup was largely successful. The major wins are:
- All 32 skill descriptions normalized to "Use when/before" pattern
- All namespace references scrubbed
- Cross-references between work/execute-plan added
- Agent category counts match documentation
- Routing table is accurate

Two issues require attention:
1. **P0-1** is the most significant: `agent-native-architecture/SKILL.md` was missed in the XML-to-markdown conversion. It has 9 redundant XML tag pairs that violate the project's own skill-writing conventions. The fix is straightforward -- delete the XML tags, keep the markdown headings that are already inside them.
2. **P1-1** is cleanup residue: `engineering-docs/SKILL.md` was converted but left behind 3 pairs of duplicate headings.

The P2 issues are minor formatting inconsistencies that don't affect functionality.

### Top 3 Changes for Better Consistency

1. **Remove XML tags from `agent-native-architecture/SKILL.md`** -- 9 tag pairs, same conversion pattern already applied to `engineering-docs`
2. **Deduplicate headings in `engineering-docs/SKILL.md`** -- 3 heading pairs from the XML conversion
3. **Update AGENTS.md line 88** -- change "third-person" to match the actual "Use when" imperative convention used by all 32 skills
