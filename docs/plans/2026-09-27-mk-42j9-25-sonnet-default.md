---
artifact_type: plan
bead: mk-42j9.25
stage: design
requirements:
  - F1: Unpinned bb threads default to Sonnet 5 medium
  - F2: Opus/Astra only through routing.yaml roles (planning, plan-review, validation, escalation)
  - F3: Per-project routing (records the mk-42j9.5-reversal coordinator table)
  - F4: Rotation successors carry forward the source's live model + effort (mk-42j9.25 part 1, mk-42j9.17)
  - F5: Shadow/A-B rollout gated by the mk-42j9.33 scorecard, automatic re-pin on regression
  - F6: Rollback
---
# Sonnet-default for unpinned threads, per-project routing, successor carry-forward

> **For agentic workers:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task. Phase 2 is NOT authorized until the lane-A coordinator says so.

**Bead:** mk-42j9.25 (bundles mk-42j9.17). Parent epic mk-42j9. Gate: mk-42j9.33.
**Goal:** Threads that nobody pinned run on Sonnet 5 at medium effort. Opus and Astra appear only where a routing.yaml role sends them (planning, plan-review, validation, escalation, and the per-project `coordination` seats), and a rotation successor runs exactly what its source ran.

**Architecture:** bb (the Aleph fork) decides a thread's model. Clavain's `config/routing.yaml` is the policy record, and `ic route dispatch` resolves it. Spawners (the Clavain handoff and coordination guidance, and Quilan rotation) turn a resolved role into explicit `bb` spawn flags. The unpinned default is enforced at two points:
- mainly at every spawner, which must stop hardcoding Opus;
- secondarily in bb's per-project execution defaults, for threads created with no model.

Static policy (roles, tiers, per-project coordination profiles) lives in routing.yaml and ships through a Clavain release. **Rollout state** (which lineage is in the control or treatment arm, and the prior execution tuple to restore) lives in a host-local runtime file that `route-spawn.sh` reads. The automatic rollback therefore never needs a commit or a release (fix round 1: A1, N4, N5).

**Tech Stack:** YAML policy + Go `ic` (unchanged), bash/python Clavain scripts, TypeScript Quilan plugin (`bb-plugin-handoff`), TypeScript Aleph server/CLI.

**Spec:** the mk-42j9.25 and mk-42j9.17 descriptions and notes; the mk-42j9.5 notes (reversal table); mk-42j9.33 (scorecard).

**Author declaration:** frontier plan by Opus 5.5 (`claude-opus-5-5`). This is the `planning-opus` seat in the `frontier-planning` chain; the primary seat, `planning-astra`, was not dispatched. The lane-A coordinator assigned authorship to this session, and a running session's effort cannot be changed by configuration. Policy hash at authoring: `7209d67e29c4d9e668cb1ecd1d4d931600902cba4031fd35866b8b434b34f79b` (installed 0.6.325). Decision context: `reasons: [foundational-invariants, broad-consequences]`, `investigation_active: true`.

## Observed facts (2026-09-27, read-only)

Evidence was collected read-only against `bb.db` (opened `mode=ro`), Aleph `feat/thecla-default-theme`, Quilan-live `8efadc3` (the production `handoff` plugin install, v0.7.2), Quilan dev `rpnv12-governor` `64d2b10`, and intercore `d5b2f00`.

1. **Where an unpinned thread's model comes from.** bb always passes an explicit model and effort to Claude Code, so `~/.claude/settings.json` `"model": "sonnet"` never reaches bb threads. For each turn, bb resolves model and effort in this order (Aleph `apps/server/src/services/threads/thread-execution-plan.ts:281-286, 315-323`):
   1. explicit input (a spawn flag or per-turn `--model`);
   2. `threads.model_override` / `reasoning_level_override` (**the pin**);
   3. **the thread's last `client/turn/requested` execution (sticky)**;
   4. `project_execution_defaults` for the thread's bb project, provider match only;
   5. the provider catalog default. For Claude Code that is `claude-opus-5-5`, effort `high`.

   Reasoning follows the same order and falls back to `medium`.
