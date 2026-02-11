Below is a comprehensive gap analysis of **everything on factory.strongdm.ai (Techniques + Principles + Products + Weather Report + Story)** and **Simon Willison’s writeup**, focusing on what **Clavain** (Claude Code plugin) should adopt **beyond** the three techniques you already designed (Pyramid Summaries, Gene Transfusion, Shift Work).

I’m treating your three as “adopted (design-doc stage)” and listing the **remaining techniques/principles/patterns** as findings.

---

## 1. [P0] Holdout Scenarios + Satisfaction Scoring (Scenario testing, not “unit tests”)

1. **What is it?**
   StrongDM shifts validation from “tests pass” to **scenario testing**: end-to-end user stories treated like **holdout sets**, evaluated via **satisfaction** (“what fraction of observed trajectories likely satisfy the user?”) rather than a boolean. ([Simon Willison’s Weblog][1])

2. **Does Clavain already do something similar?**
   Partially: **/lfg** has “test” + “quality-gates”, and you have a **bug-reproduction-validator** workflow agent. But Clavain does **not** (a) maintain a scenario bank as an external holdout set, or (b) compute satisfaction over trajectories as a first-class metric (especially not as a gate).

3. **Should Clavain adopt it?**
   **Yes.** This is arguably *the* missing keystone that makes “non-interactive / no-human-review” even remotely defensible. It also directly addresses the “architecturally shallow” critique: without holdout scenarios, you don’t have an externalized notion of correctness.

4. **If yes, how? Concrete plugin implementation sketch**
   Add a **Scenario Bank + Satisfaction Harness** as a first-class substrate:

* **Filesystem layout (new):**

  * `.clavain/scenarios/dev/` — scenarios allowed to be seen by implementers (training set)
  * `.clavain/scenarios/holdout/` — hidden-from-implementation “QA holdout”
  * `.clavain/satisfaction/` — scores, trajectory logs, judge rationales (auditable)
* **New slash commands:**

  * `/scenario:new` → scaffold a scenario YAML/MD with: *intent*, *setup*, *steps*, *expected observations*, *rubric*, *risk tags*
  * `/scenario:run` → run selected scenarios, produce “trajectory bundles”
  * `/scenario:score` → LLM-as-judge + deterministic rubric scoring → outputs `satisfaction.json`
* **Agent roles (reuse + add minimal):**

  * reuse **fd-user-product** as primary “user satisfaction judge”
  * reuse **fd-correctness** as “technical oracle judge”
  * reuse **fd-safety** for “risk gating”
  * extend **bug-reproduction-validator** → becomes *scenario runner / harness operator*
* **Hard separation (“holdout” actually means holdout):**

  * Run implementation in a **git worktree** that *does not contain* `.clavain/scenarios/holdout/`
  * Run validation in a separate worktree/environment that *does* mount holdouts
  * If Claude Code’s file access can’t be hard-blocked, use **physical separation** (worktrees) rather than “please don’t read this folder”.
* **Gate integration (critical):**

  * `/lfg` must refuse “ship” unless `satisfaction >= threshold` *on holdouts*, not just tests.

5. **Priority**
   **P0.** (This is a core factory primitive, not a “nice add-on”.)

---

## 2. [P0] The Validation Constraint (Black-box correctness, not source inspection)

1. **What is it?**
   StrongDM explicitly requires a system that can **grow from natural-language specs** and be **validated automatically without semantic inspection of source**, treating code like an “ML model snapshot” whose correctness is inferred only from externally observable behavior. ([StrongDM][2])

2. **Does Clavain already do something similar?**
   Not really. Clavain’s **flux-drive** and the 6 core review agents imply a *very Software-1.0* stance: “inspect the artifact (doc/code) and critique it.” That’s valuable, but it’s the opposite of StrongDM’s black-box framing.

3. **Should Clavain adopt it?**
   **Partially.** Clavain is “general-purpose engineering discipline,” so you shouldn’t ban code reading. But you *should* offer a **Factory Mode** where review agents are instructed to prioritize **observable behavior + harness quality** over style/structure.

4. **If yes, how? Concrete plugin implementation sketch**
   Add **/factory-mode** (toggle) that changes defaults across workflows:

* **In factory-mode:**

  * `fd-correctness` and `fd-user-product` review **scenario outcomes, traces, API contracts**, not implementation details.
  * `fd-architecture` focuses on *system-level invariants* and *failure modes* expressed as harnessable properties (SLOs, backpressure, idempotency), not internal abstractions.
* Add `/validate-first` command:

  * forces creation/refresh of `.clavain/validation/` artifacts *before* “implement”
  * outputs: scenario list, coverage map, risk register, pass criteria
* Add a **“black-box review report”** output format: “What would a user observe if this fails?”

5. **Priority**
   **P0.** (This is the conceptual backbone StrongDM uses to justify everything else.)

---

## 3. [P1] Digital Twin Universe (DTU) as a Validation Accelerator

1. **What is it?**
   DTU is **behavioral clones** of critical third-party dependencies (Okta/Jira/Slack/Google apps, etc.) used to validate at high volume with deterministic replay, safely exercising failure modes without rate limits/costs. ([StrongDM][3])

2. **Does Clavain already do something similar?**
   No. You have **Context7** (docs) and Serena (semantic code analysis), but nothing that generates or manages **behavioral API clones**.

3. **Should Clavain adopt it?**
   **Yes (as “DTU-lite”).** Clavain is a plugin, not a platform, so you likely won’t ship full twins for Okta/Slack. But you *can* adopt DTU as a **repeatable workflow** for: “generate a high-fidelity mock service that behaves like X enough to run scenarios deterministically.”

4. **If yes, how? Concrete plugin implementation sketch**
   Introduce a DTU workflow + artifact standard:

* **New skill:** `/dtu` (or `/twin`) with subcommands:

  * `/dtu:scope` → identify *which endpoints/behaviors you actually need* by analyzing code usage (Serena) + traffic logs
  * `/dtu:spec` → assemble an API contract bundle (OpenAPI, SDK docs, edge cases)
  * `/dtu:build` → scaffold a twin service (language-agnostic template; Dockerized)
  * `/dtu:conformance` → run differential tests against the real service until behavior matches
  * `/dtu:faults` → inject failure modes (timeouts, partial writes, 429s, eventual consistency)
* **Artifact layout:**

  * `.clavain/dtu/<service>/contract/`
  * `.clavain/dtu/<service>/twin/`
  * `.clavain/dtu/<service>/conformance/`
  * `.clavain/dtu/<service>/replay/` (captured interactions → deterministic replays)

5. **Priority**
   **P1** (P0 for integration-heavy systems; otherwise high leverage but not always needed).

---

## 4. [P1] “Compatibility Targets” Prompting Strategy (DTU fidelity trick)

1. **What is it?**
   A key strategy (shared via Willison’s update) is: use **popular public reference SDK client libraries** as compatibility targets, aiming for **100% compatibility**—a pragmatic way to define “behavioral correctness” for twins. ([Simon Willison’s Weblog][1])

2. **Does Clavain already do something similar?**
   Not explicitly. Gene Transfusion uses exemplars, but Clavain doesn’t formalize “compatibility target = SDK X + its tests” as a validation contract.

3. **Should Clavain adopt it?**
   **Yes.** It’s a concrete, mechanical way to reduce ambiguity in any emulation/porting effort (DTU and Semport).

4. **If yes, how? Concrete plugin implementation sketch**
   Add a small but powerful convention to `/dtu` and `/semport`:

* require: `.clavain/compatibility-targets.yml`

  * lists SDK repos, versions, test suites, golden examples
* provide `/compat:verify` that:

  * runs those SDK tests against the twin/port
  * produces a “compatibility report” + diff artifacts

5. **Priority**
   **P1.** (Huge ROI, relatively small implementation.)

---

## 5. [P0] The Filesystem as Primary Memory + “Genrefying” (self-organizing repo memory)

1. **What is it?**
   StrongDM treats the filesystem as a **mutable, inspectable world-state**: agents write indexes/scratch/state to disk, rehydrate context via search, and periodically reorganize (“genrefying”) to optimize future retrieval. ([StrongDM][4])

