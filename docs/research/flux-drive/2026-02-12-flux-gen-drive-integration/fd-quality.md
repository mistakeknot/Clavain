# fd-quality Review: Flux-Gen + Flux-Drive Integration

## Findings Index
- P0 | P0-1 | "Step 1.0b Structure" | Step numbering collision with existing 1.0a creates ambiguous insertion point
- P0 | P0-2 | "Exit Code Convention" | Exit code 3 overloads meaning (stale vs. missing cache) violates single-responsibility
- P1 | P1-1 | "Test Plan" | Missing negative case for override:true + structural changes (should stay fresh)
- P1 | P1-2 | "Test Plan" | No integration test for flux-gen silent mode (confirmation bypass)
- P1 | P1-3 | "Terminology Inconsistency" | "structural_hash" in cache but "structural change detection" in algorithm mixes concepts
- P1 | P1-4 | "Git Dependency Edge Cases" | Plan assumes git log works but provides no fallback test when .git exists but is corrupted
- P1 | P1-5 | "Naming Convention" | STRUCTURAL_FILES and STRUCTURAL_EXTENSIONS violate project pattern (all caps constants in Python scripts)
- IMP | IMP-1 | "Test Coverage" | Add property-based test for structural hash determinism (same inputs → same hash regardless of file order)
- IMP | IMP-2 | "Performance Test" | Test plan budget claims < 100ms hash compare but provides no verification test
- IMP | IMP-3 | "User Experience" | Step 1.0b output examples lack timestamp context (when was cache last fresh?)
- IMP | IMP-4 | "Error Messaging" | When detect-domains.py unavailable, log says "skip Step 1.0b" but doesn't explain why auto-gen won't work
Verdict: needs-changes

---

## Summary

This plan introduces meaningful integration between flux-gen and flux-drive but contains **critical naming and convention violations** that will degrade codebase maintainability. The Step 1.0b numbering collides with existing 1.0a, exit code 3 conflates two distinct failure modes (stale vs. missing), and the test plan omits key negative cases that validate override:true behavior. The structural hash approach is sound but uses naming patterns inconsistent with the existing Python codebase.

**Most severe**: The exit code design violates the existing convention established at line 8-11 of detect-domains.py where each exit code maps to exactly one semantic meaning. Exit code 3 meaning both "cache is stale" AND "no cache exists" breaks this contract and will cause confusion when debugging failures.

---

## Issues Found

### P0-1: Step numbering collision creates ambiguous insertion point

**Location:** Design Section 1, "New Step 1.0b in flux-drive SKILL.md"

**Issue:** The plan proposes inserting "Step 1.0b" between existing "Step 1.0a" (line 67-90 of flux-drive SKILL.md) and "Step 1.1" (line 92). However, the skill file already uses decimal notation for primary steps (1.0, 1.1, 1.2) and letter suffixes for sub-steps within a parent (1.0a for domain classification). This creates three problems:

1. **Semantic confusion**: Is "1.0b" a sibling of "1.0a" (both sub-steps under a parent "1.0"), or is it a distinct primary step between 1.0 and 1.1?
2. **Insertion location ambiguity**: Current text says "Insert between Step 1.0a and Step 1.1" but if both are sub-steps of 1.0, this contradicts the existing structure where 1.0a IS the only sub-step (the parent Step 1.0 is "Understand the Project" at line 45).
3. **Navigation fragility**: Developers reading "go to Step 1.0b" will not know if that's under "Step 1.0: Understand the Project" or a standalone step.

**Why this is P0**: Ambiguous step references in a multi-phase skill with background agent dispatch will cause integration failures when agents are told "see Step 1.0b for domain context" but cannot locate it.

**Correct approach (choose one consistently):**
- **Option A (sibling sub-steps)**: Rename 1.0a → 1.0.1 and 1.0b → 1.0.2, make both children of "Step 1.0: Pre-analysis Setup"
- **Option B (sequential primary steps)**: Rename 1.0a → 1.0 and 1.0b → 1.1, shift all following steps +1 (old 1.1 becomes 1.2, etc.)

