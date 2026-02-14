# Flux-Drive Protocol Specification — Quality & Style Review

**Reviewer:** Flux-drive Quality & Style Reviewer (Clavain agent)
**Reviewed:** 2026-02-14
**Scope:** 5 specification documents (README.md, staging.md, synthesis.md, knowledge-lifecycle.md, completion-signal.md)
**Focus:** Template adherence, rationale consistency, terminology consistency, RFC-2119 conformance, style drift

---

## Review Methodology

1. **Template Adherence:** Verified all documents follow the expected structure (Overview → Specification → Interflux Reference → Conformance)
2. **Rationale Callouts:** Checked format and placement of "> **Why this works:**" blocks
3. **Terminology Consistency:** Extracted key terms and verified usage across documents
4. **RFC-2119 Keywords:** Validated MUST/SHOULD/MAY usage in Conformance sections
5. **Style Drift:** Identified voice, tone, and formatting variations

---

## Findings Index

| SEVERITY | ID | "Section" | Title |
|----------|----|-----------|-------------------------------------------------|
| P2 | QS-1 | "Template Structure" | README.md does not follow the 4-section template |
| P2 | QS-2 | "Rationale Callouts" | Inconsistent placement (mid-section vs. end-of-algorithm) |
| P2 | QS-3 | "Terminology" | "flux-drive" vs "Flux-drive" casing inconsistent |
| P2 | QS-4 | "Terminology" | "orchestrator" vs "Orchestrator" casing inconsistent |
| P2 | QS-5 | "Terminology" | "Phase 2 (Launch)" vs "Stage 2" naming collision |
| P1 | QS-6 | "Conformance" | staging.md references undefined shared-contracts.md |
| P2 | QS-7 | "Conformance" | Missing negation keywords (MUST NOT coverage incomplete) |
| P2 | QS-8 | "Style Drift" | staging.md has more detailed examples than other docs |
| P2 | QS-9 | "Style Drift" | knowledge-lifecycle.md uses different code fence labeling |

**Verdict:** needs-changes

---

## Detailed Findings

### P2 — QS-1: README.md does not follow the 4-section template

**Evidence:**
- `README.md` structure: What This Is → Audience → Documents → Conformance Levels → Versioning → Reading Order → Directory Structure
- Other docs: Overview → Specification → Interflux Reference → Conformance

**Impact:**
The entry-point document has a different structure than all other specification documents. Readers expecting consistent templates will be disoriented.

**Recommendation:**
Accept this divergence and document it explicitly. README.md serves a different purpose (directory navigator, conformance levels definer) than the individual protocol documents. Add a note in the README stating:

> "This README follows a different structure than individual spec documents. Each protocol document uses the template: Overview → Specification → Interflux Reference → Conformance."

**Alternative:**
Restructure README.md to follow the 4-section template, with:
- **Overview:** What This Is + Audience
- **Specification:** Documents table + Conformance levels + Versioning
- **Interflux Reference:** Reading Order + Directory Structure
- **Conformance:** (move conformance levels here, or note "See individual documents")

### P2 — QS-2: Rationale callouts have inconsistent placement

**Evidence:**
- `staging.md` line 15: rationale immediately after "Two-Stage Design Philosophy" heading (before any algorithm content)
- `staging.md` line 52: rationale after research dispatch details (mid-algorithm)
- `staging.md` line 76: rationale after adjacency map definition (end-of-definition)
- `synthesis.md` line 29: rationale after validation table (end-of-step)
- `synthesis.md` line 51: rationale after prose fallback bullet (mid-step)
- `completion-signal.md` line 26: rationale after write flow diagram (end-of-flow)

**Pattern:**
Most rationales appear **after** the content they justify, but `staging.md` line 15 appears **before** the two-stage algorithm is described.

**Impact:**
Readers looking for rationale in a consistent location (e.g., always at end-of-section) will miss some callouts.

**Recommendation:**
Standardize on **end-of-algorithm** or **end-of-definition** placement:
- After describing a mechanism, explain why it works
- Never front-load rationale before the reader knows what the mechanism does

