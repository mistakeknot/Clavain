# Plan: Clavain-7p2 — Resolve output format strategy: native YAML vs markdown Findings Index

## Context
This is a **decision bead**, not an implementation bead. Two competing approaches exist for the output format problem, and this bead must decide which one to pursue. The decision blocks Clavain-27u (Findings Index implementation).

### The Problem
Flux-drive agents have their own native output format (defined in each agent's `.md` file), but flux-drive needs structured YAML frontmatter for machine-parseable synthesis. Currently, a ~50-line "Output Format Override" block is injected into every agent's task prompt, overriding their native format. This override is:
- Token-expensive (~2K tokens × N agents per run)
- Fragile (agents sometimes partially follow their native format AND the override)
- Redundant (the same override is pasted into every prompt)

### Option A: Native YAML (push structured format to agents)
- Modify all review agent `.md` files to use YAML frontmatter as their native output format
- Remove the Output Format Override block from launch.md entirely
- Saves ~2K tokens/run in override instructions
- **Downside**: Agents used outside flux-drive (standalone reviews) would also output YAML, which is less human-readable
- **Downside**: Every agent `.md` file must be edited

### Option B: Markdown Findings Index + findings.json (Clavain-27u)
- Keep agents' native prose format
- Replace YAML frontmatter with a rigid markdown "Findings Index" table at the top of each output
- Orchestrator parses the Findings Index into a central `findings.json` for synthesis
- **Downside**: Still needs an override block (albeit for markdown table, not YAML)
- **Downside**: Adds a post-processing step (parse markdown tables → JSON)
- **Upside**: Agents remain human-readable standalone

### Option C: Hybrid — context-aware format selection
- Agents have their native prose format by default
- When invoked by flux-drive, the override block tells them to ADD YAML frontmatter BEFORE their normal prose
- Standalone use: prose only. Flux-drive use: YAML + prose.
- **Upside**: Best of both worlds — human-readable AND machine-parseable
- **Downside**: Override block still needed but smaller (just "add YAML frontmatter", not "replace your entire format")

## Recommended Decision: Option C (Hybrid)

### Rationale
1. **Token savings**: Override block shrinks from ~50 lines to ~15 lines (just the YAML schema, no prose format instructions). Saves ~1.5K tokens/run.
2. **Agent reusability**: Agents work standalone with their native format AND work in flux-drive with added frontmatter.
3. **No agent file changes needed**: Native agent prompts stay as-is. The override just prepends YAML.
4. **Synthesis unchanged**: synthesize.md already uses frontmatter-first parsing — this keeps working.
5. **Incremental**: Can be implemented immediately without touching all agent files.

### Implementation Sketch (for the chosen approach)
1. **Slim the Output Format Override** in launch.md:
   - Remove all prose format instructions (Summary, Issues Found, etc.)
   - Keep only: "Prepend YAML frontmatter with this schema: [schema]. Then write your review in your native format."
   - Keep the `.partial` → `.md` rename protocol and `<!-- flux-drive:complete -->` marker
2. **Update synthesize.md** frontmatter parsing to handle YAML + arbitrary prose (already works this way)
3. **Update launch-codex.md** override block similarly
4. **Close Clavain-27u as "won't do"** since the Findings Index approach is superseded

## Decision Process
This plan recommends Option C. To resolve this bead:
1. Review the three options above
2. Decide (user confirms via bead close or in-session discussion)
3. Update Clavain-27u status based on decision
4. Create an implementation bead for the chosen approach

## Files Changed (decision only)
1. This plan document (for the record)
2. `bd close Clavain-7p2 --reason="Decision: Option C hybrid"` once confirmed
3. `bd update Clavain-27u` — either close as won't-do or update description based on decision

## Downstream Impact
- **Clavain-27u** (blocked by this): Either proceeds with modified scope or gets closed
- **Clavain-amz** (blocked by 27u): Template Step 3.5 synthesis — proceeds once format is decided
- **Clavain-apn** (blocked by 27u): launch-codex.md refactor — proceeds once format is decided
