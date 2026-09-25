# Research report: mk-42j9.7 host-neutral Jev decision layer — background material

Compiled 2026-09-25. Read-only research; no repo state changed. Clavain checkout used:
`/home/mk/projects/Clavain` (symlinked from `/home/mk/projects/Sylveste/os/Clavain`),
origin `git@github.com:mistakeknot/Clavain.git`, HEAD `573683a` at research time.
Note: per the user's zklw-canonical policy, zklw's local checkout may be ahead of this
GitHub-tracked one — UNVERIFIED whether zklw has newer commits than `573683a` for the
files cited below.

---

## 1. Plan doc: docs/plans/2026-09-23-clavain-subscription-efficiency.md

Path: `/home/mk/.bb-machines/autarch.getbb.app/plugins/environment-personal-workspace/host-data/workspaces/thr_5u5ct783ei/docs/plans/2026-09-23-clavain-subscription-efficiency.md`

### Overall structure

- Frontmatter: `artifact_type: plan`, `bead: none`, `stage: implementation-review-corrections`.
- Goal: reduce Opus 5.5 / GPT-6 Astra quota consumption 20-30% per accepted routine task on bb, "an experiment target, not a savings claim."
- Architecture stance: keep policy enforcement deterministic; reduce redundant instructions/cycles/context first; only later compare rules+registry search against an *optional* Jev selector that runs before frontier context assembly. Jev proposes bounded selections; explicit instructions, mandatory dependencies, and role eligibility stay separately enforced.
- Priority/dependency table, 10 work packages, ordered 1→6 sequential, then **7-9 form "a separate blocked integration branch"** (see blocker quote below), 10 applies after each independently verified improvement.
- "Must-haves" section: same acceptance criteria as baseline; count retries/fallback/compaction in usage; mandatory skills/review/approval boundaries survive optimization; every unique skill stays discoverable; record actual provider/model/effort/tier/account-window/config hashes — missing attribution stays unknown; a selector failure returns to the existing capable workflow and never silently omits required work; no savings claim from shorter prompts/API-price estimates/cache ratio alone.
- Tasks 1-6 (baseline/attribution, startup-contract dedup, skill-body cleanup, cycle elimination, effort/tier routing experiments, context lifecycle) are NOT Jev-related — general subscription-efficiency work with their own artifacts/tests.
- Handoff/open-gates section at the end records decisions, constraints, verification approach, escalation triggers, and current gate status (Intercore store initialized; governed Astra planning receipt 4 has unknown account attribution; independent Opus review completed via bb pool; review findings H1-H3/M1-M4 incorporated; "quota goal, live baseline, admission integration and rollout remain unproven").

### Task 7: Rules/search before model admission (source lines ~108-116)

**Source surfaces (proposed, not yet existing):** `scripts/skill-admission.py`, `config/skill-admission.yaml`, `scripts/tests/test_skill_admission.py` — "only if no existing component serves this role." Explicitly requires establishing "the owning bb/plugin/provider pre-request integration first; its exact source file remains a discovery prerequisite, not an invented API."

**Actions:** apply explicit requests and deterministic mandatory rules; retrieve candidates from a complete versioned registry; close mandatory dependency sets; enforce budgets only on optional content; unknown/ambiguous cases fall back to the current capable path; registry snapshots and selection results bind task-state/registry/policy hashes; re-evaluate after material scope change.

**Acceptance criteria (quoted):**
> "On held-out labeled tasks, required skills remain reachable and no mandatory dependencies are suppressed. Tests cover multiple relevant skills, explicit requests, unknown domains, missing catalog entries, changed policy, stale cache and selectors attempting forbidden omissions. Demonstrate that filtering occurs before the expensive request; a tool invoked after full catalog injection is not a call-avoidance success. Within a live conversation, account for already-loaded content."

**Exit decision (quoted):**
> "If bb/provider integration cannot safely reduce admission context, retain useful registry/search improvements and defer admission changes; do not claim a working pre-model gate. Rollback bypasses the selector and restores existing discovery."

### Task 8: Jev shadow evaluation (source lines ~118-126)

**Proposed artifacts:** `scripts/eval-skill-admission.py`, `scripts/tests/test_jev_admission.py`, `docs/research/subscription-efficiency/jev-shadow.md`; service integration stays behind the Task 7 admission interface.

**Actions:** start public/synthetic prompts only, separately authorize private material before sending anything to TypeSafe; check supported API/retention/service-access at implementation time; send bounded task state + retrieved metadata; evaluate workflow family, per-candidate relevance, and scope-change as separate bounded judgments; Jev must not author architecture, certify correctness, or grant authority.

**Compare:** rules/search alone vs. Jev on the same held-out inputs, "with labels fixed before seeing results." Measure missed required skills, abstention, fallback, latency, total resource use. Shadow decisions never control live behavior. Calibrate on one split, evaluate on another.

**Acceptance criteria (quoted):**
> "Jev adds a measurable improvement beyond rules/search within a predeclared quality floor. A small zero-error sample is not rare-case assurance. Failures, timeouts, low confidence and out-of-distribution tasks retain the existing route. If no incremental value appears, stop here; a Jev rollout is optional."

### Task 9: Conditional Jev pilot (source lines ~128-132)

**Actions:** enable only validated low-risk selection cases on an opt-in cohort; explicit requests/mandatory rules/role eligibility stay outside learned suppression; cache by bounded state+versions; bound retry attempts, fall back to existing workflow on failure; record decisions, chosen skills, omissions, fallback, and actual accepted-task outcomes.

**Acceptance criteria (quoted):**
> "Lower end-to-end resource use, including Jev calls and fallback/recovery, with no mandatory-policy omission. Quota claims require real attributed provider windows. Any mandatory omission immediately disables the pilot; independent review investigates before resumption. No global deployment follows solely from successful shadow labels."

### Task 10: Review and incremental rollout (source lines ~134-140)

Independent review of each shared policy/runtime change; land small verified units in canonical sources under repo instructions; narrow sync + fresh-host canaries; test Opus 5.5 and Astra separately; no sweeping installer/blanket disablement/unaudited config restore. CI: existing independent zklw automation; any workflow-class migration stays in its existing fleet task and needs the two-same-commit-fresh-guest-runs + canaries policy before trigger transfer. **This plan does not authorize source publication, releases, or deployment.**

