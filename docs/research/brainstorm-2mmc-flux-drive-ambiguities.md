# Brainstorm: Clarify flux-drive instruction ambiguities (Clavain-2mmc)

## Context

10 documentation + hardening fixes from the v0.5.4 quality reviews (fd-quality + fd-correctness). These are all P1/P2 clarifications — no new features, no architectural changes. The goal is to make flux-drive instructions unambiguous before extracting them into a standalone spec (Phase 1 of Clavain-o4ix).

## Issue Inventory

### From fd-quality review (issues 1-6)

**Issue 1: Step 1.0.2 exit code 1 handling unclear**
- **Current**: SKILL.md line 104 says exit 1 → "No domains detected. Skip agent generation entirely. Proceed to Step 1.1."
- **Problem**: Does "skip agent generation" mean skip Step 1.0.3 AND 1.0.4, or just 1.0.4? Reads ambiguously.
- **Fix**: Add explicit note: "Exit 1 → proceed to Step 1.1, skipping Steps 1.0.3 and 1.0.4. Use core plugin agents only."
- **Location**: `skills/flux-drive/SKILL.md` line 104

**Issue 2: Step 1.0.3 'change flag' referenced but implicitly handled**
- **Current**: SKILL.md line 122 says "Proceed to Step 1.0.4 with change flag set" but Step 1.0.4 never explicitly reads a "change flag" — it uses the decision matrix (cases a/b/c) which implicitly handles it.
- **Problem**: "change flag" sounds like a variable that should be set somewhere. Confusing for implementers.
- **Fix**: Replace "with change flag set" with "for domain-shift handling (case b)". Step 1.0.4 already has the logic — just need to connect the reference.
- **Location**: `skills/flux-drive/SKILL.md` line 122

**Issue 3: Orphan agent handling incomplete in Step 1.0.4**
- **Current**: Step 1.0.4 case b (line 141-144) says "Identify orphaned agents (domain removed)" but doesn't say what to DO with them.
- **Problem**: Should orphaned agents be deleted? Skipped? Reported? The instruction just identifies them.
- **Fix**: Add "report but do NOT delete" instruction. Users may have customized orphaned agents. Log: "Orphaned agents (domain no longer detected): [list]. These agents will NOT be included in triage. Delete manually if unwanted."
- **Location**: `skills/flux-drive/SKILL.md` lines 141-144

**Issue 4: Timestamp format not specified in flux-gen.md frontmatter**
- **Current**: flux-gen.md line 80 says `generated_at: '{ISO 8601 timestamp}'` but doesn't show timezone format.
- **Problem**: ISO 8601 allows many formats. Without specifying timezone, implementations vary.
- **Fix**: Change to `generated_at: '2026-02-09T14:30:00+00:00'` (with explicit UTC offset example). Add note: "Always use UTC with explicit +00:00 offset."
- **Location**: `commands/flux-gen.md` line 80

**Issue 5: Exit code 1 docstring vs SKILL.md disagreement**
- **Current**: detect-domains.py docstring (line 10) says exit 1 → "No domains detected (caller should use LLM fallback)". SKILL.md line 83 says exit 1 → "No domains detected — use LLM fallback below." But SKILL.md line 104 (Step 1.0.2) says exit 1 → "Skip agent generation entirely."
- **Problem**: Three places describe exit 1 behavior differently. The LLM fallback is only for Step 1.0.1 (first detection), while Step 1.0.2 (staleness check) should skip entirely. But this distinction is unclear.
- **Fix**: Harmonize all three:
  - detect-domains.py docstring: "No domains detected (caller decides: LLM fallback on first scan, skip on staleness check)"
  - SKILL.md line 83 (Step 1.0.1): "Exit 1: No domains detected — use LLM fallback below (first scan only)."
  - SKILL.md line 104 (Step 1.0.2): Already correct — "No domains detected. Skip agent generation entirely." Add clarification: "(this is a staleness check, NOT first detection — LLM fallback does not apply)"
- **Locations**: `scripts/detect-domains.py` line 10, `skills/flux-drive/SKILL.md` lines 83, 104

