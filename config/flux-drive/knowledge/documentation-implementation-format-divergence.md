---
lastConfirmed: 2026-02-10
provenance: independent
---
Architecture documentation can drift from implementation when design decisions change mid-development. The fd-v2 architecture doc stated "Reads YAML, not prose" but the actual implementation uses Findings Index (markdown format), creating a documentation-implementation gap.

Evidence: docs/research/flux-drive-v2-architecture.md describes "YAML frontmatter" as agent output format, but skills/flux-drive/phases/synthesize.md compounding agent instructions read "Findings Index from each agent's .md file (first ~30 lines)" and agents actually output markdown Findings Index per shared-contracts.md.

Verify: Cross-reference architecture design decision descriptions with actual agent output formats in shared-contracts.md and agent prompt instructions. Look for format references that contradict actual implementation.
