# Background

## Who this Is for

Clavain serves three concentric circles, inner circle first:

1. **My personal rig.** Optimized relentlessly for my workflow and projects. The primary goal is to make a single person as effective as a full team without losing the parts of building I find fun and important.
2. **Reference implementation.** Shows what's possible with disciplined multi-agent engineering and sets conventions for plugin structure, skill design, and agent orchestration.
3. **Research artifact.** Demonstrates what disciplined human-AI collaboration looks like in practice by solving real problems under real constraints and publishing the results.

Clavain is not the best workflow for everyone, but it can, at the very least, provide some inspiration for your own approach to Claude Code.

## Philosophy

Most agent tools skip the product phases: brainstorm, strategy, specification: and jump straight to code generation. Clavain makes them first-class. The brainstorm and strategy phases are real product capabilities, not engineering context-setting.

A few operating principles that shape every design decision:

**Refinement > production.** The review phases matter more than the building phases. Resolving ambiguity during planning is far cheaper than dealing with it during execution.

**Composition > integration.** Small, focused tools composed together beat large integrated platforms. The inter-\* constellation, Unix philosophy, modpack metaphor: it's turtles all the way down.

**Human attention is the bottleneck.** Optimize for the human's time, not the agent's. Multi-agent output must be presented so humans can review quickly and confidently, not just cheaply.

**Multi-AI > single-vendor.** No one model is best at everything. Clavain is built on Claude Code and uses Codex and Oracle-style review as complements: architecturally multi-model while remaining platform-native.

**Discipline before automation.** Encode judgment into checks before removing the human. Agents without discipline ship slop.

The full set of operating principles and the project roadmap live in [`vision.md`](vision.md).

## Development model

**Clavain-first, then generalize out.** Capabilities are built tightly integrated, battle-tested through real use, and only extracted into companion plugins when the patterns stabilize. The inter-\* constellation represents crystallized research outputs: each companion started as a tightly-coupled feature inside Clavain that earned its independence through repeated, successful use.

This inverts the typical "design the API first" approach: build too-tightly-coupled on purpose, discover the natural seams through practice, and only then extract.

| Companion | Crystallized Insight |
|---|---|
| interphase | Phase tracking and gates are generalizable |
| interflux | Multi-agent review is generalizable |
| interline | Statusline rendering is generalizable |
| interpath | Product artifact generation is generalizable |
| interwatch | Doc freshness monitoring is generalizable |

## What Clavain Is not

**Not a framework.** The inter-\* constellation offers composable pieces anyone can adopt independently, but Clavain itself is not designed to be "framework-agnostic" or "configurable for any workflow." It is an opinionated rig that also happens to produce reusable components.

**Not for non-builders.** Clavain is for people who build software with agents. It is not a no-code tool, not an AI assistant for non-technical users, not a chatbot framework.

**Platform-native, not vendor-neutral.** Clavain is built on Claude Code. It dispatches to Codex CLI, Oracle-style review, and other model lanes as complements, but it is not trying to be a universal agent orchestrator for any LLM platform.
