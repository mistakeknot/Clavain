---
agent: fd-architecture
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Agent Roster — Tier 3"
    title: "Roster omits 8 registered review agents that could be relevant"
  - id: P1-1
    severity: P1
    section: "Phase 1 — Step 1.2"
    title: "Tier bonus arithmetic creates an effective floor of 1 for all Tier 1/2 agents, undermining 'irrelevant' scoring"
  - id: P1-2
    severity: P1
    section: "Phase 2 — Step 2.1"
    title: "Token optimization trimming delegated to agents with no enforcement or fallback"
  - id: P1-3
    severity: P1
    section: "Phase 4 — Step 4.3"
    title: "Splinterpeer invoked inline in main session but designed for multi-model input it will not have"
  - id: P1-4
    severity: P1
    section: "Phase 3 — Step 3.4"
    title: "Write-back to INPUT_FILE during concurrent reviews risks data loss"
  - id: P1-5
    severity: P1
    section: "Phase 4 — Step 4.2"
    title: "Oracle output format is unstructured prose — comparison against structured YAML frontmatter is underspecified"
  - id: P1-6
    severity: P1
    section: "Phase 1 — Step 1.2"
    title: "Deduplication rule 4 contradicts itself — prefers T1 except when it doesn't"
  - id: P2-1
    severity: P2
    section: "Integration"
    title: "Integration section is thin — no mention of using-clavain routing, hooks, or MCP server dependencies"
improvements:
  - id: IMP-1
    title: "Add concurrency-reviewer, agent-native-reviewer, and language-specific reviewers to roster"
    section: "Agent Roster"
  - id: IMP-2
    title: "Define explicit Oracle output format requirement in the Oracle prompt template"
    section: "Agent Roster — Tier 4"
  - id: IMP-3
    title: "Add a file-locking or sequential-write strategy for Step 3.4"
    section: "Phase 3 — Step 3.4"
  - id: IMP-4
    title: "Specify behavior when the document is itself the flux-drive SKILL.md (self-review)"
    section: "Input"
  - id: IMP-5
    title: "Expand Integration section with hook dependencies, MCP server usage, and routing table entry"
    section: "Integration"
verdict: needs-changes
---

### Summary

The flux-drive SKILL.md is a well-structured 600-line orchestration spec with clear phase boundaries and a thoughtful tiered agent model. However, it has a significant roster gap: 8 of the 20 registered review agents are invisible to flux-drive's triage, meaning the skill can never select concurrency-reviewer, agent-native-reviewer, plan-reviewer, deployment-verification-agent, data-migration-expert, or any of the 4 language-specific kieran reviewers. The scoring arithmetic for Tier 1/2 bonuses creates a floor that makes the "irrelevant" score functionally impossible for codebase-aware agents. Phase 4's cross-AI escalation chain has an input-format mismatch between Oracle's unstructured prose output and the YAML frontmatter the rest of the pipeline expects, and the inline splinterpeer invocation assumes multi-model input that is not actually available in this context.

### Section-by-Section Review

#### Input (lines 9-32)

The path derivation rules are sound. The `PROJECT_ROOT` detection via `.git` ancestor is correct. The absolute path requirement for `OUTPUT_DIR` (line 31) is well-motivated and explicitly called out.

One edge case: when `INPUT_PATH` points to a file that is itself inside the `docs/research/flux-drive/` tree (e.g., reviewing a previous flux-drive output), the `INPUT_STEM` derivation would create a nested output directory like `docs/research/flux-drive/SKILL/fd-architecture/`. This is not necessarily wrong, but the spec does not acknowledge it or define whether self-referential reviews are supported.

Another edge case: `PROJECT_ROOT` falls back to `INPUT_DIR` when no `.git` ancestor exists. This means reviewing a file on a non-git filesystem writes output alongside the input, which could be surprising. The spec should state this explicitly as intended behavior or guard against it.

#### Phase 1 — Analyze + Static Triage (lines 35-153)

