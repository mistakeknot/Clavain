# Tier 3 Beads: Simplification Issues

## Analysis Date: 2026-02-09

## Purpose

Created five P2 beads issues targeting simplification of the Tier 3 (beads/research) subsystem in Clavain. These issues collectively reduce complexity in the research workflow by removing unnecessary features and extracting shared contracts.

## Issues Created

| ID | Type | Title |
|---|---|---|
| Clavain-27u | feature | Replace YAML frontmatter with rigid markdown Findings Index + central findings.json |
| Clavain-ne6 | task | Simplify Phase 4: keep cross-AI classification, add consent gate, target 30-40 lines |
| Clavain-apn | task | Refactor launch-codex.md: extract shared contracts, keep only Codex-specific mechanics |
| Clavain-dh6 | task | Remove thin-section deepening from synthesize.md (lines 79-109) |
| Clavain-1va | task | Remove manual token trimming from launch.md — trust 200K context windows |

## Rationale

### 1. Replace YAML frontmatter (Clavain-27u)
YAML frontmatter in research findings is fragile and hard to validate. A rigid markdown "Findings Index" pattern paired with a central `findings.json` file provides structured metadata without YAML parsing complexity. This is the only feature-type issue — it adds a new pattern rather than removing an old one.

### 2. Simplify Phase 4 (Clavain-ne6)
Phase 4 (cross-AI classification) currently has too much surface area. The core value — having a second AI classify findings — should be preserved, but wrapped in a consent gate so it only runs when the user opts in. Target: 30-40 lines total, down from whatever it is now.

### 3. Refactor launch-codex.md (Clavain-apn)
`launch-codex.md` duplicates contracts that should be shared between Claude and Codex launch paths. Extract the shared parts (output format, completion protocol, file conventions) into a common contract, leaving only Codex-specific mechanics (CLI flags, environment setup) in the Codex-specific file.

### 4. Remove thin-section deepening (Clavain-dh6)
Lines 79-109 of `synthesize.md` implement "thin-section deepening" — automatically re-researching sections that seem underdeveloped. This adds complexity without proportional value. The user can always ask for more depth manually.

### 5. Remove token trimming (Clavain-1va)
`launch.md` includes manual token trimming logic that was written when context windows were 8-32K tokens. With 200K context windows now standard, this complexity is unnecessary ballast.

## Verification

All five issues confirmed present in `bd list` output alongside existing P0-P3 issues. The new issues slot in at P2 priority, between the existing P1 operational fixes and P3 housekeeping tasks.

Total open issues after creation: 15 (3 P0, 4 P1, 5 P2, 3 P3).
