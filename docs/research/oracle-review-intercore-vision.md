Below is a kernel-focused review against the stated layering you gave:

* **Layer 1 — Kernel (Intercore):** mechanisms/primitives, durability, enforcement, observability.
* **Layer 2 — OS (Clavain):** workflow/policy, routing, UX hooks, “what to do next”.
* **Layer 3 — Apps (Autarch):** UI/TUI surfaces over kernel state + OS actions.

I’m flagging **layer boundary violations**, **contradictions**, **completeness gaps**, and **writing issues**, each with **P0–P3 severity** and **direct quotes**.

---

## P0 — Must-fix architecture boundary breaks

### P0.1 — “Three-layer architecture” contradicts your stated 3-layer model (and the doc itself)

You asked for Kernel → OS → Apps, but the doc defines “three layers” as Kernel/OS/**Drivers**, and then separately introduces Apps and a Profiler.

> “### Three-Layer Architecture
> The ecosystem has three distinct layers, each with clear ownership:
> …
> **Layer 3: Drivers (Plugins)** …
> **Layer 2: OS (Clavain)** …
> **Layer 1: Kernel (Intercore)** …”

Yet earlier:

> “**Autarch (Apps) — interactive TUI surfaces** (see Autarch vision doc)”

And the earlier model section also introduces an extra system:

> “**Interspect (Profiler)** …”

**Why this is P0:** readers will not know what “Layer 3” actually is (Drivers vs Apps), and you’re mixing two different architectural decompositions in the same kernel vision doc. This will cause incorrect ownership decisions (what belongs in kernel vs OS vs apps).

**Fix direction:** pick one consistent stack and reflect it everywhere. If “Drivers” exist, either:

* treat them as **OS extensions** (still Layer 2), or
* treat them as **Apps** (Layer 3), but then they shouldn’t be described as bypassing the OS for shared state without strong constraints.

---

### P0.2 — “Drivers” is overloaded: plugin drivers vs dispatch/sandbox drivers

Same word used for two different concepts.

> “**Companion Plugins (Drivers)** …”

Later:

> “Sandboxing is a **dispatch driver capability**, not a kernel subsystem.”

**Why this is P0:** it’s impossible to reason about boundary ownership when the term “driver” can mean “Claude Code plugin” *and* “agent execution backend/runtime”. These have different trust, API, and lifecycle constraints.

**Fix direction:** rename one class:

* “plugins” / “extensions” for Claude Code-native integrations
* “runners” / “executors” for dispatch backends (Claude CLI, Codex CLI, container runtime)

---

### P0.3 — Kernel claims “mechanism not policy” but specifies policy algorithms for discovery/backlog

The kernel section drifts into policy/algorithmic choice (scoring model and weights), which belongs in OS (policy) or Profiler (learning), not kernel primitives.

> “**Confidence scoring** — Embedding-based similarity against a learned profile vector, with configurable weight multipliers for source trust, keyword matches, recency, and capability gaps”

and

> “**Feedback ingestion** … update the interest profile and source trust weights”

and

> “**Staleness decay mechanism.** … (configurable rate, default: **one priority level per 30 days** without activity).”

**Why this is P0:** this isn’t “mechanism”; it’s a specific policy model (weights, learned vectors, decay defaults). If kernel owns this, kernel becomes the policy layer—contradicting the doc’s own principle and your intended architecture.

**Fix direction:** kernel should provide:

* durable storage for “discovery facts” + “scores” (as opaque numbers with provenance)
* primitive gates like “can promote from tier X → Y”
  …but scoring computation, learned profiles, weighting, decay defaults should be OS/Profiler.

---

### P0.4 — Kernel takes ownership of “backlog” semantics (App/OS domain object)

Backlog is a workflow artifact, not a kernel primitive (unless you explicitly redefine kernel scope to include PM/backlog as a first-class kernel domain—which then conflicts with “mechanism not policy”).

Examples:

> “Event sources: … **Backlog changes** (refined, merged, submitted, prioritized)”

and

> “### Backlog Refinement Primitives
> The kernel provides two backlog enforcement mechanisms: …”

and

> “**Backlog rollback.** … identifies all beads created … proposes closing them …”

**Why this is P0:** “backlog item”, “bead”, “priority level” are OS/app vocabulary. Kernel owning these breaks the layer boundary and creates a kernel that is no longer host/workflow-agnostic.

**Fix direction:** if kernel must support backlog, define it as a **generic “work item registry” primitive** (opaque labels + state machine), and keep “beads / priority / refinement rules” purely OS/app-level.

---

### P0.5 — Kernel tries to generate Git revert sequences (OS/app responsibility)

This is operational workflow logic, not kernel mechanism.

> “`ic run rollback <id> --layer=code` … **generates a `git revert` sequence**. The kernel doesn't execute the revert — it produces the plan.”

**Why this is P0:** kernel is now encoding VCS-specific operational policy and emitting actionable commands. In a strict kernel model, kernel records provenance (commit SHAs), and OS/app generates “plans”.

**Fix direction:** kernel primitive: “list commits associated with run/dispatch/artifact”. OS/app: “generate git revert plan”.

---

### P0.6 — Kernel defaults/presets contradict “kernel doesn’t own phase semantics”

In “Open-source product” and horizon success you move toward kernel owning workflow presets.

> “Phase chains, gate rules, and throttle intervals **should have defaults** that cover common cases.”

and

> “Fully custom phase chains with **sprint as default preset**.”

But earlier:

> “**Phase names and semantics** — "brainstorm", "review", "polish" are Clavain vocabulary.”

**Why this is P0:** A “sprint preset” is explicitly OS policy. If it’s in kernel, kernel now contains OS.

**Fix direction:** ship presets in Clavain (OS) or as sample configs; kernel can ship **example JSON** but not built-in semantics.

---

### P0.7 — “Plugins call ic directly — no Clavain bottleneck” undermines OS policy enforcement

This statement sets up a bypass channel around the OS layer.

> “Plugins call `ic` directly for shared state — **no Clavain bottleneck**”

**Why this is P0:** if plugins can mutate kernel state directly, how does Clavain enforce workflow policy coherently? Either:

* kernel must have capability controls and namespace boundaries, or
* OS must be the sole writer for policy-governed state transitions.

Right now the doc implies “everyone writes,” while also promising OS-controlled policy.

**Fix direction:** define:

* what kernel APIs are “public writes” vs “OS-only writes”
* scope/namespace rules (e.g., plugin can write under `state/plugin/<name>/…` but cannot advance runs unless OS actor)

---

### P0.8 — Dependency graph “auto-verification events” are workflow reactions (OS/app), not kernel mechanism

This is an implicit policy reaction embedded into kernel.

> “When intercore ships a change, **the kernel auto-creates a verification event** for dependent projects. The OS consumes this event and creates a "verify downstream" bead…”

**Why this is P0:** deciding that “run.completed triggers downstream verification” is workflow policy. Kernel should record facts (run completed; dependency graph exists) and emit minimal signals; OS should choose reaction semantics.

**Fix direction:** kernel emits `run.completed` + exposes dependency graph query; OS generates verification runs/beads/events.

---

## P1 — Major contradictions / internal inconsistencies

### P1.1 — “No polling” vs “pull-based tail” vs “subscribe”

The doc oscillates between “no polling” and “poll/tail”.

> “**No background event loop.** … Event consumption is **pull-based**: consumers call `ic events tail …`”

Later:

> “This means the OS doesn't need to **poll** for changes. **It subscribes** to kernel events and reacts.”

**Why this is P1:** “subscribe” implies push; “tail” implies pull/polling. Readers will mis-design the event reactor lifecycle.

**Fix direction:** say: “OS doesn’t poll state tables; it polls the event log via cursor tailing.”

---

### P1.2 — Event retention/pruning is described as automatic *and* manual

In Events section:

> “**Event retention:** Events are pruned by a configurable retention policy (default: 30 days).”

In Assumptions:

> “The event log grows unboundedly without pruning. The kernel provides `ic events prune …` … **The OS is responsible for scheduling these — the kernel does not auto-prune.**”

**Why this is P1:** contradictory operational model.

**Fix direction:** explicitly: “Retention policy is enforced only when OS runs `ic events prune`.”

---

### P1.3 — “Kernel never stores OS policy” vs “kernel stores run config snapshots of OS policy”

You say:

> “The kernel never stores, interprets, or manages OS policy.”

Then immediately:

> “**Run config snapshots:** … kernel captures an immutable snapshot of the OS-provided configuration (phase chain, gate rules, dispatch policies)… The kernel treats it as opaque structure — **it evaluates gate rules from the snapshot**…”

**Why this is P1:** “never stores” is false if snapshots exist. “opaque” is also inconsistent with “evaluates”.

**Fix direction:** reword to: “Kernel stores OS policy *as run provenance* and interprets only the minimal subset required for primitive enforcement (gate check types, tiers).”

---

### P1.4 — Versioning conflict: “planned v3” but “current kernel schema (v5)”

This line is likely to confuse everyone:

> “The discovery subsystem is planned for v3. … do not exist in the current kernel schema (**v5**).”

**Why this is P1:** you have at least three version axes in play: doc version 1.6, horizon v1–v4, schema v5. It’s not explained.

**Fix direction:** define version namespaces explicitly:

* Product horizon: H1/H2/H3 (or “Release v1/v2…”)
* Schema version: “schema_rev=5”
* Doc version: “doc=1.6”

---

### P1.5 — Spawn limits and rollback described as present capabilities but marked “planned”

Dispatch section:

> “**Spawn limits** — maximum concurrent dispatches … Prevents runaway agent proliferation…”

Enforcement table:

> “Spawn limits … Horizon: **v1.5 (planned)**”

Kernel/OS model includes rollback:

> “Rollback: phase rewind, dispatch cancellation…”

Enforcement table:

> “Rollback … Horizon: **v2 (planned)**”

**Why this is P1:** the doc reads like these exist today, but your horizon table says they don’t. This undermines credibility and implementation sequencing.

**Fix direction:** stamp each subsystem heading with (current vs planned), or split “Current kernel contract” vs “Target kernel contract”.

---

### P1.6 — Cross-project visibility: “no visibility” vs “you can share one DB”

Earlier:

> “Today, there is **no cross-project visibility — each project's `ic` database is an island.**”

Later:

> “Multiple repos can use separate databases … **or share one** — the kernel scopes by run ID…”

**Why this is P1:** this is either false (“no visibility”) or missing constraints (“shared DB is discouraged / not supported / breaks invariants”).

**Fix direction:** clarify supported topology for v1: “one DB per project” (enforced), or “shared allowed but not recommended,” and how it interacts with portfolio/relay.

---

### P1.7 — “CLI can’t crash between calls” is rhetorically cute but technically wrong/confusing

> “A CLI binary is zero-ops… and **can't crash between calls because it doesn't exist between calls**.”

Later you correctly discuss:

> “If `ic` crashes mid-operation…”

**Why this is P1:** readers may misunderstand reliability claims. The “between calls” line is a rhetorical distraction that conflicts with the later crash semantics section.

**Fix direction:** replace with: “No daemon lifecycle to manage; failure modes are limited to individual invocations.”

---

### P1.8 — Filesystem locks rationale doesn’t match their declared purpose

> “locks must work even when the database is unavailable (corruption, locked by another writer), providing a recovery path.”

But later:

> “Filesystem locks protect exactly one thing: serializing read-modify-write operations on the SQLite database itself…”

**Why this is P1:** if DB is corrupted/unavailable, serializing DB mutations is moot. “Recovery path” isn’t explained.

**Fix direction:** either:

* change rationale to “avoid SQLite busy contention / provide deterministic mutual exclusion,” or
* describe an explicit recovery workflow where locks matter.

---

## P2 — Completeness gaps that will block implementation alignment

### P2.1 — Cursor semantics are underspecified (does tail advance? who acks? concurrency?)

You say both:

> “consumers call `ic events tail --consumer=<name>` to retrieve events since their last cursor position.”

and

> “cursor advancement is the consumer's responsibility (call `ic events cursor set`).”

Missing:

* Does `tail` implicitly advance the cursor?
* Is there an atomic “read + advance” mode?
* What happens if two processes tail with the same consumer name?

**Fix direction:** define a single contract:

* `tail` returns events without advancing
* `tail --commit` advances to last returned event in same transaction
* consumer names must be unique per process class or support leases

---

### P2.2 — Using SQLite `rowid` as cursor is unsafe if you recommend `VACUUM`

> “Each consumer tracks its high-water mark (the `rowid` of the last processed event).”

Later you recommend:

> “SQLite `VACUUM` should be run periodically…”

`VACUUM` can rewrite tables; `rowid` stability is not a safe long-term cursor identifier unless you explicitly define the event table with `INTEGER PRIMARY KEY` and treat that as the cursor.

**Fix direction:** specify `event_id INTEGER PRIMARY KEY` and cursor on `event_id`, not `rowid`.

---

### P2.3 — Gate “override” exists in event taxonomy but override mechanism is not specified

You list:

> “Gate evaluations (pass, fail, override)”

…but there’s no primitive/command described for:

* who can override
* whether override advances phase
* how override evidence is recorded

**Fix direction:** add a kernel primitive (`ic gate override …`) and clarify role/actor semantics.

---

### P2.4 — “Soft gates warn” is ambiguous in a CLI world

> “Gate tiers control enforcement: hard gates block advancement, **soft gates warn**, none-tier gates skip…”

What is a “warn” at the kernel boundary?

* exit code 0 with warning event?
* exit code 0 but additional stderr?
* does it still advance?

**Fix direction:** define behavioral contract: advancement + warning event, or no advancement but non-fatal code, etc.

---

### P2.5 — Artifact ingestion/validity is unclear (DB-only check can drift from filesystem reality)

You explicitly state:

> “it checks the database, **not the filesystem directly**. Artifact content lives on disk; the kernel tracks metadata.”

Missing:

* how artifacts get registered (spawn output? explicit `ic artifact add`?)
* what happens if the file is deleted/changed after registration
* whether hash is verified at gate time (currently implied “no”)

**Fix direction:** specify: registration source-of-truth, optional verification mode, and drift events (artifact.missing / artifact.hash_mismatch).

---

### P2.6 — Dispatch “liveness detection” references undeclared side channels

> “convergent signals (kill(pid,0), **state file presence, sidecar appearance**) handle reparented processes.”

What is the state file? Who writes it? What’s the schema? What’s “sidecar appearance”?

**Fix direction:** define an executor interface: runner must write a standardized “dispatch heartbeat/status file” if PID isn’t reliable.

---

### P2.7 — Storing environment variables/prompt file paths in DB is a security/secret-leak footgun

Dispatch config includes:

> “environment variables”

Scenario: API keys, tokens, credentials get persisted in SQLite + event logs.

**Fix direction:** explicitly define secret handling:

* disallow storing certain env keys
* store hashes/redacted values
* or store in OS secret store and reference by handle

---

### P2.8 — Multi-project “portfolio runs” doesn’t reconcile with “one DB per project”

> “`ic run create --projects=intercore,clavain …` creates a portfolio run with per-project scoping…”

If you maintain “one DB per project”, where does the **portfolio parent** record live? If it’s in one DB, you’re back to shared DB; if it’s in relay DB, that’s an OS/app service.

**Fix direction:** specify topology:

* portfolio lives in a dedicated “portfolio DB”
* or portfolio is an OS-layer projection built from per-project runs

---

### P2.9 — “Compliant driver registered” requires a registration/trust model that’s not defined

> “The kernel can refuse to dispatch without a compliant driver registered…”

Missing:

* how drivers register
* what “compliant” means
* how the kernel authenticates driver identity (especially given “callers are cooperative”)

**Fix direction:** add a minimal capability registry: driver name, version, declared features; OS chooses; kernel stores provenance.

---

### P2.10 — Several OS/app-specific terms appear without definition (open-source readability gap)

Examples:

> “bead metadata”

> “creates a "verify downstream" **bead**”

> `${SID}` in temp file examples

These are unexplained in this kernel doc, yet you later claim:

> “Documentation for strangers… for people who don't know what Clavain is…”

**Fix direction:** either define them (glossary) or remove them from kernel doc and keep in OS doc.

---

## P3 — Writing and editorial issues

### P3.1 — “Real magic” phrasing conflicts with “mechanism not policy” tone and repeats inconsistently

Two conflicting claims:

> “The **"real magic" lives here**: everything that matters is in `ic`”

vs

> “Plugins work in Claude Code, but the **real magic is in Clavain + Intercore**.”

**Fix direction:** drop “real magic” entirely; state capabilities/ownership plainly.

---

### P3.2 — “Interverse monorepo … each with its own git repository” is self-contradictory phrasing

> “The Interverse **monorepo** contains 25+ modules, each with its own git **repository**.”

**Fix direction:** pick one: monorepo (single repo) vs multi-repo workspace.

---

### P3.3 — Deep relative links make the kernel doc brittle

> “[Clavain vision doc](../../../../os/clavain/docs/clavain-vision.md)”

Kernel vision docs tend to get copied/read outside the repo layout; these paths will break.

**Fix direction:** use stable doc IDs/shortpaths or a docs site URL convention.

---

### P3.4 — Repetition: idempotency is described multiple times

You repeat the same concept in Events and again in Contracts:

> “**Idempotency:** Events carry a deduplication key…”

and later again:

> “### Idempotency
> Events carry a deduplication key…”

**Fix direction:** keep one authoritative description; reference it elsewhere.

---

## Highest-leverage rewrite recommendation (kernel doc hygiene)

If you want this doc to read as a true **kernel** spec (mechanism/primitives), the fastest structural improvement is:

1. **Front-load a strict boundary statement** (“kernel owns X/Y/Z; everything else is OS/app”).
2. **Move or demote** these into OS/app/profiler docs (or mark as “non-kernel future”):

   * discovery scoring algorithms, weights, profile learning, decay defaults
   * backlog semantics and rollbacks
   * git revert plan generation
   * TUI subcommand roadmap (`ic tui`)
   * dependency auto-verification reactions
3. **Resolve naming collisions**: “drivers/plugins” vs “dispatch runners”.
4. **Create a “Current vs Planned” capability matrix** and ensure every subsystem section matches it.

If you want, I can also propose **an edited outline** (reordering + what to cut/move) while keeping your content, but strictly enforcing Kernel → OS → Apps boundaries.
