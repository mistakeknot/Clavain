---
agent: fd-code-quality
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Phase 2 Prompt Template"
    title: "YAML frontmatter delimiters (---) inside code block are ambiguous and cause agent parse confusion"
  - id: P0-2
    severity: P0
    section: "SKILL.md Size"
    title: "3,720 words exceeds AGENTS.md convention limit of 1,500-2,000 words by 86%"
  - id: P1-1
    severity: P1
    section: "Phase 3 Step Numbering"
    title: "Phase 4 starts at Step 4.1 (missing 4.0) while Phases 1-3 all start at X.0"
  - id: P1-2
    severity: P1
    section: "Phase 2 Prompt Template"
    title: "Token optimization instruction is ambiguous about WHO does the trimming (orchestrator vs agent)"
  - id: P1-3
    severity: P1
    section: "Phase 3 Step 3.4"
    title: "Task Explore is an undocumented subagent_type — only appears in one other file (agent-native-audit.md)"
  - id: P1-4
    severity: P1
    section: "Phase 2 Prompt Template"
    title: "Prompt template omits Tier 2 agents from tier field — YAML example shows {1|2|3} but no Tier 4"
  - id: P2-1
    severity: P2
    section: "Phase Naming"
    title: "flux-drive uses Step X.Y numbering while peer skills (winterpeer, splinterpeer) use Phase N naming"
  - id: P2-2
    severity: P2
    section: "Agent Roster"
    title: "Oracle agent output filename oracle-council.md inconsistent with kebab-case agent naming"
improvements:
  - id: IMP-1
    title: "Extract prompt template and Agent Roster into sub-files to bring SKILL.md under word limit"
    section: "Overall Structure"
  - id: IMP-2
    title: "Add explicit guidance for when agents return empty issues list vs no file at all"
    section: "Phase 3 Step 3.1"
  - id: IMP-3
    title: "Frontmatter template should include an empty-list example for issues/improvements"
    section: "Phase 2 Prompt Template"
  - id: IMP-4
    title: "Step 1.2 scoring examples show security-sentinel scored as 0 due to dedup but text says score 0 means irrelevant"
    section: "Phase 1 Scoring Examples"
verdict: needs-changes
---

### Summary

The flux-drive SKILL.md is a well-structured multi-agent orchestration spec with clear phase progression, concrete scoring examples, and robust error handling for agent output validation. However, it has two blocking issues: (1) the YAML frontmatter delimiters inside the prompt template code block are syntactically ambiguous and have caused real parse failures in agent output, and (2) at 3,720 words it exceeds the project's own 1,500-2,000 word convention by 86%, making it a prime candidate for sub-file extraction. The step numbering inconsistency (Phase 4 missing Step 4.0) and ambiguous token-optimization ownership in the prompt template are secondary but worth fixing.

### Section-by-Section Review

#### Phase 2: Prompt Template (Lines 253-349) -- DEEP REVIEW

**1. YAML Frontmatter Delimiter Ambiguity (P0-1)**

Lines 312-329 contain a YAML frontmatter example with `---` delimiters. This block sits inside a larger code fence (lines 255-349, opened with triple backticks). The structural issue: when the orchestrating Claude constructs the agent prompt, it copies this template. The resulting prompt contains bare `---` lines that agents must interpret as "start your output file with this format." But `---` is also a markdown horizontal rule and a YAML document separator. Multiple prior flux-drive runs (visible in `/root/projects/Clavain/docs/research/flux-drive/Clavain-v2/`) show agents successfully parsing this, but the ambiguity is a latent failure mode.

The fix: wrap the YAML example in its own inner code fence (e.g., triple-backtick yaml) within the prompt template, or add explicit prose like "Start your output file with exactly these three dashes on a line by themselves."

**2. Token Optimization Ownership Ambiguity (P1-2)**

Lines 275-282 contain the "Token Optimization" instruction block:

```
IMPORTANT -- Token Optimization:
For file inputs with 200+ lines, you MUST trim the document before including it:
1. Keep FULL content for sections listed in "Focus on" below
...
Target: Agent should receive ~50% of the original document, not 100%.
```

This instruction appears inside the prompt template that the orchestrator assembles and sends to agents. But the trimming must happen BEFORE the prompt is sent -- it is the orchestrator's job, not the agent's. The instruction reads as if the agent should trim, but the agent receives a pre-assembled prompt and cannot retroactively trim it.

Lines 299-302 ("When constructing the prompt, explicitly list which sections to include in full and which to summarize") clarify that this is orchestrator-directed, but the surrounding context inside the code block is confusing. The Token Optimization block should either be moved outside the code fence (as orchestrator instructions) or reworded to make clear it is a reminder to the orchestrator, not a directive to the agent.

**3. Tier Field Completeness (P1-4)**

