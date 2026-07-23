---
artifact_type: plan
bead: mk-e6ta
stage: design
requirements:
  - F1: Trustworthy tldrs packet selection
  - F2: Auditable Clavain context gateway
  - F3: Cross-harness interactive adoption
  - F4: Token and coding-performance validation
---
# tldrs Context Gateway Enforcement Implementation Plan

> **For implementers:** Use `intertest:test-driven-development` for every behavior change and `intertest:verification-before-completion` before release.

**Bead:** `mk-e6ta`

**Goal:** Ensure Clavain-launched and Clavain-enabled coding agents receive a validated, bounded tldrs packet before model invocation, or produce an explicit bypass/fallback receipt, without regressing coding correctness.

**Architecture:** tldr-swinton owns deterministic source ranking, packet assessment, packet rendering, and a portable receipt payload. Clavain owns task eligibility, receipt persistence, prompt injection, harness-profile selection, and native hook/installer adapters. Direct dispatch is the hard enforcement boundary; interactive hooks provide additional coverage but are never treated as the sole guarantee.

**Tech stack:** Python 3 stdlib, Bash, Bats, pytest, Claude/Codex/Kimi lifecycle hooks, JSON/JSONL.

**Prior Learnings:**

- `tldr-swinton/docs/research/2026-07-22-external-context-gateway-validation.md` validated middleware-first packets across Python, Go, Codex, and Claude. The promoted Codex owner-hint profile uses 750 source characters; generic and Claude use 1500.
- `tldr-swinton/docs/solutions/best-practices/hooks-vs-skills-separation-plugin-20260211.md` requires a single automatic enforcement point and reserves skills for optional strategy.
- `Clavain/docs/plans/2026-02-19-deep-tldrs-integration-clavain.md` proposed a reusable bounded adapter, confidence fallback, and outcome measurement; this plan implements that missing layer.
- Current Codex, Claude, and Kimi harnesses all expose `UserPromptSubmit`; Codex and Claude accept `hookSpecificOutput.additionalContext`, while Kimi appends successful hook stdout.

---

## Must-Haves

**Truths**

- A Clavain coding task reaches Codex, Kimi, Claude-through-Zaka, or another Zaka adapter only after one gateway decision.
- Eligible tasks receive a bounded packet when tldrs returns a sufficiently grounded candidate.
- Known-small, documentation/configuration-only, already-injected, and non-code tasks receive explicit bypass receipts rather than unnecessary context.
- Missing, failing, or low-confidence tldrs execution leaves the original prompt intact and records an explicit fallback; it is never silent.
- Interactive Claude, Codex, and Kimi sessions installed through Clavain use the same gateway core.
- Receipt files contain hashes and bounded metadata, not the full user prompt.
- Coding correctness remains non-inferior and token results are reported by harness/model/language rather than as one universal claim.

**Artifacts**

- `tldr-swinton/src/tldr_swinton/modules/core/task_context.py` exports packet assessment/building APIs and includes shell/Bats sources while excluding worktrees.
- `tldr-swinton/src/tldr_swinton/cli.py` emits the portable machine packet and receipt schema.
- `tldr-swinton/kimi.plugin.json` matches the current Kimi plugin schema and the released tldr-swinton version.
- `Clavain/scripts/context-gateway.py` implements deterministic eligibility, packet invocation, injection, hook adaptation, doctor checks, and atomic receipt persistence.
- `Clavain/scripts/dispatch.sh` invokes the gateway exactly once after prompt assembly and before backend-specific command construction.
- `Clavain/hooks/context-gateway.sh` provides a stable plugin hook entrypoint.
- Clavain Codex/Kimi installers install and diagnose the managed interactive hook without deleting unrelated user hooks.

**Key Links**

