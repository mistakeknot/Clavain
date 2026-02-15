# interflux Source File Survey — Flux-Drive Protocol

Analysis of interflux flux-drive source files for protocol spec development.
Generated: 2026-02-14

## File Size and Content Analysis

| File | Lines | Type | Protocol Knowledge | Implementation |
|------|-------|------|-------------------|-----------------|
| `/root/projects/interflux/skills/flux-drive/SKILL.md` | 415 | Master skill | Complete orchestration contracts, phase routing, input classification, agent triage scoring algorithm (7-point scale), domain detection integration, slot allocation formula, Stage 1/Stage 2 routing rules, cross-AI integration points | Input handling, OUTPUT_DIR resolution, Phase 1-4 sequencing |
| `/root/projects/interflux/skills/flux-drive/phases/launch.md` | 454 | Phase file | Task dispatch contracts, monitoring protocol, completion signal format (`.md.partial` → `.md`), research escalation rules (max 1 per review, 60s timeout), domain-aware expansion scoring, adjacency map, per-agent content delivery templates, slicing activation rules | Agent launch mechanics, background Task calls, polling loops (30s intervals, 5m timeout) |
| `/root/projects/interflux/skills/flux-drive/phases/synthesize.md` | 365 | Phase file | Output format contracts (Findings Index structure), deduplication rules, convergence tracking, verdict logic (P0→risky, P1→needs-changes), findings.json schema, beads creation rules, knowledge compounding protocol (provenance rules, decay at 10 reviews), slicing report templates | Write strategies per input type, file I/O for summary.md, bead creation bash loops |
| `/root/projects/interflux/skills/flux-drive/phases/shared-contracts.md` | 69 | Contract reference | Findings Index format (SEVERITY \| ID \| "Section" \| Title), completion signal (`<!-- flux-drive:complete -->`), error stub format, output trimming rules (strip examples, Output Format sections, personality), monitoring contract (30s polling, 5m timeout, completion detection), content slicing contracts | File path conventions, prompt construction rules, retries |
| `/root/projects/interflux/skills/flux-drive/phases/slicing.md` | 366 | Slicing spec | Cross-cutting agent rules (fd-architecture, fd-quality always full), domain-specific routing patterns (5 agents × file patterns + hunk keywords), 80% overlap threshold, safety override for secrets, section classification (priority vs context), per-agent temp file structure, synthesis rules (convergence adjustment, out-of-scope discovery tags), slicing metadata format | File enumeration, keyword matching, content compression, diff parsing, line counting |
| `/root/projects/interflux/skills/flux-drive/references/scoring-examples.md` | 67 | Reference | Triage scoring worked examples (4 document types), base/domain/project/agent bonus breakdown, slot allocation formulas, thin-section thresholds (< 5 lines = thin), scoring table format | Examples for training |
| `/root/projects/interflux/scripts/detect-domains.py` | 713 | Python utility | Domain detection algorithm (4-tier weighted scoring: 0.3 dirs, 0.2 files, 0.3 frameworks, 0.2 keywords), cache format (CACHE_VERSION=1), staleness detection (3-tier: hash → git → mtime), structural hash computation, confidence thresholds per domain | File I/O, YAML parsing, dependency extraction, keyword scanning, git log integration |
| `/root/projects/interflux/config/flux-drive/domains/index.yaml` | 454 | Config | 10 domain profiles (game-simulation, ml-pipeline, web-api, cli-tool, mobile-app, embedded-systems, library-sdk, data-pipeline, claude-code-plugin, tui-app), min_confidence thresholds (0.3-0.35), signal definitions (directories, files, frameworks, keywords per domain) | YAML structure, domain bootstrap data |
| `/root/projects/interflux/config/flux-drive/knowledge/README.md` | 79 | Knowledge spec | Entry format (YAML frontmatter + body), frontmatter fields (lastConfirmed, provenance), decay rules (10 reviews → archive), sanitization rules (heuristics only), provenance rules (independent vs primed), retrieval via qmd (5 entries/agent cap) | Knowledge lifecycle documentation |

**Total source lines:** 2,982 lines

## Protocol Coverage Summary

### Complete Protocols (>100 lines of spec)
1. **Agent Triage & Scoring** (SKILL.md + scoring-examples.md, 482 lines)
   - Dynamic slot allocation algorithm
   - 7-point scoring scale with bonuses
   - Pre-filter rules per agent
   - Stage assignment logic

2. **Task Dispatch & Monitoring** (launch.md + shared-contracts.md, 523 lines)
   - Findings Index output format
   - Completion signals and retries
   - Polling contract (30s intervals, 5m timeout)
   - Knowledge context injection
   - Domain context injection

3. **Content Slicing** (slicing.md, 366 lines)
   - Cross-cutting vs domain-specific routing
   - File/section classification per agent
   - 80% overlap threshold and safety override
   - Synthesis convergence adjustments
   - Out-of-scope discovery tags

4. **Domain Detection** (detect-domains.py + index.yaml + SKILL.md Step 1.0, ~600 lines)
   - 4-tier weighted scoring (0.3 dirs, 0.2 files, 0.3 frameworks, 0.2 keywords)
   - Cache format and staleness checks (hash → git → mtime)
   - 10 domain profiles with signal definitions
   - Injection criteria per agent per domain

5. **Synthesis & Knowledge** (synthesize.md + knowledge README, 444 lines)
   - Findings deduplication and convergence tracking
   - Verdict logic (P0/P1/P2 severity map)
   - findings.json schema
   - Knowledge entry format and decay protocol
   - Compounding rules (independent vs primed provenance)

