# Kernel Contract Review — Intercore Vision v1.6

**Reviewer:** fd-kernel-contract
**Date:** 2026-02-19
**Documents evaluated:**
- `infra/intercore/docs/product/intercore-vision.md` (v1.6)
- `os/clavain/docs/vision.md`
- `infra/intercore/CLAUDE.md` + `AGENTS.md`

---

## Invariants That Must Remain True

Before evaluating the vision, I write down the invariants the document claims hold. If any claim below cannot be supported by the described mechanism, it is a finding.

1. **Dual-write atomicity:** For every state change, the state table mutation and its event log entry are either both committed or neither committed.
2. **Gate enforcement is real:** A run cannot advance past a hard gate whose condition is not satisfied, regardless of what the caller requests.
3. **At-least-once event delivery:** A durable consumer that registered before an event was written will eventually see that event, assuming events have not been pruned while the consumer's cursor still precedes them.
4. **Optimistic concurrency prevents double-advance:** Two concurrent `ic run advance` calls on the same run cannot both succeed.
5. **Filesystem lock scope invariant:** Filesystem locks protect only SQLite read-modify-write operations, never non-DB resources.
6. **Stale lock safety:** A lock held by a dead process is detected within the stale age window and broken; it does not permanently prevent progress.
7. **Discovery tier enforcement:** An OS-layer caller cannot autonomously create a bead for a discovery scored below 0.8; the kernel rejects the promotion.
8. **Token tracking trustworthiness:** Reported token counts are the system of record for budget enforcement.
9. **Schema forward-migration safety:** `ic init` migrates an older DB without data loss; old binary + new DB gracefully fails rather than silently misreading.

---

## Finding Summary

| ID | Priority | Subsystem | Title |
|----|----------|-----------|-------|
| F1 | P0 | Events | Transactional dual-write is incomplete: dispatch events fire after commit |
| F2 | P0 | Discovery | Confidence-tier enforcement is an assertion without a mechanism |
| F3 | P1 | Locks | PID-based stale detection is a two-stage race with a TOCTOU window |
| F4 | P1 | Events | Durable consumer cursor is stored in state table with 24h TTL — contradicting "never expire" |
| F5 | P1 | Events | Event pruning blocked by stale durable consumers: no alerting mechanism is specified |
| F6 | P1 | Token tracking | Self-reported token counts described as the system of record while acknowledged as unverifiable |
| F7 | P2 | Gate override | Override writes phase change then event — crash between them produces advance without audit trail |
| F8 | P2 | Locks | Stale-break is not atomic: rmdir(owner.json) + rmdir(lockDir) allows another process to race in |
| F9 | P2 | Schema / API | "API stability" claimed for CLI flags + DB schemas but migration strategy covers only DB, not CLI |
| F10 | P2 | Event cursors | Dual-cursor design conflates two independent AUTOINCREMENT sequences; at-least-once delivery is only best-effort if either sequence wraps around or a consumer resumes mid-dual-sequence |
| F11 | P3 | Process model | "No background event loop" framing overstates statelessness: SpawnHandler and HookHandler run detached goroutines with 5s timeouts — goroutine leaks on repeated invocations |
| F12 | P3 | Clock monotonicity | Vision acknowledges the risk but does not prescribe a mitigation |

---

## Detailed Findings

---

### F1 — P0: Transactional Dual-Write Is Incomplete for Dispatch Events

**Stated guarantee (vision doc, "Transactional Dual-Write"):**
> "State table mutations and their corresponding events are written in the same SQLite transaction. A phase advancement writes the new phase to the runs table and appends a `phase.advanced` event atomically. There is no window where a table reflects a new state but the event log doesn't (or vice versa)."

**Mechanism described in AGENTS.md (Event Bus, "Architecture"):**
```
dispatch.UpdateStatus() → DispatchEventRecorder → Notifier.Notify() → handlers
```
> "Callbacks fire **after DB commit** (fire-and-forget). Handler errors are logged but never fail the parent operation."

**Achievability assessment:**

The transactional guarantee holds only for phase events — `phase.Advance()` presumably writes both the `runs` table update and the `phase_events` row in a single transaction.

For dispatch events, the event fires **after** the `dispatch.UpdateStatus()` commit returns. This is explicit in AGENTS.md: "Callbacks fire after DB commit." The architecture description shows `dispatch.UpdateStatus()` commits first, then `DispatchEventRecorder` notifies, then `Notifier.Notify()` calls handlers. If the process dies between the dispatch status commit and the event append, the state table says "dispatch completed" but the event log has no `dispatch.completed` entry.

