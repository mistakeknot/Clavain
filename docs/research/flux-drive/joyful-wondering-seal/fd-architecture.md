### Findings Index
- P0 | P0-1 | "Component Removal Risks" | Removing deny-gate without comprehensive verification plan creates unauditable behavioral contract enforcement
- P0 | P0-2 | "Behavioral Contract Sufficiency" | Proposed session-start injection lacks enforcement mechanism verification and provides no failure detection
- P1 | P1-1 | "Missing Test Updates" | Plan deletes autopilot.sh but doesn't update structural tests that verify its existence
- P1 | P1-2 | "Documentation Scope Gaps" | Plan updates 2 docs but misses 15+ references across research, plans, and README
- P1 | P1-3 | "Hook Count Inconsistency" | Deleting PreToolUse changes hook count from 5 to 4 but plan doesn't update CLAUDE.md
- IMP | IMP-1 | "Script Location Convention" | New toggle script should live in hooks/ not scripts/ for consistency with other session-level state management
- IMP | IMP-2 | "Verification Depth" | Plan needs runtime behavioral verification strategy, not just syntax checks
- IMP | IMP-3 | "Rollback Strategy" | No documented recovery path if behavioral contract proves insufficient in production
Verdict: risky

### Summary

This plan removes a mechanical enforcement layer (PreToolUse hook) and replaces it with a purely behavioral contract (context injection), fundamentally changing the clodex system's reliability model from "cannot violate" to "should not violate." The architectural concern is not whether this *can* work, but whether the plan provides sufficient verification that it *does* work, and what happens when it doesn't.

The plan has two P0 gaps: (1) no verification strategy for whether the behavioral contract actually prevents unwanted writes in practice, and (2) insufficient scope analysis — the plan identifies 6 files to modify but the codebase has 15+ documentation references to the hook, plus structural tests that will break. The verification section proposes syntax checks and pytest, but the core risk is behavioral — will Claude actually respect the context injection without the hook backstop? The plan provides no way to measure this.

The architectural shift itself is defensible: hooks that block Claude's tools create friction, and behavioral contracts are the native enforcement layer for LLM-driven systems. But the plan treats this as a refactoring (delete hook, update docs) when it's actually a reliability model change that requires behavioral validation and monitoring.

### Issues Found

#### P0-1: Removing deny-gate without comprehensive verification plan creates unauditable behavioral contract enforcement

**Location:** Entire plan scope, specifically Step 3 (delete autopilot.sh) and verification section

**Problem:** The plan removes a mechanical gate (PreToolUse hook that returns `permissionDecision: deny`) and replaces it with context injection, but provides no way to verify the behavioral contract actually works in production. The verification section (lines 80-87) only checks syntax and structural tests — it doesn't verify whether Claude will respect the injected context.

**Risk:** After deployment, there's no way to detect when Claude violates the clodex contract. The old system failed safe (hook denied writes). The new system fails open (Claude gets a reminder in context but no enforcement). Without audit telemetry, clodex mode violations become silent failures.

**Architecture Impact:** This changes the system boundary. Currently: clodex mode is a hard constraint enforced by the Claude Code runtime (PreToolUse hook). Proposed: clodex mode is a soft suggestion carried in Claude's context window. This is a fundamental reliability model shift from "cannot violate" to "should not violate."

**Evidence:**
- Verification section only checks: `bash -n` syntax, `python3 -c "import json"` for hooks.json, pytest structural tests, manual toggle test
- None of these verify behavioral contract adherence — they only verify files parse correctly
- Session-start injection (lines 48-61) has no mechanism to detect if Claude ignores it
- Plan explicitly says "This is the *only* enforcement mechanism — no hook backstop" (line 63) but provides no telemetry to verify it works

**Specific gap:** After this change ships, how do you know when Claude writes to a .go file in clodex mode instead of dispatching? The old system: hook logs a denial. The new system: no signal unless you manually diff `git status`.

**What's needed:** Either (1) add telemetry to detect contract violations (PostToolUse hook that logs writes to source files when clodex flag exists, write-only, no denial), or (2) staged rollout with manual verification period (deploy, monitor git history for unexpected direct commits in clodex projects, measure for 1 week before declaring success).

**Why P0:** Removing an enforcement mechanism without verification that its replacement works is a reliability regression. In a system where the whole point is routing work through Codex to stay under Claude's token limits, silently failing to route is a budget overspend risk.

---

#### P0-2: Behavioral contract sufficiency analysis missing — context injection vs hook denial have different reliability guarantees

**Location:** Step 5 (session-start.sh context injection), design rationale (implicit)

