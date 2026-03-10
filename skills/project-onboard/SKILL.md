---
name: project-onboard
description: Use when setting up any project (new or existing) in the Demarch ecosystem — introspects infrastructure, creates GitHub repo if needed, conducts guided interview, scaffolds docs and automation, configures observability, seeds content via interpath. Replaces the former project-kickstart command.
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. -->

# Project Onboard

## Overview

One-command project setup. Introspects any repo, asks minimal questions with smart defaults, then orchestrates full Demarch-level automation: beads tracking, doc scaffolding, observability, and content seeding.

Safe to re-run — all operations are idempotent (skip what already exists).

**Announce at start:** "I'm using the project-onboard skill to set up this project."

## Preconditions

Must be in a git repository (or willing to create one). Verify:

```bash
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [[ -z "$GIT_ROOT" ]]; then
    echo "Not in a git repository — will initialize one."
    git init
    GIT_ROOT=$(pwd)
fi
cd "$GIT_ROOT"
```

Also verify `bd` is available: `command -v bd`. If missing, warn but continue (beads steps will be skipped).

## Phase 0: Repository Setup (new projects only)

Skip this phase entirely if the project already has a git remote.

If no remote exists (`git remote get-url origin` fails):

1. Ask the user: "Create a GitHub repo, or add a remote manually?"
   - Default: create via `gh repo create mistakeknot/<project-name> --private --description "<one-liner>"`
   - Alternative: user provides remote URL
2. Set origin: `git remote add origin <url>`

This absorbs what was previously the separate `project-kickstart` command.

## Phase 1: Introspect

Scan the project. For each item, record ✔ (exists) or ✖ (missing):

**Infrastructure:**
- Git repo (always ✔ — precondition)
- Git remote: `git remote get-url origin 2>/dev/null`
- `.beads/` directory
- `.clavain/` directory
- `.interwatch/` directory

**Core docs:**
- `CLAUDE.md`
- `AGENTS.md`
- `PHILOSOPHY.md`
- `CONVENTIONS.md`

**Docs tree** — check each: `brainstorms plans research guides canon prd prds solutions audits diagrams migrations policies reports traces`

**Language detection** — scan for:
- `go.mod` → Go
- `Cargo.toml` → Rust
- `package.json` → JavaScript/TypeScript (check for `tsconfig.json` to distinguish)
- `pyproject.toml` or `setup.py` → Python
- `*.java` in `src/` → Java
- Fall back to file extension survey if no manifests found

**Project name inference** (first match wins):
1. `package.json` → `.name`
2. `Cargo.toml` → `[package] name`
3. `go.mod` → last segment of module path
4. `pyproject.toml` → `[project] name`
5. Git remote basename (strip `.git` suffix)
6. Current directory name

**Project type inference:**
- Multiple language manifests or top-level dirs with own manifests → monorepo
- `.claude-plugin/` directory → plugin
- `lib.rs`, or `src/index.ts` with no `app/`/`pages/` → library
- `main.go`, `cmd/`, `Dockerfile`, `app/`, `pages/` → application
- Default: application

Present the checklist to the user. Example:

```
Project scan complete: myproject (Rust application)

Infrastructure:
  ✔ Git repo (remote: github.com/user/myproject)
  ✖ Beads tracking (.beads/)
  ✖ Clavain memory (.clavain/)
  ✖ Drift detection (.interwatch/)

Core docs:
  ✖ CLAUDE.md
  ✖ AGENTS.md
  ✖ PHILOSOPHY.md
  ✖ CONVENTIONS.md

Docs tree: 0/15 directories present

Detected: Rust, 1 crate, application
```

## Phase 2: Guided Interview

Use **AskUserQuestion**. Skip questions whose answers were inferred.

**Q1** (skip if name + description inferred from README or manifest):
"What is this project? Name and one-liner."
Show inferred default in option description.

**Q2** (skip if languages detected):
"What languages and frameworks does this project use?"
Show detected languages as default.

**Q3** (skip if type inferred):
"What type of project is this?"
Options: Library, Application, Monorepo, Plugin. Show inferred default.

**Q4** (always ask):
"What are the key goals for this project in the next month?"
This seeds the brainstorm, vision, PRD, and roadmap.

**Q5** (always ask):
"How is the project built and tested?"
Infer defaults from Makefile, package.json scripts, Cargo.toml, etc.
Show inferred commands as the default option.

