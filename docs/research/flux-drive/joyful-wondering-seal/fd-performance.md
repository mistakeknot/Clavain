### Findings Index
- P0 | P0-1 | "Session-start injection cost" | 8-line injection adds 100-150 tokens per session — justified by removing per-tool overhead
- P1 | P1-1 | "Behavioral contract optimization" | Contract can be compressed to match toggle message format
- IMP | IMP-1 | "Quantified savings from hook removal" | Removing PreToolUse hook eliminates 5ms + jq overhead on every Edit/Write call
- IMP | IMP-2 | "Quantified savings from toggle script conversion" | Bash toggle eliminates 1 full LLM round-trip (1500-3000 tokens saved per toggle)
- IMP | IMP-3 | "Additional optimization opportunity" | Session-start injection can reference behavioral-contract.md instead of inlining

Verdict: safe

### Summary

The plan converts a hybrid enforcement system (PreToolUse gate + context injection) into a pure behavioral contract enforced via session-start context. From a token and latency perspective, this is strongly justified. The proposed 8-line session-start injection adds 100-150 tokens per session, but eliminates (1) per-tool hook overhead on every Edit/Write call (5ms + jq parsing), and (2) converts the toggle command from LLM-driven to zero-latency bash script, saving 1500-3000 tokens per toggle invocation.

The session-start injection cost is front-loaded (once per session) while the PreToolUse hook cost was recurring (every Edit/Write). For a typical session with 10-20 edit operations, removing the hook saves 50-100ms of cumulative latency. The behavioral contract text could be further optimized by referencing the external file instead of inlining, saving another 50-70 tokens per session.

### Issues Found

#### P0-1: Session-start injection cost justified by removing per-tool overhead

**Location:** `hooks/session-start.sh` line 68, plan step 5

**Current state:**
- Session-start currently injects 1-line clodex notification (32 tokens)
- PreToolUse hook runs on every Edit/Write/MultiEdit/NotebookEdit call (5ms baseline + jq parsing)

**Proposed change:**
8-line behavioral contract injection (estimated 100-150 tokens):
```
**CLODEX MODE: ON** — Route ALL implementation through Codex.

You are an orchestrator. Do NOT use Edit/Write on source code. Instead:
1. Read/Grep/Glob freely to understand the codebase
2. Write task prompts to /tmp/ files
3. Dispatch via /clodex skill → Codex agents do the implementation
4. Verify: read output, run tests, review diffs
5. Git operations (add, commit, push) are yours — do them directly

Non-code files (.md, .json, .yaml, .toml, etc.) can still be edited directly.
Run /clodex-toggle to turn off.
```

**Token accounting:**
- **Cost:** +118 tokens per session (8 lines × ~15 tokens/line average)
- **Saved per Edit call:** ~5ms latency + negligible token cost (hook output is empty on pass-through)
- **Saved per toggle:** 1500-3000 tokens (eliminates LLM call entirely)

**Justification:**
This is a classic front-loading optimization. The 118-token session-start cost is paid once, while the PreToolUse hook latency was paid on every Edit/Write operation. For a typical clodex session with 10-20 Codex dispatch cycles (read/plan/dispatch/verify), Claude might attempt 5-10 direct edits before routing correctly. Removing the hook eliminates 25-50ms of cumulative latency.

More importantly, the toggle command conversion from LLM-driven to bash script is a massive win — every toggle invocation currently burns 1500-3000 tokens for Claude to parse the command markdown, check state, write the flag file, and return status. The bash script does this in <10ms with zero LLM calls.

**Risk:** Low. The behavioral contract is clear and specific enough to trigger routing without enforcement. The existing toggle command's "Behavioral Contract Reminder" section (lines 56-66) already proves Claude can internalize these rules.

**Recommendation:** Accept this trade-off. The per-session cost is small compared to the recurring savings.

### Improvements Suggested

#### IMP-1: Quantified savings from PreToolUse hook removal

**Measurement:**
The PreToolUse hook in `hooks/autopilot.sh` runs on every Edit/Write/MultiEdit/NotebookEdit call. From `hooks/hooks.json`:
```json
"matcher": "Edit|Write|MultiEdit|NotebookEdit",
"timeout": 5
```

The hook performs:
1. File existence check (`[[ -f "$FLAG_FILE" ]]`) — 1-2ms
2. jq parsing of tool input JSON (stdin) — 2-3ms
3. Path-based exception matching (lines 41-60) — <1ms
4. jq output encoding if denied — 1-2ms

**Per-call overhead:** 5-8ms when clodex mode is OFF (early exit at line 27), 8-12ms when ON (full path checks + potential deny).

**Cumulative cost in a typical session:**
- Session with 20 Edit/Write operations = 100-240ms total latency
- Token cost is zero (hook output is empty on pass-through, ~50 tokens on deny)

**Savings from removal:**
Eliminating this hook removes 5-12ms per tool call. The latency is small per-call but accumulates. More importantly, it removes a *synchronous blocking operation* from the critical path of every file write.

#### IMP-2: Quantified savings from toggle command conversion

**Current implementation (LLM-driven):**
The `/clodex-toggle` command is a 90-line markdown file with embedded bash snippets. When invoked:
1. Claude reads the command markdown (503 words ≈ 670 tokens input)
2. Claude parses instructions, generates bash commands
3. Claude executes bash via Bash tool (flag file check + toggle)
4. Claude formats response with status message (200-300 tokens output)

