### Findings Index
- P0 | P0-1 | "Template (lines 63-101)" | Generated agents lack persona, voice, and decision heuristics — producing generic reviewers instead of specialized experts
- P0 | P0-2 | "Template (lines 84-86)" | Identical suffix on every bullet destroys domain specialization — agents cannot distinguish what to DO with each review area
- P1 | P1-1 | "Template (lines 63-101)" | No "What NOT to Flag" section — generated agents will duplicate core fd-* agent findings despite Focus Rules saying not to
- P1 | P1-2 | "Template (lines 63-101)" | Missing success criteria and example outputs make agent behavior unpredictable across invocations
- P1 | P1-3 | "Domain Profile (lines 68-93)" | Agent Specifications lack action verbs and review methodology — "Key review areas" are noun phrases, not instructions
- P1 | P1-4 | "Template (lines 63-101)" | No frontmatter block — generated agents miss model selection, description, and routing examples
- IMP | IMP-1 | "Template (lines 63-101)" | Template wastes ~120 tokens per agent on static boilerplate that could be injected at dispatch time
- IMP | IMP-2 | "Template (lines 88-93)" | "How to Review" section is generic wisdom, not domain-calibrated methodology
- IMP | IMP-3 | "Domain Profile (lines 68-93)" | Agent Specifications should include anti-overlap clauses defining boundaries with core fd-* agents
Verdict: needs-changes

### Summary

The flux-gen template (lines 63-101 of `commands/flux-gen.md`) produces structurally valid but substantively weak agent prompts. Comparing the two generated agents (`fd-plugin-structure`, `fd-prompt-engineering`) against the seven core fd-* agents reveals a quality gap that undermines the entire domain-agent concept. Core agents have personas, structured methodologies with numbered subsections, "What NOT to Flag" guardrails, decision lenses, and language-specific depth. Generated agents get five repetitive bullets with identical suffixes and four lines of generic advice. The template transforms carefully crafted domain expertise from the profile into flat, undifferentiated instructions.

The root cause is that the template treats agent generation as a formatting exercise (slot Focus and Key Review Areas into a fixed structure) rather than a prompt engineering exercise (translate domain expertise into effective review behavior). The domain profile provides the *what* but the template fails to generate the *how*, *when to stop*, and *what good looks like*.

### Issues Found

#### P0-1: Generated agents lack persona, voice, and decision heuristics

**Severity**: P0 — this is the core value proposition of flux-gen and it fundamentally underdelivers

The seven core fd-* agents each have distinct identities that shape their review behavior:

- `fd-architecture` (line 7): "evaluate structure first, then complexity" — establishes review sequence
- `fd-correctness` (line 7): "half data-integrity guardian, half concurrency bloodhound" — establishes persona and scope
- `fd-safety` (lines 26-29): risk classification matrix (High/Medium/Low) — establishes prioritization framework
- `fd-user-product` (line 19): "Start by stating who the primary user is" — establishes first action
- `fd-performance` (lines 16-23): requires identifying performance profile type before reviewing — establishes context-gathering

The generated `fd-prompt-engineering` agent (the file reviewing this review right now) has none of this. Its entire identity is: "You are a project-specific flux-drive reviewer focused on **skill instruction clarity, agent prompt effectiveness, token efficiency, routing accuracy**." That is a topic list, not a reviewer identity.

**Impact**: Without a persona or decision framework, generated agents produce generic checklist reviews instead of the opinionated, structured analysis that core agents deliver. The generated agent has no way to decide what matters MORE — it treats all five bullet points as equally weighted, whereas core agents have explicit prioritization ("Start with issues that can corrupt persisted data" in fd-correctness line 82).