2. **Does Clavain already do something similar?**
   **Somewhat**: `/compound` writes durable institutional knowledge to `docs/solutions/`, and you have hooks like **session-handoff**, **dotfiles-sync**, and **auto-compound**. But Clavain does not yet define a **single coherent “agent memory filesystem contract”** (where things go, how indexed, how pruned/rebalanced).

3. **Should Clavain adopt it?**
   **Yes.** This is foundational for multi-agent discipline and cross-session continuity—especially for Claude Code workflows.

4. **If yes, how? Concrete plugin implementation sketch**
   Create a **Clavain Memory Substrate (CMS)** with strict conventions:

* **Standard directories (new):**

  * `.clavain/index/` (search-friendly markdown indexes)
  * `.clavain/runs/` (run manifests, checkpoints)
  * `.clavain/scratch/` (ephemeral working state)
  * `.clavain/learnings/` (curated, durable—feeds /compound)
  * `.clavain/scenarios/` (dev + holdout as above)
  * `.clavain/contracts/` (API contracts, invariants, SLOs)
* **New commands:**

  * `/index:update` (refresh indexes based on new artifacts)
  * `/genrefy` (restructure taxonomy + rewrite indexes + preserve backlinks)
* **Hook changes:**

  * extend **auto-compound** to also update `.clavain/index/`
  * make **session-handoff** write a canonical `handoff.md` into `.clavain/runs/<run>/`

5. **Priority**
   **P0.** (Without this, everything else becomes brittle and “chat-memory dependent.”)

---

## 6. [P1] CXDB Patterns (Turn DAG + Blob CAS + Typed Payloads) for Observability + Recovery

1. **What is it?**
   CXDB is a self-hosted context store purpose-built for agent conversations: **Turn DAG** (branching with O(1) forks), **Blob CAS** (content-addressed dedup; BLAKE3), and a **type registry** enabling projections + UI debugging. ([StrongDM][5])

2. **Does Clavain already do something similar?**
   Partially: **session-handoff** + **beads** + `/compound` give *some* persistence, but not a first-class execution database with branching, deduped artifacts, typed envelopes, and visual debugging.

3. **Should Clavain adopt it?**
   **Partially (adopt the architecture, not necessarily the full product).** Clavain doesn’t need to ship CXDB, but it *does* need:

* a **run record**
* **branching history**
* **artifact dedup**
* structured “what happened?” debugging

4. **If yes, how? Concrete plugin implementation sketch**
   Two viable paths:

* **Option A (practical): “CXDB-lite” embedded**

  * local SQLite for turns + edges (DAG)
  * filesystem CAS for blobs: `.clavain/blobs/<hash>`
  * typed JSON envelopes for events: `clavain.turn.v1`, `clavain.toolcall.v1`, `clavain.scenario_result.v1`
* **Option B (ambitious): CXDB as an optional external dependency**

  * add a third MCP server: `cxdb`
  * log every command + tool output + scenario trajectory
  * support “fork run at checkpoint” → branch execution

5. **Priority**
   **P1.** (Becomes P0 if you implement Attractor-mode/resumability seriously.)

---

## 7. [P1] Attractor-Style Graph Orchestration (beyond linear /lfg)

1. **What is it?**
   Attractor is a **non-interactive coding agent** built as a graph of nodes (phases) with **natural-language edges** evaluated by an LLM; key properties include determinism (given same inputs), observability at transitions, resumability, and composability. ([StrongDM][6])

2. **Does Clavain already do something similar?**
   Somewhat: `/lfg` is a pipeline and you’ve designed a Shift-Work Boundary, but `/lfg` is still fundamentally a **fixed linear workflow**, not a graph with conditional branching, convergence loops, and explicit checkpoints.

3. **Should Clavain adopt it?**
   **Yes.** This is the cleanest way to make Clavain’s workflows “factory-grade” rather than “agent chat with structure.”

4. **If yes, how? Concrete plugin implementation sketch**
   Add **Attractor-mode for Clavain** without copying their whole stack:

* **New file format:** `.clavain/pipelines/<name>.dot` *or* YAML
* **New commands:**

  * `/pipeline:new` (scaffold graph)
  * `/pipeline:run` (execute node-by-node)
  * `/pipeline:resume` (resume from checkpoint)
  * `/pipeline:fork` (branch from a node with new assumptions)
* **Node execution contract:**

  * each node declares: `agent`, `inputs`, `tools allowed`, `expected outputs`, `gate condition`
  * node outputs are written to `.clavain/runs/<run_id>/<node>/...`
* **Checkpointing:**

  * after each node, create a git commit on a run branch or worktree
  * store manifest (`run.json`) + pointers to blob CAS (ties into CXDB-lite)

5. **Priority**
   **P1.**

---

## 8. [P1] Weather Report Model Routing + “Consensus Operator” (operationalizing model choice)

1. **What is it?**
   StrongDM publishes a frequently updated “Weather Report”: which models they run for which tasks, with configurations and a “consensus operator” (merge independent plans). It’s an experience report of what works in practice, not a benchmark. ([StrongDM][7])

2. **Does Clavain already do something similar?**
   Partially: Clavain has **Oracle integration** (cross-AI review with GPT-5.2 Pro) and a **Clodex toggle** for Codex agents, but you don’t have a unified “model routing policy” artifact or a systematic consensus planner.

3. **Should Clavain adopt it?**
   **Yes.** Especially because Clavain already spans multiple “agent roles”—model selection should be a first-class control surface.

4. **If yes, how? Concrete plugin implementation sketch**

* **Add `.clavain/weather.md` + `.clavain/models.yml`**

  * map tasks → preferred model/provider/settings
  * include “escalation policy” when confidence is low
* **Add `/models:route`**

  * given task type + risk tier → select model(s)
* **Add `/consensus:plan`**

  * run **two independent planners** (e.g., Claude + GPT via Oracle)
  * merge using a dedicated “consensus merge” agent (could reuse `plan-reviewer`)
* **Hook:** `session-start` injects today’s routing rules.

5. **Priority**
   **P1.** (It’s how you avoid “one-model-does-everything” failure modes.)

---

## 9. [P2] Semport (One-time, Ongoing, Adaptive semantic ports)

1. **What is it?**
   Semport is semantic code porting that preserves intent/behavior—not just syntax. StrongDM also uses it as an **ongoing dependency-through-translation** system: daily sync from an upstream repo into an internal language/framework, with tests + releases automated. ([StrongDM][8])

2. **Does Clavain already do something similar?**
   Not directly. Clavain has Serena (semantic analysis) and could use Context7 for docs, but there’s no defined workflow for “port this, prove equivalence, keep in sync.”

3. **Should Clavain adopt it?**
   **Yes (P2).** It’s not always needed, but when you need it, it’s extremely valuable—and it fits a “general-purpose engineering discipline” plugin well.

4. **If yes, how? Concrete plugin implementation sketch**
   Add a `/semport` workflow with explicit invariants + conformance:

* **/semport:one-shot**

  * generate target implementation
  * derive invariants from source: public API behavior, edge cases, golden traces
  * run equivalence harness (golden tests)
* **/semport:ongoing**

  * track upstream commits (CI job or scheduled local run)
  * generate PR with translated changes
  * run full validation + scenario suite
  * record decisions + patches into `/compound`

5. **Priority**
   **P2.**

---

## 10. [P2] StrongDM ID Pattern (Agent identity, scoped sharing, and capability boundaries)

1. **What is it?**
   StrongDM ID provides identity for humans/workloads/agents with federated auth, programmatic onboarding, evidence-based identity (attestation), and fine-grained policy controls (including scoped sharing). ([StrongDM][9])

2. **Does Clavain already do something similar?**
   Only superficially: you have named agents, but not real identity/attestation, and not a policy framework for “which agent can touch what.”

3. **Should Clavain adopt it?**
   **Partially.** Full identity infra is out of scope for a plugin, but the **principle of provenance + scoped capability** is highly adoptable and directly supports holdout protection + safety.

4. **If yes, how? Concrete plugin implementation sketch**

* Add `.clavain/provenance/` run manifests containing:

  * agent name, model, version, commands invoked, artifacts produced