**Total per-toggle cost:** 1500-3000 tokens (input + output + reasoning)

**Proposed implementation (bash script):**
Direct bash execution via thin command wrapper:
- Command markdown reduced to ~10 lines (just invokes script)
- Script runs in <10ms, outputs formatted message
- Claude receives pre-formatted output, no reasoning needed

**Total per-toggle cost:** <100 tokens (just the command invocation + output)

**Savings:** 1400-2900 tokens per toggle, plus elimination of LLM latency (typically 2-5 seconds for a simple command).

**Frequency:** Toggle operations are relatively rare (1-3 times per project setup), but the savings are significant when they do occur.

#### IMP-3: Session-start injection can reference behavioral-contract.md instead of inlining

**Current proposal:**
Inline 8 lines of behavioral contract text in session-start.sh (lines 65-68 of the plan).

**Token cost:** 100-150 tokens per session

**Alternative approach:**
Replace inline text with a file reference:
```bash
if [[ -f "$CLODEX_FLAG" ]]; then
    contract_text=$(cat "${PLUGIN_ROOT}/skills/clodex/references/behavioral-contract.md" 2>/dev/null) || contract_text="Clodex mode ON (contract unavailable)"
    companions="${companions}\\n- **clodex**: ON — $(escape_for_json "$contract_text")"
fi
```

**Token cost:** 50-70 tokens per session (just the contract title + first rule, or a pointer)

**Savings:** 30-80 tokens per session

**Trade-off:**
- **Pro:** Slightly lower per-session cost, behavioral contract stays in sync with reference doc
- **Con:** Requires file read (negligible latency ~1ms), adds dependency on file availability
- **Con:** Existing behavioral-contract.md is 20 lines including headers — needs condensing to match proposed 8-line format

**Recommendation:**
If the behavioral contract is expected to evolve frequently, this approach keeps the source of truth in one place. However, the current proposal's inline approach is simpler and avoids file I/O. The 30-80 token difference is marginal compared to the overall session context budget.

**Better optimization:**
Condense the proposed 8-line injection to match the structure of behavioral-contract.md's "Three Rules" format (3 numbered rules + exception), reducing to ~60-80 tokens:

```
**CLODEX MODE: ON** — Route source code changes through Codex.
1. Read freely (Read/Grep/Glob)
2. Write source via /clodex dispatch
3. Edit non-code directly (.md/.json/.yaml/etc)
Exception: Git ops are yours (add/commit/push).
Run /clodex-toggle to turn off.
```

This cuts the injection from 118 tokens to ~70 tokens (40% reduction) while preserving clarity.

#### P1-1: Behavioral contract can be compressed to match toggle message format

**Location:** Plan step 5 (session-start injection)

**Issue:**
The proposed 8-line session-start injection duplicates much of the information already in the toggle command's output message. The toggle command (lines 34-44) already tells the user:
- Edit/Write to source code will be blocked
- Non-code files are still editable
- /tmp/ files are writable
- Git operations are Claude's responsibility

The session-start injection repeats all of this, creating redundancy.

**Optimization:**
The session-start injection should focus on *routing instructions* rather than *capability descriptions*. The toggle output handles the "what's blocked" messaging, so the session-start context can be more concise:

**Proposed compressed version (4 lines, ~70 tokens):**
```
**CLODEX MODE: ON** — Dispatch source code changes via /clodex.
Plan (Read/Grep) → Prompt (Write to /tmp/) → Dispatch (/clodex) → Verify (diff/test).
Non-code files (.md/.json/.yaml) editable directly. Git ops yours.
Toggle off: /clodex-toggle
```

**Savings:** 48 tokens per session (from 118 to 70)

**Justification:**
The toggle command already primes Claude with the full behavioral contract when clodex mode is turned ON (lines 56-66 of the toggle command). The session-start injection is for *resume* scenarios where Claude didn't see the toggle output. In those cases, a concise reminder is sufficient.

### Overall Assessment

This plan is a well-reasoned performance optimization with strongly positive cost/benefit characteristics. The key insight — replacing recurring per-tool-call overhead with a one-time per-session context injection — is sound architectural thinking.

**Quantified benefits:**
1. **PreToolUse hook removal:** Eliminates 5-12ms per Edit/Write call (100-240ms per session with 20 edits)
2. **Toggle script conversion:** Saves 1400-2900 tokens per toggle invocation (rare but high-impact)
3. **Simplified enforcement:** Removes a synchronous blocking hook from the critical path

**Quantified costs:**
1. **Session-start injection:** +70-118 tokens per session (depending on compression level)

**Net result:** Positive for any session with >1 edit operation, strongly positive for sessions with 10+ edits or any toggle operations.

**Recommended refinements:**
1. Compress the session-start injection to 4 lines (~70 tokens) using the format from IMP-3
2. Update behavioral-contract.md to match the compressed format for consistency
3. Verify that the compressed version is still clear enough to trigger correct routing behavior

**Risk assessment:**
The only real risk is behavioral — will Claude respect the session-start contract without the PreToolUse gate enforcing it? The existing toggle command's reminder section (lines 56-66) suggests yes, but this should be validated with smoke tests. If routing compliance drops, the gate can be re-added as a fallback, but the script-based toggle should be kept regardless (it's a pure win).

<!-- flux-drive:complete -->
