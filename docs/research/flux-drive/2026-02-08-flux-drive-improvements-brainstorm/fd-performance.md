---
agent: fd-performance
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Improvement Area 2 (Token Optimization)"
    title: "model: haiku hint in SKILL.md is advisory-only — all agent .md files hardcode model: inherit"
  - id: P1-1
    severity: P1
    section: "Token Budget Target"
    title: "29% savings target math is internally inconsistent with the per-agent halving claim"
  - id: P1-2
    severity: P1
    section: "Improvement Area 2 (Token Optimization)"
    title: "Section trimming relies on orchestrator compliance with no enforcement or verification"
  - id: P1-3
    severity: P1
    section: "Open Questions"
    title: "Model selection question has no cost/quality analysis to inform the decision"
improvements:
  - id: IMP-1
    title: "Add a concrete token accounting breakdown that distinguishes prompt template, agent system prompt, document body, and tool-use overhead"
    section: "Token Budget Target"
  - id: IMP-2
    title: "Define a measurable verification step for section trimming (e.g., count tokens in the agent prompt before launch)"
    section: "Improvement Area 2 (Token Optimization)"
  - id: IMP-3
    title: "Provide a structured cost/quality tradeoff table for haiku vs sonnet vs opus on Tier 3 agent workloads"
    section: "Open Questions"
  - id: IMP-4
    title: "Add --fast flag cost projection showing the 3-agent ceiling's expected token range"
    section: "Open Questions"
  - id: IMP-5
    title: "Include Phase 4 Oracle token cost in the budget table — Oracle adds browser-mediated API overhead that is invisible to the current accounting"
    section: "Token Budget Target"
verdict: needs-changes
---

### Summary

The brainstorm identifies the right cost problem (38% token waste from document duplication) and proposes reasonable levers (section trimming, model downgrade, prompt compression). However, the Token Budget Target section contains an arithmetic inconsistency that undermines credibility: halving per-agent document cost from 12K to 6K across 6 agents saves 36K tokens, which should drop the total from 197K to 161K (an 18% reduction), not the claimed 140K (29% reduction). The remaining 21K gap is unaccounted for. More critically, the haiku model hint for Tier 3 agents is a SKILL.md recommendation that has no enforcement mechanism -- every agent `.md` file in the codebase hardcodes `model: inherit`, meaning the orchestrator would need to override model selection at Task dispatch time, a behavior not described anywhere in the brainstorm.

### Section-by-Section Review

#### Token Budget Target

The table presents three numbers:

| Metric | Current | Target |
|--------|---------|--------|
| Per-agent document cost | ~12K tokens | ~6K tokens |
| 6-agent total | ~197K tokens | ~140K tokens |
| Savings | -- | ~29% reduction |

The arithmetic does not hold. If the *only* optimization is halving per-agent document cost (12K to 6K per agent, times 6 agents), the savings are 36K tokens. That brings the total from 197K to 161K, which is an 18.3% reduction -- not 29%.

To reach 140K (a 57K reduction), the brainstorm would need to account for an additional 21K tokens of savings beyond document trimming. These could come from:
- Prompt template compression (Improvement Area 2, bullet 3): reducing from ~85 lines to ~50 lines saves roughly 700-1,000 tokens per agent (4-6K total for 6 agents)
- Model downgrades reducing output token costs (but the table says "6-agent total" which appears to measure input, not output)
- Reducing the number of agents launched (but the brainstorm does not propose this as a default)

Even with prompt compression, the maximum plausible savings are around 40-42K tokens (36K from trimming + 6K from prompt compression), yielding ~155K total -- a 21% reduction, not 29%.

The 140K target is aspirational rather than derived. This matters because if the implementation achieves only 18-21% savings instead of 29%, the team may perceive the optimization as having failed when it actually succeeded.

#### Improvement Area 2 (Token Optimization)

Four sub-items are proposed. Here is a cost/performance analysis of each:

**1. Enforce section trimming** -- This is the highest-leverage item and deserves priority. The SKILL.md already contains trimming instructions in the prompt template (lines 277-284), but compliance depends entirely on the orchestrator following them when constructing prompts. There is no verification step. A 200-line document at ~4 chars/token is roughly 3,000-4,000 tokens raw; a 600-line document like SKILL.md itself would be ~6,000-7,000 tokens. Trimming to 50% is plausible but should be verified by measuring actual prompt sizes post-trimming.