**Step 1.0 (lines 37-56):** The project understanding step is well-designed. The qmd MCP integration (line 47-50) is a good use of the available infrastructure — qmd is registered in `plugin.json` as a stdio MCP server. The divergence detection (lines 51-56) is a strong defensive measure.

**Step 1.1 (lines 59-91):** The document profile structure is comprehensive. The section analysis with thin/adequate/deep classification (lines 77-78) is the key input to triage and is well-defined. The review goal adaptation by document type (lines 83-88) is practical.

**Step 1.2 (lines 93-131):** This is where the most significant architectural issues cluster.

**Scoring system (lines 96-100):** The 0/1/2 base scoring plus tier bonuses creates problematic arithmetic:
- A Tier 1 agent scored as "irrelevant" (base 0) gets +1 bonus = score 1. Per rule 2 (line 107), agents scoring 1 are included if they cover a thin section. This means a Tier 1 agent in a completely wrong domain can still be selected if any section is thin — which undermines the "irrelevant" classification.
- A Tier 3 agent scored as "maybe" (base 1) gets no bonus = score 1. This is the same score as an "irrelevant" Tier 1 agent, creating ambiguity in the deduplication logic.

**Deduplication rule 4 (lines 108):** "If a Tier 1 or Tier 2 agent covers the same domain as a Tier 3 agent, drop the Tier 3 one — unless the target project lacks CLAUDE.md/AGENTS.md, in which case prefer the Tier 3 generic." This rule has a logical gap: it assumes domain overlap is binary (same/different), but the roster has cases where domains partially overlap (e.g., fd-architecture covers "module boundaries, component structure" while architecture-strategist covers "system design, component boundaries" — overlapping on component boundaries but diverging on module vs. system scope). The spec does not define how to handle partial overlap.

**Step 1.3 (lines 133-152):** The user confirmation step is good practice. The three options (Approve/Edit/Cancel) are sufficient.

#### Agent Roster (lines 156-215)

**Tier 1 (lines 158-168):** All 5 agents (`fd-architecture`, `fd-code-quality`, `fd-performance`, `fd-security`, `fd-user-experience`) exist in `/root/projects/Clavain/agents/review/` with matching `name` fields in their YAML frontmatter. The `subagent_type` values follow the `clavain:review:<name>` convention consistently. These are verified as registered.

**Tier 2 (lines 170-177):** The dynamic discovery mechanism (check `.claude/agents/fd-*.md`) is elegant and extensible. The `general-purpose` subagent_type with pasted system prompt is the correct approach for non-plugin agents.

**Tier 3 (lines 179-189):** All 6 agents exist and are registered:
- `architecture-strategist` -- verified in `/root/projects/Clavain/agents/review/architecture-strategist.md`
- `code-simplicity-reviewer` -- verified
- `performance-oracle` -- verified
- `security-sentinel` -- verified
- `pattern-recognition-specialist` -- verified
- `data-integrity-reviewer` -- verified

**Missing from Roster:** The following 8 registered review agents are completely absent from the flux-drive roster:

| Agent | File | Potential Domain Relevance |
|-------|------|---------------------------|
| `concurrency-reviewer` | `agents/review/concurrency-reviewer.md` | Race conditions, async bugs — relevant for any concurrent system |
| `agent-native-reviewer` | `agents/review/agent-native-reviewer.md` | Agent accessibility parity — relevant for agent-facing tools |
| `plan-reviewer` | `agents/review/plan-reviewer.md` | Plan validation — directly relevant for plan-type documents |
| `deployment-verification-agent` | `agents/review/deployment-verification-agent.md` | Deploy checklists — relevant for deployment plans |
| `data-migration-expert` | `agents/review/data-migration-expert.md` | Migration safety — relevant for data migration plans |
| `kieran-go-reviewer` | `agents/review/kieran-go-reviewer.md` | Go-specific idioms |
| `kieran-python-reviewer` | `agents/review/kieran-python-reviewer.md` | Python-specific idioms |
| `kieran-typescript-reviewer` | `agents/review/kieran-typescript-reviewer.md` | TypeScript-specific idioms |
| `kieran-shell-reviewer` | `agents/review/kieran-shell-reviewer.md` | Shell-specific idioms |

