# Vocabulary Capture

Adapted from compound-engineering `ce-compound` (v3.29.0, `references/concepts-vocabulary.md`). Runs as Step 8 of engineering-docs, after the learning is written.

## Target file

Use the project's existing glossary: `docs/glossary.md`, `GLOSSARY.md`, or `CONCEPTS.md`, in that order. Never start a second glossary beside an existing one. When none exists, create `CONCEPTS.md` at the repo root, but only if this learning surfaced at least one qualifying term. Seed it with that learning's area only; do not survey the whole project.

## What qualifies

A term qualifies when the learning depended on it and a future reader could misread it: a project-specific name for a concept, a word used in a narrower sense than usual, or two names in use for one thing. Generic engineering vocabulary does not qualify.

## Entry shape

- **Term** — one-sentence definition that stands alone.
  Optional short paragraph of rules or boundaries.
  *Avoid:* aliases that mean the same thing and should not be used.

Entries hold no file paths, class names, or current config values; those go stale and belong in the learning doc. Keep any "Flagged ambiguities" and "Retired" sections at the end of the file.

## Allowed mutations

A capture run may only:

- **add** a new qualifying term;
- **refine** an existing definition the learning showed to be incomplete or wrong;
- **fold** a duplicate name into the canonical entry and list it under *Avoid:*;
- **scrub** paths, class names or config values that leaked into an entry.

Retiring or deleting entries is a deliberate glossary edit, not part of capture. After any change, reread the neighbouring entries that mention the changed term and keep them consistent.

## Apply and report

Apply the edits without a confirmation prompt, then report one line:

`Vocabulary (<file>): not present | scanned, no qualifying terms | updated — N added, N refined, N folded, N scrubbed`
