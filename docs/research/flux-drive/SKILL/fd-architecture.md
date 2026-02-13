# Flux-Drive Architecture Review Plan

## Task
Deep architectural review of the flux-drive skill orchestration system.

## Scope
- `skills/flux-drive/SKILL.md` (546 lines)
- `skills/flux-drive/phases/launch.md` (429 lines)
- `skills/flux-drive/phases/shared-contracts.md` (98 lines)
- `skills/flux-drive/phases/synthesize.md` (369 lines)
- `skills/flux-drive/phases/cross-ai.md` (31 lines)
- `config/flux-drive/domains/index.yaml` (454 lines)
- `config/flux-drive/diff-routing.md` (134 lines)

## Analysis Areas

### 1. Phase Decomposition & Boundaries
**Status**: Analysis complete

#### Finding: Progressive Loading is an Illusion (P0)
The skill claims "Progressive loading: This skill is split across phase files. Read each phase file when you reach it — not before." This is misleading architecture.

**Evidence**:
- Line 10 in SKILL.md: "Progressive loading: This skill is split across phase files. Read each phase file when you reach it — not before."
- Lines 513-526 in SKILL.md show Phase 2-4 sections that say "Read the [phase] file now"
- But the orchestrator MUST read all phase files before dispatching agents to construct valid agent prompts

**Why this is a boundary violation**:
The orchestrator needs information from later phases during earlier phases:
1. **launch.md** (Phase 2) contains the prompt template (lines 232-384) that defines the Findings Index contract
2. **shared-contracts.md** defines the completion signal (`.md.partial` → `.md` rename) and error stub format
3. **synthesize.md** (Phase 3) defines convergence counting rules that affect how many agents to launch in Phase 2

The orchestrator cannot defer reading these files - it needs them upfront to:
- Construct agent prompts with the correct output format override
- Know what completion looks like for monitoring
- Understand convergence thresholds for domain-aware expansion decisions

**Correct architecture**: Either admit "read all phase files at the start" OR actually support deferred loading by:
- Moving the prompt template to SKILL.md
- Moving completion/error contracts to SKILL.md
- Making each phase truly independent (Phase 3 synthesis should not define rules that affect Phase 2 decisions)

**Impact**: This creates cognitive debt for developers maintaining the skill. They think phases are independent but find cross-references requiring simultaneous understanding of all files.

#### Finding: Hidden Coupling Between Triage and Synthesis (P1)
Step 1.2 (triage) defines "convergence" as a metric (lines 323, 341) but doesn't specify the algorithm. The convergence algorithm is buried in synthesize.md Step 3.3.

**Evidence**:
- SKILL.md line 340: "Track convergence: Note how many agents flagged each issue (e.g., '4/6 agents')"
- synthesize.md lines 36-46: Actual convergence dedup algorithm with diff-slicing awareness
- The triage step uses convergence to decide agent slot allocation (domain_slots calculation), but the definition of what convergence means is 2 phases away

**Why this matters**:
If convergence is part of the triage decision (how many slots?), the triage phase needs the convergence rules co-located, not forward-referenced to a later phase.

**Fix**: Move convergence algorithm definition to SKILL.md or create a glossary section that defines shared concepts upfront.

### 2. Scoring System Design
**Status**: Analysis complete

#### Finding: Domain Boost Calculation is Opaque (P1)
Lines 271-275 in SKILL.md define domain boost as +2 for "≥3 bullets" and +1 for "1-2 bullets" but this requires the orchestrator to count injection criteria bullets across multiple domain profile .md files.

**Evidence**:
```
Domain boost (+0, +1, or +2; applied only when base score ≥ 1):
- Agent has injection criteria with ≥3 bullets for this domain → +2
- Agent has injection criteria (1-2 bullets) for this domain → +1
- Agent has no injection criteria for this domain → +0
```

