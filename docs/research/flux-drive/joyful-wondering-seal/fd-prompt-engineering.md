### Findings Index
- P0 | P0-1 | "Step 5 — Injection Text" | Bash tool writes are an unguarded bypass — the injection only forbids Edit/Write, not `Bash(echo/cat/sed/tee > source.py)`
- P0 | P0-2 | "Step 5 — Injection Text" | "Source code" is undefined — no file extension list or heuristic tells Claude what counts as source code vs. non-code
- P1 | P1-1 | "Step 5 — Injection Text" | No mention of Bash tool restriction for destructive commands (rm, mv, chmod on source files)
- P1 | P1-2 | "Step 6 — Behavioral Contract Update" | Plan says "remove hook references" but gives no replacement text — risk of an incoherent or half-updated document
- P1 | P1-3 | "Verification" | No behavioral test — verification is all structural (syntax, JSON, file existence) but nothing validates the injection actually routes Claude
- IMP | IMP-1 | "Step 5 — Injection Text" | Injection text should name the escape hatch cost — why NOT editing directly matters (token budget, Codex limits)
- IMP | IMP-2 | "Step 5 — Injection Text" | "Non-code files (.md, .json, .yaml, .toml, etc.)" uses "etc." — should be an explicit list matching the former hook's allowlist
- IMP | IMP-3 | "Step 5 — Injection Text" | Missing: what to do when Codex is unavailable (CLI not installed, config missing)
- IMP | IMP-4 | "Step 2 — Command Rewrite" | The thin wrapper should echo the behavioral contract summary on ON, not just the toggle state, since there is no longer a hook to remind Claude
Verdict: needs-changes

### Summary

The plan's core idea is sound: removing the deny-gate hook in favor of a pure behavioral contract injected at session start. This eliminates a class of friction (hook false-positives on non-code files, latency on every Edit/Write call) while simplifying the hook surface. However, the proposed injection text in Step 5 — the single point of enforcement — has two P0 gaps: (1) it forbids Edit/Write but says nothing about the Bash tool, which can write arbitrary files via shell redirects, and (2) it never defines what "source code" means, leaving Claude to guess which files need dispatch. The existing hook had an explicit extension allowlist for exactly this reason.

### Issues Found

#### P0-1: Bash tool writes are an unguarded bypass

**Location:** Step 5 injection text, line "Do NOT use Edit/Write on source code"

The injection says "Do NOT use Edit/Write on source code." But Claude has a third write vector: the Bash tool. Commands like `echo "code" > main.py`, `cat <<EOF > handler.go`, `sed -i 's/old/new/' service.ts`, and `tee source.rs` all modify source files without touching Edit or Write. The existing deny-gate hook (`autopilot.sh`) only matched `Edit|Write|MultiEdit|NotebookEdit` — so this gap already existed with the hook. But the hook's hard denial at least made Claude aware something was wrong if it tried Edit/Write. Without the hook, and with no mention of Bash writes, Claude has zero friction on any write path.

The existing behavioral contract (`behavioral-contract.md` lines 15-16) partially addresses this with an "Allowed Bash (read-only)" section listing specific safe commands. But the Step 5 injection text does not incorporate this. It says "Read/Grep/Glob freely" (step 1) and "Git operations are yours" (step 5) but never says "Bash is read-only for everything except git and test commands."

**Recommended fix:** Add an explicit Bash rule to the injection:

```
Bash: read-only only (git, test, build commands). Do NOT use Bash to write/modify source files (no redirects, sed -i, tee, etc.).
```

This should appear between steps 1 and 2, or as a bolded rule after the numbered list.

#### P0-2: "Source code" is undefined in the injection

**Location:** Step 5 injection text, "Do NOT use Edit/Write on source code"

The term "source code" appears without definition. The existing hook defined this precisely via an extension allowlist: `.md`, `.json`, `.yaml`, `.yml`, `.toml`, `.txt`, `.csv`, `.xml`, `.html`, `.css`, `.svg`, `.lock`, `.cfg`, `.ini`, `.conf`, `.env` were allowed; everything else was denied. The behavioral contract (`behavioral-contract.md` line 19) has an explicit list: `*.go`, `*.py`, `*.ts`, `*.js`, `*.rs`, `*.java`, `*.rb`, `*.c`, `*.cpp`, `*.h`, `*.swift`, `*.kt`, `*.sh`.

Without this, Claude must infer whether a `.proto` file, a `Makefile`, a `Dockerfile`, a `.sql` migration, or a `.graphql` schema is "source code." Different Claude instances will make different judgment calls, leading to inconsistent routing.

