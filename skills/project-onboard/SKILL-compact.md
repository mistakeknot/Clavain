# Project Onboard (compact)

One-command project setup. Repo Setup → Handoff Ingest → Introspect → Interview → Scaffold → Observe → Seed → Verify.

Safe to re-run (idempotent). Works for both new and existing projects.

## Invocation

- Bare: `/clavain:project-onboard`
- With handoff/brief doc: `/clavain:project-onboard --from=PATH.md`

## Phase 0: Repository Setup (new projects only)

If not in a git repo, run `git init`. If no remote, offer to create one via `gh repo create mistakeknot/<name> --private` or let user provide a URL. Skip entirely if remote already exists.

## Phase 0.5: Handoff Doc Ingestion

If `--from=PATH.md` was passed, use that. Else auto-detect by globbing for `*HANDOFF*.md`, `*BRIEF*.md`, `*PITCH*.md`, `*ONEPAGER*.md`, `*PRD*.md`, `*SPEC*.md` (case-insensitive). One match → confirm; multiple → list and pick; none → skip.

Heuristic-parse for: Q0 mission (thesis/pitch section), Q1 name+one-liner (H1 + tagline), Q2 stack, Q3 project type, Q4 goals (Phase plan / Roadmap / MVP), Q5 build, Q7 personas (Audience/Users/Personas), Q8 pain (Problem/Why/Motivation).

Show extracted summary, let user accept/edit/skip per field. Accepted fields skip their question in Phase 2.

## Phase 1: Introspect

Scan for: git remote, .beads/, .clavain/, .interwatch/, MISSION.md, CLAUDE.md, AGENTS.md, PHILOSOPHY.md, CONVENTIONS.md, docs/canon/personas.md, docs/ subdirs, languages (from manifests/extensions), project name (from manifest/remote/dirname), project type (monorepo/library/app/plugin).

Report ✔/✖ checklist to user.

## Phase 2: Guided Interview

Use AskUserQuestion. Skip questions answered by introspection or pre-filled in Phase 0.5.

- **Q0**: Mission statement — one sentence (skip if MISSION.md exists)
- **Q1**: Project name + one-liner (skip if inferred)
- **Q2**: Languages/frameworks (skip if detected)
- **Q3**: Project type (skip if inferred)
- **Q4**: Key goals for next month (always ask)
- **Q5**: Build/test commands (always ask, show inferred default)
- **Q6**: Roadmap module dirs (monorepo only — auto-detect dirs with plugin.json/CLAUDE.md subdirs)
- **Q7**: 1–3 primary personas (name + one-line context each — lightweight; deep JTBD deferred to follow-up bead)
- **Q8**: Core pain point per persona (one sentence each)

## Phase 3: Scaffold

Skip anything that exists. Execute in order:

1. `bd init` + `bd setup claude --project` (if no .beads/)
2. `/clavain:clavain-init` (if no .clavain/)
3. Generate MISSION.md from `templates/MISSION.md.tmpl` (Q0 → one-sentence mission)
4. Generate CLAUDE.md from `templates/CLAUDE.md.tmpl` (30-60 lines, operations only)
5. Generate AGENTS.md from `templates/AGENTS.md.tmpl` (architecture, build, conventions)
6. Generate PHILOSOPHY.md from `templates/PHILOSOPHY.md.tmpl` (mission + goals → principles)
7. Generate CONVENTIONS.md from `templates/CONVENTIONS.md.tmpl` (canonical doc paths)
8. Create full docs/ tree: brainstorms, plans, research, guides, canon, prd, prds, cujs, solutions/{patterns,best-practices,runtime-errors}, audits, diagrams, migrations, policies, reports, traces
9. Generate `docs/canon/personas.md` from `templates/personas.md.tmpl` (Q7+Q8)

## Phase 4: Observability

1. Create `.interwatch/watchables.yaml` from template (AGENTS.md 14d, roadmap 30d, philosophy 90d)
2. Create `.interwatch/project.yaml` from template (project name from Q1, scan_dirs from Q6)
3. Register in intertree (skip silently if unavailable)

## Phase 5: Content Seeding

From Q4 (key goals) and `docs/canon/personas.md`:

1. Write brainstorm doc to `docs/brainstorms/`
2. `/interpath:vision` (reads MISSION.md + personas + brainstorm)
3. `/interpath:prd` (reads brainstorm + vision + personas)
4. `/interpath:roadmap`
5. `/interpath:cuj` (one per critical user-facing flow from PRD — required for user-facing projects, skip for pure libraries/infra)
6. Create initial beads (epic + features from PRD)
7. Create follow-up beads (idempotent — skip if duplicate title exists):
   - `Deep persona interview (JTBD per persona)` — task, P3
   - `Migrate MISSION/PHILOSOPHY/CONVENTIONS into docs/canon/` — task, P4

## Phase 6: Verify & Report

Present status of everything created/existing. Show next steps: `/clavain:brainstorm`, `/clavain:sprint`, `/interwatch:watch`, `bd ready`.

---

*For detailed introspection logic, template placeholders, and language-specific conventions, read SKILL.md.*
