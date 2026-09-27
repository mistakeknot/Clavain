# Engineering Docs (compact)

Document solved problems as searchable institutional knowledge with YAML frontmatter and category-based organization.

## When to Invoke

After confirmation phrases ("that worked", "it's fixed", "problem solved") or via `/clavain:compound`. **Non-trivial problems only** — skip typos, obvious syntax errors, trivial fixes, and anything the final code already makes impossible or obvious to repeat. **One learning per run**: never batch several problems into one doc; run once per problem.

## Algorithm

### Step 1: Gather Context

Extract from conversation: module name, symptom (exact error messages), investigation attempts, root cause, solution, prevention guidance, environment details.

**If critical context missing:** Ask user and WAIT before proceeding.

### Step 2: Check Existing Docs

Search `docs/solutions/` for similar issues. If found, present options: create new with cross-reference (recommended), update existing (same root cause or now materially wrong), or other.

### Step 3: Generate Filename

Format: `[sanitized-symptom]-[module]-[YYYYMMDD].md` (lowercase, hyphens, <80 chars).

### Step 4: Validate YAML (BLOCKING)

Validate frontmatter against schema in `references/yaml-schema.md`. All required fields present, enum values match exactly. **BLOCK until valid.**

### Step 5: Create Documentation

Map `problem_type` to category directory (mapping in `references/yaml-schema.md` lines 49-61). Write to `docs/solutions/${CATEGORY}/${FILENAME}` using template from `assets/resolution-template.md`.

### Step 6: Cross-Reference

If similar issues exist, add bidirectional links. If 3+ similar issues, add pattern to `docs/solutions/patterns/common-solutions.md`.

### Step 7: Vocabulary Capture

Update the nearest existing glossary (`docs/glossary.md`, `GLOSSARY.md`, `CONCEPTS.md`, checking parent directories up to the workspace root), matching its format. Only if none exists and the learning surfaced a qualifying term, create `CONCEPTS.md` seeded with this learning's area only. Mutations: add, refine, fold, and scrub entries this run touched; entries carry no paths or config values. Apply silently and report `Vocabulary (<file>): not present | scanned, no qualifying terms | updated — N added, N refined, N folded, N scrubbed`. Rules: `references/vocabulary-capture.md`.

### Step 8: Decision Menu

Present the vocabulary line, then options: (1) Continue workflow, (2) Add to Required Reading (critical-patterns.md), (3) Link related issues, (4) Add to existing skill, (5) Create new skill, (6) View documentation.

## Quality Checklist

Required: exact error messages, file:line references, failed attempts, technical explanation, code examples, prevention guidance, cross-references.

---

*For YAML schema details, resolution template, or critical pattern template, read references/ and assets/ directories.*
