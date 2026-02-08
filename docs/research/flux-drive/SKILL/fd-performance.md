---
agent: fd-performance
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Phase 2 Prompt Template (lines 275-282)"
    title: "Token trimming is delegated to the orchestrator via prose instructions with no enforcement, verification, or fallback — real-world compliance is unverifiable"
  - id: P1-1
    severity: P1
    section: "Phase 2 Prompt Template (lines 253-349)"
    title: "Prompt template contains ~20 lines of conditional scaffolding that is always sent but rarely used, inflating every agent prompt by ~200 tokens"
  - id: P1-2
    severity: P1
    section: "Phase 2 Prompt Template (lines 310-329)"
    title: "YAML frontmatter example in prompt template is 19 lines of static boilerplate duplicated identically across all agents"
  - id: P1-3
    severity: P1
    section: "Phase 3 Frontmatter Collection (lines 384-390)"
    title: "The ~60 line frontmatter assumption is violated by agents with many findings — real outputs show 59-83 lines, and the strategy has no overflow handling"
  - id: P2-1
    severity: P2
    section: "Phase 2 Prompt Template (lines 299-302)"
    title: "Section mapping example (FULL/SUMMARY) is instructional meta-commentary that wastes tokens on every invocation"
  - id: P2-2
    severity: P2
    section: "Phase 3 Frontmatter Collection (lines 384-390)"
    title: "Frontmatter-only reading strategy assumes issue titles are self-explanatory — but short titles often lack the context needed for deduplication without reading prose"
improvements:
  - id: IMP-1
    title: "Move token trimming from agent-side prose instructions to orchestrator-side pre-computation in Phase 1"
    section: "Phase 2 Prompt Template (lines 275-282)"
  - id: IMP-2
    title: "Split prompt template into a fixed skeleton (~40 lines) and a per-agent variable block, eliminating conditional scaffolding duplication"
    section: "Phase 2 Prompt Template (lines 253-349)"
  - id: IMP-3
    title: "Replace inline YAML example with a reference to a shared output format file, saving ~19 lines x N agents"
    section: "Phase 2 Prompt Template (lines 310-329)"
  - id: IMP-4
    title: "Replace the fixed ~60 line assumption with a delimiter-based parsing strategy (read until second ---) to handle variable-length frontmatter"
    section: "Phase 3 Frontmatter Collection (lines 384-390)"
  - id: IMP-5
    title: "Add a token budget assertion: orchestrator should estimate prompt token count before launch and warn if it exceeds a configurable ceiling"
    section: "Phase 2 Prompt Template"
verdict: needs-changes
---

### Summary

The token optimization mechanisms in the flux-drive SKILL.md are structurally reasonable but operationally fragile. The prompt template (lines 253-349) carries approximately 1,200-1,500 tokens of fixed overhead per agent, of which roughly 300-400 tokens are conditional scaffolding and instructional meta-commentary that could be eliminated. The core token trimming strategy (lines 275-282) relies entirely on prose instructions to the orchestrator LLM with no verification, no fallback, and no measurement — making the claimed ~50% document reduction an aspiration rather than a guarantee. The Phase 3 frontmatter-first collection strategy (lines 384-390) is a sound optimization for synthesis token cost, but its "~60 lines" assumption is already violated by real agent outputs (59-83 lines observed in actual runs), and the strategy lacks overflow handling. The net effect is that the spec promises significant token savings but provides no mechanism to verify they are achieved.

### Section-by-Section Review

#### Phase 2 Prompt Template (lines 253-349) — FULL Review

The prompt template is 94 lines of instructional markdown inside a code block. At approximately 10-15 tokens per line of markdown instruction, this represents ~940-1,400 tokens of fixed overhead sent to every agent. For a 6-agent review, that is 5,600-8,400 tokens consumed by template text alone — roughly 3-4% of the reported 197K total.

**Structural decomposition of the 94 lines:**

| Section | Lines | Token estimate | Purpose |
|---------|-------|---------------|---------|
| Opening + Project Context | 256-271 | ~150-200 | Sets role and context |
| Document to Review + Trimming Rules | 273-291 | ~200-280 | Token optimization instructions |
| Focus Area | 293-302 | ~100-140 | Per-agent routing |
| Output Requirements + YAML example | 304-348 | ~450-600 | Output format specification |
| **Total fixed template** | **94** | **~940-1,400** | |

The template has three token efficiency problems:

**1. Conditional scaffolding always included (lines 263-271, 288-291)**

Lines 263-271 contain the divergence context block, prefixed with "[If document-codebase divergence was detected in Step 1.0, add:]". This is a conditional section that is included in the template text but only applies when divergence exists. In the common case (no divergence), these 9 lines (~90-130 tokens) are dead weight. The same applies to lines 288-291 (divergence-specific agent instructions), adding another ~40-60 tokens.

