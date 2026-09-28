---
artifact_type: card
card_version: 1
project: clavain
status: confirmed
confirmed_by: mk
confirmed_at: 2026-09-27
line: "Engineer whose agent output ships unchecked"   # 43 chars
fields:
  persona:
    state: confirmed
    value: "The author — one product-minded engineer running a personal agent rig"
    evidence:
      - { path: "docs/PRD.md:44", scope: project }
  pain:
    state: confirmed
    value: "AI coding assistants are powerful but undisciplined: work skips review and ships unrefined, agent output goes unchecked (hallucinations, false positives, redundant findings), context is lost between sessions, and multi-agent coordination has no measurement"
    evidence:
      - { path: "docs/PRD.md:52-58", scope: project }
  cuj:
    state: declined
    reason: "No docs/cujs/ file or equivalent single-journey artifact exists in this repo. docs/PRD.md:4.3 (Lifecycle Coverage) describes phase capability, not a citable user journey."
    needs: "A CUJ file (cujgel-format or prose) for at least one lifecycle phase, e.g. brainstorm-to-ship"
  success:
    state: confirmed
    value: "Track B/C targets: human override rate < 30%, time-to-first-signal < 45s from /flux-drive, redundant-finding ratio < 20%, cost-per-landed-change trending down"
    evidence:
      - { path: "docs/PRD.md:173-186", scope: project }
  guardrail:
    state: confirmed
    value: "Improve at least one of the three frontier axes (orchestration, reasoning quality, token efficiency) without regressing whichever of the other two are not being improved, unless offset by clear, measurable gain on the one that is"
    evidence:
      - { path: "docs/PRD.md:16-30", scope: project }
decisions: []
---

# Clavain

Clavain is an autonomous software agency that orchestrates the full
development lifecycle — problem discovery through shipped code — using
heterogeneous AI models selected for cost, capability, and task fit
(docs/PRD.md:11). It exists because AI coding assistants are powerful but
undisciplined: without structure, work skips review and ships unrefined,
agent output goes unchecked, context is lost between sessions, and nobody can
tell whether more agents are actually helping (docs/PRD.md:52-58).

Today it is built for its author — one product-minded engineer running Clavain
as a personal rig — with the Claude Code plugin community and the wider
AI-assisted development field as secondary audiences who get a reference
implementation and a research artifact, respectively (docs/PRD.md:39-44).

One field is honestly unresolved: `cuj` has no citable single-journey file in
this repo yet (declined, not invented). `success` and `guardrail` cite real
project-scope targets (docs/PRD.md §7.2), though that section's own framing
notes no baseline is measured against them yet (docs/PRD.md §7.1,
"pre-analytics") — that gap is Track B/C work, not settled fact.
