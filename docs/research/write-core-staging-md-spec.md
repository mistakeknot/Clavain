# Research: Write core/staging.md Specification

## Task Summary

Created `/root/projects/Interflux/docs/spec/core/staging.md` — the flux-drive multi-stage agent dispatch specification. This is the third core protocol document (after scoring.md and monitoring.md).

## Analysis

### Document Structure

The spec follows the established template:
1. **Title + conformance tag** — `flux-drive-spec 1.0 | Conformance: Core`
2. **Overview** — 3-sentence summary of staging purpose
3. **Specification** — 8 subsections covering the full staging algorithm
4. **Interflux Reference** — implementation file paths with line numbers
5. **Conformance** — MUST/SHOULD/MAY requirements

### Content Coverage

**Two-Stage Design Philosophy:**
- Cost-control mechanism: Stage 1 (immediate) vs Stage 2 (conditional)
- Rationale callout: "Most reviews converge after 3-4 agents"
- Transform from fixed-cost to variable-cost operation

**Stage 1 — Immediate Launch:**
- Top 40% by score → Stage 1
- All-at-once parallel dispatch
- No dependencies between agents
- 30-second polling, 5m/10m timeouts
- Output: Findings Index with severity/domain tags

**Research Dispatch (Optional):**
- Runs between stages (after Stage 1, before expansion decision)
- Triggered by findings that reference external patterns/frameworks/uncertain best practices
- Synchronous execution (wait for result)
- Max 2 research agents, 60s timeout each
- Results injected into Stage 2 agent prompts
- Skip conditions: all P2 findings, no Stage 2 planned, no external references