Move `staging.md` line 15 rationale to after line 32 (after Stage 1 dispatch behavior is described).

### P2 — QS-3: "flux-drive" vs "Flux-drive" casing inconsistent

**Evidence:**
- `README.md` line 9: "Flux-drive is a **domain-aware..." (capitalized, start of sentence)
- `README.md` line 48: "### flux-drive-spec 1.0 Core" (lowercase, conformance level)
- `staging.md` line 3: "> flux-drive-spec 1.0" (lowercase, header badge)
- `staging.md` line 6: "The flux-drive protocol separates..." (lowercase, mid-sentence)
- `completion-signal.md` line 17: `<!-- flux-drive:complete -->` (lowercase, HTML comment)

**Current convention (inferred):**
- Sentence-start: "Flux-drive" (capitalized)
- Mid-sentence: "flux-drive" (lowercase)
- Conformance level identifier: "flux-drive-spec" (lowercase)
- Sentinel comment: "flux-drive:complete" (lowercase)

**Impact:**
No actual ambiguity, but inconsistent capitalization can suggest lack of editorial review.

**Recommendation:**
Accept the current convention and document it. Add a style note in a CONTRIBUTING.md or spec README:

> "flux-drive is lowercase except at sentence-start. Conformance levels and sentinel identifiers always use lowercase: flux-drive-spec, flux-drive:complete."

**Alternative:**
Treat "flux-drive" as a proper noun and capitalize everywhere: "Flux-Drive protocol", "Flux-Drive agents", etc. This is the stricter choice but requires editing all 9 documents.

### P2 — QS-4: "orchestrator" vs "Orchestrator" casing inconsistent

**Evidence:**
- `staging.md` line 29: "Orchestrator monitors completion..." (capitalized, sentence-start)
- `staging.md` line 125: "| max(expansion_scores) | Decision | Orchestrator Behavior |" (capitalized, table header)
- `staging.md` line 161: "The orchestrator is an advisor..." (lowercase, mid-sentence)
- `synthesis.md` line 51: "Prose is loaded lazily when the orchestrator needs..." (lowercase, mid-sentence)

**Current convention (inferred):**
- Sentence-start: "Orchestrator" (capitalized)
- Mid-sentence: "orchestrator" (lowercase)
- Table headers: "Orchestrator" (capitalized)

**Impact:**
Same as QS-3 — editorial consistency question.

**Recommendation:**
Accept the current convention. "Orchestrator" is a role, not a proper noun. Lowercase mid-sentence is correct.

Document the convention: "Orchestrator is capitalized only at sentence-start or in headings/tables."

### P2 — QS-5: "Phase 2 (Launch)" vs "Stage 2" naming collision

**Evidence:**
- `README.md` line 29: "core/protocol.md — The 3-phase review lifecycle: triage → launch → synthesize"
- `staging.md` line 19: "Stage 1 — Immediate Launch"
- `staging.md` line 165: "Stage 2 — Conditional Launch"
- `staging.md` line 36: "After Stage 1 completes but before the expansion decision..."

**Collision:**
The protocol has:
- **3 Phases:** Triage (Phase 1), Launch (Phase 2), Synthesize (Phase 3)
- **2 Stages within Phase 2 (Launch):** Stage 1 (immediate), Stage 2 (conditional)

This is not an error, but the overloaded term "Stage" can confuse readers. "Phase 2" and "Stage 2" are different concepts but use similar numbering.

**Impact:**
A reader skimming might think "Stage 2" refers to "Phase 2" (synthesis). The distinction is clear in context but requires careful reading.

**Recommendation:**
Accept the current naming. The distinction is documented in `staging.md` and clear once you read the full spec.

**Optional improvement:**
Rename the stages to avoid number collision:
- Stage 1 → **Immediate Stage** or **Initial Launch**
- Stage 2 → **Expansion Stage** or **Conditional Launch**

Then refer to them as "Immediate/Expansion" throughout, not "Stage 1/2". This makes the distinction clearer but requires editing staging.md and all references.