**Concrete failure scenario:**
1. `ic dispatch poll` sees the agent's verdict sidecar.
2. It calls `UpdateStatus(completed)` → transaction commits → `dispatches` row now shows `status=completed`.
3. Process receives SIGKILL (OOM, timeout, user interrupt).
4. The PhaseEventCallback / DispatchEventRecorder never runs.
5. Clavain's event reactor, which drives automatic phase advancement (Level 2 autonomy), is waiting for a `dispatch.completed` event. It never arrives.
6. The run is stuck. The database says "completed"; the event log has no record. A consumer polling `ic events tail` sees no completion event. The human must reconcile manually.

This is a 3 AM incident waiting to happen in any Level 2 deployment.

**The vision text contradicts itself:** The "Transactional Dual-Write" section says "there is no window," but the Event Bus implementation description says callbacks fire after commit — which is the exact window being denied.

**Why not fixable by "just use the same transaction":** The vision's own event bus design routes through a `Notifier` callback rather than inlining the event write in the `UpdateStatus` transaction. The architectural separation (`UpdateStatus → callback → Notifier → handlers`) means any handler that writes to SQLite must open a new transaction, which is a second transaction, not the same one.

**Minimal corrective fix:** For dispatch status changes, perform the `dispatch_events` INSERT in the same transaction as the `dispatches` UPDATE, before returning to the callback infrastructure. The callback/Notifier layer then does non-durable fan-out (in-process, UI, hooks) but the DB record is already there. This mirrors how phase events are described.

---

### F2 — P0: Discovery Confidence-Tier Enforcement Has No Specified Mechanism

**Stated guarantee (vision doc, "Confidence-Tiered Autonomy"):**
> "This is a **kernel-enforced gate**, not a prompt suggestion. The scoring model produces a number; the tier boundaries are configuration; the action constraints at each tier are invariants. An OS-layer component cannot auto-create a bead for a discovery scored at 0.4 — the kernel will reject the promotion."

**What the kernel actually provides:**

The AGENTS.md schema tables listed are: `state`, `sentinels`, `dispatches`, `runs`, `phase_events`, `dispatch_events`, `run_agents`, `run_artifacts`. There is no `discoveries` table in the current schema. The vision doc itself acknowledges (in "What already exists") that kernel integration is missing:

> "What's missing is kernel integration — discovery events through the event bus, event-driven scan triggers, kernel-enforced confidence tiers, and backlog refinement."

The enforcement claim appears in the invariants section of the vision document as if it is a current guarantee. It is not. It is a planned future feature (v3 per the horizon table). At v1 and v1.5 (the current and near-term horizon), the enforcement does not exist at all.

**Why this matters as a P0:**

The "Enforces vs Records" table lists "Discovery autonomy" under "Enforced" with the note "Confidence tier gates (auto/propose/log/discard)." This is a false claim for the current kernel. If anyone builds OS-layer logic today that assumes the kernel will reject out-of-tier promotions, they are building on a guarantee that does not exist. The interject plugin, which already implements discovery, will integrate with the kernel under this misapprehension.

**Concrete failure scenario:**
1. Interject scores a discovery at 0.4 (Low tier).
2. OS code calls `ic [something] promote <discovery-id>` to create a bead.
3. The kernel, having no discovery table or tier enforcement, either returns an error ("unknown command") or succeeds without any tier check.
4. A bead is created for a low-confidence discovery.
5. No audit trail. No block. The guarantee was entirely absent.

**Corrective fix:** The vision document must clearly partition enforcement claims by availability horizon. The "Enforces vs Records" table should add a column indicating whether each enforcement is "current" or "planned (v3)." The invariants section should be rewritten to describe only what the v1 kernel actually enforces.

---

### F3 — P1: PID-Based Stale Detection Has a TOCTOU Window

**Stated guarantee (vision doc, "Coordination"):**
> "Stale detection checks PID liveness (`kill(pid, 0)`). This is best-effort on single-machine deployments — PID reuse is theoretically possible but vanishingly rare for the short-lived operations locks protect (typically < 100ms)."