- `dispatch.sh` passes the original public task and project root to `context-gateway.py` before Zaka, Kimi, or Codex command construction.
- `context-gateway.py` consumes `tldrs --machine packet`, validates its schema/hash/confidence, and injects only its bounded `packet` field.
- Claude/Codex `UserPromptSubmit` and Kimi plugin/config hooks call the same `hooks/context-gateway.sh`, which delegates to `context-gateway.py`.
- Installer doctor checks verify the tldrs executable, packet schema, managed hook command, and writable receipt path separately.

## Agent-Native Architecture Checklist

- **Parity:** Direct dispatch and interactive sessions both receive the same gateway decision contract.
- **Granularity:** tldr-swinton only ranks and assesses source; Clavain only decides eligibility/injection/persistence.
- **Composability:** New harnesses map to `generic`, `codex`, `claude`, or `kimi` without changing ranking logic.
- **Emergent capability:** The packet bounds initial context but leaves full reads, edits, and verification available.
- **Dynamic context:** Packets are generated from the current task and workspace at prompt submission, never cached across tasks.
- **Context limits:** Packets retain the validated 750/1500-character source budgets.
- **No silent actions:** Every decision produces a receipt; failures do not masquerade as successful injection.
- **Approval proportionality:** Normal runtime is fail-open with an explicit fallback; CI can require an inject or approved bypass receipt.
- UI/mobile/CRUD concerns are not applicable to this command-line middleware.

---

### Task 1: Harden tldr-swinton source selection

**Files:**

- Modify: `/Users/sma/projects/tldr-swinton/src/tldr_swinton/modules/core/task_context.py`
- Test: `/Users/sma/projects/tldr-swinton/tests/test_task_context.py`

**Step 1: Write failing shell/worktree tests**

Add tests that construct both `scripts/dispatch.sh` and `.worktrees/stale/scripts/dispatch.sh`, then assert:

```python
assert excerpts[0].path == "scripts/dispatch.sh"
assert all(".worktrees" not in excerpt.path for excerpt in excerpts)
```

Add a `.bats` fixture and assert it is discoverable when it is the strongest task owner.

**Step 2: Run tests and confirm RED**

Run:

```bash
uv run pytest tests/test_task_context.py -k 'shell or worktree or bats' -v
```

Expected: failure because `.sh`/`.bats` are not source suffixes and `.worktrees` is not excluded.

**Step 3: Implement the smallest ranking change**

- Add `.sh`, `.bash`, `.bats`, and `.zsh` to `_SOURCE_SUFFIXES`.
- Add `.worktree` and `.worktrees` to `_SKIP_PARTS`.
- Preserve existing ranking and packet budgets.

**Step 4: Verify GREEN**

Run the focused tests, then reproduce the Clavain task:

```bash
tldrs --machine packet \
  "modify scripts/dispatch.sh so Clavain injects a tldrs context packet" \
  --project /Users/sma/projects/Sylveste/os/Clavain \
  --harness-profile codex
```

Expected: `scripts/dispatch.sh` is the top candidate and no `.worktrees` path appears.

<verify>
- run: `uv run pytest tests/test_task_context.py -v`
  expect: exit 0
</verify>

### Task 2: Add packet assessment and receipt schema

**Files:**

- Modify: `/Users/sma/projects/tldr-swinton/src/tldr_swinton/modules/core/task_context.py`
- Modify: `/Users/sma/projects/tldr-swinton/src/tldr_swinton/cli.py`
- Test: `/Users/sma/projects/tldr-swinton/tests/test_task_context.py`

**Depends on:** Task 1

**Step 1: Write failing schema tests**

Define the desired machine result:

```json
{
  "schema_version": 1,
  "decision": "inject",
  "reason": "explicit_path",
  "confidence": 1.0,
  "packet": "# Agent context packet\n...",
  "receipt": {
    "schema_version": 1,
    "decision": "inject",
    "packet_sha256": "64 lowercase hex characters",
    "packet_chars": 123,
    "candidate_paths": ["scripts/dispatch.sh"]
  }
}
```

Tests must cover explicit-path injection, ranked-candidate injection, no-candidate fallback, low-separation fallback, deterministic packet hashes, and the `kimi` harness profile.

