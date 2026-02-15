# Interspect — Design Document

**Date:** 2026-02-15
**Status:** Brainstorm → Design (pre-implementation)
**Module:** interspect (planned companion extraction from Clavain)

---

## 1. What Interspect Is

Interspect is Clavain's self-improvement engine — the module that makes "recursively self-improving" real rather than aspirational. It implements an OODA loop (Observe → Orient → Decide → Act) that captures evidence about Clavain's own performance and autonomously modifies skills, prompts, routing, and workflows based on that evidence.

## 2. Autonomy Model

- **Default: Full autonomy.** Interspect rewrites Clavain's own files and commits changes. The human reviews commits after the fact.
- **Optional: Propose mode.** A flag that switches the pipeline to present diffs via `AskUserQuestion` instead of committing directly. One "yes" per batch.

Interspect cannot modify its own safety gates, canary thresholds, revert logic, or autonomy mode flag. These meta-rules are human-owned.

## 3. Architecture

### 3.1 Evidence Store

**Location:** `.clavain/interspect/evidence/`
**Format:** JSONL files, one per event type, append-only, git-tracked.

```
events/overrides.jsonl      — human overrode an agent recommendation
events/false-positives.jsonl — finding dismissed as not actionable
events/corrections.jsonl    — human corrected agent output
events/token-usage.jsonl    — cost per workflow step
events/timing.jsonl         — latency per agent/workflow
events/extractions.jsonl    — capability stability signals
```

**Event schema** (common envelope):

```json
{
  "ts": "2026-02-15T14:32:00Z",
  "session_id": "abc123",
  "source": "fd-safety",
  "event": "override",
  "context": {
    "finding": "SQL injection risk in query builder",
    "verdict": "false_positive",
    "reason": "parameterized queries already used"
  },
  "project": "intermute"
}
```

**Collection points:**

| Signal | Source | How |
|--------|--------|-----|
| Human override | `AskUserQuestion` responses in review workflows | PostToolUse hook on flux-drive/quality-gates |
| False positive | Dismissed findings in `/resolve` | Hook on resolve command |
| Human correction | User edits agent output | Diff between agent output and final committed version |
| Token usage | Every agent dispatch | Wrap subagent calls with cost tracking |
| Timing | Every workflow step | Timestamps in signal engine |
| Extraction signal | Capability used across N projects without modification | Periodic batch scan |

### 3.2 Four Cadences

#### Cadence 1: Within-Session (Reactive)

**Trigger:** Immediate pattern detection during active work.
**Scope:** Session-only. Changes are in-memory. Promoted to persistent by Cadence 2 if pattern persists.
**Safety:** None needed — changes die with the session.

What it catches:
- Same override pattern twice → adjust agent prompt in-memory
- Agent producing zero actionable findings → demote for remainder of session
- Token budget blown on single agent → throttle

Mechanism: `interspect_check()` called after each review/dispatch cycle.

#### Cadence 2: End-of-Session (Pattern Sweep)

**Trigger:** Signal-weight engine, weight ≥ 3 (alongside auto-compound).
**Scope:** Persistent file changes. Atomic git commits.
**Safety:** Canary flag on modified files. Monitored next session.

What it catches:
- Session evidence + last 5 sessions' evidence → persistent modifications
- Learnings from auto-compound → auto-injected into relevant skill sidecar files
- Within-session demotions → checked for cross-session consistency

Mechanism: `interspect-sweep` hook (Stop event). Requires ≥ 2 sessions showing same pattern.

#### Cadence 3: Periodic Batch (Structural)

**Trigger:** `/interspect` command or every 10 sessions (counter in evidence store).
**Scope:** Structural changes. Can create files, modify multiple skills, propose companions.
**Safety:** Shadow testing required. Report generated before applying.

What it catches:
- Companion extraction candidates (capability stable across 5+ projects)
- Workflow pipeline optimization (low signal-to-noise steps)
- Agent topology changes (agents never producing actionable findings for a project)
- Cross-project knowledge transfer

#### Cadence 4: Threshold Gate (Confidence Filter)

Not a cadence — the confidence filter all cadences pass through.

```
confidence = f(evidence_count, cross_session_count, cross_project_count, recency)

< 0.3  → log only
0.3-0.7 → session-only (Cadence 1)
0.7-0.9 → persistent with canary (Cadence 2)
> 0.9  → persistent, skip shadow test (Cadence 2/3)
```

