---
name: recall
description: Search across all knowledge systems — curated docs, memory files, legacy entries
argument-hint: "<query>"
disable-model-invocation: false
---

# /recall

Unified retrieval across C4 (curated knowledge) and C5 (ephemeral memory). Returns ranked, deduplicated results with source attribution.

## Context

<context> #$ARGUMENTS </context>

## Sources

| Source | Layer | Path / Interface |
|--------|-------|------------------|
| Estate index | C3 | Estate MCP (`mcp__estate__*`) over the Uqbar canon: entities, relationships, decisions-with-rationale, each tagged ruled or proposed |
| Compound docs | C4 | `docs/solutions/**/*.md` |
| Legacy knowledge | C4 | `config/knowledge/*.md` (prefer qmd MCP over grep) |
| Auto-memory | C5 | Project memory dir (`MEMORY.md` + topic files) |
| bd memories | C5 | `bd memories <keyword>` (repo-scoped; run from the repo) |

Lane map + provenance shapes: `~/projects/Sylveste/ops/canongraph/recall-lanes.md`.

## Execution

### 1. Parse query

Extract from context arg. If empty, ask the user.

### 1.5. Query the estate index (C3 — skip silently if the estate MCP is absent)

If the query names (or implies) a **thing** — a project, person, plugin, machine, client — or asks "what did we decide":
1. `mcp__estate__resolve` the candidate name, with `entity_type` when it is clear (project, then plugin, person, machine, client). A hit returns the record's properties, its file in the Uqbar and its `state`.
2. On a project hit: `mcp__estate__query` `decisions_for_project` for its decision history with rationale and who made the call. For a plugin: `plugins_maintained_by` from the person side, or `project_card`.
3. For "what did we decide in <session/run>": `decisions_in_run`. For location questions: `projects_on_machine`. For serving/URL questions: `serving_map` or `project_card`. For a layer: `projects_in_layer`. For how a ruling changed over time: `decision_lineage`. `mcp__estate__list_queries` lists the rest.
4. `mcp__estate__search` the query text. It searches the migrated documents (the former CanonGraph document lane), decision rationales and themes, and returns passages verbatim with their file path. Treat document hits as memory-file-grade evidence.

Estate results carry file provenance: the record's path in the Uqbar, and `state`. `ruled` means mk signed it; `proposed` means nobody has ruled on it yet. Rank ruled results FIRST when they answer the question directly, and label a proposed one "(proposed)" so it never reads as settled.

### 2. Search docs/solutions/ (C4 curated)

**Primary — semantic via intersearch:**
1. `intersearch:embedding_index path="docs/solutions" glob="**/*.md"`
2. `intersearch:embedding_query query="<query>" top_k=10`

**Fallback — keyword Grep** on `docs/solutions/**/*.md`. Exclude `INDEX.md`, `critical-patterns.md`, `search-surfaces.md`. Extract `title`, `problem_type`, `component`, `severity`, `lastConfirmed`, `provenance` from frontmatter.

### 3. Search auto-memory (C5)

Check `.claude/projects/` memory dir, then `.clavain/memory/`. Grep all `.md` files with 3 lines context around each match.

### 4. Search legacy knowledge (C4 fallback)

Prefer qmd MCP when available: `mcp__plugin_interknow_qmd__query` with paired sub-queries (`lex` + `vec`) and an `intent` string. Fallback: only if fewer than 5 results found, Grep `config/knowledge/*.md`. Skip `README.md` and `archive/`.

### 4.5. Search bd memories (C5 — skip silently if bd absent)

`bd memories <keyword>` from the current repo (bd is cwd-sensitive). Repo-scoped task insights only — never rank above an estate or C4 hit that answers the same question.

### 5. Rank and deduplicate

Priority: **C3 estate** (typed, file-backed, ruled before proposed; answers "what/who/why-decided" directly) → semantic similarity → provenance quality (`independent` > `primed`) → recency → C4 curated > C4 legacy > C5 memory → C5 bd. Deduplicate: keep `docs/solutions/` over `config/knowledge/` for same pattern; when a memory file merely points at an estate record, show the estate record and cite the pointer. Cap: 10 results (2 C3, 5 C4, 3 C5).

### 6. Present results

```
## Recall: {query summary}

### 1. {title} [C4:solutions]
{problem summary}
**Component:** {component} | **Severity:** {severity} | **Confirmed:** {lastConfirmed} ({provenance})
📄 {relative file path}

### 2. {title} [C5:memory]
{matching context}
📄 {relative file path}

---
Searched: {N} docs/solutions, {M} memory files, {L} legacy entries
Matched: {total} ({method: semantic|keyword})
```

Tags: `[C3:estate]` `[C4:solutions]` `[C4:legacy]` `[C5:memory]` `[C5:bd]`

If no matches: "No knowledge entries match this query. Try broader keywords or check `docs/solutions/INDEX.md`."
