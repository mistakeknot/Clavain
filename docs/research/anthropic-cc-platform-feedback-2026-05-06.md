---
artifact_type: external-feedback-draft
audience: Anthropic Claude Code TMTS
source_method: flux-review (4 tracks, 16 agents)
source_synthesis: docs/research/flux-review/anthropic-cc-platform-gaps-sylveste/2026-05-06-synthesis.md
date: 2026-05-06
status: draft
bead: sylveste-mvaw
---

# Feedback for Claude Code — What to Build Natively to Deprecate the Sylveste Plugins

Distilled from a multi-track flux-review across the 63-plugin Sylveste/Interverse ecosystem (and 19 Clavain orchestration skills). The plugins are treated as a dataset — each one is evidence of a Claude Code primitive that's missing, mis-shaped, or write-only.

## TL;DR

> The seven primitives that look obvious aren't seven — they're seven instances of one missing substrate. **Ship the substrate first** (typed, durable, append-only evidence ledger with a registrar primitive), then sequence the rest in three tiers with stability flags, and explicitly resist absorbing four named ceilings.

## The meta-diagnosis

Claude Code ships **write-only primitives**: TodoWrite, TaskCreate, single-shot Agent, ephemeral session memory, MCP catalog with no telemetry on what worked. Sylveste's PHILOSOPHY.md says it directly: *"Every action produces evidence; evidence earns authority."* Anthropic ships the action half. Users build the evidence half. Sixty-three times.

OODA → OODARC. The Reflect-Compound back-half is what's missing. Five families of plugins exist because of this same gap.

---

## The substrate to ship first (4/4 cross-track convergence)

A typed, durable, append-only evidence ledger with a registrar primitive — `accession` / `quire` / `chain_for(id)`.

**Specification (composite of 4 tracks):**
- Single ID issued at the moment of any "action that produces evidence" (tool call, session boundary, agent dispatch, hook event, bead transition)
- Plugins record their own IDs alongside it; `chain_for(id)` returns the linked upstream chain
- Persisted append-only with: `{pre-state hash, post-state hash, evidence-chain, agent-id, source_class, as_observed_date, decay_rule, layer}`
- Content-addressed; signed at emission (not validated at retrieval); offline-verifiable; vendor-portable

**Named transfer mechanism:** Datomic `(append fact) / (observe scope as_of) / (subscribe predicate replay-from-event-id)` + Git refs+reflog + OpenTelemetry envelope shape.

**Why this is precondition.** Without it, every primitive Anthropic absorbs reinvents its own ID space and the integration matrix grows quadratically. With it, 8–12 plugins collapse into feeders. The "every action produces evidence" principle becomes enforceable rather than aspirational.

**Source convergence:**
- Track A (adjacent): typed durable event ledger that closes the OODARC loop
- Track B (orthogonal): host-mediated typed event bus, kernel "we never break userspace" stability contract
- Track C (distant): museum accession + `chain_for` query, Hanseatic standardized weights
- Track D (esoteric): Heian warifu split-tally certificate (authority at signature time, not verification time), Ifá canon-arbitrated divergence resolution

---

## Memory is not one primitive — decompose before absorbing (4/4 convergence)

The cleanest mechanism is the kernel VFS / DAW host-vs-instrument split. Track D adds the timing axis the others miss: training-time vs runtime is *additional to* the boundary-level split.

| Layer | Shape | Anthropic action |
|---|---|---|
| **1-League (substrate)** | accession + append log + `chain_for` | Ship native |
| **1-Kontor (project-scoped)** | AGENTS.md / CLAUDE.md / project rules | Cross-vendor format only — do NOT absorb internals |
| **1-Merchant (plugin-differentiated)** | Semantic retrieval, decay, embeddings | Do NOT absorb. This is where plugin authors compete. |
| **1b-Compilation (training-time)** | Absorbs declared content into agent baseline before first turn | Ship as a separate primitive |

**Eight plugins want the compilation primitive that doesn't exist:** intermem, interknow, interlearn, interlore, interfluence, interlens, interscribe, interseed. They currently fake it as runtime preamble — exactly the cost line the Sylveste 2,285-token preamble trim targeted.

**Marketplace shape inversion:** plugins aren't runtime-vs-native competitors, they're *compilable inputs* feeding a baseline. Structurally more defensible for Anthropic's marketplace than the current frame.

---

## The prior 7 as a single release cohort triggers the App Store Sherlock pattern (3/4 convergence)

~25 plugins displaced in one release cycle reads as Sherlock regardless of per-absorption justification. Author-attrition kills future absorption candidates.

### Sequence in three tiers, ship each with stability scaffolding

