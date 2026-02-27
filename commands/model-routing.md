---
name: model-routing
description: Toggle subagent model routing between economy (smart defaults) and quality (all opus) mode
argument-hint: "[economy|quality|status]"
---

# Model Routing

Toggle how subagents pick their model tier. Reads from `config/routing.yaml` — the single source of truth for all model routing policy.

## Current Mode

<routing_arg> #$ARGUMENTS </routing_arg>

### `status` (or no argument)

Source `scripts/lib-routing.sh` and call `routing_list_mappings` to show the full routing table.

Determine the mode label by inspecting `config/routing.yaml`:
- If `defaults.model` is `sonnet` and categories match economy defaults → **economy**
- If `defaults.model` is `opus` and all categories are `opus` → **quality**
- Otherwise → **custom**

Display phase overrides that differ from the default model. Only show phases where the model or a category override deviates.

Output format:

```
Mode: economy

Defaults:
  research: haiku | review: sonnet | workflow: sonnet | synthesis: haiku

Phase overrides:
  brainstorm:          opus (all categories)
```

### `economy` (default)

Set smart defaults optimized for cost:

| Category | Model | Rationale |
|----------|-------|-----------|
| Research | `haiku` | Grep, read, summarize — doesn't need reasoning |
| Review | `sonnet` | Structured analysis with good judgment |
| Workflow | `sonnet` | Code changes need reliable execution |
| Synthesis | `haiku` | Aggregation tasks — pattern matching, not reasoning |

Update `config/routing.yaml` subagents defaults section:

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
```

Also reset all phase models to their standard economy values:

```bash
sed -i '/^  phases:/,/^dispatch:/{
  /^\(      model:\).*/s//\1 sonnet/
  /brainstorm:/{n;s/^\(      model:\).*/\1 opus/}
}' config/routing.yaml
```

Only brainstorm stays on opus — brainstorm-reviewed and strategized use sonnet (structured analysis, not creative generation).

### `quality`

Maximum quality — all resolution paths return `opus`:

Update `config/routing.yaml`:

1. Set all defaults to `opus`:

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
```

2. Set all phase models to `inherit` (so defaults.model=opus flows through):

```bash
sed -i '/^  phases:/,/^dispatch:/{
  s/^\(      model:\).*/\1 inherit/
}' config/routing.yaml
```

3. Set all phase category overrides to `inherit`:

```bash
sed -i '/^  phases:/,/^dispatch:/{
  /^        [a-z].*:/{
    s/^\(        [a-z][a-z0-9_-]*:\).*/\1 inherit/
  }
}' config/routing.yaml
```

**Result:** `resolve_model` at any phase + category returns `opus` (via inherit → defaults.model=opus fallback chain).

**Use when:** Critical reviews, production deployments, complex architectural decisions where you want maximum reasoning on every agent.

## Important

- Changes take effect immediately for new agent dispatches in this session
- Does not affect agents already running
- Economy mode saves ~5x on research and ~3x on review vs. quality mode
- Individual agents can still be overridden with `model: <tier>` in the Task tool call
- `config/routing.yaml` is the single source of truth — no agent frontmatter involved