**Acceptance (quoted):**
> "Publish a result table per intervention and provider: quality, attributed quota/task where known, requests, context, output/reasoning, retries, fallback and limitations. Retain only winners; unresolved measurements stay inconclusive. Preserve all failed-cohort evidence and package/configuration rollback references."

### The blocker assumed for Tasks 7-9 (quoted, from the priority table + narrative)

Priority table, row 7: *"Depends on: 2-4; verified host integration"*. Execution-order paragraph (quoted in full):

> "Packages 7-9 form a separate blocked integration branch: the installed public bb plugin API is synchronous, own-plugin only, and lacks documented task prompt input or general asynchronous cross-catalog admission. A verified source-owned bb/provider extension is a prerequisite. Never put network inference into that synchronous hook."

This blocker is corroborated in detail by two evidence files (see §1a below): `bb.agents.configure` runs synchronously at `thread.start`/`turn.submit`, sees no prompt text, can only select *that plugin's own* statically registered skills, and is capped at 4096 chars via `contributeInstructions`; the separate `message.dispatch` hook sees prompt text but can only `proceed`/`wait`/`reject` — it cannot rewrite input or return a skill set. No documented bb API today does prompt-dependent, pre-request, cross-catalog skill selection.

Note: mk's 2026-09-25 decision (recorded in bead mk-42j9, see §2) explicitly **generalizes this beyond bb** — "generalize via Clavain across hosts (Claude Code, Codex, Hermes, Kimi Code, Pi)" — so mk-42j9.7 is not scoped to the bb-only blocker the plan assumed; it is a host-neutral layer where the *host* prepares candidates and Clavain owns the decision/record logic, sidestepping the bb-specific `configure`-hook blocker for at least the Claude Code and Codex adapters.

### Files in `efficiency-evidence/` (118 entries; one line each, grouped)

Full directory: `/home/mk/.bb-machines/autarch.getbb.app/plugins/environment-personal-workspace/host-data/workspaces/thr_5u5ct783ei/docs/plans/efficiency-evidence/`

- `active-runtime-handles.json` — snapshot of active runtime handles at plan-authoring time.
- `baseline-landing.md`, `baseline-quality-brief.md`, `baseline-quality-review.{log,md,md.summary,md.verdict}`, `baseline-quality-review.md.provider-events.*.jsonl` — Task 1 baseline review pass + raw provider event transcript.
- `baseline-quality-routing-receipt.json` — `ic route dispatch` receipt for the baseline review (see §4 receipt schema).
- `baseline-recon.md` — reconnaissance notes for baseline task.
- `baseline-screen/` (dir) — baseline six-case feasibility screen artifacts.
- `baseline-spec-followup.md`, `baseline-spec-review.md` — spec review notes for baseline task.
- `baseline-task.json` — Task 1 task definition record.
- `bb-admission-owner.md` — bb source-ownership map for a future skill-admission feature (quoted in §4).
- `bb-drain-preparation.json`, `bb-update-backup-preflight.json`, `bb-update-progress.json` — bb pool/update operational state snapshots.
- `beads-efficiency-search.json`, `beads-startup-search.json`, `beads-subscription-search.json` — near-empty (3 bytes each) bead-search results, likely "no matches."
- `bootstrap-canaries/` (dir), `bootstrap-canary-status.json` — Task 2 canary run tracking.
- `bootstrap-consumer-inventory.json` — enumerated managed consumers of `config/host-adapters.json`.
- `bootstrap-correction-red-green.md`, `bootstrap-followup-brief.md`, `bootstrap-followup-review.{log,md,md.summary,md.verdict}`, `bootstrap-followup-review.md.provider-events.*.jsonl`, `bootstrap-followup-routing-receipt.json`, `bootstrap-followup-state.json` — Task 2 follow-up review round.
- `bootstrap-proposal.md` — Task 2 startup-contract shortening proposal.
- `bootstrap-quality-brief.md`, `bootstrap-quality-review.{log,md,md.summary,md.verdict}`, `bootstrap-quality-review.md.provider-events.*.jsonl`, `bootstrap-quality-routing-receipt.json`, `bootstrap-review-state.json` — Task 2 quality-review round (this is the receipt read in full in §4).
- `bootstrap-rollout-order.md`, `bootstrap-task.json` — Task 2 rollout sequencing / task definition.
- `ci-migration-task.json` — CI migration task reference (mk-ag2s scope, not duplicated here).
- `clavain-ci-status.json`, `interstat-ci-status.json` — `zklw-ci status` snapshots for Clavain / Interstat repos.
- `coordinator-context-observation.json` — coordinator context-floor observation.
- `credential-artifact-scan.json`, `credential-remediation-status.json`, `credential-snapshot-redaction.json` — credential-scan/redaction evidence.
- `cycle-reduction-proposal.md` — Task 4 proposal.
- `decision.json` — decision-context JSON with `reasons`/`rationale`/`investigation_active` (quoted in full in §4).
- `dispatch-failure.md` — a recorded dispatch failure.
- `effort-context-experiment-prerequisites.md` — Task 5/6 prerequisites.
- `epic.json` — epic-level task record (mk-42j9).
- `execution-authorization.json` — mk's execution authorization record.
- `fable-quota-receipt.json` — Fable quota-fallback usage receipt.
- `frontier-plan-attempt2.{log,md,md.provider-events.*.jsonl,md.summary,md.verdict,md.verdict.pre-error}`, `frontier-plan-attempt3.{log,md,md.provider-events.*.jsonl,md.summary,md.verdict}`, `frontier-plan.md.provider-events.*.jsonl`, `frontier-plan-routing-receipt.json` — multiple frontier-planning attempts (2 failed/retried) plus routing receipt.
- `graceful-recovery-design.md` — design note for the sibling graceful-process-recovery plan.
- `independent-plan-review.{log,md,md.summary,md.verdict,md.verdict.pre-error}`, `independent-plan-review.md.provider-events.*.jsonl`, `independent-plan-review-opus.{log,md,md.summary,md.verdict,md.verdict.pre-error}`, `independent-plan-review-opus.md.provider-events.*.jsonl`, `independent-plan-review-opus-pooled.{log,md,md.summary,md.verdict}`, `independent-plan-review-opus-pooled.md.provider-events.*.jsonl`, `independent-plan-review-opus-pooled-receipt.json` — three independent-review attempts, the last (pooled Opus) succeeding.
- `jev-service-prerequisites.md` — TypeSafe/Jev API/data-terms reconnaissance (quoted extensively in §4).
- `measurement-protocol.json` — Task 1 measurement protocol definition.
- `native-skill-audit.{json,log}` — native skill catalog audit (79 skills, 79 unique names, 20,104 metadata chars, no loader errors).
- `opus-review-route.json` — routing decision for an Opus review pass.
- `planning-brief.md`, `planning-route.json` — initial planning brief and its routing decision.
- `plan-review-brief.md` — plan-review task brief.
- `pool-rollout-prerequisites.md`, `pool-routing-thread-brief.md`, `pool-routing-thread.json`, `pool-thread-snapshot-redaction.json` — bb account-pool rollout evidence.
- `quota-routing.yaml` — quota-aware routing config snapshot (600 mode, likely contains sensitive routing detail).
- `recovery-continuation-status.json`, `recovery-design-decision.json`, `recovery-owner-map.md`, `recovery-plan-decision.json`, `recovery-planning-route.json`, `recovery-review-route.json` — graceful-recovery sibling-plan evidence.
- `resume-checklist.md` — session-resume checklist.
- `review-call-baseline.json` — baseline review-call metrics.
- `skill-admission-recon.md` — pre-model surface reconnaissance for skill admission (quoted extensively in §4).
- `skill-body-path-costs.json`, `skill-body-priority.md` — Task 3 skill-body cost/priority ranking.

