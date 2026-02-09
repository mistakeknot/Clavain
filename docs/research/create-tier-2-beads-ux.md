# Tier-2 Beads Creation: UX Improvements for Interpeer/Beads Workflow

**Date:** 2026-02-09
**Status:** Complete

## Objective

Create four P1 task issues in Beads tracking UX improvements for the interpeer/beads workflow. These address friction points observed during multi-agent review sessions: lack of progress visibility, missing synthesis templates, destructive write-back defaults, and unauthorized auto-chaining.

## Issues Created

| ID | Title | Type | Priority | Status |
|---|---|---|---|---|
| Clavain-690 | Surface per-agent completion ticks during 3-5 min wait | task | P1 | open |
| Clavain-amz | Template Step 3.5 synthesis report with same rigor as agent prompt template | task | P1 | open |
| Clavain-2kf | Default to summary.md for file inputs, opt-in for inline annotations | task | P1 | open |
| Clavain-c7i | Replace auto-chain to interpeer mine mode with explicit user consent | task | P1 | open |

## Issue Details

### 1. Progress Feedback During Wait (Clavain-690)

**Problem:** When interpeer launches 3-5 agents in parallel, the user stares at a blank terminal for 3-5 minutes with no indication of progress.

**Solution direction:** Surface per-agent completion ticks — as each agent finishes, show a brief status line (agent name, elapsed time, pass/fail). This transforms a silent wait into visible progress.

### 2. Synthesis Report Template (Clavain-amz)

**Problem:** Step 3.5 (synthesis of multi-agent results) lacks the structural rigor that agent prompt templates have. The synthesis output is inconsistent across runs.

**Solution direction:** Create a formal template for synthesis reports with the same level of detail as agent prompt templates — defined sections, expected fields, formatting conventions.

### 3. Non-Destructive Write-Back Default (Clavain-2kf)

**Problem:** When interpeer processes file inputs, it can annotate files inline by default, which modifies the user's source files without explicit consent.

**Solution direction:** Default output target should be `summary.md` (a separate file). Inline annotations should require an explicit opt-in flag, preserving the user's original files.

### 4. Consent Gate for Interpeer Mine Mode (Clavain-c7i)

**Problem:** The system auto-chains into interpeer mine mode without asking the user, which can trigger unexpected agent runs and consume resources.

**Solution direction:** Replace the automatic transition with an explicit consent prompt. The user must acknowledge before mine mode activates.

## Current Beads State

After creation, `bd list` shows 11 total issues:
- **3 P0 issues** — pre-existing (timeout, lifecycle guard, completion protocol)
- **4 P1 issues** — newly created (the four above)
- **2 P2 issues** — pre-existing (refactor, simplify)
- **1 P2 feature** — pre-existing (YAML frontmatter replacement)
- **1 P3 bug** — pre-existing (tier vocabulary fix)

## Observations

- All four issues were created without descriptions. Future iterations should include `--description` flags for better context.
- The `beads.role` config warning appeared on every command — running `bd init` would suppress this.
- The P1 tier sits between the critical P0 reliability fixes and the P2 structural improvements, correctly reflecting that these are important UX improvements but not blocking bugs.
