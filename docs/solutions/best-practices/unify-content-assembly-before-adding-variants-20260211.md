---
module: FluxDrive
date: 2026-02-11
problem_type: best_practice
component: tooling
symptoms:
  - "Diff slicing and pyramid mode solve the same problem with different mechanisms"
  - "Two parallel content-assembly paths double maintenance and testing surface"
  - "Orchestrator must hold logic for both systems in working context (~200 extra lines)"
root_cause: missing_workflow_step
resolution_type: workflow_improvement
severity: high
tags: [flux-drive, content-assembly, diff-slicing, pyramid-mode, abstraction, strongdm]
---

# Unify Content-Assembly Abstractions Before Adding Variants

## Problem

During flux-drive review of 3 StrongDM-inspired design docs, all 3 review agents (fd-architecture, fd-performance, fd-user-product) independently converged on the same finding: **diff slicing** (for large diffs) and the proposed **pyramid mode** (for large files/directories) are the same abstraction applied to different input types.

Both solve: "How to give each agent a subset of content relevant to their domain while compressing the rest."

| Aspect | Diff Slicing | Pyramid Mode |
|--------|-------------|--------------|
| Input type | Diffs (>= 1000 lines) | Files/directories (> 500 lines) |
| Routing | File pattern + keyword matching | Section-to-domain keyword mapping |
| Content delivery | Priority hunks (full) + context summaries | Overview + domain-expanded sections |
| Expansion | "Request full hunks" annotation | "Request expansion: [section]" annotation |
| Metadata | `[Diff slicing active: ...]` | `[Pyramid mode: ...]` |

Building pyramid mode as a second system would mean:
- Two content-assembly code paths in the orchestrator
- Two metadata formats in shared-contracts.md
- Two convergence-counting adjustments in synthesize.md
- Double the testing surface for content-routing bugs

## Root Cause

The diff slicing system was built for a specific input type without abstracting the underlying pattern. When a new input type (files/directories) needed the same treatment, the natural path was to build a parallel system rather than generalize the existing one.

## Solution

Define a single **ContentSlice** abstraction that both producers feed into:

```
ContentSlice {
  overview: string           // Compressed summary of all content
  domain_sections: Map<agent, string[]>  // Full content relevant to each agent
  metadata: string           // Slicing/pyramid metadata line
  expansion_requests: string[] // Agent requests for more content
}
```

Two producers:
- `DiffSlicer` — produces ContentSlice from diff inputs using file patterns + keywords
- `PyramidScanner` — produces ContentSlice from file/directory inputs using section-to-domain mapping

The prompt template in launch.md consumes ContentSlice uniformly. Synthesis handles one convergence model, not two.

## Key Insight

This mirrors StrongDM's Attractor architecture: the graph structure (container) is uniform regardless of whether the payload is a diff, a document, or a codebase scan. The container is the abstraction; only the content producer changes.

## Prevention

Before building a variant of an existing system for a new input type:
1. Check if the existing system can be generalized with a shared interface
2. If the core operation is the same (route relevant content, compress the rest), unify first
3. Build the abstraction before the second variant, not after

## Investigation Notes

- 3/3 review agents flagged this independently — highest convergence finding in the review
- fd-performance noted the orchestrator holds both systems' logic, consuming ~200 extra lines of working context
- fd-architecture proposed the ContentSlice abstraction
- fd-performance recommended instrumenting token usage on the existing system before building either enhancement

## Files Referenced

- `skills/flux-drive/SKILL.md` — main orchestration
- `skills/flux-drive/phases/launch.md` — agent dispatch (would need 3 content modes without unification)
- `skills/flux-drive/phases/shared-contracts.md` — Diff Slicing Contract (lines 57-88) is the template
- `config/flux-drive/diff-routing.md` — domain keywords that both systems should share
- `docs/research/pyramid-mode-flux-drive.md` — pyramid mode design doc
- `docs/research/flux-drive/strongdm-techniques/summary.md` — full review findings
