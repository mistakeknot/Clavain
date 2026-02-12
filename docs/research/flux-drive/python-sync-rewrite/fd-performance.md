# fd-performance Review

## Findings

### [P2] Git subprocess overhead: multiple small calls per upstream

**Description:**
Each upstream triggers 4-7 sequential git subprocess calls:
1. `git fetch` (lines 1197-1199)
2. `git reset --hard` (lines 1201-1204)
3. `git rev-parse HEAD` (lines 1209-1213)
4. `git cat-file -e <commit>` (lines 1218-1221)
5. `git rev-list --count` (lines 1227-1231)
6. `git diff --name-status` (lines 1239-1241)
7. Per-file `git show` for ancestor content (lines 1257-1262)

For 6 upstreams with 10-50 files each, this is 200-400+ subprocess invocations. Each subprocess has ~1-2ms overhead for fork/exec/parse. At weekly cadence this is fine (total runtime <5s even with overhead), but it's measurably inefficient.

**Recommendation:**
Batch operations where feasible:
- Combine steps 1+2 (fetch+reset) into single git call: `git fetch origin && git reset --hard origin/branch`
- Replace per-file `git show` loop with single `git archive | tar -x` to extract all changed files at ancestor commit into a temp dir. Read from disk instead of 50+ `git show` subprocesses.

**Trade-off:**
Batching adds code complexity. For weekly sync against 200 files, current overhead is ~0.5-1s total. Only implement if profiling shows git subprocess time dominates (unlikely — Claude AI call will be 10-100x slower).

**Priority:** P2 (minor optimization, no user-facing impact at weekly frequency)

---

### [P2] File I/O: reading each file 1-3 times without caching

**Description:**
For each changed file, the sync reads:
- Local version (line 1399)
- Upstream version (line 1400)
- Ancestor version via `git show` subprocess (lines 1401-1403)

Then for COPY/AUTO classifications, reads upstream file again (line 1321) to copy it. For namespace replacement, reads the local file AGAIN after copy (line 1321), applies replacements in memory, writes back (line 1323).

This is 2 reads + 1 write for files with namespace replacements, when it could be 1 read from upstream + 1 write to local with replacement applied in-flight.

**Recommendation:**
Refactor `apply_file()` to accept upstream content as string parameter instead of reading from disk:

```python
def apply_file(upstream_content: str, local_file: Path, namespace_replacements: dict[str, str]) -> None:
    """Write upstream content to local path, applying namespace replacements."""
    local_file.parent.mkdir(parents=True, exist_ok=True)
    content = apply_replacements(upstream_content, namespace_replacements)
    local_file.write_text(content)
```

Then pass `upstream_content` (already in memory from classification) directly. Eliminates 1 disk read + 1 metadata copy (`shutil.copy2`) per synced file.