**Mechanism (AGENTS.md, "Lock Module" + "Acquire Behavior"):**
```
4. Stale detection: compare `owner.json` created timestamp against `StaleAge` (default 5s)
5. Stale-break: os.Remove(owner.json) + os.Remove(lockDir)
```

**ic lock clean uses kill(pid,0):** Only the `clean` subcommand does PID liveness. The `acquire` spin-wait stale-break (step 5 above) uses the timestamp comparison only — no PID check.

**Concrete interleaving:**

1. Process A acquires lock, begins a 6-second operation. `StaleAge = 5s`.
2. Process A's operation takes 6 seconds (long DB transaction, slow disk, etc.).
3. At t=5s, Process B spins on acquire. It reads `owner.json`, sees created_at is 5 seconds ago, considers the lock stale.
4. Process B calls `os.Remove(owner.json)` then `os.Remove(lockDir)`.
5. Process A is still mid-operation. Process C immediately calls `os.Mkdir(lockDir)` — succeeds. Process C acquires the lock.
6. Process A and Process C are now both inside the critical section simultaneously.
7. The DB read-modify-write that locks were supposed to serialize now has two concurrent writers. Given `SetMaxOpenConns(1)` and SQLite's own write locking, this degrades to a SQLite `SQLITE_BUSY` or `ErrStalePhase` — which is a correctness failure, not a crash.

The vision doc acknowledges "PID reuse is theoretically possible but vanishingly rare." But the bigger issue is that PID liveness is only checked in `ic lock clean`, not in the spin-wait stale-break path. The acquire path uses only timestamps. A slow operation — not a dead process — triggers the stale break. The vision's "typically < 100ms" claim is an average-case assumption that does not hold under load, slow disk I/O, or DB migration operations which may take seconds.

**Why the scope invariant claim is weakened:** The vision says "Locks are transient coordination primitives, not persistent state... if the lock directory disappears, the worst case is a brief race on the next DB mutation, not data loss." This is correct for SQLite which has its own write lock. But the stale-break race means the filesystem lock provides weaker mutual exclusion than claimed — it only serializes under normal conditions.

**Corrective fix:** The acquire stale-break path should also check PID liveness via `kill(pid, 0)` before breaking a lock, not just compare timestamps. If the holder is alive but slow, the lock is not stale. Only break if the holder PID is dead (`ESRCH`). If PID is alive, wait longer. The stale age should be significantly larger than any expected operation duration, or the concept of "stale by timeout" should be removed in favor of "stale by liveness."

---

### F4 — P1: Durable Consumer Cursors Have a 24h TTL, Contradicting "Never Expire"

**Stated guarantee (vision doc, "Consumer cursors"):**
> "**Durable consumers** (e.g., Interspect, Clavain's event reactor) register with `ic events cursor register --durable`. Their cursors never expire. The kernel guarantees no event loss for durable consumers as long as events haven't been pruned by the retention policy."

**Actual implementation (AGENTS.md, "Dual Cursors"):**
> "Cursors are persisted in the `state` table with a **24h TTL** for auto-cleanup."

