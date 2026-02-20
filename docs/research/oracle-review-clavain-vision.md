## Severity rubric (P0–P3)

* **P0 (critical):** Breaks the stated 3-layer boundary (Kernel ⇄ OS ⇄ Apps), assigns authority to the wrong layer, or creates contradictions that will force architectural rework.
* **P1 (high):** Strongly confusing/unstable spec that will cause misimplementation, but fixable without re-architecting.
* **P2 (medium):** OS-level completeness gaps: key concerns are named but not specified enough to implement consistently.
* **P3 (low):** Readability, terminology, doc-rot risks, or minor inconsistencies.

---

# P0 issues

### P0 — Kernel is described as “mechanism not policy” while repeatedly taking policy ownership

**Quotes**

* > “**Mechanism, not policy — the kernel doesn't know what "brainstorm" means**”
* > “**The kernel enforces tier boundaries; the OS decides the policy at each tier**”
* > “**Deduplication — kernel enforces cosine similarity threshold (default 0.85)**”
* > “**Staleness decay — kernel decays priority on inactive beads (default: one level per 30 days)**”

**Problem**
You explicitly assert the kernel is policy-free, then assign it policy-laden behavior:

* “tier boundaries” and score thresholds are **policy** (they encode human preference / autonomy rules).
* cosine similarity thresholds and priority decay rates are also **policy**, not generic primitives.
  If Intercore truly stays “mechanism,” these belong in **OS configuration/policy** (or in a driver like Interject), with the kernel exposing only primitives (store records, run a gate, link items, emit events).

**Fix**

* Rewrite kernel responsibilities to: *store discoveries*, *run generic gates*, *emit events*, *support similarity search as a primitive* — **but not choose thresholds or decay rules**.
* Move “0.85 cosine similarity,” “one level per 30 days,” and tier cutoffs into an **OS policy module** (“Discovery Policy: Defaults”) and treat them as configurable constants.

---

### P0 — OS is required to “emit kernel events,” contradicting “kernel is system of record”

**Quote**

* > “**Emit a `run.paused` event with the gate failure evidence**”

**Problem**
If Intercore is “the durable system of record” and “every state change produces a typed, durable event,” then **the kernel emits events** as a consequence of state transitions. The OS should not be responsible for emitting `run.paused`—it should *request a pause* and rely on the kernel to emit the event.

**Fix**

* Replace with: “Call the kernel pause operation; **kernel emits `run.paused`** with evidence attached.”
* If you genuinely want OS-authored events, then you need an explicit concept like “external annotations” or “OS side-channel events” (but that weakens the “kernel is the record” claim).

---

### P0 — OS vision doc hardcodes kernel CLI commands, poll intervals, and service-management (layer breach + portability conflict)

**Quotes**

* > “**`ic events tail -f --consumer=clavain-reactor --poll-interval=500ms`**”
* > “**Systemd unit** (recommended for Level 2): `clavain-reactor.service` with `Restart=on-failure`.”
* > “**A systemd timer runs the scanner at configurable intervals (default: 4x daily with randomized jitter).**”
* > “**`ic discovery scan` triggers a full scan. `ic discovery submit`… `ic discovery search`…**”

**Problem**
This is kernel/app/deployment detail embedded in the OS philosophy/vision:

* Kernel CLI spellings (`ic …`) and consumer flags are **kernel interface details**.
* systemd is **host/ops** detail (Linux-specific) and belongs in an app/deployment doc, not OS policy.
* poll intervals are implementation tuning, not OS “opinion.”

Also, you claim:

* > “**If the host platform changes, opinions survive; UX wrappers are rewritten**”
  > …but the OS spec is currently entangled with **Linux + CLI** execution mechanics.

**Fix**

* Replace command strings with abstract interfaces:

  * “Reactor consumes kernel event stream via a consumer cursor.”
  * “Reactor advances runs via kernel ‘advance’ operation.”
* Move systemd examples + exact commands into:

  * Intercore docs (CLI reference)
  * or an “Ops / Deployment” doc under Apps/Autarch or infra.

---

### P0 — Drivers “call the kernel directly” undermines OS authority over policy/workflow

