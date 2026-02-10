# Plan: Clavain-6a4 — Slim agent system prompts for flux-drive context

## Context
Review agents have system prompts ranging from 3K to 13K chars. When invoked by flux-drive, several sections are redundant: native Output Format (overridden by flux-drive), personality/style instructions (don't affect structured output), verbose language-specific pattern libraries. This bead evaluates how to trim agent prompts for flux-drive dispatch.

## Current State
- Agent `.md` files in `agents/review/` contain full system prompts
- These prompts include: role definition, CLAUDE.md check, review approach, output format, examples, pattern libraries
- flux-drive overrides the output format section entirely
- Personality instructions ("British wit and Eastern-European directness" in concurrency-reviewer) don't affect finding quality in structured mode
- Some agents have 150+ lines of language-specific patterns

## Options Evaluated

### Option A: `<!-- flux-drive: skip -->` markers
- Add markers around sections that should be stripped during flux-drive dispatch
- Orchestrator strips marked sections when constructing prompt
- **Pro**: Per-section control, agents remain unchanged for standalone use
- **Con**: Markers clutter agent files, maintenance burden (must remember to add markers to new sections)

### Option B: Separate flux-drive-optimized variants
- Create `agents/review/flux-drive/` with stripped-down copies
- **Pro**: Clean separation
- **Con**: Maintenance nightmare — two versions of every agent to keep in sync

### Option C: Accept the cost
- Agent richness may occasionally produce better findings
- 200K context windows can absorb 13K per agent easily
- **Pro**: Zero effort, zero risk
- **Con**: Still wastes tokens (2-5K per run)

### Option D: Strip by section type (recommended)
- In launch.md, instruct orchestrator to strip known-redundant section types from ALL agents:
  1. **Output Format sections**: Already overridden by flux-drive
  2. **`<example>` blocks**: Already covered by Clavain-2yx
  3. **Style/personality sections**: Don't affect structured output quality
- Do NOT strip: role definition, review approach/checklist, pattern libraries (these affect finding quality)
- **Pro**: No agent file changes, single rule in launch.md
- **Con**: Orchestrator must identify section types (but these follow consistent naming)

## Recommended Approach: Option D (strip by section type)

## Implementation Plan

### Step 1: Audit agent prompt structure
Survey all agents in `agents/review/` to identify section naming patterns:

Typical structure:
1. Role definition (1-3 lines) — KEEP
2. "First Step" / CLAUDE.md check — KEEP (but note: flux-drive already provides project context)
3. Review Approach / Checklist — KEEP
4. Pattern libraries / language-specific checks — KEEP (these guide analysis)
5. Output Format — STRIP (overridden by flux-drive)
6. Examples (`<example>` blocks) — STRIP (covered by Clavain-2yx)
7. Style/personality notes — STRIP

### Step 2: Add stripping rules to launch.md
**File:** `skills/flux-drive/phases/launch.md`

In Step 2.2, after the existing `<example>` stripping instruction (from Clavain-2yx), add:

> **Additional prompt trimming for flux-drive dispatch:**
> When constructing agent prompts, strip these sections from the agent's system prompt:
> 1. **Output Format section** (any section titled "Output Format", "Output", "Response Format", or similar) — flux-drive provides its own format
> 2. **Style/personality sections** (any section about tone, wit, directness, humor) — not relevant for structured output
> 
> **Do NOT strip**: Role definition, review approach/checklist, pattern libraries, language-specific checks. These affect finding quality.

### Step 3: Same for launch-codex.md
**File:** `skills/flux-drive/phases/launch-codex.md`

Add same stripping rules for the AGENT_IDENTITY section of Codex task files.

### Step 4: Verify no regression risk
The stripped sections are:
- Output Format: Already ignored (overridden)
- Style: Doesn't affect what issues are found, only how they're described (and flux-drive's format overrides description style anyway)
- Examples: Covered by Clavain-2yx

No finding quality regression expected.

## Design Decisions
- **Option D over Option A**: Markers would need to be added to every agent file AND maintained for new agents. Launch.md rules are centralized and automatic.
- **Keep pattern libraries**: These are the substantive part of agent expertise. A Go reviewer's goroutine lifecycle patterns directly guide what it looks for.
- **Keep CLAUDE.md check**: Even though flux-drive provides project context, the agent's own context check adds project-specific grounding.

## Dependencies
- **Clavain-2yx** (strip examples): Should land first or concurrently. This bead adds Output Format and style stripping on top.

## Files Changed
1. `skills/flux-drive/phases/launch.md` — Add section-type stripping rules
2. `skills/flux-drive/phases/launch-codex.md` — Same rules for Codex dispatch

## Estimated Scope
~10-15 lines of new instructional content per file. Builds on Clavain-2yx.

## Acceptance Criteria
- [ ] Output Format sections are stripped from agent prompts in flux-drive
- [ ] Style/personality sections are stripped
- [ ] Role definition, review approach, and pattern libraries are preserved
- [ ] Rules are in launch.md and launch-codex.md
- [ ] No agent `.md` files are modified