**Trade-off:**
Loses file metadata preservation (timestamps, permissions). For markdown files this is irrelevant (git doesn't track mtime), but makes the code slightly less general-purpose. Worth it for 50% I/O reduction on the hot path.

**Priority:** P2 (nice to have, saves ~50ms total for 50-file sync)

---

### [P1] Claude subprocess: timeout handling exists but no progress visibility

**Description:**
AI conflict resolution (lines 880-892) shells out to `claude -p` with 120s timeout. For GPT-based models this is appropriate, but:
- No visibility into whether Claude is hung vs actively analyzing
- Timeout exception returns fallback (`needs_human`) but doesn't log the failure reason
- No backpressure/rate limiting if multiple conflicts trigger rapid-fire Claude calls

**Recommendation:**
1. Add stderr logging on timeout/failure (line 900): `except subprocess.TimeoutExpired: print(f"WARNING: AI analysis timed out for {local_path}", file=sys.stderr); return _FALLBACK`
2. Consider adding progress indicator for AI calls in orchestrator (line 1449): "Analyzing with AI (timeout: 120s)..."
3. For auto mode with multiple CONFLICTs, consider sequential processing with visible progress rather than blocking silently

**Trade-off:**
Adds stderr noise. But users running `--auto` mode expect to see what the script is doing, especially if it blocks for 2 minutes on a Claude call.

**Priority:** P1 (should fix before shipping — timeout failures are silent and confusing)

---

### [P2] Memory usage: buffering entire file contents is fine for markdown

**Description:**
The plan reads full file contents into memory (lines 1399-1403) and passes them as strings through the classification pipeline. For typical markdown files (1-50KB), this is 1-5MB total memory for 100 files in flight.

Ancestor content for all changed files across 6 upstreams will be ~5-10MB resident. This is negligible on a server with GB of RAM.

**Recommendation:**
No action needed. If the project ever syncs binary assets or >1MB files, add a size check and skip classification for oversized files (similar to how deletion status "D" is skipped on line 1376).

**Priority:** P2 (informational — not a concern for current use case)

---

### [P2] Report generation: string concatenation via list + join (optimal)

**Description:**
Report generation (lines 1135-1159) uses `lines.append()` + `"\n".join(lines)`. This is the correct pattern for building large strings in Python. No repeated string concatenation with `+=`.

AI decision formatting (lines 1152-1157) uses f-strings in a loop. For <100 conflicts this is fine. If conflict count exceeds 1000, consider using a template or generator expression.

**Recommendation:**
No action needed. Current implementation is already optimal for the expected workload (<50 conflicts per sync).

**Priority:** P2 (informational — no change needed)

---

### [P2] Startup cost: 7 modules + pytest overhead vs bash exec

**Description:**
Python startup cost is ~50-100ms for import + module load. Bash script startup is <10ms. For interactive `--dry-run` checks this is barely perceptible. For CI weekly cron job it's irrelevant.

Only matters if the script were invoked repeatedly in a tight loop (e.g., per-file webhook), which is not the design.

**Recommendation:**
No action needed. The plan preserves `--dry-run` as a fast preview mode (no git fetch/reset, only classification). Startup cost is dominated by git operations, not Python import.

**Priority:** P2 (informational — not a bottleneck)

---

### [P2] Classification hot path: 7-way enum comparison is constant time

**Description:**
`classify_file()` (lines 621-688) has 7 possible outcomes. Worst case: 4 string comparisons + 2 boolean checks. For 200 files this is <1ms total CPU time.

Namespace replacement (line 658) calls `apply_replacements()` which does naive `str.replace()` in a loop (lines 289-292). For 3 replacements over 10KB files, this is ~0.1ms per file. No regex compilation overhead.

**Recommendation:**
No action needed. Classification is already O(n) in file count, O(m) in replacement count, with small constants. Only optimization would be compiling replacements into a single regex, but that's premature for 3 patterns.

**Priority:** P2 (informational — already optimal)

---

## Summary

The Python sync rewrite is **performance-appropriate for weekly batch workload**. Total runtime for 6 upstreams with 200 changed files: ~10-30s (dominated by git fetch + Claude AI calls, not Python overhead).

**Must fix before shipping (P1):**
- Add stderr logging and progress visibility for Claude subprocess timeouts (line 900, 1449)

**Nice to have (P2):**
- Refactor `apply_file()` to pass content as string parameter, eliminating redundant disk reads (saves ~50ms per sync)
- Consider batching `git show` calls via `git archive` if profiling shows subprocess overhead is significant (unlikely)

**No action needed:**
- Memory usage is appropriate for markdown files (5-10MB resident)
- Report generation uses optimal list+join pattern
- Classification hot path is already O(n) with small constants
- Python startup cost is negligible for weekly batch job

**Overall assessment:** The plan demonstrates good performance discipline. No gross inefficiencies. The AI subprocess call (120s timeout) will dominate runtime for conflict-heavy syncs, which is intentional and unavoidable. Subprocess overhead and file I/O are minor compared to network I/O (git fetch) and AI analysis. Recommend implementing P1 stderr logging, defer P2 optimizations until profiling shows they matter.
