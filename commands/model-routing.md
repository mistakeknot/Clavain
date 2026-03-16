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
