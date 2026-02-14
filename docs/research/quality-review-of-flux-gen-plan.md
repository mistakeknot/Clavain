# Quality Review: Add Success Criteria to flux-gen Template

**Plan:** `/root/projects/Clavain/docs/plans/2026-02-13-flux-gen-success-criteria.md`
**Date:** 2026-02-13
**Reviewer:** Flux-drive Quality & Style Reviewer
**Status:** Actionable — minor gaps require clarification before implementation

---

## Executive Summary

The plan is well-scoped, strategically sound, and operationally ready. It addresses a real gap (generated agents lack quality calibration mechanisms) by injecting domain-specific success criteria into the flux-gen template. The design draws appropriately from core agents' proven patterns (Failure Narrative, Focus Rules, Communication Style). All three tasks are properly sequenced and measurable.

**Key Findings:**
- **P1 (Correctness):** Template variable injection logic must be clarified — is {domain-name} substituted at generation time or runtime?
- **P2 (Scope):** Task 2 scope is unclear — will hints be retroactively added to all 11 domains or only the 3 examples?
- **P2 (Implementation):** Decision lens impact on Success Criteria section unclear — potential overlap or redundancy

---

## Detailed Findings by Priority

### P1: Template Variable Substitution Logic (Correctness)

**Issue:** The template shows `{domain-name}` and `{domain_success_hints — if present in profile, appended...}` but the mechanics are underspecified.

**Current state:**
- Line 42: `A good {domain-name} review:` — implies string substitution at generation time
- Line 48: `{domain_success_hints — if present in profile, appended as additional bullets}` — implies conditional appending

**What's missing:**
1. **Substitution timing:** When is `{domain-name}` replaced? In the flux-gen command itself (Python), or in Step 4's template expansion?
2. **Conditional logic:** Does Step 4 check for the presence of "Success criteria hints" in the profile and conditionally include it, or does the generated file contain a placeholder that is resolved later?
3. **Human readability:** The generated agent file should be readable standalone — does this mean the substitution happens at file-write time (preferred) or does it happen at prompt injection time (less readable)?

**Recommendation:**
Add a sub-section under "Template Design" titled "Substitution Mechanics" with pseudo-code or algorithm:

```
For each domain:
  1. Load agent spec from domain profile
  2. Substitute {domain-name} with domain's human-readable name (e.g. "game simulation" not "game-simulation")
  3. Extract "Success criteria hints" from each agent spec's Agent Specifications section if present
  4. If hints exist: append them as additional bullet points; else: omit the placeholder line entirely
  5. Write final markdown to generated agent file
```

Also clarify: what is the domain's "human-readable name"? Is it in a separate metadata field in the profile, or derived from the YAML key (e.g. `game-simulation` → `game simulation`)?

**Impact:** Without this, the implementation step will have ambiguity about where and how to interpolate. Slightly delays Task 1, does not block it.

---

### P2: Task 2 Scope Ambiguity (Scope/Planning)

**Issue:** Task 2 is described as "add hints to 2-3 domains as examples" but leaves open whether the full 11 domains should eventually have hints.

**Current state:**
- Line 26-31: "Only add hints to 2-3 domains as examples (game-simulation, web-api, claude-code-plugin) — others can be added later"
- Non-goals (line 54): "Not adding success criteria to domain profiles that don't have Agent Specifications sections"

**What's unclear:**
1. **Future intent:** Are the 2-3 example hints meant as a proof-of-concept to inform future additions, or is the decision made to only hint those three domains forever?
2. **Maintenance burden:** If future agents regenerate after the hint examples are created, will we get requests to add hints to the other 8 domains? Should this plan reserve capacity for that?
3. **Domain parity:** Does the absence of hints on `ml-pipeline` or `embedded-systems` mean those generated agents are lower quality, or is the hint feature truly optional?

**Recommendation:**
Reframe Task 2 under a "Phased Rollout" framing:

```
**Task 2: Add domain-specific success criteria hints to 3 pilot domains**
- Target domains: game-simulation, web-api, claude-code-plugin
- These are chosen because they have the most mature Agent Specifications and clearest domain boundaries
- Future work (P2): Extend hints to remaining 8 domains as domain expertise matures
- Success criteria hints are optional; generated agents work without them (degrade gracefully)
```

