---
name: project-kickstart
description: Use when bootstrapping a new project — runs the full init-to-beads ceremony in one shot
---

# Project Kickstart

## Overview

Bootstrap a new project with the full Demarch ceremony: scaffold agent memory, generate product docs, and create trackable beads. Replaces the manual sequence of `/init` + `/interpath:vision` + `/interpath:prd` + `/interpath:roadmap` + bead creation.

**Announce at start:** "I'm using the project-kickstart skill to bootstrap this project."

## Inputs

The user provides:
- **Project name** (required)
- **One-liner description** (required)
- **GitHub repo** — create if it doesn't exist, or use existing
- **Brainstorm notes** — any existing context, vision, or requirements

## The Process

### Step 1: Scaffold

Run the Clavain `/init` command to scaffold the `.clavain/` agent memory filesystem:
- Creates CLAUDE.md and AGENTS.md if missing
- Sets up `.clavain/` directory structure
- Initializes beads with `bd init`

If a GitHub repo needs to be created:
```bash
gh repo create mistakeknot/<project-name> --private --description "<one-liner>"
git remote add origin git@github.com:mistakeknot/<project-name>.git
```

### Step 2: Philosophy (if Demarch subproject)

If this project lives under the Demarch monorepo, create a `PHILOSOPHY.md` with:
- Core design bets (3-5 bullets)
- Key tradeoffs and why they were chosen
- What this project deliberately does NOT do

Skip for standalone projects — the vision doc covers this.

### Step 3: Generate Product Docs

Run these in sequence (each builds on the previous):

1. **Vision doc** — `/interpath:vision`
   - Big idea, design principles, success criteria
2. **PRD** — `/interpath:prd`
   - Problem statement, components, requirements
3. **Roadmap** — `/interpath:roadmap`
   - Milestones, phases, dependencies

### Step 4: Create Beads

From the roadmap, create beads for each milestone/epic:

```bash
bd create --title="<milestone>" --description="<scope>" --type=epic --priority=<N>
```

Then create child tasks for the first milestone only (don't over-plan future milestones).

### Step 5: Initial Commit

Stage all generated files and commit:

```bash
git add .
git commit -m "kickstart: scaffold project with vision, PRD, roadmap, and beads"
git push
```

### Step 6: Report

Summarize what was created:
- Files generated (list)
- Beads created (count + epic names)
- Next step recommendation (which bead to start with)
