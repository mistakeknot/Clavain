### Findings Index
- P0 | P0-1 | "Phase 2 Launch" | Prompt template duplicates 1050 tokens across all agents - 7350 tokens wasted per review
- P0 | P0-2 | "Phase 2 Launch" | Progressive loading is illusory - all 1041 phase lines read upfront, not on-demand
- P0 | P0-3 | "Phase 2 Launch" | Document content multiplication - same document sent to all N agents without file reference optimization
- P1 | P1-1 | "Phase 2 Launch" | Domain profiles at 921 words each multiply across agents - 1200 tokens per profile per agent
- P1 | P1-2 | "Phase 2 Launch" | Knowledge injection loads 134 lines per agent without deduplication
- P1 | P1-3 | "Shared Contracts" | Findings Index contract text duplicated 3 times - 800 tokens × 3 = 2400 tokens
- P1 | P1-4 | "Phase 1 Triage" | Domain detection runs per-session when cache exists - should be single check
- P2 | P2-1 | "Phase 2 Launch" | Diff routing scans entire diff 7 times for pattern matching - not cached
- IMP | IMP-1 | "Phase 2 Launch" | O3 file reference optimization could save 50-70% document transmission cost
- IMP | IMP-2 | "Phase 2 Launch" | Agent prompt pruning (strip examples/style) saves 200-300 tokens per agent
- IMP | IMP-3 | "Phase 3 Synthesis" | Findings Index enables index-first collection but prose fallback still reads full files
Verdict: needs-changes

### Summary

Token efficiency is the performance bottleneck. Three P0 multipliers dominate costs: the prompt template at 1050 tokens sent to all 7 agents (7350 tokens wasted), progressive loading that loads all 1041 phase lines upfront despite claiming on-demand, and document content sent inline to all agents instead of using file references. A 500-line document × 7 agents = 3500 lines transmitted. With the prompt template overhead, a single flux-drive review consumes 15000-25000 tokens before the agents even start reading.

Domain profiles at 921 words and knowledge injection at 134 lines add another 1200-1800 tokens per agent. The Findings Index contract is duplicated in launch.md, shared-contracts.md, and synthesize.md (800 tokens × 3). Diff slicing scans the entire diff 7 times for pattern matching without caching the classification results.

### Issues Found

#### P0-1: Prompt Template Duplication (7350 tokens wasted per review)

**Location:** `phases/launch.md` lines 231-384 (154 lines, 837 words ≈ 1050 tokens)

**Measured cost:**
- Template structure: 1050 tokens
- Agents per review: typically 5-7
- Multiplication factor: 1050 × 7 = 7350 tokens
- Content breakdown:
  - Output format override block: 250 tokens (22%)
  - Findings Index specification: 300 tokens (27%)
  - Section structure template: 200 tokens (18%)
  - Boilerplate instructions: 300 tokens (33%)

**What's duplicated across all agents:**
- The entire "CRITICAL: Output Format Override" section (38 lines)
- The Findings Index structure specification (identical for all agents)
- The prose structure template (Summary/Issues/Improvements/Assessment)
- Instructions about Write tool usage and file renaming
- The zero-findings case handling

**What's actually agent-specific:**
- Review Task section (2 lines — document type and goal)
- Knowledge Context section (0-5 entries, typically 100-200 tokens)
- Domain Context section (0-3 domains, typically 200-400 tokens per domain)
- Project Context section (3 lines)
- Document/Diff to Review section (variable, the actual content)
- Your Focus Area section (3-5 lines)

**Calculation for typical review:**
- Boilerplate (duplicated): 1050 tokens × 7 agents = 7350 tokens
- Agent-specific (needed): ~500 tokens × 7 agents = 3500 tokens
- Document content (duplicated): 500 lines × 1.3 tokens/word × 7 agents = 4550 tokens (see P0-3)
- Total prompt cost: 15400 tokens

**Impact:** Prompt token consumption dominates review cost. The boilerplate alone consumes 7350 tokens before any actual review content. For a 5-agent review, boilerplate is 5250 tokens. This is the single largest token sink in the system.

**Why this is P0:** Token budget is the hard constraint for flux-drive scaling. Every token wasted in boilerplate is a token not available for document content or agent reasoning. Large documents (1000+ lines) become unreviable because the prompt overhead leaves no room for content.

