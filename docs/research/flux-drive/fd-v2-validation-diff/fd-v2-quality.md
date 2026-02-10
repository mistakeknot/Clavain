### Findings Index
- P1 | P1-1 | "Agent Frontmatter" | All 6 fd-v2-*.md agents are missing required `<example>` blocks in their description field
- P1 | P1-2 | "Agent Frontmatter" | fd-v2-correctness has a persona name ("Julik") and editorial voice inconsistent with the other 5 agents
- P1 | P1-3 | "Agent Frontmatter" | fd-v2-quality has a broken heading hierarchy — "## Universal Review" should be "### Universal Review"
- P2 | P2-1 | "Shell Script" | validate-roster.sh hardcodes "6" in the success message instead of using $EXPECTED_COUNT
- P2 | P2-2 | "Shell Script" | validate-roster.sh lost plugin.json cross-validation — no longer verifies agent files are registered in the manifest
- P2 | P2-3 | "Agent Frontmatter" | fd-v2-performance uses "Check for project documentation:" (no "in this order") while the other 5 agents use "Check for project documentation in this order:"
- IMP | IMP-1 | "Knowledge README" | Decay rules use "10 reviews" as threshold but no mechanism tracks review count — only date-based approximation exists
- IMP | IMP-2 | "Compounding Prompt" | The compounding agent prompt uses `## Heading` inside a fenced code block, creating ambiguous heading hierarchy within synthesize.md
- IMP | IMP-3 | "Knowledge README" | Example in Entry Format section contradicts Sanitization Rules — shows specific file path "middleware/auth.go:47-52"
Verdict: needs-changes

---

### Summary (3-5 lines)

The 6 new fd-v2-*.md agent files are structurally sound and well-written, but all 6 are missing the `<example>` blocks in their `description` frontmatter field that AGENTS.md documents as a MUST-have convention for agents in this plugin. One agent (fd-v2-correctness) breaks voice consistency by introducing a persona name "Julik" not used in any other agent. The validate-roster.sh rewrite is clean and well-quoted but hardcodes a magic number in its success message and drops the plugin.json cross-validation that the v1 script performed. The knowledge README has a small internal contradiction between its example (which includes a specific file path) and its sanitization rules (which prohibit specific file paths).

### Issues Found

**P1-1: All 6 fd-v2-*.md agents are missing required `<example>` blocks in their description field**

AGENTS.md lines 127-128 state:

> Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger

Every existing v1 review agent (architecture-strategist, security-sentinel, go-reviewer, etc.) includes at least one `<example>` block in its description frontmatter. None of the 6 new fd-v2-* agents include any example blocks. This is a documented convention, not a style preference.

The `<example>` blocks serve a functional purpose: they help the Claude Code routing layer match user intent to the correct agent. Without them, the routing layer has weaker signal for when to dispatch these agents vs. the old v1 agents that still exist in the repo.

Affected files:
- `/root/projects/Clavain/agents/review/fd-v2-architecture.md` (line 3)
- `/root/projects/Clavain/agents/review/fd-v2-safety.md` (line 3)
- `/root/projects/Clavain/agents/review/fd-v2-correctness.md` (line 3)
- `/root/projects/Clavain/agents/review/fd-v2-quality.md` (line 3)
- `/root/projects/Clavain/agents/review/fd-v2-performance.md` (line 3)
- `/root/projects/Clavain/agents/review/fd-v2-user-product.md` (line 3)

**P1-2: fd-v2-correctness has a persona name and editorial voice inconsistent with the other 5 agents**

The opening line of fd-v2-correctness.md (line 7) reads:

> You are Julik, the Flux-drive v2 Correctness Reviewer: half data-integrity guardian, half concurrency bloodhound. You care about facts, invariants, and what happens when timing turns hostile.

Compare with the other 5 agents:
- fd-v2-architecture: "You are a Flux-drive v2 Architecture & Design Reviewer."
- fd-v2-safety: "You are a Flux-drive v2 Safety Reviewer."
- fd-v2-quality: "You are the Flux-drive v2 Quality & Style Reviewer."
- fd-v2-performance: "You are a Flux-drive v2 Performance Reviewer."
- fd-v2-user-product: "You are the Flux-drive v2 User & Product Reviewer."

The persona name "Julik" appears nowhere else in the codebase or the diff. The editorial style ("half data-integrity guardian, half concurrency bloodhound") and the line "Be courteous, be direct, and be specific about failure modes. If a race would wake someone at 3 AM, say so plainly." (line 9) introduce a Communication Style section at the top that no other agent has. The agent also has a dedicated "Communication Style" section near line 72 and a "Failure Narrative Method" section — structural elements absent from the other 5 agents.

This is not about disallowing personality — it is about consistency across a set of 6 agents that are designed to be interchangeable parts of the same system. The correctness agent reads as if it was written by a different author with different conventions.

Affected file: `/root/projects/Clavain/agents/review/fd-v2-correctness.md` (lines 7-9, 66-71, 73-78)

**P1-3: fd-v2-quality.md has a broken heading hierarchy**

In `/root/projects/Clavain/agents/review/fd-v2-quality.md`, lines 20-23:

```markdown
## Review Approach

## Universal Review
```

"Universal Review" is a subsection of "Review Approach" and should be `### Universal Review` (H3), not `## Universal Review` (H2). Every other agent in the set uses `### Numbered Heading` as subsections under `## Review Approach`. For comparison, fd-v2-architecture.md uses:

```markdown
## Review Approach

### 1. Boundaries & Coupling
```

Similarly, "## Language-Specific Checks" (line 33) should be "### Language-Specific Checks" to stay consistent with the established hierarchy. This means the sub-language headings (Go, Python, etc.) that are currently `###` should be `####`.

Affected file: `/root/projects/Clavain/agents/review/fd-v2-quality.md` (lines 22, 33)

### P2 Issues

**P2-1: validate-roster.sh hardcodes "6" in success message instead of using $EXPECTED_COUNT**

In `/root/projects/Clavain/scripts/validate-roster.sh`, line 62:

```bash
echo "✓ All 6 roster entries validated"
```

The script already defines `EXPECTED_COUNT=6` on line 8 and uses it in the comparison on line 40. The success message should use `$EXPECTED_COUNT` for consistency:

```bash
echo "✓ All $EXPECTED_COUNT roster entries validated"
```

This is minor but creates a maintenance risk — if EXPECTED_COUNT is updated (e.g., when a 7th agent is added per the Oracle recommendation), the success message would become stale.

**P2-2: validate-roster.sh lost plugin.json cross-validation**

The v1 script validated that every roster entry in SKILL.md had a corresponding entry in `.claude-plugin/plugin.json` (the plugin manifest). The v2 rewrite only checks that each roster agent name maps to a file in `agents/review/`. This means the script no longer catches the case where an agent file exists on disk but is not registered in the plugin manifest — a scenario that has caused real bugs in this project before (see bead Clavain-pai where 3 PRD agents existed on disk but were never committed/registered).

The simplification is understandable (the v2 agents are auto-discovered by naming convention, not an explicit agents array), but the cross-validation loss should be a conscious trade-off, not an accidental one. If plugin.json does list agents explicitly, the check should remain.

Affected file: `/root/projects/Clavain/scripts/validate-roster.sh`

**P2-3: fd-v2-performance "First Step" heading text is slightly inconsistent**

In `/root/projects/Clavain/agents/review/fd-v2-performance.md`, line 10:

```markdown
Check for project documentation:
```

The other 5 agents use:

```markdown
Check for project documentation in this order:
```

The phrase "in this order" is functionally significant — it tells the agent to prefer CLAUDE.md over AGENTS.md over domain-specific docs. Its absence in fd-v2-performance is a minor inconsistency but could subtly change agent behavior.

Affected file: `/root/projects/Clavain/agents/review/fd-v2-performance.md` (line 10)

### Improvements Suggested

**IMP-1: Decay rules specify "10 reviews" but the system has no review counter**

In `/root/projects/Clavain/config/flux-drive/knowledge/README.md` (line 50):

> Entries not independently confirmed in **10 reviews** get archived

The compounding agent prompt in synthesize.md (line 256) acknowledges this gap by using a date approximation: ">60 days". The README should either match the actual implementation (date-based) or document that "10 reviews" is the conceptual target and ">60 days" is the current approximation. The current state has two documents giving different thresholds for the same mechanism.

**IMP-2: Compounding agent prompt heading hierarchy is ambiguous**

In `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md`, the compounding agent prompt (lines 195-262) is embedded inside a `````markdown` fenced block. Inside this block, it uses `## Heading` level headings (e.g., `## Input`, `## Decision Criteria`, `## Knowledge Entry Format`). These are visually indistinguishable from the surrounding document's own `## Heading` structure when scanning the file. Using `###` inside the embedded prompt would make the nesting clearer, even though the fenced block technically isolates them. This is a readability improvement for maintainers editing synthesize.md.

**IMP-3: Knowledge README example contradicts sanitization rules**

In `/root/projects/Clavain/config/flux-drive/knowledge/README.md`, the Entry Format example (lines 7-17) includes:

```
Evidence: middleware/auth.go:47-52, handleRequest() — context.Err() not checked after upstream call.
```

But the Sanitization Rules section (lines 56-64) says:

> **Bad**: "middleware/auth.go in Project X has a bug at line 47"

The example entry includes a specific file path with line numbers, which contradicts the "never store file paths to specific repos" rule. While the example could be read as applying to Clavain's own codebase (which is permitted), it would be clearer if the example used a generalized form consistent with the "Good" example in the Sanitization Rules section, or if the example explicitly noted it was a Clavain-internal entry. As written, a compounding agent reading both sections would receive contradictory guidance.

### Overall Assessment

The v2 migration is well-structured and the 6 core agents are substantively strong. The primary gap is the missing `<example>` blocks in all 6 agent description fields — a documented requirement in AGENTS.md that every existing agent follows. The correctness agent's persona inconsistency and the quality agent's heading hierarchy are straightforward fixes. The shell script is clean but lost a useful validation check.

<!-- flux-drive:complete -->
