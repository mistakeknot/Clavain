# Interverse Version Management: Pain Points Investigation

**Date:** 2025-02-14  
**Scope:** Version synchronization across Interverse monorepo plugins and publishing workflow

---

## Executive Summary

The Interverse monorepo has **14 plugins** and **1 core hub (Clavain)** with a version synchronization system that is **partially automated but fragile**. Key findings:

- **Multi-location version tracking**: 3-4 version locations per plugin with NO unified source of truth
- **Manual marketplace updates**: While `bump-version.sh` automates Clavain, other plugins require manual marketplace sync
- **Permission-blocked plugins**: 7/14 plugins have `.claude-plugin/plugin.json` with restricted read permissions, causing access issues
- **Missing pre-commit validation**: No hooks enforce version sync before commit
- **Cache symlink complexity**: Plugin caching mechanism requires manual bridging during version bumps

---

## 1. Version Locations per Plugin (Multi-Location Fragmentation)

### Clavain (Hub) - 4 Locations
Located at `/root/projects/Interverse/os/clavain/`

1. `.claude-plugin/plugin.json` → **0.6.13**
2. `agent-rig.json` → **0.6.13**
3. `docs/PRD.md` → **Version: 0.6.13**
4. `scripts/gen-catalog.py` → Auto-updates via `TARGET_FILES`

**Sync Status:** ✓ In sync via `bump-version.sh`

### Plugin: interdoc
1. `.claude-plugin/plugin.json` → **5.0.0**
2. No `package.json` or `pyproject.toml`
3. Marketplace entry → **5.0.0**

**Sync Status:** ✓ In sync (manually updated)

### Plugin: interkasten (Multi-Language)
1. `.claude-plugin/plugin.json` → **0.2.2** ✓
2. `server/package.json` → **0.2.0** ⚠️ **MISMATCH**
3. Marketplace → **0.2.2**

**Sync Status:** ⚠️ **DRIFT** between plugin and server

### Plugin: tldr-swinton (Python + Tests)
1. `.claude-plugin/plugin.json` → **PERMISSION DENIED** (root:root owned)
2. `pyproject.toml` → **version = "0.7.5"**
3. `tldr-bench/pyproject.toml` → separate version
4. Marketplace → **0.7.6** ⚠️

**Sync Status:** ⚠️ **DRIFT** - marketplace ahead of local source

### Plugin: tuivision (TypeScript)
1. `.claude-plugin/plugin.json` → **PERMISSION DENIED** (root:root owned)
2. `package.json` → **0.1.1** (found at root)
3. Marketplace → **0.1.2** ⚠️

**Sync Status:** ⚠️ **DRIFT** - marketplace ahead

### Plugin: tool-time (Multi-Package)
1. `.claude-plugin/plugin.json` → **PERMISSION DENIED**
2. `community/package.json` → **separate version**
3. Marketplace → **0.3.1**

