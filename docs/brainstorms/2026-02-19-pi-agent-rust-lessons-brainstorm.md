# Lessons from pi_agent_rust for Clavain/Intercore

**Date:** 2026-02-19
**Bead:** iv-yeka (extended)
**Sources:** [research-pi-agent-rust-repo.md](../research/research-pi-agent-rust-repo.md), [research-openclaw-pi-ecosystem.md](../research/research-openclaw-pi-ecosystem.md)

---

## What We're Building

This brainstorm extracts architectural lessons from three projects in the Pi ecosystem — Pi (minimalist agent harness), pi_agent_rust (security-hardened Rust rewrite), and OpenClaw (consumer product built on Pi) — and maps them to Clavain's three-layer stack (Kernel → OS → Drivers) and roadmap (Tracks A/B/C).

## Why This Approach

The Pi ecosystem represents three distinct philosophies applied to the same problem space we're in:

1. **Pi (original)** — Radical minimalism. 4 tools, 300-word system prompt, no MCP, no sub-agents. Bet: context engineering > feature engineering. Validated by competitive Terminal-Bench 2.0 performance.

2. **pi_agent_rust** — Security-first re-architecture. 86.5K lines of Rust for the extension subsystem alone (3.2x the original codebase). Capability-gated hostcalls, trust lifecycle, adaptive dispatch, graduated enforcement rollout. The extension runtime became the product.

3. **OpenClaw** — Viral consumer product (145K+ GitHub stars). Consumes Pi as embedded SDK via `createAgentSession()`, adds messaging gateway, workspace files, skill registry. Acquired by OpenAI Feb 2026.

Each teaches something different. Pi teaches context discipline. pi_agent_rust teaches infrastructure hardening. OpenClaw teaches SDK embedding. oh-my-pi (a fork that adds LSP, subagents, model roles without touching the core loop) validates the extensibility thesis.

---

## Key Decisions

### 1. Don't move to Rust

**What pi_agent_rust achieved:** 3-5x faster sessions vs Node, 8-13x lower memory, sub-20ms resume for 1M-token sessions, zero unsafe code.

**Why it doesn't apply to us:**

| Factor | pi_agent_rust | Clavain/Intercore |
|--------|--------------|-------------------|
| Language replaced | Node.js (inherent memory/latency overhead) | Go (already compiled, predictable perf) |
| Bottleneck addressed | Session I/O, extension sandbox overhead | LLM API latency (10-30s per call) |
| State management | JSONL + sidecar + SQLite (3 systems) | SQLite WAL (1 system, already crash-safe) |
| Concurrency model | Single-user CLI, async extension sandbox | Multi-agent coordination through shared DB |
| Rewrite cost | 86.5K lines for extension subsystem alone | Would consume months on Track A/B/C work |

**The real lesson:** The extension runtime became pi_agent_rust's product — 3.2x the original codebase. For Clavain, the orchestration kernel is our product. Go is well-suited for durable state management and CLI tooling. Rust would help if we need untrusted extension sandboxing (post-C5 platform play), but that's years away and WASM/containers may be the right tool then.

**Exception:** If we ever embed local model inference (llama.cpp/candle), Rust interop is cleaner than Go CGO. Not on the current roadmap.

### 2. Adopt capability declarations now, enforce later

**What pi_agent_rust does:** Extensions declare capabilities (read, write, exec, http, events, session, ui, tool, log, env). Policy profiles (Safe/Standard/Permissive) compose capabilities into enforcement modes. Per-extension overrides layer on top.

**What we should do:**

When building C1 (agency specs), include a `capabilities` field in companion plugin manifests:

```yaml
# Example: interflux companion declaration
capabilities:
  kernel:
    - events.tail        # Read event stream
    - dispatch.spawn     # Launch review agents
    - dispatch.status    # Check agent status
  filesystem:
    - read               # Read project files for review
    - write              # Write synthesis output files
```

Don't enforce these yet — all companions remain trusted. But having the declarations means:
- Future enforcement is a config change, not a schema migration
- `ic` can validate calls against declarations in shadow mode (log violations without blocking)
- The platform play (circle 3) has a foundation for sandboxing third-party companions

**Pattern to adopt:** pi_agent_rust's graduated rollout: Shadow → LogOnly → EnforceNew → EnforceAll. Each stage can auto-rollback based on false-positive rate, error rate, or latency thresholds.

### 3. Structure adaptive routing as a decision pipeline

**What pi_agent_rust does:** Three dispatch lanes (Fast/IoUring/Compat) with zero-cost fast path when advanced features are off. CUSUM + BOCPD + SPRT statistical detectors for regime shifts. Shadow dual execution for divergence detection.

**What we should do for Track B (Model Routing):**

Structure routing as a pipeline, not a function:

```
gather signals → evaluate rules → select model → record outcome → feedback loop
```

Key patterns to adopt:

1. **Zero-cost abstraction** — When B3 (adaptive routing) is off, routing should collapse to B1's static path with zero overhead. No extra DB queries, no scoring, just config lookup. This is what pi_agent_rust's Fast lane does — the advanced machinery has zero cost when disabled.

2. **Shadow mode for routing changes** — When changing routing rules, log what the new policy *would* have selected alongside what the current policy *actually* selected. Compare outcomes over N dispatches before enforcing. pi_agent_rust does this with deterministic FNV-1a sampling at 2.5% of calls.

3. **Outcome-level detection, not infrastructure-level** — pi_agent_rust detects stall ratios and queue depth. We need to detect at the *outcome* level: defect escape rates, human override rates, cost-per-landed-change. Interspect already reads kernel events — it just needs to correlate model choice with outcome quality.