**Problem**: This is a lossy coupling. The boost value is encoded indirectly through bullet count in separate .md files. If a domain profile author adds a 4th bullet for clarity, they've unknowingly changed triage scoring.

**Better design**: Domain profiles should declare boost weights explicitly in frontmatter:
```yaml
---
domain: game-simulation
agents:
  fd-game-design:
    boost: 2
    focus: pacing, balance, emergent behavior
  fd-correctness:
    boost: 2
    focus: simulation state consistency
---
```

This makes the coupling explicit and prevents accidental changes to triage behavior when editing review criteria.

#### Finding: Dynamic Slot Allocation Formula is Fragile (P1)
Lines 288-309 define the slot ceiling formula but it's spread across narrative text, not machine-readable config.

**Evidence**:
```
base_slots    = 4
scope_slots:
  - single file:          +0
  - small diff (<500 lines): +1
  - large diff (500+):    +2
  - directory/repo:       +3
domain_slots:
  - 0 domains detected:   +0
  - 1 domain detected:    +1
  - 2+ domains detected:  +2
```

**Problem**: This is a hardcoded decision tree embedded in narrative. Changing the thresholds (e.g., "small diff" from <500 to <300 lines) requires editing markdown prose. No validation that these numbers make sense together.

**Better approach**: Extract to YAML config:
```yaml
slot_allocation:
  base: 4
  hard_maximum: 12
  scope:
    single_file: 0
    small_diff_threshold: 500
    small_diff_bonus: 1
    large_diff_bonus: 2
    directory_bonus: 3
  domain:
    zero: 0
    one: 1
    multiple: 2
  generated_agents: 2
```

This makes the formula testable, tunable, and validates that base + max(scope) + max(domain) + generated <= hard_maximum.

#### Finding: Stage Assignment Percentage is Arbitrary (P2)
Line 320 says "Stage 1: Top 40% of total slots (rounded up, min 2, max 5)" but provides no rationale for 40% vs 30% or 50%.

**Evidence**: The 40% value appears once, with no justification or empirical basis.

**Impact**: Minor, but this feels like a magic number. If the goal is "launch high-confidence agents first, wait for results, then decide on expansion", the percentage should be tuned based on actual review outcomes (how often does Stage 1 find sufficient issues to stop early?).

**Suggestion**: Either justify the 40% value in a comment (e.g., "Empirically, 40% captures the 2-3 highest-scoring agents in typical reviews") OR make it configurable.

### 3. Agent Dispatch Architecture
**Status**: Analysis complete

#### Finding: Diff Slicing Coupling Creates Split Responsibility (P0)
The diff slicing feature (lines 182-230 in launch.md) is architecturally split:
- **Routing patterns** in `config/flux-drive/diff-routing.md` (separate file, 134 lines)
- **Slicing algorithm** in launch.md Step 2.1b (49 lines)
- **Convergence adjustment** in shared-contracts.md lines 84-88
- **Synthesis reporting** in synthesize.md lines 178-191

**Why this is a problem**:
Diff slicing is a single feature but its logic is scattered across 4 files. To understand how slicing works, you must read:
1. What makes a file "priority" (diff-routing.md patterns)
2. How priority files are assembled into per-agent diffs (launch.md)
3. How convergence counts adjust for partial visibility (shared-contracts.md)
4. How slicing metadata appears in the report (synthesize.md)

**Root cause**: This is a cross-cutting concern (affects triage, dispatch, synthesis, reporting) but it's implemented as localized additions to each phase rather than as a first-class abstraction.

**Better architecture**:
- **Option A** (minimal): Create `config/flux-drive/slicing.md` that consolidates all slicing logic (patterns, algorithm, convergence rules, reporting format) and reference it from phase files.
- **Option B** (proper): Extract slicing as a module with a clean interface:
  ```
  SlicingEngine:
    .classify_files(diff, agent) -> {priority: [...], context: [...]}
    .build_agent_diff(diff, classification) -> string
    .adjust_convergence(finding, slicing_map) -> int
    .generate_report(slicing_map) -> markdown
  ```

