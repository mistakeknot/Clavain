---
lastConfirmed: 2026-02-10
provenance: independent
---
When consolidating agents (N-to-M merge), explicitly document where each retired agent's capabilities were absorbed. Missing agents in merge mappings create "where did agent X go?" confusion and risk capability loss.

Evidence: fd-v2 19-to-6 merge listed architecture-strategist → fd-v2-architecture, but data-migration-expert and spec-flow-analyzer were absent from the merge table in skills/flux-drive/SKILL.md despite being in the v1 roster. The merge table showed 16 agents mapped but claimed 19 were replaced.

Verify: Count agents in "before" roster vs agents listed in merge mapping table. Every agent in the old roster should appear in at least one merge target, even if capability overlap is partial.
