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

- Pinned threads are never changed by this work. mk applies pins with `bb thread update <id> --model … --reasoning-level medium`. No task writes `threads.model_override` except Task 6's copy of an existing pin to that pin's own rotation successor (Decision D2).
- The mk-42j9.5-reversal table stays exactly as recorded. Opus 5.5 medium: Aleph, Clavain, Autarch, After Them, bbOps, Shadow Work, Quilan, SylvesteOps, Nartopo. Sonnet 5 medium: Autosigil, Rakes, Uncrancher, Cujgel, AgMoDB, Linsenkasten.
- Opus and Astra are reached only through routing.yaml roles: planning/frontier-planning, plan-review, validation, cross-lab-review, escalation, deep-execution, and the per-project `coordination` seats. Every spawner resolves model **and effort** through `ic route dispatch --role`; none hardcodes them.
- Quilan code is implemented by the Quilan coordinator (thr_n8twxx4psd). Aleph code is implemented by the Aleph coordinator, who gates its release; release and switch go through the publisher thread (thr_d8mtvmpmer). Lane A edits Clavain only.
- No push, PR, publish or version bump without coordinator authorization.
- `ic` (intercore) is unchanged by this plan. Lane C owns intercore effort changes.
- TDD: a failing test first for every behavior change. The only accepted failures are the recorded baseline: criteria-seal, executor-routing and zaka-collect in tests/routing; remontoire_attention bats #280–283; test_ic_selection; and the runtime evidence canary.

## Review Focus

- **Sticky last turn.** A thread that last ran Opus stays on Opus after a default flips (fact 1.3). The treatment cohort is therefore **new** threads only. Existing unpinned threads are neither migrated nor counted as treatment.
- **Unpinned successors carried as pins.** If carry-forward pins the successor of an *unpinned* source, the successor freezes on the old model and rollback cannot reach it. Task 6 pins only when the source was pinned; otherwise it passes spawn flags only.
- **Cross-provider successors.** When the successor provider differs, the source effort may not exist on the target model. Carry-forward drops the effort to the target model's default and records the drop, rather than failing the spawn.
- **Campaign profile collision.** Only one `--policy-profile` applies. A `ci-campaign-pilot` (scope `mk-ag2s`) resolution inside a project with a project profile keeps the campaign profile, and the receipt records the skip.
- **Receipt schema drift.** If the `ic` output keys change, `route-spawn.sh` exits non-zero. The spawner then falls back to carry-forward or to no model flag, and **never** to a hardcoded Opus.

---

## Design decisions (recommendations; D1–D4 need mk)

**D1. Where the "unpinned default" lives.** In three places, in order of leverage:
1. **Spawners.** Coordinators' lane spawns and handoffs resolve `main-session` or a governed role through Clavain, instead of `--model claude-opus-5-5` (fact 5). Clavain owns the guidance; each coordinator follows it.
2. **bb `project_execution_defaults`,** for threads created with no model. The write needs a setter that does not exist yet, which is Aleph Task 7. mk (or the Quilan re-pin actor, D4) applies it, and Clavain never writes `bb.db`.
3. **Not changed:** the Claude Code catalog default, which is not ours to set. Aleph's last-turn stickiness is also left alone, because changing it alters bb semantics for all users; that is an open option for mk.

Clavain routing.yaml records the desired default as role `main-session`, and a read-only reconciler reports drift.

**D2. Pin carry-forward.** When the source has `model_override` set, the successor gets the same override (model and effort). When the source is unpinned, the successor gets the source's live model and effort as spawn flags only, and stays unpinned. This is the only automated override write, and it propagates mk's own pin to the same logical coordinator. mk should confirm it.

