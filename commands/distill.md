---
name: distill
description: Synthesize accumulated docs into categorized solutions and generate missing SKILL-compact.md files
argument-hint: "[--mode interactive|batch] [--scope compound|reflect|research|skills|all]"
---

# Knowledge Distillation

Synthesize accumulated documentation into categorized `docs/solutions/` entries, generate missing SKILL-compact.md files, and archive processed originals.

## Input

<input_args> #$ARGUMENTS </input_args>

Parse arguments:
- `--mode`: `interactive` (default, guided with approvals) or `batch` (automated, review gate at end)
- `--scope`: What to distill. Default `all`. Options:
  - `compound` — Only compound/reflect docs → solutions
  - `research` — Only research docs → solutions
  - `skills` — Only generate missing SKILL-compact.md
  - `all` — Everything

## Phase 1: Discovery

Scan for unprocessed documents:

1. **Compound & reflect docs** — Find docs in `docs/solutions/` that don't have `synthesized_into` in frontmatter AND were created >7 days ago (let fresh docs settle)
2. **Research docs** — Find docs in `docs/research/` that share topics with existing solutions (potential synthesis candidates)
3. **Skills without compact** — Find SKILL.md files that lack a companion SKILL-compact.md

```bash
# Discovery counts
echo "=== Distillation Candidates ==="
echo "Compound/reflect docs: $(grep -rL 'synthesized_into' docs/solutions/ --include='*.md' | wc -l)"
echo "Research docs: $(find docs/research -name '*.md' | wc -l)"
echo "Skills without compact: $(for d in os/clavain/skills/*/; do [ ! -f "${d}SKILL-compact.md" ] && [ -f "${d}SKILL.md" ] && echo "$d"; done | wc -l)"
```

Present discovery results to user. If `--mode interactive`, ask which categories to proceed with.

## Phase 2: Clustering (compound/research scope)

Group related documents by topic:

1. Extract keywords from each document's title, tags, and first 5 lines
2. Use `Grep` to find documents sharing 2+ keywords
3. Present clusters to user:
   ```
   Cluster 1: "Plugin Loading" (3 docs)
     - docs/solutions/integration-issues/plugin-loading-failures-interverse-20260215.md
     - docs/solutions/patterns/plugin-validation-errors-20260222.md
     - docs/research/plugin-cache-staleness-analysis.md

   Cluster 2: "WAL Protocol" (2 docs)
     - docs/solutions/patterns/wal-protocol-completeness-20260216.md
     - docs/research/intercore-wal-edge-cases.md
   ```
4. If `--mode interactive`: ask user to approve/edit clusters before synthesis
5. If `--mode batch`: proceed with all clusters that have 2+ documents

## Phase 3: Synthesis (compound/research scope)

For each approved cluster:

1. Spawn `Task(subagent_type="intersynth:synthesize-documents")` with:
   - All documents in the cluster (read contents)
   - Existing docs/solutions/ entries with overlapping tags (for dedup)
   - The target category (inferred from cluster content)
2. Review synthesis output:
   - If `--mode interactive`: present each synthesized doc for approval
   - If `--mode batch`: collect all, present summary for batch approval
3. Write approved docs to `docs/solutions/[category]/`
4. Update source document frontmatter with `synthesized_into: [path to new solution doc]`

## Phase 4: SKILL Compact Generation (skills scope)

For each skill missing a SKILL-compact.md:

1. Read the full SKILL.md
2. If the skill is <60 lines: skip (already compact enough)
3. Generate compact version following the established pattern:
   - Keep: core workflow steps, key rules, quick commands
   - Remove: examples, edge cases, detailed explanations, integration tables
   - Add footer: `*For [details removed], read SKILL.md.*`
   - Target: 30-60 lines (70-85% reduction)
4. Write to `[skill-dir]/SKILL-compact.md`
5. If `--mode interactive`: present each compact for approval

## Phase 5: Summary

Present distillation results:

```
=== Distillation Complete ===
Synthesized: 3 clusters → 3 new docs/solutions/ entries
Archived: 7 source docs marked with synthesized_into
Compacted: 4 new SKILL-compact.md files
Token savings: ~X lines removed from active context
```

If `--mode batch`: present all changes for final approval before committing.

## Commit

```bash
git add docs/solutions/ os/clavain/skills/*/SKILL-compact.md
git commit -m "docs: distill accumulated knowledge into solutions and compact skills"
```
