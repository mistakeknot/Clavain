# Port the FLUXrig executor-routing doctrine to Clavain dispatch — brainstorm

**Origin:** FLUXrig proved a per-task-class executor-routing doctrine end to end
(beads FLUXrig-aeu, FLUXrig-7lv, FLUXrig-92u). Two parity evals, opposite
verdicts: bounded tagging → Kimi-first (100% coverage, 0 drops, faster); relation
inference → Luna-only (Kimi 7.7× slower, worse coverage+drops, tied quality).
**The load-bearing finding: parity on one task class does NOT transfer to
another.** This brainstorm ports that doctrine + its reusable harness into
Clavain's dispatch layer.

## What Clavain dispatch ALREADY has (grounded read, 2026-07-23)

- **Kimi is already a backend.** `dispatch.sh --to kimi` exists; `resolve_tier_model_kimi`
  maps tiers to kimi aliases (fast→kimi-for-coding, deep→k3). Introduced as a
  "second-opinion backend," NOT as a free-first executor with paid fallback.
- **Rich routing.yaml**: subagents (B1), complexity tiers C1-C5 (B2), calibration
  (B3), CC↔Codex delegation categories (B4), local-model free-first cascade (B5).
- **`lib-routing.sh`** resolves models by phase/category/complexity, with a tier
  `fallback` chain — but only *within* one backend (codex tiers), never *between*
  backends (kimi→codex).

## The three real gaps (what the doctrine adds)

1. **No free-first failover BETWEEN backends.** `--to kimi` and `--to codex` are
   manual, mutually exclusive; if `--to kimi` fails there is no fall-through to
   codex. FLUXrig's `_llm.run` ordered-fallback loop is exactly this missing piece.
2. **No task-class-pinned defaults grounded in a parity eval.** delegation
   categories exist but their routing is set by hand/calibration, not by a
   reproducible A/B that empirically decides "this class holds parity on the cheap
   tier."
3. **No parity-eval harness.** B3 calibration uses flux-drive verdict outcomes, not
   a controlled tiered-agreement + blind-quality-judge + explicit-threshold A/B.

## Design (decided with MK, 2026-07-23)

### D1 — Free-first failover lives in dispatch.sh's backend layer (`--to auto`)
- New `--to auto`: reads a per-class backend order from routing.yaml, runs the
  FLUXrig-style ordered failover (try backend 1; on quota/rate-limit/empty/nonzero
  → try backend 2 …). `--to kimi` / `--to codex` stay as explicit pins.
- **Why here, not a wrapper or config-only:** dispatch.sh is the single canonical
  entry point every skill + interserve calls — a second script (`dispatch-routed.sh`)
  would silently be missed by callers and drift. Config alone can't express runtime
  try/catch failover (catch a quota error, retry) — YAML declares the ORDER, shell
  runs the loop. Same split FLUXrig uses (_llm.py loop + _STAGE_DEFAULT config) and
  that routing.yaml already uses for tier fallback.

### D2 — Task-class = explicit `--class` flag, defaults SAFE (paid/stronger)
- New `--class <name>` (tagging | reasoning | …). Unmapped → the safe default
  order (codex-only). Cheap routing is **opt-in only after a parity eval**.
- **Why explicit, not inferred:** complexity ≠ task-class — typed_edges was
  LOW-complexity yet needed Luna, so complexity-inference would have mis-routed the
  exact case we proved. delegation.categories (exploration/implementation/…) don't
  map 1:1 to tagging-vs-reasoning (one "implementation" spans a mechanical rename
  AND a subtle algorithm). An explicit flag names what the eval actually measures.
- **The safe default is the point:** you never silently route reasoning to the
  cheap model; you only opt a class into the cheap tier after its parity eval
  passes. The "callers must set --class for savings" cost is a feature — it forces
  the eval to happen first.

### D3 — Carry the FLUXrig SECURITY fixes into Clavain's kimi backend (REQUIRED)
- Clavain's current `--to kimi` uses bare `kimi -p "$PROMPT"` — tools ENABLED and
  auto-approved, and the prompt passed as a bare arg (argv-injection surface).
  FLUXrig proved both are unsafe for untrusted input. The port MUST add: the
  restricted no-tools `--agent-file` profile (KIMI_CODE_EXPERIMENTAL_FLAG=1) and
  the `--prompt=<value>` binding, for `--to auto`/`--to kimi` when the prompt may
  be untrusted. (An explicit opt-out for trusted/interactive kimi use is fine.)

### D4 — Port the parity-eval harness as a reusable Clavain script
- `scripts/executor-parity-eval.sh` (+ a python core): run any task's prompts
  through two backends via dispatch.sh pinned per backend, compute tiered agreement
  (where the output is comparable) OR yield/coverage/drops (always), + a blind
  quality judge, + an explicit-threshold verdict. Generic over "prompt generator"
  so any pipeline can validate a cheaper executor for a task class before adopting.

## routing.yaml shape (new section)

```yaml
executor_routing:
  # backend order per task class; first that succeeds wins (free-first).
  # A class is added here ONLY after its parity eval passes (D2).
  mode: enforce            # off | shadow | enforce
  classes:
    tagging:   [kimi, codex]    # FLUXrig-aeu: Kimi holds parity
    reasoning: [codex]          # FLUXrig-92u: Luna-only (Kimi 7.7x slower)
  default:     [codex]          # safe: unmapped class -> paid/stronger
```

## Non-goals

- Not touching B1/B2/B3/B5 resolution (subagent/complexity/calibration/local) —
  this is a NEW orthogonal layer for the CLI-backend dimension.
- Not auto-classifying task-class from prompt content (explicit --class only).
- Not making kimi-first a global default — per-class, opt-in, safe-default.

## Success condition

A caller can `dispatch.sh --to auto --class tagging "…"` and get the free Kimi
backend with automatic codex fallback + the restricted safe sandbox; an unmapped
or reasoning class transparently uses codex; and `executor-parity-eval.sh` can
produce a verdict for a new class the same way the FLUXrig evals did.