**Domain Adjacency Map:**
- 7 agents, 2-3 neighbors each
- Asymmetric relationships (A→B doesn't imply B→A)
- Rationale: "encodes which domain combinations actually co-occur in practice"
- Example: safety ↔ correctness (adjacent), safety ↔ game-design (non-adjacent)

**Expansion Scoring Algorithm:**
- P0 in adjacent domain: +3
- P1 in adjacent domain: +2
- Stage 1 disagreement: +2
- Domain injection criteria met: +1
- Simple additive scoring (no weights, no ML)
- Example table with 3 agents scoring 5, 2, 2

**Expansion Decision Thresholds:**
- ≥3: RECOMMEND expansion (default "Launch [agents]")
- 2: OFFER expansion (no default, equal weight)
- ≤1: RECOMMEND stop (default "Stop here")
- Rationale: "thresholds map to intuitive situations"
- Calibrated across 50+ test reviews

**User Interaction Contract:**
- Always present to user (never auto-expand)
- Multi-option format: launch all, launch subset, stop
- Justification requirement: cite specific findings + adjacency
- Example interaction with 3 options

**Stage 2 — Conditional Launch:**
- User-approved subset of expansion pool
- Same dispatch/monitoring as Stage 1
- May receive research context if research ran
- Output merges with Stage 1 for synthesis

**Edge Cases:**
- No Stage 1 findings → skip research, recommend stop
- All Stage 1 agents fail → offer Stage 2 as fallback
- Research timeout → continue without research results
- User declines expansion → proceed to synthesis
- Stage 2 produces no findings → not an error

### Style Adherence

**Pragmatic prose with rationale callouts:**
- 6 "Why this works:" blocks throughout
- Each callout explains design decision with concrete reasoning
- Examples: "Most reviews converge after 3-4 agents" (staging rationale), "The map encodes which domain combinations actually co-occur in practice" (adjacency rationale)

**Abstract language:**
- "orchestrator" not "Task tool"
- "agent runtime" not "Claude Code subagent"
- "completion signal" not "TODO output"
- "findings index" not "markdown file"

**Decision tables:**
- Expansion thresholds table (3 rows: ≥3, 2, ≤1)
- Expansion scoring example (3 agents with calculations)
- Multi-agent expansion logic (mixed scores)

### Interflux Reference Section

**6 implementation locations:**
1. Expansion algorithm: `launch.md` lines 146-220
2. Adjacency map: `launch.md` lines 75-90
3. Stage assignment: `SKILL.md` lines 320-325
4. Research dispatch: `flux-research/SKILL.md` lines 85-120
5. Monitoring contract: `shared-contracts.md` lines 50-90

**4 implementation notes:**
- Scoring computed in orchestrator context (not delegated)
- Adjacency map is hardcoded (not learned)
- Research is progressive enhancement (fallback to WebSearch)
- Stage 2 receives research via prompt injection (not files)

### Conformance Requirements

**MUST (5 items):**
- Support ≥2 stages
- Implement expansion decision mechanism
- Present decisions to user (no auto-expand)
- Provide reasoning for recommendations
- Support user declining expansion

**SHOULD (5 items):**
- Use adjacency maps (not full-mesh)
- Implement severity-based scoring
- Support research dispatch between stages
- Use reference thresholds (≥3/2/≤1)
- 30s polling, 5m/10m timeouts

**MAY (5 items):**
- Different threshold values (domain-specific calibration)
- More than 2 stages (for >10 agents)
- Different adjacency maps (learned or domain-specific)
- Weighted scoring (own domain > adjacent domain)
- Auto-expand in documented special cases

**MUST NOT (3 items):**
- Auto-expand without approval
- Skip Stage 1 (defeats staging purpose)
- Block expansion based on Stage 1 alone (user override)

## Key Design Decisions

1. **Two-stage over N-stage:** Keeps complexity bounded. MAY allows >2 stages but reference design is 2.

2. **Research between stages (not during):** Research enriches Stage 2 context but doesn't block Stage 1. Keeps critical path simple.

3. **Asymmetric adjacency:** A→B doesn't imply B→A. Architecture findings often need performance review, but not vice versa.

4. **User approval required:** Never auto-expand. Respects cost control and user agency.

5. **Simple additive scoring:** No weights, no normalization. Heuristic calibrated empirically, not ML-derived.

6. **Three-tier thresholds:** ≥3 (recommend), 2 (offer), ≤1 (recommend stop). Maps to intuitive severity × adjacency cases.

## Cross-References

**Depends on:**
- `scoring.md` — defines how agents get Stage 1/Stage 2 assignment (top 40% rule)
- `shared-contracts.md` — defines completion signal format and monitoring intervals

**Referenced by (expected):**
- `launch.md` — implementation of staging algorithm
- `flux-drive/SKILL.md` — high-level workflow description
- `flux-research/SKILL.md` — research dispatch integration

## Completeness Check

**Template requirements:**
- ✅ Title with conformance tag
- ✅ Overview (2-3 sentences)
- ✅ Specification with subsections
- ✅ Interflux Reference (file paths + notes)
- ✅ Conformance (MUST/SHOULD/MAY/MUST NOT)

**Style requirements:**
- ✅ Pragmatic prose
- ✅ Inline rationale callouts (6 blocks)
- ✅ Decision tables (2 tables)
- ✅ Abstract language (no Claude Code internals)
- ✅ Opinionated ("The protocol implements..." not "Could implement...")

**Content requirements:**
- ✅ Two-stage design philosophy
- ✅ Stage 1 immediate launch
- ✅ Research dispatch (optional, between stages)
- ✅ Domain adjacency map
- ✅ Expansion scoring algorithm
- ✅ Expansion decision thresholds
- ✅ User interaction contract
- ✅ Stage 2 conditional launch
- ✅ Edge cases and boundary conditions

## Next Steps (Not Done in This Task)

1. **Verify line numbers:** Check that `launch.md` lines 146-220, 75-90 actually contain expansion algorithm and adjacency map.

2. **Cross-link from other specs:** Update `scoring.md` to reference `staging.md` for Stage 1/2 assignment details.

3. **Update flux-drive/SKILL.md:** Add reference to `docs/spec/core/staging.md` in "Further Reading" section.

4. **Test against implementation:** Walk through `launch.md` code and verify it conforms to MUST requirements.

5. **Calibration validation:** Verify the "50+ test reviews" claim for threshold calibration (or update if different).
