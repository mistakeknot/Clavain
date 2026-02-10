### Findings Index
- P0 | P0-1 | "launch.md" | Stale v1 agent names in launch.md examples, monitoring, and agent-type dispatch instructions
- P1 | P1-1 | "synthesize.md" | Stale v1 agent names in findings.json example
- P1 | P1-2 | "SKILL.md / synthesize.md" | Stale "Adaptive Reviewer" terminology persists in multiple files
- P1 | P1-3 | "validate-roster.sh" | Validation script does not verify subagent_type column or agent file content
- P1 | P1-4 | "using-clavain SKILL.md" | Routing table not updated for v2 agents — still references all 19 v1 agents
- P1 | P1-5 | "synthesize.md" | Compounding agent reads "YAML frontmatter" but agents produce Findings Index (not YAML)
- P1 | P1-6 | "SKILL.md" | spec-flow-analyzer and data-migration-expert dropped from roster without explicit merge target
- P1 | P1-7 | "launch.md" | Knowledge retrieval pipelining instruction is aspirational — no mechanism exists
- IMP | IMP-1 | "validate-roster.sh" | Add subagent_type cross-reference to prevent roster/dispatch drift
- IMP | IMP-2 | "knowledge README.md" | Decay rule uses "10 reviews" but no review counter exists
- IMP | IMP-3 | "fd-v2-quality.md" | Quality agent model should be inherit, not sonnet — inconsistent with v1 code-simplicity-reviewer merge
Verdict: needs-changes

---

### Summary (3-5 lines)