The `state` table has TTL-based expiry. AGENTS.md confirms that even cursor state is stored in this table. There is no `cursors` table — cursors piggyback on the state key-value store that has TTL as a first-class attribute. A 24h TTL means a durable consumer that does not poll for 25 hours will lose its cursor position. When it resumes, it will receive events from the oldest retained event (per the vision's ephemeral cursor behavior) — not from where it left off.

**This directly breaks the at-least-once guarantee for durable consumers.** An Interspect process that is offline for more than 24 hours (maintenance window, crash + slow restart, extended batch job) silently loses its cursor. It cannot know it lost events. The vision says "durable consumers never expire" but the implementation uses the same TTL-expirable state store as ephemeral data.

**Concrete failure scenario:**
1. Interspect registers as a durable consumer.
2. Server is taken down for 30-hour maintenance.
3. Interspect restarts. Its cursor is gone (expired at 24h).
4. Interspect now replays from the oldest retained event (or from now, depending on implementation).
5. Hundreds of `dispatch.completed` and `phase.advanced` events were emitted during the outage.
6. Interspect's self-improvement model is trained on an incomplete event history. Routing proposals are based on biased data.

**Corrective fix:** Durable consumer cursors must be stored in a dedicated table without TTL. The `state` table is inappropriate as a backing store for anything that must survive multi-day outages. Alternatively, the vision doc must be corrected to acknowledge that "durable" means "24h TTL" rather than "never expire."

The command `ic events cursor register --durable` referenced in the vision doc does not appear in the AGENTS.md CLI command table. The implementation may not yet exist — another gap between stated and implemented guarantees.

---

### F5 — P1: Stale Durable Consumers Block Event Pruning With No Specified Alert Path

**Stated guarantee (vision doc, "Event retention"):**
> "The kernel guarantees that no event is pruned while any durable consumer's cursor still points before it. This means a durable consumer that falls behind can block event pruning — the OS should monitor consumer lag and alert on stale durable consumers."

**Problem:** The spec places the alerting responsibility on the OS layer with "the OS should monitor" — but provides no kernel primitive that makes this monitorable. There is no `ic events consumer lag` command in the CLI table. There is no `consumer.lag.warning` event in the event sources list.

**Consequence:** If a durable consumer (Interspect, a custom reactor) crashes and is never restarted, the event log grows without bound. The default 30-day retention policy is neutered. In a long-running system, this is a disk exhaustion path.

**The vision notes this risk but defers the solution to the OS.** The OS (Clavain) has no current tooling to detect consumer lag. The hook system is file-based and does not query kernel consumer state.

**Corrective fix:** Add `ic events consumer list --lag` that emits consumer name, last cursor position, and age since last advance. Add a `consumer.stale` event emitted when a durable consumer's cursor has not advanced in more than a configurable threshold (e.g., 7 days). This makes the problem observable without requiring the OS to grow custom SQL queries against the state table.

---

### F6 — P1: Self-Reported Token Counts as System of Record for Budget Enforcement

**Stated guarantee (vision doc, "Transactional dual-write" + "Resource Management"):**
> "The kernel tracks and reports. The OS decides and acts. When a dispatch exceeds a configured threshold, the kernel emits a `budget.warning` event."

**Also stated (vision doc, "Assumptions and Constraints"):**
> "**Token tracking is self-reported.** The kernel records token counts that dispatched agents report. It cannot independently verify these counts. An agent that misreports its token usage undermines budgeting."

**Why this is P1 and not just P3:**

The vision document places budget threshold events (`budget.warning`, `budget.exceeded`) in the event sources list and the "Enforces vs Records" table. The table lists "Cost/billing" as "Recorded" rather than "Enforced," which is correct phrasing — but the event system fires on recorded (unverified) counts. An agent that underreports (intentionally or through a bug) will never trigger `budget.warning`, even if its actual API cost is 10x the budget.

The `ic dispatch tokens <id> --set --in=N --out=N` command writes whatever numbers the caller provides. There is no cross-check, no ceiling, no sanity validation against the expected output size.

**Concrete failure scenario:**
1. A Codex dispatch is spawned with a 100k token budget.
2. The dispatch runs for 4 hours and consumes 2M tokens.
3. The dispatch reports 80k tokens (either through a bug in the wrapper script that reads token counts, or due to a model API change that changes the counter format).
4. The kernel records 80k tokens. No budget warning fires.
5. The Anthropic bill shows $300 for a run expected to cost $15.

The vision acknowledges this and proposes Tier 1 mitigation (cross-reference with billing API) and Tier 2 (runner-level injection). But neither exists in v1. The budget system is described as an enforcement mechanism when it is actually a recording mechanism with enforcement dependent on accurate self-reporting.

**Corrective fix:** The "Enforces vs Records" table is correct in listing this as "Recorded," but the event system should be clearly documented as "budget events fire on self-reported data, which may be inaccurate." Any consumer of `budget.warning` must understand it is a best-effort signal, not a hard guarantee. The vision's budget section currently implies stronger guarantees than the mechanism supports.

---

### F7 — P1: Gate Override Writes Phase Change Before Audit Event — Crash Leaves Advance Without Audit Trail

**Stated in AGENTS.md ("Override"):**
> "`ic gate override` force-advances past a failed gate. It calls `UpdatePhase` first, then records the event — if a crash occurs between, the advance happened without audit (safer than audit without advance)."

This is a real, acknowledged trade-off. AGENTS.md is honest about it. But the vision doc ("Fail Safe, Not Fail Silent") claims:
> "When a gate blocks advancement, the evidence is recorded. [...] The kernel never silently swallows failures."

A gate override is a deliberate bypass of gate enforcement. If the crash-between scenario occurs, the kernel has advanced the run without recording why. The audit trail has a gap. Interspect's analysis of gate override patterns will be incomplete. The vision's "Fail Safe, Not Fail Silent" principle is violated specifically for the code path that is most likely to be scrutinized (forced overrides are exactly the events you want to audit).

**Corrective fix:** Use a single transaction: begin transaction → UpdatePhase → INSERT event → commit. The "safer than audit without advance" reasoning would then be unnecessary, because they happen atomically. The fear that drove the current ordering is that the advance might fail if done after the event, but both operations are SQLite writes on the same connection with `SetMaxOpenConns(1)` — they can be wrapped in one transaction.

---

### F8 — P2: Lock Stale-Break Is Not Atomic

**Mechanism (AGENTS.md, "Acquire Behavior"):**
> "Stale-break: `os.Remove(owner.json)` + `os.Remove(lockDir)` (no `os.RemoveAll` — prevents destroying concurrently re-acquired locks)"

The two-step `os.Remove(owner.json)` then `os.Remove(lockDir)` is not atomic. Between the two removes:

1. Process B removes `owner.json`.
2. Process C calls `os.Mkdir(lockDir)` — fails because `lockDir` still exists.
3. Process B calls `os.Remove(lockDir)`.
4. Now `lockDir` is gone. Process C immediately retries `os.Mkdir(lockDir)` — succeeds.
5. Process B also calls `os.Mkdir(lockDir)` after the remove — succeeds.
6. Both B and C think they hold the lock.

The comment "no `os.RemoveAll` — prevents destroying concurrently re-acquired locks" acknowledges the race but the fix chosen (sequential removes) does not eliminate the race; it just makes a different variant of the race slightly less likely.

The fundamental issue is that POSIX `mkdir`-based locking is only atomic for the initial acquire. Stale-breaking requires a non-atomic sequence of removes followed by a new mkdir, creating a brief window where no lock is held.

**Impact:** Low likelihood per operation, but given that lock operations happen on every hook invocation (potentially hundreds per session), the race materializes eventually. SQLite's own write serialization prevents actual data corruption in most cases, but the ErrStalePhase response to a lost race can produce incorrect "another process advanced this run" errors when no other process was involved.

**Corrective fix:** Before the `os.Mkdir(lockDir)` atomic attempt, document clearly that stale-breaking creates a brief unprotected window. Add a comment. The real fix is to use a lock file (not a directory) and `os.Rename` for the stale-break, which is closer to atomic on most filesystems. Alternatively, rely on SQLite's own `busy_timeout` and `SetMaxOpenConns(1)` as the primary serialization and reduce reliance on the filesystem lock for anything other than initial DB access serialization.

---

### F9 — P2: API Stability Claim Is Underspecified — CLI Flag Stability Not Covered

**Stated guarantee (vision doc, "Assumptions and Constraints"):**
> "**API stability.** CLI flags, event schemas, and database schemas need backward compatibility discipline from v1 onward. Breaking changes require migration paths and deprecation periods."

**What the implementation covers:**

The migration strategy describes `PRAGMA user_version` for DB schema versioning with pre-migration backup. This is adequate for DB schema evolution.

There is no versioned CLI contract. The CLI flags are not documented with stability levels (stable, experimental, internal). There is no deprecation mechanism for removing a flag. The `--disable-gates` flag on `ic run advance` is an example of an escape hatch that, once used by hooks, becomes load-bearing and cannot be removed without breaking callers.

**For an "open-source product" (vision's own framing):**

Community adopters will write hooks and scripts against `ic` CLI flags. If `ic run advance` gains a required positional argument in v1.5 (e.g., a `--reason` flag becomes required), every existing hook silently breaks. The DB migration is safe; the CLI contract is not.

**Corrective fix:** Add a CLI stability tier annotation to the AGENTS.md command table (e.g., "stable: subject to backward-compat policy", "experimental: may change without notice"). Define what constitutes a breaking CLI change. Add `ic version --schema` and `ic version --cli` to distinguish protocol versions from implementation versions.

---

### F10 — P2: Dual-Cursor Design Has Subtle At-Least-Once Degradation Cases

**Stated guarantee (vision doc, "Consumer cursors"):**
> "At-least-once from the consumer's perspective. The consumer is responsible for idempotent processing."

**Mechanism (AGENTS.md, "Dual Cursors"):**
> "`ic events tail` tracks separate high-water marks for phase and dispatch events because they use independent AUTOINCREMENT sequences."

The dual-cursor design stores two independent high-water marks: `phase_cursor` (last `phase_events.rowid` seen) and `dispatch_cursor` (last `dispatch_events.rowid` seen). The `ListAllEvents` query is described as `UNION + dual cursors`.

**Problem:** When a consumer resumes after a cursor save, it reads "all phase events with rowid > phase_cursor UNION all dispatch events with rowid > dispatch_cursor." This correctly replays missed events from each table independently.

However, the ordering guarantee is ambiguous. If the consumer needs to process events in creation order (e.g., phase.advanced must be processed before dispatch.spawned that triggered by that advancement), the UNION ordering depends on the timestamp or a synthetic ordering column. If timestamps are equal (sub-millisecond operations on fast hardware), the ordering within the UNION is non-deterministic.

**More critically:** The AGENTS.md says cursors have a "24h TTL for auto-cleanup." This applies to both phase and dispatch cursors. If the cursor expires, the consumer cannot know which cursor expired or what events were missed. The `ic events cursor reset <consumer>` command resets to the beginning — which, for a consumer that only needs to resume from the last position, means replaying all events from the start. For a consumer with 30 days of event history, this is expensive and potentially infinite for high-throughput systems.

**Corrective fix:** Introduce a monotonic global sequence number across both event tables (or a single events table with a discriminator column). This eliminates the dual-cursor complexity and provides unambiguous total ordering. It also simplifies cursor storage to a single integer. The current dual-cursor design is a complexity tax that degrades at-least-once guarantees under TTL expiry and produces ambiguous ordering under high concurrency.

---

### F11 — P3: "No Background Event Loop" Overstates Statelessness — Goroutine Leak Risk

**Stated design principle (vision doc, "Process Model"):**
> "**Why not a daemon?** Daemons add operational complexity [...] A CLI binary is zero-ops: it works when called, requires no lifecycle management, and can't crash between calls because it doesn't exist between calls."

**Actual implementation (AGENTS.md, "Event Bus", "Handlers"):**
> "The hook handler runs in a detached goroutine with `context.Background()` and a 5s timeout to avoid blocking the single DB connection."

The HookHandler (`handler_hook.go`) and SpawnHandler (`handler_spawn.go`) launch goroutines with `context.Background()`. These goroutines are not tracked. If `ic run advance` is called repeatedly in a tight loop (e.g., in an integration test or a malfunctioning retry loop), and each invocation spawns a hook goroutine that takes close to 5s to timeout, the number of in-flight goroutines grows without bound until the process exits.

For a CLI binary invoked once and then exit, this is low risk — the goroutines terminate with the process. But the pattern is architecturally sloppy: "no lifecycle management" is true for the binary's own lifecycle, but the goroutines inside it during a single invocation are untracked fire-and-forget work. If the hook script hangs (waiting for a blocked subprocess), the binary will not exit for 5 seconds. Under concurrent invocations from multiple hooks fired by Claude Code in parallel, multiple `ic` processes may each be holding the single DB connection's busy_timeout open while their goroutines wait.

**Corrective fix:** Use a `sync.WaitGroup` or `errgroup` to track hook goroutines, and ensure they are drained before the CLI process exits. The 5s timeout should be enforced via a derived `context.WithTimeout`, which the current description implies but the `context.Background()` contradicts. The binary is not quite "stateless between calls" when it runs goroutines that outlive the main goroutine's useful work.

---

### F12 — P3: Clock Monotonicity Risk Acknowledged But Not Mitigated

**Stated (vision doc, "Assumptions and Constraints"):**
> "The kernel uses Go's `time.Now().Unix()` (not SQLite's `unixepoch()`) to avoid float promotion, but doesn't guard against backward clock jumps."

**Impact assessment:**

TTL computations for sentinels and state entries compare stored Unix timestamps against `time.Now().Unix()`. A backward NTP jump of even 60 seconds would:
- Make all sentinel TTLs appear to be in the future (they were set at t=X; now t=X-60 < X, so the sentinel appears valid longer than intended).
- Make all state TTLs appear valid for longer.
- Make lock stale detection incorrect (locks appear younger than they are).

For a single-machine autonomous agent that runs continuously, NTP corrections are routine. This is not exotic.

**Corrective fix at P3 (wording):** Document the risk in AGENTS.md with a recommendation: "If the system clock is managed by NTP, use `time.Now().Monotonic()` for duration comparisons within a process. For cross-process TTLs stored in the DB, document the assumption that the clock does not jump backward more than `sentinel_ttl / 2`." For production deployments, recommend `chronyd` with the `makestep` option disabled (gradual correction only, no backward jumps).

---

## "Enforces vs Records" Table Audit

The vision doc table is reproduced here with findings:

| Category | Claimed Enforcement | Finding |
|---|---|---|
| Gate conditions | Hard gates block advancement | **Correct for current v1 gates** (`artifact_exists`, `agents_complete`, `verdict_exists`). |
| Spawn limits | Max concurrent dispatches, max depth | **Unverified**: Vision claims enforcement; AGENTS.md describes the `dispatches` table but no `maxConcurrent` or `maxDepth` column or check is mentioned in current schema. This may be planned (v2) rather than current. |
| Phase transitions | Optimistic concurrency, gate checks | **Correct**: `WHERE phase = ?` is implemented. |
| Coordination locks | Mutual exclusion via filesystem | **Partially correct**: Stale-break race (F3, F8) weakens the claim to "best-effort mutual exclusion." |
| Token usage | — (recorded only) | **Correctly labeled as recorded, not enforced.** |
| Sandbox contracts | — (recorded only) | **Correctly labeled.** The kernel stores specs but cannot verify enforcement. |
| Discovery autonomy | Confidence tier gates (auto/propose/log/discard) | **False for v1**: No discoveries table, no tier enforcement mechanism exists (F2). |
| Backlog changes | Dedup threshold (blocks duplicate bead creation) | **Unverified**: Similar to discovery enforcement — depends on a discoveries/backlog subsystem not in current schema. |
| Rollback | Phase reset validation, dispatch cancellation | **Partial**: `ic run skip` is implemented. Full rollback (`ic run rollback`) is in the vision but not in the AGENTS.md CLI table — it is planned (v2+), not current. |
| Cross-project deps | Portfolio gate rollup | **Not yet implemented**: `portfolio_id` column, `project_deps` table are future (v4). |
| Cost/billing | Budget threshold events | **Weaker than stated** (F6): Events fire on self-reported data only. |

**Summary:** Of 11 categories in the enforcement table, 2 are false claims about current capability (discovery autonomy, backlog dedup), 2 are unverified (spawn limits, backlog), 1 is a planned feature incorrectly implied as current (rollback), and 1 is weaker than stated (budget). Only 5 are accurately described enforcement claims for the current implementation.

---

## Transactional Guarantee Achievability Assessment

**Technology stack:** Go 1.22, `modernc.org/sqlite` (pure Go, no CGO), `SetMaxOpenConns(1)`, PRAGMAs set after `sql.Open`.

**Can phase events be written in the same transaction as state mutations?** Yes. With `SetMaxOpenConns(1)`, all operations go through the same connection. A `BEGIN` → write runs → write phase_events → `COMMIT` sequence is achievable and correct. The implementation must ensure the event INSERT happens inside the same transaction as the phase UPDATE, not as a callback after commit.

**Can dispatch events be written in the same transaction as dispatch status updates?** Yes, with the same approach. The current callback-after-commit architecture (F1) is a design choice, not a technical constraint. Moving the dispatch_events INSERT inside the `UpdateStatus` transaction is straightforward.

**WAL mode + `MaxOpenConns(1)` correctness:** WAL mode allows concurrent reads while a write is in progress. With only one writer connection (enforced by `MaxOpenConns(1)`), write serialization is guaranteed at the SQLite level. Filesystem locks provide application-level serialization for read-modify-write patterns that need to be atomic across multiple SQL statements. This is sound.

**CTE + UPDATE RETURNING limitation:** The AGENTS.md notes this modernc.org/sqlite limitation. The sentinel check uses direct `UPDATE ... RETURNING` with row counting — this is the correct workaround. No CTE wrapping needed for the described use cases. Not a blocking issue.

**Pre-migration backup:** Automatic timestamped backup before `ic init` migration is adequate for rollback safety. The backup is created before any DDL runs, so an interrupted migration can be recovered. Forward-only migration (no downgrade path) is a gap: if a new binary writes schema v7 and the operator needs to roll back to a binary that only speaks schema v6, the backup is the only recovery path. This should be documented explicitly.

---

## Two-Tier Coordination Model Assessment

**Filesystem `mkdir` locks for DB serialization:**

The model is conceptually sound: filesystem operations are independent of SQLite and provide a recovery path when the DB is unavailable. The stale-break race (F3, F8) is the primary weakness. For the stated use case (<100ms operations, single machine, cooperative callers), the probability of the race materializing is low but nonzero over a long-running system.

**SQLite sentinels for throttling:**

Using the `sentinels` table with `UPDATE ... RETURNING` for atomic claim is correct. Auto-prune in the same transaction (per AGENTS.md) is correct — no orphaned sentinels accumulate. The TTL computation in Go (not SQL) avoids float promotion. This subsystem is well-designed.

**Scope invariant (locks protect only DB operations):**

The vision explicitly states the scope invariant. The AGENTS.md confirms locks are never used for non-DB coordination. This is a clear, maintained boundary. No violation found.

---

## Event System Contract Clarity

**At-least-once delivery:** Correctly specified for in-scope events, but undermined by:
- F1: Dispatch events not written atomically with state changes.
- F4: "Durable" cursors stored in TTL-expirable state table.

**Cursor-based consumption:** Design is sound conceptually. Dual-cursor complexity (F10) is an implementation debt.

**Retention blocking by stale consumers:** Correctly described as a risk. The missing kernel primitive (F5) is the gap.

**Deduplication key (`source_type:source_id:action`):** Correctly specified. This makes at-least-once production safe for retrying producers. However, the dedup check on insert is not described in AGENTS.md — it is unclear whether it is enforced via `INSERT OR IGNORE` on a unique index or via application-level checking. If it is application-level only, a retry that bypasses the application layer loses the dedup guarantee.

**Ephemeral vs durable classification:** The distinction is correct in intent but broken in implementation (F4). The `ic events cursor register --durable` command does not appear in the current CLI table, suggesting it is not implemented.

---

## API Stability Contract

The vision claims API stability "from v1 onward." What constitutes the API surface:

1. **DB schema** — versioned via `PRAGMA user_version`. Migration strategy is adequate. Pre-migration backup provides rollback. **Score: Adequate.**

2. **CLI flags** — Not versioned. No stability tier annotations. No deprecation mechanism. **Score: Insufficient (F9).**

3. **Event schemas** — Event field names, types, and dedup key format are de facto API for all consumers (Interspect, Clavain reactor, TUI, custom hooks). Not versioned separately from DB schema. A change to the event `reason` JSON format (which carries `GateEvidence`) breaks all consumers that parse it. **Score: Insufficient.**

4. **Exit codes** — Documented in AGENTS.md. 4-code scheme (0/1/2/3) is clear. This is part of the API. **Score: Adequate.**

5. **Bash wrapper API (lib-intercore.sh v0.6.0)** — The bash wrapper functions are versioned (v0.6.0). This is good practice. Callers should pin the version. **Score: Adequate.**

---

## Summary of Contractual Gaps by Priority

**P0 — Must fix before any Level 2 (reactive) deployment:**
- F1: Write dispatch events inside the UpdateStatus transaction, not after.
- F2: Remove enforcement claims for discovery tier gating from current-capability documentation; segregate by horizon.

**P1 — Must fix before open-source release or production hook cutover:**
- F3: Add PID liveness check to the acquire stale-break path, not only to `ic lock clean`.
- F4: Move durable consumer cursors to a dedicated no-TTL table; implement `ic events cursor register --durable`.
- F5: Add `ic events consumer list --lag` and a `consumer.stale` event emission.
- F6: Annotate budget events as best-effort (self-reported); do not present budget enforcement as a hard guarantee.

**P1 — Acknowledged but not mitigated (F7):** Gate override writes phase change then event. Wrap both in a single transaction.

**P2 — Must fix for correctness under load or adversarial conditions:**
- F8: Document the stale-break non-atomicity; consider lock file + rename instead of directory + sequential removes.
- F9: Add CLI stability tier annotations; version the event schema separately.
- F10: Consider a single unified event table with a monotonic sequence to replace dual-cursor complexity.

**P3 — Should fix before community adoption:**
- F11: Track hook goroutines with WaitGroup; drain before process exit.
- F12: Document NTP jump behavior; recommend `chronyd` gradual-correction mode.

---

*End of review. Full analysis saved for Interspect / roadmap integration.*