**D3. The per-project routing mechanism, keyed by logical project and not by bb project (fact 4).** Reuse `ic`'s existing profile overlay, with no `ic` change:
- `reasoning.profiles.project-<slug>: {scope: "project:<slug>", roles: {...}}` for each project that deviates from the fleet default.
- `reasoning.project_profiles: {<slug>: project-<slug>}` lists which slugs have one.
- `reasoning.project_aliases: {<bb project id>: <slug>}` maps dedicated bb projects to a slug. `proj_personal` has **no** alias, so its threads name their slug explicitly.
- A Clavain wrapper, `scripts/route-spawn.sh --project <slug|bb project id>`, resolves the slug, passes `--policy-profile`, and sets `scope` in the decision context. The receipt's `policy_profile` names the profile.
- The slug source for a spawner:
  - for a coordinator, its Quilan marking field `project` (Task 6);
  - for a worker lane, the spawning coordinator's slug, passed explicitly;
  - otherwise the alias, and failing that, the fleet default.

Rejected alternatives:
- Keying on bb project id cannot tell the Clavain coordinator from the Quilan coordinator.
- Per-project overlay files through `CLAVAIN_ROUTING_POLICY` fork the policy hash and drift.
- A new `ic --project` flag is an intercore change that collides with lane C; it can be a follow-up bead if mk prefers it.

**D4. What "automatic re-pin on regression" writes.** On a scorecard regression for cohort P:
- The spawner side reverts by a policy change: remove P's `main-session` treatment entry. That is a Clavain commit, which the re-pin actor proposes and the lane-A coordinator lands.
- The bb-default side is restored by the Quilan re-pin actor to the prior value recorded in `project_profiles_prior`.

It never touches `threads.model_override`. mk must authorize Quilan as the automatic writer of project defaults.

**Where each part lands.**

| Part | Owner | Tasks |
|---|---|---|
| routing.yaml roles, tiers, profiles, aliases; `route-spawn.sh`; reconciler; spawner guidance; docs; tests | Clavain (lane A) | 1–5 |
| Carry-forward, coordinator `--model/--reasoning-level/--project`, fitted receipt schema, re-pin actor | Quilan coordinator | 6, 9 |
| Project-default setter; spawn-time pin option; override read in SDK | Aleph coordinator | 7 |
| Scorecard metrics, cohort thresholds, regression verdict | lane B (mk-42j9.33) | consumed in 8 |
| Stage approvals, project-default flips before Task 9 exists, coordinator pins | mk | 8 |

## Must-Haves

**Truths**
- A worker lane spawned per the Task 3 guidance by a treatment coordinator runs `claude-sonnet-5` at `medium`, unpinned.
- `route-spawn.sh --role coordination --project clavain` prints `claude-code claude-opus-5-5 medium` plus a receipt path.
  - `--project autosigil` and `--project proj_3ktdvx76vj` (alias) print `claude-code claude-sonnet-5 medium`.
  - An unlisted project gets the fleet default.
- `route-spawn.sh --role main-session` prints `claude-code claude-sonnet-5 medium` for every slug.
- A rotation successor of a pinned Opus-medium coordinator is pinned Opus medium, and a successor of an unpinned Sonnet thread is unpinned Sonnet.
- A regression verdict on a treatment cohort restores its prior defaults within one Quilan evaluation cycle, and a receipt records it.

**Artifacts**
- `config/routing.yaml`: role `main-session`; tiers `main-sonnet`, `main-sol`, `coordination-opus`; `reasoning.profiles.project-*`; `reasoning.project_profiles`, `project_aliases`, `project_profiles_prior`.
- `scripts/route-spawn.sh`: role + project → `<bb-provider> <model> <effort>` + receipt.
- `scripts/project-defaults-reconcile.py`: read-only drift and exposure report.
- Tests: `tests/routing/route-spawn-test.sh`, `project-profiles-test.sh`, `project-defaults-reconcile-test.sh`; a structural no-hardcoded-Opus-spawn test.

**Key Links**
- Spawner → `route-spawn.sh` → `ic route dispatch --policy-profile` → bb spawn flags.
- Quilan rotation → source override → successor override (D2).
- Scorecard verdict (lane B) → re-pin actor → policy entry and bb default → reconciler.

## Acceptance Criteria

