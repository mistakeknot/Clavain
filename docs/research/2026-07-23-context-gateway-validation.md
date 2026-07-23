---
title: "Clavain tldrs Context Gateway Validation"
date: 2026-07-23
status: validated
bead: mk-e6ta
---

# Clavain tldrs Context Gateway Validation

## Decision

Clavain now owns one context gateway policy across direct dispatch and
interactive Claude Code, Codex, and Kimi Code sessions. Eligible coding tasks
receive a validated tldrs packet before model invocation. Non-code, docs/config,
already-injected, and known-small target tasks bypass it. Failures preserve the
original prompt and write a fallback receipt; direct dispatch can opt into
`required` mode.

This follows the current native hook surfaces:

- [Codex `UserPromptSubmit`](https://developers.openai.com/codex/hooks) accepts
  model-visible `additionalContext`.
- [Claude Code hooks](https://code.claude.com/docs/en/hooks) use the same
  `hookSpecificOutput.additionalContext` shape.
- [Kimi Code hooks](https://moonshotai.github.io/kimi-code/en/customization/hooks)
  append successful hook stdout, while
  [Kimi plugins](https://moonshotai.github.io/kimi-code/en/customization/plugins.html)
  package hooks, skills, commands, and MCP servers.

## Live Clavain-shaped experiment

The experiment used the tldr-swinton source checkout after explicit-owner
budget reservation and the Clavain source checkout after gateway integration.
It ran `scripts/context-gateway.py prepare --mode required` and inspected the
persisted receipts.

| Public task shape | Decision | Named-owner recall | Full named source | Packet | Source-to-packet reduction |
|---|---|---:|---:|---:|---:|
| `scripts/dispatch.sh` | inject | 1/1 | 52,918 chars | 2,003 chars | 96.2% |
| both harness installers | inject | 2/2 | 74,640 chars | 2,066 chars | 97.2% |
| small hook plus Bats test | bypass | 2/2 exact targets | 2,654 chars | 0 chars | 100% initial injection avoided |

The two injected cases retained 3/3 explicitly named large owners and reduced
127,558 source characters to 4,069 packet characters, a 96.8% representation
reduction. Gateway time was 935–939 ms. The small two-file task made its
decision without invoking tldrs and took less than one measured millisecond.

The small-target result is intentionally reported as *initial injection*
savings, not end-to-end agent savings: the agent may still read both complete
files. Bypassing is preferable because injecting a 2,156-character packet and
then reading 2,654 characters of exact source would increase total context.

## Coding-performance evidence

The packet renderer and the promoted single-owner Codex profile are unchanged
from tldr-swinton's pinned external Context Gateway confirmation:

- 16/16 hidden-grader cells passed for baseline and injected Codex/Python.
- Median paired uncached-token savings were 41.8%; aggregate savings were
  38.7%.
- The balanced Codex/Claude Python/Go matrix passed 32/32 cells and saved 14.0%
  of uncached tokens in aggregate.

The new ranker behavior only reserves a shared budget across multiple paths
that the public task explicitly names. A regression fixture reproduces the
Clavain hook-plus-test miss found during this experiment and proves that named
owners precede lexical distractors. The small-target-set policy sends complete
source discovery back to the agent rather than supplying a lossy summary, so
it does not create a new correctness shortcut.

No new paid model matrix was run for the multi-owner policy. End-to-end token
claims for that policy therefore remain provisional until it accumulates
paired agent traces.

## Enforcement map

| Surface | Enforcement point | Harness profile | Failure policy |
|---|---|---|---|
| `dispatch.sh` to Codex | before command construction | `codex` | auto fallback or required failure |
| `dispatch.sh` to Kimi | before command construction | `kimi` | auto fallback or required failure |
| `dispatch.sh --via zaka` | before spawn/steer | adapter-specific; default `claude` | auto fallback or required failure |
| Claude Code plugin | `UserPromptSubmit` | `claude` | fail open |
| Codex user install | merged `~/.codex/hooks.json` `UserPromptSubmit` | `codex` | fail open |
| Kimi plugin | generated `kimi.plugin.json` `UserPromptSubmit` | auto-detected `kimi` | fail open |
| Kimi config fallback | managed `config.toml` hook block | explicit `kimi` | fail open |

The Codex installer merges the managed group and preserves unrelated events
and commands. The Kimi installer installs either the plugin-owned hook or the
managed config block, never both. Installer doctors separately report hook
presence, tldrs resolution, packet-schema compatibility, and receipt-path
writability.

## Receipt contract

Each decision writes an atomic schema-v1 receipt containing:

- inject, bypass, or fallback plus reason and confidence;
- harness profile, mode, project, duration, and tldrs version;
- task and packet SHA-256 values, packet length, and candidate paths.

Receipts exclude both the raw user prompt and packet content. They default to
`~/.clavain/context-gateway`; restricted runtimes fall back to the operating
system temporary directory unless an explicit receipt directory was requested.

## Next measurement

Use the receipts to stratify real agent traces by harness, model, language,
decision reason, and target-size band. Promote a new multi-owner packet budget
only after paired hidden-grader runs show non-inferior correctness and a
positive token-savings interval. Until then, keep the confirmed Codex
single-owner profile and the conservative 1,500-character Claude/Kimi/generic
profile.
