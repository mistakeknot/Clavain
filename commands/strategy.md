---
name: strategy
description: Structure brainstorm output into a PRD with features, create beads for tracking, and validate before detailed planning
argument-hint: "[brainstorm doc path, or feature description if no brainstorm exists]"
---

# Strategy

Bridge between brainstorming (WHAT) and planning (HOW). Takes an idea or brainstorm doc and produces a structured PRD with trackable work items.

## Input

<strategy_input> #$ARGUMENTS </strategy_input>

### Resolve input:

1. If argument is a file path → read it as the brainstorm doc
2. If no argument → check `docs/brainstorms/` for the most recent brainstorm:
   ```bash
   ls -t docs/brainstorms/*.md 2>/dev/null | head -1
   ```
3. If no brainstorm exists → ask the user what they want to build, then proceed directly (strategy can work without a prior brainstorm)

## Phase 0: Prior Art Check

Before designing anything, check if the problem is already solved — either by an assessed external tool or by existing Demarch infrastructure.

1. **Search assessment docs** for prior verdicts on the domain:
   ```bash
   grep -ril "<2-3 keywords from the topic>" docs/research/assess-*.md 2>/dev/null
   ```
   If hits found, read the verdict. If verdict is "adopt" or "port-partially", **stop and surface this** to the user before proceeding:
   > "We already assessed [tool] for this domain with verdict '[adopt]'. Should we use that instead of building from scratch?"

2. **Search existing beads** for prior work in this area:
   ```bash
   bd search "<keywords>" 2>/dev/null
   ```

3. **Search existing plugins/skills** for overlap:
   ```bash
   ls interverse/*/CLAUDE.md 2>/dev/null | xargs grep -li "<keywords>" 2>/dev/null
   ```

4. **Web search for unknown prior art (conditional)** — if any feature involves building **new infrastructure or tooling from scratch** (not extending existing modules), run a quick web search:
   ```
   WebSearch: "open source <what we're building> CLI tool 2025 2026"
   ```
   Spend ≤2 minutes. If a mature project exists (>100 stars, active), surface it before creating beads. Skip for feature additions, bug fixes, refactors, and UI work.

If prior art exists with "adopt" verdict, the default should be integration (install + wire up), not reimplementation.

## Phase 1: Extract Features

From the brainstorm doc or user description, identify **discrete features**. Each feature should be:
- Independently deliverable
- Testable in isolation
- Small enough for one session (1-3 hours of agent work)

Present the feature list to the user with AskUserQuestion:

> "I've identified these features from the brainstorm. Which should we include in this iteration?"

Options should include "All of them" and the individual features as multi-select.

## Phase 2: Write PRD

Write to `docs/prds/YYYY-MM-DD-<topic>.md`.

**Frontmatter (required):** Every PRD MUST start with this YAML frontmatter block:

```yaml
---
artifact_type: prd
bead: <CLAVAIN_BEAD_ID or "none">
stage: design
---
```

```markdown
---
artifact_type: prd
bead: <bead_id>
stage: design
---
# PRD: <Title>

## Problem
[1-2 sentences: what pain point this solves]

## Solution
[1-2 sentences: what we're building]

## Features

### F1: <Feature Name>
**What:** [One sentence]
**Acceptance criteria:**
- [ ] [Concrete, testable criterion]
- [ ] [Concrete, testable criterion]

### F2: <Feature Name>
...

## Non-goals
[What we're explicitly NOT doing this iteration]

## Dependencies
[External systems, libraries, or prior work needed]

## Open Questions
[Anything unresolved that could affect implementation]
```

Ensure `docs/prds/` directory exists before writing.

## Phase 3: Create Beads

**Dedup guard (REQUIRED before any `bd create`):**

Before creating each feature bead, search for existing open beads with similar titles. Extract 2-3 keywords from the feature name and search:

```bash
# For each feature, check for duplicates
bd search "<keyword1> <keyword2>" --status=open 2>/dev/null
```

- If search returns beads with clearly matching intent → **do NOT create a duplicate**. Instead, reuse the existing bead ID and report: `Reusing existing bead <id> for F<n>: <name>`.
- If search returns beads with similar but different scope → report both to the user and ask via AskUserQuestion: "Existing bead <id> looks similar. Create new or reuse?"
- If no matches → proceed with creation.

This prevents the duplicate beads that accumulate when multiple sessions strategize the same domain.

**Sprint-aware bead creation:**

If `CLAVAIN_BEAD_ID` is set (we're inside a sprint):
- Do NOT create a separate epic. The sprint bead IS the epic.
- Create feature beads as children of the sprint bead:
  ```bash
  bd create --title="F1: <feature name>" --type=feature --priority=2
  bd dep add <feature-id> <CLAVAIN_BEAD_ID>
  ```
- Update sprint state:
  ```bash
  "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" set-artifact "$CLAVAIN_BEAD_ID" "prd" "<prd_path>"
  ```

If `CLAVAIN_BEAD_ID` is NOT set (standalone strategy):
- Create epic and feature beads as before:
  ```bash
  bd create --title="<PRD title>" --type=epic --priority=1
  ```
  For each feature:
  ```bash
  bd create --title="F1: <feature name>" --type=feature --priority=2
  bd dep add <feature-id> <epic-id>
  ```

Report the created beads to the user.

### Phase 3b: Record Phase

After creating beads, record the phase transition:
```bash
if [[ -n "${CLAVAIN_BEAD_ID:-}" ]]; then
    "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" advance-phase "$CLAVAIN_BEAD_ID" "strategized" "PRD: <prd_path>" ""
    "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" record-phase "$CLAVAIN_BEAD_ID" "strategized"
else
    # Standalone strategy — use the newly created epic bead
    "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" advance-phase "<epic_bead_id>" "strategized" "PRD: <prd_path>" ""
fi
```
Also set `phase=strategized` on each child feature bead created:
```bash
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" advance-phase "<feature_bead_id>" "strategized" "PRD: <prd_path>" ""
```

## Phase 4: Validate

Run a lightweight flux-drive review on the PRD:

```
/interflux:flux-drive docs/prds/YYYY-MM-DD-<topic>.md
```

This catches scope creep, missing acceptance criteria, and architectural risks before any code is written.

## Phase 5: Handoff

**If inside a sprint** (check: `bd state "$CLAVAIN_BEAD_ID" sprint` returns `"true"`):
- Skip the handoff question. Sprint auto-advance handles the next step.
- Display the output summary (below) and return to the caller.

**If standalone** (no sprint context):
Present next steps with AskUserQuestion:

> "Strategy complete. What's next?"

Options:
1. **Plan the first feature** — Run `/clavain:write-plan` for the highest-priority unblocked bead
2. **Plan all features** — Run `/clavain:write-plan` for each feature sequentially
3. **Refine PRD** — Address flux-drive findings first
4. **Done for now** — Come back later

## Output Summary

```
Strategy complete!

PRD: docs/prds/YYYY-MM-DD-<topic>.md
Epic: <epic-id> — <title>
Features:
  - <bead-id>: F1 — <name> [P2]
  - <bead-id>: F2 — <name> [P2]

Flux-drive: [pass/findings count]

Next: /clavain:write-plan to start implementation planning
```