**Quote**

* > “**Call the kernel directly for shared state — no Clavain bottleneck**”

**Problem**
In a Kernel→OS→Apps stack, the OS is the **policy/workflow authority**. If drivers mutate shared state directly, you risk:

* bypassing OS quality gates / advancement rules,
* creating inconsistent invariants (OS thinks the world looks one way; drivers mutate it out of band),
* coupling policies to drivers (drivers start encoding opinions).

**Fix options (pick one and state it explicitly)**

1. **OS-as-authority:** Drivers are *pure capabilities* that produce artifacts/evidence; only OS advances runs / changes workflow state in the kernel.
2. **Kernel-as-authority:** Kernel enforces invariants strongly enough that direct driver writes can’t violate workflow policies (requires explicit invariant list).
3. **Split-write model:** Drivers can write only within a constrained namespace (e.g., “capability records”), while OS owns run/phase/gate transitions.

Right now the doc implies (3) but doesn’t specify constraints, so it reads as a boundary violation.

---

### P0 — “Kernel stateless between CLI calls” conflicts with a kernel-owned reconciliation engine

**Quotes**

* > “**The kernel remains stateless between CLI calls.**”
* > “**The reconciliation engine detects orphaned dispatches and emits `reconciliation.anomaly` events.**”
* > “**The reconciliation polling interval (default: 60s)** …”

**Problem**
A reconciliation engine that “detects” and “emits” implies a **background process** somewhere. Either:

* it’s in the kernel (then kernel is not “stateless between CLI calls”), or
* it’s an OS reactor responsibility (then it should not be described as a kernel engine).

**Fix**

* Decide ownership:

  * If **OS reactor** owns reconciliation: rename to “OS reconciliation loop” and describe it as querying kernel state + writing reconciled terminal outcomes.
  * If **kernel** owns reconciliation: drop the “stateless between CLI calls” claim and acknowledge Intercore has a daemon/worker mode.

---

# P1 issues

### P1 — Layering/numbering is internally inconsistent and diverges from the stated “3-layer architecture”

**Quote**

* > “Apps (Autarch) … **Layer 3: Drivers** … **Layer 2: OS** … **Layer 1: Kernel** … Profiler…”

**Problem**
Apps are listed *above* “Layer 3,” so you’ve effectively defined **4+ layers** (Apps + Drivers + OS + Kernel + Profiler). That directly collides with the framing you gave in the prompt (Kernel → OS → Apps), and it will cause constant confusion in later docs.

**Fix**

* Either:

  * make Drivers part of **Kernel extensions** (still “Layer 1.x”), or
  * make Drivers part of **Apps** (capability adapters used by apps), or
  * explicitly declare a **4-layer stack** and update all references accordingly.
    But don’t half-number it.

---

### P1 — App surfaces and OS sub-agency names are conflated (Gurgeh/Bigend/Coldwine/Pollard)

**Quotes**

* > “Interactive TUI surfaces: **Bigend, Gurgeh, Coldwine, Pollard**”
* > “PRD generation and validation | **Gurgeh** (confidence-scored spec sprint)”
* > “Apps (Autarch) — **Bigend** (monitoring), **Gurgeh** (PRD generation), **Coldwine** (task orchestration), **Pollard** (research intelligence).”

**Problem**
The same nouns are used as:

* **apps/surfaces** (UI),
* **capabilities**, and
* seemingly **agents/sub-agencies**.

This is a boundary blur: the OS doc starts to imply UI modules are also workflow engines.

**Fix**

* Split naming domains:

  * UI surfaces: `autarch.bigend`, `autarch.gurgeh`
  * OS workflows/sub-agencies: `clavain.design`, `clavain.discover`
  * Drivers/capabilities: `interflux.review`, `interject.discovery`
* Or keep names but explicitly define: “Gurgeh is an Autarch surface that invokes the Design sub-agency.”

---

### P1 — Kernel implementation details leak into OS “Architecture” section

**Quote**

* > “Layer 1: Kernel (Intercore) ├── **Host-agnostic Go CLI + SQLite** …”

