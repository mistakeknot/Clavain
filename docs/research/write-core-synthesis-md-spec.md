# Analysis: Core Synthesis Spec Writing

## Task
Write `/root/projects/Interflux/docs/spec/core/synthesis.md` — the flux-drive findings synthesis specification following the template structure with pragmatic, opinionated prose and inline rationale callouts.

## Approach

### Structure
Used the exact template structure:
1. Title with conformance tag
2. Overview (2-3 sentences)
3. Specification (8 steps with subsections)
4. Interflux Reference (file paths, implementation notes)
5. Conformance (MUST/SHOULD/MAY)

### Content Organization

**Step 1: Output Validation**
- 4-state classification table (Valid/Error/Malformed/Missing)
- Early validation prevents cascading failures
- Rationale: agent crashes shouldn't poison synthesis

**Step 2: Findings Collection**
- Two-tier strategy: structured index first, prose on-demand
- Index contains all metadata for synthesis (severity, section, title)
- Rationale callout: "Index-first is the key performance optimization"
- Reference to `contracts/findings-index.md`

**Step 3: Deduplication**
- 4-step process: match, keep specific, merge metadata, flag conflicts
- Fuzzy title matching (Levenshtein < 0.3 or shared keywords)
- Prefer Project Agent > Plugin Agent (deeper context)
- JSON example showing merged finding structure
- Conflict handling: record both positions, use most severe

**Step 4: Convergence Tracking**
- Confidence levels table (high/medium/low for 3+/2/1 agents)
- Adjustment for early stop: M = agents launched in active stages
- Adjustment for content routing (slicing): M per-finding based on files received
- Rationale callout: "Naive convergence breaks under content routing"
- Implementation notes for tracking content routing decisions

**Step 5: Verdict Computation**
- Deterministic decision table (P0→risky, P1→needs-changes, P2/P3→safe)
- No heuristics, no thresholds, no judgment calls
- Conflict resolution: use most severe rating
- Rationale: deterministic verdicts are debuggable and predictable

**Step 6: Structured Output — findings.json**
- Full JSON example with all fields
- Field definitions table explaining each property
- Includes early_stop and content_routing_active flags
- ISO 8601 timestamps

**Step 7: Human-Readable Summary — summary.md**
- Complete markdown template showing all sections
- Section ordering: verdict → key findings → issues checklist → improvements → heat map → agent reports → conflicts
- Heat map table showing issue distribution by section

**Step 8: Report to User**
- Presentation format example
- Rules: verdict first, group by severity, include convergence, flag single-agent P0/P1

**Error Handling**
- 6 scenarios table: timeout, malformed, all failed, no findings, partial set, conflicts
- Partial results contract for timeouts
- Graceful degradation rationale

### Style Choices

1. **Decision tables** for multi-condition logic (validation states, convergence levels, verdict computation, error handling)
2. **JSON examples** for structured output contracts (merged finding, findings.json)
3. **Markdown examples** for human-readable output (summary.md template)
4. **Inline rationale callouts** using `> **Why this works:**` (5 total: validation, index-first, deduplication, convergence adjustment, deterministic verdicts)
5. **Abstract language** throughout:
   - "agent runtime" not "Claude Code subagent"
   - "orchestrator" not "flux-drive skill"
   - "findings collector" not "Task tool parser"

### Interflux Reference Section
- 3 subsections: Implementation, Contracts, Domain integration
- File paths to actual implementation files
- Line counts for reference (`synthesize.md` is 365 lines)
- Cross-references to related specs (slicing, shared-contracts, findings-index)

### Conformance Section
Organized into 3 tiers:
- **MUST** (6 items): validation, parsing, deduplication, deterministic verdict, structured output, error handling
- **SHOULD** (5 items): convergence tracking, adjustments, summary.md, heat map, conflict flagging
- **MAY** (5 items): additional formats, visualization, caching, fuzzy matching algorithms, parallelization

## Key Design Decisions

1. **Index-first collection is the headline optimization** — called out explicitly in Step 2 rationale. Reading ~30 lines of structured index instead of hundreds of lines of prose per agent.

2. **Convergence adjustment for content routing** — Step 4 includes detailed explanation of why M must be adjusted per-finding when agents see different content slices. This prevents misleading convergence stats.

3. **Deterministic verdict computation** — Step 5 emphasizes no heuristics, no thresholds. Given the same findings, always produce the same verdict.

4. **Graceful degradation for errors** — Error Handling section shows partial results are valuable, one agent failure shouldn't block synthesis.

5. **Conflict visibility** — When agents disagree on severity, both positions are preserved but most severe is used for verdict. Conflicts are flagged in both findings.json and summary.md.

## Coverage Completeness

All requested content covered:
- ✓ Output validation (4 states)
- ✓ Findings collection (index-first + prose fallback)
- ✓ Deduplication (fuzzy matching, metadata merging)
- ✓ Convergence tracking (adjustment for early stop and slicing)
- ✓ Verdict computation (deterministic table)
- ✓ Structured output (findings.json with full example)
- ✓ Human-readable summary (summary.md template)
- ✓ Report to user (presentation format)
- ✓ Error handling (6 scenarios)
- ✓ Interflux reference (file paths, implementation notes)
- ✓ Conformance (MUST/SHOULD/MAY tiers)

## File Metadata
- **Path:** `/root/projects/Interflux/docs/spec/core/synthesis.md`
- **Lines:** 357
- **Structure:** 5 top-level sections (Overview, Specification, Interflux Reference, Conformance)
- **Specification subsections:** 8 steps
- **Tables:** 8 (validation states, confidence levels, verdict computation, findings.json fields, section ordering, error handling, implementation reference, conformance tiers)
- **JSON examples:** 2 (merged finding, findings.json)
- **Markdown examples:** 1 (summary.md template)
- **Rationale callouts:** 5

## Quality Checks
- ✓ Template structure followed exactly
- ✓ Pragmatic, opinionated prose throughout
- ✓ Inline rationale callouts using `> **Why this works:**`
- ✓ Decision tables for multi-condition logic
- ✓ JSON examples for contracts
- ✓ Abstract language (no Claude Code specifics)
- ✓ Interflux file paths accurate
- ✓ Conformance tiers properly organized