### 3.3 Modification Pipeline

Every self-modification flows through:

1. **Classify** — What kind of change? What's the blast radius?
2. **Generate** — Produce concrete diff to target file(s)
3. **Safety gate** — Route by risk level (low → apply, medium → canary, high → shadow test)
4. **Apply** — Atomic git commit with `[interspect]` prefix, OR present diff (propose mode)
5. **Monitor** — Tag modified files with canary metadata. Next N uses compared against baseline.
6. **Verdict** — After canary window: keep (better/neutral) or revert (worse). Log outcome as evidence.

### 3.4 Risk Classification

| Change Type | Risk | Safety Gate |
|------------|------|-------------|
| Context injection (sidecar append) | Low | Apply directly |
| Model routing weight adjustment | Low | Canary |
| Agent prompt modification | Medium | Canary |
| Skill SKILL.md rewrite | Medium | Shadow test |
| Agent add/remove from triage | High | Shadow test |
| Companion extraction scaffold | High | Shadow test + report |
| Hook logic modification | High | Shadow test |

### 3.5 Shadow Testing

For medium/high-risk changes:
1. Pick 3-5 recent real inputs from evidence store
2. Run old prompt/skill → capture output
3. Run new prompt/skill → capture output
4. Compare via LLM-as-judge: same correct findings? Fewer false positives? Missed catches?
5. Score and decide

### 3.6 Canary Monitoring

After applying a change, metadata is stored:

```json
{
  "file": "agents/review/fd-safety.md",
  "commit": "abc123",
  "applied_at": "2026-02-15T14:32:00Z",
  "canary_window": 5,
  "uses_remaining": 5,
  "baseline_override_rate": 0.4,
  "baseline_false_positive_rate": 0.3
}
```

If override/false-positive rate increases > 50% relative to baseline within the canary window → auto-revert and log failure as evidence.

### 3.7 Meta-Learning Loop

Interspect's own modification failures become evidence:
- "Prompt tightening for fd-safety reverted 3 times" → interspect raises risk classification for fd-safety modifications → requires shadow testing instead of canary
- Interspect improves its own improvement process

## 4. Six Modification Types

### Type 1: Context Injection
Append project/pattern-specific context to sidecar files (`interspect-context.md`) alongside skills/agents. Additive only. Worst case: irrelevant context wastes tokens.

### Type 2: Routing Adjustment
Maintain `routing-overrides.json` with agent exclusions and model overrides. Flux-drive triage reads overrides before dispatching.

### Type 3: Prompt Tuning
Surgical edits to agent `.md` files — add "Do NOT flag X when Y" clauses, strengthen attention directives, adjust severity calibration.

### Type 4: Skill Rewriting
Restructure skill flow based on evidence about which steps are valuable/skipped. Shadow testing required.

### Type 5: Workflow Pipeline Optimization
Track timing and signal-to-noise per pipeline step. Reorder, conditonalize, or merge steps with low value.

### Type 6: Companion Extraction
Detect stability signals for tightly-coupled capabilities. Scaffold companion structure. Generate extraction report. Human does actual implementation.

## 5. Key Design Decisions

1. **Evidence store is append-only JSONL, git-tracked.** Cheap, greppable, auditable.
2. **Sidecar files over prompt rewriting for context injection.** Keeps human-authored prompts clean.
3. **Git commits as the undo mechanism.** Every modification is an atomic, revertible commit.
4. **Confidence thresholds prevent premature action.** One override isn't evidence. Three across two sessions is.
5. **Meta-rules are human-owned.** Interspect cannot modify its own safety gates or autonomy mode.
6. **Shadow testing uses LLM-as-judge.** Not perfect but sufficient for a confidence gate. Canary monitoring catches what shadow testing misses.

## 6. Open Questions

- How to handle evidence store growth over time? Pruning vs. archiving vs. summarization.
- What's the right canary window size? 5 uses may be too small for rarely-triggered agents.
- How to collect "human correction" evidence without invasive diff tracking?
- Should companion extraction be fully autonomous or always propose-mode regardless of flag?
- How does interspect interact with the existing auto-compound hook? Complement or subsume?