---

## 2. Bead family mk-42j9 (`cd /home/mk/hub && command bd show ...`)

**mk-42j9 [EPIC]** — "Improve Clavain and bb subscription efficiency with preserved acceptance." P1, IN_PROGRESS, owner `bb-thr_5u5ct783ei-efficiency`. 1/11 children complete (9%).
- Description: execute the 2026-09-23 plan via GPT-6 Sol subagents; scope covers baseline, lean-startup verification, skill cleanup, deterministic cycles, effort/context experiments, rules/search admission, conditional Jev shadow/pilot, reviewed rollout. Target 20-30% less quota per accepted routine task, "not a promised saving." Canonical plan stays in the thread workspace doc read in §1. CI migration mk-ag2s.25 stays independently owned — not duplicated.
- **Acceptance:** "All ten plan packages implemented and empirically accepted or explicitly retained with concrete unmet prerequisites; no claimed quota saving without account-window attribution; no mandatory skill or policy loss."
- 2026-09-25 note (mk's ruling that spawned .7-.11): "(1) generalize via Clavain across hosts (Claude Code, Codex, Hermes, Kimi Code, Pi) -> mk-42j9.7; (2) mk AUTHORIZED sending real work to TypeSafe/Jev for all of mk's projects (lifts the plan's public/synthetic-only restriction; still excludes credentials and unrelated private material); (3) rules/search arm required; (4) burn-weighted, cache-aware measurement; (5) one bead per candidate. Filed .7 layer, .8 launch profiles, .9 security triage shadow, .10 tool-output reduction, .11 prepared workflows. Deferred with rationale: failure-recovery selection (low volume, rules cover it) and compaction retention (host-owned; handoff at 80-100k covers most)."
  - This note is important: it **supersedes** the plan doc's Task 8 "public/synthetic prompts only" restriction — mk has now authorized real task material to TypeSafe/Jev project-wide (matching the AGENTS.md standing-authorization block), and it fixes eval design points 3-5 (rules/search arm required, burn-weighted+cache-aware measurement, one bead per candidate — matching this task's eval-harness spec).

**mk-42j9.1** — "Establish subscription task baseline and governed planning prerequisites." P1, IN_PROGRESS. Plan Task 1. Acceptance: "Focused accounting regressions pass; actual host fields and limitations recorded; correct account-window attribution or unknown verdict; governed plan receipt and independent review before shared policy changes; source ownership and CI dispositions recorded." Notes: bounded exporter landed in Interstat local main (not pushed); empirical quota baseline/account isolation "still unverified, tracker remains open." Blocks mk-42j9.2.

**mk-42j9.8** — "Jev candidate: launch-time plugin/skill/role profile selection per host." P1, OPEN, owner `bb-thr_7riapjmbnj-efficiency` (a different thread from the parent epic — i.e. a separate execution thread was spawned for .8-.11). Opportunities 4+7: select a lean plugin/skill/role profile at worker launch (bb spawn + host equivalents). "Rules first, then Jev shadow over thread briefs, then pilot only if it beats rules." Verified 2026-09-25: Claude Code 2.1.282 honors `--scope local/project enabledPlugins`. Relates to mk-42j9.4 (Aleph role profiles). Metric: fresh-session floor (~30.1k Sonnet now) and missed-required-skill rate. **Depends on mk-42j9.7.**

**mk-42j9.9** — "Jev candidate: security-review triage in shadow (security-guidance hook)." P2, OPEN, same owner thread. Opportunity 5: security-guidance ran ~102 full reviewer sessions (~32k floor each) in 8h. Jev scores proposed edits in shadow; measures how many full reviews could route to a lighter check without missed findings. "Jev may never cancel a review on its own; escalation-only until evidence and independent review approve otherwise." **Depends on mk-42j9.7.**

**mk-42j9.10** — "Jev candidate: large tool-output reduction with retrievable originals." P2, OPEN, same owner thread. Opportunity 1: deterministic truncation + retrieval reference first; Jev chunk-ranking only for very large outputs, in shadow. "Verify per host whether hooks can replace output (Claude Code may allow it only for MCP tools)." Measures missed evidence, extra retrieval, downstream mistakes, cache-prefix effects. **Depends on mk-42j9.7.**

**mk-42j9.11** — "Prepared workflows: script repeated multi-turn sequences (no Jev)." P2, OPEN, same owner thread. Opportunity 3: mine tool-time/transcripts for the most repeated multi-step sequences (release chains, zklw-ci checks, bb coordination) and replace with scripts/bb workflows so no model turn is needed per step. "Deterministic code; Jev only for a genuine branch choice, if any." No dependency on .7 listed (this is explicitly "no Jev").

All five children mk-42j9.{7,8,9,10,11} form the Jev-candidate cluster; .7 is the shared decision-layer prerequisite for .8/.9/.10, while .11 is explicitly Jev-free. (mk-42j9.7 itself was not directly `bd show`n in this pass — only its children/siblings; its own description string appears verbatim in the epic's CHILDREN listing: "Clavain host-neutral Jev decision layer (selector contract, decision records, eval harness, host adapters)".)

---

## 3. burn-report.py — weighted-token accounting

File: `/home/mk/projects/Clavain/scripts/burn-report.py` (190 lines). Last commit touching it: `deecaf09fcfe56fa74453e4f7a70ffeee1484e76`, 2026-09-24T20:57:27-06:00.

### Weight table (file:line `scripts/burn-report.py:26-31`)

```python
WEIGHTS = {
    "input_tokens": 1.0,
    "cache_creation_input_tokens": 1.25,
    "cache_read_input_tokens": 0.1,
    "output_tokens": 5.0,
}
```
Docstring (`scripts/burn-report.py:7-9`): "Weights approximate relative cost: cache write 1.25, cache read 0.1, input 1, output 5. This is an estimate of burn, not the provider's quota accounting."

### Transcript sources read

- Only Claude Code transcripts. Default `--root` is `~/.claude/projects` (`scripts/burn-report.py:170`, `os.path.expanduser("~/.claude/projects")`).
- `responses()` (`scripts/burn-report.py:60-91`) walks every `*.jsonl` under root recursively (`root.rglob("*.jsonl")`, includes subagent transcripts per the module docstring), skipping files whose mtime predates `since` as a cheap prefilter, then line-by-line JSON-parses any line containing `"usage"`.
- Excludes `model == "<synthetic>"` entries (`scripts/burn-report.py:83`) — these are Claude Code's own synthetic/system messages, not real API calls.
- **No Codex, Hermes, Kimi, or other-provider transcript support.** The module docstring says "Weighted Claude burn from local transcripts" and the code only understands the Claude Code JSONL transcript schema (`message.usage`, `message.model`, `message.id`, `event.requestId`, `event.timestamp`). There is no provider-agnostic abstraction. For a host-neutral eval harness comparing arms across hosts (Claude Code, Codex, etc. per mk's 2026-09-25 ruling), burn-report.py as-is only covers the Claude Code arm; Codex/other-host burn would need either a parallel script or an extension. This gap is directly relevant to mk-42j9.7's "cache-aware, burn-weighted, host-neutral" measurement requirement.

### Dedup logic (cache/streaming-aware)

`scripts/burn-report.py:85-90`: dedup key is `(message.get("id"), event.get("requestId"))`. Streaming writes the same response across multiple JSONL lines with increasing usage counts (later lines can carry a larger output count than earlier ones), so for each field the merge takes `max(existing, new)` rather than summing — this is what prevents double-counting a single API response and also prevents undercounting a response whose final usage line hasn't yet been observed when an earlier line first creates the dedup entry.

### Cache-creation vs cache-read treatment

Both are tracked as **separate weighted fields**, not merged: `cache_creation_input_tokens` (weight 1.25, i.e. writing to cache costs *more* than a plain input token) vs `cache_read_input_tokens` (weight 0.1, i.e. reading from cache costs a tenth of a plain input token). This directly operationalizes cache-awareness: a call that reuses a long cached prefix scores far lower than one that re-establishes it. `context_bucket()` (`scripts/burn-report.py:52-57`) buckets total non-output usage (`input + cache_creation + cache_read`, i.e. excludes `output_tokens`) into `<50k` / `50-100k` / `100-150k` / `>150k` — this bucketing is agnostic to whether those input tokens were fresh or cached (it sums all three), so it's a raw context-size metric, separate from the cost-weighting.

### CLI flags (`main()`, `scripts/burn-report.py:166-186`)

- `--since` ISO 8601 (default: `--until` minus 5h)
- `--until` ISO 8601 (default: now)
- `--root` path (default `~/.claude/projects`)
- `--top N` (default 10; number of lineages listed in text output)
- `--json` (emit JSON instead of the rendered text report)

### Session/time-window/bead scoping

- **Time window:** yes, via `--since`/`--until` (half-open `[since, until)`, confirmed by the structural test `tests/structural/test_burn_report.py:38-44`, which explicitly checks "window end exclusive").
- **Session scoping:** not directly by session id. Grouping is by **lineage**, not session: `lineage()` (`scripts/burn-report.py:44-49`) takes the top-level directory name under `--root` and extracts a `thr_<10-char-id>` slug via regex `THREAD_SLUG = re.compile(r"-thr-([a-z0-9]{10})(?=-|$)")` (`scripts/burn-report.py:33`) — "A bb thread's workspace directory survives handoffs, so the transcript directory names the lineage root … and its successors share one group. Transcripts outside a bb workspace group by their project directory" (module docstring, `scripts/burn-report.py:11-13`). So it *can* scope to a bb-thread lineage (by filtering `by_lineage` output or pointing `--root` at a single thread's transcript dir) but has no native `--session` or `--bead` flag.
- **Bead scoping:** no native support at all. There is no bead-id field read anywhere in the script. To scope burn to a specific bead/task, a caller would need to (a) know which thread lineage(s) worked that bead and filter `by_lineage` post-hoc, or (b) point `--root` at a narrower transcript directory. This is a gap relative to mk-42j9.7's eval-harness requirement to measure burn per task/arm — the harness will likely need a wrapper that maps bead/arm to a `--root`/lineage filter, or an extension to burn-report.py itself.

### Output shape

`report()` (`scripts/burn-report.py:94-135`) returns `since`, `until`, `weights`, `calls`, `weighted_total`, `by_token_type`, `by_lineage` (list of `{lineage, weighted, calls}` sorted by weighted desc), `by_model`, `by_hour`, `by_context` (bucketed), and `pace` (last-5h weighted total + per-hour rate). `render()` (`scripts/burn-report.py:146-163`) formats this as human-readable text; `--json` prints the dict directly.

### Test coverage

`tests/structural/test_burn_report.py` (pytest, part of Tier 1 structural suite — see §5) builds synthetic Claude-Code-shaped JSONL fixtures and asserts on dedup, windowing, and the weighted-total arithmetic (e.g. `10 + 100*1.25 + 1000*0.1 + 2*5 == 245`, confirmed at `tests/structural/test_burn_report.py:38-44`).

---

## 4. Existing Clavain infrastructure a decision layer would reuse

### 4a. Decision-record / receipt writers

**`config/host-adapters.json`** (`/home/mk/projects/Clavain/config/host-adapters.json`, full file read) — the existing host-neutral adapter registry: one JSON object keyed by host (`codex`, `claude`, `hermes`, `gemini`, `kimi`, `opencode`, `cursor`, `vscode`), each entry giving `surface` (which file/mechanism carries instructions into that host), `adapter`/`instruction` (the actual text or its source file), and `dispatch` (which script executes governed work for that host — `scripts/dispatch.sh` for six of the eight, `adapters/hermes` for Hermes). **This is the direct precedent for mk-42j9.7's "host adapters" requirement** — a new Jev decision layer would plausibly add a `jev` or `decision-layer` key per host here, or a parallel file, describing how each host supplies candidate IDs and receives the decision.

**`scripts/context-gateway.py`** (610 lines) + **`hooks/context-gateway.sh`** (39 lines) — this is explicitly named in `efficiency-evidence/skill-admission-recon.md` (§1 listing) as "a better comparator for rules/search than inventing another router," and it is the closest existing analogue to a "host prepares candidates, a selector decides, host revalidates, fallback" pipeline:
  - `SCHEMA_VERSION = 1`, `MARKER = "clavain-context-gateway:v1"` (`scripts/context-gateway.py:21-22`) — versioned decision-record convention to imitate.
  - `assess_eligibility(prompt, project, mode) -> Decision | None` (`scripts/context-gateway.py:156`) — deterministic pre-check before the expensive path runs (analogous to "rules first" gating before Jev).
  - `_parse_tldrs_result()` (`scripts/context-gateway.py:206-260`) validates a `receipt` dict with `schema_version`, a `packet_sha256` digest check, and a `packet_chars` length check (`scripts/context-gateway.py:221-240`) — i.e. the tool output is bound to a hash-verified receipt, exactly the "versioned decision records" pattern mk-42j9.7 needs.
  - `persist_receipt()` (`scripts/context-gateway.py:357-398`) writes to `_writable_receipt_dir()` with a `_fallback_receipt_dir()` if the primary is unwritable (`scripts/context-gateway.py:311-398`), and `_write_receipt()` uses `tempfile.mkstemp` + atomic write (`scripts/context-gateway.py:338-355`).
  - `decide()` (`scripts/context-gateway.py:401`) is the top-level entry that ties eligibility assessment, invocation, and receipt persistence together.
  - The hook wrapper `hooks/context-gateway.sh` is a `UserPromptSubmit` hook that "fails open" per the recon note — i.e. selector failure falls back to normal behavior, matching the plan's must-have "a selector failure returns to the existing capable workflow."

**Routing receipts via `ic route dispatch`** — `scripts/dispatch.sh:527` builds `route_cmd=(ic --json route dispatch --role="$role" --policy="$policy_source")`, and `--context-file` is wired from `CLAVAIN_DECISION_CONTEXT` (`scripts/dispatch.sh:529,548`). I read a live example receipt in full: `efficiency-evidence/bootstrap-quality-routing-receipt.json`. Its schema (paraphrased, real field names): `id`, `dispatch_id`, `run_id`, `session_id`, `bead_id`, `project_dir`, `phase`, `agent`, `category`, `selected_model`, `rule_matched`, `floor_applied`/`floor_from`/`floor_to`, `candidates`, `excluded` (JSON-encoded array string), `policy_hash`, `override_id`, `complexity`, `context_json` (a JSON-encoded string embedding the full decision context: `attempt_id`, `bead_id`, `checkout.{before,after}` git SHAs, `execution.{account,backend,model,reasoning_effort,sandbox,service_tier,session_id,transport}`, `resolved_route.{classification_reasons, decision_context.{reasons,rationale,investigation_active}, fallback_chain[...], frontier_required, policy_hash, policy_profile, policy_source, producer_identity, profile, review_requirement, validator_relationship}`, `result.{exit_code,failure_class,output_path,verdict}`), and `decided_at` (unix timestamp). **This `ic route dispatch` receipt schema — with its policy hash, fallback chain, classification reasons, and result verdict — is the closest existing "versioned decision record" format in the codebase and is a strong template for a Jev decision record** (candidate id chosen, confidence/reasons, fallback chain, policy hash, outcome).

**`decision.json`** in efficiency-evidence (read in full): `{"reasons": [...], "rationale": "...", "investigation_active": true}` — this is the `CLAVAIN_DECISION_CONTEXT` JSON shape referenced by the CLAUDE.md/AGENTS.md Sylveste contract text ("Record an accountable JSON decision context with `reasons` and nonempty `rationale`"). The five allowed `reasons` values per the contract: `unresolved-success-criteria`, `foundational-invariants`, `broad-consequences`, `difficult-verification`, `capability-failure`.

### 4b. Feature-flag conventions

No generic "feature flag" file/registry exists; Clavain's convention is **environment variables read at point of use, defaulting to off/existing-behavior**, e.g. (all found via grep across `scripts/`, `hooks/`, `config/`):
- `CLAVAIN_ALLOW_UNSAFE=1` (`scripts/dispatch.sh:980`) — override a safety-blocked command.
- `CLAVAIN_STRICT_PREFLIGHT=1` (`scripts/dispatch.sh:1292-1358`) — fail-fast vs. warn-and-continue default.
- `CLAVAIN_PREFLIGHT_INJECT_PATH=1` (`scripts/dispatch.sh:1293,1362`) — opt-in PATH injection.
- `CLAVAIN_REQUIRE_USAGE=1` combined with `DISPATCH_TRANSPORT=direct-pooled` (`scripts/dispatch.sh:2444-2449`) — makes a pooled dispatch fail (`terminal_accounting`) rather than accept unattributed usage; direct precedent for mk-42j9's "no claimed quota saving without account-window attribution" must-have.
- `CLAVAIN_ROUTING_POLICY`, `CLAVAIN_DECISION_CONTEXT` (`scripts/dispatch.sh:852-859`, `docs/canon/reasoning-routing.md:19,28-30`) — override policy source / pass decision context; settable via `--policy`/`--context-file` flags or env.
- `MYCROFT_OVERRIDE=true` (`scripts/dispatch.sh:1461`) — explicit opt-in bypass, requires "explicit user opt-in" per the error message.
- `SHADOW_SCAN_DEADLINE` (`hooks/lib-shadow-tracker.sh`, see §4d) — tunable deadline, `0` disables.
- Config-file-level "opt-in" gate: `config/default-policy.yaml:54` — `blocked: 9  # score 7+: blocked, require explicit user opt-in via policy override`.
- `scripts/dispatch.sh:1041` comment: "Detect whether Clavain-specific tier remapping should be used. This is opt-in via: [env var]."

**Pattern to follow for mk-42j9.7's "feature flag per integration":** a `CLAVAIN_JEV_<INTEGRATION>=1`-style env var per consuming integration (e.g. `CLAVAIN_JEV_LAUNCH_PROFILE`, `CLAVAIN_JEV_SECURITY_TRIAGE`, `CLAVAIN_JEV_TOOL_OUTPUT`), defaulting unset/off, checked at the point each integration (.8/.9/.10) would call the shared decision layer — consistent with how `CLAVAIN_STRICT_PREFLIGHT`/`CLAVAIN_REQUIRE_USAGE` gate optional stricter behavior today.

### 4c. Intercore `ic` events for recording outcomes

`ic --help` output (`/home/mk/projects/Clavain`, live binary) lists, among much else:
```
events tail <run_id|--all> [--follow] [--consumer=<name>]
events tail ... [--since-phase=N] [--since-dispatch=N] [--limit=N]
events record --source=<s> --type=<t> --payload=<json> [opts]  Record event
events list-agency [--agency=<name>] [--run=<id>] [--since=N]  Query agency lifecycle events
events cursor list             List named cursors
events cursor reset <name>     Reset a named cursor
```
`ic events record --help` (invoked without a real payload) errored with: `"events record: --source is required (agency, interspect, review, coordination, intent)"` — i.e. `--source` is a closed enum of five values; none of them is obviously "jev-decision" or "selector," so **recording Jev decision outcomes through `ic events record` would need to pick one of these five existing sources (most plausibly `agency` or `coordination`) or get a new source value added to that enum** — UNVERIFIED whether the enum is extensible without an `ic` binary change (the CLI is a compiled Go binary per the ERROR JSON log style; its source wasn't located in this pass — UNVERIFIED whether `ic`'s own source is in this Clavain checkout or a separate Intercore repo).

The `ic route dispatch` mechanism (§4a) already double-duties as a decision + outcome recorder (its receipt embeds both the routing decision and, once the dispatch completes, `result.{exit_code,failure_class,verdict}`) — this may be a more direct fit for Jev decision records than raw `ic events record`, since it already has policy-hash/fallback-chain/reasons fields matching the layer's requirements.

### 4d. Existing eval harnesses

**`scripts/executor-parity-eval.py`** (`/home/mk/projects/Clavain/scripts/executor-parity-eval.py`) — "Compare two dispatch executors without leaking source identity to judges." Module docstring describes exactly a 3-stage blind eval:
1. Run the same JSONL prompts through cheap and stronger backends.
2. Compute mechanical yield/coverage/agreement metrics, write a blind interleaved judge queue (opaque ids only).
3. After human/external judge fills defensibility scores, apply explicit `PARITY`/`PIN_STRONGER` threshold.
Key functions (file:line): `compute_metrics()` (`:109`), `_jaccard()` (`:134`), `agreement_tier()` (`:139`), `tiered_agreement()` (`:156`), `_opaque_id()` (`:181`, blinding), `build_blind_judge_queue()` (`:189`), `write_judge_queue()`/`load_judge_scores()` (`:216`,`:225`), `aggregate_defensibility()` (`:252`), `explicit_verdict()` (`:270`), `run_prompt()` (`:315`, docstring: "callers opt into this real-run path" — i.e. real-run is itself opt-in, self-test is the default), `run_self_test()` (`:380`, "backend-free check of the metric and blinding paths"), `build_parser()`/`run_evaluation()`/`main()`. **This is the strongest existing precedent for a 3-arm eval harness with fixed labels and blinding** — its blind-judge-queue + opaque-id + fixed-threshold-verdict pattern maps closely onto mk-42j9.7's "3 arms ... labels fixed beforehand" requirement. It has a companion `scripts/executor-parity-eval.sh` wrapper and a `--self-test` mode for backend-free CI.

**`interlab*` family** (`/home/mk/projects/Clavain/interlab.sh`, `interlab.md`, `interlab-sprint-scan.sh`, `interlab-satisfaction.sh`, `interlab-go-bench.sh`, `interlab-route-prompt.sh`, `interlab-sprint-go.sh`, `interlab-multi.md`, `interlab-sprint-state.sh`) — a separate, apparently sprint/satisfaction-benchmarking harness family (route-prompt, go-bench, sprint-scan/state/go). Not read in depth in this pass; flagged as a second existing eval-adjacent surface worth checking before building new harness scaffolding — UNVERIFIED how much overlaps with what mk-42j9.7 needs versus executor-parity-eval.py.

### 4e. `scripts/lib-*.sh`

Full list in `scripts/`: `lib-bb.sh`, `lib-compose.sh`, `lib-dispatch-audit.sh`, `lib-fleet.sh`, `lib-routing.sh`, `lib-ship-class.sh`. (Separately, `hooks/` has its own `lib-*.sh` set: `lib-discovery.sh`, `lib-dispatch.sh`, `lib-gates.sh`, `lib-goal-audit.sh`, `lib-headless.sh`, `lib-intercore.sh`, `lib-log.sh`, `lib-loop-breaker.sh`, `lib-next-goal-provenance.sh`, `lib-recovery.sh`, `lib-session-project.sh`, `lib.sh`, `lib-shadow-tracker.sh`, `lib-signals.sh` — two parallel `lib-` namespaces, one per directory, not one shared library dir.) `scripts/lib-routing.sh` contains the `ic route dispatch --tier=` fallback call at `scripts/lib-routing.sh:1453` (`_ic_result=$(ic route dispatch --tier="$1" 2>/dev/null)`). `scripts/tier-fallback-chain.py` is the tier-side fallback-chain resolver (full docstring read): resolves a `dispatch.tiers.<name>` entry plus its deduped `fallbacks:` chain directly from `routing.yaml`, because `ic route dispatch --tier=` (unlike `--role=`) doesn't walk fallback chains itself. Exit codes: 0 success, 1 unknown/malformed tier or fallback (fails loudly, not silently — "a typo'd fallback should never look like 'no fallback was configured'"), 3 missing pyyaml (distinct code so caller can degrade). **This fallback-chain pattern (declared chain, deduped, loud-fail on typo, distinct exit code for "dependency missing so degrade gracefully") is a direct template for mk-42j9.7's "host revalidates, fallback" requirement.**

### 4f. Hooks dir layout

`/home/mk/projects/Clavain/hooks/` (30 entries total; representative subset): `hooks.json` (4384 bytes — the hook-registration manifest), plus per-hook scripts: `agents-md-refresh.sh`, `auto-publish.sh`, `auto-push.sh`, `auto-stop-actions.sh` (16553 bytes — the Stop-hook referenced in the user's CLAUDE.md "Goal Cadence" rule), `bead-agent-bind.sh`, `catalog-reminder.sh`, `context-gateway.sh` (the `UserPromptSubmit` hook, §4a), `dotfiles-sync.sh`, `gate-calibration-session-end.sh`, `gauge-gate-executor-spawn.sh`, `guard-plugin-cache.sh`, `interserve-audit.sh`, plus the `lib-*.sh` set (§4e). Pattern: one script per hook event/concern, registered centrally in `hooks.json`, thin shell wrapper calling into a Python/shell library, fail-open where the hook is advisory (per the `lib-shadow-tracker.sh` docstring: "A category that times out contributes no matches — silently, by design: this is a nudge, not a gate.").

`hooks/lib-shadow-tracker.sh` (full header read) is a good example of hook engineering discipline worth imitating for a decision-layer hook: documents a specific performance incident (62% of Stop-hook time, some runs exceeding the 120s cap entirely), root-causes it precisely (`-not -path` filters but still descends; only `-prune` skips the subtree), fixes it, and exposes a `SHADOW_SCAN_DEADLINE` env var with `0` to disable, defaulting to a value chosen to stay under the hook's hard cap with margin.

### 4g. Existing "rules/search admission" or skill-admission code

**None exists yet in the repo as running code.** Confirmed by `find . -iname "*skill-admission*" -o -iname "*skill_admission*"` returning nothing, and by `grep -rli jev` (excluding efficiency-evidence) returning nothing — i.e. no `scripts/skill-admission.py`, `config/skill-admission.yaml`, or any Jev-named source file exists in Clavain today. What exists is the *plan* for it (Task 7, §1) plus two research memos in efficiency-evidence:

- **`efficiency-evidence/bb-admission-owner.md`** (read in full) — maps bb's actual source ownership for a hypothetical admission feature: `bb.agents.configure` (thread.start/turn.submit, own-plugin-only, no prompt text, 4096-char cap via `contributeInstructions`) vs. the separate `message.dispatch` hook (`apps/server/src/services/threads/dispatch-hooks.ts`, sees combined input text pre-scheduling, but can only `proceed`/`wait`/`reject`, cannot rewrite input or return a skill set). Names the specific bb source files that would need to change for a real cross-catalog pre-request admission feature: `apps/server/src/services/plugins/plugin-agent-contributions.ts`, `apps/server/src/services/threads/{dispatch-hooks.ts,thread-turn-dispatch.ts}`, `apps/server/src/services/skills/{skill-catalog.ts,injected-skills.ts}`, provider bridges `plugins/provider-codex/src/bridge/bridge.ts` and `plugins/provider-claude-code/src/bridge/{bridge.ts,sdk-session.ts,skill-plugins.ts}`, public contracts under `packages/plugin-sdk/src` (new public members need an `experimental_` prefix + API audit). Decision: "retain Task 7's host integration gate and do not count plugin configuration or a dispatch wait as a working pre-request admission gate" — i.e. as of 2026-09-23, bb itself cannot do prompt-dependent pre-request admission; **this is precisely the gap mk's "host prepares candidate IDs" design in mk-42j9.7 works around**, since it puts candidate preparation in the host adapter (deterministic, pre-existing per-host capability) rather than requiring a new bb server-side interception API.
- **`efficiency-evidence/skill-admission-recon.md`** (read in full) — corroborates the same finding independently, and additionally flags `hooks/context-gateway.sh` + `scripts/context-gateway.py` as "a better comparator for rules/search than inventing another router" (already covered in §4a), notes the native skill catalog is already lazy-loaded (79 skills, no dup names, no removal needed), and gives reproduction commands for re-verifying source/cache drift.
- **`efficiency-evidence/jev-service-prerequisites.md`** (read in full) — the actual TypeSafe/Jev API shape, checked against public docs 2026-09-23 (UNVERIFIED beyond documentation — "This is a documentation check, not service access... No account was created or key read"):
  - Endpoint: `POST https://api.typesafe.ai/v1/systemone`, bearer auth via API key from dashboard; `GET /v1/models` lists available model names/aliases.
  - Python SDK (`typesafe-sdk`, Python ≥3.10): `TypeSafeClient.system_one(state=..., questions=...)`; JS/TS SDK also documented; default retries are automatic per the SDK docs.
  - Question types: **Choice**, **Score**, **Noul** — Choice/Score return probabilities plus a derived confidence; Noul returns a yes-probability with no separate confidence.
  - **No documented native abstain status** — TypeSafe recommends coding an explicit `other`/`none of the above` Choice option and a fallback for low confidence; "Typed output cannot certify correct skill selection or mandatory dependency closure." This directly shapes mk-42j9.7's "selector picks one or abstains" — abstention must be modeled as an explicit `none` choice, not a native API feature.
  - Model identity: response `model` field may differ from the requested alias (e.g. request `jev-latest`, response `jev-1.13.0` in the docs' own example) — the recon memo recommends recording both requested and returned model names, since "an alias alone is insufficient immutable version evidence."
  - Data terms: TypeSafe's privacy policy says it does not train/fine-tune on Input; its customer agreement permits processing for service/fees/telemetry with no fixed deletion interval, deletable "at TypeSafe's discretion" — "No zero-retention or private-repository transport guarantee was found." (This predates mk's 2026-09-25 authorization to send real task material — see bead notes in §2 and the standing-authorization AGENTS.md block — so the memo's caution about needing separate destination authorization is now superseded for mk's own projects, per the epic note.)
  - Recommended smallest shadow screen: 20-30 fixed task descriptions (explicit requests, no-fit tasks, changed scope, mandatory-dependency cases), labels frozen before any Jev result, synthetic-only state sent, one bounded Choice question (candidate-or-`none`) plus optional Noul applicability questions, fixture JSON for request/expected-response, metrics: missed-required-skill / wrong-load / needless-load / abstention-fallback / latency / retries / full call cost.

---

## 5. Repo test conventions

`tests/run-tests.sh` defines three tiers (full header read):
- **Tier 1 — Structural (pytest):** `cd tests && uv run pytest structural/ -v --tb=short`. Directory `tests/structural/` (partial listing, ~30+ files): `conftest.py`, `helpers.py`, `__init__.py`, and one `test_*.py` per concern, e.g. `test_agents.py`, `test_auto_publish_loud_failure.py`, `test_bb_host.py`, `test_bb_seat.py`, `test_bb_startup.py`, `test_burn_report.py` (the burn-report tests, §3), `test_calibration_close_gate.py`, `test_calibration_sessionend_ownership.py`, `test_catalog_freshness.py`, `test_claude_usage.py`, `test_clavain_sync` (dir), `test_codex_installers.py`, `test_codex_mcp_config.py`, `test_commands.py`, `test_context_gateway_installers.py`, `test_context_gateway.py`, `test_cross_references.py`, `test_discovery.py`, `test_dispatch_bb.py`, `test_headroom_dispatch.py`, `test_hooks_json.py`, `test_ic_selection.py`, `test_native_readiness.py`, `test_native_skill_selection.py`, `test_orchestrate_fresh_output.py`, `test_orchestrate_observability.py`, and more not listed (dir was truncated at ~30 entries by the read limit).
- **Tier 2 — Shell (bats):** `bats "$PROJECT_ROOT/tests/shell/" --recursive` (parallelized with `--jobs 4` if GNU `parallel` is available). Directory `tests/shell/` (partial listing): `auto_push.bats`, `context_gateway_hook.bats`, `dispatch_claude_seat.bats`, `dispatch_claude_settings.bats`, `dispatch_codex_uv_no_sync.bats`, `dispatch_codex_writable_roots.bats`, `dispatch_context_gateway.bats`, `dispatch_error_surfacing.bats`, `dispatch_flere.bats`, `dispatch_kimi.bats`, `dispatch_parser.bats`, `dispatch_preflight.bats`, `dispatch_zaka.bats`, `dotfiles_sync.bats`, `gate_record_vetted_sha.bats`, `gauge_gate_executor_spawn.bats`, `goal_audit.bats`, `goal_shape_guide.bats`, `hooks_json.bats`, `inflight_agents.bats`, `lib.bats`, `lib_signals.bats`, `loop_breaker.bats`, `next_goal_candidates.bats`, `next_goal_provenance.bats`, `next_goal_verify.bats`, `pattern_f_verdict.bats`, `pattern_f_verdict_unrun.bats`, `quality_gates_grounding.bats`, `remontoire_attention.bats`, and more.
- **Tier 3 — Smoke (`claude` subagents):** `tests/smoke/run-smoke-tests.sh`, requires a live `claude` CLI ("Run from within a Claude Code session").
- Invocation: `./tests/run-tests.sh` (Tiers 1+2 default), `--structural`, `--shell`, `--smoke`, `--all`.
- Other top-level `tests/` entries: `authz-e2e_test.sh`, `authz-v15-e2e_test.sh`, `authz-v2-e2e_test.sh` (standalone auth e2e scripts, not under structural/shell/smoke), `fixtures/`, `node_modules/` + `package.json`/`package-lock.json` (some JS-based tests, per `codex-skill-audit.test.mjs` run via `node --test` noted in the plan's Task 3), `pyproject.toml`/`uv.lock` (Python deps managed via `uv`), `test_flere_seam.py`, `test_flere_worker.py`, `test_task_delivery.py` (top-level, outside `structural/`), `verification-pilot.json`.
- Plan doc's Task 2 verification commands additionally reference `python3 -m unittest discover -s scripts/tests -p test_sync_instructions.py`, `python3 -m pytest -q scripts/lean-startup-pilot/test_support.py`, and `bash tests/routing/reasoning-contract-test.sh` — i.e. there is also a `scripts/tests/` directory (separate from `tests/structural/`) and a `tests/routing/` subdirectory with role-dispatch tests (`tests/routing/role-dispatch-test.sh`, `tests/routing/role-dispatch-integration-test.sh` per Task 5's verification line).

**For a Jev decision layer / eval harness, the established convention is:** a pytest module under `tests/structural/` for pure-logic/contract tests (mirroring `test_burn_report.py`'s synthetic-fixture-plus-subprocess-plus-assert pattern), a `.bats` file under `tests/shell/` for the hook-wrapper/CLI-integration behavior, and — if the harness touches routing — a `tests/routing/*.sh` script following the existing role-dispatch test pattern.

---

## Gaps / follow-ups surfaced by this research (not yet acted on)

1. burn-report.py has zero Codex/non-Claude-Code support — a genuinely host-neutral eval harness (per mk-42j9.7's host-neutral framing) needs either an extension to burn-report.py or a parallel per-host burn accounting mechanism before the eval harness can produce comparable numbers across hosts.
2. burn-report.py has no bead/session scoping — only time-window and (indirectly, via directory-name lineage) thread scoping. The eval harness will need its own bead-to-lineage/time-window mapping layer on top of burn-report.py, or a burn-report.py patch adding bead-aware filtering.
3. `ic events record --source` is a closed five-value enum (`agency, interspect, review, coordination, intent`) with no obviously-named source for Jev/selector decisions — UNVERIFIED whether it's extensible, and UNVERIFIED where `ic`'s own source repo lives (not found inside this Clavain checkout in this pass).
4. No skill-admission or Jev source code exists yet anywhere in the repo — Task 7's proposed files (`scripts/skill-admission.py`, `config/skill-admission.yaml`, `scripts/tests/test_skill_admission.py`) are still just a plan; mk-42j9.7 is a from-scratch build, though it has strong templates to reuse (`context-gateway.py`'s receipt/eligibility/fallback pattern, `ic route dispatch`'s decision-record schema, `tier-fallback-chain.py`'s fallback-chain resolution, `executor-parity-eval.py`'s blind 3-arm eval scaffold).
5. The `interlab*` script family was not read in depth — worth a follow-up pass to rule out (or confirm) overlap with the 3-arm eval harness requirement before building new scaffolding.
6. mk-42j9.7 itself was not `bd show`n directly in this pass (only referenced via the epic's children listing and via .8/.9/.10's "DEPENDS ON" edges); a direct `bd show mk-42j9.7` would give its own description/acceptance-criteria text verbatim rather than reconstructed from siblings.