The instruction says "add:" — implying the orchestrator should conditionally include it — but the template is presented as a single block to be used as-is, creating ambiguity about whether this is an instruction to the orchestrator (exclude these lines when no divergence) or to the agent (ignore this section when no divergence applies). In practice, the orchestrator is an LLM that may or may not correctly parse this conditional.

**2. YAML frontmatter example is static boilerplate (lines 310-329)**

The output format specification includes a 19-line YAML frontmatter example that is identical for every agent. Only the placeholder values (`{agent-name}`, `{1|2|3}`) change. This is approximately 250-350 tokens duplicated across all agents.

At 6 agents, this is 1,500-2,100 tokens spent on the same YAML schema example. These tokens could be eliminated entirely if agents were told "Follow the standard flux-drive output format" with a reference to a shared format definition — but the current spec has no mechanism for shared format references across subagents.

Within the current architecture (each agent is independent, cannot read shared config), this duplication is arguably necessary. But it represents the single largest fixed-cost block in the template and should be acknowledged as a known cost center.

**3. Meta-instructional commentary (lines 299-302)**

Lines 299-302 contain an example of how to construct the FULL/SUMMARY section mapping:

```
When constructing the prompt, explicitly list which sections to include in full
and which to summarize. Example:
- FULL: Architecture, Security (agent's domain)
- SUMMARY: Skills table, Commands table, Credits (not in domain)
```

This is instruction to the orchestrator about how to fill in the template, not content that should appear in the agent's prompt. If the orchestrator correctly follows the instruction, the agent never sees these 4 lines — but if the orchestrator includes the template verbatim (which is likely given it is presented as a code block), these meta-instructions consume ~50-70 tokens per agent for no benefit.

#### Token Trimming Rules (lines 275-282) — FULL Review

The trimming rules are:

```
IMPORTANT — Token Optimization:
For file inputs with 200+ lines, you MUST trim the document before including it:
1. Keep FULL content for sections listed in "Focus on" below
2. Keep Summary, Goals, Non-Goals in full (if present)
3. For ALL OTHER sections: replace with a single line: "## [Section Name] — [1-sentence summary]"
4. For repo reviews: include README + build files + 2-3 key source files only

Target: Agent should receive ~50% of the original document, not 100%.
```

**Critical issue: Who performs the trimming?**

The template is sent as the prompt to each agent via the Task tool. But lines 275-282 are instructions about what to include in the prompt — they are instructions to the *orchestrator* that constructs the prompt, not to the agent that receives it. This creates a fundamental ambiguity:

- If the orchestrator reads these instructions and pre-trims the document before pasting it into the agent prompt, the trimming works as intended. The agent receives a smaller document.
- If the orchestrator pastes these instructions into the agent prompt along with the full document, the agent receives the full document PLUS trimming instructions it cannot act on (since the document is already in its prompt). The instructions then become dead weight — the agent sees the full document regardless.

The spec says "[For file inputs: Include the trimmed document following the rules above.]" (line 284), which suggests the orchestrator should do the trimming. But the entire block is inside a code fence labeled "Prompt template for each agent" — suggesting this is text that goes into the agent's prompt.

This ambiguity is the root cause of the unverifiable token savings. The orchestrator (Claude) will likely interpret the template as a combination of instructions-to-self and content-for-agent, but there is no guarantee it will correctly separate the two. A previous fd-performance review of a brainstorm document (from the `2026-02-08-flux-drive-improvements-brainstorm` run) identified this same issue as P1-2.

**Quantifying the risk:**

For a 600-line document like SKILL.md itself (~25,700 chars, ~6,400 tokens), the difference between full inclusion and 50% trimming is approximately 3,200 tokens per agent, or 19,200 tokens for 6 agents. This is 9.7% of the reported 197K total — a significant saving if achieved, but entirely dependent on orchestrator compliance.

For a smaller document (200 lines, ~3,000 tokens), the saving is ~1,500 tokens per agent, or ~9,000 tokens total — roughly 4.5% of the budget. The saving scales with document size, making it most valuable precisely for the documents where compliance is hardest (large documents with many sections to summarize).

**The 200-line threshold:**

The rules activate only for "file inputs with 200+ lines." This means documents under 200 lines are always included in full. At ~15 tokens/line, a 199-line document is ~3,000 tokens — which is significant if sent to 6 agents (18,000 tokens). The threshold should arguably be lower (100 lines or a token count rather than line count) to capture more cases.

#### Phase 3 Frontmatter-First Collection (lines 384-390) — FULL Review

The strategy reads:

> For each **valid** agent output, read the **YAML frontmatter** first (first ~60 lines). This gives you a structured list of all issues and improvements without reading full prose. Only read the prose body if:
> - An issue needs more context to understand
> - You need to resolve a conflict between agents

**The "~60 lines" assumption:**

