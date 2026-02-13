# Flux Drive Review Summary — Clodex Overhaul Plan

**Reviewed**: 2026-02-12 | **Agents**: 4 launched, 4 completed | **Verdict**: risky

## Agent Results

| Agent | Verdict | P0 | P1 | IMP |
|-------|---------|----|----|-----|
| fd-architecture | risky | 2 | 3 | 3 |
| fd-prompt-engineering | needs-changes | 2 | 3 | 4 |
| fd-performance | safe | 0 | 1 | 3 |
| fd-quality | needs-changes | 2 | 4 | 3 |

## Deduplicated P0 Findings

1. **"Source code" undefined** — injection uses vague "etc." instead of explicit extension allowlist (fd-prompt-engineering, fd-quality)
2. **Bash tool bypass unguarded** — Edit/Write forbidden but Bash redirects/sed can still write source files (fd-prompt-engineering)
3. **No behavioral verification** — all verification is structural (syntax, JSON, pytest); none tests contract adherence (fd-architecture, fd-prompt-engineering, fd-quality)
4. **Context window dilution** — session-start injection fades after 50+ tool calls; no reinforcement mechanism (fd-architecture)
5. **No shebang specified** — new script missing `#!/usr/bin/env bash` + `set -euo pipefail` (fd-quality)

## Deduplicated P1 Findings

1. **"Blocked" wording is a lie after hook removal** — toggle output and injection use enforcement language that won't be true (fd-quality, fd-prompt-engineering)
2. **15+ stale doc references** — AGENTS.md, README.md, skills reference PreToolUse hook (fd-architecture, fd-quality)
3. **Hook count 5→4 not propagated** — CLAUDE.md, README.md headline counts (fd-architecture)
4. **Missing test updates** — need regression guard asserting no PreToolUse in hooks.json (fd-architecture)
5. **No replacement text for behavioral-contract.md** — Step 6 says what to remove but not what to write (fd-prompt-engineering, fd-quality)
6. **Thin wrapper pattern not demonstrated** — Step 2 missing command body example (fd-quality)
7. **Missing error handling in script** — no $PROJECT_DIR validation (fd-quality)
8. **Destructive Bash commands unrestricted** — rm/mv source files not addressed (fd-prompt-engineering)

## Key Improvements

1. Compress injection to 4 lines (~70 tokens) — 40% reduction (fd-performance)
2. Script location: hooks/ not scripts/ for convention consistency (fd-architecture)
3. Explain WHY in injection — token budget motivation increases compliance (fd-prompt-engineering)
4. Codex-unavailable fallback — what to do when CLI isn't installed (fd-prompt-engineering)
5. Script UX: show state on error, colored output, timestamp (fd-quality)

## Recommended Path

Address all P0s by:
1. Define "source code" explicitly (full extension allowlist in injection)
2. Add Bash write restriction to behavioral contract
3. Add behavioral smoke test to verification section
4. Add context reinforcement strategy (remind in /clodex skill, or periodic re-injection)
5. Specify shebang and error handling in script spec

Address P1s by:
1. Update all stale references (grep sweep)
2. Fix wording to "behavioral, not enforced"
3. Update hook counts in CLAUDE.md, README.md
4. Add structural test for no-PreToolUse regression guard
5. Provide target state for behavioral-contract.md
6. Show command body template for thin wrapper