The 19-to-6 agent merge is structurally sound: agent boundaries are well-chosen, the knowledge layer design (provenance tracking, sanitization, decay) is rigorous, and the silent compounding approach avoids user-facing complexity. However, the diff has a **P0 stale-reference problem**: `launch.md` still contains v1 agent names in its dispatch instructions and monitoring examples, which will cause orchestrators to use wrong `subagent_type` values. Additionally, the `using-clavain/SKILL.md` routing table (the plugin's primary discovery mechanism) was not updated in this diff and still references all 19 v1 agents. Several P1 terminology and contract mismatches need correction before the migration is safe to ship.

---

### Issues Found

**P0-1: Stale v1 agent names in launch.md examples, monitoring, and agent-type dispatch instructions** (Section: `skills/flux-drive/phases/launch.md`)

The diff adds Step 2.1a (knowledge retrieval) and the Knowledge Context prompt template section to `launch.md`, but does NOT update the existing content that still references v1 agents. Three specific locations:

1. **Line 107-108** ("How to launch each agent type"): The section titled "Adaptive Reviewers (clavain)" still reads:
   ```
   - Use the native `subagent_type` from the roster (e.g., `clavain:review:architecture-strategist`)
   ```
   This is now wrong. The correct example should be `clavain:review:fd-v2-architecture`. An orchestrator following this instruction would dispatch a v1 agent that is NOT in the v2 roster.

2. **Lines 238-240** (Step 2.3 monitoring examples): Still shows:
   ```
   ⏳ architecture-strategist
   ⏳ security-sentinel
   ⏳ go-reviewer
   ```
   And line 248: `✅ architecture-strategist (47s)`, line 254: `⚠️ Timeout: security-sentinel still running after 300s`. These should use fd-v2-* names.

3. **Line 107**: The category heading "Adaptive Reviewers (clavain)" should be "Plugin Agents (clavain)" to match the terminology used in the updated SKILL.md roster table.

This is P0 because `launch.md` is the actual dispatch instruction set. An orchestrator that reads these instructions will use `architecture-strategist` as the subagent_type, which dispatches the OLD v1 agent (which still exists on disk), completely bypassing the new v2 agent. The review would silently run v1 agents while the roster table claims v2.

**Fix**: Replace the three stale-reference locations in `launch.md` with v2 agent names and update the category heading from "Adaptive Reviewers" to "Plugin Agents".

---

**P1-1: Stale v1 agent names in findings.json example** (Section: `skills/flux-drive/phases/synthesize.md`)

The `findings.json` schema example at lines 117 and 126 of `synthesize.md` shows:
```json
"agent": "architecture-strategist",
```
and:
```json
"agent": "fd-code-quality",
```

Both are v1 agent names. The orchestrator that generates `findings.json` will use whatever agent names it dispatched, so if P0-1 is fixed and v2 agents are dispatched, the examples just need to match for documentation accuracy. However, if any downstream tooling parses these examples as a schema reference, the mismatch could cause confusion.

**Fix**: Update the example agent names in the `findings.json` template to `fd-v2-architecture` and `fd-v2-quality`.

---

**P1-2: Stale "Adaptive Reviewer" terminology persists in multiple files** (Section: `skills/flux-drive/SKILL.md`, `skills/flux-drive/phases/synthesize.md`)

The diff renamed the roster table heading from "Adaptive Reviewers" to "Plugin Agents (clavain)" in `SKILL.md`, which is correct. However, the term "Adaptive Reviewer" persists in three locations not touched by the diff:

1. `/root/projects/Clavain/skills/flux-drive/SKILL.md` line 253: "Oracle replaces the lowest-scoring Adaptive Reviewer"
2. `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md` line 39: "prefer Project Agents over plugin Adaptive Reviewers"
3. `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md` line 43: "When a Project Agent and an Adaptive Reviewer give different advice"

These are semantic references that an orchestrator will parse to understand agent categories. The v2 roster no longer has a concept called "Adaptive Reviewer" -- they are "Plugin Agents". This terminology drift means the orchestrator's deduplication and priority logic references a category that no longer exists in the roster.

**Fix**: Replace "Adaptive Reviewer(s)" with "Plugin Agent(s)" in all three locations.

---

**P1-3: Validation script does not verify subagent_type column or agent file content** (Section: `scripts/validate-roster.sh`)

The v1 `validate-roster.sh` cross-referenced the roster's `subagent_type` column against `plugin.json` agents entries, then verified file paths on disk. The v2 script was significantly simplified: it only (a) counts roster entries (expects 6), (b) checks for duplicates, and (c) verifies `agents/review/{name}.md` exists.

What is lost:

- **No subagent_type validation**: The SKILL.md roster table has a `subagent_type` column (e.g., `clavain:review:fd-v2-architecture`), but the script does not verify these values match the agent files. If someone typos the subagent_type in the roster table, the script passes but dispatch fails at runtime.
- **No cross-reference with launch.md**: The script cannot detect the P0-1 problem above (launch.md references v1 names) because it only reads SKILL.md.
- **Hardcoded "6"**: The expected count is hardcoded as both `EXPECTED_COUNT=6` and the success message `"All 6 roster entries validated"`. If a 7th agent is added, both constants need updating. Using `$EXPECTED_COUNT` in the success message would be marginally better.

The simplified script is appropriate for the v2 roster size, but losing the subagent_type-to-file cross-reference removes a valuable consistency check.

**Fix**: (a) Extract the subagent_type column (column 3) and verify each one matches the pattern `clavain:review:{agent-name}`. (b) Use `$EXPECTED_COUNT` in the success message. The launch.md cross-reference is a nice-to-have for IMP-1.

---

**P1-4: Routing table in using-clavain/SKILL.md not updated for v2 agents** (Section: `skills/using-clavain/SKILL.md`)

The `using-clavain/SKILL.md` file is the primary routing mechanism -- it is injected into every session via the SessionStart hook. The diff does NOT modify this file. Looking at the current live file:

- Line 37: Key Agents column lists `architecture-strategist, spec-flow-analyzer` for the Plan stage
- Line 41: Key Agents column lists `{go,python,typescript,shell,rust}-reviewer, security-sentinel, performance-oracle, concurrency-reviewer, code-simplicity-reviewer` for the Review stage
- Line 42: Key Agents column lists `deployment-verification-agent` for the Ship stage
- Lines 48-56: Layer 2 domain routing references `pattern-recognition-specialist`, `code-simplicity-reviewer`, `data-integrity-reviewer`, `data-migration-expert`, `deployment-verification-agent`, etc.

None of these reference the new fd-v2-* agents. This means that the routing table -- which drives how Claude selects agents for non-flux-drive tasks (direct `/review`, `/quality-gates`, etc.) -- will continue routing to v1 agents. Users who invoke individual review agents through the routing table will get v1 agents, while flux-drive reviews use v2 agents, creating a confusing split.

This is P1 rather than P0 because the v1 agents still exist on disk and will function correctly when dispatched directly. The inconsistency is that flux-drive uses v2 while everything else uses v1. But this is likely intentional -- the v1 agents are not deleted in this diff, so they remain available for direct use. However, the routing table should at minimum mention the fd-v2 agents for the flux-drive review stage (line 38).

**Fix**: At minimum, update line 38 to note that flux-drive uses fd-v2-* agents. Ideally, add a note to the routing table that fd-v2-* agents are flux-drive-internal and the v1 agents remain available for direct dispatch. This clarification prevents users from manually dispatching fd-v2-* agents outside of flux-drive (they lack the Knowledge Context injection that flux-drive provides).

---

**P1-5: Compounding agent reads "YAML frontmatter" but agents produce Findings Index (not YAML)** (Section: `skills/flux-drive/phases/synthesize.md`)

The architecture doc (`docs/research/flux-drive-v2-architecture.md`) line in the diff states:
> "Reads YAML, not prose: Decoupled from synthesis presentation format."

And the compounding agent prompt in `synthesize.md` says:
> "Read the Findings Index from each agent's .md file (first ~30 lines)"
> "For P0/P1 findings, read the full prose section for evidence anchors"

This is internally consistent -- the compounding agent reads the Findings Index (markdown), not YAML. However, the architecture doc's design decision description creates a documentation-implementation gap: it says the compounding agent reads "YAML frontmatter" and "structured agent output files (YAML frontmatter)" but the actual agent output format (per `shared-contracts.md`) is a Findings Index in markdown, not YAML frontmatter.

This happened because the original v2 design assumed agents would output YAML frontmatter (the format that was debated in Clavain-7p2). The resolution was to use the Findings Index format instead (Clavain-27u). The architecture doc's design decision text was not updated to reflect this.

**Fix**: Update the architecture doc's "Key design decisions" section: change "Reads YAML, not prose" to "Reads Findings Index, not synthesis prose" and update the related sentence about "YAML frontmatter as the system's Achilles heel."

---

**P1-6: spec-flow-analyzer and data-migration-expert dropped without explicit merge target** (Section: `skills/flux-drive/SKILL.md`)

The diff's architecture table shows which v1 agents merged into which v2 agents:
- Architecture & Design: architecture-strategist, pattern-recognition, code-simplicity
- Safety: security-sentinel, deployment-verification
- Correctness: data-integrity-reviewer, concurrency-reviewer
- Quality & Style: fd-code-quality, 5 language reviewers
- User & Product: fd-user-experience, product-skeptic, user-advocate, spec-flow-analyzer
- Performance: performance-oracle

Two v1 agents from the old roster are not mentioned in the merge mapping:
1. **data-migration-expert** -- was in the v1 roster (`agents/review/data-migration-expert.md` exists on disk) but is not listed in any v2 merge. Its domain (migration safety, ID mapping validation) is partially covered by fd-v2-correctness (data consistency, transactions) and fd-v2-safety (migration safety, rollback), but the deep expertise in SQL verification queries and production-fixture mapping is not explicitly absorbed.
2. **agent-native-reviewer** -- was in `agents/review/` but was never in the flux-drive roster (it was a Layer 2 domain agent). No coverage gap here.

For data-migration-expert: the v2 architecture doc lists 19 specialized agents being replaced but only names 16 in the merge mapping table (excluding data-migration-expert, agent-native-reviewer, and strategic-reviewer). Strategic-reviewer appears to be absorbed into fd-v2-user-product alongside product-skeptic and user-advocate, but this is not explicit in the merge table.

**Fix**: Add data-migration-expert to the Correctness merge (it is the closest domain match) and add strategic-reviewer to the User & Product merge in the architecture doc's merge table. Even if the capability is covered, the explicit accounting prevents "where did agent X go?" questions.

---

**P1-7: Knowledge retrieval pipelining instruction is aspirational -- no mechanism exists** (Section: `skills/flux-drive/phases/launch.md`)

Step 2.1a ends with:
> "**Pipelining**: Start qmd queries before agent dispatch. While queries run, prepare agent prompts. Inject results when both are ready."

This is describing concurrent execution of MCP tool calls (qmd retrieval) and prompt preparation. However, the orchestrator (Claude Code) executes tool calls sequentially -- there is no mechanism to "start qmd queries" and "prepare prompts" in parallel. The orchestrator would need to either:
1. Run all qmd queries first, then dispatch agents (serial, adds latency)
2. Dispatch agents without knowledge, then somehow inject knowledge mid-execution (not possible)

In practice, the orchestrator will do option 1: run qmd queries serially, collect results, build prompts with knowledge context, then dispatch agents. The "pipelining" instruction creates a false expectation and could lead an orchestrator to skip knowledge injection (thinking it can be deferred) when it actually must happen before dispatch.

**Fix**: Replace the pipelining instruction with: "Run all qmd queries before agent dispatch. If qmd latency is unacceptable, skip knowledge injection rather than blocking dispatch." This matches the actual execution model.

---

### Improvements Suggested

**IMP-1: Add subagent_type cross-reference to validate-roster.sh**

The v1 script verified subagent_type values against plugin.json. The v2 script dropped this. Even without plugin.json integration, the script could extract the subagent_type column from the SKILL.md table and verify it matches the pattern `clavain:review:{agent-name}` where `{agent-name}` matches an existing file. This catches typos in the roster table that would cause silent dispatch failures.

Smallest viable change: add 5-10 lines of awk to extract column 3, strip whitespace, and verify `agents/review/{stem}.md` exists where `{stem}` is derived from `clavain:review:{stem}`.

---

**IMP-2: Decay rule uses "10 reviews" but no review counter exists**

The knowledge README and compounding agent prompt both specify: "entries not independently confirmed in the last 10 reviews get archived." The compounding agent prompt then clarifies: "approximate by date: >60 days."

The "10 reviews" metric assumes a review counter or log that does not exist in the current design. The "60 days" approximation is reasonable but breaks down for projects reviewed infrequently (1 review/month means 10 reviews = 10 months, not 60 days) or frequently (daily reviews mean 10 reviews = 10 days, much less than 60 days).

Suggestion: Either commit to date-based decay ("entries older than 60 days without independent confirmation") or add a simple review counter (e.g., a `review-count` file in the knowledge directory incremented by the compounding agent each run). The current dual-metric creates ambiguity.

---

**IMP-3: Knowledge README example contradicts sanitization rules**

The knowledge README's entry format example includes:
```
Evidence: middleware/auth.go:47-52, handleRequest() -- context.Err() not checked after upstream call.
Verify: grep for ctx.Err() after http.Do() calls in middleware/*.go.
```

This includes specific file paths (`middleware/auth.go:47-52`), which the sanitization rules say should be generalized for global entries: "Remove specific file paths from external repos (not the Clavain repo)."

The example appears to be showing a project-specific entry that would violate sanitization rules if compounded to global. The "Good" example later in the README is correctly generalized. However, having the first example in the "Entry Format" section show a format that violates the later sanitization rules is confusing.

Suggestion: Either note that the first example shows a project-local format that would need sanitization before global storage, or use the generalized form in the primary example.

---

### Overall Assessment

The v2 migration architecture is well-reasoned: the 6-agent split (separating Safety from Correctness per Oracle's recommendation), the provenance-tracked knowledge layer, and the silent compounding design all represent solid engineering decisions grounded in the self-review consensus. The primary risk is execution completeness -- the diff updates the roster and adds new features (knowledge injection, compounding) but leaves stale v1 references in the dispatch instructions (`launch.md`), monitoring examples, and the top-level routing table (`using-clavain/SKILL.md`). The P0 in launch.md must be fixed before shipping because it would cause the orchestrator to dispatch v1 agents while the roster claims v2, producing a functionally broken migration. The P1 items are consistency issues that should be addressed in the same commit to prevent confusion.

<!-- flux-drive:complete -->
