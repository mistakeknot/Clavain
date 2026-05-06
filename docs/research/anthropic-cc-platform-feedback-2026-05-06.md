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

Distilled from a multi-track flux-review across the 63 Sylveste plugins and 19 Clavain orchestration skills that compose them. Each plugin is treated as evidence of a Claude Code primitive that is missing, mis-shaped, or write-only.

## TL;DR

> The seven primitives in the prior pass collapse into one missing substrate. Ship that first (a typed, durable, append-only evidence ledger with a registrar primitive), frame five of the seven as MCP capabilities, sequence the rest in three tiers with Origin-Trials-style stability flags, and leave four named ceilings to the marketplace.

## The meta-diagnosis

Claude Code ships write-only primitives: TodoWrite, TaskCreate, single-shot Agent, ephemeral session memory, an MCP catalog with no telemetry on what worked. Sylveste's PHILOSOPHY.md states the design bet directly: *"Every action produces evidence; evidence earns authority."* Anthropic ships the act half; the sixty-three plugins in this dataset are users building the reflect-compound half.

---

## 1. The substrate to ship first (4/4 cross-track convergence)

A typed, durable, append-only evidence ledger with a registrar primitive — `accession` / `quire` / `chain_for(id)`.

**Specification:**

- Single ID issued at any action that produces evidence: tool call, session boundary, agent dispatch, hook event, bead transition.
- Plugins record their own IDs alongside it; `chain_for(id)` returns the linked upstream chain.
- Append-only, with `{pre-state hash, post-state hash, evidence-chain, agent-id, source_class, as_observed_date, decay_rule, layer}`.
- Content-addressed, signed at emission, offline-verifiable, vendor-portable.
- Transfer mechanism: Datomic `(append fact) / (observe scope as_of) / (subscribe predicate replay-from-event-id)`, plus Git refs+reflog and OpenTelemetry's envelope shape.

**Why first.** Without the substrate, every absorption reinvents its own ID space and the integration matrix grows quadratically. With it, 8–12 plugins collapse into feeders, and the principle *"every action produces evidence"* becomes enforceable.

Four independent tracks named the same primitive from different vocabularies: typed durable event ledger (adjacent), host-mediated typed event bus (orthogonal), museum accession with `chain_for` query (distant), Heian warifu split-tally with Ifá canon-arbitrated divergence resolution (esoteric).

---

## 2. Memory is four primitives — decompose before absorbing (4/4)

| Layer | Shape | Action |
|---|---|---|
| **1-League (substrate)** | accession + append log + `chain_for` | Ship native |
| **1-Kontor (project-scoped)** | AGENTS.md / CLAUDE.md / project rules | Cross-vendor format only |
| **1-Merchant (plugin-differentiated)** | Semantic retrieval, decay rules, embeddings | Plugin territory |
| **1b-Compilation (training-time)** | Absorb declared content into agent baseline before first turn | Ship as a separate primitive |

The esoteric track adds the timing axis the others miss: training-time and runtime are independent decomposition axes from the boundary-level split.

Eight plugins want a compilation primitive: intermem, interknow, interlearn, interlore, interfluence, interlens, interscribe, interseed. They fake it as runtime preamble today, which is exactly the cost line Sylveste's 2,285-token preamble trim targeted.

**Marketplace shape inversion.** Plugins are compilable inputs awaiting a baseline.

---

## 3. The prior 7 as a single release cohort triggers the Sherlock pattern (3/4)

Roughly 25 plugins displaced in one release cycle reads as predation regardless of per-absorption justification. Author-attrition kills future absorption candidates.

