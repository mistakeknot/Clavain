# GPT-6 Astra rollout

State as of 2026-09-03: **opt-in only; promotion blocked on account access**.

## Activation evidence

- Invoked standalone Codex upgraded from 0.146.0 to 0.153.2; Astra-capable profiles require at least 0.153.1.
- `$CODEX_HOME/astra.config.toml` is selected with `codex --profile astra`. It sets `gpt-6-astra`, `xhigh`, Standard processing (`service_tier = "default"` in Codex vocabulary), and experimental context management.
- The base Codex profile remains GPT-5.6 Sol.
- The model catalog exposes Astra metadata, but the live ChatGPT-authenticated read-only canary returns HTTP 400: Astra is not supported for this account. This is an explicit account-access fallback condition, not a promotion signal.

## Rollout state

Role routing is opt-in through `dispatch.sh --role`; existing tier consumers and direct Chat Completions clients are unchanged. This is the shadow stage: role resolutions and fallbacks can be inspected without switching default traffic.

Promotion order:

1. opt-in Astra profile;
2. interactive `main-integrator`;
3. `deep-execution`;
4. selected downstream consumers.

Do not advance while the canary reports missing account access. After access succeeds, run a narrow canary for 20 completed tasks or 14 days. Observe main-integrator context per turn against 100K and report absolute main-integrator cost per completed task; neither token share nor cost share is a promotion gate.

Required gates:

- no loss of accepted high-severity findings;
- plan-to-execution success at least 0.909;
- producer and validator never resolve to the same model on consequential work;
- policy blocks never retry or change backend/model;
- routing decisions and verdicts are durable and queryable.

## Existing executor-routing corpus

Phase one from `Sylveste-d3m` is complete and was not repeated. The configured corpus path, `~/.clavain/executor-routing-shadow.jsonl`, has no accumulated rows on this host at this checkpoint. Therefore neither `interserve-fast` nor `interserve-deep` has parity evidence, and neither class was added to `executor_routing.classes`. They continue through the safe `codex` default until real rows and blinded defensibility judgments exist.

## Rollback

Restore the role mapping to its declared GPT-5.6 Sol fallback. Keep the isolated Astra profile and collected decision/evaluation evidence for diagnosis. Rollback never changes release authority or silently switches direct API clients.
