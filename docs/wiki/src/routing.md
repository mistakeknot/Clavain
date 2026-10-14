# Model routing

`config/routing.yaml` is the routing policy. It has these top-level sections:
`executor_routing`, `subagents`, `reasoning`, `dispatch`, `complexity`,
`calibration`, `delegation` and `local_models` (**8** sections).

The reasoning section names the frontier models (`gpt-6-astra`,
`claude-opus-5-5`), five frontier reasons for elevating a task, and a
**2**-strike rule: two demonstrated capability failures request escalation.
