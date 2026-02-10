# Architecture Dependency Analysis: Thin-Section Deepening Removal

**Bead:** Clavain-dh6
**Scope:** Remove lines 79-109 from `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md`
**Date:** 2026-02-09
**Analyst:** architecture-strategist (system architecture review)

---

## 1. Architecture Overview

The flux-drive skill follows a strict four-phase pipeline:

```
Phase 1 (Analyze + Triage) --> Phase 2 (Launch) --> Phase 3 (Synthesize) --> Phase 4 (Cross-AI)
```

Phase 3 (`synthesize.md`) is responsible for collecting agent results, deduplicating findings, updating the input document, and reporting to the user. The block at lines 79-109 ("Deepen thin sections") is a sub-section of Step 3.4 ("Update the Document") that conditionally launches new `Task Explore` agents and Context7 MCP queries during synthesis to enrich sections classified as `thin` in Step 1.1.

---

## 2. Dependency Analysis: Five Questions

### 2.1 Does Phase 4 (cross-ai.md) reference or depend on deepened content?

**No.** Phase 4 has zero references to deepened content, "Research Insights" blocks, thin-section enrichment, or any artifact produced by lines 79-109. The only backward reference Phase 4 makes to Phase 3 is at line 21 of `cross-ai.md`:

> "Compare Oracle's findings with the synthesized findings from Step 3.2"

Step 3.2 is the "Collect Results" step, which reads agent output files. It is entirely upstream of Step 3.4 and is unaffected by the removal. Phase 4 consumes the deduplicated findings from Steps 3.2-3.3, not the document amendments from Step 3.4.

**Verdict: No dependency. Removal is safe with respect to Phase 4.**

### 2.2 Does SKILL.md reference the deepening feature?

**No.** SKILL.md references the `thin` classification in three contexts, none of which relate to deepening:

1. **Step 1.1 section analysis** (line 79): `[Section name]: [thin/adequate/deep]` -- this is the classification schema itself.
2. **Step 1.2 scoring rule 2** (line 107): "Agents scoring 1 are included only if their domain covers a thin section" -- this uses the `thin` classification for triage.
3. **Scoring examples** (lines 120, 131, 146-148): Worked examples showing how `thin` sections influence agent selection, plus threshold definitions.

SKILL.md never mentions "Research Insights", "deepen", "Task Explore" in the deepening context, or "Context7 MCP" in any context. The deepening feature is entirely self-contained within `synthesize.md` lines 79-109.

**Verdict: No dependency in SKILL.md. Removal is safe.**

### 2.3 Does the "thin" section classification still serve a purpose after removal?

**Yes, fully.** The `thin/adequate/deep` classification from Step 1.1 serves two distinct purposes:

1. **Triage gating (Step 1.2):** Agents scoring 1 ("maybe") are included only if they cover a thin section. This is the primary consumer of the `thin` classification and is located in SKILL.md lines 100-107. It remains entirely intact after the removal.

2. **Launch prompt hints (Phase 2, launch.md line 147):** The prompt template includes "Depth needed: [thin sections need more depth, deep sections need only validation]" to calibrate agent review depth. This also remains intact.

The deepening block was a third, optional consumer. After its removal, the `thin` classification retains two active consumers, both in the critical path. No orphaned data.

**Verdict: Classification remains fully purposeful. No cleanup needed.**

### 2.4 Are there downstream consumers of the "Research Insights" blocks?

**No.** A comprehensive search across the entire Clavain repository found the string "Research Insights" in exactly two locations:

1. `synthesize.md` line 85 -- the instruction to create the block (inside the removal target)
2. `synthesize.md` line 88 -- the markdown template for the block (inside the removal target)
3. `docs/research/explore-flux-drive-agent-definitions.md` line 545 -- historical research notes describing the feature

No phase, skill, agent, hook, or command reads, parses, or references "Research Insights" blocks after they would be written. The blocks are a terminal artifact: they are written into the input document and never machine-read afterward. Their only consumer is the human reader.

Furthermore, this feature has never been exercised in production. The code-simplicity-reviewer in the self-review notes it as "the least-exercised path and the most likely to fail silently." The `Task Explore` subagent type referenced in line 83 is itself undocumented -- the fd-code-quality agent flagged it as a P1 issue (undocumented subagent type that would fail silently at runtime).

**Verdict: No downstream consumers. The "Research Insights" output is a dead-end artifact.**

### 2.5 Does the removal affect the Phase 3 to Phase 4 handoff?

**No.** The Phase 3 to Phase 4 handoff occurs implicitly: Phase 4 begins after Phase 3 completes. Phase 4's Step 4.2 reads `{OUTPUT_DIR}/oracle-council.md` (written during Phase 2) and compares it against "the synthesized findings from Step 3.2" (the collected, deduplicated agent results).

