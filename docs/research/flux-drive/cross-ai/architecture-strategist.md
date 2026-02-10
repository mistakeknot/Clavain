---
agent: architecture-strategist
tier: adaptive
scope: Phase 4 cross-ai.md rewrite (Clavain-ne6)
issues:
  - id: P1-1
    severity: P1
    section: "Phase Boundary"
    title: "Phase 4 reads synthesized findings from Step 3.2 but individual agent perspectives are needed for meaningful cross-AI comparison"
  - id: P1-2
    severity: P1
    section: "Interpeer Coupling"
    title: "Auto-chain to interpeer mine/council modes bypasses interpeer's own prompt-optimization pipeline and consent model"
  - id: P1-3
    severity: P1
    section: "State Dependency"
    title: "Step 4.2 depends on oracle-council.md existing with parseable findings, but Oracle fails frequently (timeout exit 124 observed in self-review)"
  - id: P2-1
    severity: P2
    section: "Escalation Complexity"
    title: "Steps 4.3-4.5 create a 3-stage escalation ladder (mine -> council offer -> final summary) that is unlikely to be traversed in practice"
  - id: P2-2
    severity: P2
    section: "Classification Model"
    title: "The 4-way classification (Agreement/Oracle-only/Claude-only/Disagreement) conflates findings-level comparison with model-level attribution"
improvements:
  - id: IMP-1
    title: "Decouple Phase 4 from interpeer by making escalation a user-initiated action, not an automatic chain"
    section: "Interpeer Coupling"
  - id: IMP-2
    title: "Add SKILL.md skip gate so the phase file is never even read when Oracle was absent from the roster"
    section: "Phase Boundary"
  - id: IMP-3
    title: "Simplify to 2 steps: classify + present (with optional escalation as a single AskUserQuestion)"
    section: "Escalation Complexity"
verdict: needs-changes
---

# Architecture Review: Phase 4 Cross-AI Escalation

**Reviewed file:** `/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` (97 lines)
**Supporting context:** `/root/projects/Clavain/skills/flux-drive/SKILL.md`, `/root/projects/Clavain/skills/interpeer/SKILL.md`
**Bead:** Clavain-ne6 (rewrite to ~30-40 lines with consent gate)

---

## 1. Architecture Overview

The flux-drive skill implements a 4-phase document review pipeline:

- **Phase 1** (SKILL.md): Analyze input, profile document, triage agents from a static roster, get user approval.
- **Phase 2** (`phases/launch.md`): Dispatch approved agents in parallel via Task tool or Codex CLI. Oracle runs as a background Bash command. Verify completion with retry.
- **Phase 3** (`phases/synthesize.md`): Validate agent outputs (YAML frontmatter), collect and deduplicate findings, update the source document, report to user.
- **Phase 4** (`phases/cross-ai.md`): Compare Oracle findings against Claude agent findings, classify divergences, optionally chain into the interpeer skill for resolution.

Phase 4 is the only phase that chains to another skill (interpeer). It is also the only phase marked "(Optional)" in SKILL.md. The interpeer skill is itself a multi-mode system (quick, deep, council, mine) with its own consent model, prompt-optimization pipeline, and error handling.

### Key Architectural Contracts

| Contract | Source | Consumer |
|----------|--------|----------|
| Agent output files in `{OUTPUT_DIR}/` | Phase 2 | Phase 3, Phase 4 |
| YAML frontmatter with issues/verdict | Phase 2 prompt template | Phase 3 Step 3.1 |
| `oracle-council.md` output file | Phase 2 (Bash background) | Phase 4 Step 4.2 |
| Synthesized findings from Step 3.2 | Phase 3 | Phase 4 Step 4.2 |
| interpeer mine mode input contract | interpeer SKILL.md | Phase 4 Step 4.3 |

---

## 2. Change Assessment

The planned rewrite (Clavain-ne6) targets the right problems. The current Phase 4 is 97 lines with a 5-step escalation ladder that auto-chains into interpeer mine mode and offers interpeer council mode. The rewrite to ~30-40 lines with a consent gate is architecturally sound. Below is a detailed assessment of each dimension.

