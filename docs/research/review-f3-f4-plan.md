# Review: M1 F3/F4 Implementation Plan

**Reviewer:** plan-reviewer agent
**Date:** 2026-02-13
**Plan:** docs/plans/2026-02-13-m1-f3-f4-work-discovery.md
**PRD:** docs/prds/2026-02-12-phase-gated-lfg.md

## Executive Summary

The plan is **MOSTLY SOUND** with **3 critical gaps** and **2 important risks** that need addressing before implementation. The task breakdown is logical, file locations are correct, and the integration strategy is clean. However, the plan misses key acceptance criteria from the PRD, has an incomplete routing implementation, and underspecifies error handling.

**Recommendation:** Address the 3 critical gaps below, then proceed. Estimated fix time: 30-45 minutes.

---

## Detailed Analysis

### 1. PRD Acceptance Criteria Coverage

#### F3: Orphaned Artifact Detection ✅ MOSTLY COVERED
**PRD Acceptance Criteria:**
- [ ] Orphaned artifacts included in discovery results with "Create bead?" action
- [ ] Artifacts linked to closed beads excluded (not orphaned)
- [ ] Linking detected via `**Bead:**` header pattern in markdown files

**Plan Coverage:**
- ✅ Scan `docs/brainstorms/`, `docs/prds/`, `docs/plans/` (Task 1.1)
- ✅ Grep for bead ID via header pattern (Task 1.2)
- ✅ Check if bead was deleted via `bd show` (Task 1.4)
- ✅ Exclude closed beads (Task 1.5)
- ✅ Return JSON array with suggested action (Task 1.6)
- ✅ AskUserQuestion integration (Task 2.1-2.4)

**Gap:** Task 2.3 says "link bead to artifact by inserting `**Bead:** <new-id>` header" but doesn't specify WHERE in the file (after title? after metadata block?). Sprint-scan.sh's orphan detection uses filename-based matching (topic slug), while lib-discovery.sh's pattern is header-based. These are **different detection strategies** that will produce **different results**. The plan should clarify:
1. Does F3 use filename-based OR header-based detection?
2. If header-based (as Task 1.2 suggests), does sprint-scan.sh need updating for consistency?

**Verdict:** Gap is important but not blocking. Recommend: use header-based detection (more reliable), update sprint-scan.sh in a follow-up P3 bead.

---

#### F4: Session-Start Light Scan ⚠️ INCOMPLETE
**PRD Acceptance Criteria:**
- [ ] Shows count of open beads and how many are ready to advance
- [x] Shows highest-priority item with suggested action
- [x] Uses 60-second TTL cache to avoid repeated beads queries
- [x] Adds no more than 200ms to session startup (cached path)

**Plan Coverage:**
- ✅ 60s TTL cache (Task 3.1-3.2)
- ✅ Lightweight `bd list --status=open` query (Task 3.3)
- ✅ Count open beads (Task 3.4)
- ✅ Highest-priority item (Task 3.4)
- ❌ **"Ready to advance" beads NOT COUNTED**

**CRITICAL GAP 1:** Task 3.4 says "count open beads, count in_progress beads, find highest-priority item" but the PRD requires "how many are ready to advance". This requires **phase state inspection**, not just status. A bead is "ready to advance" when its phase is terminal for its current stage (e.g., `phase=planned` + no plan-reviewed state = ready for flux-drive).

**Impact:** The discovery_brief_scan output won't match user expectations from the PRD. This is a core acceptance criterion.

**Fix:** Task 3.4 must:
1. Query phase state via `bd state <id> phase` for each open bead
2. Count how many have phases like `brainstorm`, `planned`, `plan-reviewed` (terminal phases)
3. Include "N ready to advance" in the summary

**Estimated complexity:** +20 lines of shell, +1 `bd state` call per bead (adds ~5-10ms per bead, but within 200ms budget for <10 beads).

---

### 2. Task Ordering & Dependencies

**Plan Order:** T1 (F3 orphan detection) → T2 (F3 routing) → T3 (F4 brief scan) → T4 (F4 integration) → T5 (tests) → T6 (publish)