1. The new routing tests pass. The routing, structural and shell suites show no new failures against the recorded baseline.
2. All 15 coordinators in the mk-42j9.5 table resolve `coordination` to the table's model at `medium` through `route-spawn.sh --project <slug>`, and the test asserts all 15.
3. `main-session` resolves Sonnet 5 medium, and its capacity fallback is `gpt-5.6-sol` medium, never Opus.
4. Quilan tests cover four cases: pinned to pinned, unpinned to unpinned (no override write), cross-provider effort drop, and marking precedence.
5. The shadow reconciler report exists for at least 2 cohorts before any treatment starts.
6. Every stage transition in Task 8 cites a lane-B verdict artifact, and rollback is exercised once on a synthetic regression.

---

### Task 1: routing.yaml roles, tiers, profiles, aliases (Clavain)

**Files:** Modify `config/routing.yaml`. Test `tests/routing/project-profiles-test.sh` (new).

- Tier `main-sonnet`: role `main-session`, backend claude, `claude-sonnet-5`, `medium`, standard, `fallbacks: [main-sol]`. Tier `main-sol` (`gpt-5.6-sol`, medium). There is no Opus fallback: an outage must not upgrade the default.
- Tier `coordination-opus`: role `coordination`, `claude-opus-5-5`, `medium`, `fallbacks: [coordination-sonnet]`.
- `dispatch.roles.main-session: main-sonnet`. Keep `coordination: coordination-sonnet` as the fleet default; the 6 Sonnet coordinators need no profile.
- 9 profiles `project-<slug>`, each with `scope: "project:<slug>"` and `roles: {coordination: coordination-opus}`, for aleph, clavain, autarch, after-them, bbops, shadow-work, quilan, sylvesteops and nartopo.
- `project_profiles` lists those 9. `project_aliases` maps each dedicated bb project to its slug, including the 6 Sonnet projects so `--project <bb id>` works. `project_profiles_prior: {}`.
- Take the ids read-only from `bb project list --json` and cross-check them against each coordinator thread's `project_id`, then verify them live before commit. A coordinator whose bb project is shared (for example `proj_personal`) gets no alias. Names alone are ambiguous. As checked live on 2026-09-27, `After-Them` is `proj_2apc9fag87`, while the After Them coordinator runs in `After-Them-rust` `proj_fsrj27djw2`, and the Rakes coordinator runs in `rotnb` `proj_sy6myvvmq2`. Both ids get aliases, and the test asserts each one.

**Tests first:**
- Every `project_profiles` value names a profile whose `scope == "project:"+slug`.
- Every alias targets a slug from the 15-row table.
- No profile maps `main-session` to an Opus or Astra tier.
- `ic --json route dispatch --role=coordination --policy-profile=project-clavain` with context `scope=project:clavain` returns `claude-opus-5-5` / `medium` / `policy_profile=project-clavain`. The same call without a profile returns Sonnet.

**Run:** `bash tests/routing/project-profiles-test.sh`. Expected: FAIL before, PASS after.

### Task 2: `scripts/route-spawn.sh` (Clavain; supersedes `coordinator-model.sh`)

**Files:** Create `scripts/route-spawn.sh`. Test `tests/routing/route-spawn-test.sh`.

- Usage: `route-spawn.sh --role <role> [--project <slug|bb project id>] [--context-file <json>]`.
- Resolve the alias, then the slug, then the profile, with `python3` + PyYAML; confirm the dependency is present during implementation. Merge `scope` into a temporary copy of the context and run `ic --json route dispatch` with `--policy-profile` when one applies.
- If `CLAVAIN_POLICY_PROFILE` is already set, keep it and record `project_profile_skipped` in the receipt.
- Print `<bb-provider> <model> <effort>`. Write the receipt JSON (ic output plus slug and profile decision) under `${ROUTE_SPAWN_RECEIPT_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/clavain/route-spawn}/`.
- Map backend `codex→codex` and everything else to `claude-code`, with the model/effort allowlist regex.
- **Failure:** exit 3 with empty stdout. Callers carry forward or omit flags. This removes `coordinator-model.sh`'s hardcoded Sonnet fallback and its Opus ban.

