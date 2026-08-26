# epistemic-provenance-forensics — round 2

## Findings Index

- [P0] compound-md-write-is-an-ungraded-transfer-carrier — Adjudication: both prior findings fail on the trace; Compound's `*.md` write lands in CLAUDE.md/AGENTS.md/SKAFFEN.md, which `contextfiles.Load` prepends to every future session's system prompt at top precedence, so transfer is carried — by the worst-governed channel in the system (§Lessons item 7:43, §Mandatory disagreement:128, §Hard gates:99)
- [P1] append-only-authority-makes-retirement-load-bearing — The transfer channel has a writer and a reader but no remover or expirer, which retargets the mandatory subtractive candidate from the mutations store to the context-file channel and falsifies the charter's closing goal as written (§Candidate-generation:70, §Required output:172)

## Findings

### compound-md-write-is-an-ungraded-transfer-carrier

- **Severity:** P0
- **Where:** `internal/tool/registry.go:44-46,67-70` (the disputed location); charter `docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:43`, `:99`, `:128`
- **What:** The contradiction is decidable, not a taste call, and the trace refutes *both* prior findings — in opposite directions.

  Finding (2) rests on the premise that Compound's markdown write is *unindexed*. That premise is false. `manifestGlobs` (registry.go:44-46) contains `*.md`; `GateConstraint.MatchesPath` matches against `filepath.Base` (registry.go:30-41), so `CLAUDE.md`, `AGENTS.md`, `SKAFFEN.md`, and `.skaffen/SKAFFEN.md` all pass. Those are exactly `contextfiles.DefaultFileNames` plus the `.skaffen/` special case (contextfiles.go:22, 58). `contextfiles.Load` walks workdir→home collecting them and `buildSystemPrompt` prepends the result to the system prompt of **every** future Skaffen session, in **every** phase (main.go:843). Load orders sections outermost-first so "project-level instructions appear last and take precedence" (contextfiles.go:24-26). Sandbox does not stop it: `DefaultPolicy.WriteDirs` and even `StrictPolicy.WriteDirs` include `workDir` (sandbox/policy.go:44,61).

  So Compound has a durable, high-precedence, cross-session write channel. Transfer is carried.

  Finding (1) is therefore right that transfer has a named carrier — but for the wrong reason, and its framing ("carried, therefore no gap") is the actual error. This carrier satisfies **none** of the charter's four hard-gate clauses at line 99 / lessons item 4 (36-40): no grade (the reader emits `# Context: /path/to/CLAUDE.md` — byte-indistinguishable from a human-authored instruction, contextfiles.go:79), no separating store or namespace (it writes into the *human* instruction file), no read filter (Load has no filter of any kind — every non-empty file is concatenated), and no expiry or retention rule (verified: no prune/expire/retire/TTL code exists anywhere in `internal/mutations`, `internal/session`, or `internal/contextfiles`).

  This is strictly worse than the grade-blind `cass` channel already on the record: `cass` output is at least fenced under an `## Orient Inspiration` header, Orient-only, and capped at 3 results (inspire.go:62-85, session.go:80-92). The context-file channel is unfenced, unbounded, all-phase, and top-precedence.

  Finding (2)'s *conclusion* nonetheless partially survives, upgraded: "Compound is thin enough to warrant the same knife" understates it. Compound is not thin; it is a durable-authority write with zero epistemic gate — the precise failure the charter's hard gate was written to disqualify, applied to a candidate and never to the incumbent.
- **Evidence:**
  - `internal/tool/registry.go:44-46` — `manifestGlobs = []string{"*.md", ...}`
  - `internal/tool/registry.go:67-71` — `PhaseCompound: { ..., "edit": {AllowedGlobs: manifestGlobs}, "write": {AllowedGlobs: manifestGlobs} }`
  - `internal/tool/registry.go:30-41` — `MatchesPath` matches `filepath.Base(filePath)`, so `CLAUDE.md` ∈ `*.md`
  - `internal/contextfiles/contextfiles.go:22` — `DefaultFileNames = []string{"SKAFFEN.md", "CLAUDE.md", "AGENTS.md"}`
  - `internal/contextfiles/contextfiles.go:47-61,79` — collects every level, wraps as `# Context: <path>`, no grade/filter/expiry
  - `cmd/skaffen/main.go:843` — `ctx := contextfiles.Load(workDir)` feeding `buildSystemPrompt`
  - `internal/sandbox/policy.go:44,61` — `workDir` writable under both default and strict policy
  - Negative evidence: `grep -rn "prune|expire|retire|TTL"` over `internal/mutations internal/session` returns only `web_search` cache TTL and unrelated `Truncate` calls