**Analysis:**
- ✅ T1 and T3 are independent (both add functions to lib-discovery.sh)
- ✅ T2 depends on T1 (needs `action: "create_bead"` in scanner output)
- ✅ T4 depends on T3 (needs discovery_brief_scan function)
- ⚠️ T5 depends on T1-T4 but Task 5 says "verify 29/17/37 still correct" — this is a **weak test**

**CRITICAL GAP 2:** The plan says "Tasks 1+3 are independent but I'll do them sequentially to avoid merge conflicts" — but **they're adding functions to THE SAME FILE**. This is NOT a merge conflict risk if you write T1 functions first, then append T3 functions. However, the plan should explicitly state the **line range** or **section** where each function goes to avoid accidental overwrites.

**Recommendation:** Add to Task 1: "Place discovery_scan_orphans() after line 192 (after discovery_scan_beads function)". Add to Task 3: "Place discovery_brief_scan() after discovery_scan_orphans()".

---

### 3. Missing Implementation Details

#### Task 1.2: Bead ID Regex Pattern
The plan says "same regex as `infer_bead_action`" — let's verify:

**Existing pattern in lib-discovery.sh line 35:**
```bash
pattern="Bead.*${bead_id}\b"
```

This pattern matches:
- `**Bead:** Clavain-abc123`
- `Bead: Clavain-abc123`
- `<!-- Bead: Clavain-abc123 -->`

**What it does NOT match:**
- Orphaned artifacts (no bead ID exists yet)

**CRITICAL GAP 3:** Task 1.2 is backwards. To detect orphans, you need to:
1. Find files with NO bead header at all (unlinked artifacts)
2. Find files with a bead header that references a deleted bead

The current plan says "grep for Bead header pattern" but doesn't specify what happens when grep finds NOTHING (which is the unlinked case). Task 1.3 says "If no bead ID found → unlinked" but how do you extract the bead ID from "no match"?

**Fix:** Task 1.2 should be:
```
1.2a. For each file, extract bead ID if present: grep -oP 'Bead[:\s*]+(\K[A-Za-z]+-[a-z0-9]+)' (capture group)
1.2b. If no ID extracted → artifact is unlinked (potential orphan)
1.2c. If ID extracted, proceed to 1.4
```

---

#### Task 2.3: Bead Creation & Linking
Plan says:
> "If yes: `bd create --title="<artifact title>" --type=task --priority=3` then link bead to artifact by inserting `**Bead:** <new-id>` header"

**Missing details:**
1. WHERE in the file? (After `# Title` line? After front matter?)
2. What if the file has YAML front matter? (Insert after `---` block)
3. What if title extraction fails? (Use filename as fallback)
4. After linking, should the artifact be re-scanned or removed from orphan list?

**Impact:** Medium. Without line-number specificity, implementation might insert the header in the wrong place (e.g., inside a code block).

**Fix:** Add to Task 2.3:
```
Insert `**Bead:** <id>` on line 3 if file starts with `# Title`, else after YAML front matter (after second `---`), else at top of file. Use sed/awk for insertion (Read then Edit with old_string = first 2 lines + new_string = first 2 lines + bead header).
```

---

#### Task 3.4: Output Format Spec
Plan says:
> "Output 1-2 line summary: `5 open beads (2 in-progress). Top: Execute plan for Clavain-6czs — F1 (P2)`"

**Questions:**
1. What if there are ZERO open beads? (Output nothing, or "No open beads"?)
2. What if bd is unavailable? (Task 3.7 says "output nothing" — correct)
3. What if highest-priority item has no action inferred? (Fallback to "Review Clavain-6czs"?)

**Impact:** Low, but tests will fail if output format isn't deterministic.

**Fix:** Add explicit fallback rules to Task 3.4-3.5.

---

#### Task 4.2: Sprint Signals Integration
Plan says:
> "Append result to sprint signals (same format: `"• <summary>\n"`)"

**Problem:** Sprint signals in session-start.sh use `\n` literal strings (escaped for JSON injection). The discovery_brief_scan output format needs to match. But does discovery_brief_scan return:
- Plain text with actual newlines (`\n` characters)?
- JSON-escaped string (`"\\n"` literals)?
- Multi-line string (relies on escape_for_json)?

**From session-start.sh lines 113-115:**
```bash
sprint_context=$(sprint_brief_scan 2>/dev/null) || sprint_context=""
if [[ -n "$sprint_context" ]]; then
    sprint_context=$(escape_for_json "$sprint_context")
