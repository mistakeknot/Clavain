# fd-distributed-systems-handoff-cox — round 0

## Findings Index

- [P0] mixed-revision-handoff-can-pass — A path-only handoff can execute and validate different plan and repository revisions (§The shape)
- [P1] parallel-worktree-cross-talk — Concurrent items share one mutable worktree, so a task review can absorb a sibling's changes (§The shape)
- [P1] blind-retry-after-partial-effects — A failed or interrupted attempt is redispatched into its own unexplained mutations (§Escalation)
- [P2] q-e-collapses-a-fault-family — Q-E treats plan drift as one candidate failure instead of a family of distributed-state faults (§Open questions the review should attack)

## Findings

### mixed-revision-handoff-can-pass

- Severity: P0
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:15-19,25`; `scripts/orchestrate.py:321-356,446-466,582-612,1412-1455`
- What: The design identifies work by a plan path, but does not bind the plan revision, criteria revision, base commit, dependency state, attempt, verify-command identity, or resulting commit. The current orchestrator parses task sections once at run start, tells executors to read the live plan path later, and tells reviewers to read the live criteria sidecar. A mid-run edit can therefore give the executor a newer plan, the reviewer an older in-memory task section, and both a newer criteria file. Each component can honestly report PASS while no single immutable contract was executed and validated.
- Evidence: `parse_plan_tasks()` snapshots task prose into memory (`scripts/orchestrate.py:446-466`), while `build_prompt()` sends only the live plan path to the executor (`:321-356`). `build_review_prompt()` receives that earlier section but dereferences `criteria_path` at review time (`:582-612`). The run-start journal records absolute manifest and plan paths, not their hashes or the base HEAD (`:1443-1455`); the only recorded HEAD is sampled after task completion (`:1174-1188`).
- Suggestion: Freeze a minimal handoff envelope before any write: `{goal_id, plan_sha256, criteria_sha256, manifest_sha256, base_commit, dirty_tree_digest, task_id, attempt_id, verify_spec_sha256}`. Require the executor to return `{result_commit, verify_run_id}` and require validation and landing to fail closed unless every identity still matches.

### parallel-worktree-cross-talk

- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:16-19`; `scripts/orchestrate.py:134-174,531-564,753-800,1057-1100`
- What: Independent-looking tasks run concurrently in the same `project_dir`, but validation computes a repository-wide diff. If two items touch the same file, a generated artifact, the index, or HEAD, one reviewer can approve code produced by the other item or reject its own item for sibling scope. A subsequent fix agent then edits this mixed state. The affected executor, validator, and landing controller no longer know which commit belongs to which task.
- Evidence: `validate_graph()` checks unknown dependencies and cycles but not overlapping file ownership (`scripts/orchestrate.py:154-174`). `dispatch_batch()` runs tasks in a `ThreadPoolExecutor` against the same project directory (`:1057-1100`). Each task samples `head0` from that shared repository (`:753-777`), and `task_diff()` includes every tracked change since that HEAD plus up to five repository-wide untracked files (`:531-564`).
- Suggestion: Before dispatch, reject or serialize tasks whose declared files, generated outputs, or repository roots overlap. For admitted parallel tasks, validate the task's explicit result commit/diff rather than the mutable worktree-wide `head0..current` diff.

### blind-retry-after-partial-effects

- Severity: P1
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:19`; `scripts/orchestrate.py:753-847,915-1054,1158-1188,1386-1407`
- What: A timeout, executor loss, or nonzero exit can leave edits or commits behind. The pipeline either returns early on `error` or starts a fix round against whatever survived; resume later redispatches every non-pass task without reconciling that state. Because the initial attempt reuses `prompt.md`, `output.md`, and `meta.json`, a resumed attempt can also overwrite the evidence needed to determine what the first attempt did. Duplicate insertions, overwritten sibling changes, and spurious second strikes can follow.
- Evidence: `run_task_pipeline()` returns immediately after an implementation `error` and performs no compensation or state classification (`scripts/orchestrate.py:774-789`). `dispatch_task()` writes fixed per-phase artifact names and judges a timeout/nonzero exit partly by file mtimes (`:940-1045`). `_journal_completed()` trusts only terminal status (`:1158-1171`); resume restores those statuses and blindly redispatches everything else into the same run directory (`:1386-1407`).
- Suggestion: Make attempts append-only (`attempt-1/`, `attempt-2/`), record pre/post HEAD and dirty-tree digests for each, and add a recovery preflight that classifies `no effects`, `committed effects`, `uncommitted effects`, or `unknown`. Only `no effects` may retry automatically; other states require idempotent continuation or explicit compensation.

### q-e-collapses-a-fault-family

- Severity: P2
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md:34`; `commands/model-routing.md:108-119`
- What: Q-E asks for "the failure mode" and offers stale-plan drift as one candidate. The handoff creates several independent fault classes: contract-version skew, repository-state drift, cross-item interference, partial-effect replay, stale validation evidence, and environment/infra failure misclassified as a capability strike. Treating them as one mode invites one generic drift check that leaves the others silent.
- Evidence: The doctrine already distinguishes capability/premise failures from sandbox, auth, rate, and infrastructure failures (`commands/model-routing.md:108-113`), while the current execution path has separate plan, criteria, worktree, journal, and reviewer artifacts with different read times. The three failure traces above arise from different state transitions and need different controls.
- Suggestion: Replace Q-E with a failure matrix over `{contract, repo, attempt, environment, evidence}` × `{dispatch, mutate, verify, validate, land, resume}` and require one fail-closed invariant or recovery rule per populated cell.

## Verdict

Pattern F is unsafe to pilot as a shared-worktree execution architecture until artifact identity, overlap admission, and partial-effect recovery are explicit. Q-E has the wrong singular premise: "plan drift" is only one member of a distributed-state fault family.