**Tests first:**
- The 15-row table by slug and by alias.
- An unlisted project.
- `main-session`.
- `ic` missing or a bad policy exits 3 with empty stdout.
- Campaign precedence.

### Task 3: spawner guidance (Clavain)

**Files:** `skills/dispatching-parallel-agents/SKILL.md` (full and compact coordinator sections), `docs/canon/reasoning-routing-operations.md` (new subsection "Spawning bb threads"), and the handoff command doc if it is on main; otherwise record that the coordburn branch must adopt this.

**Rules:**
- A worker lane spawned as a bb thread resolves `main-session`, which is Sonnet 5 medium.
- A lane whose job is frontier planning or review resolves `planning`, `plan-review` or `validation`, with `--producer-identity` where required.
- `--model` and `--reasoning-level` both come from `route-spawn.sh --project <coordinator slug>`.
- A self-rotation of a pinned coordinator passes no model; Quilan carries the pin (Task 6).
- If `route-spawn.sh` fails, spawn with no model flag and report it; never hardcode Opus.

**Test first:** a structural test that fails on any `bb thread spawn` / `bb handoff` line under `skills/ commands/ hooks/ docs/canon/` carrying a literal Opus or Fable model id.

### Task 4: `scripts/project-defaults-reconcile.py` (Clavain, read-only)

- It reads `project_execution_defaults` (`bb.db` `mode=ro`, or the HTTP read route when `BB_SERVER` is set) and compares it with the policy's desired `main-session` value per bb project.
- It reports exposure: the count of unpinned threads by last-turn model, per bb project and per spawning coordinator lineage (join `threads.model_override IS NULL` with the last `client/turn/requested`). This is the cohort-exposure input lane B needs, and it corrects the sidebar-pin confusion (fact 2).
- It never writes.

**Tests first:** a fixture SQLite database with 3 projects and 6 threads (pinned and unpinned, sticky Opus) gives the expected drift and exposure JSON.

### Task 5: docs and bead records (Clavain)

- Add `reasoning-routing-operations.md` § "Per-project routing": profiles, aliases, slug sources, campaign precedence and rollback. The short canon gets one line at most.
- Note on mk-42j9.12 that `coordinator-model.sh` is superseded by `route-spawn.sh --role coordination`.

### Task 6: Quilan carry-forward and coordinator override (Quilan coordinator implements)

Behavior specification only; Quilan chooses the code. Target the live tree (Quilan-live / main); the dormant checkpoint path stays Quilan's experiment.

1. **Rotation, `--compact --replace`, plain `--replace` handoff, failover.** Carry forward the source's resolved model and effort. Same provider: both. Cross provider: model per the rotation decision, and effort drops to the target default with the drop logged. If the source is pinned, the successor gets the same override through Task 7's spawn option. There is never an implicit fall to the project or catalog default for a replacement (closes fact 7).
2. **`coordinator enable --model <m> --reasoning-level <e> --project <slug>` (mk-42j9.17).**
   - The flags are stored on the marking.
   - Precedence: marking override > source pin > source live execution.
   - Optional `--route-role coordination`: run Clavain `route-spawn.sh` **once, at enable time**, and store the result and receipt path, so Quilan stays `ic`-free per rotation.
3. **`routing-receipt.ts`.** Fit the schema to real snake_case `ic` output (fixture: `.clavain/decisions/mk-rpnv.2-route.json` plus a fresh sample with `policy_profile`). Use it only for the item-2 receipt. A parse failure leaves the marking without an override (carry-forward) and never reaches the catalog default.

**Quilan tests:** pinned to pinned; unpinned to unpinned with no override write; cross-provider effort drop; marking precedence; parse failure falls back to carry-forward.

### Task 7: Aleph setter and pin option (Aleph coordinator implements)

- `bb project defaults show|set <project> --provider --model --reasoning-level`, as an authenticated PATCH on the existing route, plus `sdk.projects.setDefaultExecutionOptions`.
- A spawn-time option to persist the requested execution as the override (`pinExecution: true`), and `modelOverride` / `reasoningLevelOverride` exposed read-only to plugins.
- Through the Aleph release-coordinator gate and the publisher thread.