**Tier 1 — ship now (broad benefit, weak per-plugin differentiation):**
- Observability (#4) as canonical receipt format on the substrate
- AGENTS.md (#7) as **cross-vendor format only** (publish JSON-Schema + write protocol; do not absorb authoring)
- Durable task tracker (#6) — kill the TodoWrite/TaskCreate workaround pattern

**Tier 2 — ship after substrate convergence:**
- Multi-session file coordination (#3)

**Tier 3 — protocol/format only, NOT category absorption:**
- Memory (#1)
- Parallel-fleet **dispatch + finding-pipe** (subset of #2)
- Token-efficient code recon (#5) as tool-capability declaration, not algorithm

### Per-absorption shipping requirements (Track B kernel/browser/DAW/app-store)

1. `STABILITY.md` declaring stable surface vs internal API vs deprecation runway. Without it, plugin authors freeze in wait-and-see for 6–18 months.
2. `--enable-trial` for 2–3 release cycles before commitment (Origin Trials shape).
3. Two-implementation rule (WHATWG): a primitive is absorption-ready only when ≥2 substrate implementations have converged on a shape. Of the prior 7 — multi-session coordination, observability, AGENTS.md show convergence; memory, code recon, task tracker do not.
4. 3–5 named residual-niche statement per absorption (Sparkle survival template). Without it, plugin authors price in predation risk and stop building.
5. Default-app replacement (iOS keychain pattern): users can redirect "Claude task" to their preferred plugin even after native ships.

---

## Three primitives the prior pass entirely missed

1. **Marketplace UX as a primitive.** Sylveste built 5 plugins (interplug + interpub + interform + intercheck + parts of interskill) just to make CC's marketplace usable — discovery, ranking, trust signals, install metrics, dependency resolution, version compatibility. Unnamed gap.
2. **Tool-capability declaration.** No MCP/CC concept of "this tool returns code-aware excerpts at a token budget" vs "raw bytes." Cross-vendor primitive opportunity.
3. **Async session-resumption protocol.** CC's Task tool blocks the parent. Devin/Codex Cloud are async-by-default with session resumption (shipped 12+ months ago). LSP-shaped `initialize/shutdown`. Difference between "review 12 findings" (works) and "kick off a 6-hour refactor and come back" (doesn't).

## Two more primitives — single-track, unique, testable

1. **Corrections feed with cadence (`chart-issue`).** Track C portolan / Notice to Mariners. Weekly publication taking corrections from observability + reflect docs, propagating dated, monotonic, immutable corrections to every active session at session start. Required fields: `source_class (observed | inferred | synthesized)`, `as_observed_date`, `decay_rule`, hazard-marker permanence. Without cadence, OODARC's Reflect-Compound back-half is per-session and platform defaults silently drift across the fleet.
2. **Bani-stamp unification.** Track C Carnatic. interfluence + interlore are one primitive — durable lineage signature on persisted facts. Required fields: `layer (kriti | manodharma)`, `source_class`, `bani_stamp` (which agent/lineage emitted it). Cross-checks become automatic — an artifact stamped bani-X is rejected if it violates the bani.

---

## Hidden coupling — the load-bearing reframe

Three to four "independent" plugin clusters are actually one missing primitive in disguise:

- **Signed-decision artifacts** (warifu shape): interlock + intercept + intertrust + interspect — four implementations of authority-at-signature-time
- **Canon-arbitrated divergence** (Ifá shape): intermem + interpeer + intertrust + intermonk + interspect — five implementations of one integrated divergence-resolution protocol
- **Training-time compilation** (rebbelib shape): intermem + interknow + interlearn + interlore + interfluence + interlens + interscribe + interseed — eight implementations of one absent compilation primitive
- **Hook-bus subscribers**: interwatch + interject + interlearn + tool-time + intercept + interspect + interpath + interlore + parts of intermem — all subscribe to events Claude Code doesn't publish

intermem appears in three clusters; intertrust in two; interspect in three. The overlap is the finding: **a single integrated primitive with three faces — signed-decision artifacts that compile into baseline behavior and resolve divergence by canonical precedent.**

---

## Counter-arguments — what NOT to build natively

| NOT build | Tracks | Reasoning |
|---|---|---|
| Native code-recon ranking | A, C, B | No shape convergence (Aider/Cursor/Cody all differ); fails two-impl rule; herring-pricing seizure converts authors to competitors. Ship a tool-capability declaration + reference implementation. |
| Multi-agent synthesis policy | A, B | Three schools encode different scoring philosophies (Sylveste flux-drive ≠ Compound Engineering ≠ Superpowers). Absorbing collapses three to one. Ship the runner, not the workflow. |
| Voice/style as runtime API | A, C, D | Microsoft Word never absorbed Grammarly. No competitor ships voice as platform primitive. Voice + philosophy unify as one *training-time* primitive — feed the compilation, don't run a voice API. |
| AGENTS.md as runtime interpretation | D | A Codex user must be able to validate offline. Build cross-vendor file format + canonical compilation semantics; AGENTS.md remains inert at runtime. |
| Cognitive lens databases (FLUX 288, philosophy observers) | A, D | Pure content. Anthropic has no authority on FLUX's lenses or any project's PHILOSOPHY.md. A small compiled subset is the right shape. |
| Trust scoring as dashboard surface | C, D | Without compilation into routing-frequency consequence, the dashboard is theatrical. Specify trust as the consultation-frequency derivative, not the score itself. Citation chain is mandatory. |
| Memory hierarchy/graduation/decay as one primitive | A, B, C, D | All four tracks. Policy-bundling. Decompose per the 4-tier table above; absorb only the substrate. |

---

## Strategic / business-model angle

**The plugin ecosystem IS Anthropic's competitive moat against Cursor / Codex / Devin — not the model.** The model is commodity within ~6 months; the ecosystem is a multi-year accumulation that competitors cannot replicate quickly.

- **Absorbing the floor** (durable substrate, coordination capability, cost-receipt envelope, async sessions, hook-event schema, training-time compilation) is healthy.
- **Absorbing the ceiling** (synthesis policy, voice content, AGENTS.md authoring, ranked code recon, lens curation) trades a moated multi-year position for a quarterly feature win.

**The VSCode 2017–2019 lesson applied:** ship 50+ floor primitives (LSP, DAP, terminal, tasks, settings sync), leave ceilings to plugins. The marketplace **grew** to 10× competitors. Same playbook applies.

**Cross-vendor governance is itself a competitive lever.** AGENTS.md already touches Codex, Cursor, Gemini. The highest-leverage move is publishing a JSON-Schema + write protocol cross-vendor — a WHATWG-shape forum for agent platforms (Track B) — not absorbing authoring CC-internally.

---

## The five-of-seven MCP-shape (Track A, fd-mcp-protocol-architect)

Five of seven prior-pass primitives are MCP-shaped, not host-shaped:

| Primitive | MCP shape |
|---|---|
| Memory | `memory://` resource scheme + `memory` capability |
| Coordination | `coordination` capability + reference server (interlock-shaped) |
| Cost observability | tool-call response `_meta.cost` envelope |
| Parallel fleet | `sampling/createMessageBatch` extension |
| AGENTS.md | `resources/subscribe` with drift-staleness notifications |

**Framing them as host primitives creates permanent cross-host fragmentation** and locks Anthropic users in. A user with six months of curated memory cannot switch hosts — that's a moat *against* Anthropic among power users.

---

## The headline single sentence

> The prior 7 are scaffolding for one missing primitive — ship the substrate first (typed durable evidence ledger with `accession` + `chain_for`), reshape 5 of the remaining 7 as MCP-protocol moves rather than CC-host moves, sequence absorptions in 3 tiers with Origin-Trials-style stability flags, and explicitly DO NOT absorb four named ceilings.

---

## Appendix — per-plugin survival projection (post-absorption, if executed as recommended)

**Collapse cleanly into native** (~12 plugins): intermem, intercache, interflux dispatch layer, intersynth dispatch layer, intermux, interpulse, interphase task layer, interscribe drift-checks, parts of interlock, parts of intertrust, TodoWrite-replacement scope of beads, parts of interspect.

**Survive up-stack as differentiated layers on top of native floor** (~25 plugins): interknow, interspect (calibration), interstat (cost analytics), intercept (decision distillation), tool-time (analytics), tldr-swinton (algorithms), interwatch (drift signals), interscribe (progressive disclosure), interpath (artifact generation), internext (prioritization), interlearn (cross-repo), interleave (compile templates), interlab (campaign mutation), interbrowse, intersight, interdeep, interpeer (model diversity), intermonk (dialectic), and others.

**Survive forever as content / domain layer** (~15 plugins): interlens (288 FLUX), lattice, interlore (philosophy), interseed (idea garden), interfluence (voice), intersite, interchart, interfer (MLX), interkasten (Notion), interslack, intership, intername, tuivision, interform, intertrack.

**Become specifications cross-vendor rather than CC-internal** (~5): interdoc, parts of intermem (graduation), parts of intercheck (validators), interplug (lifecycle), interpub (publishing).

The outcome: ~12 plugins gracefully retire, ~40 plugins evolve up-stack onto a healthier substrate, and the marketplace continues to differentiate Anthropic from Cursor/Codex/Devin.