The injection text does say "Non-code files (.md, .json, .yaml, .toml, etc.) can still be edited directly" but the "etc." is doing too much work. It should either:
- List all allowed extensions explicitly (matching the former hook's allowlist), or
- State the heuristic: "If a file would be compiled, interpreted, or executed as program logic, it's source code — dispatch it."

**Recommended fix:** Replace the vague line with:

```
Direct-edit OK: .md, .json, .yaml, .yml, .toml, .txt, .csv, .xml, .html, .css, .svg, .lock, .cfg, .ini, .conf, .env, dotfiles, /tmp/*
Everything else (code files): dispatch via /clodex
```

#### P1-1: No restriction on destructive Bash commands against source files

**Location:** Step 5 injection text

Beyond writes, the Bash tool can `rm`, `mv`, or `chmod` source files. The current hook doesn't guard against these either, but the behavioral contract should. If Claude is not supposed to modify source code, it also should not delete or rename source files directly — those are implementation changes that should go through Codex.

**Recommended fix:** Extend the Bash rule:

```
Bash: read-only for source files. No writing (redirects, sed -i), no deleting (rm), no renaming (mv). Git and test/build commands are fine.
```

#### P1-2: Step 6 gives no replacement text for the behavioral contract update

**Location:** Step 6 — "Remove references to 'PreToolUse hook', 'blocked by hook', 'denied with dispatch instructions'"

The plan says what to remove but not what to replace it with. The behavioral contract (`behavioral-contract.md`) currently says things like "not blocked by hook" in the "Allowed Direct Edits" header comment. After removing hook references, the document needs a coherent narrative: "This contract is enforced via session-start context injection. There is no hook backstop."

Without replacement text, whoever implements Step 6 might:
- Delete too much (leaving a skeletal document that doesn't explain enforcement)
- Delete too little (leaving stale hook references)
- Rewrite inconsistently with the Step 5 injection text

**Recommended fix:** Provide the target state of `behavioral-contract.md` in the plan, not just deletion instructions. At minimum, add a line like: "Add a note at the top: 'This contract is enforced purely through session-start context injection. No PreToolUse hook is involved.'"

#### P1-3: No behavioral verification step

**Location:** Verification section (lines 82-87)

All six verification steps are structural: syntax checks, JSON validity, file existence, pytest. None test whether the injection text actually causes Claude to route through Codex. This is the riskiest part of the change — the entire enforcement mechanism is now a prompt, and prompts can fail silently.

The plan should include at least one behavioral verification:
- A smoke test where a clodex-ON session is asked to "fix a typo in scripts/dispatch.sh" and the test verifies Claude invokes `/clodex` rather than Edit
- Or a manual test protocol: "Enable clodex, ask Claude to edit a .py file, verify it dispatches rather than editing directly"

**Recommended fix:** Add verification step 7:

```
7. Behavioral smoke test: Start a session with clodex ON, ask "add a comment to scripts/dispatch.sh line 1", verify Claude dispatches via /clodex rather than using Edit directly. (Manual — cannot be automated in pytest.)
```

### Improvements Suggested

#### IMP-1: Injection should explain WHY — the token budget motivation

The injection text tells Claude what to do but not why. Claude is more likely to comply with behavioral instructions when it understands the rationale. The existing `clodex-toggle.md` command (line 37) hints at this but the injection doesn't.

**Suggested addition** (one line at the top of the injection):

```
**CLODEX MODE: ON** — Route ALL implementation through Codex (preserves Claude token budget for orchestration).
```

This costs 10 tokens and significantly increases compliance because Claude understands the constraint serves a purpose rather than being arbitrary.

#### IMP-2: Replace "etc." with explicit extension list

**Location:** Step 5 injection text, "Non-code files (.md, .json, .yaml, .toml, etc.)"

The "etc." introduces ambiguity. The hook had a precise 16-extension allowlist. The behavioral contract (`behavioral-contract.md` line 13) has the same list. The injection should match.

**Suggested:** Either list them all (`.md`, `.json`, `.yaml`, `.yml`, `.toml`, `.txt`, `.csv`, `.xml`, `.html`, `.css`, `.svg`) or use the framing "config and documentation files" with a parenthetical of the most common ones plus "see behavioral-contract.md for full list."

#### IMP-3: Missing fallback when Codex CLI is unavailable

The SKILL.md (line 30) says: "If Codex is unavailable, suggest falling back to `clavain:subagent-driven-development`." But the injection text doesn't mention this. If someone enables clodex mode without Codex installed, Claude will be stuck: forbidden from editing source code but unable to dispatch.

**Suggested addition:**

```
If Codex CLI is not available, fall back to clavain:subagent-driven-development or run /clodex-toggle to turn off.
```

#### IMP-4: The thin toggle wrapper (Step 2) should echo the contract summary

Currently the plan says the toggle ON message just prints state. But the old 90-line command (lines 36-44) printed a detailed explanation of what's blocked vs. allowed. Since there's no longer a hook to remind Claude on every write attempt, the toggle's ON message is the last explicit reminder before the session proceeds. It should include at minimum the 5-step behavioral contract summary.

The script output should include the injection text (or a condensed version) so Claude sees it twice: once from the toggle, once from session-start on next resume.

### Overall Assessment

The plan's architecture is correct: a pure behavioral contract is simpler, more maintainable, and eliminates hook latency. The deny-gate was always incomplete (it didn't catch Bash writes) and its hard denials created friction without routing. Removing it is the right call.

However, the injection text — now the sole enforcement mechanism — needs to be tighter. The two P0 issues (Bash bypass, undefined "source code") mean the current injection text would allow Claude to circumvent clodex mode through normal tool usage without even realizing it's violating the contract. The existing behavioral-contract.md already has the answers (explicit extension lists, Bash read-only rules) — the injection just needs to incorporate them.

The P1 issues (destructive Bash, incomplete Step 6, no behavioral test) are important but less urgent — they represent gaps in thoroughness rather than fundamental design flaws.

Estimated risk: **Medium-High** if shipped as-is (the Bash bypass alone makes clodex mode porous). **Low** if P0-1 and P0-2 are addressed (the contract becomes as precise as the hook was, minus the hard gate).

<!-- flux-drive:complete -->
