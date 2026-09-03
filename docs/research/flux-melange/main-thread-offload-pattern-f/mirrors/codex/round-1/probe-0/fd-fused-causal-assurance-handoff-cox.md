# fd-fused-causal-assurance-handoff-cox — round 1

## Findings Index

- [P0] revision-skew-produces-hybrid-verdicts — One PASS can combine a cached plan section, an executor's later plan revision, and criteria dereferenced at review time. (§The shape)
- [P0] per-task-passes-do-not-compose-at-landing — A verdict valid for an intermediate task state is retained after dependent work changes the state, with no final union-of-criteria gate on the landing commit. (§The shape)
- [P1] validator-can-mutate-beyond-dirty-tree-guard — A validator can commit a change and leave the worktree equally clean, so its PASS covers the pre-review diff while landing includes validator-authored state. (§The shape)

## Findings

### revision-skew-produces-hybrid-verdicts

- Severity: P0.
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md` §The shape; `scripts/orchestrate.py:353-356`, `scripts/orchestrate.py:786-800`, `scripts/orchestrate.py:1396-1419`, and `scripts/orchestrate.py:1443-1455`.
- What: Does Pattern F prevent a plan or criteria edit between orchestration start, executor dispatch, and validation from producing a hybrid assurance claim? The current runner snapshots each task section into memory at run start, tells the executor to read the mutable plan path later, and tells the reviewer to dereference the mutable criteria path later still. Resume compounds this: it reloads current plan content but skips prior PASS/WARN tasks solely from journal status. A concrete failure is plan A being parsed, plan B being read and implemented by Sonnet, criteria C being read by Opus, and the resulting PASS being treated as support for a single coherent item. The orchestrator can then land code for B under a verdict whose task specification came from A and whose oracle came from C.
- Evidence: `parse_plan_tasks(plan_path)` runs once before dispatch (`scripts/orchestrate.py:1412-1419`), while executor prompts carry only the plan path and instruct the worker to read it (`scripts/orchestrate.py:353-356`). Review uses the earlier in-memory `section` (`scripts/orchestrate.py:786-800`) but gives the validator a path to read sealed criteria (`scripts/orchestrate.py:603-609`). The run journal records absolute paths, not plan/criteria digests (`scripts/orchestrate.py:1443-1455`), and resume reconstructs completed tasks from status without comparing the old plan, manifest, criteria, or result state (`scripts/orchestrate.py:1396-1407`).
- Remediation: Bind every dispatch and verdict to immutable plan and criteria digests, base and result tree IDs, and attempt ID, and reject validation, resume, or landing when any coordinate differs.
- intersection_justification: The distributed-systems/handoff parent contributes the temporal fact that the three roles dereference different mutable representations and that resume reuses status across revisions; the verification/validator-value parent contributes the requirement that a verdict is meaningful only for the exact criterion and artifact it observed. Jointly, the system can present internally inconsistent evidence as corroboration; without either the revision skew or the assurance claim, this P0 does not exist.

### per-task-passes-do-not-compose-at-landing

- Severity: P0.
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md` §The shape; `scripts/orchestrate.py:753-818`, `scripts/orchestrate.py:1521-1531`, `scripts/orchestrate.py:1595-1597`; `skills/executing-plans/SKILL.md:91-106`.
- What: Does the landing decision re-establish every earlier verdict on the exact final integrated commit? Today, each validator rules on the diff since its own task started, that PASS immediately satisfies dependency edges, and later dependent tasks can alter the files or key links that made the earlier criterion true. There is no final validator run over the union of frozen criteria. A concrete failure is task A adding an authorization check and passing at H1, then task B refactoring the dependent handler at H2 and bypassing that check while satisfying only task B's criteria; the orchestrator retains A's H1 PASS and lands H2. The PASS was informative, but not about the state shipped to the user.
- Evidence: Each pipeline captures `head0` once and reviews `task_diff(project_dir, head0)` (`scripts/orchestrate.py:771-800`). An approved result is immediately marked done, unblocking dependents (`scripts/orchestrate.py:1521-1531`). After all waves, orchestration prints a summary and returns without an integrated assurance pass (`scripts/orchestrate.py:1595-1597`). The later plan-wide Must-Have check is manual and its failures are explicitly advisory (`skills/executing-plans/SKILL.md:91-106`), so it cannot bind all per-task claims to the landing commit.
- Remediation: Make landing contingent on one final validation of the exact proposed landing tree against the union of frozen criteria, invalidating any earlier verdict whose covered artifacts or key links changed afterward.
- intersection_justification: The distributed-systems/handoff parent contributes the causal sequence H1 PASS then H2 dependent mutation and the loss of applicability across that transition; the verification/validator-value parent contributes the non-compositional nature of criterion-scoped verdicts and the need for a final oracle over their union. Either parent alone sees ordinary sequencing or ordinary coverage, but only their intersection shows why individually sound PASSes jointly certify no landing state.

### validator-can-mutate-beyond-dirty-tree-guard

- Severity: P1.
- Where: `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md` §The shape; `scripts/orchestrate.py:694-745`.
- What: Does the validator remain observational when it has write capability and the mutation guard compares only porcelain status? The review prompt is built from the pre-review diff, Codex reviewers receive `workspace-write`, and Claude dispatch is not paired here with a filesystem snapshot. If a helpful validator edits and commits a fix, `git status --porcelain` can be clean both before and after, so the guard accepts its verdict. The orchestrator then treats a PASS over the old diff as assurance for a new, validator-authored HEAD that no independent validator observed.
- Evidence: `dispatch_review` materializes `task_diff(...)` before dispatch (`scripts/orchestrate.py:694-701`), grants Codex `workspace-write` (`scripts/orchestrate.py:703-714`), and determines contamination only by comparing `git status --porcelain` strings (`scripts/orchestrate.py:716-744`). It never compares HEAD/tree identity or runs the validator against an immutable checkout. A commit can therefore change repository history and content while preserving identical empty porcelain output.
- Suggestion: Run validators against an immutable snapshot or read-only checkout and bind the verdict to its tree ID; at minimum, reject any HEAD, index-tree, or worktree-tree change across review rather than comparing porcelain status alone.
- intersection_justification: The distributed-systems/handoff parent contributes the hidden state transition caused by a validator commit that the status-based guard cannot observe; the verification/validator-value parent contributes the independence rule that an oracle cannot both change the specimen and certify an earlier observation. Together they create false acceptance of unreviewed state; removing either the undetected transition or the assurance role reduces this to an ordinary permission issue.

## Verdict

Pattern F is not pilot-ready until a causal-assurance cell binds each plan/criteria revision, base/result tree, attempt, oracle, fault model, and verdict, and until that cell is re-established at landing. Q-E has the wrong premise: stale-plan execution already exists in the mutable-repository baseline, so the useful question is how offload changes its probability, detectability, and consequence rather than whether it is newly introduced.
