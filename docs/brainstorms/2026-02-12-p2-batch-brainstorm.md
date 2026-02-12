# P2 Batch Brainstorm: Upstream Sync Rewrite + Discoverability

**Date:** 2026-02-12
**Beads:** Clavain-3w1x, Clavain-swio, Clavain-4728, Clavain-p5ex, Clavain-np7b

## What We're Building

Two independent work clusters addressing Clavain's P2 backlog:

### Cluster A: Upstream Sync Infrastructure (3 beads)

Full Python rewrite of the sync pipeline, which has outgrown bash at 1,019 lines with 5 inline Python subprocess calls and a 7-outcome three-way classification system.

**Scope:**
1. **Split upstreams.json** (Clavain-3w1x) — Separate static config (URLs, file maps, namespace replacements, blocklists) from mutable state (lastSyncedCommit per upstream). State goes to `upstream-state.json`, gitignored.
2. **Python rewrite** (Clavain-swio) — Port sync-upstreams.sh (1,019 lines) to Python. Preserve all 7 classification outcomes: SKIP, COPY, AUTO, KEEP-LOCAL, CONFLICT, REVIEW:new-file, REVIEW:unexpected-divergence.
3. **Absorb upstream-check.sh** (Clavain-4728) — Fold the 149-line release monitor into the Python package as a subcommand. Consolidate 3 `gh api` calls per upstream into 1 with multi-field extraction.

### Cluster B: Discoverability (2 beads)

4. **Split using-clavain** (Clavain-p5ex) — Reduce injected SKILL.md from 117 lines to ~25-line Stage-only routing table. Full Domain + Concern routing tables move to `references/routing-tables.md`, accessible via `/clavain:help`.
5. **Guessable command aliases** (Clavain-np7b) — Add `/deep-review` (flux-drive), `/full-pipeline` (lfg), `/cross-review` (interpeer). Router card recommends guessable names first.

## Why This Approach

### Cluster A: Full rewrite over incremental extraction

- The 5 inline Python heredocs create shell/Python boundary fragility (quoting, escaping, error propagation)
- The three-way classification logic (283-362) is the core algorithm — it deserves proper unit tests, which are impractical in bash
- upstream-check.sh shares the same config (upstreams.json) — folding it in eliminates a separate config reader
- AI conflict resolver stays as `claude -p` subprocess calls — simple, works today, runs weekly at most

### Cluster B: Stage-only router card

- 117 lines = ~2K tokens injected every session, most of which is rarely-used Domain/Concern lookup tables
- Stage routing covers 80% of decisions: "I'm exploring → /brainstorm", "I'm executing → /work"
- Domain and Concern are reference lookups, not routing decisions — they belong in `/help`
- ~25 lines = ~400 tokens, saving ~1.6K tokens per session

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Rewrite scope | Full Python rewrite | 1K lines of bash with 5 Python calls = hybrid fragility |
| AI conflict resolver | Keep `claude -p` | Simple, infrequent, no API key management |
| State storage | `upstream-state.json`, gitignored | Machine-local state, regenerated on first sync |
| API consolidation | Fold into Python package | Shares config, eliminates redundant reader |
| Router card size | Stage-only (~25 lines) | 80% routing coverage, 80% token savings |
| Alias mechanism | Separate command .md files | Simplest approach, no aliasing layer needed |

## Architecture: Python Sync Package

```
scripts/
  clavain_sync/
    __init__.py
    __main__.py          # CLI entry: clavain-sync {sync,check,status}
    config.py            # Load upstreams.json (config only)
    state.py             # Load/save upstream-state.json
    classify.py          # Three-way classification (7 outcomes)
    resolve.py           # AI conflict resolution via claude -p
    namespace.py         # Namespace replacement + blocklist filtering
    check.py             # Release monitor (absorbed upstream-check.sh)
    report.py            # Markdown report generation
  sync-upstreams.sh      # Deprecated, kept for one release cycle
  upstream-check.sh      # Deprecated, kept for one release cycle
```

**Entry point:** `python3 -m clavain_sync sync` / `check` / `status`

**Key design principles:**
- Each module is independently testable
- `classify.py` is pure functions (no I/O) — takes file contents, returns classification
- `resolve.py` shells out to `claude -p` — isolated for easy mocking in tests
- `config.py` validates schema on load (no pydantic — just dict checks + clear errors)
- `state.py` uses atomic writes (tempfile + rename) for crash safety

## Dependency Order

```
Clavain-3w1x (split config/state)
    ↓
Clavain-4728 (API consolidation) ── both feed into ──→ Clavain-swio (Python rewrite)

Clavain-p5ex (router card split) ──→ Clavain-np7b (aliases reference router card)
```

Clusters A and B are fully independent and can execute in parallel.

## Open Questions

1. **pull-upstreams.sh fate** — Should the 188-line pull script also fold into the Python package, or stay as a thin bash wrapper around `git fetch`?
2. **CI workflow update** — `.github/workflows/sync.yml` calls sync-upstreams.sh directly. Need to update after Python migration.
3. **upstream-impact-report.py** — Already Python (214 lines). Should it merge into the package or stay standalone?

## Testing Strategy

- **Unit tests** for classify.py (7 classification paths), namespace.py (replacement + blocklist), config.py (schema validation)
- **Integration tests** using fixture repos (small git repos with known sync scenarios)
- **Parity test** — run both bash and Python on same inputs, compare classifications (one-time validation before deprecating bash)
