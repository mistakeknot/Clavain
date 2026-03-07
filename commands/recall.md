---
name: recall
description: Search across all knowledge systems — curated docs, memory files, legacy entries
argument-hint: "<query>"
disable-model-invocation: false
---

# /recall

Unified retrieval across C4 (curated knowledge) and C5 (ephemeral memory) systems. Returns ranked, deduplicated results with source attribution.

## Context

<context> #$ARGUMENTS </context>

## Sources

| Source | Layer | Path | Format |
|--------|-------|------|--------|
| Compound docs | C4 | `docs/solutions/**/*.md` | YAML frontmatter + markdown body |
| Auto-memory | C5 | Project memory dir (`MEMORY.md` + topic files) | Markdown with `#` headers |
| Legacy knowledge | C4 | `config/knowledge/*.md` (via interknow) | YAML frontmatter + markdown body |

## Execution

### 1. Parse query

Extract the query from the context argument. If no argument provided, ask the user what they want to recall.

### 2. Search docs/solutions/ (C4 curated)

**Primary path — semantic search via intersearch:**

If intersearch MCP server is available (`intersearch:embedding_query`):
1. First ensure docs/solutions/ is indexed: `intersearch:embedding_index path="docs/solutions" glob="**/*.md"`
2. Query: `intersearch:embedding_query query="<user query>" top_k=10`
3. Results include file paths and similarity scores

**Fallback — keyword grep:**

If intersearch is unavailable, use Grep to search `docs/solutions/**/*.md` for query keywords. Exclude `INDEX.md`, `critical-patterns.md`, `search-surfaces.md`.

For each matching file, extract from frontmatter:
- `title` or filename
- `problem_type`, `component`, `severity` (compound docs schema)
- `lastConfirmed`, `provenance` (interknow provenance fields)

### 3. Search auto-memory (C5 ephemeral)

Locate the project's auto-memory directory. Check these paths in order:
1. `.claude/projects/` memory dir (the one loaded into context as MEMORY.md)
2. `.clavain/memory/` if it exists

Search all `.md` files in the memory directory for query keywords using Grep. For each match, extract the surrounding context (3 lines before/after).

### 4. Search legacy knowledge (C4 legacy fallback)

Only if fewer than 5 results found so far.

Check `config/knowledge/*.md` (interknow's legacy store, if the directory exists in the current project or via `CLAUDE_PLUGIN_ROOT` for interknow). Skip `README.md` and `archive/`.

### 5. Rank and deduplicate

Rank results by:
1. **Semantic similarity** (if intersearch was used) — highest score first
2. **Provenance quality** — `independent` ranked above `primed`
3. **Recency** — more recent `lastConfirmed` ranked higher
4. **Source priority** — C4 curated > C4 legacy > C5 ephemeral

Deduplicate: if the same pattern appears in both docs/solutions/ and config/knowledge/, keep only the docs/solutions/ version (it's the converged canonical copy).

Cap at **8 results** (5 from C4, 3 from C5).

### 6. Present results

```
## Recall: {query summary}

### 1. {title} [C4:solutions]
{first paragraph or problem summary}
**Component:** {component} | **Severity:** {severity} | **Confirmed:** {lastConfirmed} ({provenance})
📄 {relative file path}

### 2. {title} [C5:memory]
{matching context}
📄 {relative file path}

...

---
Searched: {N} docs/solutions entries, {M} memory files, {L} legacy entries
Matched: {total} results ({method: semantic|keyword})
```

**Source tags:**
- `[C4:solutions]` — curated compound docs (docs/solutions/)
- `[C4:legacy]` — unmigrated interknow entries (config/knowledge/)
- `[C5:memory]` — auto-memory topic files (MEMORY.md, *.md)

If no matches found: "No knowledge entries match this query. Try broader keywords or check `docs/solutions/INDEX.md` for a full listing."
