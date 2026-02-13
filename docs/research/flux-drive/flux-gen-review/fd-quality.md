### Findings Index
- P1 | P1-1 | "Template Output" | Repetitive boilerplate in Key Review Areas reduces prompt effectiveness
- P2 | P2-1 | "Template Design" | Generic instruction suffix prevents agent specialization
- IMP | IMP-1 | "Description Quality" | Command description could be more specific about when to use
- IMP | IMP-2 | "User Guidance" | Missing guidance on when NOT to use flux-gen
- IMP | IMP-3 | "Template Output" | Missing concrete examples in agent prompts
- IMP | IMP-4 | "Confirmation UX" | Option labels could be clearer about what gets overwritten
Verdict: needs-changes

### Summary

The command definition is well-structured with clear steps and good separation of concerns. However, the generated agent output suffers from repetitive boilerplate that undermines the domain-specific value. Each of the 5 "Key review areas" bullets ends with identical text ("Examine this aspect carefully. Look for concrete evidence in the code or document. Flag specific issues with file paths and line numbers where possible."), creating 5 lines of duplicate instructions per agent. This wastes tokens and reduces prompt specificity — the generic suffix applies to ALL review work, not the specific domain expertise these agents should provide.

The template design itself prevents specialization: the suffix is hardcoded in the template (line 86), not derived from domain profile content. This means every generated agent, regardless of domain (game-simulation, web-api, embedded-systems), gets identical meta-instructions that don't reflect domain-specific review techniques.

Minor improvements needed in user-facing guidance (when to use the command, what gets overwritten) and output quality (concrete examples missing from agent prompts).

### Issues Found

**P1-1: Repetitive boilerplate in Key Review Areas reduces prompt effectiveness**
Location: commands/flux-gen.md lines 85-86, affects .claude/agents/fd-plugin-structure.md lines 22-26 and fd-prompt-engineering.md lines 22-26

Each of the 5 Key review areas bullets ends with identical text: "Examine this aspect carefully. Look for concrete evidence in the code or document. Flag specific issues with file paths and line numbers where possible."

This creates severe problems:
1. Token waste: 5 bullets × 23 words = 115 duplicate words per agent × 2 agents = 230 words of pure redundancy in the current output
2. Dilutes domain expertise: The suffix is generic review advice (be specific, use line numbers) that applies to ANY review work, not the specific techniques for plugin structure or prompt engineering
3. Reduces actionability: A plugin structure reviewer should know to "Check plugin.json against the schema validator output" not generic "look for concrete evidence"

The template design hardcodes this suffix at line 86:
```markdown
{For each bullet in Key review areas:}
- **{bullet}**: Examine this aspect carefully. Look for concrete evidence in the code or document. Flag specific issues with file paths and line numbers where possible.
```

This prevents domain profiles from providing specialized instruction. The domain profile's bullets (e.g., "plugin.json schema compliance and completeness") are supposed to BE the specialized instruction, but they're undermined by the generic wrapper.

Recommended fix: Remove the hardcoded suffix entirely. Let the domain profile bullets stand alone. If meta-instructions are needed, put them in the "How to Review" section (which already has this guidance at lines 30-33).

**P2-1: Generic instruction suffix prevents agent specialization**
Location: commands/flux-gen.md line 86

The template's `{For each bullet in Key review areas:}` loop appends the same generic advice to every bullet from every domain profile. This architectural choice prevents domain profiles from encoding specialized review techniques.

Example of what's lost:
- A game-simulation reviewer should get: "Profile frame time budgets in hot loops — 60fps requires <16ms per frame"
- Instead it gets: "Profile frame time budgets in hot loops — 60fps requires <16ms per frame: Examine this aspect carefully. Look for concrete evidence..."

The domain expertise becomes a prefix to generic instructions, rather than the primary instruction.

This affects all 11 domain profiles × average 2 agent specs per domain × 5 bullets per agent = 110 occurrences of duplicate text across potential generated output.