**2. Add haiku model hint** -- This is labeled as applying to "Tier 3 agents doing pattern/simplicity review." The SKILL.md roster already specifies `haiku` for `code-simplicity-reviewer` and `pattern-recognition-specialist`, and `sonnet` for the other four Tier 3 agents. However, every agent `.md` file in `agents/review/` uses `model: inherit`. The `model` field in the roster table is advisory text inside SKILL.md -- it does not propagate to the agent's own frontmatter. When Claude Code dispatches a Task with `subagent_type: clavain:review:code-simplicity-reviewer`, the model is determined by the agent's `.md` frontmatter (`inherit`), not by the SKILL.md table.

This means the brainstorm's model hint is currently a no-op. To make it effective, either:
- (a) Change the agent `.md` files to `model: haiku` / `model: sonnet` -- but this affects ALL uses of those agents, not just flux-drive invocations.
- (b) Pass `model` as a parameter in the Task tool call -- if Claude Code supports this override at dispatch time.
- (c) Document that the orchestrator should explicitly set the model parameter when launching Tier 3 agents via Task.

None of these options are discussed in the brainstorm.

**3. Compress prompt template** -- Reducing from ~85 to ~50 lines. The current template (lines 257-351 of SKILL.md) is 94 lines including the code block delimiters. At ~10-15 tokens per line of instructional markdown, that is ~940-1,400 tokens. Compressing to ~50 lines saves roughly 400-700 tokens per agent, or 2.4-4.2K tokens for 6 agents. This is a real but modest saving -- approximately 1-2% of the 197K total. Worth doing but should not be over-weighted.

**4. Domain-specific document slicing** -- "Phase 1 extracts per-domain section summaries that agents receive instead of full document." This is the most architecturally significant change because it shifts work from Phase 2 (each agent trims independently, with variable compliance) to Phase 1 (orchestrator pre-computes slices centrally, with guaranteed consistency). However, it adds orchestrator complexity: Phase 1 must now produce N different document views instead of one profile. For a brainstorm document with 6-8 sections, the orchestrator would need to decide which sections map to which agent domains.

This is the right direction but needs a concrete algorithm. Without one, the implementation will likely fall back to the existing "include the trimming instructions and hope agents comply" approach.

#### Open Questions

The three open questions are all performance-relevant but lack the analysis needed to make decisions:

**1. --fast flag limiting to 3 agents** -- This is a strong idea that would roughly halve token costs. A 3-agent review at the current 12K per-agent document cost would total roughly 100K tokens (3 agents x 12K document + 3 x ~20K for system prompt + tool use + output). With section trimming, this could drop to ~75-85K. The brainstorm should model this explicitly rather than leaving it as an open question.

**2. Thin-section enrichment testing** -- Step 3.3 launches additional Task Explore agents for thin sections. Each such agent adds another 15-30K tokens (system prompt + research + output). If a typical review finds 2-3 thin sections, this is 30-90K tokens *on top of* the base review cost. The brainstorm does not account for this in the token budget table at all. This should be called out as a potential budget-buster.

**3. Model selection for Tier 3 agents** -- The question asks "haiku saves tokens, sonnet is middle ground" but provides no quantitative framing. Key facts that should inform this decision:

| Model | Approximate input cost | Approximate output cost | Quality for review tasks |
|-------|----------------------|------------------------|------------------------|
| Haiku | ~$0.25/M input tokens | ~$1.25/M output tokens | Adequate for pattern matching, simplicity checks. Misses nuanced architectural reasoning. |
| Sonnet | ~$3/M input tokens | ~$15/M output tokens | Strong general review. Good cost/quality balance. |
| Opus (inherit) | ~$15/M input tokens | ~$75/M output tokens | Highest quality but 5-60x more expensive than alternatives. |

For a Tier 3 agent consuming ~12K input tokens and producing ~2K output tokens:
- Haiku: ~$0.003 + ~$0.0025 = ~$0.006 per agent
- Sonnet: ~$0.036 + ~$0.030 = ~$0.066 per agent
- Opus: ~$0.18 + ~$0.15 = ~$0.33 per agent

Using haiku for 2 Tier 3 agents instead of opus saves ~$0.65 per review. Over hundreds of reviews this adds up, but per-review it is modest. The real question is whether haiku's quality is sufficient for the agent's domain -- pattern recognition and simplicity checking are well-suited to haiku, but security review and architecture strategy benefit from stronger reasoning.

