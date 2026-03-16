# interlab: Route Prompt Token Reduction

## Objective
Reduce the token cost of `commands/route.md` (Clavain's most-invoked command prompt) while preserving all routing behavior.

## Metrics
- **Primary**: total_chars (int, lower_is_better)
- **Secondary**: approx_tokens (int)
- **Guard**: errors (int) — must remain 0

## How to Run
`bash interlab-route-prompt.sh` — measures size and validates 30+ behavioral fidelity checks

## Files in Scope
- `commands/route.md`

## Constraints
- All 17 heuristic table rows preserved
- 30+ structural/behavioral checks pass
- Key bash code blocks preserved verbatim
- Discovery flow, claim handling, staleness checks intact

## What's Been Tried
- **Baseline**: 20,651 chars, ~6,257 tokens, 17 heuristic rows, 0 errors.
- **Exp 1 (kept)**: Pattern extraction (token-attribution 3→1, claim-identity 2→1, claim-bead 2→1), CLI path dedup, prose→bullets, haiku prompt compression. 10,291 chars (−50.1%).
- **Exp 2 (kept)**: Removed Reason column from heuristic table, shortened Condition column. 9,509 chars (−54%).
- **Exp 3 (kept)**: Replaced remaining `${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli` with `clavain-cli`. 9,479 chars.
- **Exp 4 (kept)**: Removed spaces around `||` in bash, removed quotes around artifact names. 9,455 chars.
- **Exp 5 (kept)**: Flattened discovery route table and action verb mappings into compact inline format. 8,817 chars (−57.3%).
- **Exp 6 (kept)**: Converted pattern code blocks to inline code. 8,696 chars (−57.9%).
- **Exp 7 (kept)**: Compressed header and new-project hint. 8,569 chars (−58.5%).
- **Exp 8 (kept)**: Compressed Step 1 sprint resume flow. 8,283 chars (−59.9%).
- **Exp 9 (kept)**: Compressed staleness check description. 8,105 chars (−60.7%).
- **Exp 10 (kept)**: Compressed haiku fallback classification prompt from literal template to procedural description. 7,842 chars (−62.0%).
- **Exp 11 (kept)**: Compressed background staleness sweep. 7,749 chars (−62.5%).
- **Exp 12 (kept)**: Compressed AskUserQuestion specification and action verb mapping. 7,623 chars (−63.1%).

## Final Summary
- **Starting**: 20,651 chars (~6,257 tokens)
- **Ending**: 7,623 chars (~2,310 tokens)
- **Improvement**: −13,028 chars (63% reduction), ~3,947 tokens saved per invocation
- **Experiments**: 12 (12 kept / 0 discarded / 0 crashed)
- **Key wins**: Pattern extraction (−50% in first pass), heuristic table Reason column removal, CLI path dedup, prose-to-bullets compression
- **Key insights**: The biggest single technique was pattern extraction — defining repeated code blocks once and referencing by name. The LLM reader doesn't need the same bash snippet three times. Prose→terse bullets was the second-largest win. The heuristic table's Reason column was pure documentation waste — the Condition column already implies the reason.
