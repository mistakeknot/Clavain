---
artifact_type: card
card_version: 1
project: clavain
status: confirmed
confirmed_by: mk
confirmed_at: 2026-09-14
line: "Engineer whose AI assistants skip discipline"
fields:
  persona:
    state: confirmed
    value: "The author: one product-minded engineer running a personal rig (inner circle; plugin community and the wider field are secondary)"
    evidence:
      - { path: "docs/PRD.md:48", scope: project }
      - { path: "docs/PRD.md:44", scope: project }
  pain:
    state: confirmed
    value: "AI coding assistants are powerful but undisciplined: work skips review, agent output goes unchecked, context is lost between sessions, and multi-agent coordination has no measurement"
    evidence:
      - { path: "docs/PRD.md:54", scope: project }
      - { path: "docs/PRD.md:55", scope: project }
      - { path: "docs/PRD.md:58", scope: project }
  cuj:
    state: declined
    reason: "No CUJ file exists in the repo; docs/cujs/ is absent"
    needs: "A written journey for the author taking one change from brainstorm to landed"
  success:
    state: confirmed
    value: "Cost per landed change trends down, and the human override rate stays under 30%"
    evidence:
      - { path: "docs/PRD.md:189", scope: project }
      - { path: "docs/PRD.md:188", scope: project }
  guardrail:
    state: confirmed
    value: "No measurable regression on orchestration, reasoning quality or token efficiency unless offset by a larger quantified gain"
    evidence:
      - { path: "AGENTS.md:23", scope: project }
decisions: []
---

Clavain turns one engineer's AI coding assistants into a disciplined agency: work is planned, reviewed and verified before it lands, and the rig measures whether that discipline is paying for itself.

Drafted by an agent from in-repo citations while working bead mk-qozg and confirmed by mk on 2026-09-14. The PRD marks defect escape rate as "Baseline TBD" (docs/PRD.md:187), so only the metrics with a stated direction or threshold are in `success`; the cost metric has a direction but no baseline yet. `cuj` is declined because no journey file exists.
