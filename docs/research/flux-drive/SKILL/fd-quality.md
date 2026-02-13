### Findings Index
- P0 | P0-1 | "SKILL.md" | 546-line SKILL.md violates plugin convention (should be under 100 lines with references)
- P0 | P0-2 | "Findings Index Format" | Findings Index format defined in 3 separate places without single source of truth
- P1 | P1-1 | "Phase File Loading" | Progressive loading instructions contradicted by cross-phase references
- P1 | P1-2 | "Scoring Examples" | Domain boost calculation in examples uses ad-hoc bullet counting ("5 items", "4 items")
- P1 | P1-3 | "Terminology Inconsistency" | Inconsistent terms: "tiers" vs "stages", "launch" vs "dispatch", "document" vs "file" vs "input"
- P1 | P1-4 | "Output Directory Ambiguity" | OUTPUT_DIR resolution instructions scattered across 3 locations with conflicting guidance
- P1 | P1-5 | "Agent Roster Placement" | Agent roster appears mid-skill (line 450) instead of in reference file
- P2 | P2-1 | "Hardcoded Path Pattern" | Hardcoded plugin root pattern ${CLAUDE_PLUGIN_ROOT} appears 8 times
- IMP | IMP-1 | "SKILL.md" | Extract phases, scoring examples, and roster into references/ directory
- IMP | IMP-2 | "Findings Index Format" | Create single canonical format specification in shared-contracts.md
- IMP | IMP-3 | "Scoring Table" | Add score calculation formula to scoring table for clarity
- IMP | IMP-4 | "Terminology Guide" | Create glossary in references/ defining tier/stage/phase/launch/dispatch
- IMP | IMP-5 | "Path Resolution Helper" | Extract path derivation logic into reusable template or helper function
Verdict: needs-changes

### Summary (3-5 lines)

The flux-drive skill has serious structural quality issues. At 546 lines, it violates the plugin convention requiring skills under 100 lines with references. The Findings Index format is duplicated in 3 places (SKILL.md line 253-260, launch.md line 233-274, shared-contracts.md line 4-25) without a canonical source. Terminology is inconsistent throughout (tiers vs stages, launch vs dispatch). Progressive loading is undermined by cross-phase references that force reading all phases upfront. The scoring examples use ad-hoc bullet counting for domain boost instead of following a clear algorithm.

### Issues Found

#### P0-1: 546-line SKILL.md violates plugin convention (should be under 100 lines with references)

**Severity**: P0
**Location**: skills/flux-drive/SKILL.md (entire file, 546 lines)
**Context**: Plugin convention from domain context states "keep under 100 lines with references"

**Evidence**:
```
$ wc -l skills/flux-drive/SKILL.md
546 skills/flux-drive/SKILL.md
```

The skill is 5.4× the recommended maximum length. Content that should be in `references/` includes:

1. **Lines 329-385**: Four scoring examples (57 lines) — belongs in `references/scoring-examples.md`
2. **Lines 387-391**: Thin section thresholds (5 lines) — belongs in `references/triage-guide.md`
3. **Lines 450-508**: Agent roster (59 lines) — belongs in `references/agent-roster.md`
4. **Lines 1-506 in launch.md**: Launch phase instructions (429 lines) — this entire phase file is part of the skill's injected context
5. **Lines 1-98 in shared-contracts.md**: Shared contracts (98 lines) — also part of injected context

The skill loads phase files on-demand ("Read each phase file when you reach it"), but agents receive the full SKILL.md content immediately. The 546-line main file alone consumes excessive context tokens.

