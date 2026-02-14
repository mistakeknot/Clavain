---
name: init
description: Scaffold .clavain/ agent memory directory in the current project
argument-hint: ""
disable-model-invocation: false
---

# /init

Scaffold the `.clavain/` agent memory filesystem in the current git repository. This creates a per-project directory contract for durable knowledge, ephemeral working state, and API contracts.

## Execution

1. **Determine the git repository root:**

```bash
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [[ -z "$GIT_ROOT" ]]; then
    echo "ERROR: Not in a git repository. /clavain:init requires git."
    exit 1
fi
```

2. **Create directory structure** (at `$GIT_ROOT/.clavain/`):

```
.clavain/
├── learnings/          # Curated durable knowledge (committed)
├── scratch/            # Ephemeral state (gitignored)
│   └── runs/           # Future: run manifests
└── contracts/          # API contracts, invariants (committed)
```

Use `mkdir -p` for each directory. Do NOT create files that already exist.

3. **Add `.clavain/scratch/` to `.gitignore`** (duplicate-safe):

```bash
if ! grep -qF '.clavain/scratch/' "$GIT_ROOT/.gitignore" 2>/dev/null; then
    echo '.clavain/scratch/' >> "$GIT_ROOT/.gitignore"
fi
```

4. **Create `.clavain/README.md`** (only if it doesn't exist) with:

```markdown
# .clavain/

Agent memory filesystem for this project. Created by `/clavain:init`.

## Directories

- **learnings/** — Curated durable knowledge. YAML frontmatter + markdown body. Feeds into review agents.
- **scratch/** — Ephemeral working state (gitignored). Session handoffs, run checkpoints.
- **contracts/** — API contracts, invariants, SLOs. Read by interflux:fd-correctness and interflux:fd-safety during reviews.

## Gitignore

`scratch/` is gitignored. Everything else is committed and travels with the repo.

## Extension Points

Downstream features add their own subdirectories:
- `scenarios/` — holdout scenario bank
- `pipelines/` — graph pipeline definitions
- `provenance/` — agent run manifests
```

5. **Report what was created:**

```
.clavain/ initialized at $GIT_ROOT
  learnings/    — durable project knowledge
  scratch/      — ephemeral state (gitignored)
  contracts/    — API contracts and invariants
```

## Idempotency

This command is safe to re-run. It only creates directories and files that don't already exist, and only appends to `.gitignore` if the entry is missing.