### 2.1 Phase Boundary: Phase 4 vs Phase 3

**Current state:** Phase 4 depends on Phase 3 in two ways:

1. **Synthesized findings from Step 3.2** -- Phase 4 Step 4.2 says "Compare Oracle's findings with the synthesized findings from Step 3.2." But Step 3.3 actively deduplicates and merges individual agent findings, destroying per-agent attribution. When Phase 4 compares "Claude agents" against Oracle, it is actually comparing a merged composite against one model's raw output. This is an apples-to-oranges comparison.

2. **Oracle output file** -- Oracle is launched in Phase 2 alongside other agents, and its output file (`oracle-council.md`) is available from Phase 2 onward. Phase 3 does not process Oracle output (it handles only YAML-frontmatter agents). Phase 4 is the sole consumer of `oracle-council.md`.

**Assessment:** The phase boundary is clean in one direction (Phase 4 reads but does not write back to Phase 3 artifacts) but the data dependency on "synthesized findings" is problematic. The rewrite should compare Oracle findings against individual agent outputs, not the merged synthesis. This preserves attribution and makes the Agreement/Oracle-only/Claude-only/Disagreement classification meaningful.

**Recommendation for the rewrite:** Step 4.2 should read individual agent output files from `{OUTPUT_DIR}/` directly, not rely on the synthesized output from Step 3.2. The frontmatter `issues` arrays provide structured per-agent findings that are directly comparable to Oracle's output.

### 2.2 Coupling to Interpeer

**Current state:** Phase 4 couples to interpeer in three places:

| Step | Coupling | Mode | Trigger | Consent |
|------|----------|------|---------|---------|
| 4.1 | Suggestion only | quick | Oracle absent | User must invoke manually |
| 4.3 | Auto-chain (inline) | mine | Any disagreements found | None -- executes immediately |
| 4.4 | Offer with options | council | P0/P1 critical decisions | AskUserQuestion (3 options) |

The auto-chain in Step 4.3 is the primary architectural violation. It invokes interpeer mine mode inline without user consent and without going through interpeer's own prompt-optimization pipeline. The interpeer SKILL.md explicitly states:

> "Every Oracle CLI invocation MUST go through deep mode's prompt-optimization pipeline"

And mine mode's prerequisites section says:

> "If prior Oracle/GPT output exists in context -> proceed directly."

This means mine mode expects structured model perspectives as input. But what Phase 4 actually provides is:
- Oracle's raw output (not structured per interpeer's format)
- A synthesized summary (per-agent attribution destroyed)

This is the contract mismatch identified in the prior self-review as P1-3 (`architecture-strategist.md`).

**Assessment:** The auto-chain creates tight coupling between flux-drive and interpeer. If interpeer's mine mode input contract changes, Phase 4 breaks. If interpeer adds new prerequisite checks, Phase 4 bypasses them. The auto-chain also violates the user's expectation of control -- flux-drive launches agents with explicit consent (Step 1.3 AskUserQuestion) but then chains to a different skill without asking.

**Recommendation for the rewrite:** Replace all three interpeer coupling points with a single AskUserQuestion that presents the classification results and offers escalation as options. The user can then invoke interpeer themselves if desired. This is the consent gate from the Clavain-ne6 acceptance criteria.

### 2.3 Error Handling: Oracle Failure Mid-Escalation

**Current state:** SKILL.md has solid error handling for Oracle launch:

```
|| echo "Oracle failed (exit $?) -- continuing without cross-AI perspective"
>> {OUTPUT_DIR}/oracle-council.md
```

And explicit guidance:

> "If the Oracle command fails or times out, note it in the output file and continue without Phase 4."

However, Phase 4 itself has no error handling. If Oracle's output file exists but contains only the failure notice ("Oracle failed (exit 124)"), Step 4.2 would attempt to "Compare Oracle's findings" against an error message. The classification table would produce nonsensical results.

