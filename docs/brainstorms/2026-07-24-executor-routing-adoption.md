# Adopt --to auto --class across Clavain dispatch call sites — brainstorm

**Bead:** Sylveste-<adopt> (follow-on to Sylveste-dnl / PR #24, merged 3540a36)
**Origin:** The executor-routing doctrine shipped to Clavain (--to auto + --class,
executor_routing config, parity-eval harness) but NOTHING calls it yet — a
proven-correct capability that is inert until call sites opt in. This goal wires
adoption so the free-first routing actually engages.

## Grounded read of the call sites (2026-07-24)

Most dispatch "call sites" are **skill INSTRUCTIONS**, not fixed scripts — Claude
builds the dispatch command by following interserve-engine / codex-delegate /
debate. So `--class` is threaded at the point where the skill already decides how
to dispatch, not hardcoded in shell.

- **interserve-engine** (SKILL.md Step 1) ALREADY classifies each task —
  "Independent implementation / Exploratory·research / Architecture-sensitive" —
  and routing.yaml `delegation.categories` already enumerates the taxonomy:
  exploration, implementation, review, test-generation, doc-update, architecture,
  brainstorm, interactive.
- **debate.sh** shells dispatch.sh directly (reasoning-heavy by nature).
- **codex-delegate** agent: well-scoped implementation/exploration/test/review.

## The taxonomy tension (the core design problem)

FLUXrig's parity evals classified on **tagging vs reasoning** (bounded
classification vs multi-step inference). Clavain's existing taxonomy is
**delegation.categories**. They don't line up cleanly — `implementation` spans a
mechanical rename (tagging-like) AND a subtle algorithm (reasoning). And
critically: **the FLUXrig verdicts were on FLUXrig's OWN prompts.** Clavain's
"test-generation" is a different task; parity does NOT transfer (the load-bearing
finding of the whole doctrine), so we cannot route Clavain classes to Kimi on
FLUXrig evidence.

## Decisions (with MK, 2026-07-24)

### D1 — Eval-gate every Clavain class; ship phase 1 in SHADOW
- **Phase 1:** wire `--class` at every call site + add an `executor_routing`
  shadow mode. Shadow LOGS what would route (`[executor-shadow] category=… →
  class=… → would-route=kimi`) but routes NOTHING to kimi — codex/safe default
  runs. Zero behavior change, pure instrumentation.
- **Phase 2 (separate goal, gated):** run `executor-parity-eval` on Clavain's
  ACTUAL per-class prompts; flip ONLY passing classes to enforce. No unproven
  kimi routing ever ships.
- **Why:** honors "parity does not transfer" — Clavain earns its own evidence.

### D2 — Map --class from the existing delegation categories
- One `category → class` lookup (in routing.yaml, read by lib-routing): the skill
  passes `--class` derived from the category interserve-engine ALREADY picked in
  its Step-1 classification. No new judgment, no per-skill taxonomy.
- Mapping (safe-biased — `implementation` spans both, so → reasoning):
  ```
  test-generation -> tagging      doc-update   -> tagging
  exploration     -> reasoning    implementation -> reasoning (safe)
  review          -> reasoning    architecture -> reasoning
  brainstorm      -> reasoning    interactive  -> reasoning
  ```
- `tagging`/`reasoning` stay the parity CLASSES (what evals verdict on);
  categories are the SOURCE. In shadow, even `tagging` routes to codex.

### D3 — Shadow logging reuses the B2/B5 pattern (and BUILDS the eval corpus)
- Clavain already logs `[B2-shadow]`/`[B5-shadow]` and reports via
  `routing-shadow-report.sh` (cass / /tmp grep). Add `[executor-shadow]` lines +
  an `executor-routing-shadow-report.sh`. **The shadow logs become the source of
  real Clavain prompts to sample for each class's phase-2 parity eval** — phase 1
  isn't just instrumentation, it produces the eval corpus.

## Scope this goal (phase 1 only)

1. `routing.yaml executor_routing`: add `mode: shadow` support + a
   `category_class_map` (D2 mapping).
2. `lib-routing.sh`: `routing_resolve_class_for_category <category>` (lookup) and
   shadow logging in the executor-order path.
3. dispatch.sh: accept `--class` already (shipped); in shadow, log the
   would-route decision, run the safe backend.
4. interserve-engine SKILL: after Step-1 classification, pass `--class <mapped>`.
5. `executor-routing-shadow-report.sh`: per-class volume + would-route summary.
6. Tests: category→class mapping, shadow logs-but-routes-safe, report parses.

## Non-goals (explicitly phase 2+)

- Flipping ANY class to enforce (needs a Clavain parity eval first).
- Per-skill explicit --class edits beyond interserve-engine (the highest-volume
  path); other skills adopt once the category map is proven.
- Sub-classifying `implementation` into mechanical-vs-reasoning (stays safe).

## Success condition

Every interserve-engine dispatch logs an `[executor-shadow]` would-route line
derived from its own task classification; the report shows per-class volume;
NOTHING routes to kimi yet; and the accumulated shadow corpus is ready to feed a
phase-2 parity eval per class.
