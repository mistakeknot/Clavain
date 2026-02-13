# Flux-Drive Correctness Review: Flux-Gen Integration

## Findings Index
- P0 | P0-1 | "Section 2: Staleness Detection" | Date boundary TOCTOU race between git log and cache file read
- P0 | P0-2 | "Section 2: Staleness Detection" | Git --since includes detected_at date, causing false stale on same-day re-runs
- P1 | P1-1 | "Section 3: Agent Lifecycle" | Orphan detection misses agents with customized/removed headers
- P1 | P1-2 | "Section 2: Staleness Detection" | Structural hash has no collision detection or versioning
- P1 | P1-3 | "Section 4: Cache Format" | Cache write is not atomic, can corrupt on mid-write crashes
- P1 | P1-4 | "Section 3: Agent Lifecycle" | Missing agent generation skips validation that domain profile still exists
- P2 | P2-1 | "Section 2: Staleness Detection" | STRUCTURAL_EXTENSIONS lacks common game/embedded formats
- P2 | P2-2 | "Section 2: Staleness Detection" | Git log filtering doesn't handle renames correctly
- P2 | P2-3 | "Section 3: Agent Lifecycle" | No handling for partial agent generation failures
- IMP | IMP-1 | "Section 2: Staleness Detection" | Add dry-run mode for staleness check debugging
- IMP | IMP-2 | "Section 4: Cache Format" | Include hash algorithm identifier in cache
- IMP | IMP-3 | "Section 9: Edge Cases" | Document cache corruption recovery procedure

Verdict: needs-changes

---

## Summary

This integration plan has solid high-level design but contains critical correctness gaps in staleness detection, cache integrity, and agent lifecycle management. The most severe issues are race conditions in the staleness check (TOCTOU between git log and cache read) and date boundary bugs (git --since includes the boundary date, causing false staleness). Cache writes are non-atomic, risking corruption on crashes. Agent lifecycle logic assumes headers remain intact but doesn't handle customization. With fixes, this will be robust.

---

## Issues Found

### P0-1: Date boundary TOCTOU race between git log and cache file read

**Location**: Section 2, staleness detection algorithm step 1-2

**Issue**: The plan reads `detected_at` from the cache, then runs `git log --since="{detected_at}"` to find changes. Between these two operations, another flux-drive process could write a **new** cache with updated `detected_at`, causing the git log to use a stale cutoff date.

**Interleaving**:
1. Process A reads cache: `detected_at = 2026-02-10`
2. Process B runs full detection, writes cache: `detected_at = 2026-02-12`
3. Process A runs: `git log --since="2026-02-10"` (misses changes from Feb 10-12 that B already processed)
4. Process A compares to stale cutoff, reports "fresh" even though files changed

**Consequence**: Stale cache incorrectly marked fresh. Domain changes go undetected until the next manual re-detection.

**Fix**: Use the `detected_at` from the cache content you **actually read**, and re-check that the cache file's mtime hasn't changed after git log completes. If mtime changed, retry the entire staleness check with the new cache. Alternatively, add a monotonic `check_sequence` counter to the cache and verify it matches before/after git log.

---

### P0-2: Git --since includes detected_at date, causing false stale on same-day re-runs

**Location**: Section 2, staleness detection algorithm step 4

**Issue**: `git log --since="2026-02-12"` includes commits from **2026-02-12 00:00:00** onwards. If you detect domains on Feb 12 morning, then make structural changes on Feb 12 afternoon, git log will show those changes. But the cache `detected_at: '2026-02-12'` is ambiguous about **what time** on Feb 12 detection happened.

**Interleaving**:
1. User runs flux-drive at 10:00 AM on Feb 12 → detects domains, writes `detected_at: '2026-02-12'`
2. User edits package.json at 2:00 PM on Feb 12
3. User runs flux-drive again at 3:00 PM → staleness check runs `git log --since="2026-02-12"` → finds the 2:00 PM commit → reports stale
4. Re-detection runs, produces identical results, writes `detected_at: '2026-02-12'` again
5. Infinite loop: every flux-drive run re-detects because same-day changes are always "after" the date boundary

