---
name: project-onboard
description: Use to set up any Sylveste project (new or existing) — introspects, creates repo, scaffolds docs/automation/observability, seeds via interpath.
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. -->

# Project Onboard

One-command project setup. Idempotent — skips what already exists.
**Announce at start:** "I'm using the project-onboard skill to set up this project."

## Invocation

- Bare: `/clavain:project-onboard`
- With handoff/brief doc: `/clavain:project-onboard --from=PATH.md`

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

## Phase 0.5: Handoff Doc Ingestion

If `--from=PATH.md` was passed, use that file. Otherwise, **auto-detect** by globbing the repo root for any of:
`*HANDOFF*.md`, `*BRIEF*.md`, `*PITCH*.md`, `*ONEPAGER*.md`, `*PRD*.md`, `*SPEC*.md` (case-insensitive).

If exactly one match: ask the user `"Found <file>. Use it to pre-fill onboarding answers? [Y/n]"`. If multiple: list them and ask which (or none). If none: skip Phase 0.5 entirely.

When a handoff doc is in play, parse it for the following — heuristic, best-effort, never block on a missing section:

| Maps to | Look for |
|---|---|
| Q0 mission | First section/paragraph that reads as a thesis or one-line pitch ("# Pitch", "## The pitch", "## Mission", first `>` blockquote near the top) |
| Q1 name + one-liner | H1 of the doc; tagline/one-liner if present |
| Q2 languages | "Stack", "Tech", "Technical considerations" sections |
| Q3 project type | Inferred from stack section + the words "library/app/CLI/plugin" |
| Q4 key goals | "Phase plan", "Roadmap", "Goals", "MVP", "Phase 1" sections — extract bullet lists |
| Q5 build/test | "Build", "Run", "Setup", "Getting started" sections |
| Q7 personas | "Audience", "Users", "Personas", "Who this is for" sections |
| Q8 pain points | "Problem", "Why", "Motivation", "Pitch" — pull pain framing |

Store extracted answers as `prefilled` map. **Show the user a summary of what was extracted before scaffolding**:

```
From SOLWEND_HANDOFF.md, I extracted:
  Q0 mission: "A walking app that routes for human comfort and aesthetic experience..."
  Q1 name: Solwend  one-liner: "Walking directions calibrated to shade, weather, and checkpoints"
  Q4 goals: [DTLA shadow spike, comfort score + checkpoints, cafe-finder flow]
  Q7 personas: not found — will ask
  ...
Use these? [Y/edit/skip]
```

User may accept, edit any field, or skip the handoff entirely. Accepted fields skip their question in Phase 2.

## Phase 1: Introspect

Check ✔/✖ for each:
- **Infrastructure:** git remote, `.beads/`, `.clavain/`, `.interwatch/`
- **Core docs:** `MISSION.md`, `CLAUDE.md`, `AGENTS.md`, `PHILOSOPHY.md`, `CONVENTIONS.md`
- **Docs tree:** `brainstorms plans research guides canon prd prds solutions audits diagrams migrations policies reports traces`

**Language detection:** `go.mod`→Go, `Cargo.toml`→Rust, `package.json`→JS/TS (`tsconfig.json` distinguishes TS), `pyproject.toml`/`setup.py`→Python, `*.java` in `src/`→Java.

**Project name** (first match): `package.json`.name → `Cargo.toml` [package] name → `go.mod` last segment → `pyproject.toml` [project] name → git remote basename → cwd name.

**Project type:** multiple manifests or top-level dirs with own manifests→monorepo; `.claude-plugin/`→plugin; `lib.rs`/`src/index.ts` no app/pages→library; `main.go`/`cmd/`/`Dockerfile`/`app/`/`pages/`→application; default: application.

Present checklist summary, e.g.: `myproject (Rust application) — ✖ .beads/ ✖ CLAUDE.md ...`

## Phase 2: Guided Interview

Use **AskUserQuestion**. Skip if already inferred or pre-filled from Phase 0.5.

- **Q0** (skip if `MISSION.md` exists): "What is this project's mission? One sentence — the outcome it exists to create." This becomes the content of `MISSION.md`.
- **Q1** (skip if inferred): Name and one-liner.
- **Q2** (skip if detected): Languages and frameworks.
- **Q3** (skip if inferred): Project type (Library/Application/Monorepo/Plugin).
- **Q4** (always): Key goals for next month. Seeds brainstorm, vision, PRD, roadmap.
- **Q5** (always): How is it built and tested? Infer defaults from Makefile/package.json/Cargo/etc.
- **Q6** (monorepo only): Which top-level dirs contain modules for the roadmap? Auto-detect dirs with `.claude-plugin/plugin.json` or `CLAUDE.md`. Store as `roadmap_scan_dirs` for Phase 4a.
- **Q7** (always): Who are the 1–3 primary personas? For each: a name/label + one-line context (role, goal in using this product). Lightweight here — a deeper JTBD interview is filed as a follow-up bead in Phase 5.
- **Q8** (always): For each persona from Q7, what is their core pain point in one sentence — what hurts today that this product addresses?