Line 314 shows `tier: {1|2|3}` in the YAML template, but the Agent Roster defines four tiers (Tier 1-4). Oracle (Tier 4) outputs to a separate file via Bash, not through the Task tool, so it never writes frontmatter. This is logically correct but undocumented -- a comment or note explaining why Tier 4 is absent from the template would prevent confusion during synthesis (Step 3.1) when the validator encounters an Oracle output file without frontmatter.

**4. Code Fence Language Specifier**

Line 255 opens the prompt template with bare triple backticks (no language hint). Within the template, the YAML frontmatter example (lines 312-329) also lacks a language specifier. Using ` ```yaml ` for the inner block and ` ```markdown ` for the outer block would improve parsing reliability in editors and when agents consume the prompt.

#### Phase 3: Step Numbering (Lines 358-483) -- DEEP REVIEW

**5. Step 4.0 Missing (P1-1)**

Phase 1 starts at Step 1.0 (line 37), Phase 2 at Step 2.0 (line 220), Phase 3 at Step 3.0 (line 360). Phase 4 starts at Step 4.1 (line 490). This breaks the established pattern. The step numbering convention in flux-drive uses X.0 as a "preparation/gate" step:
- Step 1.0: Understand the Project (prep before analysis)
- Step 2.0: Prepare output directory (prep before launch)
- Step 3.0: Wait for all agents (prep before synthesis)

Phase 4 has an implicit gate at Step 4.1 ("Detect Oracle Participation") that functions as a prep/gate step. It should be renumbered to Step 4.0, with subsequent steps shifting to 4.1-4.4.

**6. Step 3.3 vs Step 3.4 Boundary**

Step 3.3 is titled "Deduplicate and Organize" (line 392) and Step 3.4 is "Update the Document" (line 400). Step 3.4 contains three sub-sections:
- For file inputs (lines 404-434)
- Deepen thin sections (lines 436-466)
- For repo reviews (lines 468-474)

The "Deepen thin sections" sub-section (lines 436-466) launches additional `Task Explore` agents and Context7 MCP calls. This is a significant operation -- closer in scope to a separate step than a sub-section of "Update the Document." Consider promoting it to Step 3.5 and renumbering current Step 3.5 (Report to User) to Step 3.6.

**7. Task Explore Subagent Type (P1-3)**

Line 440 references launching a `Task Explore` agent. The only other occurrence of this pattern is in `/root/projects/Clavain/commands/agent-native-audit.md` (line 36: `subagent_type: Explore`). Neither `AGENTS.md` nor the routing table in `using-clavain/SKILL.md` document `Explore` as a valid subagent type. If it is a built-in Claude Code subagent type, it should be documented. If it is not, the step will fail silently.

#### Phase 1: Triage Scoring (Summary Review)

**8. Scoring Example Ambiguity (IMP-4)**

Line 118 shows:
```
security-sentinel: 0 (T1 fd-security covers this -> deduplicated)
```

The scoring rubric (lines 96-98) defines score 0 as "irrelevant: Wrong language, wrong domain, no relationship to this document." But security-sentinel's score of 0 is not because it is irrelevant -- it is because deduplication drops it. The score should be 2 (relevant) with a note "deduplicated by fd-security." Using 0 conflates two different concepts: "not relevant" vs "relevant but redundant."

**9. Calibration Example Coverage**

The two scoring examples (lines 113-130) cover a Go API plan and a Python CLI README. There is no example for a repo-level review (directory input), which is a substantially different workflow. Adding a third example for repo reviews would reduce ambiguity about how to score agents when there is no specific document to section-analyze.

#### Agent Roster (Summary Review)

**10. Oracle Output Naming (P2-2)**

The Oracle agent output is written to `{OUTPUT_DIR}/oracle-council.md` (line 209, 251, 505). All other agents write to `{OUTPUT_DIR}/{agent-name}.md` where `{agent-name}` matches the kebab-case name from the roster table. The Oracle's table entry (line 203) uses the name `oracle-council`, which is consistent. However, "oracle-council" is a compound name that does not follow the `fd-*` prefix pattern for codebase-aware agents or the single-concept pattern for Tier 3 agents. This is a minor naming inconsistency, justified by Oracle's unique invocation mechanism.

#### Overall Structure

**11. Word Count Violation (P0-2)**

At 3,720 words, this SKILL.md is 86% over the 1,500-2,000 word limit stated in AGENTS.md line 96. For comparison:
- `interpeer/SKILL.md`: 882 words
- `winterpeer/SKILL.md`: 1,758 words
- `splinterpeer/SKILL.md`: 2,094 words

The main bloat sources:
- Agent Roster (lines 156-215): ~450 words -- could be a sub-file `roster.md`
- Prompt Template (lines 253-349): ~650 words -- could be a sub-file `prompt-template.md`
- Phase 4 (lines 486-601): ~800 words -- could be a sub-file `phase-4-cross-ai.md`

Extracting these three sections into sub-files would bring the main SKILL.md to approximately 1,800 words, within convention. The main file would reference them as: "See `roster.md` for the full agent roster" with inline `Read` instructions.