2. **A pin is `threads.model_override IS NOT NULL`.** Only `bb thread update --model/--reasoning-level` or the UI sticky picker sets it. Spawn flags do **not** pin; lane A itself was spawned with `--model claude-opus-5-5`, yet its override is NULL. `bb thread show --json` `pinnedAt` is the **sidebar** pin, not the model pin; the burn review's coordinator scan read that sidebar field.
3. **Project defaults.** `project_execution_defaults`: `proj_personal` = `claude-code / claude-opus-5-5 / medium`, and three more projects are Opus 5.5 medium. The table is rewritten only by app-UI creates (Aleph `project-execution-defaults.ts:45-56, 113-129`). There is **no CLI or SDK setter**; reads exist at `GET /api/v1/projects/:id/default-execution-options` / `sdk.projects.defaultExecutionOptions`.
4. **Where the threads live.**
   - `proj_personal` holds 72 of the 100+ non-archived threads, including the Clavain, Quilan, Aleph and bbOps coordinators and most worker lanes.
   - Coordinators for other logical projects sit in their own bb projects, for example Linsenkasten `proj_g4vgbq6jst` and Autarch `proj_dnrqkvnf5x`.
   - **A bb project id therefore does not identify a logical project.**
   - The After Them, Autosigil and Cujgel coordinators are currently **unpinned**.