4. **Regime shift detection for model degradation** — When a model version changes or degrades silently (frontier models update without notice), we need statistical detection that a previously-good routing decision is now producing worse outcomes. CUSUM is the right tool here — it detects sustained shifts in a moving average.

### 4. Validate our three-layer architecture against the oh-my-pi pattern

**What oh-my-pi demonstrates:** A fork of Pi that adds LSP integration, subagents with full output access, model role routing, and TTSR (a novel extension mechanism) — all without modifying Pi's core agent loop. The core stayed minimal; all features were added through Pi's extension points.

**What this validates for us:**

Our three-layer architecture (Kernel → OS → Drivers) makes the same bet: the kernel provides durable primitives, the OS encodes policy, drivers wrap capabilities. If the architecture is sound, you should be able to add significant features (new agent types, new dispatch strategies, new review protocols) without modifying the kernel.

oh-my-pi's success validates this pattern empirically:
- **LSP integration** = new driver capability (comparable to adding a new companion plugin)
- **Subagents** = orchestration feature added at the OS layer (comparable to Clavain's sub-agent dispatch)
- **Model roles** = routing policy added at the OS layer (comparable to Track B)
- **Core loop untouched** = kernel integrity preserved

The risk to watch: feature creep into the kernel. pi_agent_rust's extension subsystem grew to 3.2x the original codebase. If Intercore's primitives accumulate too many "just this one more thing" additions, the kernel loses its mechanism-not-policy identity. Decision filter: "Does this belong in `ic` (kernel) or in a Clavain hook/skill (OS)?"

### 5. Learn from Pi's context engineering discipline

**What Pi demonstrates:** Competitive performance on Terminal-Bench 2.0 with 4 tools and a 300-word system prompt. Mario Zechner's thesis: frontier models are "RL-trained up the wazoo" and don't need 10,000-token system prompts.

**What this means for Clavain:**

We're not going to adopt Pi's minimalism — our multi-agent orchestration requires skills, hooks, and companion context that Pi deliberately rejects. But the context engineering principle is valid:

- **Progressive disclosure works** — Pi's skills load on demand, not at session start. Clavain already does this (skills load when invoked), but session-start hooks inject significant context (~2K tokens of `using-clavain` skill). Audit what's in that context and whether all of it is needed for every session.

- **Context budget as constraint** — Pi treats context as a scarce resource to be optimized. Clavain treats it as a delivery mechanism for discipline. Both can be true — but we should measure. How much of the session-start context actually influences model behavior? This is a Track B research question.

- **Extension events > system prompt** — Pi's `context` event lets extensions rewrite the message list per turn. This is more powerful than injecting static system prompt content. If Clavain builds richer hook events (Track A), consider per-turn context injection as an alternative to session-start bulk loading.

### 6. Adopt pi doctor's fluent finding pattern for /clavain:doctor

**What pi_agent_rust does:** Six scoped diagnostic categories (Config, Dirs, Auth, Shell, Sessions, Extensions). Fluent finding builder with severity levels, detail, remediation hints, and auto-fixable flag. Three output formats (text, JSON, markdown). Auto-remediation with severity downgrade on success.

**What we should improve:**

`/clavain:doctor` currently does ad-hoc checks. Adopt the structured pattern:

- **Scoped categories**: companions, hooks, MCP servers, beads, kernel, permissions
- **Finding severity**: Pass < Info < Warn < Fail (enables `max()` aggregation for overall health)
- **Auto-remediation**: When `--fix` is passed, attempt repair and downgrade severity to Pass. Example: missing directory → create it; stale plugin cache → reinstall
- **Machine-readable output**: JSON format enables programmatic health checks (CI, session-start hooks, monitoring)

This is a small improvement with high leverage — doctor runs every session start and every PR.

---

## Open Questions

1. **Capability declaration schema**: Should companion capabilities be declared in plugin.json (static, validated at install) or in a runtime registration call (dynamic, validated at first use)?

2. **Shadow routing telemetry storage**: Where do shadow routing decisions get stored? In the kernel event bus (typed events) or in Interspect's profiling database?

3. **Context budget measurement**: How do we measure the impact of session-start context on model behavior? A/B test with reduced context? Or track which context tokens the model actually references in its responses?

4. **Kernel primitive creep signal**: What's the objective criterion for "this belongs in the kernel" vs "this belongs in the OS"? Pi drew the line at 4 tools. We drew it at "durable state operations." Is that boundary sharp enough?

---

## Summary of Takeaways

| Lesson | Source | Applies To | Priority |
|--------|--------|-----------|----------|
| Don't rewrite to Rust | pi_agent_rust | Infrastructure | Decision (closed) |
| Capability declarations in companion manifests | pi_agent_rust security model | C1 (agency specs) | Do now (schema only) |
| Graduated enforcement rollout | pi_agent_rust SEC-7.2 | C1+ (future enforcement) | Design now, implement later |
| Zero-cost adaptive routing abstraction | pi_agent_rust dispatch lanes | B2-B3 (model routing) | Design into B2 |
| Shadow mode for routing changes | pi_agent_rust shadow dual execution | B2-B3 (model routing) | Design into B2 |
| Outcome-level regime shift detection | pi_agent_rust CUSUM+BOCPD+SPRT | B3 (adaptive routing) | Research item |
| Three-layer architecture validated | oh-my-pi fork success | Architecture confidence | Validated |
| Guard against kernel primitive creep | pi_agent_rust extension subsystem growth | Intercore governance | Ongoing vigilance |
| Context engineering as measurable discipline | Pi's 300-word system prompt thesis | Track B research | Research item |
| Structured doctor diagnostics | pi_agent_rust doctor.rs | /clavain:doctor | Small improvement |
