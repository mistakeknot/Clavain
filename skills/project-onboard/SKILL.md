---
name: project-onboard
description: Use when setting up any project (new or existing) in the Demarch ecosystem — introspects infrastructure, creates GitHub repo if needed, conducts guided interview, scaffolds docs and automation, configures observability, seeds content via interpath. Replaces the former project-kickstart command.
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. -->

# Project Onboard

One-command project setup. Idempotent — skips what already exists.
**Announce at start:** "I'm using the project-onboard skill to set up this project."

## Preconditions

```bash
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
[[ -z "$GIT_ROOT" ]] && git init && GIT_ROOT=$(pwd)
cd "$GIT_ROOT"
```
Check `command -v bd` — if missing, warn and skip beads steps.

## Phase 0: Repository Setup (new projects only)

Skip if `git remote get-url origin` succeeds. If no remote:
1. Ask: create via `gh repo create mistakeknot/<name> --private --description "<one-liner>"`, or user provides URL.
2. `git remote add origin <url>`

## Phase 1: Introspect

Check ✔/✖ for each:
- **Infrastructure:** git remote, `.beads/`, `.clavain/`, `.interwatch/`
- **Core docs:** `CLAUDE.md`, `AGENTS.md`, `PHILOSOPHY.md`, `CONVENTIONS.md`
- **Docs tree:** `brainstorms plans research guides canon prd prds solutions audits diagrams migrations policies reports traces`

**Language detection:** `go.mod`→Go, `Cargo.toml`→Rust, `package.json`→JS/TS (`tsconfig.json` distinguishes TS), `pyproject.toml`/`setup.py`→Python, `*.java` in `src/`→Java.

**Project name** (first match): `package.json`.name → `Cargo.toml` [package] name → `go.mod` last segment → `pyproject.toml` [project] name → git remote basename → cwd name.

**Project type:** multiple manifests or top-level dirs with own manifests→monorepo; `.claude-plugin/`→plugin; `lib.rs`/`src/index.ts` no app/pages→library; `main.go`/`cmd/`/`Dockerfile`/`app/`/`pages/`→application; default: application.

Present checklist summary, e.g.: `myproject (Rust application) — ✖ .beads/ ✖ CLAUDE.md ...`

## Phase 2: Guided Interview

Use **AskUserQuestion**. Skip if already inferred.

- **Q1** (skip if inferred): Name and one-liner.
- **Q2** (skip if detected): Languages and frameworks.
- **Q3** (skip if inferred): Project type (Library/Application/Monorepo/Plugin).
- **Q4** (always): Key goals for next month. Seeds brainstorm, vision, PRD, roadmap.
- **Q5** (always): How is it built and tested? Infer defaults from Makefile/package.json/Cargo/etc.
- **Q6** (monorepo only): Which top-level dirs contain modules for the roadmap? Auto-detect dirs with `.claude-plugin/plugin.json` or `CLAUDE.md`. Store as `roadmap_scan_dirs` for Phase 4a.

## Phase 3: Scaffold Infrastructure

Execute in order; skip existing.

**3a: Beads** — if `.beads/` missing and `bd` available: `bd init && bd setup claude --project`

**3b: Clavain Memory** — if `.clavain/` missing: run `/clavain:clavain-init`

**3c: CLAUDE.md** — if missing, generate from `templates/CLAUDE.md.tmpl`. Fill: `{{PROJECT_NAME}}`, `{{PROJECT_DESCRIPTION}}`, `{{PROJECT_STRUCTURE}}`. Target 30-60 lines — operations/pointers only.

**3d: AGENTS.md** — if missing, generate from `templates/AGENTS.md.tmpl`. Fill: `{{PROJECT_NAME}}`, `{{PROJECT_DESCRIPTION}}`, `{{DIRECTORY_LAYOUT}}` (table), `{{BUILD_TEST_COMMANDS}}` (from Q5), `{{CODING_CONVENTIONS}}` (language defaults), `{{DEPENDENCIES}}` (from manifests).

**3e: PHILOSOPHY.md** — if missing, generate from template. Fill from Q4 → design principles.

**3f: CONVENTIONS.md** — if missing, generate from template. Fill `{{PROJECT_SLUG}}` (lowercase, hyphenated).

**3g: Docs Tree**
```bash
for d in brainstorms plans research guides canon prd prds cujs \
         solutions/patterns solutions/best-practices solutions/runtime-errors \
         audits diagrams migrations policies reports traces; do
    mkdir -p "docs/$d"
done
```

## Phase 4: Observability

**4a: Interwatch** — if `.interwatch/` missing, create from templates. Always generate `.interwatch/project.yaml` with `{{PROJECT_NAME}}` and `{{ROADMAP_SCAN_DIRS}}` (Q6 or empty). Merge without overwriting if file already exists.

**4b: Intertree** — register in intertree hierarchy if interkasten MCP tools available; skip silently if not.

## Phase 5: Content Seeding

Using Q4 (key goals):
1. Write `docs/brainstorms/YYYY-MM-DD-<project>-initial-goals.md`
2. Run `/interpath:vision` (reads brainstorm)
3. Run `/interpath:prd` (reads brainstorm + vision)
4. Run `/interpath:roadmap` (reads beads)
5. Run `/interpath:cuj` for each critical user-facing flow from the PRD. Skip only for pure libraries or internal infra.
6. Create beads:
```bash
bd create --title="<project>: initial setup and first features" --type=epic --priority=1
# For each feature from PRD:
bd create --title="F1: <feature name>" --type=feature --priority=2
bd dep add <feature-id> <epic-id>
```

## Phase 6: Verify & Report

List everything created or already-existing. Include next steps:
```
/clavain:brainstorm — explore your first feature
/clavain:sprint — full development lifecycle
/interwatch:watch — check doc health
bd ready — see available work
```