This is the most significant gap. The AGENTS.md describes 20 review agents, the routing table mentions "triaged from roster — up to 8 agents", but the flux-drive roster only includes 11 of those 20 (5 Tier 1 + 6 Tier 3). The missing agents cannot be selected regardless of document content because they are invisible to the triage scoring system.

The language-specific reviewers (kieran-*) are especially notable omissions because Step 1.1 explicitly asks for "Languages" in the document profile, suggesting the spec *intended* to route to language specialists but never connected the wiring.

**Tier 4 (lines 192-214):** The Oracle availability check (lines 193-196) correctly mirrors the logic in `hooks/session-start.sh` (line 38), which checks `command -v oracle` and `pgrep -f "Xvfb :99"`. The SessionStart hook reports "oracle: available for cross-AI review" as companion context, and line 194 of the SKILL.md checks for that exact string. This is consistent.

The Oracle prompt template (lines 207-209) is reasonable but outputs unstructured prose to a markdown file. This creates an asymmetry with all other agents, which output structured YAML frontmatter. Phase 4's comparison logic (Step 4.2) must manually parse Oracle's prose against the synthesized YAML findings — but the spec does not define how to do this parsing.

#### Phase 2 — Launch (lines 217-356)

The prompt template (lines 255-349) is well-structured. The token optimization instruction (lines 275-283) delegates trimming responsibility to the orchestrating agent ("you MUST trim the document"), which is correct — the orchestrator knows which sections map to which agent's focus area.

However, there is no enforcement mechanism. If the orchestrator fails to trim (or trims incorrectly), agents receive the full document and consume unnecessary tokens. Given that this runs up to 8 agents in parallel, token waste compounds quickly. A fallback such as "if the document exceeds N tokens, truncate non-focus sections to headers only" would provide a safety net.

The `run_in_background: true` requirement (line 231) is critical and well-emphasized. The output format specification in the prompt template (lines 310-348) is thorough — it defines the YAML frontmatter schema, prose structure, and severity levels clearly.

#### Phase 3 — Synthesize (lines 358-483)

**Step 3.0 (lines 360-369):** The polling strategy (check every 30 seconds, timeout at 5 minutes) is reasonable. The fallback to "no findings" for missing agents is correct.

**Step 3.1 (lines 371-382):** The three-tier validation (Valid/Malformed/Missing) is good defensive design. The fallback to prose-based reading for malformed frontmatter is the right call.

**Step 3.2 (lines 384-389):** Reading only the YAML frontmatter first (~60 lines) is a smart token optimization for synthesis. The conditional prose reading for conflict resolution is well-motivated.

**Step 3.3 (lines 391-398):** Deduplication and convergence tracking are well-defined. The priority rule for codebase-aware agents (line 398) is consistent with the tier model.

**Step 3.4 (lines 400-467):** The write-back strategy has a concurrency concern. If flux-drive is run concurrently on the same file (which is possible via multiple Claude Code sessions), two instances could read the same `INPUT_FILE`, generate different findings, and overwrite each other. The spec does not mention locking, versioning, or conflict detection.

The "Deepen thin sections" feature (lines 436-466) for plans is architecturally interesting — it launches additional `Task Explore` agents and uses Context7 MCP. This is a second wave of agent launches that is not counted in the Phase 2 cap of 8 agents. The spec should clarify whether these research agents count toward the cap.

The repo review path (lines 468-474) correctly avoids modifying existing files and writes a standalone summary. This is clean separation.

#### Phase 4 — Cross-AI Escalation (lines 486-583)

**Step 4.1 (lines 488-499):** When Oracle is absent, offering `/clavain:interpeer` is the correct fallback. The interpeer skill provides Claude-Codex bidirectional review, which is a lighter-weight cross-AI option.