### Partial/Reference Protocols
- **Beads Integration** (synthesize.md Step 3.6, 60 lines) — creation only, not lifecycle
- **Research Escalation** (launch.md Step 2.2a, 25 lines) — brief mention, full spec elsewhere
- **Project Agent Generation** (SKILL.md Step 1.0.4, 30 lines) — generation triggers, templates elsewhere

## Cross-Cutting Concerns

### Error Handling
- Retry logic (Step 2.3): failed agents → re-launch with `run_in_background: false`, 5m timeout
- Error stub format: `Verdict: error` line + message
- Graceful fallback: missing qmd → agents run without knowledge, missing domains → core agents only

### Token Budget Management
- Slicing for documents ≥200 lines (document slicing) and diffs ≥1000 lines (diff slicing)
- Prompt trimming rules: strip examples, Output Format sections, personality
- Temp file approach: write content once, agents Read (eliminates duplication)
- Knowledge cap: 5 entries/agent, 3 domains max per agent

### State Tracking
- Findings Index format enables index-first synthesis (read ~30 lines per agent)
- Slicing metadata stored per agent (section_map, slicing_map)
- Convergence counts per finding
- findings.json captures full structure for post-review analysis

## Protocol Entry Points

1. **Input**: User provides `INPUT_PATH` (file, directory, or diff)
2. **Triage** (SKILL.md + scoring-examples.md): Project → Domain → Agents → Stages
3. **Launch** (launch.md): Prepare content → Dispatch Stage 1 → Poll → Expand
4. **Synthesize** (synthesize.md): Validate → Collect Index → Deduplicate → Report
5. **Knowledge** (synthesize.md Step 3.6 + knowledge README): Compound findings → Archive decay

## Key Configuration Files

- **index.yaml**: Domain definitions (10 profiles, 454 lines)
- **detect-domains.py**: Detection algorithm (713 lines)
- **knowledge/README.md**: Entry format and lifecycle (79 lines)
- *Domain profiles*: `config/flux-drive/domains/{game-simulation,ml-pipeline,web-api,...}.md` (not surveyed here — referenced as injection criteria)

## Data Structures

### Findings Index
```
### Findings Index
- SEVERITY | ID | "Section Name" | Title
Verdict: safe|needs-changes|risky
```

### findings.json
```json
{
  "reviewed": "YYYY-MM-DD",
  "input": "path",
  "agents_launched": ["agent1"],
  "agents_completed": ["agent1"],
  "findings": [{"id": "P0-1", "severity": "P0", "agent": "...", "convergence": 3}],
  "improvements": [...],
  "verdict": "needs-changes",
  "early_stop": false
}
```

### Cache (flux-drive.yaml)
```yaml
cache_version: 1
domains: [{name: "game-simulation", confidence: 0.65, primary: true}]
detected_at: "2026-02-14T15:30:00+00:00"
structural_hash: "sha256:abc123..."
override: false
```

### Knowledge Entry
```yaml
---
lastConfirmed: 2026-02-10
provenance: independent
---
Auth middleware swallows context cancellation errors.

Evidence: middleware/auth.go:47-52
Verify: grep for ctx.Err() after http.Do() calls
```

## Specification Readiness

**Status**: ~85% ready for protocol spec

**Fully specified:**
- Triage scoring algorithm (deterministic, 7-point scale)
- Output format (Findings Index, findings.json, completion signals)
- Monitoring contract (polling intervals, timeout, retry logic)
- Content slicing routing (file/section patterns, priority keywords)
- Domain detection scoring (4-tier weighted formula)
- Knowledge decay (10 reviews → archive)

**Partially specified:**
- Research escalation (trigger conditions exist, but escalation agent dispatch logic brief)
- Beads integration (creation rules clear, but lifecycle/deduplication outside scope)
- Cross-AI comparison (Phase 4 referenced but spec in separate file)

**Missing/External:**
- Domain profiles (11 files with injection criteria — not surveyed)
- Project agent generation template (referenced but full template elsewhere)
- Oracle integration details (Clavain companion plugin)
- Cross-AI comparison phase (referenced as optional, spec in other file)

## Size Summary

- **SKILL.md**: 415 lines — master orchestration, input/output, phase routing
- **launch.md**: 454 lines — dispatch contracts, monitoring, expansion logic
- **synthesize.md**: 365 lines — output validation, deduplication, beads, knowledge
- **shared-contracts.md**: 69 lines — Findings Index format, completion signals, retries
- **slicing.md**: 366 lines — routing patterns, classification, synthesis adjustments
- **scoring-examples.md**: 67 lines — worked examples and thresholds
- **detect-domains.py**: 713 lines — detection algorithm + staleness check
- **index.yaml**: 454 lines — 10 domain profiles with signals
- **knowledge/README.md**: 79 lines — entry format, lifecycle, provenance rules

**Total: 2,982 lines of protocol + implementation source**

## Spec Development Recommendations

1. **Separate concerns**: Split triage (scoring) from dispatch (launch) — they have different audience (triage is deterministic; dispatch is implementation detail)
2. **Highlight deterministic vs heuristic**: Triage scoring is fully deterministic (section classifiers are more heuristic). Make this explicit.
3. **Document contracts as machine-readable**: Findings Index and findings.json can become JSON Schema or Protobuf for formal validation.
4. **Extract domain profiles**: 11 domain files (not surveyed) should be referenced in spec but kept as config examples.
5. **Address optional features**: Phase 4 (cross-AI), research escalation, and beads integration are well-integrated but optional. Make optionality explicit.