Recommended fix: Change the template from:
```markdown
- **{bullet}**: Examine this aspect carefully. Look for concrete evidence in the code or document. Flag specific issues with file paths and line numbers where possible.
```

To:
```markdown
- **{bullet}**
```

Let the domain profile authors write complete, specialized instructions. The claude-code-plugin profile already does this well (its bullets are complete sentences with specific actions).

### Improvements Suggested

**IMP-1: Command description could be more specific about when to use**
Location: commands/flux-gen.md line 3

Current: "Generate project-specific review agents from detected domain profiles"

This is accurate but doesn't convey WHEN to use it. Users need to know this is for projects where domain-specific expertise matters (game performance, embedded constraints, API design patterns) vs general code quality.

Suggested:
```yaml
description: Generate domain-specific review agents (game perf, API design, etc.) when generic code review isn't enough
```

Tradeoff: Slightly longer (95 chars vs 73 chars) but helps users decide if they need this vs just running `/flux-drive` with core agents.

**IMP-2: Missing guidance on when NOT to use flux-gen**
Location: commands/flux-gen.md (no section for this)

The command explains what it does and how, but not when it's overkill. Users might run `/flux-gen` on every project thinking more agents = better reviews.

Add a brief "When to Use" section before Step 1:

```markdown
## When to Use

Run `/flux-gen` when your project has domain-specific concerns that core flux-drive agents don't cover:
- Game/simulation performance constraints (frame budgets, determinism)
- Embedded systems resource limits (memory, power, real-time)
- Plugin architecture patterns (manifest validation, frontmatter)
- Mobile app platform conventions (lifecycle, permissions)

Skip it for general web apps, CLI tools, or libraries where architecture/safety/correctness agents suffice.
```

This prevents cargo-cult usage ("I should generate agents because the command exists").

**IMP-3: Missing concrete examples in agent prompts**
Location: commands/flux-gen.md lines 82-87 (### Key Review Areas section)

The template tells agents what to review but not what good/bad looks like. Domain profiles have this knowledge but the template doesn't surface it.

Current template has no example section. Add after "### How to Review":

```markdown
### Common Issues in {domain-name} Projects

{Extract 2-3 examples from the domain profile's injection criteria or add a new "Examples" section to domain profiles}
```

For claude-code-plugin, this could be:
```markdown
### Common Issues in Claude Code Plugin Projects

- Frontmatter with `name: "quoted-string"` instead of `name: unquoted-string` (YAML syntax)
- Skills over 100 lines without splitting into references/ subdirectory
- Hook exit codes using 1 (error) instead of 2 (block with message)
```

This gives agents concrete patterns to recognize, not just abstract areas to check.

**IMP-4: Confirmation UX could be clearer about what gets overwritten**
Location: commands/flux-gen.md lines 54-57

Current options:
```
- Option 1: "Generate N new agents (skip M existing)" (Recommended)
- Option 2: "Regenerate all (overwrite existing)"
- Option 3: "Cancel"
```

Option 2's label doesn't convey the consequence: user customizations in existing .md files will be lost. Users who don't understand the .claude/agents/ directory structure might pick Option 2 thinking it "refreshes" agents.

Suggested:
```
- Option 1: "Generate N new agents only (preserve M existing)" (Recommended)
- Option 2: "Regenerate all M existing + N new (DESTROYS customizations in existing agents)"
- Option 3: "Cancel"
```

The all-caps WARNING makes the data loss explicit. "Preserve" vs "destroys" framing is clearer than "skip" vs "overwrite".

### Overall Assessment

The command is structurally sound with good step-by-step guidance, but the generated output quality is undermined by repetitive boilerplate that wastes tokens and prevents domain-specific instruction. Fixing the template's hardcoded suffix (P1-1, P2-1) will make generated agents actually embody domain expertise rather than generic review advice.

<!-- flux-drive:complete -->