**Issue 6: Cache version check missing from SKILL.md and flux-gen.md**
- **Current**: detect-domains.py checks `cache_version` (line 324) and treats missing/outdated versions as stale. But SKILL.md's cache check (line 71) and flux-gen.md's cache check (line 16) don't mention version checking.
- **Problem**: Implementers following SKILL.md would read stale v0 caches without knowing the script handles version internally.
- **Fix**: Add note to SKILL.md line 71: "The detect-domains.py script handles cache version validation internally — callers do not need to check cache_version." Same for flux-gen.md cache read.
- **Locations**: `skills/flux-drive/SKILL.md` line 71, `commands/flux-gen.md` line 16

### From fd-correctness review (issues 7-10)

**Issue 7: Shallow clone false-fresh in tier 2 git log**
- **Current**: detect-domains.py `_check_stale_tier2` (line 206) uses `git log --since=...` which returns empty for shallow clones (no history beyond depth).
- **Problem**: Empty git log → no triggers → returns 0 (fresh). But the cache may actually be stale — shallow clone just can't prove it.
- **Fix**: Before running git log, detect shallow clone: `git rev-parse --is-shallow-repository`. If true, skip tier 2 and fall to tier 3 (mtime). This is safe because mtime always works regardless of git history depth.
- **Location**: `scripts/detect-domains.py` `_check_stale_tier2()` around line 214

**Issue 8: Naive datetime parsing accepts timezone-less strings**
- **Current**: `_parse_iso_datetime` (line 174) calls `fromisoformat()` which accepts strings without timezone info (e.g., "2026-02-09T14:30:00"). These become naive datetimes.
- **Problem**: Comparing naive datetime to aware datetime raises TypeError in Python. Also, `timestamp()` on naive datetime uses local timezone, which varies by system.
- **Fix**: After successful `fromisoformat()`, check if result is naive (`tzinfo is None`). If so, assume UTC: `result = result.replace(tzinfo=dt.timezone.utc)`. This handles v0 caches that didn't include timezone.
- **Location**: `scripts/detect-domains.py` `_parse_iso_datetime()` line 179

**Issue 9: Cache version comparison uses < instead of !=**
- **Current**: Line 324: `if version is None or (isinstance(version, int) and version < CACHE_VERSION)`.
- **Problem**: If a future version (e.g., version 2) writes a cache, then the code is downgraded, `version > CACHE_VERSION` is silently accepted as fresh. Future caches may have incompatible schemas.
- **Fix**: Change `<` to `!=`: `if version is None or (isinstance(version, int) and version != CACHE_VERSION)`. Log which direction the mismatch is: "Cache version {version} != {CACHE_VERSION} — stale ({direction})."
- **Location**: `scripts/detect-domains.py` `check_stale()` line 324

**Issue 10: Git subprocess stderr discarded**
- **Current**: `subprocess.run(..., capture_output=True, ...)` captures stderr but never logs it. If git fails, the error message is silently lost.
- **Problem**: Makes debugging hard — you see "fell to tier 3" but don't know why git failed.
- **Fix**: When `returncode != 0`, log stderr to stderr: `print(f"Warning: git log failed (exit {result.returncode}): {result.stderr.strip()}", file=sys.stderr)`. Then fall through as currently.
- **Locations**: `scripts/detect-domains.py` lines 228-233 (tier 2 main check), lines 250-256 (tier 2 rename check)

## Grouping by File

| File | Issues | Type |
|------|--------|------|
| `skills/flux-drive/SKILL.md` | 1, 2, 3, 5, 6 | Doc clarifications |
| `commands/flux-gen.md` | 4, 6 | Doc clarifications |
| `scripts/detect-domains.py` | 5, 7, 8, 9, 10 | Code hardening |

## Risk Assessment

- **All changes are backwards-compatible** — no behavioral changes for working cases
- **Issues 7-10 are defensive hardening** — they fix edge cases (shallow clones, naive datetimes, future cache versions) that don't affect normal usage
- **Issues 1-6 are documentation only** — clarifying existing behavior, not changing it
- **Test impact**: Issues 7-10 need new test cases in the existing detect-domains.py test suite

## Approach

1. Fix all 5 SKILL.md issues in one pass (issues 1, 2, 3, 5, 6)
2. Fix both flux-gen.md issues in one pass (issues 4, 6)
3. Fix all 5 detect-domains.py issues in one pass (issues 5, 7, 8, 9, 10)
4. Add tests for issues 7, 8, 9, 10
5. Run existing test suite to verify no regressions
