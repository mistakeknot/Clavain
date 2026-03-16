---
name: sprint-dag
description: Visualize sprint execution as a DAG — shows phases, dispatches, and artifacts
argument-hint: "[sprint bead ID or empty for active sprint]"
---

# Sprint DAG

Render a sprint's execution history as a mermaid flowchart.

## Context

<sprint_id> #$ARGUMENTS </sprint_id>

## Steps

1. **Resolve sprint.**
   ```bash
   sprint_id="${ARGUMENTS:-$(clavain-cli sprint-find-active 2>/dev/null)}"
   ```
   If still empty: print "No active sprint found." and stop.

2. **Fetch turns.**
   ```bash
   clavain-cli cxdb-history "$sprint_id"
   ```
   Output: JSON array of `{turn_id, type_id, payload, depth}`. If CXDB unavailable or empty: print "No CXDB history for $sprint_id." and stop.

3. **Build mermaid graph from turns.**

   Parse the JSON. Map `type_id` → node category:
   - `clavain.phase.v1` → phase node (label: `payload.phase`)
   - `clavain.dispatch.v1` / `clavain.dispatch.v2` → dispatch node under its phase (label: `payload.agent_name`, subtext: model if present)
   - `clavain.artifact.v1` → annotation on the nearest preceding dispatch (label: `payload.artifact_type: basename(payload.path)`)
   - `clavain.scenario.v1` → child of nearest dispatch (label: `scenario_id step_index pass/fail`)
   - Other types → append as metadata note on the parent phase

   Node IDs: `P<turn_id>` for phases, `D<turn_id>` for dispatches, `A<turn_id>` for artifacts.

   Determine current phase: the last `clavain.phase.v1` turn with no successor phase turn.

   Color coding via `style` directives:
   - Phase nodes: `fill:#4a9` (green) if not current, `fill:#fa0` (yellow) if current
   - Dispatch nodes: `fill:#69f` (blue) for completed (`status=success`), `fill:#f66` (red) for failed (`status=error|failed`), `fill:#ccc` (gray) for pending/unknown
   - Artifact nodes: `fill:#fff,stroke:#888` (white with border)

4. **Emit mermaid block.**

   ```
   flowchart TD
     subgraph Sprint $sprint_id
       P1[brainstorm] --> P2[strategy]
       P2 --> D1[fd-architecture]
       D1 --> A1[artifact: brainstorm.md]
       ...
     end
   ```

   Print inside a fenced ` ```mermaid ` block. Claude renders it inline.

5. **Show summary stats.**

   After the graph, print a compact table:

   | Metric | Value |
   |--------|-------|
   | Total turns | N |
   | Phases completed | N |
   | Agents dispatched | N (unique: N) |
   | Artifacts registered | N |
   | Time span | first→last timestamp (HH:MM elapsed) |

   Per-phase timing: for each phase, compute elapsed between its timestamp and the next phase turn's timestamp. List as `phase: Xm` on one line if ≤6 phases, else skip per-phase detail.

   If CXDB is available but has <2 turns: print "Sprint just started — not enough history to render DAG." and show whatever partial data exists.