5. **Fleet tally.** 45 unpinned claude-code threads last ran Opus or Fable, and 9 last ran Sonnet. 25 pinned threads run Opus variants. Most unpinned Opus threads are agent-spawned lanes that were given an explicit `--model claude-opus-5-5`.
6. **Live rotation (Quilan-live).** `server.ts:247` → `handleRotationIdle` (`rotation.ts:150-250`). It takes `sdk.threads.defaultExecutionOptions({threadId})` (the source's resolved options, which include the override) and spawns the successor with that model. `reasoningLevel` and `serviceTier` pass through only for a same-provider successor (`rotation.ts:247`). **The successor runs the right model but is not pinned**, so a pin is lost at the first rotation. The rotation is enabled per thread by the coordinator marking `rotateAt`.
7. **Handoff gaps (Quilan-live).**
   - `bb handoff` supports `--model` and `--effort`, and has no `--reasoning-level`; the dev branch adds that flag.
   - A plain handoff or a non-compact `--replace` that omits `--model` spawns with no model (`handoff.ts:693-694`). The successor then lands on project default, then catalog default, which is Opus. **This is the live cause of "successor falls back to project default".**
   - `--compact --replace` copies the model but not the `reasoningLevel`.
   - Failover spawns carry only `decision.model` (`failover.ts:460-464`).
   - `coordinator enable` has no `--model` or `--reasoning-level` (mk-42j9.17).
8. **Quilan dev branch** (not deployed):
   - `handleRotationIdle` always declines.
   - The checkpoint path has only test callers: `handleCheckpointClosure` → `beginCheckpointSpawn`, and `prepareCheckpointBriefing` / `prepareJudgeSubject`. The `routeBindingSchema.parse` sits at `checkpoint-briefing.ts:270`, inside `prepareJudgeSubject`.
   - `routing-receipt.ts` `resolveGovernedSpawnTuple` expects flat camelCase (`policySha256, providerId, model, reasoningLevel…`). Real `ic --json route dispatch` output is snake_case and nested (`policy_hash, profile.{backend,model,reasoning_effort,service_tier}, fallback_chain, policy_profile…`), so every real receipt fails `.parse()`, and the function has no production caller.
   - The checkpoint path is Quilan's runtime experiment (mk-rpnv.*), not this plan's.
9. **Nothing in Quilan runs `ic` or reads routing.yaml.** `scripts/coordinator-model.sh` exists only on the unmerged Clavain branch `feat/mk-42j9.12-13-coordinator-burn`. It prints the model with no effort, and **forbids Opus**, which contradicts the mk-42j9.5 reversal.
10. **`ic` already has a scoped overlay.** Under `reasoning.profiles.<name>`, a `{scope, roles}` entry is selected with `--policy-profile`. Its `scope` must equal `decision_context.scope` (`internal/routing/reasoning.go:150-160`). YAML decoding is non-strict, so unknown keys are ignored.

## Global Constraints

- Pinned threads are never changed by this work. mk applies pins with `bb thread update <id> --model … --reasoning-level medium`. **No task writes `threads.model_override`, for any thread.** Carry-forward and rollback use explicit spawn or turn inputs only, which bb's last-turn stickiness then holds. Spawn/tell flags are not pins (fact 2).
- Every routing failure fails closed. When `route-spawn.sh` exits non-zero, the spawn does not happen and the spawner reports it. There is no silent default and no hardcoded model.
- The mk-42j9.5-reversal table stays exactly as recorded. Opus 5.5 medium: Aleph, Clavain, Autarch, After Them, bbOps, Shadow Work, Quilan, SylvesteOps, Nartopo. Sonnet 5 medium: Autosigil, Rakes, Uncrancher, Cujgel, AgMoDB, Linsenkasten.
- Opus and Astra are reached only through routing.yaml roles: planning/frontier-planning, plan-review, validation, cross-lab-review, escalation, deep-execution, and the per-project `coordination` seats. Every spawner resolves model **and effort** through `ic route dispatch --role`; none hardcodes them.
- Quilan code is implemented by the Quilan coordinator (thr_n8twxx4psd). Aleph code is implemented by the Aleph coordinator, who gates its release; release and switch go through the publisher thread (thr_d8mtvmpmer). Lane A edits Clavain only.
- No push, PR, publish or version bump without coordinator authorization.
- `ic` (intercore) is unchanged by this plan. Lane C owns intercore effort changes.
- TDD: a failing test first for every behavior change. The only accepted failures are the recorded baseline: criteria-seal, executor-routing and zaka-collect in tests/routing; remontoire_attention bats #280–283; test_ic_selection; and the runtime evidence canary.

## Review Focus

- **Sticky last turn.** A thread that last ran Opus stays on Opus after a default flips (fact 1.3). The treatment cohort is therefore **new** threads only. Existing unpinned threads are neither migrated nor counted as treatment.
- **Pinned coordinators across rotation.** A successor of a pinned coordinator runs the pinned tuple through flags and stays unpinned (D2). Whether mk re-pins successors or authorizes pin inheritance is open decision D2b.
- **Cross-provider successors.** When the successor provider differs, the source effort may not exist on the target model. Carry-forward drops the effort to the target model's default and records the drop, rather than failing the spawn.
- **Campaign profile collision.** Only one `--policy-profile` applies. A `ci-campaign-pilot` (scope `mk-ag2s`) resolution inside a project with a project profile keeps the campaign profile, and the receipt records the skip.
- **Receipt schema drift.** If the `ic` output keys change, `route-spawn.sh` exits non-zero and the spawn stops (fail closed). Quilan rotation, which never calls `ic` at rotation time, carries the source forward.

---

## Design decisions (recommendations; D1–D5 need mk)

**D1. Where the "unpinned default" lives.** In three places, in order of leverage:
1. **Spawners.** Coordinators' lane spawns resolve role `lane` through Clavain, instead of `--model claude-opus-5-5` (fact 5). Clavain owns the guidance; each coordinator follows it.
2. **bb project defaults,** for threads created with no model. This needs Aleph Task 7:
   - a setter;
   - a **managed/locked** flag, so UI creates stop overwriting the row (`project-execution-defaults.ts:113-129`);
   - a **server-level fallback** for projects with no row, used instead of the catalog default.

   mk applies stage flips. The automatic actor (D4) writes only dedicated-project rows.
3. **Not changed:** the Claude Code catalog default and Aleph's last-turn stickiness.

`route-spawn.sh` reads the policy for spawners, and a read-only reconciler reports drift in bb defaults.

**D2. Carry-forward, with no pin writes.**
- Every successor (rotation, `--replace`, compact, failover) gets the source's resolved model and effort as **explicit spawn flags**. bb stickiness keeps them, so the successor runs the same tuple without a pin.
- Where a Quilan **alternate decision** fires (rotation headroom or failover), the alternate's model wins and the effort drops to the target default.
- **Treatment lineages** (N10): an unpinned successor re-resolves `route-spawn.sh --role lane` instead of carrying forward, so F1 converges. Everywhere else, it carries forward.

**D2b (mk).** A pinned coordinator's successor is unpinned, although it runs the same tuple. So after rotation, mk's pinned list stops matching bb state. The options:
- (a) mk re-pins successors with `bb thread update`, prompted by a Quilan notice;
- (b) mk explicitly authorizes Quilan to copy the source's own pin to its successor (an Aleph spawn option), with the ownership contract revised to say so.

Recommend (a) until rotation frequency makes it burdensome.

**D3. Per-project routing, keyed by logical project and not by bb project (fact 4).** Use `ic`'s existing profile overlay, with no `ic` change:
- `reasoning.profiles.project-<slug>: {scope: "project:<slug>", roles: {coordination: coordination-opus}}` for each of the 9 Opus coordinators.
- `reasoning.project_profiles: {<slug>: project-<slug>}`.
- `reasoning.project_aliases: {<bb project id>: <slug>}` for dedicated bb projects. `proj_personal` has no alias.
- `route-spawn.sh --project <slug|id>` resolves the slug and chooses the effective profile **before** it touches the context. An existing `CLAVAIN_POLICY_PROFILE` wins and keeps its own scope. The project is recorded separately in the receipt (A8).
- `--project` is mandatory for role `coordination`. There is no silent fleet default for a coordinator.

Rejected alternatives:
- keying on bb project id, which cannot separate the Personal coordinators;
- per-project policy files, which fork the hash;
- a new `ic --project` flag, which is lane C's code (possible follow-up).

**D4. Automatic "re-pin" means restoring the prior execution, never writing overrides.** F5's "re-pin" is read as "return the regressed lineage to its prior model"; mk should confirm. On a lane-B `regressed` verdict for lineage L, the Quilan actor does four things:
1. Sets L's arm to `reverted` in the runtime rollout state. `route-spawn.sh --role lane` then resolves L's recorded prior tuple.
2. For each live unpinned thread in L whose last execution is the treatment tuple, sends `bb thread tell <id> --model <prior> --reasoning-level <prior>` with a one-line rollback notice. This is explicit turn input: it becomes sticky and is not a pin (A3).
3. Restores a bb project default only when the project is **dedicated to L** (all its lineages are L). It never writes `proj_personal` or any other shared project (A2).
4. Records a receipt.

mk must authorize Quilan as the writer of (1)–(3).

**D5. Lineage is the cohort key.** A lineage is Quilan's `coordinatorId` (it survives rotation) plus every thread that lineage spawns. Lane B's scorecard (mk-42j9.33, currently keyed by project) and the bead→lineage attribution (assignee or actor → coordinatorId) must be agreed with lane B **before** stage-0 baselining (N6).

**Where each part lands.**

| Part | Owner | Tasks |
|---|---|---|
| routing.yaml roles/tiers/profiles/aliases; `route-spawn.sh`; rollout-state schema and `rollout-arm.sh`; reconciler; spawner guidance; docs; tests | Clavain (lane A) | 1–5 |
| Carry-forward, coordinator execution flags, fitted receipt schema, rollback actor, lineage id lookup | Quilan coordinator | 6, 9 |
| Project-default setter, managed/locked rows, server fallback default | Aleph coordinator | 7 |
| Scorecard metrics, lineage key, thresholds, verdict JSON | lane B (mk-42j9.33) | consumed in 8, 9 |
| Stage approvals, Clavain release/publication, shared-project default flips, coordinator pins | mk | 8 |

## Must-Haves

**Truths**
- In a treatment lineage, `route-spawn.sh --role lane --lineage L` gives `claude-code claude-sonnet-5 medium`. In a control lineage it gives the status-quo `lane` tier. In a reverted lineage it gives L's recorded prior tuple.
- `route-spawn.sh --role coordination --project clavain` prints `claude-code claude-opus-5-5 medium`. `--project autosigil` and `--project proj_3ktdvx76vj` print Sonnet 5 medium. Omitting `--project` exits 2.
- `route-spawn.sh --role plan-review` without `--producer-identity` exits non-zero, and nothing is spawned.
- Every successor runs its source's tuple, or the Quilan alternate's, and no `model_override` changes.
- A regressed verdict for lineage L changes L's arm, L's live threads' next turns and L's dedicated defaults within one Quilan cycle. It does not change any other lineage or any shared project default. There is no release in the loop.

**Artifacts**
- `config/routing.yaml`: roles `main-session` and `lane`; tiers `main-sonnet`, `main-sol`, `lane-status-quo`, `coordination-opus`; `reasoning.profiles.project-*`, `project_profiles`, `project_aliases`.
- `scripts/route-spawn.sh`; `scripts/rollout-arm.sh`; the rollout-state schema `schemas/rollout-state.schema.json`.
- `scripts/project-defaults-reconcile.py`.
- Tests: `tests/routing/route-spawn-test.sh`, `project-profiles-test.sh`, `rollout-arm-test.sh`, `project-defaults-reconcile-test.sh`; a structural no-hardcoded-Opus-spawn test.

**Key Links**
- Spawner → `route-spawn.sh` (arm lookup) → `ic route dispatch` → `bb thread spawn --provider --model --reasoning-level`.
- Quilan rotation → source's resolved tuple → successor flags.
- Lane-B verdict → Quilan actor → rollout state + `bb thread tell --model` + dedicated defaults → reconciler.

## Acceptance Criteria

1. The new tests pass. The routing, structural and shell suites show no new failures against the recorded baseline.
2. All 15 coordinators in the table resolve `coordination` correctly by slug and by alias, and the test asserts all 15.
3. `main-session` resolves Sonnet 5 medium, and its fallback chain never includes Opus.
4. Quilan tests cover:
   - carry-forward on rotation, `--replace`, compact and failover;
   - an alternate beating carry-forward;
   - the cross-provider effort drop;
   - no override write in any path;
   - pin beats marking;
   - `--clear-execution`;
   - a stale marking being ignored.
5. Before stage 0 is declared, the Clavain release carrying Tasks 1–3 is installed on every coordinator host, and each host's receipt `policy_hash` equals the committed hash.
6. Rollback is exercised on a synthetic regression, with one regressed and one healthy lineage both inside `proj_personal`. Only the regressed lineage changes.

---

### Task 1: routing.yaml roles, tiers, profiles, aliases (Clavain)

**Files:** Modify `config/routing.yaml`. Test `tests/routing/project-profiles-test.sh` (new).

- Tier `main-sonnet`: role `main-session`, claude, `claude-sonnet-5`, medium, `fallbacks: [main-sol]`. Tier `main-sol`: `gpt-5.6-sol`, medium. There is no Opus fallback.
- Role `lane` → tier `lane-status-quo`: `claude-opus-5-5`, medium, `fallbacks: [main-sonnet]`. This is today's de facto lane spawn, recorded as policy so the control arm is explicit and governed (N4). It flips to `main-sonnet` only at stage 2 keep.
- Tier `coordination-opus`: `claude-opus-5-5`, medium, `fallbacks: [coordination-sonnet]`. The fleet `coordination` stays `coordination-sonnet`.
- The 9 profiles, `project_profiles`, and `project_aliases`: verify ids live against each coordinator thread's `project_id`. Names are ambiguous. As checked live on 2026-09-27, `After-Them` is `proj_2apc9fag87` but the After Them coordinator runs in `After-Them-rust` `proj_fsrj27djw2`, and the Rakes coordinator runs in `rotnb` `proj_sy6myvvmq2`.

**Tests first:**
- Each profile's scope is `project:<slug>`.
- Each alias targets a table slug.
- No profile maps `main-session` or `lane` to Astra.
- `ic` resolves `coordination` with `--policy-profile=project-clavain` and scope `project:clavain` to Opus medium, and without a profile to Sonnet.
- If `ic` rejects `:` in scope, the test fails, and scope becomes `project-<slug>`.

### Task 2: `scripts/route-spawn.sh` and `scripts/rollout-arm.sh` (Clavain; supersedes `coordinator-model.sh`)

**`route-spawn.sh`**
- Usage: `route-spawn.sh --role <role> [--project <slug|id>] [--lineage <coordinatorId>] [--producer-identity <id>] [--context-file <json>]`.
- `--project` is required for `coordination`. `--lineage` is required for `lane`. `--producer-identity` is required for the roles `ic` demands it for (`plan-review`, `validation`, `cross-lab-review`), and is forwarded to `ic` (A5).
- **Arm lookup** for `lane`: read `${XDG_STATE_HOME:-$HOME/.local/state}/clavain/rollout/mk-42j9-25.json`.
  - `treatment` → resolve `main-session`.
  - `reverted` → print the recorded `prior` tuple; no `ic` call.
  - `control`, or absent → resolve `lane`.
- **Profile selection** (A8): pick the effective profile first. An existing `CLAVAIN_POLICY_PROFILE` wins and its context scope is untouched. Otherwise use the project profile, with its scope written into a temporary copy of the context.
- `available_models`: populated from `bb pool status --json` when available; otherwise omitted, and the receipt notes that fallbacks were not evaluated (N7).
- Output: `<bb-provider> <model> <effort>` on stdout. The receipt goes under `${ROUTE_SPAWN_RECEIPT_DIR:-$XDG_STATE_HOME/clavain/route-spawn}/` and records the `ic` output, slug, profile decision, arm, lineage and policy hash.
- Exit codes: 0 ok; 2 usage; 3 resolution failure, with empty stdout and **fail closed**.

**`rollout-arm.sh get|set <lineage> <control|treatment|reverted> [--prior provider,model,effort] [--verdict <path>]`**
- Writes atomically under `flock`, validated against `schemas/rollout-state.schema.json`.
- Used by mk or the lane-A coordinator for stage moves, and by the Quilan actor for `reverted`.
- The state file is host-local. Each coordinator host holds its own copy, and the stage checklist verifies it on every host.

**Tests first:**
- the 15-row table by slug and by alias;
- missing `--project` or `--lineage`;
- a missing producer identity for `plan-review`;
- same-producer exclusion;
- `ic` missing or a bad policy gives 3 with empty stdout;
- campaign + project: `ci-campaign-pilot` with scope `mk-ag2s` resolves and records the project;
- each arm, including `reverted` without `ic`;
- a concurrent `set`.

### Task 3: spawner guidance (Clavain)

**Files:** `skills/dispatching-parallel-agents/SKILL.md` (full and compact coordinator sections), `docs/canon/reasoning-routing-operations.md` § "Spawning bb threads", and the handoff command doc if it is on main (otherwise note on mk-42j9.12 that coordburn must adopt it).

**Rules:**
- Worker lanes use `route-spawn.sh --role lane --lineage <own coordinatorId> --project <own slug>` → `bb thread spawn --provider P --model M --reasoning-level E`.
- Frontier lanes use `planning`, or `plan-review` / `validation` with `--producer-identity` taken from the producer's receipt.
- Pinned coordinators' self-handoffs pass no model; Quilan carries forward.
- On a non-zero exit: do not spawn, and report.
- The guidance is arm-neutral. Until a lineage is set to `treatment`, `lane` resolves the status quo, so landing the guidance does not contaminate the controls (N4).

**Test first:** a structural test failing on a literal Opus or Fable model id in any `bb thread spawn` / `bb handoff` line under `skills/ commands/ hooks/ docs/canon/`.

### Task 4: `scripts/project-defaults-reconcile.py` (Clavain, read-only)

- It compares bb defaults (`bb.db` read-only, or the HTTP read route) against the stage's intended values, and flags UI-create overwrites (A4).
- It reports exposure per lineage: unpinned threads by last-turn model, and threads whose last turn differs from their lineage's arm.
- It never writes.

**Tests first:** a fixture DB with 3 projects and 6 threads (pinned, unpinned, sticky Opus, and two lineages in one project).

### Task 5: docs and bead records (Clavain)

- `reasoning-routing-operations.md` § "Per-project routing and rollout arms".
- Note on mk-42j9.12 that `coordinator-model.sh` is superseded.

### Task 6: Quilan carry-forward and coordinator execution flags (Quilan coordinator implements)

This is a behavior spec on the live tree (Quilan-live / main). The checkpoint path stays Quilan's experiment.

1. **Carry-forward** (D2) on rotation, plain and non-compact `--replace`, `--compact --replace`, and failover.
   - Explicit `--provider/--model/--reasoning-level` from the source's resolved execution. The implicit fall to the project or catalog default is closed (fact 7).
   - The Quilan alternate decision beats carry-forward, with a cross-provider effort drop.
   - **No `model_override` write.**
   - When the source was pinned, post a notice to mk's coordinator channel so mk can re-pin (D2b option a).
   - For a treatment lineage, an unpinned successor re-resolves via the arm, per the recorded tuple Quilan reads from the rollout state; no `ic` call.
2. **`coordinator enable --model <m> --reasoning-level <e> [--route-receipt <path>]` and `--clear-execution`** (mk-42j9.17, N1).
   - The coordinator's own session resolves the tuple first with `route-spawn.sh --role coordination --project <slug>`. Quilan stores the tuple, the receipt's `policy_hash`, and the source's execution **at enable time**. Quilan's server never calls `route-spawn.sh` or `ic` (N8).
   - Precedence: source pin > marking > live execution. An enable whose tuple conflicts with a pinned source is refused (N2).
   - A marking is ignored if the source's live execution has changed since enable (A7).
   - `--clear-execution` removes the stored tuple.
3. **Lineage id.** `bb handoff coordinator id` (or its equivalent) prints the thread's `coordinatorId` for use as `--lineage`. Threads spawned by a coordinator inherit it through spawn metadata, if bb supports that; otherwise through the spawner's `--lineage` in the receipt.
4. **`routing-receipt.ts`.** Fit the schema to real snake_case `ic` output (fixture `.clavain/decisions/mk-rpnv.2-route.json` plus a fresh sample with `policy_profile`), for validating `--route-receipt`. A parse failure means the enable is refused with a clear error.

**Quilan tests:** as in Acceptance 4.

### Task 7: Aleph project defaults (Aleph coordinator implements)

- `bb project defaults show|set|lock|unlock <project> --provider --model --reasoning-level`, plus SDK setters.
- A locked row is not overwritten by UI creates.
- A server-level fallback default (config) applies to projects with no row, before the catalog default.
- Through the Aleph release-coordinator gate and the publisher thread (thr_d8mtvmpmer).
- No spawn-time pin option (A6, N3, N9).

### Task 8: rollout (mk approves stages; lane B gates)

**Precondition for every stage:** the Clavain release carrying the needed policy is installed on each coordinator host, with the receipt `policy_hash` matching (N5), and the rollout state is present on each host. Each release is a publication step mk approves; rollback never needs one.

| Stage | What changes | Cohort | Exit rule |
|---|---|---|---|
| 0: shadow | Release Tasks 1–3 and Quilan Task 6. Every lineage is `control`, so behaviour is unchanged except that carry-forward closes the fall-to-Opus gaps. The reconciler runs daily, and lane B baselines per lineage (D5). | none | ≥7 days of baseline for ≥2 lineages, or lane B's minimum-sample rule |
| 1: A/B | The 6 Sonnet-coordinator lineages are set to `treatment` (`rollout-arm.sh`). Their dedicated bb project defaults are set to Sonnet medium **and locked** (Task 7). The 9 Opus lineages stay `control`. | new lanes, and successors, in treatment lineages | 7 days plus lane B's minimum closed beads |
| 2: expand | The 9 Opus lineages go to `treatment`. Once all Personal lineages keep for a full window, mk sets and locks `proj_personal` and sets the server fallback. Then the fleet `lane` role flips to `main-sonnet` in a release, and the arms retire. Coordinator pins are unchanged. | all new unpinned threads | 7 days, same metrics |

**Keep rule** (lane B sets the thresholds; stage 1 does not start without them). Per lineage, against its own baseline and the control drift:
- P0/P1 findings per deliverable do not rise;
- escaped defects within 7 days do not rise;
- rework turns per bead stay within the threshold;
- beads closed per hour stay within the threshold;
- weighted burn per closed bead falls.

A regression triggers Task 9 for that lineage only.

### Task 9: regression rollback actor (Quilan implements; lane B supplies the verdict)

- Input: lane B's verdict JSON `{lineage, change: "mk-42j9.25", verdict: regressed|holds|insufficient, metrics}` (schema agreed before stage 0).
- On `regressed`, run steps (1)–(4) of D4. The actor is idempotent and does not wait for a release.
- On `holds` at a stage exit, nothing changes. mk advances the stage.
- Tested with a synthetic regression: one regressed lineage and one healthy lineage, both in `proj_personal` (Acceptance 6).

## Rollback

- **One lineage (automatic):** Task 9.
- **The whole change (manual, mk):**
  1. `rollout-arm.sh set <each lineage> reverted`.
  2. `bb project defaults set` + `unlock` from the snapshot at `$XDG_STATE_HOME/clavain/project-defaults-snapshot-<date>.json`, taken before stage 1. The snapshot also records each treatment lineage's prior tuple for `--prior`.
  3. Tells to live treatment threads, as in D4 (2).
  4. Revert the Task 1 policy in the next Clavain release.
- **Quilan:** `coordinator enable --clear-execution` per coordinator. Carry-forward itself is the status quo and stays.
- **Pinned coordinators** are never touched at any step.

## Handoff to Phase 2

- **Decisions for mk:**
  - D1–D5;
  - D2b, re-pin successors or authorize pin inheritance;
  - reading F5's "re-pin" as prior-execution restore (D4);
  - authorizing Quilan as the automatic writer of the rollout arm, tells and dedicated defaults;
  - the stage-1 cohort;
  - Clavain release timing for stage 0;
  - whether to pin the unpinned After Them, Autosigil and Cujgel coordinators.
- **Constraints:** Global Constraints.
- **Verification:** Acceptance Criteria.
- **Escalation:**
  - If Task 7 is refused, shared-project defaults stay UI-driven and stage 2's default half is manual.
  - If lane B has no lineage key or thresholds, stage 0 baselining does not start.
  - If bb cannot carry lineage through spawn metadata, attribution relies on receipts, and lane B must accept that.

## Review record

- **Round 1 reviewers.**
  - **Astra** (governed `plan-review` → review-astra, gpt-6-astra xhigh, producer `claude-opus-5-5`; dispatch f3a19004, 436k/6.1k tokens): REJECT, 6 P1 and 2 P2.
  - **Opus 5.5** (declared same-model, adversarial orthogonal, fresh context): REJECT. It confirmed A1–A8 and added N1–N10.
- **Fix round 1 changes:**
  - A1/N4/N5: the `lane` role, runtime arms and a release precondition.
  - A2: lineage-scoped rollback; no automated shared-default write.
  - A3: `bb thread tell --model` for live threads.
  - A4: Aleph locked rows and the server fallback.
  - A5/N7: producer identity, `--provider`, `available_models`, fail-closed routing.
  - A6/N3/N9: pin writes dropped, alternates first, the Task 7 pin option removed.
  - A7/N2/N8: pin beats marking, stale markings ignored, enable-time resolution in the coordinator's session.
  - A8: profile chosen before scope.
  - N1: `--clear-execution`.
  - N6: lineage key agreed with lane B (D5).
  - N10: treatment successors re-resolve.