**Tier 1 — ship now (broad benefit, weak per-plugin differentiation):**
- Observability (#4) as a canonical receipt format on the substrate
- AGENTS.md (#7) as a cross-vendor file format: publish a JSON-Schema and a write protocol; leave authoring to the marketplace
- Durable task tracker (#6) to retire the TodoWrite/TaskCreate workaround

**Tier 2 — ship after substrate convergence:**
- Multi-session file coordination (#3)

**Tier 3 — protocol or format only; the category itself stays in the marketplace:**
- Memory (#1)
- Parallel-fleet dispatch and finding-pipe (subset of #2)
- Token-efficient code recon (#5) as a tool-capability declaration that plugins implement

### Per-absorption shipping requirements

1. `STABILITY.md` declaring stable surface vs internal API vs deprecation runway. Without it, plugin authors freeze in wait-and-see for 6–18 months.
2. `--enable-trial` for 2–3 release cycles before commitment (Origin Trials shape).
3. WHATWG two-implementation rule. Absorption-ready only when ≥2 substrate implementations have converged on a shape. Of the prior 7, only coordination, observability, and AGENTS.md show convergence; memory, code recon, and task tracker do not.
4. A named 3–5-item residual-niche statement per absorption (Sparkle survival template) so plugin authors stay invested instead of pricing in predation risk.
5. Default-app replacement (iOS keychain pattern). Users redirect "Claude task" to their preferred plugin even after native ships.

---

## 4. Three primitives the prior pass entirely missed

1. **Marketplace UX.** Sylveste built five plugins — interplug, interpub, interform, intercheck, parts of interskill — just to make CC's marketplace usable: discovery, ranking, trust signals, install metrics, dependency resolution, version compatibility.
2. **Tool-capability declaration.** No MCP/CC concept of "this tool returns code-aware excerpts at a token budget" vs. "raw bytes." Cross-vendor primitive opportunity.
3. **Async session-resumption protocol.** CC's Task tool blocks the parent; Devin and Codex Cloud shipped async-by-default with session resumption 12+ months ago. LSP-shaped `initialize/shutdown`. Sync handles short fan-outs; anything that wants to kick off a 6-hour refactor and come back to it later needs detach and resume.

## 5. Two more — single-track, unique, testable

1. **Corrections feed with cadence (`chart-issue`).** Notice-to-Mariners shape. Weekly publication taking corrections from observability and reflect docs, propagating dated, monotonic, immutable corrections to every active session at session start. Required fields: `source_class (observed | inferred | synthesized)`, `as_observed_date`, `decay_rule`. Without cadence, the reflect-compound back-half is per-session and platform defaults silently drift across the fleet.
2. **Bani-stamp unification.** interfluence and interlore are one primitive: a durable lineage signature on persisted facts. Required fields: `layer (kriti | manodharma)`, `source_class`, `bani_stamp`. An artifact stamped bani-X is rejected automatically if it violates the bani, so cross-checks no longer need a separate review pass.

---

## 6. Hidden coupling — the load-bearing reframe

Four plugin clusters encode the same missing primitive:

- **Signed-decision artifacts** (warifu shape): interlock + intercept + intertrust + interspect — four implementations of authority-at-signature-time.
- **Canon-arbitrated divergence** (Ifá shape): intermem + interpeer + intertrust + intermonk + interspect — five implementations of one integrated divergence-resolution protocol.
- **Training-time compilation** (rebbelib shape): intermem + interknow + interlearn + interlore + interfluence + interlens + interscribe + interseed — eight implementations of one absent compilation primitive.
- **Hook-bus subscribers**: interwatch + interject + interlearn + tool-time + intercept + interspect + interpath + interlore + parts of intermem — all wait on an event stream Anthropic has yet to expose.

intermem appears in three clusters; intertrust in two; interspect in three. **The single integrated primitive has three faces: signed-decision artifacts that compile into baseline behavior and resolve divergence by canonical precedent.**

---

## 7. What stays in the marketplace

The counter-arguments. Each row is a primitive that looks tempting to absorb and shouldn't be.

| Stays in the marketplace | Reasoning |
|---|---|
| Native code-recon ranking | Aider, Cursor, and Cody have all shipped different shapes; the space has not converged enough for the two-impl rule. Absorbing here turns plugin authors into competitors against a free first-party. Ship a tool-capability declaration plus a reference implementation. |
| Multi-agent synthesis policy | Three schools encode different scoring philosophies (Sylveste flux-drive ≠ Compound Engineering ≠ Superpowers). Absorbing collapses three to one. Ship the dispatch runner and structured-finding pipe; let plugins ship the synthesis algorithms. |
| Voice/style as runtime API | Word never absorbed Grammarly. Voice and philosophy unify as a single training-time commitment, fed into the compilation primitive in §2. |
| AGENTS.md as runtime interpretation | A Codex user must validate offline. Build the cross-vendor file format and canonical compilation semantics; the file itself stays inert at runtime. |
| Cognitive-lens databases (FLUX 288, philosophy observers) | Pure content. Anthropic has no authority on FLUX's lenses or any project's PHILOSOPHY.md. A small compiled subset is the right shape. |
| Trust scoring as dashboard surface | Without compilation into routing-frequency consequence, the dashboard is theatrical. Specify trust as the consultation-frequency derivative; require citation chains as a first-class field. |
| Memory hierarchy/graduation/decay as one primitive | Policy-bundling. Decompose per §2; absorb only the substrate tier. |

---

## 8. Strategic / business-model angle

Models commoditize within ~6 months. The plugin ecosystem accumulates over years, and that accumulation is what moats Anthropic against Cursor, Codex, and Devin.

- **Absorb the floor** — durable substrate, coordination capability, cost-receipt envelope, async sessions, hook-event schema, training-time compilation. Healthy.
- **Absorb the ceiling** — synthesis policy, voice content, AGENTS.md authoring, ranked code recon, lens curation. Trades a multi-year moat for a quarterly feature win.

**The VSCode 2017–2019 lesson.** Ship 50+ floor primitives (LSP, DAP, terminal, tasks, settings sync); leave the ceilings to plugins. The marketplace grew to 10× competitors. The same playbook applies here.

**Cross-vendor governance is itself a competitive lever.** AGENTS.md already touches Codex, Cursor, and Gemini. Publishing a JSON-Schema and write protocol cross-vendor (a WHATWG-shape forum for agent platforms) claims three wins at once: standards leadership, switching-cost economics, and a quality bar across the field that Anthropic helped set.

---

## 9. Five of seven primitives belong in MCP

| Primitive | MCP shape |
|---|---|
| Memory | `memory://` resource scheme + `memory` capability |
| Coordination | `coordination` capability + reference server (interlock-shaped) |
| Cost observability | tool-call response `_meta.cost` envelope |
| Parallel fleet | `sampling/createMessageBatch` extension |
| AGENTS.md | `resources/subscribe` with drift-staleness notifications |

Framing these as host primitives creates permanent cross-host fragmentation and locks Anthropic users in. Six months of curated memory becomes a switching cost users hold over the host, which works against Anthropic among the power users most likely to evangelize.

---

## Appendix — per-plugin survival projection

If executed as recommended:

**Collapse cleanly into native (~12):** intermem, intercache, interflux dispatch layer, intersynth dispatch layer, intermux, interpulse, interphase task layer, interscribe drift-checks, parts of interlock, parts of intertrust, TodoWrite-replacement scope of beads, parts of interspect.

**Survive up-stack as differentiated layers on the native floor (~25):** interknow, interspect (calibration), interstat (cost analytics), intercept (decision distillation), tool-time (analytics), tldr-swinton (algorithms), interwatch (drift signals), interscribe (progressive disclosure), interpath (artifact generation), internext (prioritization), interlearn (cross-repo), interleave (compile templates), interlab (campaign mutation), interbrowse, intersight, interdeep, interpeer (model diversity), intermonk (dialectic).

**Survive forever as content / domain layer (~15):** interlens (288 FLUX), lattice, interlore (philosophy), interseed (idea garden), interfluence (voice), intersite, interchart, interfer (MLX), interkasten (Notion), interslack, intership, intername, tuivision, interform, intertrack.

**Become cross-vendor specifications (~5):** interdoc, parts of intermem (graduation), parts of intercheck (validators), interplug (lifecycle), interpub (publishing).

Net outcome: ~12 plugins gracefully retire, ~40 evolve up-stack onto a healthier substrate, and the marketplace continues to differentiate Anthropic from Cursor, Codex, and Devin.