### Task 8: rollout (mk approves stages; lane B gates)

The cohort unit is the **coordinator lineage**: a coordinator plus the threads it spawns. bb projects cannot separate the `proj_personal` coordinators (fact 4).

| Stage | What changes | Cohort | Exit rule |
|---|---|---|---|
| 0: shadow | Tasks 1–6 land. Carry-forward only preserves the status quo. The guidance lands with `main-session` recorded but spawners unchanged. The reconciler runs daily, and lane B baselines per lineage. | none | ≥7 days of baseline for ≥2 lineages, or lane B's minimum-sample rule |
| 1: A/B | The 6 Sonnet-coordinator lineages (Autosigil, Rakes, Uncrancher, Cujgel, AgMoDB, Linsenkasten) adopt the Task 3 spawns (lanes on `main-session`). mk flips their dedicated bb projects' defaults to Sonnet 5 medium via Task 7. The 9 Opus lineages are concurrent controls. | new lanes and threads in treatment lineages | 7 days (the escaped-defect window) plus lane B's minimum closed beads |
| 2: expand | The 9 Opus lineages adopt `main-session` for their lanes. mk flips `proj_personal` and the remaining defaults. Coordinator pins are unchanged. | all new unpinned threads | 7 days, same metrics |

**Keep rule** (lane B sets the thresholds; stage 1 does not start without them). Per treatment lineage, measured against its own baseline and against the control drift:
- P0/P1 review findings per deliverable do not rise;
- escaped defects (reopens, reverts, failed landings within 7 days) do not rise;
- rework turns per bead do not rise beyond the threshold;
- beads closed per hour do not fall beyond the threshold;
- weighted burn per closed bead falls.

**Regression →** Task 9 reverts that lineage. Other cohorts stay in their stage.

### Task 9: regression re-pin actor (Quilan implements; lane B supplies the verdict)

- Input: lane B's verdict JSON (`{cohort, change: "mk-42j9.25", verdict: regressed|holds|insufficient, metrics}`). The schema is agreed with lane B before stage 1.
- On `regressed`:
  - restore the lineage's dedicated bb project default from `project_profiles_prior` via Task 7;
  - write a Clavain policy-revert proposal (the lineage's `main-session` treatment entry) for the lane-A coordinator to land;
  - message the lineage's coordinator to resume its prior spawn model;
  - record a receipt.

  All of it is idempotent.
- It is tested on a synthetic regression (mk-42j9.33 acceptance).

## Rollback

- **Policy:** revert the Task 1 commit, or remove one profile, alias or treatment entry. The policy hash change shows in the receipts.
- **bb defaults:** `bb project defaults set` to the stage-entry snapshot. Before stage 1, snapshot all `project_execution_defaults` rows to `${XDG_STATE_HOME:-$HOME/.local/state}/clavain/project-defaults-snapshot-<date>.json`, recorded in `project_profiles_prior`.
- **Threads:** new threads follow the restored defaults at once. Existing unpinned treatment threads keep Sonnet by stickiness until they end; mk can pin any back with `bb thread update`. Pinned coordinators are never touched.
- **Quilan:** clear marking overrides with `coordinator enable` without `--model`. Carry-forward preserves the status quo and needs no rollback.

## Handoff to Phase 2

- **Decisions for mk:** D1–D4; the stage-1 cohort; authorizing Quilan as the automatic project-default writer; whether to pin the unpinned After Them, Autosigil and Cujgel coordinators (mk's pins, not this plan's).
- **Constraints:** Global Constraints.
- **Verification:** the acceptance criteria.
- **Escalation:**
  - If Task 7 is refused, bb defaults can only be set through UI creates and rollback of that half is manual. Escalate before stage 1.
  - If lane B has no thresholds, stage 1 does not start.
  - If `ic` rejects a scope with `:`, Task 1's test catches it and the scope becomes `project-<slug>`.
