# Delegation shadow observations (mk-42j9.7.8)

Log-only observations of three main-thread delegation choices. They never
change the choice, never gate a step and never print. Built on the S1 decision
layer ([decide.md](decide.md)); read that first for modes, bands and the kill
switch.

## Call sites

Each instruction makes its choice first, then calls
`scripts/clavain_selector/delegation_shadow.py` with the choice it actually made.

| `--site` | Instruction | Native choice (actual) | Candidates |
|----------|-------------|------------------------|------------|
| `quality-gates` | `commands/quality-gates.md` Phase 2 | always `delegate_flux_drive` (fixed delegation) | `delegate_flux_drive`, `main_thread_review` |
| `codex-delegate` | `skills/codex-delegate/SKILL.md` step 4 | the role used (`$ROLE`) | `scout`, `routine-execution`, `deep-execution`, `validation` |
| `interserve-engine` | `skills/interserve-engine/SKILL.md` Dispatch Routing | the mode chosen (`$MODE`) | `megaprompt`, `parallel_delegation`, `ordered_delegation`, `debate_first` |

`quality-gates` has one real option today, so its observation measures only
whether the shadow would agree with that fixed delegation; its label is not a
dynamic selection. flux triage and document slicing inside flux-drive are out of
scope.

## When it runs

Only when `decision_models.flux_triage.mode` in `config/routing.yaml` is exactly
`shadow`. It ships `off`; so `off`, `enforce`, an unknown mode, a missing entry
and `CLAVAIN_SELECTOR=off` all return before any process, credential, call or
file. `enforce` is never honoured. Egress is always false (no hosted call, no
`sources`), and the shipped `decision_models` registry entry stays disabled with
budget 8. Turn it on for a trial by setting the question's `mode: shadow` with
`backend: heuristic`.

The helper detaches (fire-and-forget), prints nothing and exits 0 whatever
happens. Total work is capped at six seconds; a timeout, crash, missing
`clavain-cli` or unwritable log leaves the flow untouched and writes nothing.
`CLAVAIN_CLI` overrides the binary lookup (default: `bin/clavain-cli` in the
plugin, then `PATH`).

## Records

Records append to `<project>/.clavain/decisions/YYYY-MM-DD.jsonl` through the S1
locked writer (directory 0700, files 0600, no symlinks followed). Each
observation writes two lines. Join them exactly on `decision_id`:

- `schema: clavain-decide-v1` (from `decide`; one per observation)
- `schema: clavain-delegation-shadow-v1` (this helper; one per decide record)

Companion fields: `site`, hashed `question_id`/`candidates`/`native_choice`/
`shadow_choice` (SHA-256 of the identifier), `agreement`, `confidence`, `band`,
`backend`, `reason`, `latency_ms`, `main_thread_tokens`,
`estimated_claude_tokens_saved`, `estimate_method`, `native_actual_outcome`,
`egress_allowed` (always false). No prompt, state, description or question text
is recorded. Companion lines carry no outcome of their own beyond
`native_actual_outcome`; `records.append_outcome` entries keyed by `decision_id`
attach to both lines when joined.

## Estimate method

`estimate_method = main_thread_decision_tokens_if_agree_accept_v1` counts
main thread decision tokens only: the Claude tokens the main thread spent
choosing. Executor tokens, diff, document and prompt tokens are excluded. The caller
passes `SHADOW_DECISION_TOKENS` only when it has a counted or measured estimate;
otherwise the field stays null.

- `estimated_claude_tokens_saved` = `main_thread_tokens` when `agreement` is true
  and `band` is `accept`; 0 when the observation completed but disagreed or was
  below `accept`; null when the estimate is unknown or the observation did not
  complete.
- `agreement` is computed only for a completed observation (`reason:
  shadow_mode`); otherwise null. Fallback reasons (`egress_not_authorized`,
  `timeout`, ...) therefore never count as agreement.
- `native_actual_outcome` is `success`, `warn` or `failure` as the call site
  reports it after the native path finishes, else null.

The heuristic backend always agrees with the native choice at confidence 1, so
heuristic savings measure only the size of the decision, not model quality.

## Reading the logs

```bash
jq -c 'select(.schema=="clavain-delegation-shadow-v1")
  | {site, agreement, band, estimated_claude_tokens_saved, native_actual_outcome}' \
  .clavain/decisions/*.jsonl
jq -s 'map(select(.schema=="clavain-delegation-shadow-v1" and .estimated_claude_tokens_saved!=null))
  | group_by(.site) | map({site: .[0].site, n: length, saved: (map(.estimated_claude_tokens_saved)|add)})' \
  .clavain/decisions/*.jsonl
```

Hash an identifier before comparing: `printf %s delegate_flux_drive | sha256sum`.
The files have no byte cap or retention (see decide.md); watch disk use during a
trial. Disable instantly with `CLAVAIN_SELECTOR=off` or `mode: off`.
