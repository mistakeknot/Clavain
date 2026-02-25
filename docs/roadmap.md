# Clavain Roadmap

**Version:** 0.6.88
**Last updated:** 2026-02-24
**Vision:** [`docs/vision.md`](vision.md)
**PRD:** [`docs/PRD.md`](PRD.md)
**Strategic context:** [Demarch Roadmap](../../../docs/demarch-roadmap.md)

> Auto-generated from beads + project state. Refresh with `/interpath:roadmap`.

## Where We Are

**Components:** 16 skills, 46 commands, 4 agents, 8 hooks, 1 MCP server
**Beads:** 402 open, 49 blocked, 1880 closed (2305 total)
**Recent:** Interspect extracted to companion plugin, bead auto-close hook shipped, install.sh rewritten, agency specs (C1) completed

### What's Working

- Full sprint lifecycle (brainstorm through ship) with phase gates
- 32 companion plugins as drivers (Interverse constellation)
- Intercore kernel backing durable run/dispatch/event state
- Interspect profiler extracted to standalone companion (autonomous routing proposals)
- Multi-agent review via flux-drive (7 domain-specific agents)
- Cross-AI peer review (Oracle/GPT escalation via interpeer)
- Auto-publish on push, auto-compound on stop, auto-drift-check
- Bead auto-close on git push (new: `bead-auto-close.sh`)
- Install script with modpack-based Interverse installation

### What's Not Working Yet

- Bash-heavy L2 logic (hooks/lib-sprint.sh, lib-signals.sh) — fragile, hard to test
- No CI pipeline or critical-path test coverage
- First-stranger experience still incomplete (install flow gaps)
- No cost-per-landable-change baseline metric
- Self-building loop (C5) blocked on composer (C3) and handoff protocol (C4)

## Roadmap

### Now (P0-P1)

| ID | Title | Status |
|----|-------|--------|
| iv-t712t | First-stranger experience — README, install, clavain setup | epic, open |
| iv-1opqc | First-run validation on clean environment | open |
| iv-be0ik | CI pipeline + critical-path test coverage | epic, open |
| iv-1xtgd | Bash-Heavy L2 Logic Migration | epic, open |
| iv-1xtgd.2 | Enforce shell hardening baseline for hooks and scripts | blocked by iv-1xtgd |
| iv-b46xi | Measure north star — cost-per-landable-change baseline | blocked by iv-xftvq |
| iv-xftvq | Hook Cutover — migrate remaining temp-file hooks to ic kernel | epic, blocked |
| iv-zsio | Integrate full discovery pipeline into sprint workflow | open |
| iv-kpoz8 | Bead lifecycle reliability — auto-close parents + universal claiming | open |
| iv-4xnp4 | C1 Agency specs — unblock Track C convergence | epic, open |
| iv-9hx1t | Go Module Path Alignment (Demarch Reorg) | epic, open |
| iv-jay06 | Formalize interbase as a Multi-Language SDK | epic, open |
| iv-ip4zr | Autarch self-hosting: make usable for developing Demarch | epic, open |

### Next (P2)

| ID | Title | Status |
|----|-------|--------|
| iv-e8dg | Migrate Clavain to consume flux-drive Python library | blocked by iv-0etu |
| iv-ia66 | Extract domain detection library | blocks iv-0etu |
| iv-ho3 | StrongDM Factory Substrate — validation-first infrastructure | epic, open |
| iv-6u3s | Sprint Scan Release Visibility | open |
| iv-qlt8 | Unify duplicated command entry points across Clavain/modules | closed children |
| iv-c2b4 | /interspect:disable command | open |
| iv-g0to | /interspect:reset command | open |

### Later (P3-P4)

| ID | Title | Status |
|----|-------|--------|
| iv-6ixw | C5: Self-building loop — Clavain runs its own sprints | blocked by iv-1vny, iv-240m |
| iv-240m | C3: Composer — match agency specs to fleet within budget | blocks iv-6ixw |
| iv-1vny | C4: Cross-phase handoff protocol — structured contracts | blocks iv-6ixw |
| iv-i198 | B3: Adaptive routing — Interspect outcomes drive selection | open |
| iv-d6vf | B2: Zero-cost routing abstraction + shadow mode | open |
| iv-4xqu | Adaptive model routing based on measured trust | open |
| iv-a0mv | Sprint completion rate tracking | open |
| iv-8hhd | Fix dotfiles-sync.sh log path — /var/log not writable | bug |
| iv-6i37 | Blueprint distillation: channel optimization for sprint intake | planned |
| iv-u2pd | Arbiter extraction Phase 2: spec sprint sequencing | blocked |
| iv-d5hz | Extract Coldwine task orchestration to Clavain skills (v2) | blocked |
| iv-bkzf | Arbiter extraction Phase 3 | blocked |
| iv-k1q4 | Coldwine: intent submission to Clavain OS | blocked |
| iv-1quv | Add TTL cleanup for /tmp/clavain-* sentinel files | open |
| iv-eqbo | Add Conductor-style project init wizard to /clavain:init | open |
| iv-d8yi | Add inherit model tier to Clavain model routing | open |
| iv-64j3 | Multi-agent sprint reflection (N artifacts for N dispatches) | open |

## Research Agenda

- **Token-efficient orchestration** (iv-1zh2 series): Lead-orchestrator + worker roles, cross-model specialization, complexity-based dispatch, artifact-first handoffs, context compaction, lazy skill loading. 7 brainstorm subtasks strategized.
- **Flux-drive library extraction** (iv-ia66 → iv-0etu → iv-e8dg → iv-rpso): Domain detection → scoring library → Clavain migration → full pipeline. Phase 2 next.
- **Agent communication patterns** (iv-5leh): Hook-level agent comms for intra-session coordination.
- **ADL discipline extensions** (iv-icqo): Research extensions for Clavain agents.
- **Sprint resilience**: Phase 1 and Phase 2 brainstorms completed. Implementation pending.

## Recently Closed

| ID | Title |
|----|-------|
| iv-asfy | C1: Agency specs — declarative per-stage agent/model/tool config |
| iv-iu31 | Remove tool-time PreToolUse binding, extract Task redirect |
| iv-1xtgd.1 | Centralize plugin discovery API and remove cache-glob duplication |
| iv-1zh2 | Brainstorm on all 7 token-efficiency findings |
| iv-qlt8.1-4 | Unified canonical commands (/status, /changelog, /doctor, /setup) |

## Keeping Current

```
Run /interpath:roadmap to regenerate from current project state.
Auto-monitored by interwatch — drift signals trigger refresh.
```