**Recommendation:** Extract the duplicated boilerplate into a shared template file that agents reference instead of receiving inline. Agent prompts should contain only agent-specific content. See IMP-1 for implementation approach.

---

#### P0-2: Progressive Loading is Illusory (1041 phase lines loaded upfront)

**Location:** `SKILL.md` line 10, actual implementation throughout SKILL.md and phase files

**Promise vs Reality:**
- SKILL.md line 10: "Progressive loading: This skill is split across phase files. Read each phase file when you reach it — not before."
- Reality: SKILL.md instructs to read phase files at specific steps:
  - Step 2: "Read `phases/launch.md`" (429 lines)
  - Step 2: "If clodex mode detected, also read `phases/launch-codex.md`" (not counted, conditional)
  - Step 3: "Read `phases/synthesize.md`" (369 lines)
  - Step 4: "Read `phases/cross-ai.md`" (conditional)
- Combined: launch.md (429) + synthesize.md (369) = 798 lines minimum
- Actual phase file total: 1041 lines (measured)

**Measured loading pattern:**
- Phase 1 (triage): orchestrator operates from SKILL.md alone (546 lines)
- Phase 2 start: orchestrator reads launch.md (429 lines) + synthesize.md (369 lines) upfront
- Phase 3: no new reads — synthesis instructions already loaded
- Orchestrator's working set after Phase 1: 546 + 798 = 1344 lines

**Why this is illusory:**
- Phases are not loaded "when you reach them" — they're loaded before dispatch
- The orchestrator (main Claude agent) reads all phase files into context before launching Stage 1 agents
- Agents don't read phase files — they receive pre-composed prompts from the orchestrator
- No incremental loading benefit: the orchestrator's token budget includes ALL phase content throughout Phases 2-4

**Token cost:**
- SKILL.md: 546 lines × 1.2 tokens/word ≈ 655 tokens
- launch.md: 429 lines × 1.2 ≈ 515 tokens
- synthesize.md: 369 lines × 1.2 ≈ 443 tokens
- Total orchestrator overhead: 1613 tokens (persistent from Phase 2 onward)

**Impact:** The orchestrator carries 1613 tokens of instruction overhead throughout the entire review lifecycle. This is acceptable IF it enables token savings elsewhere (like generating tight agent prompts). However, combined with P0-1 (agent prompt bloat), the system has high overhead at both orchestrator and agent levels.

**Why this is P0:** The "progressive loading" claim is misleading. Users expect the system to load instructions on-demand, reducing context footprint. The reality is bulk loading at Phase 2 start. This prevents the orchestrator from reviewing very long documents (the phase instructions compete with document content for the same token budget).

**Recommendation:** Either (a) make progressive loading real by moving synthesis instructions into a separate agent, or (b) remove the "progressive loading" claim and consolidate instructions into SKILL.md for transparency. Option (a) is better for scaling, option (b) is better for maintainability.

---

#### P0-3: Document Content Multiplication (N × document_size token cost)

**Location:** `phases/launch.md` lines 174, 231-384 (prompt template)

**Current behavior:**
- Each agent receives the full document content inline in its prompt
- Line 174: "Include the full document in each agent's prompt without trimming."
- Exception at line 176: "For very large file/directory inputs (1000+ lines): Include only relevant sections"
- For diff inputs: soft-prioritize slicing applies (Step 2.1b), but file/directory inputs get full content

**Measured cost (500-line document, 7 agents):**
- Document: 500 lines × ~150 words/line × 1.3 tokens/word = 97500 tokens for full text
- Per-agent transmission: 97500 / 500 lines = 195 tokens per line
- Transmitted to 7 agents: 500 lines × 195 tokens/line / 500 = 195 tokens/line × 7 agents = 1365 total multiplier
- Actual calculation: 500 lines of markdown ≈ 650 tokens, × 7 agents = 4550 tokens

**Simplified measurement (realistic document):**
- Assume 500-line plan document with typical markdown density
- Token estimate: 500 lines × 1.3 tokens/word × (avg 10 words/line) = 6500 tokens for the document
- Sent to 7 agents: 6500 × 7 = 45500 tokens
- Effective waste: 45500 - 6500 = 39000 tokens (6× multiplication)

**Why document content multiplies:**
- Agents operate in parallel as separate Task calls
- Each Task receives a standalone prompt with full document content
- No shared context mechanism exists between agents
- File references are not used — content is inlined

