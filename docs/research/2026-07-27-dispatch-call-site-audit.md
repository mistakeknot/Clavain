---
artifact_type: research
bead: Sylveste-d3m
stage: verification
---
# dispatch.sh call-site audit — `--to auto --class` adoption

**Date:** 2026-07-27
**Bead:** Sylveste-d3m (follow-on to Sylveste-dnl, PR #24)
**Seal:** a528af04fdd614f6 — all 7 acceptance criteria pass.

Completes the C4–C7 verification interrupted mid-run, and audits every dispatch.sh
call site for `--to auto --class` adoption.

---

## 1. Shadow invariant — verified

The invariant under test: *shadow mode logs the would-route decision while routing
nothing new to kimi.*

| Class | Shadow line | Dispatched command | Real kimi invocation |
|---|---|---|---|
| `tagging` | `class=tagging would-route=kimi codex routed=codex` | `codex exec` | none |
| `reasoning` | `class=reasoning would-route=codex routed=codex` | `codex exec` | none |
| unmapped | `class=<x> would-route=codex routed=codex` | `codex exec` | none |

Verified against the command body with the shadow log line stripped. This matters:
the log line itself contains the literal `would-route=kimi codex`, so any assertion
that greps the whole output for `kimi` passes even when nothing is dispatched to kimi.
Criterion 4's third clause (`grep -qv "kimi --agent-file"`) is additionally weak —
`grep -v` exits 0 whenever *any* line fails to match, so it is satisfied
unconditionally. Left as sealed; a strict assertion was added alongside it in
`tests/routing/executor-adoption-test.sh`.

## 2. Defect found: the adopted call site never entered the shadow path

`--class` is only read when `ENGINE == "auto"` (`dispatch.sh:918`); the default is
`codex` (`dispatch.sh:18`). interserve-engine — the only adopted call site — passed
`--class "$CLASS"` but never `--to auto`, so `routing_resolve_executor_order` was
never reached from production.

Consequence: **zero `[executor-shadow]` lines would ever be recorded**, and phase 1's
stated purpose ("building the corpus for the phase-2 per-class parity evals") would
have produced an empty corpus. Phase 2 would have had nothing to score.

All seven criteria passed anyway — C4 supplies `--to auto` by hand (proving the
mechanism, not the wiring) and C5 only greps SKILL.md for `--class`.

The sealed plan's own Key Links specify the full chain:

> interserve-engine category → `routing_resolve_class_for_category` → `--class` →
> dispatch.sh `--to auto` → `routing_resolve_executor_order` (shadow-aware)

Fixing it is conformance to the plan, not scope expansion. Both SKILL variants now
pass `--to auto --class`, and the adoption suite pins both halves.

## 3. Defect found: `mode: off` inverted the kill switch into enforce

YAML 1.1 parses a bare `mode: off` as the boolean `False` — the exact literal named
in routing.yaml's own comment (`# off | shadow | enforce`). `lib-routing.sh` compared
the raw value against `"off"` then `"shadow"`, missed both, and fell through to
`else: # enforce`.

Setting the documented kill switch therefore **enabled full enforcement and really
did invoke kimi**:

```
mode: off  →  parsed=False  →  resolver='kimi codex'  →  kimi --agent-file … --prompt=hi
```

Worst possible failure direction: the operator's "stop routing" lever turned on live
free-executor routing. `on`/`yes`/`no` had the same shape.

Fixed by normalizing the value and failing safe — anything unrecognized disables
routing. Post-fix behavior:

| `mode:` | Parsed | Resolver | Real kimi invocations |
|---|---|---|---|
| `off` | `False` | *(bypassed)* | 0 |
| `on` | `True` | *(bypassed)* | 0 |
| `bogus` | `'bogus'` | *(bypassed)* | 0 |
| `"off"` | `'off'` | *(bypassed)* | 0 |
| `shadow` | `'shadow'` | `codex` | 0 |
| `enforce` | `'enforce'` | `kimi codex` | 1 *(correct)* |

## 4. Stale test on this branch

`tests/routing/executor-routing-test.sh` still asserted the pre-shadow expectation
(`tagging → "kimi codex"`), which phase 1 invalidated by flipping the default to
shadow. The branch shipped a red suite — confirmed failing at committed HEAD, before
any change in this PR. Its `contains "$tagging" "kimi"` assertion was also vacuous
for the log-line reason above.

Rewritten to be mode-aware (asserts per `off`/`shadow`/`enforce`), so it survives the
phase-2 flip to enforce instead of needing another edit.

## 5. Call-site audit

Adoption status of every dispatch.sh call site. Phase 1's sealed scope is
interserve-engine only; the rest are recorded here as phase-2 candidates, not changed.

| Call site | Kind | `--to auto` | `--class` | Feeds shadow corpus | Disposition |
|---|---|---|---|---|---|
| `skills/interserve-engine/SKILL.md` | skill doc | ✅ *(fixed)* | ✅ | ✅ | **adopted** |
| `skills/interserve-engine/SKILL-compact.md` | compact variant | ✅ *(added)* | ✅ *(added)* | ✅ | **adopted** |
| `agents/workflow/codex-delegate.md` | agent doc | ❌ | ❌ | ❌ | phase-2 candidate |
| `skills/codex-delegate/SKILL.md` | skill doc | ❌ | ❌ | ❌ | phase-2 candidate |
| `scripts/debate.sh` (round 1) | shell | ❌ | ❌ | ❌ | phase-2 candidate |
| `scripts/debate.sh` (round 2) | shell | ❌ | ❌ | ❌ | phase-2 candidate |
| `scripts/orchestrate.py` `_dispatch_task` | python | ❌ | ❌ | ❌ | phase-2 candidate |
| `scripts/executor-parity-eval.py` | eval harness | passes `--to` explicitly | n/a | n/a | out of scope |
| `tests/routing/*` | tests | explicit | explicit | n/a | out of scope |

`SKILL-compact.md` is the material half of the interserve-engine finding: it is the
variant loaded in compact-context mode and had no `--class` guidance at all, so
adoption was conditional on which variant the agent had in context.

### Phase-2 effort notes

- **codex-delegate** (agent + skill) — the two dispatch blocks are identical to
  interserve-engine's. Same one-line change, but no category is classified upstream;
  a category step must be added first, or a fixed class pinned.
- **debate.sh** — both rounds are `-s read-only` adversarial review. `review` maps to
  `reasoning` → `[codex]`, so adoption adds shadow-corpus rows and changes no routing.
  Lowest-risk adoption of the three.
- **orchestrate.py** — `Task` carries `stage`, `tier`, `files`; no `category` field.
  Needs either a `stage → category` map or a new field, so it is the largest of the
  three.

Volume ranking is unknown until shadow data accumulates — which, per §2, has been
zero to date. Recommend adopting debate.sh next (cheapest, zero routing change),
then re-reading the shadow report before touching orchestrate.py.

## 6. Verification transcript

```
C1: MAP_OK              routing.yaml declares shadow + category→class map
C2: CAT_OK              category resolver; unmapped → reasoning
C3: SHADOW_OK           shadow logs would-route, returns safe order
C4: DISPATCH_SHADOW_OK  --to auto --class tagging → shadow line + codex
C5: SKILL_OK            interserve-engine passes --class
C6: REPORT_OK           shadow report tallies per class
C7: TESTS_OK            adoption suite passes
```

Additional checks beyond the seal:

```
shadow invariant, command body only     tagging/reasoning/unmapped → 0 kimi invocations
--class without --to auto               no shadow line (the §2 defect, now pinned)
mode normalization                      off/on/yes/no/bogus/"off" → bypassed; enforce → kimi codex
negative control                        reverting the lib-routing fix fails the new test
executor-routing-test.sh                PASS under shadow and enforce
```

No real codex/kimi/claude backend was invoked anywhere in this verification —
all checks are `--dry-run`, sourced-function, or fixture-based.
