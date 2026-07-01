---
name: model-routing
description: Toggle subagent model routing between economy (smart defaults) and quality (all opus) mode
argument-hint: "[economy|quality|status]"
---

# Model Routing

<routing_arg> #$ARGUMENTS </routing_arg>

Single source of truth: `config/routing.yaml`.

## `status` (default)

Source `scripts/lib-routing.sh`, call `routing_list_mappings`. Inspect `config/routing.yaml`:
- `defaults.model=sonnet` + economy categories → **economy**
- `defaults.model=opus` + all categories opus → **quality**
- Otherwise → **custom**

Show only phases/categories that deviate from default:
```
Mode: economy
Defaults: research: haiku | review: sonnet | workflow: sonnet | synthesis: haiku
Phase overrides:
  brainstorm: opus (all categories)
```

## `economy`

Cost-optimized defaults: research→haiku, review→sonnet, workflow→sonnet, synthesis→haiku. Brainstorm stays on opus.

```bash
sed -i '/^subagents:/,/^dispatch:/{
  /^  defaults:/,/^  phases:/{
    s/^\(    model:\).*/\1 sonnet/
    /^    categories:/,/^  [a-z]/{
      s/^\(      research:\).*/\1 haiku/
      s/^\(      review:\).*/\1 sonnet/
      s/^\(      workflow:\).*/\1 sonnet/
      s/^\(      synthesis:\).*/\1 haiku/
    }
  }
}' config/routing.yaml

sed -i '/^  phases:/,/^dispatch:/{
  /^\(      model:\).*/s//\1 sonnet/
  /brainstorm:/{n;s/^\(      model:\).*/\1 opus/}
}' config/routing.yaml
```

## `quality`

All agents on opus. Set defaults, then all phase models and category overrides to `inherit`.

```bash
sed -i '/^subagents:/,/^dispatch:/{
  /^  defaults:/,/^  phases:/{
    s/^\(    model:\).*/\1 opus/
    /^    categories:/,/^  [a-z]/{
      s/^\(      research:\).*/\1 opus/
      s/^\(      review:\).*/\1 opus/
      s/^\(      workflow:\).*/\1 opus/
      s/^\(      synthesis:\).*/\1 opus/
    }
  }
}' config/routing.yaml

sed -i '/^  phases:/,/^dispatch:/{ s/^\(      model:\).*/\1 inherit/ }' config/routing.yaml

sed -i '/^  phases:/,/^dispatch:/{ /^        [a-z].*:/{ s/^\(        [a-z][a-z0-9_-]*:\).*/\1 inherit/ } }' config/routing.yaml
```

## Notes

- Takes effect immediately for new dispatches; does not affect running agents
- Economy saves ~5x on research, ~3x on review vs quality
- Individual agents overrideable via `model: <tier>` in Task call
- `fd-safety` and `fd-correctness` always resolve to ≥sonnet regardless of mode (enforced by `agent-roles.yaml`)

## Capability-routing doctrine (frontier-tier sessions)

When a frontier-tier model (fable) is available — especially during a limited window — its capacity is the scarce resource. Route by capability, not habit:

| Role | Tier | Why |
|------|------|-----|
| Planning, plan review (/flux-review), architecture, cross-repo synthesis | fable | Small token volume, maximum downstream leverage — a bad plan multiplies cost through every later stage |
| Execution of execution-grade plans | sonnet | Bulk of token volume; near-opus on coding/agentic; ~5x cheaper than fable |
| Validation of execution | opus | Verification asymmetry: checking against explicit criteria is cheaper than producing the work — but only if criteria exist |
| Escalation target | fable | See two-strikes rule below |

**Rules:**

1. **Validators check against the plan's acceptance criteria** (`<verify>` blocks, Must-Haves), never their own judgment. The plan author writes the criteria at plan time; the validator only confirms them.
2. **Two-strikes escalation:** executor fails a task 2x, or validator rejects 2x → escalate the item to the frontier tier and record the failure mode. Never loop cheap retries — they aren't cheap.
3. **Hard-problem exception:** work that previously stalled on lesser models does NOT get the split — the frontier model stays in the execution loop or reviews every diff itself. A validator can only catch what it can understand.
4. **Small-task lane:** tasks under ~30 min of agent time skip the pipeline; one model end-to-end. Handoff overhead exceeds the savings.
5. **Plans are written for a weaker executor** — the pipeline's silent failure mode is a plan that assumes frontier judgment. `writing-plans` already enforces exact paths, complete code, and machine-checkable verify blocks; do not relax those when the plan author is a frontier model.
6. **Pilot before batching:** before fanning a plan backlog out to cheap executors, run 2-3 items through the full loop (plan → review → execute → validate → land) and fix the plan template while the frontier model is still available.
7. **Measure plan→execution pass rate** (interspect delegation calibration), not just shipped count — it's the signal that the doctrine is holding.