**Problem:** The plan assumes context injection is sufficient replacement for hook denial, but doesn't analyze the behavioral contract's actual enforcement power. Session-start context gets injected once per session. Claude's context window is ~200k tokens. After 50 tool calls and 20k tokens of conversation, that 9-line injection (lines 48-61) may be 100k tokens away from Claude's current attention window.

**Architecture concern:** Hooks run on every tool call (per-event enforcement). Context injection runs once at session start (session-level reminder). These have different temporal reliability. The plan treats them as equivalent substitutes.

**Specific scenario that could fail:**
1. User starts session, clodex flag is ON, context injection happens
2. User runs `/lfg`, generates brainstorm (15k tokens), writes plan (8k tokens), reviews plan (12k tokens)
3. Context window is now 35k+ tokens, session-start injection is distant in context
4. Plan execution begins — Claude's current attention is focused on the plan's task list, not the session-start reminder
5. Task says "Modify handler.go to add timeout retry" — Claude directly edits handler.go instead of dispatching
6. No hook denial, no error, change lands in git

**Why this matters:** The plan doesn't discuss context window dilution or provide any mitigation (e.g., injecting a reminder at the start of `/clodex` skill invocation, or adding a system message to the behavioral contract that persists beyond session-start).

**What's missing:** Analysis of when the behavioral contract is weak. Session-start injection is strong for the first 10-20 tool calls. What about after 100 tool calls? What about multi-hour sessions? The old hook enforced on every Edit/Write call. The new contract enforces... when? Only when Claude happens to recall it?

**Why P0:** The plan proposes removing a per-call enforcement gate and doesn't analyze whether a session-level reminder has the same reliability properties. This is an architectural assumption that needs validation, not assertion.

---

#### P1-1: Plan deletes autopilot.sh but doesn't update structural tests that verify its existence

**Location:** Step 3 (delete hooks/autopilot.sh), verification section