**Evidence this happens in practice:** The flux-drive self-review produced exactly this scenario. The `oracle-council.md` file at `/root/projects/Clavain/docs/research/flux-drive/flux-drive-self-review/oracle-council.md` contains only:

```
Oracle failed (exit 124) -- continuing without cross-AI perspective
```

This 1-line failure file passed Phase 2 verification (file exists) and Phase 3 validation (not a YAML-frontmatter agent, so not validated). Phase 4 would attempt to process it.

**Assessment:** There is a gap between the skip condition ("continue without Phase 4") documented in SKILL.md and the actual Phase 4 file which has no guard clause. The orchestrator must remember to skip Phase 4 based on a condition stated 20+ lines above the "Read phases/cross-ai.md" instruction.

**Recommendation for the rewrite:** Two defenses:

1. **SKILL.md skip gate** (from Clavain-ne6 acceptance criteria): Before the "Read phases/cross-ai.md" instruction, add an explicit condition: "If Oracle was not in the roster OR oracle-council.md contains a failure notice, skip Phase 4 entirely."

2. **Phase 4 guard clause**: The first line of the rewritten cross-ai.md should validate that oracle-council.md exists and contains actual findings (not just the error fallback line). If validation fails, output a brief "Oracle did not produce findings -- skipping cross-AI comparison" and stop.

### 2.4 State Dependencies

Phase 4 depends on the following state. Each has a failure mode:

| State | Source | Failure Mode |
|-------|--------|-------------|
| `{OUTPUT_DIR}/oracle-council.md` | Phase 2 Bash | File missing, empty, or contains only error message |
| Individual agent output files | Phase 2 Task/Codex | Files may have `verdict: error` (stub), may be malformed |
| Synthesized findings "from Step 3.2" | Phase 3 orchestrator memory | Not a file -- exists only in the LLM's context window. May be truncated or lost in long sessions |
| Oracle participation flag | Phase 1 triage | Tracked only as a row in the triage table -- no persistent state |
| Agent names for attribution | Phase 1 triage table | Orchestrator must remember which agents ran to attribute findings |

The most fragile dependency is the synthesized findings from Step 3.2. This is not written to a file; it exists only in the orchestrator's conversation context. In a long flux-drive session (especially with 8 agents), the context window may be approaching capacity by Phase 4. The synthesized findings could be compressed or truncated by the model.

**Recommendation for the rewrite:** Do not depend on in-context synthesis output. Instead, either (a) read the `summary.md` or inline annotations that Phase 3 writes to disk, or (b) read individual agent output files directly. Both are persistent and available regardless of context window pressure.

### 2.5 Simplification Opportunities

The current 97 lines break down as:

| Section | Lines | Value | Keep? |
|---------|-------|-------|-------|
| Step 4.1: Detect Oracle participation | 8 | Gate + lightweight suggestion | Yes, simplify |
| Step 4.2: Compare model perspectives | 12 | Cross-AI classification table | Yes, core value |
| Step 4.3: Auto-chain to mine mode | 18 | Inline interpeer invocation | **Remove** |
| Step 4.4: Council offer | 16 | Conditional escalation prompt | **Replace with unified consent gate** |
| Step 4.5: Final cross-AI summary | 22 | Output template | Simplify to inline in step 4.2 |

**What can be removed without losing value:**

1. **Steps 4.3-4.5 auto-chain and sequential decision prompts** -- These implement a 3-stage escalation ladder (mine -> council offer -> summary) that is over-engineered. In practice, most flux-drive runs either (a) have no Oracle at all, or (b) have Oracle findings that mostly agree with Claude agents. The disagreement-heavy case that triggers mine mode is the exception, not the rule. A single AskUserQuestion with all options is sufficient.

2. **The mine mode inline invocation** -- Mine mode's structured extraction (The Conflict, Evidence, Resolution, Minority Report) duplicates work that the user can do by invoking interpeer directly. Embedding mine mode logic in cross-ai.md creates a maintenance burden: any change to mine mode's format must be reflected in two places.