**Recommended**: Option A maintains existing phase boundaries (Phase 1 = Analyze + Static Triage) and avoids renumbering 20+ step references across 4 phase files.

---

### P0-2: Exit code 3 overloads meaning, violates single-responsibility convention

**Location:** Design Section 2, "detect-domains.py: Add --check-stale flag" exit codes table

**Issue:** The plan proposes exit code 3 with meaning "Cache is stale — structural changes detected since last scan." However, in the algorithm description (lines after the exit code table), the plan says:

> 2. If no cache exists → exit 3 (stale by definition)

This means exit code 3 conflates two distinct conditions:
- **Condition A**: Cache exists but is outdated (true staleness)
- **Condition B**: No cache exists at all (missing, not stale)

**Why this violates convention**: The existing detect-domains.py (lines 8-11) establishes a clear exit code contract:
```python
Exit codes:
    0  Domains detected
    1  No domains detected (caller should use LLM fallback)
    2  Fatal error
```

Each exit code maps to exactly one semantic state. The plan's overloaded exit code 3 breaks this pattern.

**Why this is P0**: Flux-drive Step 1.0b will receive exit code 3 and cannot distinguish "re-detect because project changed" from "detect for the first time because user deleted cache." These require different logging:
- Stale → "Cache outdated, re-detecting..."
- Missing → "No cache, detecting domains..."

Current plan's Step 1.0b pseudocode checks `exit 3` → re-run detection, which is correct for stale but will also trigger on missing cache (where the user might have intentionally deleted it to force LLM fallback or override mode).

**Correct approach**: Use distinct exit codes:
- **Exit 0**: Cache fresh
- **Exit 1**: No domains detected (existing)
- **Exit 2**: Fatal error (existing)
- **Exit 3**: Cache is stale (structural changes)
- **Exit 4**: No cache exists

Flux-drive Step 1.0b handles 3 and 4 identically (run detection) but logs them differently.

**Alternative (if exit code space is constrained)**: Keep exit 3 but add `--check-stale` flag to print structured JSON on stdout distinguishing the cases:
```json
{"status": "stale", "reason": "structural_files_changed", "files": ["package.json"]}
{"status": "missing", "reason": "no_cache"}
```

---

### P1-1: Test plan missing negative case for override:true + structural changes

**Location:** Design Section 8, "Test plan" → "Unit tests (detect-domains.py)"

**Issue:** The test plan includes `test_check_stale_override_true` → exit 0, verifying that override:true always reports fresh. However, it does not test the interaction between override:true AND structural file changes.

**Scenario not covered**:
1. Cache exists with `override: true` and `domains: [{custom}]`
2. User modifies package.json (structural file change)
3. `--check-stale` runs
4. **Expected behavior per plan**: exit 0 (line 4 of algorithm says "If override: true in cache → exit 0")
5. **Missing verification**: Test does not verify that structural hash computation is SKIPPED when override:true (performance contract)

**Why this is P1**: The plan claims "If override: true → never stale" at lines 3-4 of the algorithm but does not specify if structural hash is computed before the override check or short-circuited. This affects the performance budget (structural hash takes ~50-100ms for large projects, override check takes ~1ms).

**Add test**:
```python
def test_check_stale_override_true_skips_hash_computation(self, tmp_path, monkeypatch):
    """When override:true, --check-stale exits 0 without computing hash."""
    cache = tmp_path / "flux-drive.yaml"
    cache.write_text("override: true\ndomains:\n  - name: custom\ndetected_at: '2020-01-01'\n")
    (tmp_path / "package.json").write_text('{"name": "test"}')  # structural change

    hash_called = False
    original_hash = detect_domains._compute_structural_hash
    def spy_hash(*args):
        nonlocal hash_called
        hash_called = True
        return original_hash(*args)
    monkeypatch.setattr(detect_domains, "_compute_structural_hash", spy_hash)

    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), "--check-stale"])
    assert result.returncode == 0
    assert not hash_called  # Performance contract: override short-circuits hash
```