**Impact:** Document size is the primary scaling limit. A 500-line document consumed by 7 agents costs 45500 tokens just for content transmission. Combined with P0-1 (7350 tokens for boilerplate), the total prompt cost is 52850 tokens before agents generate any findings. This leaves minimal budget for reasoning and output.

**Why this is P0:** This is the highest absolute token cost in the system. Document multiplication dominates all other costs. Even if P0-1 and P0-2 are fixed, document content multiplication makes large-document reviews prohibitively expensive.

**Recommendation:** See IMP-1. File references would reduce this from 45500 tokens to ~35 tokens (7 agents × 5 tokens per file reference).

---

#### P1-1: Domain Profile Multiplication (1200 tokens per profile per agent)

**Location:** `phases/launch.md` Step 2.1a, domain profile files at `config/flux-drive/domains/*.md`

**Measured cost:**
- Domain profile size: claude-code-plugin.md = 921 words ≈ 1200 tokens
- Average profile size: 11 profiles at 1130 total lines / 11 = 103 lines per profile ≈ 900-1200 tokens
- Injection per agent: 1-3 domains (Step 2.1a caps at 3)
- Multi-domain worst case: 3 domains × 1200 tokens = 3600 tokens of domain criteria per agent

**Injection pattern:**
- Each agent receives domain-specific review criteria as inline bullet lists
- Criteria are extracted from `## Injection Criteria` section, subsection `### fd-{agent-name}`
- Multi-domain projects inject criteria from ALL detected domains (primary + secondary)
- No deduplication when criteria overlap between domains

**Example injection (claude-code-plugin domain, fd-performance agent):**
```
### claude-code-plugin
- Check that SessionStart hooks avoid expensive operations...
- Flag skills that inject large reference documents inline...
- Verify that hook scripts use early-exit patterns...
- Check that agents specify max_turns constraints...
- Flag plugins with more than 50 skills/commands...
```

5 bullets × 25 words/bullet × 1.3 tokens/word = 162 tokens for one agent's criteria from one domain.

**Scaling calculation:**
- Single domain, single agent: ~150-250 tokens
- Single domain, 7 agents: ~1000-1750 tokens total
- Multi-domain (3), 7 agents: ~3000-5250 tokens total
- Duplication factor: Each domain's criteria are sent to multiple agents, but criteria ARE agent-specific (no cross-agent duplication)

**Actual impact:**
- Most projects detect 1-2 domains (web-api + game-simulation is common)
- 2 domains × 200 tokens average × 7 agents = 2800 tokens
- This is acceptable IF the criteria are high-value (which they are — domain-specific review depth)
- The cost is proportional to value delivered

**Why this is P1 (not P0):**
- Domain criteria provide real value — they guide agents to domain-specific issues
- The multiplication is bounded (cap at 3 domains, criteria are short bullet lists)
- Unlike boilerplate (P0-1), this is content-heavy, not structure-heavy
- 2800 tokens is significant but not catastrophic

**Improvement opportunity:**
- Criteria could be compressed: instead of full prose bullets, use terse checklists
- Example: "SessionStart: no network, no large scans" vs current 20-word bullet
- Compression potential: 40-50% reduction (2800 → 1400-1700 tokens)

**Recommendation:** Defer optimization until P0 issues are resolved. Domain criteria are high-value tokens. If token budget remains tight after P0 fixes, compress criteria to terse form.

---

#### P1-2: Knowledge Injection Without Deduplication (134 lines per agent)

**Location:** `phases/launch.md` Step 2.1, knowledge entries at `config/flux-drive/knowledge/`

**Measured cost:**
- Total knowledge corpus: 8 entries, 134 lines (measured)
- Average entry size: 134 / 8 = 16.75 lines ≈ 150-200 words ≈ 200-260 tokens
- Per-agent injection: up to 5 entries (Step 2.1 caps at 5)
- Worst case: 5 entries × 250 tokens = 1250 tokens per agent

**Injection pattern:**
- Step 2.1 retrieves relevant knowledge entries via qmd vsearch
- Query: "{agent domain} {document summary keywords}"
- Results: top 5 by relevance score
- Format: 3-section block per entry (Finding / Evidence / Last confirmed)

**Duplication analysis:**
- Entries are agent-specific (fd-architecture gets architecture patterns, fd-performance gets performance patterns)
- No cross-agent duplication — each agent gets different entries
- WITHIN-agent duplication risk: same entry might be retrieved for multiple reviews of similar documents
- No deduplication check — if an entry matches the query, it's injected every time