**Problem:** The structural test suite (`tests/structural/test_scripts.py`) has dynamic discovery that finds all `.sh` files and validates they have shebangs and pass syntax checks. When `autopilot.sh` is deleted, those tests will still pass (they just won't test autopilot anymore). But `test_hooks_json.py::test_hooks_json_commands_exist` explicitly verifies that every script referenced in hooks.json exists on disk. The plan removes the PreToolUse section from hooks.json (Step 4), so that test will pass. However, there's a pytest cache at `tests/.pytest_cache/v/cache/nodeids` that lists `test_scripts.py::test_shell_scripts_syntax[autopilot.sh]` — the cache needs invalidation.

**More importantly:** The plan says "uv run --project tests pytest tests/structural/ -q" will verify correctness (line 86), but it doesn't update the test suite to reflect the new architecture. After this change, the test suite should verify:
- hooks.json has exactly 3 event types (SessionStart, Stop, SessionEnd), not 4
- session-start.sh clodex injection is present (currently not tested)
- No PreToolUse hooks exist (regression guard)

**Why P1:** Test suite will pass but won't verify the new architecture is correct. Silent test gaps are P1 because they allow future regressions.

**Fix:** Add to verification section: "Update `tests/structural/test_hooks_json.py` to assert PreToolUse is NOT in hooks.json keys. Add test case for session-start clodex injection presence."

---

#### P1-2: Documentation scope gaps — plan updates 2 docs but codebase has 15+ references to PreToolUse hook and autopilot.sh

**Location:** "Files Modified" table (lines 70-75), "Files NOT Modified" section (lines 77-78)

**Problem:** The plan identifies 2 documentation files to update:
1. `commands/clodex-toggle.md` — rewrite as thin wrapper
2. `skills/clodex/references/behavioral-contract.md` — remove hook references

But grep shows 15+ files reference the PreToolUse hook or autopilot.sh:
- `AGENTS.md` line 153-154: "PreToolUse... autopilot.sh validates write operations"
- `README.md` line 198: "PreToolUse — Autopilot gate"
- `README.md` line 263: "hooks/ # 5 hooks (SessionStart, Stop×2, SessionEnd, PreToolUse)"
- `skills/executing-plans/SKILL.md` line 27: checks for clodex flag, references "clodex mode" dispatching
- Multiple files in `docs/research/flux-drive/` that describe the hook architecture
- `docs/plans/2026-02-10-test-suite-design.md` — has test specifications for autopilot.sh

**Why this matters:** After this change, 13+ doc files will describe a hook that no longer exists. This creates confusion for contributors and false expectations for users who read AGENTS.md or README.md.

**Specific gaps:**
- `AGENTS.md` "Hooks" section needs updating (currently lists PreToolUse as hook #1)
- `README.md` needs hook count change: "5 hooks" → "4 hooks"
- `CLAUDE.md` line 7: "5 hooks" → "4 hooks"
- All research docs in `docs/research/flux-drive/*/fd-architecture.md` that analyze hook structure will be stale

**Why P1:** Stale documentation is a P1, not P2, because it directly misleads users about how clodex enforcement works. Someone reading AGENTS.md will think writes are denied by a hook when they're actually just discouraged by context.

**Fix needed:** Add to "Files Modified" section:
- `AGENTS.md` — update Hooks section, remove autopilot.sh reference
- `README.md` — change hook count to 4, update Hooks section
- `CLAUDE.md` — change hook count to 4
- `.claude-plugin/plugin.json` — description/metadata if it mentions hooks

Mark `docs/research/` files as "acceptable stale" (they're historical research, not user-facing docs).

---

#### P1-3: Hook count reduction not propagated to headline counts in CLAUDE.md and README.md

**Location:** CLAUDE.md line 7, README.md line 7

**Current state:**
- CLAUDE.md: "5 hooks"
- README.md: "5 hooks"
- Actual hooks.json: PreToolUse, SessionStart, Stop (2 scripts), SessionEnd = 5 hooks

**After this change:**
- Hooks.json will have: SessionStart, Stop (2 scripts), SessionEnd = 4 hooks (or 4 event types if counting events not scripts)
- But CLAUDE.md and README.md will still say "5 hooks"

**Why this matters:** The headline count is a verification surface. When someone runs `ls hooks/*.sh | wc -l` they get 5 (session-start, auto-compound, session-handoff, dotfiles-sync, autopilot). After this change they'll get 4. The docs need to match.

**Clarification needed:** Does "5 hooks" count event types or script files? Current hooks.json has 4 event types (PreToolUse, SessionStart, Stop, SessionEnd) but 5 script files (autopilot, session-start, auto-compound, session-handoff, dotfiles-sync). After removing PreToolUse, it's 3 event types, 4 scripts. The plan should specify which count to use.

**Why P1:** Count mismatches break the quick validation commands in CLAUDE.md. If line 7 says "5 hooks" but `ls hooks/*.sh | wc -l` returns 4, contributors don't know if they broke something or the docs are wrong.

---

### Improvements Suggested

#### IMP-1: New toggle script location breaks convention — should be in hooks/ not scripts/

**Location:** Step 1 (create `scripts/clodex-toggle.sh`)

**Current convention:** All session-level state management lives in `hooks/`:
- `hooks/session-start.sh` — reads clodex flag, injects context
- `hooks/autopilot.sh` — reads clodex flag, enforces writes
- `hooks/auto-compound.sh` — reads session state, logs signals

**Proposed:** `scripts/clodex-toggle.sh` — writes clodex flag

This breaks the convention that hooks/ owns session state, scripts/ owns external tools (dispatch.sh, upstream-check.sh, install-codex.sh).

**Better location:** `hooks/clodex-toggle.sh` — keeps all clodex state management in one directory. The fact that it's invoked via a command (not a hook event) doesn't matter — it's still session state.

**Counter-argument:** "scripts/ is for user-invocable scripts" — but `hooks/session-start.sh` is also invoked manually during troubleshooting (`bash hooks/session-start.sh` to test injection). The semantic boundary is "session state" vs "external tools," not "hook-invoked" vs "user-invoked."

**Why IMP not P1:** This works either way, just less consistent. scripts/ will have one session-state-mutating script (toggle) and multiple external-tool-wrappers (dispatch, upstream-check). hooks/ will have 3 session-state-readers (session-start, auto-compound, session-handoff) and 1 session-state-writer in a different directory.

**Recommendation:** Move to `hooks/clodex-toggle.sh` for semantic consistency.

---

#### IMP-2: Verification section lacks runtime behavioral testing — only validates syntax and structure

**Location:** Verification section (lines 80-87)

**Current verification:**
1. Syntax check the toggle script
2. Syntax check session-start.sh
3. Validate hooks.json JSON
4. Verify autopilot.sh doesn't exist
5. Run pytest structural tests
6. Manual test: toggle ON/OFF

**What's missing:** Behavioral verification. None of these checks verify that Claude actually respects the context injection. They verify the files are syntactically correct, but not that the system works.

**Needed additions:**
1. **Smoke test:** Start a fresh session with clodex ON, ask Claude to "fix a bug in test.go," verify Claude suggests `/clodex` dispatch instead of directly editing
2. **Negative test:** Start session with clodex OFF, ask Claude to edit test.go, verify direct edit works
3. **Context persistence test:** In a clodex ON session, generate 20k tokens of conversation (brainstorm + plan), then ask Claude to modify a source file — verify it still routes through clodex

**Why this matters:** The whole architectural change depends on behavioral contract strength. Without runtime verification, you won't know if it works until a user reports "Claude keeps directly editing files in clodex mode."

**Implementation:** Add to verification section:
```
7. Behavioral smoke test:
   - Start new session with clodex flag ON
   - Run: "Please add a retry timeout to handler.go"
   - Expected: Claude suggests using /clodex skill or asks to toggle OFF
   - Failure: Claude directly edits handler.go
```

**Why IMP not P1:** The plan will work in the simple case (fresh session, clear instructions). The risk is edge cases (long sessions, complex task context). Smoke testing catches simple failures; full behavioral testing would be P1 scope creep.

---

#### IMP-3: No rollback or gradual-rollout strategy if behavioral contract proves insufficient

**Location:** Implicit — plan doesn't discuss deployment or monitoring

**Current plan:** Merge, publish, done. Assumes behavioral contract works universally.

**Realistic scenario:** Behavioral contracts work 95% of the time. The 5% failure mode: Claude forgets the contract after long sessions or complex task context. Users report "clodex mode isn't working, Claude keeps editing files directly."

**What's missing:** Rollback plan. If the behavioral contract proves insufficient:
1. Restore the hook with a weaker deny message? (Allow override?)
2. Keep the behavioral contract but add PostToolUse telemetry to detect violations?
3. Add a hybrid mode: hook warns but doesn't deny, logs violations?

**Why this matters:** The plan treats this as a one-way door (delete hook, move to behavioral contract). But software changes should be reversible. The hook deletion is easy to reverse (git revert), but by the time you realize it's needed, users have already experienced silent failures.

**Recommendation:** Before merging:
1. Add a feature flag or environment variable that can re-enable hook enforcement without code changes
2. OR: Deploy to personal projects first, monitor for 1 week, then publish to marketplace
3. OR: Add PostToolUse logging (write-only, no denial) so violations are visible in debug output

**Why IMP not P1:** This is operational maturity, not a technical gap. The plan will work for most users. But best practice for enforcement mechanism changes is gradual rollout with monitoring.

**Specific implementation:** Keep autopilot.sh but change the deny decision to a log-only mode:
```bash
# Instead of denying, log and allow
echo "WARNING: clodex mode is ON but Edit was called on $FILE_PATH" >&2
exit 0  # Don't deny, just warn
```

Then collect telemetry for 1 week, verify warnings are rare, then fully remove the hook.

---

### Overall Assessment

This plan removes a mechanical enforcement gate and replaces it with a behavioral contract, which is architecturally sound for LLM-driven systems — behavioral boundaries are the native abstraction layer. The problem is not the *what* (behavioral contract) but the *how* (insufficient verification that it works, incomplete scope analysis).

**Two paths forward:**

**Path A: Low-risk (add verification, fix scope):**
1. Keep the behavioral contract approach (it's good)
2. Add behavioral smoke tests to verification section (IMP-2)
3. Update all docs (P1-2: AGENTS.md, README.md, CLAUDE.md hook counts)
4. Add structural test for "no PreToolUse in hooks.json" (P1-1)
5. Deploy to personal projects first, monitor git history for unexpected direct edits in clodex sessions
6. After 1 week clean, publish to marketplace

**Path B: Hybrid (keep telemetry backstop):**
1. Implement behavioral contract as planned
2. Keep autopilot.sh but change from deny to log-only (writes warning to stderr, doesn't block)
3. Add PostToolUse hook that logs when clodex flag is ON and a source file was written
4. Monitor logs for 1 month, collect violation rate data
5. If violations <1%, remove logging hooks and declare behavioral contract sufficient
6. If violations >1%, strengthen contract (add reminder injection to /clodex skill, add system message)

**Recommendation:** Path A with one addition from Path B — keep a PostToolUse logging hook (write-only, no denial) for 1 month after deployment. This gives you violation telemetry without blocking Claude. Remove after data confirms behavioral contract is sufficient.

**Why risky instead of needs-changes:** The core plan is architecturally sound. The risks are verification gaps (P0-1, P0-2) and scope completeness (P1-2). These are fixable by expanding verification and doc scope — they don't require rethinking the approach. But without those fixes, you're deploying an enforcement mechanism change with no way to verify it works, which is risky.

**Specific changes needed to move to safe:**
1. Add behavioral smoke test to verification (IMP-2)
2. Add rollback/monitoring strategy (IMP-3 or hybrid approach)
3. Update AGENTS.md, README.md, CLAUDE.md hook counts (P1-2, P1-3)
4. Add structural test for no PreToolUse (P1-1)
5. Deployment strategy: personal testing period before marketplace publish

<!-- flux-drive:complete -->