**Step 4.2 (lines 501-515):** The four-category comparison framework (Agreement, Oracle-only, Claude-only, Disagreement) is well-designed. However, the implementation is underspecified: Oracle's output is unstructured prose (written to `oracle-council.md` via CLI), while Claude agents produce structured YAML frontmatter. The spec says "Compare Oracle's findings with the synthesized findings from Step 3.2" but does not explain how to normalize the two formats for comparison. This is left entirely to the orchestrator's judgment.

**Step 4.3 (lines 517-536):** The auto-chain to splinterpeer has an architectural mismatch. Splinterpeer's own SKILL.md (line 18) says its input is "Two or more model perspectives (from winterpeer, prompterpeer, or manual paste)." In the flux-drive context, the "two perspectives" are: (1) the synthesized Claude findings and (2) Oracle's prose output. But splinterpeer was designed for structured multi-model outputs, not for one structured synthesis + one prose blob. The spec says to "structure each disagreement using splinterpeer's Phase 2 format" (line 534), which puts the burden on the orchestrator to pre-process Oracle's prose into splinterpeer-compatible format — an undocumented transformation step.

Additionally, splinterpeer is invoked "inline (do not dispatch a subagent)" (line 532). This means the full splinterpeer workflow runs in the main session context, which already contains the entire flux-drive context. This could approach or exceed context limits for large documents with many findings.

**Step 4.4 (lines 538-556):** The winterpeer escalation offer is well-structured with clear indicators (P0 severity, security disagreements). The three options are good. The scope limitation ("just the critical decision, not the whole document" — line 556) is important for keeping winterpeer focused.

**Step 4.5 (lines 558-583):** The cross-AI summary template is comprehensive. The table format with confidence levels is useful for decision-making.

#### Integration (lines 585-600)

This section is thin relative to the complexity of the skill. It lists chain relationships and the calling command, but omits:

1. **Hook dependency**: flux-drive relies on the SessionStart hook's Oracle detection (line 38-39 of `session-start.sh`) for its Tier 4 availability check. This coupling should be documented.
2. **MCP server dependencies**: Step 1.0 uses qmd for semantic search, Step 3.4 uses Context7 for research — both are registered in `plugin.json`. The Integration section should note these.
3. **Routing table entry**: The `using-clavain` routing table has flux-drive at "Review (docs)" row (line 38 of using-clavain/SKILL.md). This is the entry point that routes users to the skill.
4. **Conflict with code-review plugin**: AGENTS.md line 267 lists code-review plugin as conflicting with `/review` + `/flux-drive`. This means flux-drive is part of the reason that plugin is disabled — worth noting in Integration.

### Issues Found

**P0-1: Roster omits 8 registered review agents** (Agent Roster, lines 156-214)
The roster includes only 11 of 20 review agents. The missing 8 — concurrency-reviewer, agent-native-reviewer, plan-reviewer, deployment-verification-agent, data-migration-expert, and the 4 kieran language-specific reviewers — cannot be selected by triage regardless of document content. This is especially problematic for:
- Plan documents (plan-reviewer is literally named for this use case)
- Concurrent system designs (concurrency-reviewer is the only agent for race conditions)
- Go/Python/TypeScript/Shell codebases (language-specific reviewers provide deeper idiom analysis than generic agents)

The omission appears unintentional: the document profile explicitly collects "Languages" (line 72) but has no language-specific agents to route to.

**P1-1: Tier bonus creates a floor score of 1 for all T1/T2 agents** (Phase 1, lines 96-100)
An "irrelevant" (base 0) Tier 1 agent gets +1 = score 1. Per rule 2, score 1 agents are included if they cover a thin section. This means ANY Tier 1 agent can be selected for ANY document if even one section is thin — defeating the purpose of domain-based triage. Consider changing the bonus to only apply to agents scoring 1+ base, or changing the threshold for inclusion to 2+.

**P1-2: Token trimming has no enforcement** (Phase 2, lines 275-283)
The prompt template tells agents to trim to ~50% but provides no mechanism to verify this happened. If the orchestrator includes the full document in all 8 agent prompts (a likely failure mode when the orchestrator is under cognitive load), token costs multiply 8x with no warning.

