# interlab: Command Prompt Token Reduction

## Objective
Reduce the token cost of Clavain's largest command prompts while preserving all behavioral fidelity.

## Results

| File | Before | After | Reduction |
|------|--------|-------|-----------|
| route.md | 20,651 | 7,623 | −63% |
| doctor.md | 20,603 | 12,113 | −41% |
| sprint.md | 17,805 | 9,108 | −49% |
| work.md | 11,722 | 5,165 | −56% |
| **Total** | **70,781** | **34,009** | **−52%** |

~11,000 tokens saved across the top 4 commands.

## Status: COMPLETE

## Key Techniques
1. **Pattern extraction** — define repeated code blocks once, reference by name (biggest single win, −50% on route.md alone)
2. **CLI path dedup** — `clavain-cli` instead of `"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli"`
3. **Prose→terse bullets** — LLMs parse structure better than paragraphs
4. **Table column removal** — Reason columns are redundant when Condition implies meaning
5. **Redundant instruction removal** — "Stop after dispatch" consolidated, "Do NOT" deduplicated
6. **Inline code blocks** — short bash snippets don't need fenced blocks
7. **Agent prompt compression** — procedural description instead of literal template

## Key Insight
Executable bash blocks are the irreducible floor (~40-60% of doctor.md). Prose, structure, and documentation compress 60%+. Pattern extraction is the dominant technique for files with repeated code blocks.