**Step 2: Run tests and confirm RED**

Run:

```bash
uv run pytest tests/test_task_context.py -k 'assessment or receipt or kimi' -v
```

Expected: missing assessment/build APIs and schema fields.

**Step 3: Implement assessment/build APIs**

- Add an immutable packet assessment/result type.
- Give explicit-path and test-owner matches high confidence.
- Use ranking separation for otherwise lexical candidates.
- Return fallback for no candidates or an ungrounded/tied selection below the documented threshold.
- Hash the exact rendered packet with SHA-256.
- Keep prompt text out of the receipt.
- Add `kimi` as a 1500-character profile.
- Make human and machine CLI output share the same builder so they cannot drift.

**Step 4: Verify GREEN and backward compatibility**

Run the focused tests and existing packet tests.

<verify>
- run: `uv run pytest tests/test_task_context.py tests/test_machine_flag.py -v`
  expect: exit 0
</verify>

### Task 3: Modernize tldr-swinton Kimi packaging

**Files:**

- Modify: `/Users/sma/projects/tldr-swinton/kimi.plugin.json`
- Test: `/Users/sma/projects/tldr-swinton/tests/test_harness_guidance.py`
- Test: `/Users/sma/projects/tldr-swinton/tests/test_version_consistency.py`

**Depends on:** Task 2

**Step 1: Write failing manifest tests**

Assert that Kimi metadata:

- matches `.claude-plugin/plugin.json` version and description,
- exposes plugin skills and commands with current `./` paths,
- preserves the MCP server,
- uses only supported current Kimi fields.

**Step 2: Run tests and confirm RED**

Expected: the current Kimi manifest is still version `0.7.19` and exposes only MCP.

**Step 3: Update the manifest**

Use current Kimi fields: `skills`, `commands`, `interface`, and `mcpServers`. Do not add automatic packet hooks here; Clavain owns automatic enforcement to avoid duplicate injection.

<verify>
- run: `uv run pytest tests/test_harness_guidance.py tests/test_version_consistency.py -v`
  expect: exit 0
</verify>

### Task 4: Build the Clavain gateway core

**Files:**

- Create: `scripts/context-gateway.py`
- Create: `tests/structural/test_context_gateway.py`

**Depends on:** Task 2

**Step 1: Write failing policy and receipt tests**

Exercise the real command with a stub `tldrs` executable. Cover:

- eligible injection,
- explicit non-code/docs/config/known-small/already-injected bypasses,
- missing executable and malformed/low-confidence packet fallbacks,
- `off`, `auto`, and `required` modes,
- harness-profile mapping,
- prompt preservation,
- atomic receipt creation without raw prompt contents,
- hook output for Claude/Codex and Kimi.

**Step 2: Run tests and confirm RED**

Run:

```bash
uv run --project tests pytest tests/structural/test_context_gateway.py -v
```

Expected: `scripts/context-gateway.py` does not exist.

**Step 3: Implement the stdlib-only gateway**

Provide subcommands:

```text
prepare  # prompt stdin -> enriched prompt stdout; writes one receipt
hook     # hook JSON stdin -> native harness context output
doctor   # executable/schema/write-path self-test
```

The receipt includes timestamp, duration, decision, reason, harness/profile, project, tldrs version, task hash, packet hash/size, confidence, and candidate paths. It excludes full task and packet text.

**Step 4: Verify GREEN**

<verify>
- run: `uv run --project tests pytest tests/structural/test_context_gateway.py -v`
  expect: exit 0
</verify>

### Task 5: Enforce the gateway in Clavain dispatch

**Files:**

- Modify: `scripts/dispatch.sh`
- Create: `tests/shell/dispatch_context_gateway.bats`
- Modify: `tests/shell/dispatch_kimi.bats`
- Modify: `tests/shell/dispatch_zaka.bats`

**Depends on:** Task 4