**Stop after Q8.** The deep persona interview (workaround, frustration, success state, anti-personas) is intentionally deferred. Phase 5 will create a follow-up bead to run it.

## Phase 3: Scaffold Infrastructure

Execute in order; skip existing.

**3a: Beads** — if `.beads/` missing and `bd` available: `bd init && bd setup claude --project`

**3b: Clavain Memory** — if `.clavain/` missing: run `/clavain:clavain-init`

**3c: MISSION.md** — if missing and Q0 was answered, generate from `templates/MISSION.md.tmpl`. Fill: `{{PROJECT_NAME}}`, `{{MISSION_STATEMENT}}` (from Q0), `{{MISSION_ELABORATION}}` (brief expansion of what this means in practice). Must come before PHILOSOPHY.md — philosophy derives principles from the mission.

**3d: CLAUDE.md** — if missing, generate from `templates/CLAUDE.md.tmpl`. Fill: `{{PROJECT_NAME}}`, `{{PROJECT_DESCRIPTION}}`, `{{PROJECT_STRUCTURE}}`. Target 30-60 lines — operations/pointers only.

**3e: AGENTS.md** — if missing, generate from `templates/AGENTS.md.tmpl`. Fill: `{{PROJECT_NAME}}`, `{{PROJECT_DESCRIPTION}}`, `{{DIRECTORY_LAYOUT}}` (table), `{{BUILD_TEST_COMMANDS}}` (from Q5), `{{CODING_CONVENTIONS}}` (language defaults), `{{DEPENDENCIES}}` (from manifests).

**3f: PHILOSOPHY.md** — if missing, generate from template. Fill from Q4 → design principles. If `MISSION.md` exists, derive principles from the mission.

**3g: CONVENTIONS.md** — if missing, generate from template. Fill `{{PROJECT_SLUG}}` (lowercase, hyphenated).

**3h: Docs Tree**
```bash
for d in brainstorms plans research guides canon prd prds cujs \
         solutions/patterns solutions/best-practices solutions/runtime-errors \
         audits diagrams migrations policies reports traces; do
    mkdir -p "docs/$d"
done
```

**3i: Personas** — if `docs/canon/personas.md` missing and Q7+Q8 were answered, generate from `templates/personas.md.tmpl`. Fill:
- `{{PROJECT_NAME}}`
- `{{PERSONAS_BLOCK}}`: one `### <Name>` heading per persona with the one-line context underneath
- `{{PAIN_POINTS_BLOCK}}`: one bullet per persona, format: `- **<Name>:** <pain sentence>`

Personas live in `docs/canon/` because they are durable canonical knowledge that the PRD, vision, and CUJ docs all read from.

## Phase 4: Observability

**4a: Interwatch** — if `.interwatch/` missing, create from templates. Always generate `.interwatch/project.yaml` with `{{PROJECT_NAME}}` and `{{ROADMAP_SCAN_DIRS}}` (Q6 or empty). Merge without overwriting if file already exists.

**4b: Intertree** — register in intertree hierarchy if interkasten MCP tools available; skip silently if not.

## Phase 5: Content Seeding

Using Q4 (key goals) and `docs/canon/personas.md` (from Phase 3i):
1. Write `docs/brainstorms/YYYY-MM-DD-<project>-initial-goals.md`
2. Run `/interpath:vision` (reads MISSION.md + personas + brainstorm)
3. Run `/interpath:prd` (reads brainstorm + vision + personas)
4. Run `/interpath:roadmap` (reads beads)
5. Run `/interpath:cuj` for each critical user-facing flow from the PRD. Skip only for pure libraries or internal infra.
6. Create the epic + feature beads:
```bash
bd create --title="<project>: initial setup and first features" --type=epic --priority=1
# For each feature from PRD:
bd create --title="F1: <feature name>" --type=feature --priority=2
bd dep add <feature-id> <epic-id>
```
7. Create **follow-up onboarding beads** (always, idempotent — skip if a bead with the same title already exists):
```bash
bd create --title="Deep persona interview (JTBD per persona)" --type=task --priority=3 \
  --description="Lightweight personas were captured during onboarding in docs/canon/personas.md. Run a deeper Jobs-to-be-Done interview per persona: current workaround, frustration, success state, anti-personas. Update docs/canon/personas.md in place."

bd create --title="Migrate MISSION/PHILOSOPHY/CONVENTIONS into docs/canon/" --type=task --priority=4 \
  --description="MISSION.md, PHILOSOPHY.md, and CONVENTIONS.md currently live at repo root. They are canonical, slowly-changing knowledge — they belong in docs/canon/. CLAUDE.md and AGENTS.md must stay at root (harness auto-load). Migration touches every consumer of these paths (interpath:vision, PHILOSOPHY generation, etc.) — coordinate before flipping."
```

## Phase 6: Verify & Report

List everything created or already-existing. Include next steps:
```
/clavain:brainstorm — explore your first feature
/clavain:sprint — full development lifecycle
/interwatch:watch — check doc health
bd ready — see available work
```
