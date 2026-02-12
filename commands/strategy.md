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

## Phase 1: Extract Features

From the brainstorm doc or user description, identify **discrete features**. Each feature should be:
- Independently deliverable
- Testable in isolation
- Small enough for one session (1-3 hours of agent work)

Present the feature list to the user with AskUserQuestion:

> "I've identified these features from the brainstorm. Which should we include in this iteration?"

Options should include "All of them" and the individual features as multi-select.

## Phase 2: Write PRD

Write to `docs/prds/YYYY-MM-DD-<topic>.md`:

```markdown
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

Create a beads epic and child issues for each feature:

```bash
bd create --title="<PRD title>" --type=epic --priority=1
```

For each feature:
```bash
bd create --title="F1: <feature name>" --type=feature --priority=2
bd dep add <feature-id> <epic-id>
```

Report the created beads to the user.

## Phase 4: Validate

Run a lightweight flux-drive review on the PRD:

```
/clavain:flux-drive docs/prds/YYYY-MM-DD-<topic>.md
```

This catches scope creep, missing acceptance criteria, and architectural risks before any code is written.

## Phase 5: Handoff

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