This clarifies that the 2-3 domains are intentional pilots, not arbitrary selection. Helps future developers understand why some domains have hints and others don't.

**Impact:** Does not block implementation; improves clarity for future maintenance and user expectations.

---

### P2: Success Criteria Section and Decision Lens Overlap (Design)

**Issue:** The new "Success Criteria" section sits between "What NOT to Flag" (line 115-123) and "Decision Lens" (line 125-129) in the template. There's potential overlap in guidance.

**Current state:**
- Success Criteria focuses on "what a good review looks like" — concrete examples, failure narratives, specificity
- Decision Lens focuses on "prioritization heuristic" — how to sequence multiple findings

**Overlap risk:**
- Success Criteria bullet 3: "Recommends the smallest viable fix" — this is similar to Decision Lens guidance in fd-architecture ("smallest viable change")
- Success Criteria bullet 2: "Provides a concrete failure scenario" — this mirrors fd-correctness's "Failure Narrative Method"
- Decision Lens already says "When two fixes compete for attention, choose the one with higher real-world impact on {domain-name} concerns."

**What's unclear:**
1. Is the Success Criteria section meant to *inform* the Decision Lens, or is it redundant with it?
2. Could Success Criteria be condensed to avoid repeating guidance the Decision Lens already implies?

**Recommendation:**
Test the template with an example. Generate a sample agent for game-simulation and review if the Success Criteria and Decision Lens sections feel repetitive or complementary. Adjust if needed:

```markdown
## Success Criteria

A good {domain-name} review:
- Ties every finding to a specific file, function, and line number — never a vague "consider X"
- Provides a concrete failure scenario for each P0/P1 finding (what breaks, under what conditions)
- Distinguishes domain-specific expertise from generic code quality (defer the latter to core agents)
- Frames uncertain findings as questions: "Does this handle X?" not "This doesn't handle X"

## Decision Lens

{Decision lens line from profile or fallback}

When two fixes compete for attention, choose the one with higher real-world impact on {domain-name} concerns.
```

This removes the "smallest viable fix" bullet (already in Decision Lens) and keeps Success Criteria focused on *specificity and framing*, while Decision Lens handles *prioritization*.

**Impact:** Does not block implementation; improves template coherence. Optional refinement based on pilot generation.

---

### P3: Verification Steps Are Incomplete (Verification)

**Issue:** The verification section (line 57-71) checks for presence but not for correctness or usefulness.

**Current state:**
```bash
grep -c "Success Criteria" commands/flux-gen.md  # Should be 2+ (section + reference)
grep -l "Success criteria hints" config/flux-drive/domains/*.md  # Should be 2-3 files
grep "flux_gen_version: 3" commands/flux-gen.md  # Should match
uv run --project tests pytest tests/structural/ -q
```

**What's missing:**
1. No check that the template variable substitution actually works — no test of generated agent files
2. No validation that domain-specific hints actually append correctly
3. No smoke test that regenerated agents include the Success Criteria section in their output

**Recommendation:**
Extend verification to include:

```bash
# Template generates correctly
python3 scripts/test-flux-gen-template.py --domain game-simulation --output /tmp/fd-test.md
grep "Success Criteria" /tmp/fd-test.md  # Should exist and be fully interpolated
grep "game simulation" /tmp/fd-test.md  # {domain-name} should be substituted, not literal

# Domain hints render in generated agents
python3 scripts/test-flux-gen-template.py --domain claude-code-plugin --output /tmp/fd-plugin-test.md
grep -A 10 "Success Criteria" /tmp/fd-plugin-test.md | grep -q "Success criteria hints"  # Should contain appended hints

# Version metadata is updated
grep "flux_gen_version: 3" /tmp/fd-test.md  # Generated file should have v3 in frontmatter
```

This could be added as a separate "Smoke Test" or "Template Generation Test" in the verification section.

**Impact:** Optional, improves confidence. Can be added as a follow-up task or included in the broader test suite expansion.

---

### P3: "Smallest Viable Fix" Phrasing (Minor Style)

**Issue:** Task 1, bullet point about content (line 21) says "5-6 bullets" but the template (line 42-48) shows only 5 bullets (line 43-47 plus the placeholder on line 48).

