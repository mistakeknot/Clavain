# Vocabulary Capture

Adapted from compound-engineering `ce-compound` (v3.29.0, `references/concepts-vocabulary.md`). Runs in engineering-docs after the learning is written, before the decision menu.

## Target file

Use the project's existing glossary: `docs/glossary.md`, `GLOSSARY.md`, or `CONCEPTS.md`, in that order. When the repo sits inside a larger workspace, also look in parent directories up to the workspace root and use the nearest glossary found. Never start a second glossary beside an existing one. When none exists, create `CONCEPTS.md` at the repo root, but only if this learning surfaced at least one qualifying term. Seed it with that learning's area only; do not survey the whole project.

## What qualifies

A term qualifies when the learning depended on it and a future reader could misread it: a project-specific name for a concept, a word used in a narrower sense than usual, or two names in use for one thing. Generic engineering vocabulary does not qualify.

## Entry shape

Match the existing file's format (bullets, tables or headings). For a new file use:

- **Term** — one-sentence definition that stands alone.
  Optional short paragraph of rules or boundaries.
  *Avoid:* aliases that mean the same thing and should not be used.

Entries hold no file paths, class names, or current config values; those go stale and belong in the learning doc. Keep any "Flagged ambiguities" and "Retired" sections at the end of the file.

## Allowed mutations

A capture run may only:

- **add** a new qualifying term;
- **refine** an existing definition the learning showed to be incomplete or wrong;
- **fold** a duplicate name into the canonical entry and list it under *Avoid:*;
- **scrub** paths, class names or config values from entries this run adds or refines.

Retiring or deleting entries is a deliberate glossary edit, not part of capture. After any change, reread the neighbouring entries that mention the changed term and keep them consistent.

## Apply and report

Apply the edits without a confirmation prompt, then report one line:

`Vocabulary (<file>): not present | scanned, no qualifying terms | updated — N added, N refined, N folded, N scrubbed`
