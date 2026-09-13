# Independent Fable source review

Scope: source commit only. Native behavioral acceptance and rollout remain pending.
Reviewer: claude-fable-5-1, high effort, via governed dispatch from Astra producer.

**VERDICT: CLEAN** for commit. No blocking findings. Native behavioral acceptance remains pending and nothing here substitutes for it.

**Test evidence.** All 32 focused tests pass with the designated TMPDIR:

```
TMPDIR=/var/tmp/lean-review-tests python3 -m pytest tests/structural/test_startup.py review-extra/interstat/tests/test_startup_evidence.py -q
32 passed in 1.53s
```

The hook script passes a bash syntax check, the hooks manifest parses, and all 18 hook targets it references exist and are executable.

**Previous P1/P2 fixes, verified by reading the code and probing:**

- **Status derived from final selection.** The contract is removed from the candidate list before reassembly, so a longer "NOT injected" status cannot flip the decision. I confirmed the flip boundary: a contract that fits without the telemetry warning but not with it is reported as NOT injected on the telemetry-failure path. The reverse inconsistency cannot occur because the second assembly always has less room.
- **Priority order.** Contract, state summary, session identity and active task all sort before ownership, task rows and runtime blockers. Verified on a live render.
- **Clip bounds UTF-8 bytes.** Multibyte truncation stays within the byte budget and never produces an invalid string. Verified with emoji, two-byte characters and a split codepoint at the boundary.
- **Symlinked state dir refused** at the leaf, with the resolved path then checked for project, worktree, owner and mode. Ledger opened with O_NOFOLLOW and fstat checks. Sound.
- **Task-id None matching removed.** The bead guard is present and tested.
- **Non-Claude/Codex hosts** hit a parser error without an explicit instruction file, which the shell wrapper turns into the visible fallback.
- **Unknown providers cannot join.** Only claude and codex map to a provider, and the match requires it.
- **Test ledgers isolated.** The one test that runs the real hook sets the state-dir override. The fallback test never reaches Python.

End-to-end run of the hook with a session payload produced a valid 5.3 KB envelope in about 9 ms, wrote nothing into the project, and appended one private ledger row.

**Non-blocking findings for follow-up beads before rollout:**

1. **Ledger growth makes doctor permanently fail. P2.** Each render appends about 8 KB, mostly the full context identity. Doctor reads the whole file under the 16 MiB budget, so after roughly 2,000 session starts it reports the ledger as unknown and exits non-zero forever, while render keeps appending. Reproduced. It fails closed, so no false pass, but there is no rotation and no distinguishing message. See `scripts/startup.py:415`.
2. **A trailing blank line in the beads export hides all tasks. P3.** One empty line makes the entire export "unknown". Reproduced. Conservative direction, but easy to trigger and it loses ownership context. See `scripts/startup.py:199`.
3. **Render and doctor read the state dir without the private-dir ownership check. P3.** Only writes are guarded. A planted snapshot in the shared default location would need the full identity hash set to be accepted, so exploitation is impractical, but reading through the same guard would close it.
4. **Sections with default priority can be dropped under budget pressure.** The INTERSERVE mode flag, task-error and ownership-error notices all sort last with diagnostics. The routing and boundaries sections cover the governance point, so low severity.
5. **Cosmetic.** A stray `__pycache__` directory now exists under the interstat scripts folder from pytest imports. Exclude it from the commit.

On the commit question: the source is safe to commit without rollout. Finding 1 should be resolved or tracked before any rollout that runs the hook at scale.
