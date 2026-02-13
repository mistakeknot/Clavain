# P0 Bead Details

Retrieved: 2026-02-11

## Clavain-6mxp [BUG] — P0 OPEN

**Title:** Fix component counts to 33 skills, 16 agents, 26 commands across all docs

- **Owner:** mk
- **Type:** bug
- **Created:** 2026-02-11
- **Updated:** 2026-02-11

**Description:**
Quality agent found actual command count is 26 (model-routing added without doc update). Multiple surfaces disagree: using-clavain says 34/23, AGENTS.md says 33/25, plugin.json says 33/25. Fix in: using-clavain/SKILL.md, plugin.json, agent-rig.json, AGENTS.md, README.md, CLAUDE.md. See docs/research/quality-consistency-review-of-clavain.md

---

## Clavain-i3o0 [FEATURE] — P0 OPEN

**Title:** Build gen-catalog.py to auto-generate counts + CI test for drift prevention

- **Owner:** mk
- **Type:** feature
- **Created:** 2026-02-11
- **Updated:** 2026-02-11

**Description:**
Oracle insight: make drift impossible, not just fix it. Create scripts/gen-catalog.py that reads all frontmatter, regenerates counts in plugin.json/AGENTS.md/CLAUDE.md/using-clavain. Add CI test: running generator produces no diff. See Oracle cross-review in docs/research/.

---

## Key Observations

1. **Count drift is the root issue** — The actual command count is 26 (model-routing was added without updating docs), but multiple files still say 25 or 23. Skill count also disagrees (33 vs 34 depending on the file).
2. **Six files need fixing** for Clavain-6mxp: using-clavain/SKILL.md, plugin.json, agent-rig.json, AGENTS.md, README.md, CLAUDE.md.
3. **Clavain-i3o0 is the systemic fix** — Rather than manually fixing counts each time, build a generator script that reads actual filesystem state and regenerates counts, with a CI test to prevent future drift.
4. **Both beads are related** — i3o0 is the long-term prevention for the class of bugs that 6mxp represents.