The current scattered implementation makes it hard to:
- Validate that routing patterns are complete (which file types fall through to context-only?)
- Test the slicing algorithm in isolation
- Ensure convergence adjustment is applied consistently across all synthesis paths

#### Finding: Agent Prompt Template Violates DRY (P1)
Lines 232-384 in launch.md contain a 153-line prompt template. But parts of this template are duplicated or implied elsewhere:

**Duplications**:
1. **Findings Index format** is defined in both the prompt template (lines 254-260) AND shared-contracts.md (lines 11-22)
2. **Completion signal** is defined in the prompt template (line 251) AND shared-contracts.md (lines 28-32)
3. **Domain Context injection format** is defined in the prompt template (lines 299-318) AND implied by domain profile structure

**Problem**: If the Findings Index format changes (e.g., add a "Convergence" column), you must update:
- The prompt template in launch.md
- The contract definition in shared-contracts.md
- The parsing logic in synthesize.md Step 3.1
- Any examples in documentation

**Better approach**: The prompt template should reference a canonical contract definition rather than duplicating it. Use a variable substitution pattern:
```
{FINDINGS_INDEX_SPEC}  <- replaced at runtime with the contract from shared-contracts.md
```

This ensures a single source of truth.

#### Finding: Prompt Trimming Rules are Context-Dependent (P2)
shared-contracts.md lines 44-52 define trimming rules but they apply inconsistently:
- Project Agents (manual paste): trimmed
- Plugin Agents (via subagent_type): NOT trimmed (orchestrator can't strip)
- Codex AGENT_IDENTITY: trimmed

**Problem**: This creates an information asymmetry. Project Agents and Plugin Agents reviewing the same document have different context (Plugin Agents see examples, Project Agents don't).

**Impact**: Mild. Plugin Agents might produce more detailed findings due to having access to example patterns. But this breaks the assumption that agent type shouldn't affect finding quality.

**Fix**: Either:
1. Make trimming consistent (strip examples from all agent types, or none)
2. Explicitly document that Plugin Agents have richer context and this is intentional

### 4. Template System & Contracts
**Status**: Analysis complete

#### Finding: Error Stub Format is Too Minimal (P1)
shared-contracts.md lines 35-41 define the error stub:
```
### Findings Index
Verdict: error

Agent failed to produce findings after retry. Error: {error message}
```

**Problem**: This loses critical debugging context:
- What was the agent's input? (document path, slicing metadata, domain context)
- Did the agent start? (did it create .md.partial?)
- What was the timeout? (5 min for retries, but was original timeout hit?)
- Was this a Task dispatch failure or an agent logic failure?

**Better format**:
```yaml
---
agent: {agent-name}
status: error
reason: {timeout | task_failure | output_malformed}
attempted_at: {timestamp}
input_file: {path}
diff_slicing: {active|inactive}
---
### Findings Index
Verdict: error

Agent failed after retry.

Error: {error message}
Logs: {background task output excerpt}
```

This preserves enough context to debug failed agents without re-running the entire review.

#### Finding: Completion Signal Relies on Filesystem State (P1)
The completion contract (shared-contracts.md lines 28-32) uses file renaming as the completion signal:
```
- Agents write to {agent-name}.md.partial during work
- Rename .md.partial to .md as the final action
- Orchestrator detects completion by checking for .md files
```

**Problem**: This is a racy contract. If:
1. Agent writes .md.partial
2. Agent crashes before rename
3. Orchestrator retries
4. Retry succeeds and renames to .md
5. Original agent recovers and also tries to rename

You get file contention. Worse: if two agents have the same name (Project Agent + Plugin Agent both called "fd-architecture"), they clobber each other's output.

**Better approach**: Atomic completion via marker file:
```
- Agent writes {agent-name}.md.partial during work
- Agent writes {agent-name}.md.done (empty marker) when complete
- Agent renames .md.partial to .md only if .done exists
- Orchestrator polls for .done files, then verifies .md exists
```

This makes completion explicit and prevents races.

### 5. Cross-File References & Navigation
**Status**: Analysis complete

#### Finding: Domain Profile Index is Weakly Typed (P1)
`config/flux-drive/domains/index.yaml` defines 11 domains with 4 signal types each (directories, files, frameworks, keywords). But there's no validation that:
1. Each domain has a corresponding .md file in the same directory
2. Each domain .md file has the required sections (Injection Criteria with fd-{agent-name} subsections, Agent Specifications)
3. The min_confidence values are sane (all are 0.3-0.35 except claude-code-plugin at 0.35)

**Evidence**:
- index.yaml line 2-14: Comments describe structure but no schema validation
- SKILL.md line 129: "Validate domain profiles exist" but this check happens at runtime during agent generation, not at deploy time

**Problem**: A broken domain profile (missing .md file, malformed injection criteria) is discovered late (during a review) rather than early (at skill installation).

**Fix**: Add a validation step to the skill's test suite:
```bash
# For each domain in index.yaml:
# - Check that config/flux-drive/domains/{domain}.md exists
# - Parse the .md for "## Injection Criteria" section
# - Parse for "### fd-{agent}" subsections
# - Warn if any core agent is missing from any domain profile
```

This catches config drift before production.

#### Finding: Pyramid Scan Section Tagging is Ambiguous (P2)
Lines 393-424 in SKILL.md define pyramid scan logic for large documents (>500 lines). Sections are tagged as:
- `full` — in agent's core domain
- `summary` — adjacent but not core
- `skip` — no relevance

**Problem**: "Adjacent but not core" is subjective. The examples show:
- "architecture sections → fd-architecture" (full)
- "security sections → fd-safety" (full)

But what about "API design section → fd-architecture"? Is that full or summary? The mapping is implied from agent domain descriptions, not explicitly defined.

**Impact**: Two orchestrators might tag the same section differently, leading to inconsistent agent coverage.

**Fix**: Either:
1. Provide explicit domain-to-section keyword mapping (e.g., fd-architecture matches: {architecture, design, modules, components, layers})
2. OR make tagging a heuristic ("if section title matches any agent domain keyword → full, else summary") and document the heuristic

### 6. Progressive Loading Claim
**Status**: Analysis complete

#### Summary of Finding P0-1 (already documented above)
The "progressive loading" claim is architectural theater. All phase files must be read upfront for the orchestrator to function. The cross-references make deferred loading impossible.

**Recommendation**: Remove the progressive loading claim and document the actual architecture:
```
## Phase File Organization

This skill is organized into phase files for **readability**, not progressive loading.
The orchestrator must read all phase files before launching agents because:
- Agent prompts reference contracts from shared-contracts.md
- Triage decisions reference synthesis rules (convergence thresholds)
- Domain context injection requires launch.md prompt template structure

Read all files in skills/flux-drive/phases/ at the start of the skill.
```

This sets honest expectations.

### 7. Integration Points & External Contracts
**Status**: Analysis complete

#### Finding: Oracle Integration is Brittle (P1)
Lines 476-508 in SKILL.md define Oracle integration with heavy caveats:
- Requires DISPLAY=:99 and CHROME_PATH env vars
- Needs Xvfb running
- Uses --write-output to avoid stdout corruption
- Uses --timeout to avoid orphaned sessions
- Must not wrap with external timeout

**Problem**: This is a lot of environmental coupling for what should be "just another agent". The special-casing breaks the agent abstraction.

**Evidence**:
- Line 491-499: 9-line bash command with env vars, error handling, and fallback
- Lines 500-505: Two full paragraphs explaining why --write-output and why no timeout wrapper

**Better architecture**: Abstract Oracle behind a dispatch adapter:
```
OracleAdapter:
  .is_available() -> bool
  .dispatch(prompt, files, output_path) -> Result
```

The adapter encapsulates:
- Environment checks (DISPLAY, CHROME_PATH, Xvfb)
- Command construction (--write-output, --timeout)
- Error handling and fallback

The orchestrator just calls `OracleAdapter.dispatch()` and doesn't need to know about browser mode quirks.

This also makes Oracle swappable - if the implementation changes (e.g., Oracle switches to API mode), only the adapter changes, not 50+ lines of orchestrator logic.

#### Finding: QMD MCP Dependency is Optional but Not Graceful (P2)
Lines 19-46 in launch.md describe knowledge injection via qmd MCP tools. Line 47 says "If qmd MCP tool is unavailable or errors, skip knowledge injection entirely".

**Problem**: The orchestrator won't know WHY qmd is unavailable:
- Not installed?
- Collection "Clavain" doesn't exist?
- qmd server is down?

Without diagnostics, users can't fix qmd integration issues.

**Better approach**:
```python
try:
    results = qmd.vsearch(collection="Clavain", query=...)
except ToolNotFoundError:
    log.warn("qmd MCP not installed - knowledge injection disabled")
except CollectionNotFoundError:
    log.warn("qmd collection 'Clavain' not found - run qmd init first")
except qmd.ServerError as e:
    log.error(f"qmd server error: {e} - knowledge injection disabled")
```

Specific errors guide the user toward fixes.

### 8. Token Efficiency Claims
**Status**: Analysis complete

#### Finding: Prompt Trimming is Asymmetric Across Agent Types (P2)
(Already documented in section 3 - Prompt Trimming Rules are Context-Dependent)

#### Finding: Diff Slicing Token Savings are Unmeasured (P2)
Lines 182-230 in launch.md describe soft-prioritize slicing but provide no metrics for token savings. The claim is "reduce token cost for large diffs" but:
- No baseline: what's the token count for a 2000-line diff sent to 5 agents?
- No measurement: what's the token count after slicing?
- No validation: does slicing actually improve finding quality, or do agents miss issues in context-only files?

**Suggestion**: Add instrumentation:
```
Diff slicing report:
- Total diff tokens: 15,234
- fd-safety (sliced): 3,120 tokens (79% reduction)
- fd-architecture (full): 15,234 tokens (0% reduction, cross-cutting)
```

This makes the value proposition measurable and helps tune routing patterns.

## Final Findings Index

### Findings Index
- P0 | P0-1 | "Phase Decomposition" | Progressive Loading is an Illusion - orchestrator must read all phase files upfront due to cross-references
- P0 | P0-2 | "Agent Dispatch" | Diff Slicing Coupling Creates Split Responsibility - single feature scattered across 4 files
- P1 | P1-1 | "Phase Decomposition" | Hidden Coupling Between Triage and Synthesis - convergence algorithm defined in wrong phase
- P1 | P1-2 | "Scoring System" | Domain Boost Calculation is Opaque - boost derived from bullet count in separate files
- P1 | P1-3 | "Scoring System" | Dynamic Slot Allocation Formula is Fragile - hardcoded in narrative text
- P1 | P1-4 | "Agent Dispatch" | Agent Prompt Template Violates DRY - Findings Index format duplicated in 3 places
- P1 | P1-5 | "Template System" | Error Stub Format is Too Minimal - loses debugging context
- P1 | P1-6 | "Template System" | Completion Signal Relies on Filesystem State - racy contract for file rename
- P1 | P1-7 | "Cross-File References" | Domain Profile Index is Weakly Typed - no validation that profiles exist and are well-formed
- P1 | P1-8 | "Integration Points" | Oracle Integration is Brittle - heavy environmental coupling breaks agent abstraction
- P2 | P2-1 | "Scoring System" | Stage Assignment Percentage is Arbitrary - 40% value lacks justification
- P2 | P2-2 | "Agent Dispatch" | Prompt Trimming Rules are Context-Dependent - information asymmetry between agent types
- P2 | P2-3 | "Cross-File References" | Pyramid Scan Section Tagging is Ambiguous - no explicit domain-to-section mapping
- P2 | P2-4 | "Integration Points" | QMD MCP Dependency is Optional but Not Graceful - no diagnostics for why it's unavailable
- P2 | P2-5 | "Token Efficiency" | Diff Slicing Token Savings are Unmeasured - no metrics to validate efficiency claims

Verdict: needs-changes

## Improvement Suggestions

### IMP-1: Extract Slicing as First-Class Module
Create `lib/slicing.sh` or `SlicingEngine` class with:
- `.classify_files(diff, agent)` - apply routing patterns
- `.build_agent_diff(diff, classification)` - construct per-agent content
- `.adjust_convergence(finding, slicing_map)` - modify convergence counts
- `.generate_report(slicing_map)` - produce metadata section

Consolidates 134 lines of scattered logic into ~60 lines of cohesive module.

### IMP-2: Make Domain Boost Explicit in Domain Profiles
Add frontmatter to domain .md files:
```yaml
---
domain: game-simulation
agents:
  fd-game-design: {boost: 2, focus: "pacing, balance"}
  fd-correctness: {boost: 2, focus: "state consistency"}
---
```

Prevents accidental triage changes when editing review criteria.

### IMP-3: Convert Slot Allocation to YAML Config
Extract lines 288-309 to `config/flux-drive/slot-allocation.yaml` with validation:
- base + max(all bonuses) <= hard_maximum
- threshold values are sorted (small_diff < large_diff)

Makes formula testable and tunable.

### IMP-4: Create Oracle Dispatch Adapter
Abstract Oracle behind `OracleAdapter` interface:
```
.is_available() -> bool
.dispatch(prompt, files, output_path) -> Result
```

Encapsulates environment setup, command construction, error handling. Makes Oracle swappable.

### IMP-5: Add Domain Profile Validation to Test Suite
Create `tests/structural/test_domain_profiles.py`:
- For each domain in index.yaml, verify .md exists
- Parse .md for required sections
- Check that all core agents (fd-architecture, fd-safety, etc.) have injection criteria in at least one domain

Catches config drift at deploy time.

### IMP-6: Instrument Diff Slicing for Token Metrics
Add token counting to slicing report:
```
Diff slicing report:
| Agent | Mode | Tokens (full) | Tokens (sliced) | Reduction |
```

Validates efficiency claims and helps tune routing patterns.

### IMP-7: Replace Rename-Based Completion with Atomic Marker
Use `.done` marker file pattern:
1. Agent writes .md.partial
2. Agent writes .md.done when complete
3. Orchestrator polls for .done, then verifies .md exists

Prevents races and file contention.

## Overall Assessment

The flux-drive orchestration system demonstrates sophisticated phase-based architecture with domain-aware triage, multi-modal agent dispatch, and diff slicing optimization. However, it suffers from **architectural drift** — what started as clean phase boundaries has accumulated cross-references and scattered concerns.

**Core issue**: The system conflates *narrative organization* (phase files for readability) with *architectural modularity* (truly independent phases). The "progressive loading" claim is the most visible symptom, but the deeper problem is that features like diff slicing and convergence tracking span multiple phases without a unifying abstraction.

**Strengths**:
- Rich domain detection with 11 profiles and multi-domain support
- Sophisticated scoring system with 4 bonus types
- Diff slicing reduces token waste for large diffs
- Knowledge injection creates learning loop

**Weaknesses**:
- Scattered feature logic makes change risky (update slicing? touch 4 files)
- Duplicated contracts create synchronization burden
- Environmental coupling (Oracle) breaks agent abstraction
- Unmeasured efficiency claims (token savings)

**Recommendation**: Prioritize P0 fixes (progressive loading claim, slicing consolidation) before adding new features. The system has good bones but needs refactoring to match its complexity.