### P1 — QS-6: staging.md references undefined shared-contracts.md

**Evidence:**
- `staging.md` line 29: "Orchestrator monitors completion via the Completion Signal contract (defined in `shared-contracts.md`)"
- `staging.md` line 93: "Monitoring contract: `skills/flux-drive/phases/shared-contracts.md`"
- Directory listing: `docs/spec/contracts/completion-signal.md` exists, but no `shared-contracts.md` in the spec directory

**Impact:**
Broken reference. Readers following the link will not find the file. This is a **correctness issue**, not just style.

**Root cause:**
`shared-contracts.md` is an Interflux implementation file (`skills/flux-drive/phases/shared-contracts.md`), not a spec document. The spec should reference the spec-level contract document (`contracts/completion-signal.md`).

**Fix:**
Replace all `shared-contracts.md` references in `staging.md` with:
- Line 29: "(defined in `contracts/completion-signal.md`)"
- Line 93: "Monitoring contract: `contracts/completion-signal.md`"

### P2 — QS-7: Conformance sections missing negation keywords

**Evidence:**
- `staging.md` line 263: "**MUST NOT:** Auto-expand without user approval..."
- `synthesis.md` Conformance section (lines 360-381): No MUST NOT entries
- `knowledge-lifecycle.md` Conformance section (lines 130-141): No MUST NOT entries
- `completion-signal.md` Conformance section (lines 95-108): No MUST NOT entries

**Impact:**
MUST NOT clauses are critical for preventing anti-patterns. Only `staging.md` includes them. Other documents may have implicit prohibitions that should be explicit.

**Recommendation:**
Review each document for implicit anti-patterns and add MUST NOT clauses:

**synthesis.md:**
- MUST NOT skip validation step (Step 1) before processing outputs
- MUST NOT count failed agents in convergence denominator M
- MUST NOT ignore severity conflicts when computing verdict

**knowledge-lifecycle.md:**
- MUST NOT refresh lastConfirmed on primed re-confirmations
- MUST NOT delete decayed entries (archive instead)
- MUST NOT inject more than 5 knowledge entries per agent (information overload)

**completion-signal.md:**
- MUST NOT read `.partial` files before they are renamed to `.md`
- MUST NOT block indefinitely waiting for completion (timeout required)
- MUST NOT skip error stub generation for failed agents

### P2 — QS-8: staging.md has more detailed examples than other docs

**Evidence:**
- `staging.md` includes:
  - Adjacency map YAML (lines 65-74)
  - Full expansion scoring example with calculation table (lines 106-118)
  - Multi-option user interaction format (lines 140-158)
- `synthesis.md` includes:
  - findings.json example (lines 150-200)
  - summary.md example (lines 216-276)
- `completion-signal.md` includes:
  - Write flow diagram (lines 20-24)
  - Error stub template (lines 61-66)
- `knowledge-lifecycle.md` includes:
  - Knowledge entry YAML example (lines 13-26)
  - No calculation tables or multi-step walkthroughs

**Pattern:**
`staging.md` has the most worked examples. `knowledge-lifecycle.md` has the fewest.

**Impact:**
Not necessarily a problem — different protocol sections have different complexity. Staging requires more examples because the expansion algorithm is the most decision-heavy part of the protocol.

**Recommendation:**
Accept the variation. Different sections warrant different levels of detail.

**Optional improvement:**
Add a worked example to `knowledge-lifecycle.md` showing:
- Initial discovery of a finding (provenance: independent)
- Primed re-confirmation that does NOT refresh lastConfirmed
- Independent re-discovery that DOES refresh lastConfirmed
- Temporal decay after 10 reviews

This would bring `knowledge-lifecycle.md` up to the same example density as `staging.md`.

### P2 — QS-9: knowledge-lifecycle.md uses different code fence labeling

**Evidence:**
- `staging.md` line 65: `yaml` fence for adjacency map
- `synthesis.md` line 68: `json` fence for merged metadata example
- `synthesis.md` line 150: `json` fence for findings.json
- `knowledge-lifecycle.md` line 15: `yaml` fence for knowledge entry frontmatter
- `knowledge-lifecycle.md` line 50: No fence label (plain code block)

