# Plan: Flux-Gen + Flux-Drive Integration

> **Review status:** Reviewed by fd-architecture, fd-correctness, fd-quality (2026-02-12). All P0/P1 findings incorporated. See `docs/research/flux-drive/2026-02-12-flux-gen-drive-integration/` for full review outputs.

## Problem

flux-gen (generates project-specific review agents from domain profiles) and flux-drive (runs multi-agent reviews) are separate commands with no automatic integration. Users must manually:

1. Run `/flux-gen` to create `.claude/agents/fd-*.md` files
2. Then run `/flux-drive` to review

Additionally, once domain detection results are cached in `.claude/flux-drive.yaml`, they never expire — even if the project's tech stack changes significantly (new frameworks added, directories restructured, etc.).

## Goals

1. **Auto-generate agents**: When flux-drive detects domains but no project-specific agents exist, automatically run flux-gen (non-interactive)
2. **Staleness detection**: Detect when cached domain results may be outdated due to structural project changes
3. **Agent lifecycle**: Handle orphaned agents (domain removed) and missing agents (domain added)

## Non-Goals

- Real-time domain tracking (watching filesystem changes)
- Automatic deletion of user-customized agents
- Domain detection for non-git projects (fallback to mtime-based staleness instead)

## Design

### 1. New Steps 1.0.2–1.0.4 in flux-drive SKILL.md

Insert after Step 1.0.1 (domain classification, currently named Step 1.0a). The existing Step 1.0a is renamed to Step 1.0.1 for consistency.

These are three sequential gates that separate detection, comparison, and generation — each is a pure step with a single responsibility.

#### Step 1.0.2: Check staleness (pure, no side effects)

```
Run `detect-domains.py --check-stale {PROJECT_ROOT}`

Exit codes:
  0 → cache is fresh, use cached domains. Proceed to Step 1.1.
  3 → cache is stale (structural changes detected). Proceed to Step 1.0.3.
  4 → no cache exists (first run or deleted). Proceed to Step 1.0.3.
  1 → no domains detected. Skip agent generation entirely. Proceed to Step 1.1.
  2 → script error. Log warning with actionable message:
      "Domain detection unavailable (detect-domains.py error).
       Agent auto-generation skipped. To enable:
         1. Verify Clavain plugin: ls $CLAUDE_PLUGIN_ROOT/scripts/
         2. Or run /flux-gen manually
       Proceeding with core agents only."
      Proceed to Step 1.1.
```

#### Step 1.0.3: Re-detect and compare (pure, writes only cache)

```
1. Read previous domains from cache (if any) before re-detection.

2. Re-run: `detect-domains.py --no-cache {PROJECT_ROOT} --json`
   - If exit 1 (no domains): log "No domains detected." Proceed to Step 1.1.
   - If exit 2 (error): log error, proceed to Step 1.1.

3. Compare new domain list to previous:
   - Domains unchanged → proceed to Step 1.0.4 (check agents only)
   - Domains changed → log: "Domain shift: [old] → [new]"
     Proceed to Step 1.0.4 with change flag set.
```

#### Step 1.0.4: Agent generation (side-effecting, writes agent files)

```
1. Validate domain profiles exist:
   For each detected domain, check that config/flux-drive/domains/{domain}.md
   exists AND has an ## Agent Specifications section.
   - If profile missing: log warning, remove domain from generation list.
   - If ALL profiles missing: log error, suggest --no-cache re-detect. Skip generation.

2. Check for existing project agents:
   ls {PROJECT_ROOT}/.claude/agents/fd-*.md 2>/dev/null

3. Decision matrix:
   a. Agents exist AND domains unchanged → skip generation. Report "up to date."
   b. Agents exist AND domains changed →
      - Identify orphaned agents (domain removed) via frontmatter check
      - Identify missing agents (new domain added)
      - Log: "Domain shift: N new agents needed, M agents orphaned."
      - Generate only missing agents (don't touch existing)
   c. No agents exist AND domains detected →
      - Log: "Generating project agents for [domain1, domain2]..."
      - Generate agents silently (skip flux-gen's AskUserQuestion)

4. Track generation status per agent:
   - On success: report "✓ fd-{name}"
   - On failure: log error with reason (disk full, permission denied, etc.)
   - After loop: "Generated N of M agents. K failed."
   - If any failed: list failures with reasons. Do NOT abort flux-drive.

5. Report summary:
   "Domain check: game-simulation (0.65) — fresh (scanned 2026-02-09)"
   "Project agents: 2 exist, 1 generated, 0 failed"
```