---

### P1-2: No integration test for flux-gen silent mode (confirmation bypass)

**Location:** Design Section 8, "Test plan" → "Integration tests (shell)"

**Issue:** Step 1.0b's algorithm (section 3.d) says:
> Generate agents silently (skip flux-gen's AskUserQuestion confirmation)

But the test plan has no integration test verifying that:
1. When flux-drive auto-generates agents, the user is NOT prompted
2. The confirmation bypass only applies during flux-drive dispatch (not standalone `/flux-gen`)

**Why this is P1**: The implementation path is unclear:
- Does flux-gen.md gain a `--no-confirm` flag?
- Does flux-drive pass a different argument?
- Is confirmation skipped based on an environment variable?

Without a test, the integration could break in two ways:
- **False positive**: flux-drive prompts user mid-review (blocks background agents)
- **False negative**: standalone `/flux-gen` skips confirmation when it shouldn't (violates user consent)

**Add tests**:
```bash
@test "flux-drive auto-gen skips confirmation" {
  # Setup: project with domains detected, no .claude/agents/
  result=$(flux-drive plan.md 2>&1)
  [[ "$result" =~ "Generated 2 project agents" ]]
  [[ ! "$result" =~ "Generate N new agents" ]]  # No confirmation prompt
}

@test "standalone flux-gen still prompts" {
  result=$(echo "Cancel" | flux-gen)
  [[ "$result" =~ "Generate N new agents" ]]  # Prompt appears
}
```

---

### P1-3: Terminology inconsistency between "structural_hash" and "structural change detection"

**Location:** Design Sections 2 and 4

**Issue:** Section 2 introduces "Structural change detection" as an algorithm using git log to find modified files. Section 4 introduces `structural_hash` as a cache field. These names imply two different mechanisms:
- **"structural change detection"** (algorithmic, comparative)
- **"structural_hash"** (content-based, deterministic)

But the plan describes them as equivalent (Section 4: "The structural_hash is computed from the concatenated contents of all STRUCTURAL_FILES that exist").

**Why this is P1 (not IMP)**: The plan switches between these terms when describing the same concept, creating confusion about whether:
1. Both mechanisms coexist (git-based staleness check AND hash-based staleness check)
2. Hash is a cache optimization for the git-based check
3. They are completely synonymous

**Example confusion**: Section 2's algorithm says "Filter results: Any file in STRUCTURAL_FILES changed? → stale" (implies git log parsing). Section 4 says "recompute the hash and compare — if different, cache is stale" (implies content hashing). These are not the same — git log can detect renames/deletions without content change, hash cannot.

**Correct approach (choose one consistently)**:
- **Option A (git-based)**: Remove `structural_hash` from cache, use git log exclusively (supports renames, works in sparse checkouts)
- **Option B (hash-based)**: Remove git dependency, use content hash exclusively (works in non-git projects, deterministic)
- **Option C (hybrid, recommended)**: Rename `structural_hash` → `structural_snapshot` and document that it's a *cached version* of the git-based check result (not a hash of file contents). The "hash" is actually a timestamp-based cache key.

**If Option C**: Replace Section 4's description:
```yaml
structural_snapshot: '2026-02-12'  # NEW: date of last successful structural scan
```

This aligns with the existing `detected_at` field and avoids implying a hash function exists.

---

### P1-4: Git dependency edge cases not covered in fallback logic

**Location:** Design Section 2, "Structural change detection" algorithm step 4

**Issue:** The plan's git-based staleness check says:
> 4. Run: `git log --since="{detected_at}" --diff-filter=ACDR --name-only --format="" HEAD`

But provides fallback only for "no .git directory" (Section 9, "Edge cases" table). It does not handle:
1. `.git` exists but is corrupted (git log fails with exit code 128)
2. `.git` is a worktree reference file (git log works but filters are unsupported)
3. Shallow clone where `--since` date is before clone depth (git log returns empty result even if files changed)
4. Detached HEAD state (HEAD is a commit SHA, not a branch)

**Why this is P1**: These cases are common in CI/CD environments (shallow clones, detached HEAD) and will cause `--check-stale` to exit 2 (fatal error per plan's exit code table), which flux-drive interprets as "skip Step 1.0b entirely" (Section 8 edge cases table). This means a corrupted .git on a developer's machine would silently skip agent auto-generation.

**Correct approach**: Add error handling to Section 2's algorithm:
```
4. Run: git log --since="{detected_at}" --diff-filter=ACDR --name-only --format="" HEAD
   a. If exit code != 0 (git error):
      - Log warning: "Git unavailable (exit $?), assuming stale"
      - Exit 3 (stale)
   b. If exit code == 0 but output is empty:
      - Check: has structural_hash in cache?
        - Yes: use hash comparison (hash-based fallback)
        - No: exit 3 (stale by default, conservative)
```

This converts git errors into "assume stale" (conservative, triggers re-detection) rather than "fatal error" (skips integration entirely).

**Add tests**:
```python
@test "check-stale with corrupted .git assumes stale" {
  rm -rf .git/objects/*  # Corrupt git repo
  result=$(detect-domains.py . --check-stale)
  [[ $? -eq 3 ]]  # Stale, not fatal error
}

@test "check-stale in shallow clone uses hash fallback" {
  # Simulate shallow clone where --since is before clone depth
  git clone --depth 1 <repo> shallow
  result=$(detect-domains.py shallow --check-stale)
  [[ $? -eq 0 || $? -eq 3 ]]  # Either fresh or stale, not fatal
}
```

---

### P1-5: STRUCTURAL_FILES and STRUCTURAL_EXTENSIONS violate Python naming convention

**Location:** Design Section 2, "Structural change detection" → STRUCTURAL_FILES constant

**Issue:** The plan proposes:
```python
STRUCTURAL_FILES = {
    "package.json", "Cargo.toml", ...
}
```

The existing detect-domains.py uses:
```python
W_DIR = 0.3
W_FILE = 0.2
W_FRAMEWORK = 0.3
W_KEYWORD = 0.2
SOURCE_EXTENSIONS = {".py", ".go", ...}
```

**Convention established**:
- **ALL_CAPS** for module-level constants (weights, configuration)
- **ALL_CAPS_PLURAL** for sets (SOURCE_EXTENSIONS)

But the project also uses **lowercase_with_underscores** for module-level variables that are data structures (lines 31-32: `PLUGIN_ROOT`, `DEFAULT_INDEX`).

**Why this is P1 (not IMP)**: PEP 8 recommends ALL_CAPS for constants, but the existing codebase is inconsistent (PLUGIN_ROOT is a constant Path, not a variable). Adding `STRUCTURAL_FILES` perpetuates this inconsistency and makes the distinction between "configuration constants" (weights) and "data constants" (file lists) unclear.

**Correct approach**: Since the existing code uses ALL_CAPS for configuration and data structures interchangeably, and this plan adds similar data structures, maintain consistency with existing pattern:
- Keep `STRUCTURAL_FILES` (matches `SOURCE_EXTENSIONS`, line 41)
- Keep `STRUCTURAL_EXTENSIONS` (matches `SOURCE_EXTENSIONS`)

But add a docstring comment to both explaining their purpose:
```python
# Files whose presence/absence indicates structural project changes
STRUCTURAL_FILES = {
    "package.json", "Cargo.toml", ...
}

# File extensions indicating structural project type changes (new tech stack)
STRUCTURAL_EXTENSIONS = {
    ".gd", ".tscn", ".unity", ".uproject",
}
```

This is a P1 (not P0) because it doesn't break functionality, but it does reduce clarity for future maintainers who need to understand the difference between SOURCE_EXTENSIONS (scanned for keywords) and STRUCTURAL_EXTENSIONS (tracked for staleness).

---

## Improvements Suggested

### IMP-1: Add property-based test for structural hash determinism

**Rationale:** Section 4 claims "same inputs → same hash" but the test plan only has a unit test `test_structural_hash_deterministic` with a single fixture. Property-based testing would verify this across:
- File order permutations (hash should ignore file discovery order)
- Content whitespace variations (should normalize or fail explicitly)
- Missing vs. empty file (should treat differently)

**Suggested test (using Hypothesis)**:
```python
from hypothesis import given, strategies as st

@given(st.permutations(["package.json", "Cargo.toml", "go.mod"]))
def test_structural_hash_ignores_file_order(self, tmp_path, file_order):
    for f in file_order:
        (tmp_path / f).write_text(f'contents of {f}')
    hash1 = _compute_structural_hash(tmp_path)

    # Shuffle files by renaming and re-creating
    for f in reversed(file_order):
        (tmp_path / f).unlink()
    for f in file_order:
        (tmp_path / f).write_text(f'contents of {f}')
    hash2 = _compute_structural_hash(tmp_path)

    assert hash1 == hash2
```

---

### IMP-2: Add performance verification test for < 100ms budget

**Rationale:** Section 5 "Performance budget" claims `--check-stale` (hash compare) takes < 100ms, but the test plan has no verification. A performance regression test would catch hash algorithm changes that violate this contract.

**Suggested test**:
```python
import time

def test_check_stale_performance_budget(self, tmp_path):
    """--check-stale completes in < 100ms on typical project."""
    # Create realistic project: 20 structural files, 1KB each
    for f in ["package.json", "Cargo.toml", "go.mod", "pyproject.toml"]:
        (tmp_path / f).write_text("x" * 1024)
    for i in range(16):
        (tmp_path / f"config{i}.toml").write_text("x" * 1024)

    # Run detection to create cache
    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), "--no-cache"])

    # Measure --check-stale
    start = time.perf_counter()
    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), "--check-stale"])
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1  # 100ms budget
```

Run this test in CI to detect performance regressions.

---

### IMP-3: Add timestamp to Step 1.0b user-facing output

**Rationale:** Section 6 "User-facing changes" shows:
```
Domain check: game-simulation (0.65), cli-tool (0.35) — fresh
```

But users seeing "fresh" have no context for when the cache was last updated. If the cache is from 3 months ago, "fresh" is misleading even if no structural files changed.

**Suggested enhancement**:
```
Domain check: game-simulation (0.65), cli-tool (0.35) — fresh (scanned 2026-02-09)
```

Pull `detected_at` from cache and include it in the status line. This helps users understand if the cache is outdated due to non-structural changes (new features, refactorings) that don't trigger staleness but might warrant manual re-detection.

---

### IMP-4: Clarify "detect-domains.py not available" error message

**Rationale:** Section 9 "Edge cases" says:
> detect-domains.py not available (path issue) | Skip Step 1.0b entirely, log warning

But the warning text isn't specified. A vague "detection failed" message won't help users fix the problem. Suggest:

```
Warning: Domain detection unavailable (detect-domains.py not found in plugin).
  → Agent auto-generation skipped. To enable:
    1. Verify Clavain plugin installation: ls $CLAUDE_PLUGIN_ROOT/scripts/
    2. Or run /flux-gen manually after fixing plugin paths
  → Proceeding with core agents only (no domain-specific agents)
```

This tells users:
1. What failed (detection script missing)
2. How to diagnose (check plugin root)
3. What the impact is (no auto-gen, manual /flux-gen still works)
4. What will happen next (core agents only)

---

## Overall Assessment

The integration design is architecturally sound but undermines codebase quality through inconsistent naming (exit codes, step numbering, terminology) and incomplete test coverage for critical negative cases (override behavior, silent mode, git edge cases). The structural hash approach is clever but conflates with git-based detection in the naming and description. Fix P0 issues (step numbering, exit codes) before implementation to avoid integration brittleness and debugging confusion.

<!-- flux-drive:complete -->