**Pattern:**
Most code fences have language labels (yaml/json/markdown/bash). `knowledge-lifecycle.md` line 50 (the feedback loop diagram) has no label.

**Impact:**
Inconsistent syntax highlighting. Some renderers will default to plaintext, others to their default language.

**Recommendation:**
Add a label to the unlabeled code fence. Options:
- `text` (plaintext, no highlighting)
- `mermaid` (if it's a diagram)
- `markdown` (if it's meant to render as markdown)

Check line 50 content and assign the appropriate label.

---

## Terminology Audit

### Core Terms (Consistent Usage Across All Documents)

| Term | Definition | Consistency |
|------|------------|-------------|
| **flux-drive** | The multi-agent review protocol | Lowercase mid-sentence, capitalized at sentence-start. Spec identifier always lowercase: flux-drive-spec. |
| **orchestrator** | The agent that runs the protocol (triage → launch → synthesize) | Lowercase mid-sentence, capitalized at sentence-start/headings. |
| **agent** | A specialized reviewer (fd-architecture, fd-safety, etc.) | Always lowercase. |
| **Phase** | Protocol lifecycle step (3 phases: triage, launch, synthesize) | Always capitalized when referring to specific phases. |
| **Stage** | Dispatch subdivision within Launch phase (Stage 1, Stage 2) | Always capitalized when referring to stages. |
| **findings** | Issues/improvements reported by agents | Always lowercase plural. |
| **Findings Index** | Structured output format (SEVERITY \| ID \| "Section" \| Title) | Always title-cased, as it's a proper contract name. |
| **verdict** | Final review outcome (safe/needs-changes/risky) | Always lowercase. |
| **convergence** | Number of agents that independently found the same issue | Always lowercase. |
| **provenance** | Knowledge entry origin (independent/primed) | Always lowercase. |

### Terms with Inconsistent Casing (Already Covered in Findings)

- "flux-drive" vs "Flux-drive" (QS-3)
- "orchestrator" vs "Orchestrator" (QS-4)

### Domain-Specific Terms (Introduced in Individual Documents)

| Term | Document | Definition | Consistency |
|------|----------|------------|-------------|
| **expansion score** | staging.md | Metric for Stage 2 agent relevance based on Stage 1 findings | Lowercase. Consistent. |
| **adjacency map** | staging.md | YAML structure defining which agent domains co-occur | Lowercase. Consistent. |
| **completion signal** | completion-signal.md | Atomic rename + sentinel pattern for agent completion | Lowercase. Consistent. |
| **temporal decay** | knowledge-lifecycle.md | Knowledge entry archival after 10 reviews without confirmation | Lowercase. Consistent. |
| **knowledge entry** | knowledge-lifecycle.md | Markdown file with YAML frontmatter representing a learned pattern | Lowercase. Consistent. |

---

## RFC-2119 Conformance Review

### MUST Clauses (Mandatory Requirements)

All documents correctly use MUST for hard requirements:
- `staging.md` line 244: "MUST support at least 2 dispatch stages"
- `synthesis.md` line 362: "MUST validate agent outputs before processing"
- `knowledge-lifecycle.md` line 132: "MUST track provenance on all knowledge entries"
- `completion-signal.md` line 99: "MUST write agent output to .partial files during work"

### SHOULD Clauses (Recommended Requirements)

All documents correctly use SHOULD for best practices:
- `staging.md` line 251: "SHOULD use adjacency maps to scope expansion"
- `synthesis.md` line 369: "SHOULD track convergence and include counts in summary"
- `knowledge-lifecycle.md` line 136: "SHOULD use semantic retrieval for knowledge injection"
- `completion-signal.md` line 104: "SHOULD poll at regular intervals"

### MAY Clauses (Optional Features)

All documents correctly use MAY for implementation variations:
- `staging.md` line 258: "MAY use different threshold values"
- `synthesis.md` line 376: "MAY implement additional output formats"
- `knowledge-lifecycle.md` line 139: "MAY use different decay periods"
- `completion-signal.md` line 106: "MAY use different timeout values"

### MUST NOT Clauses (Prohibited Actions)

Only `staging.md` includes MUST NOT clauses:
- Line 264: "MUST NOT auto-expand without user approval"
- Line 265: "MUST NOT skip Stage 1 and launch all agents immediately"
- Line 267: "MUST NOT block expansion based on Stage 1 findings alone"

**Other documents are missing MUST NOT clauses** (see QS-7).

---

## Rationale Callout Audit

### Format Consistency

All rationale callouts use the same format:
```markdown
> **Why this works:** [Explanation]
```

No deviations found.

### Placement Patterns

| Document | Rationale Count | Placement Pattern |
|----------|----------------|-------------------|
| `staging.md` | 7 | Mixed: 1 before-algorithm, 6 after-algorithm/after-definition |
| `synthesis.md` | 6 | All after-algorithm or after-step |
| `knowledge-lifecycle.md` | 4 | All after-definition or after-rule |
| `completion-signal.md` | 3 | All after-flow or after-policy |

**Issue:** `staging.md` line 15 rationale appears before the two-stage algorithm is described (see QS-2).

### Content Quality

All rationale callouts provide:
1. **Why** the design choice was made (not just what it does)
2. **Tradeoffs** or alternatives considered
3. **Concrete benefits** of the chosen approach

Examples of high-quality rationale:
- `staging.md` line 76: Explains why adjacency is better than full-mesh (prevents "everything is connected" problem)
- `synthesis.md` line 29: Explains why early validation prevents cascading failures
- `knowledge-lifecycle.md` line 62: Compares provenance tracking to independent replication in scientific research

No low-quality rationales found (e.g., restating the algorithm without justification).

---

## Style Drift Analysis

### Voice and Tone

All documents use:
- **Second-person imperative** in specification sections ("The orchestrator polls...", "Agents follow this sequence...")
- **First-person plural** in rationale sections ("we recommend...")
- **Declarative** in conformance sections ("Implementations MUST...")

No voice inconsistencies detected.

### Heading Hierarchy

All documents follow the same hierarchy:
- H1: Document title
- H2: Major sections (Overview, Specification, Interflux Reference, Conformance)
- H3: Subsections within Specification
- H4: Sub-subsections (rare, only in staging.md and synthesis.md)

No hierarchy violations detected.

### List and Table Formatting

| Pattern | Consistency |
|---------|-------------|
| Tables use `\|` delimiters | All documents consistent |
| Code fences have language labels | Mostly consistent (see QS-9) |
| Bulleted lists use `-` (not `*` or `+`) | All documents consistent |
| Numbered lists use `1.` format | All documents consistent |

### Link Formatting

All documents use:
- Relative links for spec documents: `[core/protocol.md](core/protocol.md)`
- Backticks for file paths: `` `shared-contracts.md` ``
- Inline code for contract names: `` `flux-drive-spec 1.0` ``

**Issue:** `staging.md` references `shared-contracts.md` which doesn't exist in the spec tree (see QS-6).

---

## Cross-Reference Integrity

### Internal References (Within Spec Tree)

| Reference | Source | Target | Status |
|-----------|--------|--------|--------|
| `contracts/findings-index.md` | synthesis.md:52 | docs/spec/contracts/findings-index.md | Not checked (out of scope) |
| `shared-contracts.md` | staging.md:29, staging.md:93 | ❌ Does not exist in spec tree | BROKEN (QS-6) |
| `core/protocol.md` | README.md:29 | docs/spec/core/protocol.md | Not checked (out of scope) |

**Recommendation:** Verify all cross-references after fixing QS-6.

### Interflux References (Implementation Pointers)

All documents include "Interflux Reference" sections pointing to:
- Skill files: `skills/flux-drive/phases/*.md`
- Config files: `config/flux-drive/domains/*.md`
- Script files: `scripts/*.py`

These references are **out-of-scope** for this spec review (they point to implementation, not spec documents). They should be validated separately in an Interflux-specific review.

---

## Document Completeness

### README.md

- ✓ Lists all 9 spec documents with line counts and descriptions
- ✓ Defines 3 conformance levels (Core, Core+Domains, Core+Knowledge)
- ✓ Provides reading order for newcomers
- ✓ Includes directory tree
- ✗ Does not follow 4-section template (see QS-1)

### staging.md

- ✓ Follows 4-section template
- ✓ Includes rationale callouts (7 total)
- ✓ Defines conformance requirements (MUST/SHOULD/MAY/MUST NOT)
- ✓ Includes worked examples and calculation tables
- ✗ References non-existent `shared-contracts.md` (see QS-6)

### synthesis.md

- ✓ Follows 4-section template
- ✓ Includes rationale callouts (6 total)
- ✓ Defines conformance requirements (MUST/SHOULD/MAY)
- ✓ Includes JSON/Markdown output examples
- ✗ Missing MUST NOT clauses (see QS-7)

### knowledge-lifecycle.md

- ✓ Follows 4-section template
- ✓ Includes rationale callouts (4 total)
- ✓ Defines conformance requirements (MUST/SHOULD/MAY)
- ✗ Missing MUST NOT clauses (see QS-7)
- ✗ Fewer worked examples than staging.md (see QS-8)

### completion-signal.md

- ✓ Follows 4-section template
- ✓ Includes rationale callouts (3 total)
- ✓ Defines conformance requirements (MUST/SHOULD/MAY)
- ✓ Includes write flow diagram and error stub template
- ✗ Missing MUST NOT clauses (see QS-7)

---

## Recommendations Summary

### High Priority (P1)

1. **Fix broken reference in staging.md (QS-6):**
   - Replace all `shared-contracts.md` references with `contracts/completion-signal.md`
   - Verify the target document actually defines the referenced contracts

### Medium Priority (P2)

2. **Add MUST NOT clauses to all Conformance sections (QS-7):**
   - synthesis.md: Add 3 MUST NOT clauses (validation, convergence, verdict computation)
   - knowledge-lifecycle.md: Add 3 MUST NOT clauses (provenance, decay, injection limits)
   - completion-signal.md: Add 3 MUST NOT clauses (partial reads, blocking, error stubs)

3. **Standardize rationale placement (QS-2):**
   - Move `staging.md` line 15 rationale to after the two-stage algorithm description (line 32)

4. **Add code fence label to knowledge-lifecycle.md line 50 (QS-9):**
   - Inspect the content and assign `text`, `mermaid`, or `markdown` label

5. **Document naming conventions (QS-3, QS-4, QS-5):**
   - Add a "Style Guide" section to README.md or create CONTRIBUTING.md
   - Document: flux-drive casing, orchestrator casing, Phase vs Stage distinction

### Low Priority (Optional)

6. **Add worked example to knowledge-lifecycle.md (QS-8):**
   - Show provenance tracking across multiple reviews (independent → primed → independent → decay)

7. **Restructure README.md to match 4-section template (QS-1):**
   - Or explicitly document that README uses a different structure

8. **Consider renaming Stage 1/2 to avoid Phase 2 collision (QS-5):**
   - Immediate Stage / Expansion Stage (instead of Stage 1 / Stage 2)

---

## Verdict Justification

**Verdict:** needs-changes

**Reasoning:**
- 1 P1 finding (broken cross-reference) requires correction before the spec is reliable
- 8 P2 findings (style/consistency issues) should be addressed to maintain editorial quality
- No P0 findings — the spec is technically sound and usable as-is
- Conformance sections are mostly complete (MUST/SHOULD/MAY well-defined), but missing MUST NOT coverage
- Template adherence is strong (4/5 documents follow the structure exactly)
- Terminology is mostly consistent (only capitalization drift, no semantic confusion)

The spec is production-ready after fixing QS-6. The P2 findings are quality-of-life improvements that will make the spec easier to read and maintain long-term.
