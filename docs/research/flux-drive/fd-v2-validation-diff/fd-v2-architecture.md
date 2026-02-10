### Findings Index
- P1 | P1-1 | "Agent Merge Coverage" | Compounding agent prompt says "Reads YAML frontmatter" but agents output Findings Index markdown, not YAML
- P1 | P1-2 | "Knowledge Layer" | Decay approximation "10 reviews ~ >60 days" is unreliable and lacks a review counter
- P1 | P1-3 | "validate-roster.sh" | Script no longer validates subagent_type paths against plugin.json — silent breakage if agent name drifts from file
- P2 | P2-1 | "SKILL.md Routing" | Pre-filter rules reference only 3 conditional agents but domain-general list omits rationale for why Quality and Performance always pass
- P2 | P2-2 | "Agent Merge Coverage" | code-simplicity-reviewer and pattern-recognition-specialist checklist items absorbed into fd-v2-architecture without explicit mapping
- P2 | P2-3 | "Compounding" | Compounding agent uses model "sonnet" without version pin — will silently drift on model upgrades
- IMP | IMP-1 | "Knowledge Layer" | Sanitization rules are prose-only — no programmatic enforcement or pre-write check
- IMP | IMP-2 | "validate-roster.sh" | Hardcoded "All 6" in success message — should use $EXPECTED_COUNT variable
- IMP | IMP-3 | "Deferred Features" | Deferred doc has duplicate dependency graph (lines 249-262 repeat lines 233-247)
Verdict: needs-changes

---

### Summary

The flux-drive v2 MVP commit delivers a well-reasoned 19-to-6 agent consolidation with a clean knowledge layer and silent compounding design. The architecture doc shows strong self-review provenance, with Oracle cross-AI findings properly addressed (provenance tracking, sanitization rules, 5-to-6 agent split). The core design is sound: the agent merge covers all 19 original domains, the knowledge format is minimal and correct, and the compounding/decay system breaks the false-positive feedback loop with the provenance field.

Three P1 issues need attention: a stale reference in the architecture doc and compounding prompt that says "YAML frontmatter" when the actual output format is Findings Index markdown; a decay mechanism that approximates review counts with calendar days (unreliable); and a validation script regression that drops the subagent_type-to-file cross-check from v1.

---

### Issues Found

**P1-1: Compounding agent prompt references "YAML frontmatter" but agents produce Findings Index markdown**

The architecture doc (`docs/research/flux-drive-v2-architecture.md`, line ~858 in the diff: "Reads structured agent output files (YAML frontmatter), NOT synthesis prose") and the compounding agent prompt in `skills/flux-drive/phases/synthesize.md` (line ~1705 in diff: "Read the Findings Index from each agent's .md file") are internally inconsistent with the v2 output format.

The v1 agents used YAML frontmatter. The v2 agents use the Findings Index markdown format (defined in `skills/flux-drive/phases/shared-contracts.md` lines 10-17). The architecture doc's Phase Structure table still says "Reads YAML" — this is a leftover from the v1-to-v2 transition.

The compounding prompt itself actually says the right thing ("Read the Findings Index"), but the architecture doc's key design decisions section says "Reads YAML, not prose" and uses this as justification for the design. This creates confusion for anyone reading the architecture doc as a source of truth.

**Impact**: The compounding agent will work correctly because the prompt in synthesize.md is correct. But the architecture doc is misleading and could cause confusion when maintaining or extending the compounding system. A future developer reading "Reads YAML frontmatter" might add YAML parsing logic that doesn't match the actual format.

**Fix**: In `docs/research/flux-drive-v2-architecture.md`, change "Reads structured agent output files (YAML frontmatter)" to "Reads structured agent output files (Findings Index)" and update the key design decisions bullet from "Reads YAML, not prose" to "Reads Findings Index, not prose."

**Files**: `docs/research/flux-drive-v2-architecture.md` (architecture doc, lines ~858 and ~869 in diff)

---

**P1-2: Decay approximation "10 reviews ~ >60 days" is unreliable and lacks a counter**

The compounding agent prompt in `skills/flux-drive/phases/synthesize.md` says: "If an entry has not been independently confirmed in the last 10 reviews (approximate by date: >60 days), move it to archive."