* Add `.clavain/policy.yml`:

  * per-agent file path allowlists/denylists
  * per-agent tool permissions (e.g., “no network”, “no secrets”, “no holdout folder”)
* Enforce policy at the command layer:

  * when `/lfg` enters implementation phase, it switches to a restricted worktree (no holdouts, limited secrets)

5. **Priority**
   **P2.**

---

## 11. [P0] Seed → Validation Harness → Feedback Loop (make it the spine of /lfg)

1. **What is it?**
   StrongDM’s core loop is: **Seed → Validation harness → Feedback loop** (repeat until holdout scenarios pass consistently). Seeds can be a spec, a screenshot, a few sentences, or an existing codebase. ([StrongDM][10])

2. **Does Clavain already do something similar?**
   Partially: `/brainstorm` and `/lfg` already resemble Seed/Plan/Execute/Test. But Clavain doesn’t yet enforce:

* harness-first as a structural requirement
* feedback as a closed loop with explicit “holdouts must keep passing”

3. **Should Clavain adopt it?**
   **Yes.** This should be the organizing principle of Clavain’s “engineering discipline.”

4. **If yes, how? Concrete plugin implementation sketch**
   Refactor `/lfg` into explicit loop artifacts:

* **Seed artifact**: `.clavain/seed/seed.md`

  * contains: intent, constraints, non-goals, references (screenshots/logs/links), assumptions
* **Harness artifact**: `.clavain/validation/harness-plan.md`

  * scenarios (dev + holdout pointers), rubrics, required DTU twins, risk matrix
* **Feedback artifact**: `.clavain/feedback/iteration-N.md`

  * failing trajectories, hypothesized causes, next patch plan
* **Execution rule**: `/lfg` iterates `implement → validate → feedback` until:

  * holdout satisfaction threshold met
  * regressions absent for K consecutive runs

5. **Priority**
   **P0.**

---

## 12. [P1] Apply More Tokens (convert obstacles into model-consumable evidence packs)

1. **What is it?**
   StrongDM’s “fuel” principle: for every obstacle, convert it into something the model can understand—traces, screen captures, transcripts, incident replays, adversarial use cases, simulations, surveys, interviews, etc. ([StrongDM][10])

2. **Does Clavain already do something similar?**
   Some: Context7 (docs), Serena (semantic analysis), /compound (knowledge capture). But there’s no unified “evidence pack” pipeline that aggressively harvests and structures raw signals.

3. **Should Clavain adopt it?**
   **Yes.** This is how you turn “unknown unknowns” into runnable validation inputs.

4. **If yes, how? Concrete plugin implementation sketch**
   Create an **Evidence Pack** standard:

* `.clavain/evidence/<case_id>/`

  * `logs/`, `screens/`, `traces/`, `replays/`, `customer-notes/`
  * `manifest.yml` describing provenance + how to replay
* Add commands:

  * `/evidence:new` (scaffold)
  * `/evidence:ingest` (paste logs, link traces, normalize)
  * `/evidence:replay` (turn evidence into scenario steps)
* Wire to feedback loop:

  * failing scenario automatically generates an evidence pack + links it in iteration feedback

5. **Priority**
   **P1.**

---

## 13. [P2] “No humans write code / no humans review code” as an *optional* operational mode

1. **What is it?**
   StrongDM’s mantra/rules include “code must not be written by humans” and “code must not be reviewed by humans,” with quality driven by scenarios + DTU + validation loops. ([Simon Willison’s Weblog][1])

2. **Does Clavain already do something similar?**
   Not as a mode. Clavain is designed to assist engineering work, including review agents that mimic human review.

3. **Should Clavain adopt it?**
   **Partially.** As a **strict opt-in** mode (“Factory Mode”), because many teams will still require code review for compliance/security. But giving users the option to run “lights-out validation-first” is aligned with your goal.

4. **If yes, how? Concrete plugin implementation sketch**

* `/factory-mode:on`

  * disables/soft-deprioritizes code-style critique
  * forces harness + scenario bank creation
  * requires satisfaction gates
  * encourages multi-model consensus planning
* Provides an audit trail (CXDB-lite/provenance manifests) so humans can still *audit the process* without reading every LOC.

