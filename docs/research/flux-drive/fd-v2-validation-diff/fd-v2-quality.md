### Findings Index
- LOW | Q-01 | "Shell Script" | validate-roster.sh missing trap cleanup
- LOW | Q-02 | "Shell Script" | Hardcoded emoji in non-interactive output
- MEDIUM | Q-03 | "Agent Files" | All 6 fd-v2 agents missing `<example>` blocks in description
- LOW | Q-04 | "Agent Files" | fd-v2-correctness uses persona name "Julik" inconsistent with other agents
- LOW | Q-05 | "Agent Files" | Inconsistent section structure across fd-v2 agents
- LOW | Q-06 | "Agent Files" | fd-v2-quality uses `##` for "Universal Review" under `## Review Approach` (heading level mismatch)
- INFO | Q-07 | "Knowledge README" | Well-structured, no issues found
- INFO | Q-08 | "Shell Script" | validate-roster.sh overall quality is good

Verdict: needs-changes

---

### Summary

Reviewed 8 files: 1 shell script (`scripts/validate-roster.sh`), 6 agent markdown files (`agents/review/fd-v2-*.md`), and 1 knowledge layer README (`config/flux-drive/knowledge/README.md`). The shell script is solid. The knowledge README is clean and well-designed. The main issue is that all 6 fd-v2 agent files are missing the `<example>` blocks that AGENTS.md documents as a required convention for agent descriptions. One agent (fd-v2-correctness) uses a persona name that breaks consistency with the other five.

---

### Issues Found

#### Q-01 [LOW] — validate-roster.sh missing trap cleanup

**File:** `/root/projects/Clavain/scripts/validate-roster.sh`
**Lines:** 1-63 (entire file)

The script uses `set -euo pipefail` (good) and has no temp files, no background jobs, and no locks. In this specific case, there is nothing to clean up, so the absence of `trap` is benign. However, the shell review checklist calls for `trap`-based cleanup. If the script ever grows to use temp files, the pattern should be added.

**Verdict:** No action needed now. Note for future expansion.

---

#### Q-02 [LOW] — Hardcoded emoji in non-interactive output

**File:** `/root/projects/Clavain/scripts/validate-roster.sh`, line 62
**Code:**
```bash
echo "✓ All 6 roster entries validated"
```

The checkmark emoji `✓` may not render correctly in all terminal/CI environments. More importantly, the message hardcodes "6" instead of using `$EXPECTED_COUNT`, creating a maintenance drift risk if `EXPECTED_COUNT` changes.

**Recommendation:** Use `$EXPECTED_COUNT` in the success message:
```bash
echo "OK: All $EXPECTED_COUNT roster entries validated"
```

---

#### Q-03 [MEDIUM] — All 6 fd-v2 agents missing `<example>` blocks in description

**Files:**
- `/root/projects/Clavain/agents/review/fd-v2-architecture.md`, line 3
- `/root/projects/Clavain/agents/review/fd-v2-quality.md`, line 3
- `/root/projects/Clavain/agents/review/fd-v2-safety.md`, line 3
- `/root/projects/Clavain/agents/review/fd-v2-correctness.md`, line 3
- `/root/projects/Clavain/agents/review/fd-v2-user-product.md`, line 3
- `/root/projects/Clavain/agents/review/fd-v2-performance.md`, line 3

Per AGENTS.md (line 127-128):
> YAML frontmatter: `name`, `description` (with `<example>` blocks showing when to trigger), `model` (usually `inherit`)
> Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger

All existing review agents (e.g., `architecture-strategist.md`, `fd-code-quality.md`) include `<example>` blocks in their `description` field. None of the 6 new fd-v2 agents do. This is a documented convention violation.

**Why it matters:** The `<example>` blocks help Claude Code's routing decide when to dispatch these agents. Without them, the agents rely entirely on the flux-drive skill's explicit roster dispatch, which works but breaks the convention that agents should be self-documenting for ad-hoc invocation.

**Recommendation:** Add at least one `<example>` block with `<commentary>` to each fd-v2 agent's `description` frontmatter, following the pattern established by `architecture-strategist.md` and `fd-code-quality.md`.

---

#### Q-04 [LOW] — fd-v2-correctness uses persona name "Julik" inconsistent with other agents

**File:** `/root/projects/Clavain/agents/review/fd-v2-correctness.md`, line 7
**Code:**
```
You are Julik, the Flux-drive v2 Correctness Reviewer: half data-integrity guardian, half concurrency bloodhound.
```

All other 5 fd-v2 agents use generic role introductions:
- fd-v2-architecture: "You are a Flux-drive v2 Architecture & Design Reviewer."
- fd-v2-quality: "You are the Flux-drive v2 Quality & Style Reviewer."
- fd-v2-safety: "You are a Flux-drive v2 Safety Reviewer."
- fd-v2-user-product: "You are the Flux-drive v2 User & Product Reviewer."
- fd-v2-performance: "You are a Flux-drive v2 Performance Reviewer."