### 2. detect-domains.py: Add `--check-stale` flag

New lightweight mode that checks if structural signals changed since last detection.

#### Structural change detection

Three-tier staleness strategy (try each in order, stop at first conclusive result):

**Tier 1 — Structural hash** (fastest, < 100ms):
Compare `structural_hash` in cache to recomputed hash of current STRUCTURAL_FILES.

**Tier 2 — Git log** (medium, < 500ms):
If hash is inconclusive or missing from cache, use git history.

**Tier 3 — Mtime fallback** (for non-git projects):
Compare mtime of STRUCTURAL_FILES against `detected_at` timestamp.

```python
# Files whose presence/absence/content indicates structural project changes
STRUCTURAL_FILES = {
    "package.json", "Cargo.toml", "go.mod", "pyproject.toml",
    "requirements.txt", "Gemfile", "build.gradle", "build.gradle.kts",
    "project.godot", "pom.xml", "CMakeLists.txt", "Makefile",
}

# File extensions indicating structural project type changes (new tech stack)
STRUCTURAL_EXTENSIONS = {
    ".gd", ".tscn", ".unity", ".uproject",
}
```

#### Staleness algorithm

```
1. Read cache from {PROJECT_ROOT}/.claude/flux-drive.yaml
2. If no cache exists → exit 4 (no cache)
3. If `override: true` in cache → exit 0 (never stale, short-circuit before any computation)
4. If `cache_version` missing or < CURRENT_VERSION → exit 3 (stale, format upgrade needed)

5. Tier 1 — Hash check:
   a. If cache has `structural_hash` field:
      - Recompute hash of current STRUCTURAL_FILES (sorted keys, per-file SHA-256)
      - If hash matches → exit 0 (fresh)
      - If hash differs → exit 3 (stale), print which files changed

6. Tier 2 — Git check (if hash missing from cache OR .git exists):
   a. Run: git log --since="{detected_at}" --diff-filter=ACDM --name-only --format="" HEAD
      (Note: exclude R for renames — handle separately below)
   b. If git exit code != 0 (git error, corrupted repo, shallow clone):
      - Log warning: "Git unavailable (exit $?), falling back to mtime check"
      - Fall through to Tier 3
   c. Filter results:
      - Any file basename in STRUCTURAL_FILES? → stale
      - Any file with extension in STRUCTURAL_EXTENSIONS? → stale
      - Any new top-level directory matching a domain signal directory? → stale
   d. Handle renames separately: git log --diff-filter=R --name-status --since="{detected_at}"
      - Old is structural, new is NOT → stale (structural file removed from scope)
      - Old is NOT, new IS structural → stale (structural file moved into scope)
      - Both structural or neither → not stale (cosmetic rename)
   e. If none matched → exit 0 (fresh)
   f. If any matched → exit 3 (stale), print triggers

7. Tier 3 — Mtime fallback (no git or git failed):
   a. For each file in STRUCTURAL_FILES that exists:
      - If file mtime > detected_at timestamp → exit 3 (stale)
   b. If none newer → exit 0 (fresh)
```

#### Exit codes (updated)

| Code | Meaning |
|------|---------|
| 0 | Cache exists and is fresh (or `override: true`) |
| 1 | No domains detected |
| 2 | Fatal error (script crash, missing index.yaml) |
| 3 | Cache is stale — structural changes detected since last scan |
| 4 | No cache exists (first run or cache deleted) |

Exit codes 3 and 4 both trigger re-detection in Step 1.0.3, but are logged differently:
- Exit 3 → "Cache outdated, re-detecting..."
- Exit 4 → "No cache, detecting domains..."

#### `--check-stale --dry-run` mode

For debugging staleness behavior:
```
Cache detected_at: 2026-02-12T10:15:32-08:00
Tier 1 (hash): sha256:a1b2 → sha256:c3d4 — MISMATCH
  Changed: package.json (sha256 differs)
  Unchanged: Cargo.toml, go.mod

Verdict: STALE (package.json changed)
Exit code: 3
```

### 3. Agent lifecycle management

#### Agent provenance via YAML frontmatter

Generated agents include machine-readable frontmatter that survives user customization:

```yaml
---
generated_by: flux-gen
domain: game-simulation
generated_at: '2026-02-12T10:15:32-08:00'
flux_gen_version: 1
---
# fd-simulation-kernel — Game-Simulation Domain Reviewer

> Customize this file for your project's specific needs.
...
```

The frontmatter is the source of truth for lifecycle decisions. The human-readable header comment is supplementary.

#### Orphan detection

When domains change, identify agents that no longer match any detected domain:

```
For each .claude/agents/fd-*.md:
  1. Parse YAML frontmatter (between --- markers)
  2. If frontmatter has `generated_by: flux-gen`:
     a. Extract `domain` field
     b. If domain is NOT in current detected domains → mark as orphaned
  3. If no frontmatter or no `generated_by` field:
     → Treat as user-created. Leave alone (never touch).
```

Orphaned agents are logged but NOT deleted automatically. The user must decide:
- Keep them (they still work, just won't get domain boost in triage)
- Delete them manually
- Re-run `/flux-gen` with overwrite to regenerate from current domains

#### Missing agent detection

When a new domain is detected that has Agent Specifications in its profile:

```
For each detected domain:
  1. Validate: config/flux-drive/domains/{domain}.md exists
  2. Read domain profile, extract ### fd-{name} subsections from ## Agent Specifications
  3. Check if .claude/agents/fd-{name}.md exists
  4. If not → generate it (with frontmatter)
```

### 4. Cache format update

Updated cache format with versioning, full timestamps, and algorithm-prefixed hash:

```yaml
# Auto-detected by flux-drive. Edit to override.
cache_version: 1
domains:
  - name: game-simulation
    confidence: 0.65
    primary: true
  - name: cli-tool
    confidence: 0.35
detected_at: '2026-02-12T10:15:32-08:00'
structural_hash: 'sha256:a1b2c3d4e5f6...'
```

**Key changes from v0:**
- `cache_version: 1` — enables schema evolution. If missing or < current, treat as stale.
- `detected_at` — full ISO 8601 datetime with timezone (was: date-only YYYY-MM-DD). Prevents same-day re-detection loops.
- `structural_hash` — prefixed with algorithm name (`sha256:`). Enables future algorithm changes without false staleness.

#### Structural hash computation

The hash is computed deterministically:
1. For each file in `sorted(STRUCTURAL_FILES)`:
   - If file exists: compute `sha256(file_contents)`
   - If file missing: use sentinel `"__absent__"`
2. Concatenate: `"filename1:sha256hash1\nfilename2:sha256hash2\n..."`
3. Hash the concatenation: `sha256(concatenated)`
4. Store as `"sha256:{hex_digest}"`

File deletion changes the hash (absent sentinel differs from content hash). File order is deterministic (sorted). Algorithm is explicit in the stored value.

#### Atomic cache writes

Cache writes use the temp-file-and-rename pattern to prevent corruption:

```python
import tempfile, os

def write_cache(path: Path, results: list[dict], structural_hash: str) -> None:
    payload = {
        "cache_version": 1,
        "domains": results,
        "detected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "structural_hash": structural_hash,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# Auto-detected by flux-drive. Edit to override.\n"
    content = (header + yaml.dump(payload, default_flow_style=False, sort_keys=False)).encode("utf-8")

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, content)
        os.fsync(fd)
        os.close(fd)
        os.rename(tmp_path, str(path))  # atomic on POSIX
    except Exception:
        os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

### 5. Performance budget

| Operation | Budget |
|-----------|--------|
| `--check-stale` Tier 1 (hash compare) | < 100ms |
| `--check-stale` Tier 2 (git log) | < 500ms |
| `--check-stale` Tier 3 (mtime fallback) | < 200ms |
| Full re-detection | < 10s (existing budget) |
| Agent generation (per agent) | < 1s (file write) |
| Total Steps 1.0.2–1.0.4 overhead | < 2s typical, < 15s worst case |

### 6. User-facing changes

#### New behavior in flux-drive

Users see a brief status line during Steps 1.0.2–1.0.4:

```
Domain check: game-simulation (0.65), cli-tool (0.35) — fresh (scanned 2026-02-09)
Project agents: 3 exist, 0 generated
```

Or on first run (exit 4 — no cache):

```
Domain check: game-simulation (0.65) — detected (first scan)
Project agents: generating 2 agents for game-simulation...
  ✓ fd-simulation-kernel
  ✓ fd-game-balance
```

Or on domain shift (exit 3 — stale):

```
Domain check: web-api (0.72), game-simulation (0.45) — stale → re-detected (scanned 2026-02-09)
Project agents: 1 new (fd-api-contracts), 0 orphaned, 0 failed
```

Or on detection error:

```
Domain check: unavailable (detect-domains.py error)
  → Agent auto-generation skipped. Run /flux-gen manually. Proceeding with core agents only.
```

#### No changes to standalone `/flux-gen`

The `/flux-gen` command continues to work exactly as today — interactive, with confirmation prompt. Users can still run it manually to:
- Force regeneration with overwrite
- Generate for a specific domain
- Customize agents before first flux-drive run

### 7. Files to modify

| File | Change |
|------|--------|
| `scripts/detect-domains.py` | Add `--check-stale` flag (with `--dry-run`), three-tier staleness, atomic writes, exit code 4, full timestamps, hash versioning |
| `skills/flux-drive/SKILL.md` | Rename Step 1.0a → 1.0.1, add Steps 1.0.2–1.0.4 |
| `commands/flux-gen.md` | Add YAML frontmatter to agent template (Section 3) |
| `skills/flux-drive/phases/launch.md` | No changes (already handles domain injection) |

### 8. Test plan

#### Unit tests (detect-domains.py)

**Staleness check:**
- `test_check_stale_no_cache` → exit 4
- `test_check_stale_override_true` → exit 0
- `test_check_stale_override_true_skips_hash` → exit 0 AND hash computation not called (performance contract)
- `test_check_stale_override_true_with_structural_changes` → exit 0 (override wins)
- `test_check_stale_fresh_hash_match` → exit 0 (Tier 1)
- `test_check_stale_structural_file_changed` → exit 3 (package.json modified)
- `test_check_stale_new_extension` → exit 3 (.gd file added)
- `test_check_stale_non_structural_change` → exit 0 (only .py edits)
- `test_check_stale_cache_version_mismatch` → exit 3 (old cache format triggers re-detect)
- `test_check_stale_git_corrupted_falls_to_mtime` → exit 0 or 3 (NOT exit 2)
- `test_check_stale_shallow_clone_falls_to_mtime` → exit 0 or 3 (NOT exit 2)
- `test_check_stale_rename_cosmetic` → exit 0 (rename both structural → not stale)
- `test_check_stale_rename_structural_removed` → exit 3 (structural → non-structural)

**Structural hash:**
- `test_structural_hash_deterministic` → same inputs → same hash
- `test_structural_hash_ignores_file_order` → property-based (Hypothesis permutations)
- `test_structural_hash_excludes_missing_files` → absent files use sentinel, don't affect others
- `test_structural_hash_file_deletion_changes_hash` → removing a file changes the hash
- `test_structural_hash_includes_algorithm_prefix` → starts with `sha256:`

**Cache writes:**
- `test_write_cache_atomic` → temp file cleaned up on success, cache valid YAML
- `test_write_cache_failure_no_partial` → on write error, no partial cache left
- `test_cache_timestamp_is_full_iso8601` → `detected_at` includes time and timezone
- `test_cache_version_present` → `cache_version: 1` in output

**Performance:**
- `test_check_stale_under_100ms` → `--check-stale` on typical project completes in < 100ms

#### Integration tests (shell)

- `test_flux_drive_auto_gen_first_run` → detects domains, generates agents with frontmatter, agents appear in triage
- `test_flux_drive_skips_existing_agents` → agents exist, no regeneration
- `test_flux_drive_stale_cache_redetects` → modify package.json, verify re-detection
- `test_flux_drive_orphan_detection` → remove domain, verify orphan logged via frontmatter
- `test_flux_drive_silent_mode_no_prompt` → auto-gen does NOT prompt user
- `test_standalone_flux_gen_prompts` → standalone `/flux-gen` still prompts
- `test_flux_drive_partial_gen_failure` → disk full mid-generation, reports failures, continues review
- `test_flux_drive_missing_domain_profile` → domain in cache but profile deleted, skips gracefully

### 9. Edge cases

| Case | Handling |
|------|---------|
| No .git directory | Tier 3 mtime fallback (compare structural file mtimes to detected_at) |
| Corrupted .git | Git log fails → Tier 3 mtime fallback (NOT fatal error) |
| Shallow clone | Git --since may return empty → Tier 3 mtime fallback |
| Empty project (no build files) | No structural files → hash is sentinel-only → always "fresh" after first scan |
| `override: true` in cache | Never re-detect, never auto-generate. Short-circuit before hash/git. |
| `cache_version` missing or old | Treat as stale (exit 3), re-detect writes new format |
| User deleted generated agents | Regenerate on next flux-drive run (frontmatter missing = not tracked) |
| User customized a generated agent | Preserved — flux-gen skips existing files. Frontmatter domain field still used for orphan detection. |
| User removed frontmatter from agent | Treated as user-created. No longer tracked for orphan detection. |
| Multiple domains, partial agent coverage | Generate only missing agents |
| detect-domains.py not available | Skip Steps 1.0.2–1.0.4 entirely, log actionable warning |
| Domain profile has no Agent Specifications | Skip that domain for generation, log info |
| Domain in cache but profile deleted (version skew) | Validate before generation. Remove from active list, log warning. |
| Partial generation failure (disk full, permission error) | Track per-agent, report failures, continue flux-drive with successfully generated agents |
| Same-day re-detection | Full ISO 8601 timestamp prevents loop (git --since uses exact time, not midnight) |
| Cache corruption (partial write, YAML error) | read_cache returns None → treated as exit 4 (no cache) → full re-detect. Atomic writes prevent this in normal operation. |

## Alternatives considered

### A: New `/flux-gendrive` command
Rejected. Conflates two lifecycle concerns (setup vs. execution). Adds another command to learn. Option A (auto-gen in flux-drive) provides the same UX with zero new commands.

### B: Time-based expiry (e.g., 7 days)
Rejected. Arbitrary. A project can go months without structural changes, or restructure twice in a day. Structural change detection is both more accurate and cheaper.

### C: Always re-detect
Rejected. Detection takes up to 10s (keyword scanning). For repeat reviews of the same project, this adds unnecessary latency. The structural hash check takes <100ms.

### D: File watcher / inotify
Rejected. Overkill for a CLI tool. Would require a daemon. The on-demand check during flux-drive launch is sufficient.

### E: Semantic/LLM-based domain detection
Rejected. More accurate but violates the <10s performance budget. Structural signals (files, frameworks, directories) are deterministic and cache-friendly. If structural signals are insufficient, users can manually set `override: true` in the cache.

## Review findings addressed

| Finding | Source | Resolution |
|---------|--------|------------|
| Circular dependency in Step 1.0b | arch P0-1 | Split into 3 sequential gates (1.0.2, 1.0.3, 1.0.4) |
| Silent failures for write operations | arch P0-2 | Read failures: skip silently. Write failures: log with reason per agent. |
| Structural hash collision risk | arch P0-3, correctness P1-2 | Per-file SHA-256, sorted keys, algorithm prefix |
| Date boundary infinite loop | correctness P0-2 | Full ISO 8601 timestamp with timezone |
| TOCTOU between cache read and git | correctness P0-1 | Sequential gates + re-read cache in Step 1.0.3 |
| Exit code 3 overloaded | quality P0-2 | Split into exit 3 (stale) and exit 4 (no cache) |
| Step numbering collision | quality P0-1 | 1.0a → 1.0.1, new steps 1.0.2–1.0.4 |
| Orphan detection via header parsing | arch P1-1, correctness P1-1 | YAML frontmatter with `generated_by`, `domain` fields |
| Non-atomic cache writes | correctness P1-3 | temp file + fsync + rename pattern |
| Git-only staleness (no fallback) | arch P1-3, quality P1-4 | Three-tier: hash → git → mtime |
| No cache version field | arch IMP-2, correctness P1-2 | `cache_version: 1` in cache format |
| Missing domain profile validation | correctness P1-4 | Validate profile exists before generation |
| Partial generation failures unhandled | correctness P2-3 | Per-agent status tracking, report failures |
| Git rename false positives | correctness P2-2 | Exclude R from --diff-filter, handle separately |
| Missing test cases | quality P1-1, P1-2 | Added: override interaction, silent mode, performance, git edge cases |
| Terminology inconsistency | quality P1-3 | Clarified: hash is Tier 1, git is Tier 2, mtime is Tier 3 |
| No dry-run mode | correctness IMP-1 | Added `--check-stale --dry-run` |
| No timestamp in user output | quality IMP-3 | Added "(scanned 2026-02-09)" to status line |
| Vague error messages | quality IMP-4 | Added actionable error text with diagnostic steps |
