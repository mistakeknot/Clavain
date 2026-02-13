# Scoring Examples

Reference examples for flux-drive agent triage scoring. Read this file during Step 1.2 when you need worked examples for scoring decisions.

---

**Plan reviewing Go API changes (project has CLAUDE.md, web-api domain detected):**

Slot ceiling: 4 (base) + 0 (single file) + 1 (1 domain) = 5 slots. Stage 1: top 2 (40% of 5, rounded up).

| Agent | Category | Base | Domain Boost | Project | Total | Stage | Action |
|-------|----------|------|-------------|---------|-------|-------|--------|
| fd-architecture | Plugin | 3 | +2 (5 web-api items) | +1 | 6 | 1 | Launch |
| fd-safety | Plugin | 3 | +1 (4 web-api items) | +1 | 5 | 1 | Launch |
| fd-quality | Plugin | 2 | +1 (5 web-api items) | +1 | 4 | 2 | Launch |
| fd-performance | Plugin | 1 | +1 (5 web-api items) | +1 | 3 | 2 | Launch |
| fd-correctness | Plugin | 0 | — | — | 0 | — | Skip |
| fd-user-product | Plugin | 0 | — | — | 0 | — | Skip |

**README review for Python CLI tool (cli-tool domain detected):**

Slot ceiling: 4 (base) + 0 (single file) + 1 (1 domain) = 5 slots. Stage 1: top 2.

| Agent | Category | Base | Domain Boost | Project | Total | Stage | Action |
|-------|----------|------|-------------|---------|-------|-------|--------|
| fd-user-product | Plugin | 3 | +2 (5 cli-tool items) | +1 | 6 | 1 | Launch |
| fd-quality | Plugin | 3 | +1 (5 cli-tool items) | +1 | 5 | 1 | Launch |
| fd-architecture | Plugin | 1 | +1 (5 cli-tool items) | +1 | 3 | 2 | Launch (thin section) |
| fd-performance | Plugin | 0 | — | — | 0 | — | Skip |
| fd-safety | Plugin | 0 | — | — | 0 | — | Skip |
| fd-correctness | Plugin | 0 | — | — | 0 | — | Skip |

**PRD for new user onboarding flow (web-api domain detected):**

Slot ceiling: 4 (base) + 0 (single file) + 1 (1 domain) = 5 slots. Stage 1: top 2.

| Agent | Category | Base | Domain Boost | Project | Total | Stage | Action |
|-------|----------|------|-------------|---------|-------|-------|--------|
| fd-user-product | Plugin | 3 | +2 (5 web-api items) | +1 | 6 | 1 | Launch |
| fd-architecture | Plugin | 2 | +2 (5 web-api items) | +1 | 5 | 1 | Launch |
| fd-safety | Plugin | 1 | +1 (4 web-api items) | +1 | 3 | 2 | Launch (auth — thin) |
| fd-performance | Plugin | 0 | — | — | 0 | — | Skip |
| fd-quality | Plugin | 0 | — | — | 0 | — | Skip |
| fd-correctness | Plugin | 0 | — | — | 0 | — | Skip |

**Game project plan (game-simulation domain at 0.65, project has CLAUDE.md + /flux-gen agents):**

Slot ceiling: 4 (base) + 0 (single file) + 1 (1 domain) + 2 (flux-gen) = 7 slots. Stage 1: top 3 (40% of 7, rounded up).

| Agent | Category | Base | Domain Boost | Project | DA | Total | Stage | Action |
|-------|----------|------|-------------|---------|-----|-------|-------|--------|
| fd-game-design | Plugin | 3 | +2 (5 game items) | +1 | — | 6 | 1 | Launch |
| fd-simulation-kernel* | Project | 3 | +2 (generated) | +1 | +1 | 7 | 1 | Launch |
| fd-architecture | Plugin | 3 | +1 (5 game items) | +1 | — | 5 | 1 | Launch |
| fd-correctness | Plugin | 2 | +2 (5 game items, high-priority) | +1 | — | 5 | 2 | Launch |
| fd-performance | Plugin | 2 | +1 (5 game items) | +1 | — | 4 | 2 | Launch |
| fd-quality | Plugin | 2 | +1 (4 game items) | +1 | — | 4 | 2 | Launch |
| fd-safety | Plugin | 1 | +1 (4 game items) | +1 | — | 3 | 2 | Launch |
| fd-user-product | Plugin | 0 | — | — | — | 0 | — | Skip |

*Generated via /flux-gen. DA = domain_agent bonus.

**Thin section thresholds:**
- **thin**: <5 lines or <3 bullet points — agent with adjacent domain should cover this
- **adequate**: 5-30 lines or 3-10 bullet points — standard review depth
- **deep**: 30+ lines or 10+ bullet points — validation only, don't over-review