**12. Phase Naming Convention (P2-1)**

flux-drive uses `## Phase N` for top-level sections and `### Step N.M` for sub-steps. Peer skills use `### Phase N` for top-level sections (winterpeer, splinterpeer) and numbered sub-steps within prose. The `## Phase` / `### Step X.Y` pattern is more structured and actually clearer -- but it is unique to flux-drive within the peer skill family. This is a style difference, not a defect, but worth noting for consistency if the peer skills are ever harmonized.

### Issues Found

**P0-1: YAML frontmatter delimiters in prompt template are ambiguous** (Lines 312-329)

The `---` delimiters sit inside a code block but will be copied verbatim into agent prompts. Agents must distinguish "this is the YAML format I should output" from markdown horizontal rules or YAML document separators. The ambiguity has not caused failures in observed runs but is a latent reliability risk. Fix: add explicit prose instructions and/or wrap the YAML example in a nested code fence with `yaml` language hint.

**P0-2: SKILL.md at 3,720 words is 86% over convention limit** (Entire file)

AGENTS.md line 96 states: "Keep SKILL.md lean (1,500-2,000 words) -- move detailed content to sub-files." At 600 lines / 3,720 words, this is the longest skill in the project and nearly double the upper bound. The file has clear extraction candidates (Agent Roster, Prompt Template, Phase 4) that would bring it within limits while improving maintainability.

**P1-1: Phase 4 step numbering inconsistency** (Line 490)

Phases 1-3 all begin with Step X.0 as a preparation/gate step. Phase 4 begins at Step 4.1, breaking the pattern. Renumber Step 4.1 to Step 4.0 and shift subsequent steps.

**P1-2: Token optimization instruction ambiguously addressed** (Lines 275-282)

The "Token Optimization" block is inside the agent prompt template but describes work the orchestrator must do before sending the prompt. The audience (orchestrator vs agent) is unclear.

**P1-3: Task Explore is an undocumented subagent type** (Line 440)

Step 3.4 instructs launching a `Task Explore` agent, but this subagent type is not documented in AGENTS.md or the routing table. Only one other file references it (`agent-native-audit.md`). If the type does not exist at runtime, the step fails silently with no fallback specified.

**P1-4: Tier 4 absence from frontmatter template is undocumented** (Line 314)

The YAML template shows `tier: {1|2|3}` without explaining why Tier 4 (Oracle) is excluded. The Oracle output file has a different format entirely (raw prose from GPT), so Step 3.1's validation will classify it as "malformed" and fall back to prose reading. This is the correct behavior but should be documented explicitly rather than relying on the fallback path.

**P2-1: Phase naming convention differs from peer skills** (Throughout)

flux-drive uses `## Phase / ### Step X.Y` while winterpeer and splinterpeer use `### Phase N`. Not a defect but a consistency note.

**P2-2: oracle-council naming does not follow roster patterns** (Line 203)

Minor naming inconsistency. The compound name is justified by Oracle's unique invocation but worth noting.

### Improvements Suggested

**IMP-1: Extract three sections into sub-files**

Move the Agent Roster (~450 words), Prompt Template (~650 words), and Phase 4 (~800 words) into `skills/flux-drive/roster.md`, `skills/flux-drive/prompt-template.md`, and `skills/flux-drive/phase-4-cross-ai.md` respectively. Reference them from the main SKILL.md with `Read` instructions. This brings the main file to ~1,800 words, within the AGENTS.md convention. This also follows the pattern established by `writing-skills/SKILL.md` which uses sub-resources extensively.

**IMP-2: Document Oracle output handling in Step 3.1**

Add a note in Step 3.1 (Validate Agent Output) explicitly stating: "Oracle (Tier 4) output is raw GPT prose without YAML frontmatter. Classify it as 'malformed' and use the prose fallback path. This is expected behavior, not an error."

**IMP-3: Add empty-list YAML example to frontmatter template**

The YAML template only shows populated `issues` and `improvements` lists. Agents reviewing well-written documents may find no issues. Add an example showing:
```yaml
issues: []
improvements: []
verdict: safe
```
This prevents agents from inventing issues to fill the template.

**IMP-4: Clarify deduplication vs irrelevance in scoring examples**

Change the security-sentinel scoring example (line 118) from `0 (T1 fd-security covers this -> deduplicated)` to `2 (relevant, but deduplicated by fd-security -> skip)` to avoid conflating "irrelevant domain" with "redundant coverage."

### Overall Assessment

The flux-drive SKILL.md is a sophisticated multi-agent orchestration spec that demonstrates strong engineering discipline: explicit step ordering, concrete scoring calibration, structured output formats, and robust fallback paths. The two P0 issues (YAML ambiguity and word count) are both fixable without changing the spec's logic -- the YAML issue needs a clarity pass on the prompt template, and the word count needs sub-file extraction. The P1 step numbering and token optimization issues are worth fixing for consistency and clarity. The spec is well-designed; it needs editorial tightening, not architectural changes.
