# Research: pi_agent_rust Architecture Analysis

> **Source**: https://github.com/Dicklesworthstone/pi_agent_rust
> **Date**: 2026-02-19
> **Scope**: Architecture, security model, session management, doctor, extension dispatcher

---

## 1. Overview

pi_agent_rust is a Rust rewrite of Pi Agent (originally Node/Bun), an AI coding agent CLI. The project claims 5-8x faster session handling, 10-12x lower memory footprint, and sub-20ms resume latency for 1M-token sessions. Built on two purpose-built libraries:

- **asupersync** -- structured concurrency runtime with capability-based contexts (Cx), built-in HTTP/TLS via rustls, and structured cancellation
- **rich_rust** -- terminal rendering (port of Python's Rich library)

Three execution modes: Interactive TUI, Print (single-shot), and RPC (line-delimited JSON for IDE integration).

---

## 2. Extension Runtime Architecture

### 2.1 Two Runtime Families

| Runtime | Trigger | Notes |
|---------|---------|-------|
| QuickJS (JS/TS) | .js/.ts/.mjs/.cjs/.tsx/.mts/.cts | Embedded engine, no Node/Bun dependency. Node API shims for fs, path, os, crypto, child_process, url |
| Native descriptor | *.native.json | Runs in native Rust descriptor runtime |

Extensions register: tools, slash commands, event hooks, flags, providers, shortcuts.

### 2.2 Hostcall ABI

Extensions communicate with the host via typed hostcall opcodes. The hostcall is the fundamental unit of extension-to-host communication.

Ten capability types gate what an extension can do:

| Capability | Dangerous | Notes |
|------------|-----------|-------|
| Read, Write | No | Filesystem access |
| Http, Events, Session, Ui, Tool, Log | No | Various host APIs |
| Exec | Yes | Shell execution |
| Env | Yes | May leak secrets |

Dangerous capabilities default to Deny in Strict/Prompt modes.

### 2.3 Capability Gating and Policy Profiles

Three policy profiles expand into concrete ExtensionPolicy structs:

- **Safe** (Strict mode): denies exec/env, caps at read/write/http/events/session
- **Standard** (Prompt mode): same deny list but prompts rather than blocks (production default)
- **Permissive**: all capabilities open

Per-extension overrides via `per_extension: HashMap<String, ExtensionOverride>` allow mode, allow/deny, and quota customization per extension ID.

### 2.4 Per-Extension Quota Engine (SEC-4.1)

Sliding-window and cumulative resource limits enforced per extension:

| Tier | Calls/sec | Calls/min | Total | Subprocesses |
|------|-----------|-----------|-------|-------------|
| Strict | 20 | 500 | 5,000 | 4 |
| Prompt | 100 | 2,000 | -- | 8 |
| Permissive | 500 | 10,000 | -- | 32 |

Live counters track: timestamp sliding windows (VecDeque of i64), monotonic write bytes, HTTP request totals, and active_subprocesses (incremented on spawn, decremented on exit).

### 2.5 Compatibility Scanner

Static analysis of JS/TS source produces a CompatLedger with four categories:

1. **Capabilities** -- inferred from pi.* API usage and import patterns
2. **Rewrites** -- Node builtins mapped to pi:node/* equivalents
3. **Forbidden** -- disallowed modules (vm, net, tls, worker_threads)
4. **Flagged** -- dynamic code patterns (eval, etc.)

The scanner strips JS comments via a state machine handling block comments, template literals, strings, and regex. Minified lines >= 4096 bytes use raw text to avoid evidence loss.

---

## 3. Security Model

### 3.1 Trust Lifecycle

Extensions move through a state machine:

```
Quarantined -> Restricted -> Trusted -> Killed
```

- **Quarantined**: no dangerous hostcalls permitted
- **Restricted**: read-only hostcalls only
- **Trusted**: full policy-allowed capabilities
- **Killed**: dead state requiring re-acknowledgement

Promotions require explicit operator acknowledgment AND risk-score thresholds:
- Restricted requires score >= 30
- Trusted requires score >= 50

Demotions are unconditional and immediate. Every transition is recorded as an auditable event with timestamp and reason.

### 3.2 Risk Scoring

Five positive dimensions plus a risk penalty:

| Factor | Max Points | Key Signal |
|--------|-----------|------------|
| Popularity | 30 | Official visibility, GitHub stars, marketplace rank |
| Adoption | 15 | npm downloads, marketplace installs, forks |
| Coverage | 20 | Runtime tier, interaction patterns, host capabilities |
| Activity | 15 | Exponential decay, 180-day half-life |
| Compatibility | 20 | CompatStatus-based |
| Risk Penalty | -15 | Severity-based deduction |

final_total = base_total.saturating_sub(risk_penalty)

Tier assignment (gates policy decisions):

| Condition | Tier |
|-----------|------|
| Official origin | tier-0 |
| Gates fail | excluded |
| score >= 70 | tier-1 |
| score >= 50 | tier-2 |
| Below 50 | excluded |

Four boolean gates must all pass: provenance_pinned AND deterministic AND license_ok AND unmodified.

### 3.3 Two-Stage Exec Enforcement

Stage 1: Capability gate check (is exec allowed for this extension?)
Stage 2: Command-level mediation -- blocks dangerous shell classes:
- Recursive delete
- Disk/device writes
- Reverse shell patterns
- DCG/heredoc AST signals (multiline payload detection)

ExecMediationPolicy provides command-level allow/deny after capability-level exec is granted. SecretBrokerPolicy controls redaction of secret environment variables.

### 3.4 Kill Switches

Two emergency controls:
- forced_compat_global_kill_switch -- forces ALL extensions to compatibility lane
- forced_compat_extension_kill_switch -- per-extension containment

Kill-switch is the only way to reach the Compat dispatch lane, making emergency rollback distinguishable from ordinary capability mismatches in telemetry.

### 3.5 Graduated Enforcement Rollout (SEC-7.2)

Phase ordering: Shadow -> LogOnly -> EnforceNew -> EnforceAll

Only EnforceNew and EnforceAll actually block calls. RolloutTracker manages transitions with automatic rollback when:
- False positive rate > 5%
- Error rate > 10%
- Latency > 200ms

Minimum 10 samples required before triggers evaluate.

### 3.6 Audit and Replay

The system implements a deterministic replay trace bundle for forensics:

- Events captured as ReplayTraceEvent with sequence numbers and logical clocks
- Contiguous sequence enforcement (no gaps)
- Cancel/retry ordering rules
- ReplayCaptureBudget gates capture based on overhead per-mille and trace byte size
- first_divergence() compares two bundles field-by-field for forensic comparison
- ReplayDiagnosticSnapshot aggregates event count, gate report, divergence, and root cause hints

### 3.7 Preflight Analysis

Four-layer checks before extension loading:

1. **Module import compatibility** -- support levels: Real, Partial, Stub, ErrorThrow, Missing
2. **Capability policy evaluation** -- Allow, Prompt, or Deny per detected capability
3. **Forbidden pattern detection** -- hard errors
4. **Flagged pattern detection** -- warnings

Confidence score: baseline 100, minus 25 per error, minus 10 per warning.

A separate SecurityScanner performs static analysis across risk tiers (Critical through Low), detecting: eval patterns, prototype pollution, hardcoded secrets, native module loading.

Install recommendation maps to initial trust state: Block/Review -> Quarantined, Allow -> Trusted.

---

## 4. Session and State Management

### 4.1 JSONL v3 Format

Sessions persist as JSONL files (version 3). Entry types:

- Message -- user/assistant/tool messages
- ModelChange -- provider + model_id changes
- ThinkingLevelChange -- thinking level mutations
- SessionInfo -- name and metadata
- Custom -- extension data
- Compaction -- context window compaction records
- BranchSummary -- summarized branch content
- Label -- user-defined entry labels

Each entry carries parent_id + id (8-char hex), forming a linked tree (DAG stored as flat Vec, navigated via parent-pointer links).

### 4.2 Tree / Branching Model

**Linearity optimization**: When is_linear is true (no branching), entries_for_current_path() returns all entries directly. Once navigation diverges from the tip, the flag flips and ancestor-chain traversal activates. This avoids O(n) traversal for the common case.

**ForkPlan**: On fork, the new session's leaf is set to the parent of the selected user message, allowing re-submission without consecutive user messages.

### 4.3 Compaction

CompactionEntry stores summary text, first_kept_entry_id anchor, and tokens_before count. During message reconstruction, the algorithm finds the last compaction on the current path, prepends a synthetic summary message, and includes only entries from the anchor onward.

### 4.4 V2 Sidecar Format

The V2 store is a sidecar directory alongside the .jsonl file, enabling O(index + tail) resume for large sessions.

Directory layout:
```
<stem>.v2/
  manifest.json          -- metadata + chain hash
  segments/              -- append-only JSONL segment files
    0000000000000001.seg
    0000000000000002.seg
  index/
    offsets.jsonl         -- per-entry byte offset index
  checkpoints/           -- periodic snapshots
  migrations/
    ledger.jsonl
  tmp/                   -- atomic write staging
```

Key design decisions:

- Each SegmentFrame carries: sequence numbers (segment, frame, entry), entry_id, parent_entry_id, entry_type, timestamp, payload_sha256, payload_bytes, and payload
- OffsetIndexEntry provides O(1) random access: entry_seq -> (segment_seq, byte_offset, byte_length, crc32c)
- Running SHA-256 chain: chain[n] = SHA-256(chain[n-1] || payload_sha256[n]), genesis = 64 ASCII zeros
- CRC32C per entry for integrity validation

Hydration modes:

| Mode | Trigger | Complexity |
|------|---------|------------|
| Full | < 10,000 entries | O(N index + N seeks) |
| ActivePath | >= 10,000 entries | O(index + depth seeks) |
| Tail(N) | Explicit | O(index + N seeks) |

Staleness detection: compares mtime of index/offsets.jsonl against source .jsonl. If JSONL is newer, V2 is skipped.

Recovery: If bootstrap or validation fails (JSON parse failure, checksum mismatch, out-of-bounds index), the store rebuilds the index by scanning all segments, trimming truncated trailing frames, and reconstructing offsets.jsonl with fresh CRC and chain hash.

### 4.5 SQLite-Backed Sessions

JSON-in-SQLite hybrid: each entry serialized to JSON text stored in rows.

Schema:
```sql
pi_session_header  -- id TEXT PK, json TEXT NOT NULL
pi_session_entries -- seq INTEGER PK, json TEXT NOT NULL
pi_session_meta    -- key TEXT PK, value TEXT NOT NULL
```

Pragmas: journal_mode = WAL, synchronous = NORMAL, foreign_keys = ON.

Two save strategies: full DELETE + reinsert (atomic replacement) or INSERT-only append + UPSERT meta (incremental).

No migration framework -- CREATE TABLE IF NOT EXISTS only.

### 4.6 Write-Behind Autosave

Mutations coalesced: multiple appends between flushes count as one unit (up to 256 cap). Three durability modes:
- **Strict**: always flush on shutdown, propagate errors
- **Balanced**: flush on shutdown, swallow errors
- **Throughput**: skip shutdown flush entirely

Incremental append vs full rewrite decided by: first save, header dirty, appends since checkpoint >= 50, or defensive rewrite when persisted count > entries count. All writes use atomic temp-file + rename.

---

## 5. pi doctor Implementation

### 5.1 Six Diagnostic Categories

| Category | Label | Checks |
|----------|-------|--------|
| Config | Configuration | settings.json validity, unknown keys |
| Dirs | Directories | existence, write permissions |
| Auth | Authentication | auth.json parse, permissions, credential status |
| Shell | Shell and Tools | bash, sh, git, gh presence and execution |
| Sessions | Sessions | JSONL header validity (up to 500 files) |
| Extensions | Extensions | preflight policy analysis |

### 5.2 Scoping Logic

- Extension path provided + no --only: runs ONLY extension checks
- --only extensions without path: emits Fail finding
- --only set: filters to specified categories
- No flags: runs all non-extension categories

### 5.3 Auto-Remediation

| Issue | Fix Action | Requires |
|-------|-----------|----------|
| Missing directory | std::fs::create_dir_all | --fix flag |
| auth.json wrong permissions (Unix) | set_permissions(mode 0o600) | --fix flag |

Fixability::Fixed downgrades severity to Pass -- representing successful auto-remediation within the same run.

### 5.4 Finding Lifecycle

Builder pattern with fluent chaining:
```rust
Finding::warn(cat, "auth.json permissions are {mode:o}")
    .with_detail("...")
    .with_remediation("chmod 600 ...")
    .auto_fixable()
```

Four severities: Pass < Info < Warn < Fail (ordered, enabling max() aggregation).

### 5.5 Output Formats

Three renderers: text (grouped by category), JSON (serde_json pretty), and markdown (with category section headers).

### 5.6 Probing Strategy

Shell tool checks have two modes: PresenceOnly (PATH scan) vs ProbeExecution (spawns the command). Special case: sh --version failing with "illegal option" is treated as non-fatal (dash/POSIX sh compatibility).

---

## 6. Extension Dispatcher Design

### 6.1 Three Dispatch Lanes

| Lane | When Used | Purpose |
|------|-----------|---------|
| Fast | Default path | Direct dispatch, no telemetry overhead |
| IoUring | IO-heavy + policy allows + budget available | Bridged async I/O |
| Compat | Kill-switch activated | Emergency containment |

If neither advanced dispatch nor io_uring is active, the path collapses to direct dispatch_hostcall_fast, bypassing all telemetry overhead. This is a zero-cost abstraction when features are disabled.

### 6.2 IO Hint Classification

Tools and HTTP flagged as IoHeavy; UI/Events/Log as CpuBound:
- Read/write/grep/find/ls -> IoHeavy
- UI/Events/Log -> CpuBound

The io_uring lane applies six sequential gates (first failure wins):
1. Kill-switch -> Compat
2. Config disabled -> Fast
3. Ring unavailable -> Fast
4. Not IoHeavy -> Fast
5. Capability not in allowlist (only Filesystem/Network qualify) -> Fast
6. Queue depth >= max -> Fast
7. All pass -> IoUring

Conservative default: io_uring is OFF by default (enabled: false, ring_available: false).

### 6.3 Shadow Dual Execution (Oracle)

The compat shadow runs AFTER the fast path, comparing outcomes for divergence detection -- never replacing the authoritative result.

Sampling: FNV-1a hash over call_id, trace_id, extension_id for deterministic, allocation-free bucketing. Default sample rate: 2.5% (25,000 ppm).

Divergence budget: sliding window of 64 observations, budget of 3 divergences. When exceeded, rollback engages for 128 subsequent requests.

Shadow-safe operations (read-only): session getstate/getmessages, events getactivetools/listflags, tools read/grep/find/ls. Writes, HTTP, exec, and UI are excluded.

### 6.4 Regime Shift Detector

Combines three statistical methods:
- **CUSUM** -- two-sided cumulative sum for rate changes
- **BOCPD** -- Bayesian Online Change Point Detection with constant hazard model
- **SPRT** -- Sequential Probability Ratio Test as rollout gate

Signal composition (4 factors, weighted):
- Queue depth: 0.35
- Service time: 0.35
- Opcode entropy: 0.15
- LLC miss rate (proxy via overflow depth ratio): 0.15

Mode transitions between SequentialFastPath and InterleavedBatching:
- Requires 2 consecutive confirmations + 32 observation cooldown
- Immediate fallback when queue depth <= 1.0 AND service time <= 1200us

SPRT rollout gate: Stratifies evidence by contention level (High/Low/Mixed), updates Beta posteriors per stratum. Uses e-process thresholds (1/alpha = 20) with coverage requirements (min 30 total samples, min 10 per stratum). Asymmetric expected loss: false-promote 28.0, false-rollback 12.0, hold opportunity 10.0.

### 6.5 AMAC Batch Executor

AMAC = Asynchronous Memory Access Chaining. Interleaves multiple independent hostcall state machines per scheduler tick to hide memory-access latency when working sets exceed LLC capacity.

Group classification by memory weight (90=Http, 70=Tool, 50=SessionRead, 30=SessionWrite, 5=Log). Write groups are marked unsafe (ordering dependencies).

Interleave decision per group:
1. Group < 4 requests -> Sequential
2. Not interleave-safe -> Sequential
3. < 64 total observations -> Sequential (insufficient telemetry)
4. Stall ratio < 20% -> Sequential
5. Otherwise -> Interleave with adaptive width

Width formula: scales proportionally with stall severity and memory-boundedness weight. EMA smoothing (alpha ~0.2) on per-call latency and stall ratio. Stall threshold: 100us.

### 6.6 Three-Tier Dispatch Pipeline

```
Tier 0: Interpreter (sequential match dispatch)
Tier 1: Superinstruction fusion (plan-based opcode sequence fusion)
Tier 2: Trace-JIT (pre-compiled dispatch tables)
```

**Tier 1 -- Superinstruction Fusion**:
- Identifies frequently co-occurring opcode sequences in BTreeMap (deterministic)
- Fuses into single dispatch token with @{plan_id} prefix
- Cost model: baseline = width * 10, fused = 6 + width * 2, always saves for width >= 2
- Canonical trace always preserved for fallback/verification

**Tier 2 -- Trace JIT**:
- Plans promoted when execution count reaches threshold
- Three guards: OpcodePrefix match, SafetyEnvelopeNotVetoing, MinSupportCount
- Guard failures tracked; excessive failures permanently invalidate the trace
- Cost: 3 + width (vs tier-1's 6 + 2*width), strictly cheaper
- LRU eviction when cache exceeds limit

### 6.7 Hostcall Queue

Two-lane bounded queue: fast lock-free ring (crossbeam ArrayQueue, capacity 256) with overflow spilling into VecDeque (capacity 2,048).

Three admission outcomes: FastPath, OverflowPath, Rejected.

S3-FIFO tenant fairness: tri-queue (small/main/ghost) with per-owner budget caps. Ghost hits bypass probationary queue, promoting directly to main. Fairness instability triggers fallback bypass (latches until explicit clear).

EBR (Epoch-Based Reclamation): popped items cloned to retired list. Reclamation when no active epoch pins. Auto-transitions to SafeFallback if retired backlog exceeds threshold.

BRAVO Contention Policy: three-mode state machine (Balanced -> ReadBiased -> WriterRecovery -> Balanced). Writer starvation triggers rollback. Fairness budget caps consecutive read-bias windows.

### 6.8 Hostcall Rewrite Engine

Cost-based plan selector for hot-path marshalling. Two strategies: BaselineCanonical (default) and FastOpcodeFusion (lower overhead). Selection is deterministic and pure. Ambiguity (tie between distinct plans) returns a deopt fallback.

Disabled via env var PI_HOSTCALL_EGRAPH_REWRITE=0.

### 6.9 Policy Enforcement Layer

Policy checks gate EVERY dispatch before any lane selection:
1. Look up required capability for the request
2. Check against PolicySnapshot (O(1) capability decision table)
3. If not Allow, short-circuit with denied error (no lane selection, no telemetry)
4. Snapshot version (SHA-256 of canonical JSON policy) included in every decision trace for provenance

The ExtensionDispatcher is !Send by design (uses Rc and RefCell), binding each dispatcher instance to a single thread/reactor shard. Cross-shard coordination occurs at the mesh layer, not within the dispatcher.

---

## 7. Extension Event System

### Event Types (10 lifecycle events)

| Event | Trigger |
|-------|---------|
| startup | Once per session |
| agent_start / agent_end | Around full agent run |
| turn_start / turn_end | Around each provider API call |
| tool_call / tool_result | Before/after tool execution |
| session_before_switch / session_before_fork | Before session navigation |
| input | Before user input processed |

### Response Capabilities

- tool_call -> can block: true to halt execution
- tool_result -> can replace content or details
- input -> can transform text/images, block input, or pass through

Priority resolution chain for input events handles null, action strings, block flags, content presence, and raw string responses.

---

## 8. Permission Persistence

PermissionStore backed by a JSON file:
```
decisions: HashMap<extension_id, HashMap<capability, PersistedDecision>>
```

Each PersistedDecision carries: capability, allow/deny, decided_at, expires_at (ISO-8601), and optional version_range (semver constraint). Expiry via lexicographic ISO-8601 comparison. Version scoping evaluated externally by caller.

Cache projections strip expired entries. Revocation per-extension or global reset.

---

## 9. Performance Engineering Patterns Worth Noting

| Pattern | Implementation | Relevance to Clavain |
|---------|---------------|---------------------|
| Zero-cost lane abstraction | When io_uring/dual-exec disabled, dispatch collapses to single fast path | Plugin routing that adds zero overhead when features are off |
| Linearity flag | Boolean flag avoids tree traversal for common (non-branching) sessions | Session state optimization for linear workflows |
| Deterministic sampling | FNV-1a hash over IDs for allocation-free bucketing | Shadow testing without randomness |
| Graduated enforcement | Shadow -> LogOnly -> EnforceNew -> EnforceAll with auto-rollback | Safe policy rollout pattern |
| EMA-driven adaptive batching | Stall ratio observation drives interleave width | Load-adaptive dispatch without configuration |
| Tier promotion pipeline | Interpreter -> Fusion -> JIT with guard-failure invalidation | Progressive optimization with safe deopt |
| Atomic write-behind | NamedTempFile + persist() for all state files | Crash-safe persistence |
| Sidecar index | Byte-offset index alongside append-only segments | O(1) random access without scanning |

---

## 10. Key Architectural Ideas (Summary)

1. **Capability-first extension model**: Every host API call requires a specific capability token. Policy profiles compose capabilities into Safe/Standard/Permissive modes. Per-extension overrides layer on top. This creates a clear security boundary without runtime type confusion.

2. **Multi-lane dispatch with statistical promotion**: The three-lane (Fast/IoUring/Compat) design lets features be off by default with zero overhead. Statistical detectors (CUSUM + BOCPD + SPRT) decide when to promote to batched/interleaved mode. This is genuinely adaptive -- not just configuration.

3. **Trust is earned, not configured**: Extensions start Quarantined, earn Restricted/Trusted through risk scoring and operator acknowledgment. Kill switches provide instant demotion. The graduated enforcement rollout (Shadow -> EnforceAll) means new security policies can be deployed without breaking existing extensions.

4. **Session storage is a spectrum**: JSONL for simplicity, V2 sidecar for large sessions (O(index + tail) resume), SQLite for structured access. The linearity flag avoids tree traversal for the common case. Compaction preserves context while bounding growth.

5. **Forensic replay over audit ledger**: Instead of hash-linked audit chains, the system captures deterministic replay trace bundles with sequence validation and divergence comparison. This is more practically useful for debugging than cryptographic audit trails.

6. **Doctor as structured diagnostics**: Six scoped categories, fluent finding builder, auto-remediation with severity downgrade. The scoping logic (extension path implies extension-only checks) shows thoughtful UX for the common case.

7. **Cost-based dispatch optimization**: The superinstruction fusion and trace-JIT tiers use explicit cost models with deterministic plan generation. Guard failures permanently invalidate traces, preventing pathological optimization loops.

---

## 11. What This Is NOT

The README makes impressive claims, but some patterns in the code are aspirational/prepared rather than fully wired:

- **io_uring lane**: The module explicitly handles "policy decisions only" and avoids syscalls. It is a decision framework for when/if io_uring integration arrives.
- **NUMA-aware slab tracking**: Mentioned in README, referenced as "optional" -- likely a future extension point.
- **Reactor mesh**: The dispatcher is explicitly !Send (bound to one thread). Cross-shard coordination is referenced but implemented at a layer above this codebase.
- **AMAC batching**: The executor plans groups and tracks stall telemetry, but within a single async executor, dispatch remains sequential per group. True concurrency is deferred to the mesh layer.

This is common in ambitious Rust projects -- the type system enforces the abstractions even before all concrete implementations exist, which means the architecture is sound even if some paths are not yet exercised.