Examining actual agent outputs from a real flux-drive run on the Clavain repository itself:

| Agent | Frontmatter end line | Notes |
|-------|---------------------|-------|
| fd-architecture | 66 | 10 issues + 5 improvements |
| fd-security | 59 | 7 issues + 4 improvements |
| fd-code-quality | ~45 (estimated) | Fewer findings |
| pattern-recognition-specialist | 83 | 12+ issues + improvements |

The `pattern-recognition-specialist` output has frontmatter extending to line 83 — 38% beyond the ~60 line estimate. If the orchestrator reads only the first 60 lines, it will miss issues and improvements for agents with many findings.

This is not a catastrophic failure — the strategy says "first ~60 lines" with the tilde indicating approximation. But the orchestrator (Claude) may interpret "first ~60 lines" literally using the `limit` parameter on the Read tool. If it does, agents with extensive frontmatter will have their later issues silently dropped from synthesis.

**Frontmatter quality for deduplication:**

The strategy assumes frontmatter titles provide enough context for deduplication. Examining real outputs:

- `"title: "Pervasive count mismatch: actual 32 skills / 24 commands..."` — descriptive, self-contained
- `"title: "Two independent upstream sync systems operate on different state files..."` — descriptive
- `"title: "Hook output uses bash heredoc with variable interpolation"` — ambiguous without prose context

Most titles are adequately descriptive, but approximately 1 in 5 requires prose context to understand whether it duplicates another agent's finding. The strategy does account for this ("Only read the prose body if: An issue needs more context") but provides no heuristic for when context is needed, leaving it to the orchestrator's judgment.

**Token savings from frontmatter-first:**

This is the strategy's strongest aspect. For 6 agents producing an average of 25,000 characters (~6,250 tokens) of output each, full prose reading would consume ~37,500 tokens during synthesis. Frontmatter-first reading consumes approximately:

- 6 agents x ~60 lines x ~15 tokens/line = ~5,400 tokens (frontmatter only)
- Plus 1-2 prose reads for context = ~6,250-12,500 additional tokens
- Total: ~11,650-17,900 tokens

This is a 52-69% reduction in synthesis-phase token cost compared to full-prose reading. The optimization is real and significant.

However, the saving depends on frontmatter quality. If agents produce vague titles, more prose reads are needed, and the saving shrinks. The spec provides no mechanism to enforce title quality at the agent prompt level — the YAML example shows `"Short description of the issue"` and `"Short description"` as placeholders, which is insufficient guidance for producing self-explanatory titles.

### Issues Found

**P0-1: Token trimming is unverifiable** (Phase 2 Prompt Template, lines 275-282)

The token trimming rules are instructions embedded in a "prompt template" code block. The orchestrator must interpret these as instructions-to-self (pre-trim the document before sending) rather than content-for-agent (paste into agent prompt). There is no enforcement: no token count check before launch, no document length assertion, no orchestrator-side trimming step in Phase 1 or Phase 2. The claimed 50% reduction in document tokens per agent (potentially 19,200 tokens for a 6-agent review of a 600-line document) is entirely dependent on LLM compliance with an ambiguously-placed instruction. This is P0 because it is the single largest claimed token optimization in the spec and it has no verification mechanism.

Evidence: A previous fd-performance review of a related brainstorm document (file: `/root/projects/Clavain/docs/research/flux-drive/2026-02-08-flux-drive-improvements-brainstorm/fd-performance.md`, P1-2) flagged the same enforcement gap. The current SKILL.md does not address this finding.

**P1-1: Conditional scaffolding always included** (Phase 2 Prompt Template, lines 263-271, 288-291)

The divergence context block (9 lines, ~90-130 tokens) and divergence-specific agent instructions (4 lines, ~40-60 tokens) are included in the template even when no divergence exists. For the majority of reviews (where document matches codebase), this is 130-190 tokens of dead weight per agent, or 780-1,140 tokens for 6 agents. The template should use explicit conditional markers (e.g., `{{#if divergence}}...{{/if}}`) or the spec should instruct the orchestrator to strip these blocks when not applicable.

**P1-2: YAML frontmatter example duplicated per agent** (Phase 2 Prompt Template, lines 310-329)

The 19-line YAML frontmatter example consumes ~250-350 tokens per agent. For 6 agents, this is 1,500-2,100 tokens on identical boilerplate. Within the current architecture (independent subagents), this is partially unavoidable, but the spec should at minimum acknowledge this as a cost center and consider whether a shorter example (e.g., just the key names without full example values) would suffice.

**P1-3: Frontmatter line count assumption violated** (Phase 3, lines 384-390)

The spec says "first ~60 lines" but real outputs show frontmatter extending to line 83 for agents with many findings. The `pattern-recognition-specialist` output from a real Clavain self-review has frontmatter ending at line 83, meaning a 60-line read would miss the last 23 lines of issues/improvements. The strategy needs either a higher line estimate or a delimiter-based approach (read until the second `---`).

