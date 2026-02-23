---
name: route
description: LLM-powered sprint/work auto-router — classifies task complexity and dispatches to the right workflow
argument-hint: "[bead ID or feature description]"
---

# Auto-Route to Sprint or Work

Classifies whether a task needs the full `/sprint` lifecycle or the fast `/work` execution path, then auto-dispatches.

## Step 1: Gather Context

Determine what the user wants to route:

**If `$ARGUMENTS` is empty:**
- Set `route_mode="discovery"` — will route to `/sprint` (needs brainstorm to figure out what to do)

**If `$ARGUMENTS` matches a bead ID** (format: `[A-Za-z]+-[a-z0-9]+`):
- Set `route_mode="bead"`
- Read bead metadata:
  ```bash
  bead_info=$(bd show "$ARGUMENTS" 2>/dev/null) || { echo "Bead not found: $ARGUMENTS"; exit 1; }
  bead_id="$ARGUMENTS"
  ```
- Extract: title, description, priority, type, status
- Check for artifacts:
  ```bash
  has_plan=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" get-artifact "$bead_id" "plan" 2>/dev/null) || has_plan=""
  has_brainstorm=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" get-artifact "$bead_id" "brainstorm" 2>/dev/null) || has_brainstorm=""
  has_prd=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" get-artifact "$bead_id" "prd" 2>/dev/null) || has_prd=""
  bead_phase=$(bd state "$bead_id" phase 2>/dev/null) || bead_phase=""
  bead_action=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" infer-action "$bead_id" 2>/dev/null) || bead_action=""
  complexity=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" classify-complexity "$bead_id" "" 2>/dev/null) || complexity="3"
  child_count=$(bd children "$bead_id" 2>/dev/null | jq 'length' 2>/dev/null) || child_count="0"
  ```

**Otherwise** (free text):
- Set `route_mode="text"`, `description="$ARGUMENTS"`
- Run complexity heuristic on the text:
  ```bash
  complexity=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" classify-complexity "" "$ARGUMENTS" 2>/dev/null) || complexity="3"
  complexity_label=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" complexity-label "$complexity" 2>/dev/null) || complexity_label="moderate"
  ```

## Step 2: Fast-Path Heuristics

Skip the LLM if the answer is obvious. Check these in order — first match wins:

| Condition | Route | Reason |
|-----------|-------|--------|
| `route_mode == "discovery"` (no arguments) | `/clavain:sprint` | Needs work discovery + brainstorm |
| Bead has a plan artifact (`has_plan` is non-empty) | `/clavain:work <plan_path>` | Plan already exists |
| `bead_phase` is `planned` or `plan-reviewed` | `/clavain:work <plan_path>` | Ready for execution |
| `bead_action` is `execute` or `continue` | `/clavain:work <plan_path>` | Bead state indicates execution |
| Bead has no description AND no brainstorm artifact | `/clavain:sprint` | Needs brainstorm first |
| `complexity == 1` (trivial) | `/clavain:work` | Too simple for full sprint |

If a fast-path matches:
1. Display: `Route: <command> (heuristic) — <reason>`
2. Skip to **Step 4: Dispatch**.

If no fast-path matches, continue to Step 3.

## Step 3: LLM Classification

Dispatch a haiku subagent to classify the task:

```
Task(subagent_type="haiku", model="haiku", prompt=<see below>)
```

Build the classification prompt:

```
You are a task router for a software development workflow.

Given this task:
- Description: {description from bead or free text}
- Has plan: {yes/no}
- Has brainstorm: {yes/no}
- Has PRD: {yes/no}
- Complexity score: {complexity}/5 ({complexity_label})
- Priority: {priority or "unset"}
- Type: {type or "unset"}
- Bead phase: {bead_phase or "none"}
- Child bead count: {child_count}

Route to ONE of:
- /sprint — Full lifecycle (brainstorm → strategy → plan → execute → review → ship). Use when: new feature with no plan, ambiguous scope, research needed, security-sensitive, cross-cutting changes, epic with children, high complexity (4-5).
- /work — Fast execution (plan → execute → ship). Use when: plan already exists, scope is clear, known pattern, simple/moderate complexity (1-3), single-module change, bug fix with clear repro.

Return ONLY valid JSON on a single line: {"command": "/sprint" or "/work", "confidence": 0.0-1.0, "reason": "one sentence"}
```

Parse the JSON response. If parsing fails, default to `/sprint` (safer fallback — sprint can always skip phases, but work can't add them).

## Step 4: Dispatch

1. **Display the verdict:**
   ```
   Route: /work (0.92) — Plan exists and scope is clear
   ```
   or for heuristic routes:
   ```
   Route: /sprint (heuristic) — Needs work discovery + brainstorm
   ```

2. **Auto-dispatch** — invoke the chosen command via the Skill tool:
   - If routing to `/clavain:sprint`: pass through `$ARGUMENTS` (bead ID or feature text)
   - If routing to `/clavain:work`: pass the plan path if available, otherwise pass `$ARGUMENTS`
   - **Do not ask for confirmation** — the whole point is auto-routing

3. **Stop after dispatch.** The invoked command handles everything from here.
