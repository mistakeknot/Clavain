# Phase 4: Cross-AI Escalation (Optional)

After synthesis, check whether Oracle was in the review roster and offer escalation into the interpeer skill stack.

### Step 4.1: Detect Oracle Participation

If Oracle (Cross-AI) was **not** in the roster, offer a lightweight option:

```
Cross-AI: No Oracle perspective was included in this review.
Want a second opinion? /clavain:interpeer (quick mode) for Claude↔Codex feedback.
```

Then stop. Phase 4 only continues if Oracle participated.

### Step 4.2: Compare Model Perspectives

When Oracle was in the roster, compare its findings against the Claude-based agents:

1. Read `{OUTPUT_DIR}/oracle-council.md`
2. Compare Oracle's findings with the synthesized findings from Step 3.2
3. Classify each finding into:

| Category | Definition | Count |
|----------|-----------|-------|
| **Agreement** | Oracle and Claude agents flagged the same issue | Strong signal |
| **Oracle-only** | Oracle found something no Claude agent raised | Potential blind spot |
| **Claude-only** | Claude agents found something Oracle missed | May be codebase-specific |
| **Disagreement** | Oracle and Claude agents conflict on the same topic | Needs investigation |

### Step 4.3: Auto-Chain to Interpeer Mine Mode

If **any disagreements** were found in Step 4.2:

```
Cross-AI Analysis:
- Agreements: N (high confidence)
- Oracle-only findings: M (review these — potential blind spots)
- Claude-only findings: K (likely codebase-specific context)
- Disagreements: D (need resolution)

Disagreements detected. Running interpeer mine mode to extract actionable artifacts...
```

Then invoke `interpeer` in **mine** mode inline (do not dispatch a subagent — this runs in the main session):

1. Structure each disagreement as a conflict (The Conflict, Evidence, Resolution, Minority Report)
2. Generate artifacts: tests that would resolve the disagreement, spec clarifications, stakeholder questions
3. Present the mine mode summary

### Step 4.4: Offer Interpeer Council for Critical Decisions

After mine mode completes (or if there were no disagreements but Oracle raised P0/P1 findings), check if any finding represents a **critical architectural or security decision**. Indicators:
- P0 severity from any source
- Disagreement on architecture or security topic
- Oracle flagged a security issue that Claude agents missed

If critical decisions exist, offer council escalation:

```
Critical decision detected: [brief description]

Options:
1. Resolve now — I'll synthesize the best recommendation from available perspectives
2. Run interpeer council — full multi-model consensus review on this specific decision
3. Continue without escalation
```

If user chooses option 2, invoke `interpeer` in **council** mode for just the critical decision (not the whole document).

### Step 4.5: Final Cross-AI Summary

Present a final summary that includes the cross-AI dimension:

```markdown
## Cross-AI Review Summary

**Model diversity:** Claude agents (N) + Oracle (GPT-5.2 Pro)

| Finding Type | Count | Confidence |
|-------------|-------|-----------|
| Cross-model agreement | A | High |
| Oracle-only (blind spots) | B | Review |
| Claude-only (codebase context) | C | Moderate |
| Resolved disagreements | D | Varies |

[If interpeer mine mode ran:]
### Artifacts Generated
- N tests proposed to resolve disagreements
- M spec clarifications needed
- K stakeholder questions identified

[If interpeer council mode ran:]
### Council Decision
[Brief summary of council's synthesis on the critical decision]
```
