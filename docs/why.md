---
artifact_type: card
card_version: 1
project: clavain
status: confirmed
confirmed_by: mk
confirmed_at: 2026-09-25
line: "One engineer shipping with undisciplined agents"
fields:
  persona:
    state: confirmed
    value: "One product-minded engineer who builds software with agents (single operator through v2)"
    evidence:
      - { path: "docs/PRD.md:48", scope: project }
      - { path: "docs/PRD.md:40", scope: project }
      - { path: "docs/clavain-vision.md:164", scope: project }
  pain:
    state: confirmed
    value: "AI coding agents are undisciplined: work skips review, output goes unchecked, context is lost between sessions, and multi-agent value can't be measured"
    evidence:
      - { path: "docs/PRD.md:54-59", scope: project }
  cuj:
    state: declined
    reason: "No CUJ file exists; the closest journey is the first-sprint target stated in the vision doc, which is prose, not a CUJ"
    needs: "A CUJ for the core sprint loop, or mk accepting the vision's first-sprint target as the journey"
    evidence:
      - { path: "docs/clavain-vision.md:147", scope: journey }
  success:
    state: confirmed
    value: "Human override rate below 30%, and cost per landed change trending down"
    evidence:
      - { path: "docs/PRD.md:185-191", scope: project }
  guardrail:
    state: confirmed
    value: "Defect escape rate must not rise; token savings count only with quality held constant"
    evidence:
      - { path: "docs/clavain-vision.md:521", scope: project }
      - { path: "docs/clavain-vision.md:527", scope: project }
decisions: []
---

# Why Clavain

Clavain is the rig one engineer uses to ship software with AI agents without
losing discipline: every change goes through review, verification and
receipted routing. mk confirmed the card on 2026-09-25. The
success targets come from the PRD's Track B/C table, whose defect-escape
baseline is still to be determined.
