# Model routing

`config/routing.yaml` is the routing policy. It has these top-level sections:
`executor_routing`, `subagents`, `reasoning`, `dispatch`, `complexity`,
`calibration`, `delegation`, `local_models` and `decision_models` (**9** sections).

The reasoning section names the frontier models (`gpt-6.2-astra`,
`claude-opus-5-5`, `claude-fable-5-2`), five frontier reasons for elevating a task, and a
**2**-strike rule: two demonstrated capability failures request escalation.