**Recommended fix**:
1. Move scoring examples to `references/scoring-examples.md`
2. Move agent roster to `references/agent-roster.md`
3. Move triage guide material to `references/triage-guide.md`
4. Reduce SKILL.md to core router logic (~80-100 lines): input detection, phase sequence, integration notes
5. Phase files can remain as-is (they're loaded on-demand)

**Impact**: High token consumption on every flux-drive invocation. Agents scan through 546 lines to find routing logic buried at line 43 (Phase 1).

---

#### P0-2: Findings Index format defined in 3 separate places without single source of truth

**Severity**: P0
**Location**:
- skills/flux-drive/SKILL.md lines 253-260 (in prompt template)
- skills/flux-drive/phases/launch.md lines 233-274 (in prompt template)
- skills/flux-drive/phases/shared-contracts.md lines 4-25 (contract definition)

**Evidence**:

**SKILL.md lines 253-260**:
```markdown
### Findings Index
- P0 | P0-1 | "Section Name" | Title of the issue
- P1 | P1-1 | "Section Name" | Title
- IMP | IMP-1 | "Section Name" | Title of improvement
Verdict: safe|needs-changes|risky
```

**launch.md lines 254-260** (identical):
```markdown
### Findings Index
- P0 | P0-1 | "Section Name" | Title of the issue
- P1 | P1-1 | "Section Name" | Title
- IMP | IMP-1 | "Section Name" | Title of improvement
Verdict: safe|needs-changes|risky
```

**shared-contracts.md lines 11-16**:
```markdown
### Findings Index
- SEVERITY | ID | "Section Name" | Title
- ...
Verdict: safe|needs-changes|risky
```

The shared-contracts.md version uses the placeholder `SEVERITY` instead of concrete severity levels (P0/P1/IMP). This creates ambiguity: should agents use P0/P1/P2/IMP (from SKILL.md), or SEVERITY (from shared-contracts)?

**DRY violation**: The format is copy-pasted into every agent prompt template. If the format changes (e.g., adding a confidence score column), it must be updated in 3 locations.

**Recommended fix**:
1. Define the canonical format ONCE in `shared-contracts.md`
2. SKILL.md and launch.md should reference it: "See phases/shared-contracts.md for Findings Index format"
3. shared-contracts.md should show the concrete format, not placeholders:
   ```markdown
   ### Findings Index
   - P0 | P0-1 | "Section Name" | Title of the issue
   - P1 | P1-1 | "Section Name" | Title
   - P2 | P2-1 | "Section Name" | Title
   - IMP | IMP-1 | "Section Name" | Title of improvement
   Verdict: safe|needs-changes|risky
   ```

**Impact**: Format inconsistencies across agent outputs. Synthesis parser must handle both `SEVERITY` and `P0` variants. Future format changes require coordinated 3-location updates.

---

#### P1-1: Progressive loading instructions contradicted by cross-phase references

**Severity**: P1
**Location**: skills/flux-drive/SKILL.md line 10, plus cross-references at lines 513-514, 519-520, 524

**Evidence**:

**Line 10** (progressive loading claim):
```markdown
**Progressive loading:** This skill is split across phase files. Read each phase file when you reach it — not before.
```

**Lines 512-514** (Phase 2 instruction):
```markdown
## Phase 2: Launch

**Read the launch phase file now:**
- Read `phases/launch.md` (in the flux-drive skill directory)
```

But agents need launch.md content BEFORE Phase 2:

1. **Line 209** (Phase 1, Step 1.1, Diff Profile) references `phases/launch.md` Step 2.1b:
   > "If `slicing_eligible: yes`, the orchestrator will apply diff slicing in Phase 2 using `config/flux-drive/diff-routing.md`. See `phases/launch.md` Step 2.1b."

2. **Lines 236-243** (Phase 1, Step 1.2a, pre-filter logic) references diff-routing.md patterns:
   > "For diff inputs (use `config/flux-drive/diff-routing.md` patterns)"

   The logic to understand diff routing patterns requires reading launch.md Step 2.1b (lines 180-230 in launch.md).

3. **Phase 1, Step 1.2** scoring depends on understanding Stage 1 vs Stage 2 assignment, which is defined in launch.md (Step 2.2, Step 2.2b).

**Contradiction**: Progressive loading promises deferred context (reducing token load), but cross-phase references force reading all phases upfront to execute Phase 1 correctly.

**Recommended fix**:

Either:
1. **Option A** (true progressive loading): Remove forward references. Phase 1 should be self-contained. Move diff routing logic summary into SKILL.md Phase 1 section.
2. **Option B** (acknowledge eagerness): Change line 10 to: "This skill is split across phase files for clarity. Read all phase files at skill start to understand cross-phase dependencies."

Option A is better for token efficiency. Option B is honest but defeats the purpose of splitting phases.

**Impact**: Agents waste tokens loading all phase files upfront, or risk missing critical cross-references if they follow the "read when you reach it" guidance.

---

#### P1-2: Domain boost calculation in examples uses ad-hoc bullet counting ("5 items", "4 items")

**Severity**: P1
**Location**: skills/flux-drive/SKILL.md lines 329-385 (scoring examples)

**Evidence**:

**Example 1** (lines 336-338):
```markdown
| fd-architecture | Plugin | 3 | +2 (5 web-api items) | +1 | 6 | 1 | Launch |
| fd-safety | Plugin | 3 | +1 (4 web-api items) | +1 | 5 | 1 | Launch |
```

**Example 2** (lines 350-352):
```markdown
| fd-user-product | Plugin | 3 | +2 (5 cli-tool items) | +1 | 6 | 1 | Launch |
| fd-quality | Plugin | 3 | +1 (5 cli-tool items) | +1 | 5 | 1 | Launch |
```

Examples show annotations like "+2 (5 web-api items)" and "+1 (4 web-api items)", implying the domain boost is calculated by counting bullets in the domain profile's injection criteria section.

But the algorithm defined at lines 271-274 says:
```markdown
**Domain boost** (+0, +1, or +2; applied only when base score ≥ 1): When Step 1.0.1 detected a project domain, check each agent's injection criteria in the corresponding domain profile (`config/flux-drive/domains/*.md`):
- Agent has injection criteria with ≥3 bullets for this domain → +2
- Agent has injection criteria (1-2 bullets) for this domain → +1
- Agent has no injection criteria for this domain → +0
```

**Problem**: The examples use specific bullet counts (4, 5) in annotations, but the algorithm only cares about thresholds: ≥3 bullets = +2, 1-2 bullets = +1. This creates confusion:

1. Why does fd-safety get +1 for "4 web-api items" when ≥3 should give +2?
2. Is the boost calculated by exact count (fragile — adding one bullet changes scores), or by threshold (stable)?

**Recommended fix**:

1. Use threshold annotations in examples: "+2 (≥3 web-api criteria)" instead of "+2 (5 web-api items)"
2. OR: Show the exact bullet count followed by threshold: "+2 (5 web-api criteria, ≥3 threshold)"
3. Add a note: "Bullet counts shown are from domain profile as of example creation. Use threshold logic (≥3 → +2, 1-2 → +1), not exact counts."

**Impact**: Orchestrators may implement bullet counting instead of threshold logic, making scores fragile to domain profile edits. Adding one bullet to a domain profile shouldn't change 10 agents' scores.

---

#### P1-3: Inconsistent terminology: "tiers" vs "stages", "launch" vs "dispatch", "document" vs "file" vs "input"

**Severity**: P1
**Location**: Throughout SKILL.md, launch.md, shared-contracts.md

**Evidence**:

**Tiers vs Stages**:
- Line 327 (SKILL.md): "present the triage table showing all agents, **tiers**, scores, **stages**"
- Line 319 (SKILL.md): "assign dispatch **stages**"
- launch.md title: "Phase 2: **Launch** (Task Dispatch)"
- Line 73 in launch.md: "**Stage 1** — Launch top agents"

The skill uses both "tier" and "stage" to refer to the same concept (Stage 1 vs Stage 2 dispatch grouping). "Tier" appears only once (line 327) but is inconsistent with the rest of the document.

**Launch vs Dispatch**:
- Line 1 in launch.md: "Phase 2: **Launch** (Task **Dispatch**)"
- Line 319 (SKILL.md): "assign **dispatch** stages"
- Line 432 (SKILL.md): "**Launch** Stage 1?"
- Line 73 (launch.md): "**Launch** top agents"
- Line 319 (SKILL.md): "**dispatch** stages"

"Launch" and "dispatch" are used interchangeably. The file is named `launch.md` but the subtitle says "Task Dispatch".

**Document vs File vs Input**:
- Line 8: "reviews any **document** (plan, brainstorm, spec, ADR, README) or an entire repository"
- Line 12: "The user provides a **file** or directory path"
- Line 19: "INPUT_PATH = <the path the user provided>"
- Line 23: "If `INPUT_PATH` is a **file**"
- Line 161: "For **file inputs**: Read the file"
- Line 283: "You are reviewing a **{document_type}**"

The skill conflates "document" (semantic artifact), "file" (filesystem entity), and "input" (user-provided argument). A directory input is not a "document" or "file", yet the instructions mix these terms.

**Recommended fix**:

1. **Standardize on**:
   - "Stage" (not tier) for dispatch grouping
   - "Launch" as the user-facing verb (keep dispatch as internal implementation detail)
   - "Input" for the user-provided path, "document" for file content, "repository" for directory content

2. Create `references/glossary.md`:
   ```markdown
   ## Terminology
   - **Input**: The path provided by the user (file, directory, or diff)
   - **Document**: A file's content when INPUT_TYPE is file or diff
   - **Repository**: The codebase when INPUT_TYPE is directory
   - **Stage**: Dispatch grouping (Stage 1 = top agents, Stage 2 = remaining agents)
   - **Launch**: User-facing term for agent dispatch
   - **Phase**: Sequential skill steps (Phase 1 = Analyze, Phase 2 = Launch, Phase 3 = Synthesize, Phase 4 = Cross-AI)
   ```

3. Replace "tier" with "stage" at line 327.

**Impact**: Agents receive mixed signals about terminology, leading to inconsistent usage in output (e.g., "Tier 1 findings" vs "Stage 1 findings").

---

#### P1-4: OUTPUT_DIR resolution instructions scattered across 3 locations with conflicting guidance

**Severity**: P1
**Location**:
- SKILL.md lines 28-33 (initial definition)
- SKILL.md lines 35-39 (run isolation + absolute path note)
- launch.md lines 5-15 (Phase 2 preparation)

**Evidence**:

**SKILL.md lines 28-33** (derivation logic):
```markdown
Derive:
```
INPUT_TYPE    = file | directory | diff
INPUT_STEM    = <filename without extension, or directory basename for repo reviews>
PROJECT_ROOT  = <nearest ancestor directory containing .git, or INPUT_DIR>
OUTPUT_DIR    = {PROJECT_ROOT}/docs/research/flux-drive/{INPUT_STEM}
```
```

**SKILL.md lines 35-39** (run isolation):
```markdown
**Run isolation:** Before launching agents, clean or verify the output directory:
- If `{OUTPUT_DIR}/` already exists and contains `.md` files, remove them to prevent stale results from contaminating this run.
- Alternatively, append a short timestamp to OUTPUT_DIR (e.g., `{INPUT_STEM}-20260209T1430`) to isolate runs. Use the simpler clean approach by default.

**Critical:** Resolve `OUTPUT_DIR` to an **absolute path** before using it in agent prompts. Agents inherit the main session's CWD, so relative paths write to the wrong project during cross-project reviews.
```

**launch.md lines 5-8** (Phase 2 re-states resolution):
```markdown
### Step 2.0: Prepare output directory

Create the research output directory before launching agents. Resolve to an absolute path:
```bash
mkdir -p {OUTPUT_DIR}  # Must be absolute, e.g. /root/projects/Foo/docs/research/flux-drive/my-doc-name
```
```

**Conflicts**:

1. SKILL.md says "resolve to absolute path" (line 39) but doesn't show HOW to resolve it (realpath? pwd + concat?).
2. launch.md re-states "resolve to absolute path" but still uses the placeholder `{OUTPUT_DIR}` instead of showing the resolution step.
3. Run isolation is described in SKILL.md (lines 35-38) but the cleanup command is in launch.md (lines 10-14).

**Recommended fix**:

1. **Define resolution ONCE** in SKILL.md after line 33:
   ```markdown
   Derive:
   INPUT_TYPE    = file | directory | diff
   INPUT_STEM    = <filename without extension, or directory basename for repo reviews>
   PROJECT_ROOT  = <nearest ancestor directory containing .git, or INPUT_DIR>
   OUTPUT_DIR    = {PROJECT_ROOT}/docs/research/flux-drive/{INPUT_STEM}

   Resolve OUTPUT_DIR to an absolute path:
   ```bash
   OUTPUT_DIR=$(realpath "${PROJECT_ROOT}/docs/research/flux-drive/${INPUT_STEM}")
   ```

   This prevents relative path bugs when reviewing cross-project files.
   ```

2. **Remove redundant notes** in launch.md — just reference SKILL.md: "Use OUTPUT_DIR from Phase 1 (already resolved to absolute path)."

3. **Move cleanup to launch.md** entirely (it's a Phase 2 action, not Phase 1).

**Impact**: Orchestrators may forget to resolve to absolute paths, causing agents to write output to wrong directories during cross-project reviews.

---

#### P1-5: Agent roster appears mid-skill (line 450) instead of in reference file

**Severity**: P1
**Location**: skills/flux-drive/SKILL.md lines 450-508

**Evidence**:

The agent roster consumes 59 lines (lines 450-508) and appears between Phase 1 and Phase 2 in SKILL.md. This placement:

1. Breaks the phase flow (reader must scan through roster to find Phase 2)
2. Makes the roster harder to update (buried in a 546-line file)
3. Violates the "keep under 100 lines with references" principle

The roster contains:
- Project Agents description (lines 452-459)
- Plugin Agents table (lines 461-473)
- Cross-AI section (lines 475-508)

**Recommended fix**:

Move the entire roster to `references/agent-roster.md`. In SKILL.md, replace lines 450-508 with:

```markdown
## Agent Roster

Flux-drive selects agents from a static roster. See `references/agent-roster.md` for the full roster and availability rules.

**Quick summary:**
- **Project Agents**: `.claude/agents/fd-*.md` files (if present)
- **Plugin Agents**: 7 core agents (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance, fd-game-design)
- **Cross-AI**: Oracle (GPT-5.2 Pro) when available
```

This reduces SKILL.md by 50+ lines while preserving discoverability.

**Impact**: Roster updates require editing a 546-line file. Extracting to a reference file improves maintainability.

---

#### P2-1: Hardcoded plugin root pattern ${CLAUDE_PLUGIN_ROOT} appears 8 times

**Severity**: P2
**Location**: Throughout SKILL.md

**Evidence**:

The pattern `${CLAUDE_PLUGIN_ROOT}` appears at:
- Line 77: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect-domains.py`
- Line 97: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect-domains.py`
- Line 115: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect-domains.py`
- Line 129: `${CLAUDE_PLUGIN_ROOT}/config/flux-drive/domains/{domain}.md`
- Line 56 (launch.md): `${CLAUDE_PLUGIN_ROOT}/scripts/detect-domains.py`

This is a template variable that agents must substitute. It's not a shell variable (no `$CLAUDE_PLUGIN_ROOT` in environment).

**Clarification needed**: How should agents resolve this variable?

1. **Option A**: It's a literal string to be replaced by the skill loader before injection
2. **Option B**: Agents should infer it from their own loaded skill path
3. **Option C**: It should be an actual environment variable set by the plugin system

Current instructions don't explain resolution. If agents copy-paste the commands, they'll fail with "command not found" because `${CLAUDE_PLUGIN_ROOT}` is not a valid shell variable.

**Recommended fix**:

1. Add a note at first use (line 77):
   ```markdown
   Run the domain detection script:
   ```bash
   # Note: ${CLAUDE_PLUGIN_ROOT} is a template variable. Resolve to your
   # plugin's installation path (typically ~/.claude/plugins/cache/clavain-vX.Y.Z)
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect-domains.py {PROJECT_ROOT} --json
   ```
   ```

2. OR: Use a relative path from PROJECT_ROOT if the skill is installed:
   ```bash
   python3 "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/scripts/detect-domains.py" ...
   ```

3. OR: Define `CLAUDE_PLUGIN_ROOT` at skill start in an "Environment Setup" section.

**Impact**: Low — agents likely infer the correct path from context. But explicit resolution guidance improves clarity.

---

### Improvements Suggested

#### IMP-1: Extract phases, scoring examples, and roster into references/ directory

**Rationale**: The 546-line SKILL.md violates plugin conventions. Extracting reusable content to `references/` reduces SKILL.md to ~80-100 lines (just routing logic and phase sequence).

**Proposed structure**:
```
skills/flux-drive/
├── SKILL.md (~90 lines: input detection, phase router, integration)
├── phases/
│   ├── launch.md (unchanged, 429 lines)
│   ├── synthesize.md (unchanged)
│   ├── cross-ai.md (unchanged)
│   └── shared-contracts.md (unchanged, 98 lines)
├── references/
│   ├── agent-roster.md (59 lines, from SKILL.md lines 450-508)
│   ├── scoring-examples.md (57 lines, from SKILL.md lines 329-385)
│   ├── triage-guide.md (10 lines, from SKILL.md lines 387-391 + scoring algorithm)
│   ├── glossary.md (new, 20 lines — defines tier/stage/phase/launch/dispatch)
│   └── path-resolution.md (new, 15 lines — OUTPUT_DIR derivation)
```

**SKILL.md reduced to**:
- Input detection (lines 12-40, ~29 lines)
- Phase 1 router (lines 43-447, condensed to ~30 lines with references to triage-guide.md)
- Phase 2-4 routers (lines 512-526, ~15 lines)
- Integration notes (lines 530-546, ~10 lines)
- **Total: ~90 lines**

**Impact**: Reduces initial context load from 546 to ~90 lines. Agents reference detailed content only when needed.

---

#### IMP-2: Create single canonical Findings Index format specification in shared-contracts.md

**Rationale**: The Findings Index format is the contract between agents and synthesis. Defining it in 3 places creates drift risk.

**Proposed change**:

In `shared-contracts.md`, expand lines 11-16:

```markdown
## Output Format: Findings Index

All agents produce this exact format:

### Findings Index
- P0 | P0-1 | "Section Name" | Title of the issue
- P1 | P1-1 | "Section Name" | Title of the issue
- P2 | P2-1 | "Section Name" | Title of the issue
- IMP | IMP-1 | "Section Name" | Title of improvement
Verdict: safe|needs-changes|risky

**Field definitions**:
- **Severity**: P0 (blocking), P1 (significant), P2 (minor), IMP (improvement)
- **ID**: Severity prefix + sequential number (e.g., P0-1, P0-2, IMP-1)
- **Section Name**: Document section where the issue appears (quoted)
- **Title**: One-line issue summary
- **Verdict**: safe (no P0/P1), needs-changes (has P1+), risky (has P0)

**Zero-findings case**: Empty index with just header and verdict:
### Findings Index
Verdict: safe
```

Then in SKILL.md and launch.md, replace the duplicated format with:

```markdown
The file MUST start with a Findings Index block (see phases/shared-contracts.md for format).
```

**Impact**: Single source of truth for format. Future changes (e.g., adding a confidence column) require one edit.

---

#### IMP-3: Add score calculation formula to scoring table for clarity

**Rationale**: The scoring examples show final scores but don't show the arithmetic. Agents may not understand how base + domain_boost + project + domain_agent sum to the total.

**Proposed change**:

Add a formula row above each scoring table:

```markdown
**Score formula**: `total = base + domain_boost + project + domain_agent`

| Agent | Category | Base | Domain Boost | Project | DA | Total | Stage | Action |
|-------|----------|------|--------------|---------|----|----|-------|--------|
| fd-architecture | Plugin | 3 | +2 (≥3 web-api criteria) | +1 | — | **6** | 1 | Launch |
```

And add a note below each table:

```
(Total calculation: 3 base + 2 domain_boost + 1 project = 6)
```

**Impact**: Reduces confusion about how scores are computed. Explicit arithmetic shows the additive model clearly.

---

#### IMP-4: Create terminology glossary in references/ defining tier/stage/phase/launch/dispatch

**Rationale**: Inconsistent terminology (P1-3) creates ambiguity. A glossary provides a single definition for each term.

**Proposed file**: `references/glossary.md`

```markdown
# Flux-Drive Terminology

## Core Concepts

- **Input**: The path provided by the user (file, directory, or diff)
- **Document**: A file's content when INPUT_TYPE is file or diff
- **Repository**: The codebase when INPUT_TYPE is directory
- **Phase**: Sequential skill execution steps
  - Phase 1: Analyze + Static Triage
  - Phase 2: Launch (agent dispatch)
  - Phase 3: Synthesize (convergence analysis)
  - Phase 4: Cross-AI Comparison (Oracle-specific)

## Triage & Dispatch

- **Stage**: Dispatch grouping based on agent scores
  - Stage 1: Top 40% of slots (highest-scoring agents, launched first)
  - Stage 2: Remaining selected agents (launched on-demand after Stage 1)
- **Expansion pool**: Agents that scored ≥2 but didn't get a slot (candidates for Stage 2)
- **Launch**: User-facing term for dispatching agents (used in prompts and UI)
- **Dispatch**: Implementation term for task creation (used in code/logs)

## Scoring Components

- **Base score** (0-3): Agent's relevance to document content
- **Domain boost** (0-2): Bonus for agents with domain profile injection criteria
- **Project bonus** (0-1): Bonus when project has CLAUDE.md/AGENTS.md
- **Domain agent bonus** (0-1): Bonus for /flux-gen generated agents
- **Final score**: Sum of all components (max 7)

## Output Artifacts

- **OUTPUT_DIR**: Absolute path where agents write findings (e.g., /root/projects/Foo/docs/research/flux-drive/my-doc)
- **Findings Index**: Machine-parseable summary at top of each agent's output file
- **Verdict**: Agent's overall assessment (safe | needs-changes | risky)
```

Reference this file in SKILL.md: "See references/glossary.md for terminology definitions."

**Impact**: Eliminates terminology confusion. Agents and users have a single authoritative reference.

---

#### IMP-5: Extract path derivation logic into reusable template or helper function

**Rationale**: OUTPUT_DIR derivation is scattered (P1-4). Centralizing it reduces duplication.

**Proposed file**: `references/path-resolution.md`

```markdown
# Path Resolution

## Input Path Derivation

Detect the input type and derive paths:

```bash
INPUT_PATH="<user-provided path>"

# Detect type
if [[ -f "$INPUT_PATH" ]]; then
  if head -n5 "$INPUT_PATH" | grep -qE '^(diff --git|--- a/)'; then
    INPUT_TYPE="diff"
  else
    INPUT_TYPE="file"
  fi
  INPUT_DIR="$(dirname "$INPUT_PATH")"
  INPUT_FILE="$INPUT_PATH"
elif [[ -d "$INPUT_PATH" ]]; then
  INPUT_TYPE="directory"
  INPUT_DIR="$INPUT_PATH"
  INPUT_FILE=""
else
  echo "Error: INPUT_PATH does not exist or is not a file/directory" >&2
  exit 1
fi

# Derive stem
if [[ "$INPUT_TYPE" == "directory" ]]; then
  INPUT_STEM="$(basename "$INPUT_DIR")"
else
  INPUT_STEM="$(basename "$INPUT_FILE" | sed 's/\.[^.]*$//')"  # strip extension
fi

# Find project root
PROJECT_ROOT="$INPUT_DIR"
while [[ "$PROJECT_ROOT" != "/" ]]; do
  if [[ -d "$PROJECT_ROOT/.git" ]]; then
    break
  fi
  PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
if [[ "$PROJECT_ROOT" == "/" ]]; then
  PROJECT_ROOT="$INPUT_DIR"  # fallback if no .git found
fi

# Resolve OUTPUT_DIR to absolute path
OUTPUT_DIR="$(realpath "$PROJECT_ROOT/docs/research/flux-drive/$INPUT_STEM")"

echo "INPUT_TYPE:    $INPUT_TYPE"
echo "INPUT_STEM:    $INPUT_STEM"
echo "PROJECT_ROOT:  $PROJECT_ROOT"
echo "OUTPUT_DIR:    $OUTPUT_DIR"
```
```

Then in SKILL.md lines 19-33, replace the derivation logic with:

```markdown
Detect the input type and derive paths. See `references/path-resolution.md` for the full algorithm.

**Summary**:
- If INPUT_PATH is a diff file: `INPUT_TYPE = diff`
- If INPUT_PATH is a non-diff file: `INPUT_TYPE = file`
- If INPUT_PATH is a directory: `INPUT_TYPE = directory`
- OUTPUT_DIR is always an absolute path: `{PROJECT_ROOT}/docs/research/flux-drive/{INPUT_STEM}`
```

**Impact**: Reduces SKILL.md by ~15 lines. Provides a copy-paste-ready implementation for agents.

---

### Overall Assessment

The flux-drive skill suffers from structural bloat and DRY violations. The 546-line SKILL.md is 5.4× the recommended maximum, burying routing logic under 450+ lines of examples, rosters, and detailed instructions. The Findings Index format is copy-pasted into 3 locations without a canonical source. Terminology is inconsistent (tiers vs stages, launch vs dispatch), and path resolution logic is scattered. These are fixable quality issues that don't affect functionality but create maintenance burden and token waste. Extracting reference content and consolidating contracts will bring the skill into compliance with plugin conventions.

<!-- flux-drive:complete -->
