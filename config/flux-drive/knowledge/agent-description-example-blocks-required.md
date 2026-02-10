---
lastConfirmed: 2026-02-10
provenance: independent
---
Agent descriptions in this plugin must include concrete `<example>` blocks with `<commentary>` explaining when to trigger the agent. This is documented in AGENTS.md lines 127-128 and followed by all v1 agents but was omitted in the initial fd-v2-* agent set.

Evidence: All 6 fd-v2-*.md agents (fd-v2-architecture, fd-v2-safety, fd-v2-correctness, fd-v2-quality, fd-v2-performance, fd-v2-user-product) at line 3 (description field) lack `<example>` blocks, while v1 agents (architecture-strategist, security-sentinel, etc.) all include them.

Verify: Check agents/review/*.md frontmatter description fields for `<example>` blocks. Compare with AGENTS.md convention documentation at lines 127-128.