This conflates two different metrics. The architecture doc says decay is based on "10 reviews" (`docs/research/flux-drive-v2-architecture.md`, line ~804: "entries not confirmed in 10 reviews get archived"). The knowledge README (`config/flux-drive/knowledge/README.md`, line 50) also says "10 reviews."

But the compounding agent has no way to count reviews. There is no review counter in the knowledge directory, no metadata tracking review count, and no mechanism to increment one. The ">60 days" heuristic is a rough guess (assumes ~1 review per 6 days). A project reviewing daily would archive entries after 60 reviews. A project reviewing monthly would archive after 2 reviews. Neither matches "10 reviews."

**Impact**: Decay will be inconsistent. Heavily-reviewed projects will retain stale entries too long. Lightly-reviewed projects will archive entries prematurely. The decay mechanism is a core part of the knowledge layer's value proposition — if entries never decay or decay too fast, the system loses trust.

**Fix**: Either (a) add a simple review counter file (`config/flux-drive/knowledge/.review-count`) that the compounding agent increments each run, and use it instead of date approximation, or (b) explicitly document that date-based decay is the MVP approximation and add a counter as a fast-follow. Option (a) is ~5 lines of change.

**Files**: `skills/flux-drive/phases/synthesize.md` (compounding prompt), `config/flux-drive/knowledge/README.md` (decay rules documentation), `docs/research/flux-drive-v2-architecture.md` (architecture spec)

---

**P1-3: validate-roster.sh no longer validates subagent_type paths against plugin.json**

The v1 `validate-roster.sh` performed a cross-reference: it parsed the Plugin Agents table from SKILL.md, extracted `subagent_type` values (e.g., `clavain:review:architecture-strategist`), then checked that each subagent_type existed as a registered agent in `.claude-plugin/plugin.json`. This caught mismatches where the SKILL.md roster referenced an agent name that didn't match any actual plugin agent registration.

The v2 script drops this entirely. It now only checks:
1. That the roster table has exactly 6 entries
2. That each agent name in the roster has a corresponding `.md` file in `agents/review/`

It no longer checks that the `subagent_type` column (column 3 of the table: e.g., `clavain:review:fd-v2-architecture`) actually resolves to a registered agent. If someone renames an agent file but forgets to update the subagent_type in the SKILL.md table, the script passes but the agent won't dispatch.

**Impact**: A name drift between the SKILL.md `subagent_type` column and the actual agent registration would not be caught. The orchestrator uses `subagent_type` for dispatch (not the agent name column), so this is the more important field to validate.

**Fix**: Add a check that each `subagent_type` in column 3 of the Plugin Agents table matches the pattern `clavain:review:{agent-name}` where `{agent-name}` is the value in column 2. This is a lightweight string consistency check, not a full plugin.json parse.

**Files**: `scripts/validate-roster.sh`

---

**P2-1: Pre-filter rules lack explicit rationale for domain-general always-pass agents**

In `skills/flux-drive/SKILL.md` (Step 1.2a), three agents have explicit skip conditions:
- fd-v2-correctness: skip unless data/concurrency present
- fd-v2-user-product: skip unless PRD/user-facing
- fd-v2-safety: skip unless security/deploy present

Then: "Domain-general agents always pass the filter: fd-v2-architecture, fd-v2-quality, fd-v2-performance."

The issue is that fd-v2-performance is categorized as "domain-general" but it has a narrower domain than architecture or quality. Performance analysis is irrelevant for many document types (e.g., a product strategy document, a hiring plan, a process document). The pre-filter should have a condition for performance similar to safety's: skip unless the document mentions performance, scaling, resource usage, or algorithmic concerns.

This is a minor triage accuracy issue. The scoring system (0/1/2) will usually give performance a 0 for irrelevant documents anyway, so it gets filtered by score. But the pre-filter exists to avoid scoring overhead, and performance being always-pass means it gets scored unnecessarily.

**Impact**: Marginal. Performance will usually score 0 and be skipped via the scoring rules. But the pre-filter logic is inconsistent with the agent's actual domain breadth.

---

**P2-2: code-simplicity-reviewer and pattern-recognition-specialist absorbed without explicit mapping**