**Problem**
A vision doc for OS policy shouldn’t pin kernel internals (language, storage engine). That belongs in Intercore docs. This will doc-rot quickly and creates false coupling.

**Fix**

* Replace with: “host-agnostic CLI + durable local store” (no tech choices), or just refer to Intercore doc.

---

### P1 — Current-state inventory counts will rot and aren’t load-bearing

**Quote**

* > “Claude Code plugin (**52 slash commands, 21 hooks, 1 MCP server**)”

**Problem**
This is precise but not architecturally meaningful; it will be wrong soon and creates noise.

**Fix**

* Replace with: “dozens of slash commands and hooks” or link to a generated inventory elsewhere.

---

# P2 issues (OS completeness gaps)

Below are gaps specifically in the OS concerns you listed (macro stages, routing, gates, discovery, reactor). These are not “missing features” so much as “missing spec that would let multiple people implement it consistently.”

### P2 — Macro-stages are described, but entry/exit criteria + artifacts + gate bindings are not specified

**Quotes**

* > “Each macro-stage maps to sub-phases internally… Phase chains are configurable per-run via the kernel.”
* > “Design … **Output** | Approved plan with gate-verified artifacts”
* > “Build … **Output** | Tested, reviewed code”

**Gaps**

* What are the canonical artifacts per stage? (PRD, architecture doc, task graph, test plan, rollout plan, etc.)
* What gates apply to which artifacts?
* How does OS decide a stage is “complete” vs “needs human decision”?
* How do “beads” relate to stage artifacts (Discover→Design handoff)?

**Add**
A small per-stage contract block:

* Inputs, outputs, required artifacts, required gates, and allowed human overrides.

---

### P2 — Model routing policy is described conceptually, but the OS-level contract is underspecified

**Quotes**

* > “Clavain's routing table can override these per-project, per-run, or per-complexity-level.”
* > “The composer optimizes the entire fleet dispatch within a budget constraint.”

**Gaps**

* Precedence rules: global defaults vs project vs run vs phase vs agent overrides.
* Failure handling: provider outage, rate limits, model deprecation, “fallback model” rules.
* Budget semantics: hard cap vs soft cap; what happens when estimate exceeds cap.
* Quality controls: how you prevent “cheap routing” from silently degrading correctness (needs explicit quality gates tied to routing decisions).

**Add**
A routing policy spec section with:

* configuration schema (even in pseudo-yaml),
* precedence order,
* fallback strategy,
* and “routing decision event” (what gets recorded for reproducibility).

---

### P2 — “Quality gates” are central in claims but not enumerated as OS opinions

**Quotes**

* > “Each phase … has its own model routing, agent composition, and **quality gates**.”
* > “The kernel (Intercore) is in active development with **gates**… working”

**Gaps**

* No gate taxonomy: artifact gates vs behavioral gates vs test gates vs review gates.
* No gate evidence schema: what constitutes “evidence,” where it lives, how it is referenced.
* No override model: how human overrides are recorded (and then used by Interspect) without destroying reproducibility.
* No “stoplight semantics”: are there warn-only gates? severity levels?

**Add**
A canonical gate library section in OS:

* gate names, purpose, evidence required, default owner agent(s), pass/fail/waive semantics.

---

### P2 — Discovery pipeline is detailed operationally, but the OS policy vs driver implementation boundary is unclear (and key concepts are undefined)

**Quotes**

* > “The kernel provides the discovery primitives (scored records, confidence gates, events)”
* > “Auto-create **bead** (P3 default)”
* > “Beads history … Solution docs … Session telemetry …”

**Gaps**

* What is a “bead”? (work item? issue? kernel object? artifact bundle?) It’s used as if it’s a primitive.
* What is the “interest profile” concretely (vector store? per-project? per-user?) and where is it stored?
* Reproducibility: how do you replay a scan with the same inputs and get the same triage?
* Safety/abuse controls: how you avoid prompt-injection via web content (even at “vision” level, you should state the stance).

**Add**

* A short glossary: bead, discovery record, interest profile, promotion/dismissal.
* A boundary statement: “Interject implements scoring; Clavain defines triage/autonomy policy; Intercore stores records + events.”