**Step 1: Write failing dispatch tests**

Use a stub `tldrs` and a temporary receipt directory. Assert:

- Codex, Kimi, and each Zaka adapter receive the same packet exactly once.
- `--context-gateway off|auto|required` and `--context-test-command` parse correctly.
- A fallback leaves the prompt byte-for-byte unchanged.
- A bypass/fallback/injection each create one receipt outside `--dry-run` suppression rules.

**Step 2: Run tests and confirm RED**

Expected: dispatch never invokes the gateway.

**Step 3: Integrate once before backend branching**

Invoke `context-gateway.py prepare` after templates/docs are assembled and before Zaka/backend-specific construction. Map `claude-code` to `claude`, keep `codex` and `kimi`, and use `generic` for unknown future adapters.

<verify>
- run: `bats tests/shell/dispatch_context_gateway.bats tests/shell/dispatch_kimi.bats tests/shell/dispatch_zaka.bats`
  expect: exit 0
</verify>

### Task 6: Wire interactive hooks and installer doctors

**Files:**

- Create: `hooks/context-gateway.sh`
- Modify: `hooks/hooks.json`
- Modify: `scripts/install-codex.sh`
- Modify: `scripts/install-kimi.sh`
- Modify: `tests/structural/test_hooks_json.py`
- Modify: `tests/shell/test_codex_installer.bats`
- Modify: Kimi installer tests selected by `rg --files tests/shell | rg kimi`
- Regenerate: `kimi.plugin.json`

**Depends on:** Tasks 4 and 5

**Step 1: Write failing hook/installer tests**

- Claude plugin manifest includes one `UserPromptSubmit` hook.
- Codex installer merges one managed `UserPromptSubmit` hook and preserves unrelated hooks.
- Kimi plugin generation ports that hook.
- Standalone Kimi config bridge includes the hook only when the plugin route is absent.
- Both doctors report tldrs executable/schema and hook-match state separately.

**Step 2: Run tests and confirm RED**

**Step 3: Implement adapters**

- `hooks/context-gateway.sh` delegates to the Python core and never duplicates eligibility logic.
- Claude/Codex emit `hookSpecificOutput.additionalContext`.
- Kimi emits bounded plain stdout.
- Install/uninstall edits are marker/command-scoped and backup-first.

<verify>
- run: `bats tests/shell/test_codex_installer.bats`
  expect: exit 0
- run: `uv run --project tests pytest tests/structural/test_hooks_json.py tests/structural/test_codex_installers.py -v`
  expect: exit 0
</verify>

### Task 7: Validate outcomes, document, and release

**Files:**

- Create: `docs/research/2026-07-23-clavain-context-gateway-validation.md`
- Modify generated version surfaces only through each repository's supported bump command.

**Depends on:** Tasks 1–6

**Step 1: Run deterministic gates**

- Full tldr-swinton tests.
- Clavain structural and shell suites.
- Shell syntax and JSON validation.
- Kimi manifest generator `--check`.
- Codex/Kimi doctor tests against isolated homes.

**Step 2: Run outcome probes**

- Re-run the live Clavain shell prompt and require `scripts/dispatch.sh` owner recall.
- Compare original versus injected prompt characters/tokens.
- Run at least one existing hidden-grader external task per available harness, counterbalanced where paid calls are used.
- Require coding correctness non-inferiority; report savings by harness/model/language.

**Step 3: Record evidence**

Document versions, source SHAs, task hashes, receipt coverage, owner recall, correctness, uncached tokens, and latency. Do not claim universal savings from a single harness.

**Step 4: Release and push**

- Commit logical units as they pass.
- Pull/rebase and push tldr-swinton before updating Clavain.
- Use each repo's `scripts/bump-version.sh` supported release path.
- Verify both repositories are clean and up to date with origin.
- Close `mk-e6ta` only after release/push verification succeeds.

<verify>
- run: `git status --short --branch`
  expect: contains "up to date"
</verify>