- **Suggestion:** Drop `*.md` from `manifestGlobs`, or — better — split it: allow `CHANGELOG*`/`VERSION*`/`docs/**.md` and explicitly deny the four `contextfiles` filenames from Compound's `edit`/`write` constraint, since those four are the system's instruction channel, not its output channel. Independently, teach `contextfiles.readContextFile` to carry provenance (`# Context (agent-authored, session <id>, <ts>): <path>`) so a machine-written block is distinguishable from a human-written one at read time.
- **Remediation (brief amendment):** Amend Lessons item 7 (line 43) to require that each named carrier of exploration/falsification/simulation/transfer/retirement be scored against the same four epistemic-safety clauses as a candidate — naming a carrier does not close a gap, and the incumbent transfer carrier fails all four.

### append-only-authority-makes-retirement-load-bearing

- **Severity:** P1
- **Where:** `internal/contextfiles/contextfiles.go:38-67`; charter `docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:70`, `:172`
- **What:** The contradiction exposes a structural asymmetry neither finding named. Skaffen's knowledge plumbing has writers and readers at both ends but **no remover at either**: `Store.Write`/`WriteForType` only ever `O_APPEND` (store.go:26-52, 100-131); `ReadRecent(n)` *windows* the tail but never deletes, so the file grows unboundedly and old rows stay eligible forever; `contextfiles.Load` re-reads whatever is on disk with no notion of staleness. Compound can only ever *add* authority to CLAUDE.md; nothing in the runtime can ever remove what a past Compound asserted.

  Two consequences for the tournament.

  First, it retargets the mandatory subtractive candidate (line 70). Prior work aimed retirement at the mutations store; the store is actually the *less* harmful target, because its payload is rates and its read path is fenced. The high-value retirement target is the context-file channel, where a single bad Compound-phase generalization becomes a permanent, top-precedence, all-phase instruction. That makes the subtractive candidate — and `Reprove`, the staleness-triggered authority-removing contract — the only candidates in the field that touch the system's actual worst channel. Retirement stops being a diversity quota (line 70's "at least one") and becomes the front-runner.

  Second, it falsifies the charter's closing goal as written (line 172): "without creating a competing truth channel." A competing truth channel is not a risk to be avoided by the new design — it already exists, in the incumbent, at higher authority than anything a candidate could propose. A design that merely refrains from adding one leaves the system worse than a design that closes the existing one. As written, line 172 lets the no-S null win by default on a criterion the null already fails.
- **Evidence:**
  - `internal/mutations/store.go:26-52` (`Write`, `O_APPEND|O_CREATE|O_WRONLY`), `:100-131` (`WriteForType`, same) — no delete path
  - `internal/mutations/store.go:56-85` — `ReadRecent` returns `all[len(all)-n:]`; a tail window, not a retirement
  - `internal/contextfiles/contextfiles.go:38-67` — no mtime, no expiry, no size bound, no dedup
  - `internal/tool/registry.go:67-71` — Compound's only durable, cross-session capability is this write
  - No `prune`/`expire`/`retire` symbol exists in `internal/mutations`, `internal/session`, or `internal/contextfiles`
- **Suggestion:** Score the subtractive/retirement candidate (and `Reprove`) against the context-file channel specifically, not the mutations store: its pilot metric becomes "agent-authored context blocks removed or demoted per session" with a losing condition of "removal rate ≤ write rate," which is directly measurable against `contextfiles.Load` output size.
- **Remediation (brief amendment):** Rewrite the closing goal (line 172) to read "…without creating a competing truth channel **and that closes or governs the one Compound's context-file write already runs**," so a candidate scores against the incumbent's laundering channel rather than merely abstaining from a new one.

## Verdict

The contradiction is decidable on the trace and both prior findings lose: finding (2)'s "unindexed markdown write" is factually wrong — `*.md` ∩ `{SKAFFEN,CLAUDE,AGENTS}.md` is non-empty and `contextfiles.Load` feeds those files into every future session's system prompt at top precedence — while finding (1) is right that transfer is carried but wrong that carriage closes the gap, since this carrier fails all four of the charter's own epistemic-safety clauses. The residue is a stronger result than either parent: Skaffen's transfer channel is append-only and ungraded, which makes retirement not a quota item but the highest-value candidate in the field, and makes the charter's "do not create a competing truth channel" goal a criterion the incumbent already violates.
