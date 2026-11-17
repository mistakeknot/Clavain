# Learned router shadow observations

The dispatch EXIT handler observes each completed, receipt-armed governed
attempt, including native capacity fallbacks. Rejected preflights and legacy
tier dispatches are outside this track. Routing and dispatch still choose and
run the seat before the observer starts; observer output never returns to them.
The detached worker closes inherited output descriptors. A missing binary,
bad configuration, timeout or unwritable log silently loses an observation.
Descriptors above 2 are enumerated through procfs or `/dev/fd` and closed
before the pipeline starts. The companion append waits at most one second,
within the remaining six-second observer budget, including lock acquisition.

`decision_models.learned_router` stays `mode: off`. To collect local trial
evidence use a task-local policy copy with `mode: shadow, backend: heuristic`.
The observer refuses every other mode or backend and honors
`CLAVAIN_SELECTOR=off`. Hosted calls, registry settings and budgets are unchanged.

The worker calls `clavain-cli decide` with the resolved primary/fallback seats,
the actual executed profile as `native_choice`, and hashed role/policy state.
Egress is false; no task text is supplied. The CLI invocation has a six-second
timeout. Routes with more than sixteen candidates are omitted.

Read `.clavain/decisions/YYYY-MM-DD.jsonl` in the task working directory.
S1 records retain confidence and hashed answers. Companion records with
`schema: clavain-learned-router-v1` link through `s1_decision_id`, and contain:

- `native_choice`, `shadow_choice`, `question_id`, `role_id`: SHA256 identifiers.
- `agreement`: equality of the shadow seat and executed seat; null if absent
  or if S1 returned a non-observation fallback reason.
- `confidence`, `exit_code`, `mode: shadow`, `applied: native`.
- `estimated_input_tokens`: ceil(final assembled prompt character count / 4).
- `estimated_claude_tokens_saved`: those input tokens only when confidence is
  at least 0.6 and a Claude seat would move to a lower ordinal cost seat;
  otherwise zero, or null when a different seat's cost is unknown.
- `token_estimate_method`: `ceil_prompt_characters_div_4_input_only_seat_rank_v1`.

Design choice: the cost proxy ranks Codex 0, Haiku 1, Sonnet 2, Opus 3. It
models displaced Claude-seat tokens, not monetary prices or quality. It excludes
cache, tool traffic, output and retries. These estimates are counterfactual,
not measured savings. The heuristic always agrees and therefore yields zero;
it provides plumbing evidence, not evidence of learned routing quality.

For trial analysis, filter companion rows, average non-null `agreement`, sum
non-null `estimated_claude_tokens_saved`, and report missing counts. Group by
hashed role and exit code; a nonzero exit records an attempted seat, not a
successful task outcome. No live week-long trial is enabled by this change.