3. **The conditional council check** -- Step 4.4's P0/P1 detection logic ("any finding represents a critical architectural or security decision") duplicates the severity classification already done in Phase 3. The user has already seen the severity-ranked findings in Step 3.5's report.

4. **The detailed output template in Step 4.5** -- The 22-line markdown template for cross-AI summary can be folded into the classification table output from Step 4.2.

**What must be preserved:**

1. **The 4-way classification model** -- Agreement/Oracle-only/Claude-only/Disagreement is the core intellectual contribution of Phase 4. Without it, Phase 4 is just "here are Oracle's findings." The classification gives the user actionable signal about blind spots and confidence levels.

2. **The lightweight interpeer suggestion** -- When Oracle is absent, offering quick mode is valuable but must include a 1-sentence description (Clavain-c6m acceptance criteria).

3. **User consent before escalation** -- The AskUserQuestion gate is the architectural fix for the auto-chain problem.

---

## 3. Compliance Check

### SOLID Principles

| Principle | Current | Rewrite Target | Assessment |
|-----------|---------|----------------|------------|
| **Single Responsibility** | Phase 4 does classification AND interpeer orchestration | Classification only, with escalation as user choice | Rewrite improves SRP |
| **Open/Closed** | Adding a new interpeer mode requires modifying cross-ai.md | Decoupled -- interpeer modes are listed as options, not embedded | Rewrite improves O/C |
| **Dependency Inversion** | Phase 4 depends on concrete interpeer mine/council implementations | Phase 4 depends on interpeer as an abstract escalation option | Rewrite improves DIP |

### Architectural Principles

| Principle | Status |
|-----------|--------|
| Phase decoupling | Phase 4 reads Phase 2 artifacts (files) -- clean. Depends on Phase 3 in-context state -- fragile. Rewrite should use files only. |
| User consent model | Violated by auto-chain. Rewrite fixes this. |
| Skill boundaries | Violated by embedding mine mode logic. Rewrite fixes this. |
| Error handling | Missing for Oracle failure case. Rewrite must add guard clause. |
| Progressive loading | Respected -- Phase 4 file is read on demand. Skip gate improves this further. |

---

## 4. Risk Analysis

### Risks in the Current Design (motivating the rewrite)

1. **Auto-chain surprise** (High) -- Users who approved N agents for review suddenly find themselves in an interpeer mine session they did not request. This violates the principle of least surprise.

2. **Oracle failure cascade** (Medium) -- Oracle times out frequently (observed in self-review). When it does, the error-only output file can flow into Phase 4 and produce nonsensical classification results.

3. **Context window exhaustion** (Medium) -- By Phase 4, the orchestrator has consumed context on: document profile, triage table, 8 agent prompts, 8 agent outputs, synthesis, and the user conversation. Adding mine mode and council mode inline risks hitting context limits on long documents.

4. **Maintenance coupling** (Low-Medium) -- Any change to interpeer's mine or council mode format requires coordinated changes in cross-ai.md.

### Risks in the Proposed Rewrite

1. **Under-specification of Oracle output parsing** (Medium) -- The rewrite must specify how to extract findings from `oracle-council.md`, which is not YAML-frontmatter formatted. Oracle output is free-form prose from GPT-5.2 Pro. The classification step requires parsing this into comparable findings. If not specified, the orchestrator will improvise, producing inconsistent results.

2. **Loss of artifact generation** (Low) -- Steps 4.3's mine mode produces concrete artifacts (tests, spec clarifications, stakeholder questions). Removing the auto-chain means these artifacts are only generated if the user explicitly invokes interpeer. This is an acceptable tradeoff: the artifacts were only produced for the disagreement case, which is uncommon.

3. **Skip gate granularity** (Low) -- The proposed SKILL.md skip gate ("If Oracle not in roster, skip") means users who want interpeer quick mode (offered in current Step 4.1 for Oracle-absent runs) lose that suggestion. The rewrite should either move the quick mode suggestion to the Phase 3 report, or make the skip gate conditional: skip the file read only, but still output the quick mode suggestion.

