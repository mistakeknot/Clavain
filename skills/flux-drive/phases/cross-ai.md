# Phase 4: Cross-AI Comparison

### Step 4.1: Validate Oracle Output
- Guard clause: Read `{OUTPUT_DIR}/oracle-council.md`.
- If the file is missing, empty (`<50` bytes), or contains only `"Oracle failed"` error text, report `Oracle did not produce findings — skipping cross-AI comparison` and stop.
- Parse Oracle findings into a list: extract numbered findings with severity; if unnumbered, extract top concerns.

### Step 4.2: Classify and Present
- Read individual agent output files from `{OUTPUT_DIR}/` (not synthesized findings from context).
- Classify each finding into:
  - **Blind spots**: Oracle raised something no Claude agent flagged.
  - **Conflicts**: Oracle and Claude agents disagree on the same topic.
- Present classification as a compact list (not a wide table):
  ```text
  Cross-AI comparison:
  - N blind spots (Oracle-only findings)
  - M conflicts (Oracle contradicts Claude agents)
  [Top 3 findings briefly listed]
  ```
- If there are conflicts or notable blind spots (P0/P1 severity), use `AskUserQuestion`:
  - question: `Cross-AI found M conflicts and N blind spots. Investigate?`
  - options:
    - label: `Investigate`
      description: `Run /clavain:interpeer to analyze disagreements (~2 min)`
    - label: `Skip`
      description: `End review with current findings`
- If user approves, invoke `/clavain:interpeer` with conflicts and blind spots as input context.
- If user skips or there are no actionable findings, Phase 4 ends.
- The synthesis from Phase 3 is the final output; do not produce a separate summary.
- Never auto-invoke `/clavain:interpeer`; run it only after explicit `Investigate` consent.