**Q6** (monorepo only — skip for library/application/plugin):
"Which top-level directories contain modules for the roadmap?"
Auto-detect by scanning for subdirs with `.claude-plugin/plugin.json` or `CLAUDE.md`.
Show detected dirs as the recommended default option, with "Customize..." as second option and "Skip roadmap setup" as third.
Store the answer as `roadmap_scan_dirs` for Phase 4a.

## Phase 3: Scaffold Infrastructure

Execute in order. Skip anything that already exists.

### 3a: Beads

If `.beads/` doesn't exist and `bd` is available:

```bash
bd init
bd setup claude --project
```

### 3b: Clavain Memory

If `.clavain/` doesn't exist, run `/clavain:clavain-init`.

### 3c: CLAUDE.md

If `CLAUDE.md` doesn't exist, generate from `templates/CLAUDE.md.tmpl`.

Fill `{{PLACEHOLDERS}}` from interview answers and introspection:
- `{{PROJECT_NAME}}` — from Q1 or inferred
- `{{PROJECT_DESCRIPTION}}` — from Q1
- `{{PROJECT_STRUCTURE}}` — from filesystem scan (list top-level dirs with brief descriptions)

Target: 30-60 lines. Operations and pointers only — no architecture (that's AGENTS.md).

### 3d: AGENTS.md

If `AGENTS.md` doesn't exist, generate from `templates/AGENTS.md.tmpl`.

Fill placeholders:
- `{{PROJECT_NAME}}`, `{{PROJECT_DESCRIPTION}}` — from Q1
- `{{DIRECTORY_LAYOUT}}` — from filesystem scan (table format)
- `{{BUILD_TEST_COMMANDS}}` — from Q5
- `{{CODING_CONVENTIONS}}` — language-appropriate defaults (e.g., Go: gofmt, error wrapping; Rust: clippy, rustfmt; Python: ruff, type hints; TypeScript: strict mode, prettier)
- `{{DEPENDENCIES}}` — from manifest files

### 3e: PHILOSOPHY.md

If `PHILOSOPHY.md` doesn't exist, generate from `templates/PHILOSOPHY.md.tmpl`.

Fill from Q4 (key goals) → design principles.

### 3f: CONVENTIONS.md

If `CONVENTIONS.md` doesn't exist, generate from `templates/CONVENTIONS.md.tmpl`.

Fill `{{PROJECT_SLUG}}` from project name (lowercase, hyphenated).

### 3g: Docs Tree

Create all missing directories:

```bash
for d in brainstorms plans research guides canon prd prds cujs \
         solutions/patterns solutions/best-practices solutions/runtime-errors \
         audits diagrams migrations policies reports traces; do
    mkdir -p "docs/$d"
done
```

## Phase 4: Observability

### 4a: Interwatch

If `.interwatch/` doesn't exist, create from templates:

```bash
mkdir -p .interwatch
# Copy templates/watchables.yaml.tmpl to .interwatch/watchables.yaml
# Copy templates/project.yaml.tmpl to .interwatch/project.yaml
```

Always generate `.interwatch/project.yaml` from `templates/project.yaml.tmpl`:
- `{{PROJECT_NAME}}` — from Q1 or inferred
- `{{ROADMAP_SCAN_DIRS}}` — from Q6 (monorepo) or empty list (single project)

If `.interwatch/project.yaml` already exists, merge new values without overwriting existing config.

### 4b: Intertree

Register project in intertree hierarchy if interkasten MCP tools are available. Skip silently if not.

## Phase 5: Content Seeding

Use Q4 (key goals) to generate real content:

1. **Brainstorm** — write `docs/brainstorms/YYYY-MM-DD-<project>-initial-goals.md` from key goals
2. **Vision** — run `/interpath:vision` (reads brainstorm)
3. **PRD** — run `/interpath:prd` (reads brainstorm + vision)
4. **Roadmap** — run `/interpath:roadmap` (reads beads)
5. **CUJs** — run `/interpath:cuj` for each critical user-facing flow identified in the PRD. Required for any project with user-facing flows. Skip only for pure libraries or internal infrastructure.
6. **Initial beads** — create epic from project goals, features from PRD:

```bash
bd create --title="<project>: initial setup and first features" --type=epic --priority=1
# For each feature from PRD:
bd create --title="F1: <feature name>" --type=feature --priority=2
bd dep add <feature-id> <epic-id>
```

## Phase 6: Verify & Report

Present final status. List everything that was created or already existed. Include next steps:

```
Next steps:
  /clavain:brainstorm — explore your first feature
  /clavain:sprint — full development lifecycle
  /interwatch:watch — check doc health
  bd ready — see available work
```
