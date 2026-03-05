# Project Onboard (compact)

One-command project setup. Introspect → Interview → Scaffold → Observe → Seed → Verify.

Safe to re-run (idempotent). Must be in a git repo.

## Phase 1: Introspect

Scan for: git remote, .beads/, .clavain/, .interwatch/, CLAUDE.md, AGENTS.md, PHILOSOPHY.md, CONVENTIONS.md, docs/ subdirs, languages (from manifests/extensions), project name (from manifest/remote/dirname), project type (monorepo/library/app/plugin).

Report ✔/✖ checklist to user.

## Phase 2: Guided Interview

Use AskUserQuestion. Skip questions answered by introspection.

- **Q1**: Project name + one-liner (skip if inferred)
- **Q2**: Languages/frameworks (skip if detected)
- **Q3**: Project type (skip if inferred)
- **Q4**: Key goals for next month (always ask)
- **Q5**: Build/test commands (always ask, show inferred default)

## Phase 3: Scaffold

Skip anything that exists. Execute in order:

1. `bd init` + `bd setup claude --project` (if no .beads/)
2. `/clavain:init` (if no .clavain/)
3. Generate CLAUDE.md from `templates/CLAUDE.md.tmpl` (30-60 lines, operations only)
4. Generate AGENTS.md from `templates/AGENTS.md.tmpl` (architecture, build, conventions)
5. Generate PHILOSOPHY.md from `templates/PHILOSOPHY.md.tmpl` (goals → principles)
6. Generate CONVENTIONS.md from `templates/CONVENTIONS.md.tmpl` (canonical doc paths)
7. Create full docs/ tree: brainstorms, plans, research, guides, canon, prd, prds, cujs, solutions/{patterns,best-practices,runtime-errors}, audits, diagrams, migrations, policies, reports, traces

## Phase 4: Observability

1. Create `.interwatch/watchables.yaml` from template (AGENTS.md 14d, roadmap 30d, philosophy 90d)
2. Register in intertree (skip silently if unavailable)

## Phase 5: Content Seeding

From Q4 (key goals):

1. Write brainstorm doc to `docs/brainstorms/`
2. `/interpath:vision`
3. `/interpath:prd`
4. `/interpath:roadmap`
5. `/interpath:cuj` (one per critical user-facing flow from PRD — required for user-facing projects, skip for pure libraries/infra)
6. Create initial beads (epic + features from PRD)

## Phase 6: Verify & Report

Present status of everything created/existing. Show next steps: `/clavain:brainstorm`, `/clavain:sprint`, `/interwatch:watch`, `bd ready`.

---

*For detailed introspection logic, template placeholders, and language-specific conventions, read SKILL.md.*