The architecture doc's merge table shows:
- **Architecture & Design**: merges architecture-strategist, pattern-recognition, code-simplicity
- **Safety**: merges security-sentinel, deployment-verification
- **Correctness**: merges data-integrity-reviewer, concurrency-reviewer
- **Quality & Style**: merges fd-code-quality, all 5 language reviewers
- **User & Product**: merges fd-user-experience, product-skeptic, user-advocate, spec-flow-analyzer
- **Performance**: merges performance-oracle

Looking at the actual v2 agent files:
- `fd-v2-architecture.md` covers pattern analysis (Section 2) and simplicity/YAGNI (Section 3), which maps well to pattern-recognition-specialist and code-simplicity-reviewer
- The merge mapping is accurate in substance

However, specific checklist items from v1 agents may have been lost in the merge. For example, code-simplicity-reviewer had specific guidance about "collapse nested branches" and "ask what breaks if we remove this" — these do appear in fd-v2-architecture.md Section 3 (lines 59-67 of the agent file). pattern-recognition-specialist had "flag hidden feature flags creating parallel architectures" — this appears in Section 2 (line 53 of the agent file).

**Impact**: Low. The checklist items appear to be properly absorbed. This is a verification note, not a coverage gap.

---

**P2-3: Compounding agent uses "model: sonnet" without version pin**

The synthesize.md post-synthesis section says: "Launch a background Task agent (model: sonnet)." The model identifier "sonnet" is an alias that resolves to the current Sonnet model at runtime. If Anthropic releases a new Sonnet version with different behavior, the compounding agent's classification/extraction quality could change without any code change.

**Impact**: Low for MVP. Sonnet is appropriate for classification/extraction work. But for reproducibility of compounding decisions, a version pin (e.g., `claude-sonnet-4-20250514`) would prevent silent drift. This is optional cleanup — Claude Code may not support version-pinned model identifiers in Task calls.

---

### Improvements Suggested

**IMP-1: Add programmatic sanitization enforcement to compounding agent**

The sanitization rules in `config/flux-drive/knowledge/README.md` (lines 56-65) and the compounding prompt in `synthesize.md` are prose-only instructions. The compounding agent is told to "remove specific file paths from external repos" and "remove hostnames, internal endpoints, org names" — but this relies entirely on the LLM following instructions correctly.

For an MVP this is acceptable (and is explicitly flagged as a deferred concern in the Oracle review). But consider adding a post-write validation step: after the compounding agent writes each knowledge entry, a simple regex check for patterns like URLs, IP addresses, email addresses, or paths starting with `/home/`, `/Users/`, etc. This could be a 10-line bash post-check that scans `config/flux-drive/knowledge/*.md` and flags entries for manual review.

---

**IMP-2: validate-roster.sh hardcodes "All 6" in success message**

Line 62 of `scripts/validate-roster.sh`: `echo "All 6 roster entries validated"`. The script defines `EXPECTED_COUNT=6` on line 8 but doesn't use it in the success message. Should be `echo "All $EXPECTED_COUNT roster entries validated"` for consistency.

---

**IMP-3: Deferred features doc has duplicate dependency graph**

`docs/research/flux-drive-v2-deferred.md` lines 233-247 and lines 249-262 contain the same dependency graph twice. The second copy is slightly different (missing the last two items: "7th Agent" and "Claim-Level Convergence"). This looks like an editing artifact. Remove the second copy.

---

### Overall Assessment

The flux-drive v2 MVP is well-designed and ready to ship with minor fixes. The 19-to-6 agent consolidation preserves domain coverage through careful merge mapping. The knowledge layer design is sound — single-tier storage, provenance tracking to break feedback loops, and qmd-based retrieval with a 5-entry cap is the right level of complexity for an MVP. The silent compounding hook correctly separates infrastructure from user experience.

The three P1 issues are all fixable in under 30 minutes: a stale "YAML frontmatter" reference in the architecture doc, a decay mechanism that needs a review counter instead of calendar approximation, and a validation script that should cross-check subagent_type consistency. None of these block the core functionality — agents will dispatch, review, and compound correctly. But they represent maintenance debt that will compound if not addressed promptly.

The most important structural decision — splitting Safety from Correctness to get 6 agents instead of 5 — is well-justified by the 5/7 agent convergence finding and the Oracle recommendation. The deferred features document properly preserves the cut scope with trigger conditions, maintaining optionality without overbuilding.

<!-- flux-drive:complete -->
