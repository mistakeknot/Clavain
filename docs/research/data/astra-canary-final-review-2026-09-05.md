Text-only follow-up on the Astra canary record, as briefed. Verdict is at the end.

**Acceptance replay.** Each prior finding against the supplied remediation.

- **H1 closed.** Rows 1 to 4 and both raw reports now live in a committed, hash-bound artifact named in the receipt. Nothing depends on the temp store surviving.
- **M1 closed.** The delta between the reviewed and installed commits is enumerated as two doc lines plus one test-only environment reset, with publisher, CLI, Go CI and Secret Scan passing on that delta. Add the installed commit hash to the receipt itself so it is self-contained without the runbook.
- **M2 closed.** Checkpoint validation is flagged independent, the validator route is different-model, every validator fallback resolves to a model other than the producer, and the runbook places a sealed validator between the packet and mk's decision.
- **M3 closed.** The exposure caveat names the Astra interactive base, denies it canary credit, and the stop conditions cover un-enrolled escapes.
- **M4 closed.** Numerator, denominator, abandonment as non-success, pending disclosed separately, checkpoint-only evaluation and the terminal-sample floor are all explicit.
- **M5 closed as a hold,** not a fix. Installer and bootstrap are barred until the tracked bead resolves and working MCP config is unchanged. Acceptable for a zero-enrollment canary.
- **L1 closed as reported.** The doc verification exists only in this message and the audit doc, not in the receipt fields shown. Bind URL, fetch time and observed config key into the receipt.
- **L2 closed.** Six closures with timestamps, parent bead, session, signer host, tracker PR and merge SHA, plus an explicit no-key-or-policy-change flag.
- **L3 closed.** Full profiles and fallback chains are embedded and the binary source is defined.
- **L4 closed.** ID scheme, retry versus attempt split, contract-kind recording, strata and the legacy-metric disclaimer are present.

**Beyond-gauge concerns.** New items, none blocking.

1. **Un-started enrollments have no disposition.** Enrollment is recorded before start, but terminal states are defined only for tasks that started. A task enrolled and never dispatched sits outside both the denominator and the abandonment rule. Define "started" as first dispatch, and require un-started enrollments at checkpoint to be disclosed as pending or withdrawn with a reason.
2. **Enrollment ID reuse after a terminal state.** The scheme yields one ID per repository and bead. If a bead is abandoned and later re-enrolled, the new enrollment collides with a terminal record, and "count unique tasks, not retries" becomes ambiguous about one task versus two terminals. Forbid reuse of a terminal ID, or suffix re-enrollments and count both.
3. **Which decision owns the 14-day clock.** The runbook cites the start decision for the deadline, while the receipt is held under a later hold decision whose policy supersedes the start snapshot. If the clock runs during the hold, the checkpoint can arrive short of the sample floor for reasons unrelated to Astra. Rebase the deadline at hold release in a new decision and record it in the receipt.
4. **Threshold arithmetic.** At exactly the sample floor, the ratio tolerates a single non-success, and abandonments count against it. Not a defect, but confirm that strictness is intended for brief contracts.
5. **Excerpt truncation.** The runbook text ends mid-sentence in the async-evidence section, so delayed-error classification and any later stop rules were not assessed.

**Verdict: CLEAN.** All ten prior findings are closed on the supplied record. Items 1 to 3 are denominator and clock clarifications costing a few lines each and should land before the first enrollment. They do not reopen any prior finding, and the checkpoint validator's denominator review would catch them if missed.