**P2-1: Meta-instructional commentary in agent prompt** (Phase 2, lines 299-302)

The FULL/SUMMARY mapping example is instruction to the orchestrator about how to construct the prompt, but it appears inside the agent prompt template. If included verbatim in agent prompts, it wastes ~50-70 tokens per agent for a total of 300-420 tokens across 6 agents. Minor in isolation but symptomatic of the template's ambiguity about audience (orchestrator vs. agent).

**P2-2: Frontmatter titles insufficient for deduplication** (Phase 3, lines 384-390)

Approximately 1 in 5 frontmatter issue titles lacks sufficient context for deduplication without reading the prose body. The YAML example provides `"Short description"` as a placeholder but does not instruct agents to write self-contained, deduplication-friendly titles. Adding a line like "Titles must be specific enough to determine if two agents flagged the same issue without reading prose" would improve frontmatter utility.

### Improvements Suggested

**IMP-1: Move trimming to orchestrator pre-computation** (Phase 2, lines 275-282)

Instead of including trimming instructions in the agent prompt template, add a Step 1.4 or Step 2.0.5 where the orchestrator:
1. Takes the document profile from Step 1.1 (which already has section analysis)
2. For each agent, produces a trimmed document view based on the agent's domain
3. Passes the trimmed view directly into the agent prompt (no trimming instructions needed)

This eliminates compliance risk entirely and removes ~8 lines (~100-120 tokens) of trimming instructions from each agent prompt. The orchestrator already has the section analysis — this is a low-cost addition to Phase 1 that eliminates the most unreliable part of the optimization chain.

This aligns with the "domain-specific document slicing" idea identified in the brainstorm review (`/root/projects/Clavain/docs/research/flux-drive/2026-02-08-flux-drive-improvements-brainstorm/fd-performance.md`, IMP-2).

**IMP-2: Split template into fixed skeleton and variable block** (Phase 2, lines 253-349)

Restructure the template as:
- **Fixed skeleton** (~35-40 lines): Role assignment, project context, focus area, output path, prose format specification
- **Variable block**: Per-agent sections (trimmed document, divergence context if applicable, section mapping)
- **Shared reference** (not in template): YAML frontmatter schema (could be referenced rather than included)

This makes it clear which parts the orchestrator fills in vs. which parts go to the agent verbatim. It also makes conditional inclusion of divergence blocks explicit.

**IMP-3: Replace inline YAML example with format reference** (Phase 2, lines 310-329)

Instead of the 19-line YAML example, use a shorter instruction:

```
Output format: YAML frontmatter with keys: agent, tier, issues (array of {id, severity, section, title}), improvements (array of {id, title, section}), verdict (safe|needs-changes|risky). See flux-drive output format specification.
```

This reduces the per-agent template cost by ~200 tokens (from ~300 for the full example to ~100 for the compact reference). The risk is that agents may produce less consistent YAML without a concrete example — but since agents are LLMs that understand YAML schemas from description, the risk is low.

Total savings: ~1,200 tokens across 6 agents.

**IMP-4: Use delimiter-based frontmatter parsing** (Phase 3, lines 384-390)

Replace "read the YAML frontmatter first (first ~60 lines)" with "read each output file until the second `---` delimiter to extract the complete YAML frontmatter block." This handles variable-length frontmatter without assuming a line count. In practice, the orchestrator should use the Read tool without a line limit and parse up to the closing `---`.

**IMP-5: Add token budget assertion** (Phase 2, overall)

After constructing each agent's prompt (post-trimming), the orchestrator should estimate the token count (characters / 4 as a rough heuristic) and log it. If any agent prompt exceeds a ceiling (e.g., 15,000 tokens for input), warn the user. This provides the verification layer that P0-1 identifies as missing.

This does not require external tooling — a character count of the prompt string divided by 4 gives a reasonable token estimate. The spec should add this as a Step 2.1.5 between prompt construction and Task launch.

### Overall Assessment

The token optimization mechanisms in flux-drive are architecturally sound in concept but operationally fragile in execution. The prompt template carries justified fixed costs (~940-1,400 tokens per agent) but also avoidable waste (~300-500 tokens per agent from conditional scaffolding, meta-instructions, and verbose examples). The document trimming strategy — the single highest-impact optimization — has no enforcement or verification, making its contribution to actual token savings uncertain. The Phase 3 frontmatter-first collection strategy delivers real and significant synthesis-phase savings (52-69% reduction) but relies on an undersized line count assumption and underspecified title quality requirements. Verdict: **needs-changes** — the trimming enforcement gap (P0-1) must be resolved before the spec can claim reliable token optimization, and the frontmatter parsing assumption (P1-3) should be corrected to avoid silently dropping findings.