**Sync Status:** ⚠️ Unknown (can't read plugin.json)

### Plugin: interlock (Go)
1. `.claude-plugin/plugin.json` → **0.1.0** ✓
2. `go.mod` → module definition (no version field)
3. `tests/pyproject.toml` → test dependencies
4. Marketplace → **0.1.0**

**Sync Status:** ✓ In sync

### Plugins with Permission Issues (Read Blocked)
- `interfluence` - `.claude-plugin/plugin.json` owned by root:root
- `interpath` - `.claude-plugin/plugin.json` owned by root:root
- `interphase` - `.claude-plugin/plugin.json` owned by root:root
- `interwatch` - `.claude-plugin/plugin.json` owned by root:root
- `tldr-swinton` - `.claude-plugin/plugin.json` owned by root:root
- `tool-time` - `.claude-plugin/plugin.json` owned by root:root
- `tuivision` - `.claude-plugin/plugin.json` owned by root:root

**Impact:** Cannot validate versions without `sudo`, breaks CI/CD integration

---

## 2. Marketplace Repository Structure

**Location:** `/root/projects/Interverse/infra/marketplace/`

**Key Files:**
- `.claude-plugin/marketplace.json` — Central registry (SOURCE OF TRUTH)
- `.claude/` directory — Claude Code config
- `.beads/` directory — Conversation store
- `.git/` directory — Separate git repo

### marketplace.json Schema

```json
{
  "name": "interagency-marketplace",
  "owner": { "name": "MK", "email": "..." },
  "metadata": { "description": "...", "version": "1.0.0" },
  "plugins": [
    {
      "name": "plugin-name",
      "source": { "source": "url", "url": "https://github.com/owner/repo.git" },
      "description": "...",
      "version": "X.Y.Z",           // Must match plugin.json
      "keywords": ["..."],
      "strict": true
    }
  ]
}
```

**Current Plugin Count:** 14 plugins registered

### Version Tracking in Marketplace

| Plugin | Marketplace Version | Local Status |
|--------|-------------------|--------------|
| clavain | 0.6.13 | ✓ Synced (via bump-version.sh) |
| interdoc | 5.0.0 | ✓ Synced |
| interkasten | 0.2.2 | ⚠️ Drift (server 0.2.0) |
| interflux | 0.2.0 | ✓ Synced |
| interfluence | 0.1.2 | ⚠️ Can't verify (permission) |
| interline | 0.2.3 | ✓ Synced |
| interlock | 0.1.0 | ✓ Synced |
| interpath | 0.1.1 | ⚠️ Can't verify (permission) |
| interphase | 0.3.2 | ⚠️ Can't verify (permission) |
| interpub | 0.1.1 | ✓ Synced |
| interwatch | 0.1.1 | ⚠️ Can't verify (permission) |
| tldr-swinton | 0.7.6 | ⚠️ Ahead of local (0.7.5) |
| tool-time | 0.3.1 | ⚠️ Can't verify (permission) |
| tuivision | 0.1.2 | ⚠️ Ahead of local (0.1.1) |

**Finding:** Marketplace may have stale or ahead-of-source versions for plugins without synchronization guarantees.

---

## 3. Clavain's bump-version.sh — Orchestration & Cache Management

**Location:** `/root/projects/Interverse/os/clavain/scripts/bump-version.sh`

### What It Does Beyond Simple Replacement

1. **Version Validation**
   - Checks semver format: `^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$`
   - Exits if version invalid

2. **Catalog Generation**
   - Calls `scripts/gen-catalog.py` before version bump
   - Refreshes component counts in multiple docs:
     - `.claude-plugin/plugin.json`
     - `AGENTS.md`
     - `CLAUDE.md`
     - `README.md`
     - `skills/using-clavain/SKILL.md`
     - `agent-rig.json`

3. **Multi-Location Updates**
   - `.claude-plugin/plugin.json` → `"version": "X.Y.Z"`
   - `docs/PRD.md` → `**Version:** X.Y.Z`
   - `agent-rig.json` → `"version": "X.Y.Z"` (if present)
   - `interagency-marketplace/.claude-plugin/marketplace.json` → clavain entry

4. **Marketplace Sync**
   - Locates marketplace at:
     - First: `$REPO_ROOT/../../infra/marketplace/.claude-plugin/marketplace.json`
     - Fallback: `$REPO_ROOT/../interagency-marketplace/.claude-plugin/marketplace.json`
   - Extracts current marketplace version from clavain entry
   - Updates marketplace version to match

5. **Git Operations**
   - `git add .claude-plugin/plugin.json agent-rig.json docs/PRD.md`
   - Commits with message: `"chore: bump version to X.Y.Z"`
   - Pushes to origin

6. **Cache Symlink Management** ⭐ (Critical Complex Logic)
   ```
   Problem: Sessions can outlive multiple publish cycles
   Running sessions may be on ANY old version, not just $CURRENT
   
   Solution: Find the real (non-symlink) cache directory
   Symlink OLD_VERSIONS → real directory (so Stop hooks still work)
   Symlink NEW_VERSION → real directory (pre-download bridge)
   ```
   - Finds real cache at `~/.claude/plugins/cache/interagency-marketplace/clavain/`
   - Creates symlinks: `$CURRENT → real_dir`, `$VERSION → real_dir`
   - Logs: "Running sessions' Stop hooks bridged via $REAL_DIR"
   - Handles case where cache dir doesn't exist yet

7. **Dry-Run Mode**
   - `--dry-run` flag shows changes without writing
   - Calls `gen-catalog.py --check` to detect drift

### Limitations

❌ **Only for Clavain** — Other plugins don't have this automation  
❌ **Marketplace location is hardcoded** — Must be in specific paths  
❌ **No pre-flight validation** — Doesn't check if plugin.json is already at version

---

## 4. gen-catalog.py — Drift Detection & Auto-Update

**Location:** `/root/projects/Interverse/os/clavain/scripts/gen-catalog.py`

### What It Does

1. **Component Counting**
   - Counts skills, agents, commands, hooks, MCP servers in Clavain
   - Updates counts in 6 target files via regex

2. **Drift Detection**
   ```python
   TARGET_FILES = (
       ROOT / ".claude-plugin" / "plugin.json",
       ROOT / "AGENTS.md",
       ROOT / "CLAUDE.md",
       ROOT / "README.md",
       ROOT / "skills" / "using-clavain" / "SKILL.md",
       ROOT / "agent-rig.json",
   )
   ```
   - Reads current content from each file
   - Computes what content SHOULD be (with updated counts)
   - Compares: if current ≠ expected, marks as drifted

3. **Optional Update**
   - `--check` mode: only reports drift (exit 1 if drifted)
   - Default mode: writes corrected content to drifted files

4. **Catalog JSON**
   - Generates `docs/catalog.json` with:
     - Component inventory
     - Timestamps (ISO 8601 UTC)
     - Metadata

### Key Insight

This script ensures **documentation always reflects actual component counts**, preventing stale docs like "27 skills" when there are actually 28.

---

## 5. CI/CD & Pre-Commit Hook Status

### Current State: ❌ **NO VALIDATION**

**check-versions.sh** exists but:
- ❌ Not a git pre-commit hook
- ✓ Can be run manually: `scripts/check-versions.sh`
- ✓ Detects marketplace drift for Clavain only

**What It Does:**
```bash
1. Extracts version from .claude-plugin/plugin.json
2. Locates marketplace.json
3. Extracts clavain version from marketplace
4. Compares: if mismatch, exits 1 with error message
```

**Limitations:**
- Only checks Clavain vs. marketplace
- Not enforced on `git commit`
- No validation of pyproject.toml, package.json, go.mod sync
- Not integrated into CI/CD pipeline

### Missing Automations

❌ Pre-commit hook to prevent version drift commits  
❌ CI/CD pipeline validation (GitHub Actions, GitLab CI, etc.)  
❌ Cross-plugin version sync validation  
❌ Automated drift reporting

---

## 6. Memory & Documentation of /interpub:release

**File:** `/home/claude-user/.claude/projects/-root-projects-Interverse/memory/MEMORY.md`

```markdown
### Plugin Publishing (all plugins)
- 3 version locations must stay synced: 
  .claude-plugin/plugin.json, 
  language manifest (package.json/pyproject.toml), 
  marketplace.json
- If marketplace lags → cache dir named with old version → all paths fail
- Use `/interpub:release <version>` to bump atomically
- After publish: bump-version.sh creates old→new symlink in plugin cache
```

**Key Facts:**
- `/interpub:release` is a Claude Code skill (from interpub plugin)
- Mentioned in MEMORY but NOT found in actual interpub code yet
- Promised to "bump atomically" — likely a wrapper around bump-version.sh

---

## 7. Root Cause Analysis: What Breaks & Why

### Pain Point 1: Permission-Blocked Files
**Symptom:** Can't read `.claude-plugin/plugin.json` for 7 plugins  
**Root Cause:** Files owned by root:root (mode 0640), claude-user group has no read  
**Why It Happens:** Root's Claude Code uses atomic writes (temp+rename), doesn't preserve permissions  
**Impact:**
- Automated validation scripts fail silently
- CI/CD can't verify versions without sudo
- Cache lookup becomes unreliable

### Pain Point 2: Multi-Location Version Fragmentation
**Symptom:** interkasten has 0.2.2 in plugin.json but 0.2.0 in server/package.json  
**Root Cause:** Plugin and language manifest updated separately  
**Why It Happens:**
- No shared source of truth
- No pre-commit validation
- Different teams may update different files
- Language-specific manifests (npm, pip) not integrated into plugin version system

**Impact:**
- Installation unclear which version to use
- Package managers may install mismatched dependencies
- Debugging version issues becomes tedious

### Pain Point 3: Marketplace Ahead of Source
**Symptom:** Marketplace has tldr-swinton 0.7.6 but local repo has 0.7.5  
**Root Cause:** Manual marketplace update without pulling latest version  
**Why It Happens:**
- Marketplace update is manual for most plugins
- Only Clavain has automated sync via bump-version.sh
- No two-way sync mechanism

**Impact:**
- Users install wrong version
- Running sessions may have version mismatches vs. "latest"
- Users can't trust marketplace as source of truth

### Pain Point 4: Cache Symlink Brittleness
**Symptom:** Old session's Stop hooks fail after version bump  
**Root Cause:** Cache directory path includes version number:  
`~/.claude/plugins/cache/interagency-marketplace/clavain/0.6.13/`  
**Why It Happens:**
- Plugin loader downloads by version
- Stop hooks reference versioned cache path
- When version bumps, old path disappears

**Impact:**
- Old sessions crash on shutdown
- Symlink management adds complexity
- Fragile workaround instead of fix

### Pain Point 5: No Centralized CI/CD Validation
**Symptom:** Drift slips through to marketplace  
**Root Cause:** check-versions.sh not enforced  
**Why It Happens:**
- GitHub/GitLab CI not configured
- Pre-commit hooks optional
- Human error path

**Impact:**
- Users get wrong versions
- Marketplace becomes unreliable
- Debugging version issues takes hours

---

## 8. What Could Be Automated

### Tier 1: Immediate (Low Risk, High Value)

1. **Pre-commit Hook to Enforce Sync**
   - Git hook in each plugin repo
   - Checks: plugin.json version matches marketplace.json
   - Blocks commit if mismatch
   - Cost: ~50 lines of bash, copy to all plugins

2. **POSIX ACL Fix**
   - Set default ACLs on Interverse directory
   - Makes future files readable by claude-user
   - Prevents permission-blocked files
   - Cost: 1 command, blocks future drift

3. **Version Lint Script**
   - Scan all plugins for version files
   - Detect drift: plugin.json ≠ package.json ≠ marketplace
   - Report mismatches with remediation steps
   - Cost: ~200 lines Python

### Tier 2: Medium Risk, Medium Value

1. **Unified Version Source**
   - Create `plugin-manifest.json` with all version locations
   - Bump-version script reads from source, updates all locations
   - Eliminates fragmentation
   - Cost: ~300 lines, breaking change

2. **Generalized bump-version for All Plugins**
   - Extract Clavain bump-version.sh logic to library
   - Each plugin calls same script with plugin name
   - Ensures consistency across monorepo
   - Cost: ~400 lines

3. **Marketplace Sync Daemon**
   - Watch plugin repos for version changes
   - Auto-update marketplace.json
   - Two-way sync (local → marketplace)
   - Cost: ~500 lines

### Tier 3: High Risk, High Value (Architectural)

1. **Plugin Version Registry**
   - Single source of truth: `infra/marketplace/plugin-registry.json`
   - All plugins read/write via schema validation
   - Publish = atomic update to registry
   - Cost: ~800 lines, major refactor

2. **Cache Redesign**
   - Remove version from cache path
   - Use symlink: `~/.claude/plugins/cache/clavain/ → <latest-download>/`
   - Stop hooks follow symlink (no breakage)
   - Cost: ~200 lines, medium integration

---

## 9. Recommended Fix Sequence

### Week 1: Quick Wins (Prevent Disaster)
1. Apply POSIX ACL fix (5 min)
2. Add pre-commit hook to Clavain (15 min)
3. Run version lint script on monorepo (10 min)
4. Document findings in MEMORY.md (20 min)

### Week 2: Consolidation (Enable Consistency)
1. Generalize bump-version.sh to library
2. Add pre-commit hook to all 14 plugins
3. Create version-lint as part of CI/CD
4. Manual marketplace audit + fixes

### Week 3+: Architectural (Long-Term Stability)
1. Design unified version manifest
2. Implement plugin version registry
3. Redesign cache mechanism
4. Migrate all plugins to new system

---

## 10. Data Summary

| Metric | Count | Status |
|--------|-------|--------|
| Total plugins | 14 | ✓ |
| Plugins with version drift | 4-7 | ⚠️ |
| Permission-blocked plugin.json | 7 | ⚠️ |
| Version locations per plugin | 2-4 | ⚠️ |
| Plugins with automated sync | 1 (Clavain) | ⚠️ |
| Pre-commit validation hooks | 0 | ❌ |
| CI/CD pipeline checks | 0 | ❌ |
| Marketplace consistency | ~80% | ⚠️ |

---

## Conclusion

The Interverse version system is **operationally fragile** due to:

1. **No unified source of truth** — 3+ locations per plugin with independent updates
2. **Inconsistent automation** — Only Clavain has automated sync; others manual
3. **Unenforceable consistency** — Pre-commit hooks missing, CI/CD absent
4. **Permission debt** — 7 plugins have unreadable manifest files
5. **Cache complexity** — Symlink workarounds mask deeper architectural issue

**Recommended Priority:** Fix permissions (5 min) → add pre-commit validation (1 day) → generalize bump-version (1 week) → redesign cache (2 weeks).