fd-v2-correctness names itself "Julik" and uses a colorful persona description ("half data-integrity guardian, half concurrency bloodhound"). This is a style choice, but it breaks the naming pattern of the other 5 agents.

Additionally, fd-v2-correctness has a unique "Communication Style" section (lines 72-78) and a "Failure Narrative Method" section (lines 66-70) that no other agent has. These are not inherently bad — they fit the correctness domain — but they diverge from the structural template.

**Recommendation:** Consider whether the persona name and unique tone adds enough value to justify the inconsistency. If the intent is a uniform agent family, standardize the opening. If individual personality is desired, that's a deliberate choice to document.

---

#### Q-05 [LOW] — Inconsistent section structure across fd-v2 agents

**Files:** All 6 fd-v2 agents

The agents share a common skeleton but diverge in their section structure:

| Section | arch | quality | safety | correct | user-prod | perf |
|---------|------|---------|--------|---------|-----------|------|
| First Step (MANDATORY) | yes | yes | yes | yes | yes | yes |
| Review Approach | yes | yes | -- | yes | -- | yes |
| (Domain sections) | 3 subsections | 2 sections | 2 major sections | 2 subsections | 4 sections | 6 subsections |
| What NOT to Flag | -- | yes | yes | -- | -- | yes |
| Focus Rules | yes | yes | yes | -- | yes | yes |
| Decision Lens | yes | -- | -- | -- | yes | -- |
| Risk Prioritization | -- | -- | yes | -- | -- | -- |
| Prioritization | -- | -- | -- | yes | -- | -- |
| Failure Narrative Method | -- | -- | -- | yes | -- | -- |
| Communication Style | -- | -- | -- | yes | -- | -- |
| Measurement Discipline | -- | -- | -- | -- | -- | yes |
| Evidence Standards | -- | -- | -- | -- | yes | -- |

Observations:
- **"What NOT to Flag"** appears in quality, safety, and performance but not architecture, correctness, or user-product. This is the most useful standardization candidate — it prevents false positives uniformly.
- **"Focus Rules"** is missing from correctness (it has "Prioritization" instead, which serves a similar purpose).
- **"Decision Lens"** only appears in architecture and user-product.
- **"Review Approach"** heading is missing from safety and user-product — they jump directly into domain sections.

None of these inconsistencies are bugs. The agents work. But the inconsistency makes it harder to maintain the family as a unit — you have to remember which agent uses which section names.

**Recommendation:** Establish a canonical section template for the fd-v2 family and align all 6. A reasonable template:
1. First Step (MANDATORY) — all agents
2. Review Approach — all agents (wraps domain subsections)
3. What NOT to Flag — all agents
4. Focus Rules — all agents
5. (Optional domain-specific sections like Decision Lens, Measurement Discipline, etc.)

---

#### Q-06 [LOW] — fd-v2-quality heading level mismatch

**File:** `/root/projects/Clavain/agents/review/fd-v2-quality.md`, lines 21-24
**Code:**
```markdown
## Review Approach

## Universal Review

- **Naming consistency**: ...
```

Line 21 has `## Review Approach` and line 23 has `## Universal Review`, both at the same heading level. Given that "Universal Review" is a subsection of "Review Approach", it should be `### Universal Review`. Compare with fd-v2-architecture where subsections under `## Review Approach` use `### 1. Boundaries & Coupling`, `### 2. Pattern Analysis`, etc.

Similarly, line 33 has `## Language-Specific Checks` which should also be `###` if it's under Review Approach.

**Recommendation:** Change lines 23 and 33 from `##` to `###`:
```markdown
## Review Approach

### Universal Review
...

### Language-Specific Checks
...
```

---

### Improvements Suggested

1. **Q-03 is the only medium-severity item.** Adding `<example>` blocks to the 6 agents is the highest-value fix — it aligns with documented conventions and improves routing discoverability.

2. **Q-02 is a quick win.** Replacing the hardcoded "6" with `$EXPECTED_COUNT` takes 10 seconds and eliminates a maintenance drift vector.

3. **Q-05 and Q-06 are polish.** Standardizing section structure and fixing heading levels improves the agent family's maintainability as a unit.

4. **Q-04 is a style decision**, not a bug. The persona in fd-v2-correctness may be intentional — it just needs to be a conscious choice.

---

### Overall Assessment

The fd-v2 feature commit is well-built. The shell script is clean, properly uses strict mode, quotes variables correctly, handles errors sensibly, and avoids injection-prone patterns. The 6 agent files are substantive, domain-appropriate, and well-written — their review prompts are specific and actionable rather than generic checklists.

The knowledge layer README is excellent — the provenance/decay/sanitization design is thoughtful and well-documented.

The main gap is the missing `<example>` blocks (Q-03), which is a documented project convention that all existing agents follow. This should be addressed before the agents are considered convention-compliant. Everything else is low-severity polish.

**Quality gate:** Safe to ship as-is. The `<example>` blocks should be added in a follow-up pass.
<!-- flux-drive:complete -->
