# Plan: Wire Domain Detection into Flux-Drive Runtime

**Bead:** Clavain-7mpd (Domain-aware flux-drive)
**Status:** Domain detection script complete, profiles populated. Now wiring into runtime.
**Scope:** Connect detect-domains.py output to agent prompt injection in flux-drive Phase 2.

## Problem

Domain detection runs (Step 1.0a) and produces domains with confidence scores. Domain profiles exist (11 fully populated). Agent scoring uses domain bonuses (+1). But **agents never see the domain-specific review bullets**. The domain profiles' injection criteria sections are never loaded or injected into agent prompts.

## Changes

### 1. Add Step 2.1a to launch.md — Load Domain Profiles

After knowledge retrieval (Step 2.1) and before agent dispatch (Step 2.2), add a step that:

1. Reads detected domains from the document profile (passed through from Phase 1)
2. For each detected domain, reads the corresponding profile file: `${CLAUDE_PLUGIN_ROOT}/config/flux-drive/domains/{domain-name}.md`
3. For each selected agent, extracts the matching `### fd-{agent-name}` section from the Injection Criteria
4. Stores the extracted bullets as `{DOMAIN_CONTEXT}` per agent

**Key design decisions:**
- Inject criteria from ALL detected domains (not just primary) — a game server project should get both game-simulation and web-api bullets
- Order by confidence (primary domain first)
- Cap at 3 domains to prevent prompt bloat
- If no domains detected, skip injection (empty domain context)

### 2. Expand prompt template in launch.md — Add Domain Context section

Insert a new `## Domain Context` section in the prompt template between "Knowledge Context" and "Project Context" (around line 230):

```markdown
## Domain Context

[If domains were detected:]
This project is classified as: {domain1} ({confidence}), {domain2} ({confidence}), ...

Additional review criteria for your domain ({agent-name}) in these project types:

### {domain1-name}
- {bullet 1 from domain profile's ### fd-{agent} section}
- {bullet 2}
- ...

### {domain2-name} (if applicable)
- {bullet 1}
- ...

Apply these criteria in addition to your standard review approach. They highlight common issues specific to this project type.

[If no domains detected:]
No domain classification available — apply general review criteria only.
```

### 3. Update SKILL.md domain bonus documentation

In Step 1.2 scoring, update the domain bonus description to mention that injection criteria are now loaded during Phase 2 launch (not just scoring bonuses). Change the "Future domain profiles" comment to reflect current state.

### 4. Verify with tests

Run `uv run pytest tests/structural/ -x -q` — ensure no structural tests break.

## Files Modified

| File | Change |
|------|--------|
| `skills/flux-drive/phases/launch.md` | Add Step 2.1a (domain profile loading), expand prompt template with Domain Context section |
| `skills/flux-drive/SKILL.md` | Update Step 1.2 domain bonus docs to reference runtime injection |

## Not in Scope

- `/flux-gen` command (separate bead Clavain-8l91)
- Domain detection script changes (already complete)
- New domain profiles (Phase B already complete)
- Cross-AI phase changes (domain context doesn't affect Oracle prompts)