5. **Priority**
   **P2.**

---

## 14. [P2] Token Economics as an Engineering Control (budgeting + escalation policies)

1. **What is it?**
   StrongDM frames tokens as fuel, even using a provocative heuristic ($1,000/day/engineer) to push teams toward spending tokens to buy validation and reliability. ([Simon Willison’s Weblog][1])

2. **Does Clavain already do something similar?**
   No explicit cost instrumentation or escalation policy, beyond having Oracle/Codex toggles.

3. **Should Clavain adopt it?**
   **Yes (lightweight).** Not the dollar amount—but the idea that “budget is a knob” and Clavain should expose it.

4. **If yes, how? Concrete plugin implementation sketch**

* Add `.clavain/budget.yml` with:

  * max iterations, max tool calls, escalation thresholds (“if failing twice → use stronger model”)
* Add `/budget:report`

  * per-session and per-run token/call estimates (even approximate is useful)
* Tie into Weather Report routing:

  * cheap model for bulk classification, expensive for critique/safety, etc. ([StrongDM][7])

5. **Priority**
   **P2.**

---

## 15. [P2] Unified Multi-Provider Abstraction (reduce friction across Claude/Codex/etc.)

1. **What is it?**
   StrongDM’s ecosystem (Attractor + community implementations) emphasizes provider-neutral orchestration and multi-model pipelines—practically, a unified interface layer for models/tools to swap providers per node. ([StrongDM][6])

2. **Does Clavain already do something similar?**
   Partially: **Oracle integration** (GPT-5.2 Pro) and **Clodex toggle** indicate multi-provider thinking, but it’s not formalized as a “provider-neutral execution contract.”

3. **Should Clavain adopt it?**
   **Yes (P2).** This becomes more important as you add scenario scoring, consensus operators, and specialized roles.

4. **If yes, how? Concrete plugin implementation sketch**

* Define a single internal contract:

  * `{role, task_type, risk_tier} → {provider, model, params}`
* Route:

  * review agents may be routed differently than implement agents
  * “consensus plan” intentionally runs two different providers
* Store routing decisions in provenance manifests (auditable)

5. **Priority**
   **P2.**

---

# Supplemental: why your 3 “adopted” techniques felt shallow (and how to deepen them)

Not new techniques, but this is the likely root cause of the “architecturally shallow” verdict:

* Your Pyramid Mode / Gene Transfusion / Shift-Work Boundary are **workflow-shape improvements**. StrongDM’s core advantage is **validation architecture**: holdout scenarios + satisfaction + DTU + deterministic orchestration + observability (CXDB). ([StrongDM][2])
* If you adopt **Findings #1, #2, #5, #6, #7**, your three existing design docs will suddenly have a much deeper “factory substrate” to stand on.

If you want, I can also rewrite your existing three technique design docs in the style implied by the above (artifact contracts, file layouts, gates, run manifests, resumability), but the list above is the **complete set of gaps** from StrongDM’s published techniques/principles/products + Willison’s analysis.

[1]: https://simonwillison.net/2026/Feb/7/software-factory/ "https://simonwillison.net/2026/Feb/7/software-factory/"
[2]: https://factory.strongdm.ai/techniques "https://factory.strongdm.ai/techniques"
[3]: https://factory.strongdm.ai/techniques/dtu "https://factory.strongdm.ai/techniques/dtu"
[4]: https://factory.strongdm.ai/techniques/filesystem "https://factory.strongdm.ai/techniques/filesystem"
[5]: https://factory.strongdm.ai/products/cxdb "https://factory.strongdm.ai/products/cxdb"
[6]: https://factory.strongdm.ai/products/attractor "https://factory.strongdm.ai/products/attractor"
[7]: https://factory.strongdm.ai/weather-report "https://factory.strongdm.ai/weather-report"
[8]: https://factory.strongdm.ai/techniques/semport "https://factory.strongdm.ai/techniques/semport"
[9]: https://factory.strongdm.ai/products/strongdm-id "https://factory.strongdm.ai/products/strongdm-id"
[10]: https://factory.strongdm.ai/principles "https://factory.strongdm.ai/principles"