### Issues Found

**P0-1: Model hint is a no-op** (Improvement Area 2, Token Optimization)
The brainstorm proposes adding `model: haiku` hints for Tier 3 agents in the SKILL.md triage table. However, every agent `.md` file uses `model: inherit`. The SKILL.md table is documentation for the orchestrator, not a binding configuration. Unless the orchestrator explicitly passes a model override in the Task tool call -- and the brainstorm does not describe this mechanism -- the model hint will have no effect on actual model selection. This is a P0 because it is presented as a concrete savings mechanism but is currently non-functional.

**P1-1: Budget table arithmetic is wrong** (Token Budget Target)
Halving per-agent document cost from 12K to 6K saves 36K tokens (18% of 197K), not 57K tokens (29%). The target of 140K requires additional savings sources not itemized in the brainstorm. This creates a misleading success criterion.

**P1-2: Section trimming has no enforcement** (Improvement Area 2, Token Optimization)
The existing SKILL.md prompt template already instructs agents to trim. The brainstorm says "Actually implement" this rule, but the implementation is still phrased as prompt instructions ("you MUST trim"). There is no verification that trimming occurred -- no token count check, no document-length assertion, no orchestrator-side pre-trimming. The savings estimate of 12K to 6K per agent depends entirely on LLM compliance with an instruction it may partially ignore.

**P1-3: Open Questions lack decision-enabling analysis** (Open Questions)
All three open questions are performance-critical (--fast flag, thin-section cost, model selection) but are presented without the quantitative data needed to answer them. The brainstorm should at minimum model the token cost of each option.

### Improvements Suggested

**IMP-1: Decompose the token budget into component costs**
The current budget table shows only "per-agent document cost" and "6-agent total." A more useful breakdown would separate:
- Agent system prompt (from `.md` file): ~700-1,500 tokens per agent
- Prompt template (from SKILL.md): ~1,000-1,400 tokens per agent
- Document body (the review target): variable, currently ~12K, target ~6K
- Tool-use overhead (Read, Grep, Glob calls by the agent): ~2-5K per agent
- Agent output: ~1-3K per agent

This decomposition reveals which components are actually dominant and where optimization effort should focus. If tool-use overhead is 2-5K per agent, that is 12-30K total -- comparable to the document duplication problem and currently invisible.

**IMP-2: Add a measurable verification for section trimming**
Instead of relying on prompt instructions, the orchestrator should either:
- (a) Pre-trim the document in Phase 1 and pass the trimmed version to agents (eliminates compliance risk entirely), or
- (b) Measure the prompt token count before launching each agent and log it (enables post-hoc verification and regression detection)

Option (a) aligns with the brainstorm's "domain-specific document slicing" item and should be framed as the primary mechanism, not a separate item.

**IMP-3: Provide a model selection decision table**
Replace the open question "What model should Tier 3 agents default to?" with a structured analysis:
- Which Tier 3 agents are quality-sensitive (security-sentinel, architecture-strategist) vs quality-tolerant (code-simplicity-reviewer, pattern-recognition-specialist)?
- What is the per-review dollar cost difference for each model choice?
- Has anyone tested haiku on these agent prompts? If not, propose a comparison test.

**IMP-4: Model the --fast flag's cost envelope**
A 3-agent ceiling with section trimming should land in the 75-100K token range. Model this explicitly so the --fast flag has a concrete cost target, not just an agent count limit.

**IMP-5: Include Phase 4 Oracle cost in the budget**
Oracle's token costs are invisible to the current budget because Oracle runs via CLI (browser-mediated GPT-5.2 Pro), not through Claude's API. But from a total-cost-of-review perspective, Oracle adds significant latency (up to 5 minutes timeout) and external API costs. The budget table should include Oracle as a separate line item even if its costs are measured differently (wall-clock time + external API).

### Overall Assessment

The brainstorm correctly identifies document duplication as the primary token waste vector and proposes reasonable optimizations. However, the Token Budget Target contains an arithmetic error that will create false expectations, and the most concrete optimization (model downgrade for Tier 3) is currently non-functional due to a gap between the SKILL.md's advisory model hints and the agents' hardcoded `model: inherit`. The Open Questions section needs quantitative analysis before implementation can proceed confidently. Verdict: **needs-changes** -- fix the budget math, resolve the model override mechanism, and add decision-enabling data to the open questions before writing the implementation plan.