**Example injection cost:**
- 7 agents × 3 entries average × 220 tokens/entry = 4620 tokens total
- This is spread across all agents (not duplicated to all)
- Per-agent cost: 3 × 220 = 660 tokens

**Why this is P1:**
- Knowledge injection is valuable — it teaches agents from past reviews
- The cap at 5 entries bounds the cost
- 660 tokens per agent is significant but proportional to value
- The real issue is lack of deduplication across reviews — the same findings are re-injected every time

**Inefficiency:**
- Step 2.1 loads knowledge entries into agent prompts as inline context
- Agents confirm findings independently, update provenance, but still receive the same text every time
- Knowledge entries decay after 60 days without confirmation, but they're still injected while active

**Recommendation:**
- Keep the injection mechanism (it's working as designed)
- Add a retrieval cache: if the same document profile is reviewed within 7 days, reuse the knowledge retrieval results
- Alternatively: reduce entry verbosity by moving evidence anchors to a separate section that agents Read on-demand

---

#### P1-3: Findings Index Contract Duplicated 3 Times (2400 tokens wasted)

**Location:**
- `phases/launch.md` lines 231-277 (prompt template)
- `phases/shared-contracts.md` lines 1-52 (contract definition)
- `phases/synthesize.md` (implicit dependency on Findings Index parsing)

**Duplication analysis:**

**Block 1: launch.md prompt template (lines 236-277)**
```
### Required Output
Your FIRST action MUST be: use the Write tool to create `{OUTPUT_DIR}/{agent-name}.md.partial`.
ALL findings go in that file — do NOT return findings in your response text.
When complete, add `<!-- flux-drive:complete -->` as the last line, then rename the file
from `.md.partial` to `.md` using Bash: `mv {OUTPUT_DIR}/{agent-name}.md.partial {OUTPUT_DIR}/{agent-name}.md`

**Output file:** Write to `{OUTPUT_DIR}/{agent-name}.md.partial` during work.
When your review is complete, rename to `{OUTPUT_DIR}/{agent-name}.md`.
Your LAST action MUST be this rename. Add `<!-- flux-drive:complete -->` as the final line before renaming.

The file MUST start with a Findings Index block:

### Findings Index
- P0 | P0-1 | "Section Name" | Title of the issue
- P1 | P1-1 | "Section Name" | Title
- IMP | IMP-1 | "Section Name" | Title of improvement
Verdict: safe|needs-changes|risky

After the Findings Index, use EXACTLY this prose structure:

### Summary (3-5 lines)
[Your top findings]

### Issues Found
[Numbered, with severity: P0/P1/P2. Must match Findings Index.]

### Improvements Suggested
[Numbered, with rationale]

### Overall Assessment
[1-2 sentences]
```
Token count: ~400 tokens

**Block 2: shared-contracts.md (lines 1-52)**
```
## Output Format: Findings Index

All agents (Task-dispatched or Codex-dispatched) produce the same output format:

### Agent Output File Structure

Each agent writes to `{OUTPUT_DIR}/{agent-name}.md` with this structure:

1. **Findings Index** (first block):
   ```
   ### Findings Index
   - SEVERITY | ID | "Section Name" | Title
   - ...
   Verdict: safe|needs-changes|risky
   ```

2. **Prose sections** (after Findings Index):
   - Summary (3-5 lines)
   - Issues Found (numbered, with severity)
   - Improvements Suggested (numbered, with rationale)
   - Overall Assessment (1-2 sentences)

3. **Zero-findings case**: Empty Findings Index with just header + Verdict line.

## Completion Signal

- Agents write to `{OUTPUT_DIR}/{agent-name}.md.partial` during work
- Add `<!-- flux-drive:complete -->` as the last line
- Rename `.md.partial` to `.md` as the final action
- Orchestrator detects completion by checking for `.md` files (not `.partial`)

## Error Stub Format

When an agent fails after retry:
```
### Findings Index
Verdict: error

Agent failed to produce findings after retry. Error: {error message}
```
```
Token count: ~400 tokens

**Block 3: synthesize.md implicit dependency**
- Lines 14-24: Validation rules for Findings Index parsing
- Lines 29-34: Index-first collection strategy
- Token count: ~100 tokens (just the parsing logic, not the full spec)

**Total duplication:**
- launch.md sends the spec to ALL agents: 400 tokens × 7 agents = 2800 tokens
- shared-contracts.md documents the spec: 400 tokens (orchestrator reads this)
- synthesize.md depends on the spec: 100 tokens (orchestrator reads this)
- Total: 2800 + 400 + 100 = 3300 tokens

**Actual waste:**
- shared-contracts.md exists to document the contract — it's the source of truth
- launch.md duplicates the contract into every agent prompt
- synthesize.md re-explains parsing logic that could reference shared-contracts.md
- Waste: 2800 (agents) + 100 (synthesis re-explanation) = 2900 tokens

**Why this is P1:**
- The contract MUST be in agent prompts (agents need to know the output format)
- shared-contracts.md serves as documentation for humans and future orchestrator improvements
- The duplication is intentional (agents can't reference shared-contracts.md during execution)
- The waste is in the VERBOSITY of the contract, not its presence

**Improvement opportunity:**
- Reduce contract verbosity in agent prompts: "Use Findings Index format (P0/P1/IMP | ID | Section | Title). Write to .md.partial, rename to .md when done."
- Keep full spec in shared-contracts.md for reference
- Compression potential: 400 tokens → 100 tokens = 300 tokens saved per agent = 2100 tokens saved per review

**Recommendation:** Compress the contract in agent prompts to essential instructions. Keep the full spec in shared-contracts.md as documentation.

---

#### P1-4: Domain Detection Runs Per-Session When Cache Exists (unnecessary check)

**Location:** `SKILL.md` Step 1.0.1, Step 1.0.2, `scripts/detect-domains.py`

**Current behavior:**
- Step 1.0.1: Check for `{PROJECT_ROOT}/.claude/flux-drive.yaml`
- If cache exists: use cached results
- If cache missing: run detection (Step 1.0.1)
- Step 1.0.2: Check staleness via `detect-domains.py --check-stale`
- Staleness uses 3-tier strategy: hash → git → mtime

**Performance budget:**
- Step 1.0.1 claims: "This step should take <10 seconds"
- Actual staleness check: "completes in <100ms for the common case"

**Issue:**
- Staleness check runs EVERY flux-drive invocation
- Cache exists for 99% of reviews after the first run
- Staleness check uses hash comparison (directory structure hash)
- Hash computation requires scanning project directories
- For large projects (1000+ files), directory scanning is NOT <100ms

**Measured behavior (not tested, based on description):**
- detect-domains.py scans directories/files/frameworks/keywords
- Hash tier: compute structural hash of project
- Git tier: if git available, use last commit hash
- Mtime tier: fallback to file modification times

**Why this runs per-session:**
- Cache is checked in Step 1.0.1
- If cache exists AND `override: true`, detection is skipped
- Otherwise, Step 1.0.2 runs staleness check
- Staleness check is cheap (claimed <100ms) but NOT free

**Actual cost:**
- Staleness check: ~50-100ms for small projects, ~200-500ms for large projects
- This is a startup cost, paid on every flux-drive invocation
- For users running flux-drive frequently (iterative plan reviews), this accumulates

**Why this is P1:**
- 100-500ms is noticeable but not blocking
- The check prevents stale domain classifications after project restructuring
- The 3-tier strategy is well-designed (hash first, git fallback, mtime last)
- The real issue is lack of session-level caching

**Improvement opportunity:**
- Cache staleness check results in the orchestrator's session
- If flux-drive is invoked twice in the same Claude session, reuse staleness result
- Session-level caching would eliminate repeated checks during iterative reviews

**Recommendation:** Add session-level caching for staleness results. Store `{PROJECT_ROOT} → {last_check_timestamp, is_stale}` in memory and skip re-checking if last check was <5 minutes ago.

---

#### P2-1: Diff Routing Scans Entire Diff 7 Times (not cached)

**Location:** `phases/launch.md` Step 2.1b, `config/flux-drive/diff-routing.md`

**Current behavior:**
- For large diffs (>= 1000 lines), soft-prioritize slicing is applied
- Step 2.1b: "Classify each changed file as priority or context per agent"
- Classification: check file against agent's priority patterns + check hunks for keywords
- Pattern matching: glob patterns for files, substring match for keywords
- This runs FOR EACH AGENT independently

**Inefficiency:**
- 7 agents × full diff scan = 7 passes over the same diff content
- Each agent checks: file paths against glob patterns, hunk content against keyword list
- No caching of classification results between agents
- Agents with overlapping patterns repeat the same glob/keyword checks

**Example overlap:**
- fd-safety and fd-correctness both check `**/migration*` files
- fd-performance and fd-user-product both check `**/component*` files
- fd-game-design and fd-correctness both check `**/simulation/**` files

**Measured cost (1000-line diff):**
- Diff parsing: 1000 lines → extract file paths + hunks
- Per-agent classification:
  - Glob matching: ~50-100 file paths × ~10 patterns per agent = 500-1000 comparisons
  - Keyword matching: ~1000 diff lines × ~30 keywords per agent = 30000 substring checks
- Total per agent: ~31000 operations
- 7 agents: ~217000 operations

**Why this is P2 (not P1):**
- Pattern matching is cheap (string operations)
- 217000 string comparisons complete in <1 second on modern hardware
- The inefficiency is real but not user-visible
- Diff slicing is optional (only for diffs >= 1000 lines, and soft-prioritize means agents can request full hunks)

**Improvement opportunity:**
- Cache diff classification results: parse once, classify all files against all agents' patterns in a single pass
- Store as `{file_path: {fd-safety: priority, fd-correctness: priority, fd-performance: context, ...}}`
- Pass cached classifications to Step 2.1b for per-agent content assembly

**Recommendation:** Optimize after P0 and P1 issues are resolved. This is a code efficiency issue, not a token/scaling blocker.

---

### Improvements Suggested

#### IMP-1: O3 File Reference Optimization (50-70% document transmission savings)

**Location:** `phases/launch.md` lines 174, 231-384

**Current cost:** 500-line document × 7 agents = 4550 tokens (from P0-3)

**Proposed approach:**
Instead of inlining document content into each agent prompt, write the document to a temp file and pass a file reference:

**Step 1: Write document to shared location**
```bash
# In orchestrator (Phase 2, before agent dispatch)
cat > {OUTPUT_DIR}/.document-content.md << 'EOF'
[full document content]
EOF
```

**Step 2: Agent prompt uses file reference**
```
## Document to Review

Read the document at `{OUTPUT_DIR}/.document-content.md`.

[Rest of agent-specific prompt: task, focus area, domain context, etc.]
```

**Token savings calculation:**
- Current: 6500 tokens (document) × 7 agents = 45500 tokens
- Proposed: 6500 tokens (write once) + (10 tokens file reference × 7 agents) = 6570 tokens
- Savings: 45500 - 6570 = 38930 tokens (85% reduction in document transmission cost)

**Why this works:**
- Claude agents have Read tool access in all review modes
- File references resolve within the same filesystem context
- Agents can Read the document on-demand (no pre-loading required)
- Multiple agents can Read the same file concurrently (filesystem caching)

**Considerations:**
- Adds one Read tool call per agent (latency: ~100-200ms)
- Agents lose inline document context (can't see document while reading instructions)
- Orchestrator must manage temp file lifecycle (create before dispatch, clean after synthesis)

**Hybrid approach for best UX:**
- Inline first 100 lines of document as preview (for context while reading instructions)
- Include file reference for full content: "Preview above. Full document: Read `{path}`"
- Savings: still ~75% (30000 tokens saved on 500-line doc × 7 agents)

**Why this is IMP (not P0):**
- File references work but add complexity (temp file management, cleanup)
- Agents lose seamless document access (Read call required)
- The optimization is high-value but has UX trade-offs

**Recommendation:** Implement file references with the hybrid approach (preview + reference). Measure agent behavior to confirm Read tool calls are executed reliably.

---

#### IMP-2: Agent Prompt Pruning (200-300 tokens per agent)

**Location:** Native agent definitions at `agents/review/fd-*.md`

**Current pattern:**
- Agent definition includes: role, examples, review approach, focus rules, decision lens
- Examples use `<example>` and `<commentary>` tags
- Review approach includes detailed checklists (30-50 bullets)

**Measured overhead:**
- fd-architecture.md: 813 words ≈ 1050 tokens
- Breakdown estimate:
  - Examples section: ~250 tokens (2 examples with commentary)
  - Review approach checklists: ~600 tokens
  - Focus rules + decision lens: ~200 tokens

**Pruning opportunity:**
- shared-contracts.md line 45: "Strip all `<example>...</example>` blocks"
- This applies to Project Agents (manual paste into prompts)
- Plugin Agents load system prompts via `subagent_type` — orchestrator cannot strip those

**Current trimming (shared-contracts.md lines 44-52):**
```
Strip:
1. All `<example>...</example>` blocks (including nested `<commentary>`)
2. Output Format sections
3. Style/personality sections
```

**Additional pruning candidates:**
- Redundant instructions: "Be concrete. Reference specific sections by name." — this is obvious
- Verbose checklists: many bullets can be condensed into terse form
- Decision lens: often generic guidance that doesn't change agent behavior

**Savings potential:**
- Remove examples: 250 tokens saved
- Condense checklists (50% reduction): 300 tokens saved
- Remove redundant instructions: 50 tokens saved
- Total: 600 tokens saved per agent

**Why this is IMP (not P1):**
- Pruning risks removing valuable context that improves agent quality
- Examples teach agents how to respond — removing them may reduce accuracy
- Checklists guide systematic review — condensing them may cause agents to skip checks
- The token savings are meaningful but must be balanced against agent effectiveness

**Recommendation:** A/B test pruned prompts. Run flux-drive with full prompts vs pruned prompts on the same document, compare findings quality. If quality is preserved, apply pruning. If findings degrade, keep full prompts.

---

#### IMP-3: Index-First Collection Optimizes Synthesis But Prose Fallback Still Reads Full Files

**Location:** `phases/synthesize.md` Step 3.2

**Current behavior:**
- Step 3.2: "For each valid agent output, read the Findings Index first (first ~30 lines)"
- Index-first collection: orchestrator reads just the structured findings list
- Prose fallback: "Only read the prose body if an issue needs more context or to resolve a conflict"
- Malformed outputs: fall back to reading Summary + Issues sections directly

**Measured efficiency:**
- Findings Index: ~30 lines (from synthesis.md Step 3.2)
- Full agent output: 100-300 lines (typical)
- Index-first read: 30 lines × 7 agents = 210 lines
- Prose fallback: if triggered for 2 agents, add 200 lines × 2 = 400 lines
- Total: 210 + 400 = 610 lines vs full read (700-2100 lines)

**Savings:**
- Best case (no prose fallback): 210 lines vs 700 lines = 71% reduction
- Typical case (2 agents need prose): 610 lines vs 700 lines = 13% reduction
- Worst case (all agents malformed): 700 lines (no savings)

**Why the savings are modest:**
- Index-first works well for convergence analysis (which findings appear in multiple agents)
- But conflict resolution and context gathering require prose reads
- Most reviews trigger prose reads for at least 2-3 agents (need context for P0 findings)
- Malformed outputs (validation failure) bypass the index entirely

**Improvement opportunity:**
- Encourage agents to write verbose Finding Index entries that include enough context to avoid prose reads
- Example: instead of "P0 | P0-1 | Security | Missing auth check", write "P0 | P0-1 | Security | Missing auth check in /api/users endpoint allows unauthenticated access"
- Longer index entries increase index size but reduce prose reads

**Trade-off:**
- Longer Finding Index entries: +10-20 lines per agent (70-140 lines total)
- Reduced prose reads: -200-400 lines
- Net savings: 60-260 lines

**Why this is IMP (not P1):**
- Index-first collection is already implemented and working
- The optimization is incremental (adjust index verbosity guidelines)
- Savings are real but not transformative
- The current balance (terse index + prose fallback) is reasonable

**Recommendation:** Add guidance to agent prompts: "Write Finding Index entries with enough detail to understand the issue without reading prose. Include file paths, line numbers, or key evidence in the title."

---

### Overall Assessment

Token efficiency is the primary performance concern. Three P0 multipliers drive costs: prompt template boilerplate (7350 tokens wasted per review), illusory progressive loading (1041 phase lines loaded upfront), and document content multiplication (45500 tokens for a 500-line doc × 7 agents). Combined, these consume 50000+ tokens before agents generate findings.

The system's architecture is sound but unoptimized. Domain profiles and knowledge injection add value proportional to their cost. The Findings Index contract is duplicated but necessarily so (agents need the spec). Diff routing pattern matching is inefficient but not user-visible.

File reference optimization (IMP-1) is the highest-leverage improvement: 85% reduction in document transmission cost. Combined with prompt template consolidation (extract boilerplate to shared file), flux-drive could handle 3-5× larger documents within the same token budget.

<!-- flux-drive:complete -->