fi
```

So sprint_brief_scan returns **plain text with actual newlines**, then escape_for_json handles JSON escaping. Task 3.5 output format should use actual newlines, not `\n` literals.

**But** Task 4.2 says "same format: `• <summary>\n`" which is ambiguous. The plan should specify: "discovery_brief_scan returns plain text with actual newlines (like sprint_brief_scan), session-start.sh will call escape_for_json before injection."

**Impact:** Low, but could cause malformed JSON if misunderstood.

---

### 4. Edge Cases & Error Handling

#### Orphan Detection Edge Cases:
1. **Multi-bead artifacts:** PRD mentions "artifacts linked to closed beads excluded" but what if an artifact references MULTIPLE beads (e.g., `**Bead:** Clavain-abc (epic), Clavain-xyz (task)`)? Is it orphaned if ANY bead is open, or if ALL are closed?
   - **PRD answer:** Not specified. Recommend: orphaned only if ALL referenced beads are closed/deleted.

2. **Malformed bead IDs:** What if grep finds `**Bead:** invalid-id`? `bd show invalid-id` will fail (same as deleted bead). Is this orphaned?
   - **Correct behavior:** Yes, treat as orphaned (bead doesn't exist).

3. **Stale plans with closed beads:** Plan X references Clavain-123 (closed). Plan has checklist items 50% complete. Is this orphaned?
   - **PRD answer (line 38):** "Artifacts linked to closed beads excluded (not orphaned)".
   - **But:** This seems wrong for plans. A closed bead with an incomplete plan is a data integrity issue.
   - **Recommendation:** Add to discovery_scan_orphans: if bead is closed BUT plan_path has unchecked items, flag as "stale completed work" (not orphan, but worth surfacing).

4. **Circular refs:** Brainstorm-A.md and PRD-B.md both reference the same bead. Is one of them orphaned?
   - **Answer:** No, both are linked to the same bead. This is fine (multiple artifacts per bead is valid).

**Plan gap:** None of these edge cases are addressed. Task 1 should have a sub-task "1.8. Handle multi-bead refs and malformed IDs".

---

#### F4 Brief Scan Edge Cases:
1. **Cache corruption:** What if cache file exists but contains invalid JSON? (stat succeeds, jq parse fails)
   - **Task 3.2 says:** "read and return cached result" but doesn't specify validation.
   - **Fix:** Add `|| rm -f "$cache_file"` fallback if cache read fails, then regenerate.

2. **bd list returns empty array but status=0:** Is this an error or valid "no beads"?
   - **Valid state.** Output should be "0 open beads. No work queued."

3. **Clock skew:** What if cache mtime is in the future? (system clock changed)
   - **Low risk,** but `[[ $cache_age -lt 60 ]]` would fail. Use absolute value or clamp.

4. **Race condition:** Two Claude Code sessions start simultaneously, both see stale cache, both regenerate. Last writer wins (acceptable).

**Plan gap:** Task 3.2 needs "Validate cache content (parse JSON) before trusting".

---

### 5. Integration Risks

#### Risk 1: interphase Plugin Not Installed
**Mitigation in plan (Task 4.3):** "Guard: if interphase not available (shim returns nothing), skip silently"

**Analysis:** Clavain's shim in hooks/lib-discovery.sh delegates to interphase. If interphase is not installed, the shim's `_discover_beads_plugin()` returns nothing, and sourcing the shim is a no-op. Session-start.sh would call `discovery_brief_scan` but the function wouldn't exist.

**Actual behavior:**
- session-start.sh line 111: `sprint_context=$(sprint_brief_scan 2>/dev/null) || sprint_context=""`
- If discovery_brief_scan is not defined, bash would error: "command not found"
- The `2>/dev/null` suppresses stderr, `|| sprint_context=""` sets empty string
- **Result:** Silently skipped (correct behavior)

**But:** session-start.sh line 115 calls `escape_for_json "$sprint_context"` even when empty. This is fine (escape_for_json handles empty input).

**Verdict:** Risk 1 is correctly mitigated. No action needed.

---

#### Risk 2: lib-discovery.sh Sourcing from Multiple Hooks
**Current usage:**
- commands/lfg.md sources it on-demand (line 13)
- hooks/session-start.sh will source it (new, Task 4.1)

**Existing guard (lib-discovery.sh line 7-8):**
```bash
[[ -n "${_DISCOVERY_LOADED:-}" ]] && return 0
_DISCOVERY_LOADED=1
```

**Verdict:** Risk 2 is correctly mitigated via guard variable. No action needed.

---

#### Risk 3: Version Skew Between Clavain and interphase
Plan says (Risk section):
> "interphase plugin cache may not be fresh — Clavain's shim discovers interphase at runtime. If interphase is updated but cache is stale, new functions won't be found. Mitigation: bump-version.sh handles symlinks."

**Analysis:** This refers to Claude Code's plugin cache at `~/.claude/plugins/cache/<plugin>-<version>/`. When interphase is updated, the cache dir changes, and Clavain's runtime discovery (`_discover_beads_plugin`) would find the NEW version (it uses `find` with `-name 'interphase'` which matches any version).

**Actual risk:** If Clavain session starts BEFORE interphase is updated, then interphase is updated mid-session, Clavain's sourced functions are from the OLD interphase. But discovery_scan_orphans and discovery_brief_scan are NEW functions, so they wouldn't exist in the old version.

**Mitigation:** Plan Task 6 says "bump interphase version, commit, push, publish" THEN "bump Clavain version". This ensures users pull both updates together. But if a user is running an old Clavain with new interphase, the shim would discover the new interphase and call discovery_brief_scan successfully.

**Reverse case:** Old interphase + new Clavain = session-start.sh calls discovery_brief_scan (doesn't exist) → silent skip (correct).

**Verdict:** Risk 3 is low and correctly mitigated by publish order. Add to Risk section: "Users must update BOTH plugins (Clavain + interphase) for F3/F4 to work."

---

#### Risk 4: bd Performance on Large .beads
Plan says (Risk section):
> "bd list performance on large .beads — F4 queries bd on every session start. Mitigation: 60s TTL cache, bd list is <50ms even with 100+ beads."

**Analysis:** Verified in interphase's lib-discovery.sh lines 97-101:
```bash
open_list=$(bd list --status=open --json 2>/dev/null) || {
    echo "DISCOVERY_ERROR"
    return 0
}
```

`bd list --status=open` is a direct SQLite query (no filesystem scan). Beads stores data in `.beads/db.sqlite` and queries are indexed. With 100 beads, this is ~10-20ms. With 1000 beads, ~50-80ms.

**60s cache adds:** stat + cat = ~5ms (as plan states).

**Verdict:** Risk 4 is correctly assessed. No action needed.

---

### 6. Test Coverage

**Plan Task 5:**
- 5.1. Bats tests for discovery_scan_orphans (fixtures: unlinked, deleted bead, closed bead, valid bead)
- 5.2. Bats tests for discovery_brief_scan (cache TTL, bd unavailable, empty beads)
- 5.3. Bats test in Clavain for session-start.sh integration (mock interphase available/unavailable)
- 5.4. Update structural test counts (verify 29/17/37)

**Gaps:**
1. **No test for orphan routing in /lfg** — Task 5 tests discovery_scan_orphans in isolation, but doesn't test the AskUserQuestion integration (Task 2.1-2.4). This should be a **smoke test**: spawn a fixture project with an orphaned plan, run /lfg, verify the option appears.

2. **No test for bead creation + linking** — Task 2.3 creates a bead and inserts a header, but there's no test verifying the header is inserted at the correct line.

3. **No test for multi-bead refs** — Edge case not covered (see section 4 above).

4. **Task 5.4 is weak** — "verify 29/17/37 still correct" is a regression guard, but doesn't test F3/F4 functionality. Structural tests should verify:
   - `discovery_scan_orphans` function exists in interphase
   - `discovery_brief_scan` function exists in interphase
   - commands/lfg.md mentions `action: "create_bead"` in step 6

**Recommendation:** Add Task 5.5: "Smoke test: create fixture with orphaned plan, run /lfg, verify orphan appears in AskUserQuestion, select it, verify bead created and header inserted."

---

### 7. Documentation & Versioning

**Plan Task 6:**
- 6.1. Bump interphase version, commit, push, publish
- 6.2. Bump Clavain version, commit, push, publish
- 6.3. Close Clavain-ur4f (F3) and Clavain-89m5 (F4)

**Gaps:**
1. **No MEMORY.md update** — F3 and F4 add new functions to interphase. Clavain's MEMORY.md should document:
   - `discovery_scan_orphans()` returns synthetic beads with `action: "create_bead"`
   - `discovery_brief_scan()` uses 60s cache, outputs 1-2 line summary
   - `/lfg` routing now handles `action: "create_bead"` (step 2.1-2.4)

2. **No interphase MEMORY.md** — Interphase project should have its own memory file documenting:
   - Cache files at `/tmp/clavain-discovery-brief-${DISCOVERY_PROJECT_DIR//\//_}.cache`
   - TTL is 60s (hardcoded)
   - Orphan detection uses header-based matching (not filename-based like sprint-scan)

3. **No changelog entry** — Both plugins should have a CHANGELOG.md or version-tagged commit message documenting the feature.

**Recommendation:** Add Task 6.4: "Update MEMORY.md files (Clavain + interphase) and add changelog entries."

---

## Critical Gaps Summary

| # | Gap | Severity | Blocking? | Fix Estimate |
|---|-----|----------|-----------|--------------|
| 1 | F4 "ready to advance" count missing | Critical | Yes | 15-20 min |
| 2 | Bead ID extraction logic backwards (Task 1.2) | Critical | Yes | 10 min |
| 3 | Orphan routing (Task 2) missing header insertion location | Important | No | 5 min |
| 4 | Test coverage weak (no /lfg routing test) | Important | No | 20 min |
| 5 | Documentation updates missing | Suggestion | No | 10 min |

**Total fix time for blocking gaps:** 25-30 minutes
**Total fix time for all gaps:** 60-75 minutes

---

## Recommendations

### Before Implementation:
1. **Fix Critical Gap 1:** Add phase state inspection to Task 3.4 (query `bd state <id> phase` for each bead, count terminal phases as "ready to advance")
2. **Fix Critical Gap 2:** Rewrite Task 1.2 to use capture groups for bead ID extraction (handle "no match" case explicitly)
3. **Clarify Task 2.3:** Specify WHERE to insert the bead header (after title line, with fallback rules for YAML front matter)

### During Implementation:
4. **Add Task 5.5:** Smoke test for orphan routing in /lfg (end-to-end test with fixture)
5. **Add cache validation:** Task 3.2 should parse cached JSON before trusting it

### After Implementation:
6. **Update MEMORY.md:** Document the new functions in both Clavain and interphase
7. **Add changelog entries:** Version bump commits should document F3/F4 features

---

## Plan Quality Assessment

**Strengths:**
- ✅ Clean separation of concerns (interphase owns discovery logic, Clavain owns routing)
- ✅ Correct file locations and integration points
- ✅ Risk section identifies real risks (cache, version skew, performance)
- ✅ Task ordering is mostly correct (T1→T2, T3→T4)
- ✅ Guards against missing dependencies (bd not installed, interphase not available)

**Weaknesses:**
- ❌ Missing 1 critical PRD acceptance criterion (F4 "ready to advance" count)
- ❌ Task 1.2 implementation is backwards (grep for bead ID doesn't work for "no bead ID" case)
- ⚠️ Weak test coverage (no end-to-end /lfg routing test)
- ⚠️ Missing documentation updates (MEMORY.md, changelogs)
- ⚠️ Edge cases not addressed (multi-bead refs, malformed IDs, cache corruption)

**Overall Grade:** B+ (85/100)

**Recommendation:** Fix the 2 critical gaps (F4 count, Task 1.2 logic), then proceed. The plan is solid enough to execute with minor on-the-fly adjustments for the "important" issues.
