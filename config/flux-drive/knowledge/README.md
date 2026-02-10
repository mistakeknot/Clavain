# Flux-Drive Knowledge Layer

Knowledge entries discovered during flux-drive reviews. Each file is a markdown document with YAML frontmatter.

## Entry Format

```yaml
---
lastConfirmed: 2026-02-10
provenance: independent
---
Auth middleware swallows context cancellation errors.
Both Safety agent and Oracle flagged this independently.

Evidence: middleware/auth.go:47-52, handleRequest() — context.Err() not checked after upstream call.
Verify: grep for ctx.Err() after http.Do() calls in middleware/*.go.
```

### Frontmatter Fields

| Field | Values | Purpose |
|-------|--------|---------|
| `lastConfirmed` | ISO date (YYYY-MM-DD) | Last time this finding was independently re-observed |
| `provenance` | `independent` or `primed` | Whether the confirming agent had this entry in context |

### Body Requirements

- **Finding description**: 1-3 sentences describing the pattern or issue
- **Evidence anchors**: File paths, symbol names, line ranges — concrete pointers to the finding
- **Verification steps**: 1-3 steps to confirm the finding is still valid

Entries without evidence anchors rot into unverifiable folklore. Always include concrete pointers.

## Provenance Rules

The `provenance` field prevents a **false-positive feedback loop**:

```
Finding compounded → injected into next review → agent re-confirms (primed)
→ lastConfirmed updated → entry never decays → false positive permanent
```

- **`independent`**: Agent flagged this WITHOUT seeing the knowledge entry (genuine re-confirmation). Updates `lastConfirmed`.
- **`primed`**: Agent had this entry in its context when it re-flagged it (not a true confirmation). Does NOT update `lastConfirmed`.

Only independent confirmations refresh the decay timer.

## Decay Rules

- Entries not independently confirmed in **10 reviews** get archived
- Archived entries are moved to `config/flux-drive/knowledge/archive/`
- Archive preserves the full entry for future reference

## Sanitization Rules

Global entries must be phrased as **generalized heuristics**. Never store:
- File paths to specific repos (outside Clavain)
- Hostnames or internal endpoints
- Organization names or customer identifiers
- Secrets or credentials
- Vulnerability details with exploitable specifics

**Good**: "Auth middleware often swallows context cancellation errors — check for ctx.Err() after upstream calls"
**Bad**: "middleware/auth.go in Project X has a bug at line 47"

## Manual Retraction

To retract a wrong entry: delete the file. Knowledge entries are just markdown files.

Future: `/clavain:flux-knowledge review` command for inspection, confirmation, and retraction.

## Retrieval

Knowledge is retrieved via qmd semantic search during flux-drive Phase 2 (Launch):
- Cap: 5 entries per agent
- Query: agent domain keywords + document summary
- Pipelined with agent launch (not during triage)
- If qmd unavailable, agents run without knowledge injection
