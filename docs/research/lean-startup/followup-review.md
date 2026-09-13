# Startup follow-up review

The original comparison remains pinned to Clavain `9d58166`. These fixes are
separate: bounded private ledger reads, snapshot trust checks, blank export
lines, state-error priority, and exact host/source/configuration identity.

Fresh checks: **37 focused tests; 1,156 structural tests passed, one skipped.**
Eight regressions failed before their fixes. No passing-result cache was used.

Independent reviewer: `claude-fable-5-1`, high effort.

{
  "session_id": "41ba8f44-f988-4bc5-8856-cf344cf86b73",
  "native_transcript_sha256": "48863ff08281fbb3678d000d6d5c89efe5c2739c4902d5e90f27e6e3bbbbfea4",
  "review_sha256": "a9d156949e1b72c41c82c4de7f1e40caee61ca57b393791f5470fbac2ef8eaf7",
  "reviewed_diff_sha256": "0f3688d6c32906af769393997c844923f84fb0d9ef787ed4ebbbc8cb752be074"
}

SOURCE VERDICT: CLEAN

The delta resolves both reported issues correctly.

- **Concurrent append.** The tail read now sizes the read to the fstat-observed EOF, so bytes appended after the stat are never read and cannot trip the budget check. The regression test reproduces the race by appending inside a patched fstat and passes.
- **Wrong-host ledger match.** Doctor now requires exact equality of the whole context identity instead of project scope alone. The new test flips only the host field and confirms the ledger reports unknown.
- **Read hardening.** Snapshot and ledger reads go through a no-create private path check with O_NOFOLLOW, regular-file, owner, and mode checks, and the untrusted-snapshot tests confirm unknown status with no filesystem writes.
- **Priority change.** Mode and error sections now sort ahead of routing, ownership, and task, and the test confirms they survive truncation.

Nonblocking observations:

- When the tail window happens to start exactly at a line boundary, the partition drops one complete line instead of a partial one. With a 16 MiB window and a 100-row cap this is practically harmless.
- The claim that the eight new tests failed against the prior source is consistent with the test count in the delta, but no red-run output was supplied, so it stays a self-report. The fresh green run of 37 tests is verified from the supplied output.