---

## 5. Recommendations

### For the Clavain-ne6 Rewrite

**R1: Restructure to 2 steps, targeting ~35 lines.**

```
Step 4.1: Validate Oracle Output
  - Guard clause: if oracle-council.md missing or contains failure notice, skip
  - Parse Oracle findings into a comparable list

Step 4.2: Classify + Present
  - Read individual agent output files (not synthesized findings)
  - Classify into Agreement/Oracle-only/Claude-only/Disagreement
  - Present table with counts and top findings per category
  - AskUserQuestion with escalation options
```

**R2: Use individual agent files, not synthesis, for comparison.**

Replace the current "Compare Oracle's findings with the synthesized findings from Step 3.2" with "Compare Oracle's findings with individual agent output files from `{OUTPUT_DIR}/`." This preserves per-agent attribution and avoids the in-context state dependency.

**R3: Single AskUserQuestion with context-rich options.**

```
AskUserQuestion:
  question: "Cross-AI review complete. D disagreements found. Escalate?"
  options:
    - label: "Continue"
      description: "Accept findings as-is"
    - label: "interpeer mine"
      description: "Extract disagreements into tests and spec clarifications (~5 min)"
    - label: "interpeer council"
      description: "Full multi-model consensus on critical findings (~10 min, uses Oracle)"
```

This replaces three sequential decision points (Steps 4.3, 4.4, 4.5) with one. All options are visible at once. The descriptions give users enough context to choose without reading interpeer documentation.

**R4: Add the SKILL.md skip gate with quick mode fallback.**

In SKILL.md, before the "Read phases/cross-ai.md" instruction:

```
If Oracle was NOT in the roster:
  - Output: "No cross-AI perspective. For a second opinion, try /clavain:interpeer —
    quick Claude-vs-Codex review on specific findings (~30 seconds)."
  - Skip Phase 4 entirely (do not read cross-ai.md).
```

This satisfies Clavain-f0m (skip gate) and Clavain-c6m (1-sentence description) while avoiding the unnecessary file read.

**R5: Add a guard clause as the first line of cross-ai.md.**

Even with the SKILL.md skip gate, the phase file should be self-defending:

```
Before proceeding: Verify {OUTPUT_DIR}/oracle-council.md exists and contains
findings (not just an error message). If Oracle failed, report "Oracle did not
produce findings" and stop. Do not attempt classification with error output.
```

**R6: Specify Oracle output parsing strategy.**

Oracle output is free-form prose, not YAML frontmatter. The rewrite must tell the orchestrator how to extract comparable findings. Recommendation: "Read oracle-council.md. Extract numbered findings with their severity. If Oracle did not use numbered findings, extract the top 5 concerns. Map each to the closest section from the document profile."

### For SKILL.md Integration Section

The current Integration section at the bottom of SKILL.md should be updated to reflect the decoupled relationship:

```
Chains to (user-initiated, after Phase 4 consent gate):
- interpeer mine -- when user wants disagreement extraction
- interpeer council -- when user wants multi-model consensus

Suggests (when Oracle absent):
- interpeer quick -- lightweight Claude-vs-Codex second opinion
```

This accurately describes the new relationship: flux-drive classifies and presents, the user decides whether to escalate, and interpeer handles escalation independently.

---

## 6. Proposed Rewrite Structure (Reference)

Based on the above analysis, the rewritten `cross-ai.md` should follow this structure (approximately 35 lines):

```
# Phase 4: Cross-AI Escalation (Optional)

### Step 4.1: Validate Oracle Output
[Guard clause -- 5 lines]
[Parse Oracle findings -- 3 lines]

### Step 4.2: Classify and Present
[Read individual agent files, compare -- 5 lines]
[Classification table definition -- 8 lines]
[Present summary with counts and top findings -- 5 lines]
[AskUserQuestion consent gate -- 10 lines]
```

This removes 60+ lines of auto-chain logic, sequential decision prompts, and the detailed output template while preserving the core value: the 4-way classification and user-controlled escalation.