**Current state:**
- Task description: "5-6 bullets defining what a good domain-specific review looks like"
- Template: 5 explicit bullets + 1 conditional placeholder = functionally 5-6 depending on domain

**Recommendation:**
Clarify: "5-6 bullets including domain-specific hints when present." This makes it clear that the count is 5 generic + 0-1 domain-specific, totaling 5-6.

**Impact:** Purely cosmetic; does not affect implementation.

---

### P3: Test Maintenance Burden (Future)

**Issue:** Adding a new section to generated agents means regenerated agents will differ from older ones. Existing projects with generated agents will see diffs when they regenerate.

**Current state:**
- Non-goals (line 53): "Not changing existing generated agents (users regenerate when ready)"
- This is correct — but users *will* see Success Criteria sections appear when they do regenerate

**Consideration:**
This is not a problem (users expect regeneration to pick up new template features), but worth documenting in release notes or CHANGELOG so users understand why their generated agents change after the next plugin version bump.

**Impact:** Documentation note; does not affect implementation.

---

## Alignment with Clavain Conventions

### Positive Alignment
1. **Trunk-based development:** Plan assumes direct commit to main; no branch creation needed ✓
2. **Template-driven generation:** Consistent with existing flux-gen Step 4 approach ✓
3. **Domain profiles structure:** Adds to existing Agent Specifications sections; no new file types ✓
4. **Version tracking:** Frontmatter versioning (flux_gen_version) already in place ✓
5. **Quality bar consistency:** Draws from proven fd-* agent patterns (Failure Narrative, Focus Rules) ✓

### Conventions to Verify Before Implementation
1. **Metadata naming:** Confirm "Success criteria hints" vs "success_criteria_hints" vs another format — check existing domain profile metadata conventions
2. **Bash script updates:** If Step 4 is in a shell script, verify it handles conditional template substitution gracefully
3. **Plugin version bump:** Confirm version 0.5.7 → 0.5.8 or similar after this change is merged (not mentioned in plan)

---

## Estimated Effort & Risk

| Task | Effort | Risk | Dependencies |
|------|--------|------|--------------|
| Task 1: Add Success Criteria section to flux-gen.md | 30 min | Low | **P1 issue:** Clarify template variable mechanics |
| Task 2: Add hints to 3 domain profiles | 45 min | Low | **P2 issue:** Clarify scope and phrasing |
| Task 3: Bump flux_gen_version to 3 | 15 min | Low | None |
| Verification & testing | 20 min | Low | **P3 improvement:** Add smoke tests for generated output |
| **Total** | ~2 hours | Low | P1 clarification |

---

## Recommendations

### Must Do (Before Implementation)
1. **Clarify P1 issue:** Add "Substitution Mechanics" sub-section with pseudo-code for how {domain-name} and {domain_success_hints} are interpolated
2. **Verify metadata naming:** Check existing domain profiles for metadata field naming conventions (e.g., camelCase vs snake_case)

### Should Do (Before or After, Minimal Impact)
1. **Reframe Task 2:** Explain why those 3 domains are pilots, clarify future extensibility
2. **Test for overlap:** Generate a sample agent and review Success Criteria + Decision Lens for redundancy
3. **Extend verification:** Add a simple template generation smoke test if time permits

### Nice to Have (Can Follow-Up)
1. Update CHANGELOG to document Success Criteria feature in generated agents
2. Add hints to remaining 8 domains as follow-up P2 task
3. Document domain-name mapping (snake-case → human-readable) in a comment or reference doc

---

## Conclusion

**Verdict: READY TO IMPLEMENT**

The plan is well-structured and addresses a genuine gap in the flux-gen tool. The proposed Success Criteria section mirrors best practices from core agents (fd-correctness, fd-architecture) and should meaningfully improve generated agent quality. The three tasks are properly sequenced and independently testable.

The P1 issue (template variable mechanics) requires brief clarification in the plan document before development begins. The P2 findings (scope framing, potential overlap) are improvements but do not block implementation — they can be resolved during Task 1-2 code review.

**Path forward:**
1. Address P1 ambiguity in the plan (15 min discussion/writing)
2. Proceed with Tasks 1-3 as written
3. Verify with sample agent generation + structural tests (10 min)
4. Consider P2 improvements as refinements in the PR review phase