**Concrete fix**: The template needs three additions:
1. A persona line derived from the Focus field (e.g., "You evaluate whether plugin instructions actually produce the behavior they claim to")
2. A "Review Sequence" or "First Action" directive (what to do BEFORE reviewing — like fd-safety's threat model classification)
3. A "Prioritization" section that ranks the 5 review areas by impact severity

#### P0-2: Identical suffix destroys domain specialization

**Severity**: P0 — directly neutralizes the domain profile's carefully differentiated review areas

Template line 86:
```
- **{bullet}**: Examine this aspect carefully. Look for concrete evidence in the code or document. Flag specific issues with file paths and line numbers where possible.
```

Every bullet in every generated agent gets the identical 29-word suffix: "Examine this aspect carefully. Look for concrete evidence in the code or document. Flag specific issues with file paths and line numbers where possible."

This is visible in both generated agents. In `fd-plugin-structure.md`, all 5 bullets end identically. In `fd-prompt-engineering.md`, all 5 bullets end identically.

**Why this is P0, not just the P1 that fd-quality found**: fd-quality flagged this as "repetitive boilerplate." The prompt engineering impact is worse than repetition — the suffix actively prevents specialization. Consider the difference between:

- "**plugin.json schema compliance**: Examine this aspect carefully..." (generated)
- "**plugin.json schema compliance**: Validate required fields (name, version, description) exist and match marketplace.json. Check that declared skill/agent/command paths resolve to real files. Flag version strings that don't follow semver." (what a prompt engineer would write)

The suffix tells the agent HOW to present findings (cite files and lines) but not HOW to review (what to look for, what constitutes a violation, what the expected state is). The domain profile's "Key review areas" are noun phrases that need to be expanded into action-oriented instructions, and the template's one-size-fits-all suffix fails to do that expansion.

**Concrete fix**: Remove the static suffix entirely. Instead, the template should instruct the LLM generating the agent to expand each bullet into 2-3 sentences of domain-specific review guidance. Alternatively, the domain profile's Agent Specifications should include per-bullet action descriptions that the template can slot in directly.

#### P1-1: No "What NOT to Flag" section causes finding duplication

**Severity**: P1 — generates predictable noise in multi-agent reviews

Every core fd-* agent has either an explicit "What NOT to Flag" section (fd-quality lines 79-82, fd-safety lines 72-76, fd-performance lines 72-75) or equivalent scope-limiting language in Focus Rules. These sections are critical for multi-agent review because they prevent N agents from all flagging the same obvious issue.

The generated agents have Focus Rules that say "Don't duplicate findings that core fd-* agents would catch" but provide no specifics about WHAT those agents catch. An agent reading that instruction has to guess what fd-architecture or fd-safety would find. Compare:

- Generated: "Don't duplicate findings that core fd-* agents would catch (architecture, safety, correctness, quality, performance, user-product)"
- What's needed: "Do NOT flag: general code style issues (fd-quality), missing error handling (fd-correctness), security vulnerabilities in hooks (fd-safety), overly complex abstractions (fd-architecture). Your domain is strictly: {Focus line}."

**Concrete fix**: Add a "What NOT to Flag" section to the template with concrete exclusions derived from the agent's domain. The domain profile should specify per-agent exclusions, or the template should generate them by inverting the other agents' focus areas.

#### P1-2: Missing success criteria and example outputs

**Severity**: P1 — agents cannot self-calibrate quality

Core agents define what "good" looks like:
- fd-correctness has "Failure Narrative Method" (lines 66-71): "Describe at least one concrete interleaving for each major race finding"
- fd-safety has risk classification tiers (lines 26-29) with examples
- fd-architecture has "Decision Lens" (lines 80-82): "Favor changes that reduce architectural entropy"

Generated agents have no equivalent. `fd-prompt-engineering` doesn't know whether a good review of "token budget optimization" means counting tokens, estimating context window impact, suggesting specific content moves, or all three.

**Concrete fix**: Add a "Success Criteria" or "What Good Looks Like" section to the template. Even a single sentence per agent would help: "A successful review identifies at least one concrete token savings opportunity with before/after estimates."

#### P1-3: Domain profile Agent Specifications use noun phrases, not instructions

**Severity**: P1 — the source material fed into the template is itself insufficiently actionable

From `config/flux-drive/domains/claude-code-plugin.md` lines 87-92:
```
Key review areas:
- Instruction clarity and unambiguity
- Token budget optimization (inline vs referenced content)
- Routing table accuracy (triggers match intended use cases)
- Agent prompt specificity (clear success criteria, example outputs)
- Skill composition patterns (when skills reference other skills)
```

These are topic headings, not review instructions. Compare with the Injection Criteria in the same file (lines 48-49):
```
- Check that every skill has a clear one-line description in its frontmatter (used for routing and help text)
- Flag overly long SKILL.md files — instructions injected into context consume tokens; keep under 100 lines with references
```

The Injection Criteria use action verbs ("Check that", "Flag", "Verify") and include specific thresholds ("under 100 lines"). The Agent Specifications lack both. The template cannot compensate for source material that doesn't contain actionable review instructions.

**Concrete fix**: Rewrite Agent Specifications to use the same action-verb format as Injection Criteria. Each bullet should be: verb + what to check + threshold or success criteria. Example:
```
- Check that SKILL.md instructions use imperative verbs and specific tool names, not vague directives like "review the code"
- Measure inline content vs referenced content ratio; flag skills where >60% of tokens are reference material that could be loaded on-demand
- Verify routing table triggers in using-clavain match actual command/skill names and don't overlap
```

#### P1-4: No frontmatter block in generated agents

**Severity**: P1 — generated agents miss model selection and routing metadata

Every core fd-* agent has YAML frontmatter:
```yaml
---
name: fd-architecture
description: "Flux-drive Architecture & Design reviewer — evaluates..."
model: sonnet
---
```

The template (lines 63-101) generates no frontmatter. Generated agents in `.claude/agents/` start with `# fd-{name}`. This means:
1. No `model:` field — the agent uses whatever default the invoker sets, not a deliberate choice
2. No `description:` field — routing and help text have nothing to work with
3. No structured examples in the description — the core agents include `<example>` blocks that improve routing accuracy

Since generated agents are invoked via `subagent_type: general-purpose` with content pasted as system prompt (per `commands/flux-gen.md` line 134 and `phases/launch.md` lines 160-162), the frontmatter is less critical than for plugin agents. However, if a user wants to invoke a generated agent directly (not through flux-drive), the missing metadata matters.

**Concrete fix**: Add a frontmatter block to the template:
```yaml
---
name: fd-{name}
description: "Project-specific {domain} reviewer — {Focus line}"
model: sonnet
---
```

### Improvements Suggested

#### IMP-1: Move static boilerplate to dispatch-time injection

**Rationale**: Token efficiency — the template's value proposition

The following sections are identical across ALL generated agents:
- "First Step (MANDATORY)" (8 lines, ~80 tokens)
- "How to Review" (4 lines, ~50 tokens)
- Focus Rules preamble (4 lines, ~60 tokens)

Total: ~190 tokens per agent, repeated identically. For a project with 4 generated agents, that is ~760 tokens of duplicated static content loaded into context.

Since generated agents are always invoked through flux-drive (which already injects its own prompt template per `phases/launch.md` lines 235-384), these sections could be injected at dispatch time rather than baked into every agent file. The agent file itself would contain only the domain-specific content: persona, review methodology, prioritization, and scope boundaries.

This is ironic because "Token budget optimization (inline vs referenced content)" is literally one of fd-prompt-engineering's own review areas — and the template that generates fd-prompt-engineering violates it.

**Concrete change**: Split the template into:
- **Agent-specific content** (written to `.claude/agents/fd-{name}.md`): persona, review areas with specific instructions, "What NOT to Flag", success criteria
- **Shared preamble** (injected by flux-drive at dispatch time): "First Step", "How to Review", generic Focus Rules

#### IMP-2: Replace generic "How to Review" with domain-calibrated methodology

The "How to Review" section (template lines 88-93) is:
```
1. Read before judging
2. Be specific
3. Prioritize
4. Respect context
```

This is universally applicable advice that any reviewer should follow. It consumes tokens without adding domain-specific value. Compare with core agents:

- fd-correctness: "Start by writing down the invariants that must remain true. If invariants are vague, correctness review is guesswork." (line 21)
- fd-safety: "Before diving deep, classify the change risk: High/Medium/Low" (line 25)
- fd-architecture: Three numbered subsections with 10+ concrete bullets each

The generated agents should have methodology sections that match their domain. For fd-prompt-engineering, this might be:
```
### How to Review
1. Count tokens in each skill/agent file and identify the top 3 by size
2. For each, classify content as: core instruction, reference material, boilerplate
3. Check if triggers/routing match the actual skill behavior
4. Read generated output from the skill to verify instruction clarity
```

#### IMP-3: Add anti-overlap clauses to domain profile Agent Specifications

The domain profile (`config/flux-drive/domains/claude-code-plugin.md`) defines both Injection Criteria (for core agents) and Agent Specifications (for generated agents), but doesn't define the boundary between them.

For example, the fd-quality Injection Criteria include "Check that agent prompts include example outputs and success criteria" (line 49). The fd-prompt-engineering Agent Specification includes "Agent prompt specificity (clear success criteria, example outputs)" (line 91). These overlap directly.

Without explicit anti-overlap clauses, running both core agents (with domain injection) and generated agents produces duplicated findings. The profile should specify: "fd-prompt-engineering covers prompt effectiveness at depth; fd-quality injection covers prompt quality at surface level (presence/absence checks only)."

### Overall Assessment

The flux-gen template is architecturally sound (correct file placement, proper Step ordering, good user interaction in Step 3) but produces prompts that are approximately 30% as effective as the hand-crafted core agents. The gap is not in structure but in prompt engineering substance: the core agents are opinionated experts with methodologies, personas, and guardrails; the generated agents are topic-labeled generalists with repetitive instructions. Fixing P0-1 and P0-2 would close the majority of this gap. The P1 fixes would bring generated agents to near-parity with core agents for their narrower domains.

<!-- flux-drive:complete -->