---

### P2 — Event reactor lifecycle describes mechanics, but not OS invariants (idempotency, ordering, multi-reactor safety)

**Quotes**

* > “calls `ic run advance` when conditions are met.”
* > “Hook-triggered … Each `dispatch.completed` event triggers an `ic run advance` attempt…”

**Gaps**

* Idempotency: what prevents duplicate `advance` calls from double-advancing?
* Concurrency: what if two reactors run? (session + systemd; or two terminals)
* Ordering: does advancement require causal ordering between `dispatch.completed` and gate evaluation?
* Backoff & flapping: repeated fail/pass cycles.
* Checkpointing consumer position: where does it live and how is it recovered?

**Add**
An OS reactor contract section:

* “at-least-once consumption,” “advance is idempotent,” “kernel enforces optimistic locking on run state,” etc.

---

# P3 issues (writing / clarity / doc hygiene)

### P3 — Several deeply-specific constants are presented as defaults without rationale

**Quotes**

* > “default: **4x daily** with randomized jitter”
* > “User submissions receive a source trust bonus (default **0.2**)”
* > “threshold (default: **0.85**)”
* > “lowers by **0.02** per feedback cycle”
* > “reconciliation polling interval (default: **60s**)”

**Problem**
These values will change and aren’t philosophically load-bearing; they distract and create “false spec rigidity.”

**Fix**
Move them into a “Reference Defaults” appendix or a config file example, not the narrative.

---

### P3 — ASCII mega-diagrams inside code fences are hard to maintain and hard to read in diffs

**Quote**

* The large block under “Discovery → Backlog Pipeline”

**Fix**
Convert to:

* a small diagram + a bulleted flow, or
* a mermaid diagram (if you want diagrams), or
* separate doc: “Discovery pipeline spec”.

---

### P3 — Unintroduced external referent (“OpenClaw”) creates a dangling concept

**Quote**

* > “Not a general AI gateway. That's what **OpenClaw** does.”

**Fix**
Either define OpenClaw earlier (1 sentence) or drop the reference in this doc.

---

# Targeted rewrite recommendations (to enforce boundaries)

## 1) Add an explicit “Contracts between layers” section (small, but clarifying)

Example structure (no implementation details):

* **Kernel contract (Intercore):** primitives, persistence guarantees, event delivery guarantees, atomic operations.
* **OS contract (Clavain):** policies: stage definitions, routing rules, gate rules, reactor rules.
* **Apps contract (Autarch):** presentation + interaction only; no workflow authority.
* **Drivers contract:** capability providers; specify whether they can write to kernel and under what constraints.

This single section resolves most boundary ambiguity.

## 2) Replace CLI strings and systemd with abstract operations

Everywhere you have:

* `ic events tail …`
* `ic run pause …`
* systemd units/timers

Rewrite as:

* “consume event stream with consumer cursor”
* “invoke pause/advance operations”
* “deploy reactor as (a) session process or (b) managed service” (details elsewhere)

## 3) Normalize naming: surface vs workflow vs capability

Pick a convention and stick to it:

* UI: **Autarch surfaces** (Bigend/Gurgeh/…)
* OS: **sub-agencies** (Discover/Design/Build/Ship)
* Drivers: **capabilities** (interflux review, interject discovery, interlock coordination)

Right now the doc blurs these.

---

# Minimal “must-fix” list (if you only do a few edits)

1. **Fix kernel policy leakage** (tiers, dedupe threshold, decay): move to OS policy. (P0)
2. **Remove/relocate kernel CLI + systemd operational detail** from OS vision. (P0)
3. **Clarify who emits events** (kernel vs OS) and reconcile the reconciliation-engine ownership. (P0)
4. **Disambiguate Gurgeh/Bigend/etc** as UI surfaces vs workflows/agents. (P1)
5. **Add a gate catalog + stage artifact contracts** (even a first pass). (P2)

If you want, I can propose concrete replacement text for the worst-offending paragraphs (Discovery trigger modes + Event Reactor section) in a way that keeps your intent but stays within the OS layer boundary.