**Timezone complication**: `detected_at` is an ISO date string (YYYY-MM-DD), which git interprets as **midnight in the local timezone**. On a server in America/Los_Angeles, `--since="2026-02-12"` means 2026-02-12 00:00:00 PST = 2026-02-12 08:00:00 UTC. If the git commit was authored in UTC or another timezone, the boundary comparison may shift unexpectedly.

**Fix**: Change `detected_at` to ISO 8601 datetime with timezone: `detected_at: '2026-02-12T10:15:32-08:00'`. Use `--since="{detected_at}"` (git accepts ISO 8601). Alternatively, use `--since="{detected_at} +1 day"` to exclude commits on the detection date itself, but this delays staleness detection by up to 24 hours.

**Preferred fix**: Store `detected_at` as a full timestamp, use `git log --since="{detected_at}" --format="%ct"` (Unix timestamp) for boundary comparison. This is timezone-safe and deterministic.

---

### P1-1: Orphan detection misses agents with customized/removed headers

**Location**: Section 3, orphan detection algorithm step 1-2

**Issue**: The plan says "Read the file header: Generated by /flux-gen from the {domain-name} domain profile". But users are **encouraged to customize** generated agents. Step 4 in flux-gen.md says "Customize this file for your project's specific needs." A user might:
- Remove the header comment entirely (it's noise after the first read)
- Rewrite the header to describe their customizations
- Copy the agent to a different project where the domain name changed

When the header is missing or modified, the orphan detector cannot extract `{domain-name}`. The plan says "If file has NO flux-gen header (user-created): Leave alone". This conflates two cases:
1. User created the agent from scratch (should leave alone)
2. flux-gen created it, user removed the header (should still track for orphan detection)

**Consequence**: Orphaned agents with customized headers are not detected. User runs flux-drive, gets stale domain-specific reviews that no longer apply to the project.

**Fix**: When flux-gen creates an agent, embed a machine-readable marker that survives customization:
```markdown
<!-- flux-gen: domain=game-simulation version=1 generated=2026-02-12 -->
```
Place this at the **end** of the file (less likely to be removed). Check for this marker during orphan detection. If marker is present, extract domain name. If marker is absent, treat as user-created. If marker is present but domain name is not in detected domains, report orphaned.

Alternatively: maintain a `.claude/flux-gen-manifest.json` file tracking which agents were generated and for which domains. Orphan detection reads the manifest, not the agent files. Users can customize freely without breaking lifecycle tracking.

---

### P1-2: Structural hash has no collision detection or versioning

**Location**: Section 4, structural_hash field

**Issue**: The plan says "compute hash from concatenated contents of all STRUCTURAL_FILES that exist." No hash algorithm is specified. No collision handling. No versioning if the hash algorithm changes or STRUCTURAL_FILES list changes.

**Collision scenario**: SHA-256 is collision-resistant but not collision-proof. If a hash collision occurs (astronomically unlikely but possible), two different project states map to the same hash. Staleness check reports "fresh" when the project changed.

**Algorithm change scenario**: You ship version 0.5.1 using MD5 for the hash. Later, you switch to SHA-256 for FIPS compliance. Old caches have MD5 hashes, new staleness checks compute SHA-256. Every cache is reported stale on first check after upgrade, even if nothing changed.

**STRUCTURAL_FILES change scenario**: Version 0.5.1 includes `package.json, Cargo.toml, go.mod`. Version 0.6.0 adds `build.gradle`. Old cache has a hash computed without build.gradle. New staleness check recomputes with build.gradle. Hash mismatch → stale, even if none of those files changed.

**Consequence**: False staleness reports on version upgrades. Unnecessary re-detection on every flux-drive run after plugin update.

**Fix**: Include algorithm identifier and STRUCTURAL_FILES list version in the cache:
```yaml
structural_hash: 'sha256:a1b2c3d4'
hash_version: 1  # increment when STRUCTURAL_FILES list changes
```
On staleness check:
1. If `hash_version` mismatches current version → report stale (re-hash needed)
2. If algorithm prefix mismatches → report stale (hash incompatible)
3. Otherwise, compare hash values

Alternatively: skip the hash optimization entirely for the first version. Use git log as the sole staleness check. Add the hash optimization later if git log proves too slow (but the plan's 500ms budget is reasonable for most repos).

---

### P1-3: Cache write is not atomic, can corrupt on mid-write crashes

**Location**: Section 2 (detect-domains.py), `write_cache` function (line 84-92)

**Issue**: The current `write_cache` implementation does:
```python
path.write_text(header + yaml.dump(payload, ...), encoding="utf-8")
```
This is a non-atomic write. If the process crashes, the disk is full, or the OS buffer isn't flushed, the cache file can be left in a partially written state. On next read, `yaml.safe_load` will fail with a parse error, and the `except Exception: pass` in `read_cache` (line 79) will silently return None.

**Interleaving**:
1. flux-drive runs domain detection, writes cache
2. OS buffers the write, hasn't flushed to disk yet
3. Kill -9 (user Ctrl+C, OOM killer, server crash)
4. Partial cache file remains: `domains:\n- name: game-si` (truncated)
5. Next flux-drive run: `read_cache` fails to parse, returns None
6. Step 1.0a thinks no cache exists, runs full detection (wasteful but safe)
7. Writes new cache, same race condition exists

**Worse case**: Cache file is truncated to 0 bytes but still exists. `yaml.safe_load("")` returns None. `isinstance(None, dict)` is False. `read_cache` returns None. Harmless in this case, but if you later add logic that assumes "cache exists = domains were detected", you get silent data loss.

**Cache format update race**: User runs flux-drive on old plugin version (writes old cache format). While running, plugin updates to new version (adds `structural_hash` field). New staleness check reads cache, finds no `structural_hash`, assumes stale. Writes new cache with `structural_hash`. Old process finishes, writes cache **without** `structural_hash`, clobbering the new cache. Next run finds no `structural_hash`, assumes stale again. Infinite re-detection loop.

**Fix**: Use atomic write pattern:
```python
import tempfile, os
tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, text=True)
try:
    os.write(tmp_fd, (header + yaml.dump(payload, ...)).encode("utf-8"))
    os.fsync(tmp_fd)  # flush to disk
    os.close(tmp_fd)
    os.rename(tmp_path, path)  # atomic on POSIX
except:
    os.unlink(tmp_path)
    raise
```

Also add file locking (fcntl.flock) around cache read/write to prevent concurrent processes from clobbering each other.

---

### P1-4: Missing agent generation skips validation that domain profile still exists

**Location**: Section 1, Step 1.0b substep 3d

**Issue**: The plan says "If no agents exist AND domains detected: Generate agents silently." It assumes that every detected domain in the cache has a corresponding domain profile at `config/flux-drive/domains/{domain}.md`. But:
- Plugin version skew: user's cache says `game-simulation` detected, but they're running an old plugin version that doesn't have `game-simulation.md` yet
- Typo/corruption: cache says `game-simulaton` (typo), no matching profile exists
- Profile deleted: plugin maintainer removed a domain profile, but user's cache still references it

**Consequence**: Step 1.0b tries to read `config/flux-drive/domains/{domain}.md`, gets FileNotFoundError, crashes. flux-drive aborts before launching any agents.

**Alternative bad path**: Step 1.0b catches the error, skips agent generation, logs a warning. But Step 2.1a (domain context injection) **also** tries to read the domain profile to get injection criteria. Same FileNotFoundError. flux-drive crashes during agent prompt construction.

**Fix**: Add a validation step in Step 1.0b before agent generation:
1. For each detected domain in cache, check that `config/flux-drive/domains/{domain}.md` exists
2. If missing: log warning, remove that domain from the active domain list for this run
3. If **all** domains are missing: report to user, suggest re-running detect-domains with --no-cache

This is a defensive check. The cache-domain-profile inconsistency should be rare (only during plugin updates or manual cache edits), but when it happens, the failure mode should be "skip domain-specific features" not "crash."

---

### P2-1: STRUCTURAL_EXTENSIONS lacks common game/embedded formats

**Location**: Section 2, STRUCTURAL_EXTENSIONS definition

**Issue**: The plan defines:
```python
STRUCTURAL_EXTENSIONS = {
    ".gd", ".tscn", ".unity", ".uproject",
}
```
This covers Godot (.gd, .tscn), Unity (.unity), and Unreal (.uproject). But game-simulation projects often use:
- `.tres` (Godot resource files, often for game balance configs)
- `.godot` (Godot project metadata, similar to .uproject for Unreal)
- `.cs` (C# scripts in Unity/Godot)
- `.hlsl`, `.glsl`, `.wgsl` (shader files, structural for graphics-heavy games)
- `.asm`, `.s` (embedded systems, assembly)
- `.ld` (linker scripts for embedded systems)
- `.dts`, `.dtsi` (device tree source for embedded Linux)

If a project adds a `.tres` file defining a new game system, the staleness check won't trigger because `.tres` isn't in STRUCTURAL_EXTENSIONS.

**Consequence**: Domain-relevant structural changes are missed. Cache remains fresh when it should be stale.

**Fix**: Expand STRUCTURAL_EXTENSIONS to match the coverage in `index.yaml`'s detection signals:
```python
STRUCTURAL_EXTENSIONS = {
    # Game engines
    ".gd", ".tscn", ".tres", ".godot",  # Godot
    ".unity", ".prefab", ".asset",      # Unity
    ".uproject", ".uasset",             # Unreal
    ".cs", ".hlsl", ".glsl", ".wgsl",   # Scripts/shaders
    # Embedded systems
    ".asm", ".s", ".ld", ".dts", ".dtsi",
    # Mobile
    ".xcodeproj", ".storyboard", ".xib",  # iOS
}
```

Alternatively: instead of a hardcoded extension list, derive STRUCTURAL_EXTENSIONS from `index.yaml` by extracting all extensions mentioned in `files:` signals across all domains. This keeps the lists in sync automatically.

---

### P2-2: Git log filtering doesn't handle renames correctly

**Location**: Section 2, staleness detection step 4

**Issue**: The plan uses `git log --diff-filter=ACDR --name-only`. The `R` filter includes renames, so renamed files appear in the log. But git shows renames as:
```
old-path.txt
new-path.txt
```
The algorithm checks if either file is in STRUCTURAL_FILES or has a STRUCTURAL_EXTENSION. For a rename like `package.json → old-package.json.bak`:
- `package.json` is in STRUCTURAL_FILES → triggers stale
- But the file's **content** didn't change, just its name
- False positive: cache marked stale even though the project structure is identical

**Consequence**: Cosmetic renames (moving a file to a backup location, reorganizing directories) trigger unnecessary re-detection.

**Fix**: Use `git log --diff-filter=ACDM` (exclude R for renames). Handle renames separately with `git log --diff-filter=R --name-status`:
- Parse output: `R old-path new-path`
- If old-path is structural but new-path is NOT (file moved out of project scope) → stale
- If old-path is NOT structural but new-path IS (file moved into project scope) → stale
- If both are structural or neither is structural → not stale (just a rename)

This avoids false positives from cosmetic renames while still detecting structural reorganizations.

---

### P2-3: No handling for partial agent generation failures

**Location**: Section 1, Step 1.0b substep 3d

**Issue**: The plan says "Generate only new agents (don't touch existing)." But agent generation can fail partway through:
- Disk full during write → some agents created, others missing
- Permission error on `.claude/agents/` directory
- Domain profile exists but has malformed YAML in Agent Specifications section

**Interleaving**:
1. Detected domains: game-simulation, web-api
2. Generate fd-simulation-kernel → success
3. Generate fd-game-systems → disk full, write fails
4. Step 1.0b reports "Generated 1 project agent" and continues
5. flux-drive Step 1.2 (agent selection) looks for Project Agents, finds only fd-simulation-kernel
6. User expected fd-game-systems but it's silently missing

**Consequence**: Incomplete agent coverage. User doesn't realize an agent generation failed until they manually check `.claude/agents/`.

**Fix**: Track agent generation status per domain. After generation loop:
1. For each domain, check that **all** agents specified in the domain profile were successfully created
2. If any failed: log error with details (which agents, which domain, why)
3. Report summary: "Generated 1 of 2 agents for game-simulation (fd-game-systems failed: disk full)"
4. Optionally: add a `--strict` flag where partial failures abort flux-drive entirely

For Step 1.0b (silent generation), at minimum log the failure. For manual `/flux-gen`, report it to the user via AskUserQuestion.

---

## Improvements Suggested

### IMP-1: Add dry-run mode for staleness check debugging

**Rationale**: When staleness detection misbehaves (false positives, false negatives, infinite loops), users need visibility into **why** the check reported stale/fresh. The current design logs which signals triggered (step 5 in Section 2), but doesn't show intermediate state.

**Suggestion**: Add `--check-stale --dry-run` mode:
```bash
python3 detect-domains.py --check-stale {PROJECT_ROOT} --dry-run
```
Output:
```
Cache detected_at: 2026-02-12T10:15:32-08:00
Git log since 2026-02-12T10:15:32-08:00:
  - 2026-02-12T14:22:01 (after cutoff): src/game/combat.py
  - 2026-02-12T14:23:15 (after cutoff): package.json

Structural file changes:
  ✓ package.json (in STRUCTURAL_FILES)
  ✗ src/game/combat.py (not structural)

Verdict: STALE (package.json changed)
Exit code: 3
```
This makes debugging trivial. Users can see exactly which files triggered staleness and verify the logic is correct.

---

### IMP-2: Include hash algorithm identifier in cache

**Rationale**: Covered in P1-2. Even if you use SHA-256 today, algorithm requirements change (FIPS, performance, collision resistance updates). Embedding the algorithm makes cache format forward-compatible.

**Suggestion**: Change cache format from:
```yaml
structural_hash: 'a1b2c3d4'
```
to:
```yaml
structural_hash: 'sha256:a1b2c3d4'
hash_version: 1
```
Parsing:
```python
algo, hash_val = cached['structural_hash'].split(':', 1)
if algo != 'sha256':
    return "stale"  # incompatible hash
```

---

### IMP-3: Document cache corruption recovery procedure

**Rationale**: Despite atomic writes (P1-3 fix), corruption can still occur (disk errors, manual edits, YAML syntax errors). Users need a documented recovery path.

**Suggestion**: Add to Section 9 edge cases:

**Cache corruption**:
- **Detection**: `read_cache` returns None even though `.claude/flux-drive.yaml` exists
- **Recovery**:
  1. Backup the corrupted cache: `mv .claude/flux-drive.yaml .claude/flux-drive.yaml.corrupt`
  2. Re-run flux-drive: detection runs automatically, writes new cache
  3. If corruption persists: check disk health, filesystem errors
- **Prevention**: flux-drive writes caches atomically (temp file + rename). Corruption indicates hardware or manual edit issues.

**Cache vs. manifest mismatch** (if `.claude/flux-gen-manifest.json` is added per P1-1 fix):
- **Detection**: Manifest says fd-simulation-kernel exists for game-simulation, but file is missing or domain changed
- **Recovery**:
  1. Delete stale manifest: `rm .claude/flux-gen-manifest.json`
  2. Re-run `/flux-gen` to regenerate manifest and missing agents
- **Prevention**: Don't manually delete agents from `.claude/agents/` — use `/flux-gen` overwrite mode instead

---

## Overall Assessment

The integration design is sound but has critical correctness bugs in staleness detection (TOCTOU, date boundaries) and cache integrity (non-atomic writes, no collision handling). Agent lifecycle logic is brittle to user customization. Fix the P0 and P1 issues before shipping; P2 issues can be deferred to follow-up PRs. With corrections, this will be a robust caching and auto-generation system.

<!-- flux-drive:complete -->