The handoff depends on:
- Agent output files existing in `{OUTPUT_DIR}/` (written in Phase 2, verified in Step 3.0)
- Synthesis completing Steps 3.1-3.3 (validate, collect, deduplicate)
- The updated input document from Step 3.4 (the summary section and inline notes)

None of these artifacts are produced by the deepening block. The deepening block runs after the summary and inline notes are already written (it appears at the end of the "For file inputs" sub-section of Step 3.4). Removing it simply means synthesis completes earlier, at which point control passes to Phase 4 as before.

**Verdict: Handoff is unaffected. Phase 4 reads Phase 2 output and Phase 3 synthesis, neither of which involves deepened content.**

---

## 3. Structural Impact of Removal

### What changes in synthesize.md after removal

Lines 79-109 sit between two sibling sub-sections of Step 3.4:

- Lines 46-78: "For file inputs (plans, brainstorms, specs, etc.)" -- the main write-back logic. **Stays.**
- Lines 79-109: "Deepen thin sections (plans only)" -- the removal target.
- Lines 111-117: "For repo reviews (directory input, no specific file)" -- the repo review write-back. **Stays.**

After removal, the "For file inputs" sub-section ends at line 78 ("Write the updated document back to `INPUT_FILE`."), and the "For repo reviews" sub-section follows immediately. This is a clean seam -- no bridging text or structural repair is needed.

### What the removal eliminates

| Element | Description | Impact |
|---------|-------------|--------|
| `Task Explore` agent launch | Undocumented subagent type, would likely fail at runtime | Eliminates a latent failure path |
| Context7 MCP dependency | Only other Phase 3 reference to Context7; Step 1.0 also uses it independently | Reduces Phase 3 external dependencies |
| Secondary agent wave | Agents launched outside the Phase 2 cap of 8 | Eliminates cap bypass |
| Conditional logic | 31 lines of plan-only, thin-section-only branching | Simplifies Step 3.4 |

---

## 4. Risk Analysis

### Risks of removal: LOW

1. **Feature loss:** Users reviewing plans with thin sections will no longer get auto-researched enrichment appended. Mitigation: Users can manually invoke an explore agent or re-run flux-drive on the updated document. Multiple reviewers (code-simplicity, fd-architecture, fd-code-quality) independently recommended this as the preferred UX.

2. **Documentation drift:** Three research documents reference the deepening feature (`explore-flux-drive-agent-definitions.md`, `research-flux-drive-patterns.md`, `create-tier-3-beads-simplify.md`). These are historical research artifacts and do not need updating -- they document the decision process, not the current spec.

### Risks of keeping: MODERATE

1. **Silent failure at runtime:** `Task Explore` is an undocumented subagent type (P1 finding from fd-code-quality). If invoked, it may fail without a fallback.
2. **Phase boundary violation:** Launching new agents during synthesis violates the established phase contract (Phase 2 launches, Phase 3 reads). Three out of five self-review agents flagged this as an architectural concern.
3. **Cap bypass:** Deepening agents are not counted against the 8-agent cap, creating an uncontrolled resource expansion.

---

## 5. Recommendations

1. **Proceed with removal.** Lines 79-109 have zero downstream dependencies across all four phases, SKILL.md, and the broader Clavain plugin. The removal is a clean excision with no cascading changes required.

2. **No structural repair needed in synthesize.md.** The surrounding sections (file input write-back above, repo review write-back below) connect cleanly after the block is removed.

3. **No changes needed in SKILL.md, cross-ai.md, or launch.md.** The `thin` classification and its two remaining consumers are unaffected.

4. **No changes needed in research/historical documents.** They document the decision to remove, not the feature itself.

5. **Consider documenting the manual alternative.** A one-line note in the "For file inputs" section or in Step 3.5 (Report to User) could suggest: "For thin sections, consider running an explore agent or a second flux-drive pass for deeper coverage." This preserves the intent without the architectural violation. This is optional and could be handled in a separate bead if desired.

---

## Summary Table

| Question | Answer | Evidence |
|----------|--------|----------|
| Phase 4 depends on deepened content? | No | `cross-ai.md` references only Step 3.2; zero mentions of Research Insights or deepening |
| SKILL.md references deepening? | No | `thin` used only for triage (Step 1.2) and launch hints (Phase 2) |
| `thin` classification still useful? | Yes | Two active consumers remain: Step 1.2 triage gating, Phase 2 prompt hints |
| Research Insights has downstream consumers? | No | Only produced and consumed in the removal target; never read by any other component |
| Phase 3-to-4 handoff affected? | No | Phase 4 reads Phase 2 output + Step 3.2 synthesis; deepening runs after both |

**Conclusion:** Bead Clavain-dh6 can proceed. The removal of lines 79-109 is architecturally safe with no cascading dependencies.