**P1-3: Splinterpeer input format mismatch** (Phase 4, lines 517-536)
Splinterpeer expects "Two or more model perspectives" as structured input. In flux-drive's invocation, it receives one synthesized YAML summary and one unstructured Oracle prose blob. The transformation from these inputs to splinterpeer's Phase 2 format is undocumented and adds fragility to the escalation chain.

**P1-4: No concurrent write protection for INPUT_FILE** (Phase 3, lines 400-434)
If two flux-drive sessions review the same file simultaneously, they will read the same version, independently generate findings, and the last writer wins. This is a realistic scenario for teams sharing a codebase. The spec should either document this as a known limitation or add a lightweight guard (e.g., check for existing `## Flux Drive Enhancement Summary` section before writing).

**P1-5: Oracle output format asymmetry** (Phase 4, lines 501-515)
All Claude-based agents produce structured YAML frontmatter with machine-parseable issues. Oracle produces free-form prose via CLI redirect. The comparison in Step 4.2 must bridge this format gap, but the spec provides no guidance on how to normalize Oracle findings into the same structure for comparison.

**P1-6: Partial domain overlap undefined in deduplication** (Phase 1, line 108)
Rule 4 says "covers the same domain" but domains partially overlap (e.g., fd-architecture and architecture-strategist both cover "component boundaries" but diverge on scope). The spec needs to define whether partial overlap triggers deduplication or not.

**P2-1: Integration section is thin** (Integration, lines 585-600)
The integration section omits hook dependencies, MCP server dependencies, routing table coupling, and conflict relationships with disabled plugins. For a 600-line orchestration spec, the integration footprint is significantly underspecified.

### Improvements Suggested

**IMP-1: Add missing agents to roster as Tier 3 entries**
Add concurrency-reviewer, agent-native-reviewer, plan-reviewer, deployment-verification-agent, data-migration-expert, and the 4 kieran language reviewers to the Tier 3 table. The language-specific reviewers could form a "Tier 3b — Language Specialists" sub-tier that is selected based on the "Languages" field in the document profile. Plan-reviewer could be auto-included (score boost) when document type is "plan".

**IMP-2: Require structured output from Oracle**
Modify the Oracle prompt template (line 208) to explicitly request YAML frontmatter in the same format as Claude agents. This would eliminate the format asymmetry in Phase 4 and enable machine-parseable comparison. Example addition to the Oracle prompt: "Format your output with YAML frontmatter matching this schema: agent, tier, issues (id, severity, section, title), improvements, verdict."

**IMP-3: Add write-back guard for concurrent reviews**
Before writing findings to `INPUT_FILE` in Step 3.4, check if a `## Flux Drive Enhancement Summary` section already exists. If it does, either append findings below it (with a timestamp to distinguish runs) or warn the user and ask whether to overwrite. This prevents silent data loss from concurrent reviews.

**IMP-4: Define self-review behavior**
When `INPUT_FILE` is itself inside `docs/research/flux-drive/`, the spec should either disallow the review (guard clause) or acknowledge that it produces nested output directories. Similarly, reviewing the flux-drive SKILL.md itself is a valid use case that creates a recursive loop risk — the spec should acknowledge this.

**IMP-5: Expand Integration section**
Add: (1) SessionStart hook dependency for Oracle detection, (2) qmd and Context7 MCP server dependencies, (3) using-clavain routing table entry, (4) conflict relationship with disabled code-review plugin, (5) the fact that Phase 3.4's research agents are outside the 8-agent cap.

### Overall Assessment

Flux-drive is architecturally sound in its phase decomposition and tiered agent model. The core design — static triage, parallel background execution, YAML-first synthesis, optional cross-AI escalation — is well-conceived and matches the Clavain plugin's infrastructure correctly. The two areas requiring changes before this spec is production-ready are: (1) the roster gap that makes 8 of 20 review agents permanently invisible to triage, and (2) the Oracle format asymmetry that creates fragility in Phase 4's comparison and escalation chain. Both are fixable without restructuring the phases.
