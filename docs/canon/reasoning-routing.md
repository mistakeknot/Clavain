# Reasoning routing

Clavain owns model assignments and the executable policy in `config/routing.yaml`.
Sylveste owns the principle; Intercore enforces declared judgments; adapters carry
the packaged contract to each host. A standalone Clavain checkout contains this
canon, policy, instructions, adapters, and dispatch scripts. Intercore (`ic`),
Python 3, jq, and the selected model CLI are runtime dependencies.

## Classify and resolve

The accountable agent supplies reasons and a rationale. Intercore does not infer
task importance from keywords or domain names. Record any of:

| Reason | Typical evidence |
|---|---|
| `unresolved-success-criteria` | A new game loop needs play evidence; product strategy needs user evidence |
| `foundational-invariants` | Agent authority boundaries or graph identity/consistency semantics change |
| `broad-consequences` | A shared protocol or strategic decision affects many consumers |
| `difficult-verification` | An ML experiment, emergent behavior, or production canary decides correctness |
| `capability-failure` | Execution or review demonstrates that the current model cannot solve the problem |

Substantial new capabilities in games, agent systems, AI/ML, graph databases,
and product strategy require frontier planning. A label alone does not elevate a
routine change with settled constraints. Use one frontier author ordinarily.
Foundational or especially consequential plans require the other frontier model
for plan review. Existing stricter review and publication gates remain binding.

```json
{
  "reasons": ["foundational-invariants", "difficult-verification"],
  "rationale": "Changes admission semantics and requires replay experiments",
  "domain": "agent systems",
  "investigation_active": true
}
```

```bash
ic --json route dispatch --policy=/selected/Clavain/config/routing.yaml \
  --role=planning --context-file=/tmp/decision.json
ic --json route dispatch --policy=/selected/Clavain/config/routing.yaml \
  --role=plan-review --producer-identity=gpt-6-astra --context-file=/tmp/decision.json
CLAVAIN_DECISION_CONTEXT=/tmp/decision.json \
  bash /selected/Clavain/scripts/dispatch.sh --role planning --prompt-file /tmp/brief.md
```

The result contains the policy source and SHA256, classification reasons,
selected profile with backend/model/effort, review requirement, exclusions and
eligible fallbacks. Aliases and dated/provider-decorated identities cannot evade
reviewer separation. `available_models` may supply observed account access;
omission means unprobed, an empty array means none. Backend invocation establishes
actual availability. Required frontier work cannot silently fall back to Sol.

Resolution order: explicit `--policy`, `CLAVAIN_ROUTING_POLICY`, `CLAVAIN_ROOT`,
the selected Claude plugin root, the managed Clavain skill link, then legacy
checkout discovery. Invalid explicit selections fail closed. The dispatch wrapper
selects its own packaged policy unless explicitly overridden. Never select the
newest cache directory by accident. `--policy-profile` selects a declared role
overlay; the `ci-campaign-pilot` overlay requires `scope: mk-ag2s`. Its Opus
coordinator / Sonnet execution / Sol review mix is confined to that campaign.
Default complex planning, review, and execution retain Astra and Fable.

## Handoff and escalation

Keep frontier involvement while investigation or experiments change the plan.
Execution can hand off once `handoff` supplies nonempty `decisions`, `constraints`,
`verification`, and `escalation`, and `investigation_active` is false. Verification
must retain playtests, experiments, user evidence, or production canaries where
applicable; structural tests alone do not satisfy empirical acceptance.

`ic dispatch spawn --role=...` accepts the same policy/context/profile/producer
flags. Governed dispatch requires the packaged wrapper, records the contract
before execution, and preserves it in scheduled jobs and retry receipts. Legacy
model-only APIs remain available and are not classified as governed dispatch.

`ic dispatch retry --escalate --policy=... --failure-mode=...` counts capability,
verdict, and criteria failures as strikes. Two strikes request the policy's
escalation role; `premise-failure` requests it immediately. Authentication,
rate limits, permission, infrastructure, timeout, generic error, and unknown
failures remain operational and consume no capability strikes. The caller must
classify the failure; an exit code alone cannot establish capability failure.
Retries retain backend and effort in the decision receipt. Review escalation
requires a newly resolved independent review contract. Policy drift requires
reclassification. Retry commands create records, not running processes.

## Host delivery and evidence

`config/agent-instructions.md` is shared; `config/host-adapters.json` and the
small Codex adapter supply host details. The historical managed marker is retained
so upgrades replace the existing block once. Narrow sync follows instruction
symlinks, preserves unrelated bytes and modes, refuses malformed markers and
concurrent edits, and exposes package/contract/policy drift:

```bash
python3 scripts/sync-agent-instructions.py --source /selected/Clavain \
  --host codex --file /selected/profile/AGENTS.md --dry-run
python3 scripts/sync-agent-instructions.py --source /selected/Clavain \
  --host codex --file /selected/profile/AGENTS.md
python3 scripts/sync-agent-instructions.py --source /selected/Clavain \
  --host codex --file /selected/profile/AGENTS.md --check
```

Use the declared native surface: Claude `CLAUDE.md` plus session-start, Codex and
Kimi `AGENTS.md`, Gemini `GEMINI.md`, OpenCode `AGENTS.md`, Cursor an always-applied
`.mdc` rule, VS Code `.github/copilot-instructions.md` or a user
`prompts/*.instructions.md` file with `applyTo: "**"`. Select each profile's file
explicitly. Dotfiles consume the rendered block, never own a fork of the policy.
For Cursor, retain the native `alwaysApply: true` frontmatter outside the block.
The check reports potential unmanaged model overrides without copying local text.

For instruction files shared between machines through dotfiles, add
`--portable-policy` to sync and check. This keeps machine paths out of shared
content and selects `CLAVAIN_ROUTING_POLICY` when set, otherwise the installation
linked by `~/.agents/skills/clavain`. Each machine must have that managed link and
an Intercore version that resolves symlinks before parent-directory traversal.
Missing selections fail closed. The receipt identifies this selection mode;
rerender after installation changes to refresh the recorded policy hash. Keep
the default explicit selection for standalone installations without a managed link.

Hermes: use the selected Hermes virtualenv's Python (with PyYAML) to run:

```bash
python scripts/sync-hermes-adapter.py --source /selected/Clavain \
  --home /selected/hermes-profile --dry-run
python scripts/sync-hermes-adapter.py --source /selected/Clavain \
  --home /selected/hermes-profile
python scripts/sync-hermes-adapter.py --source /selected/Clavain \
  --home /selected/hermes-profile --check
```

This links `adapters/hermes` into that profile and enables only `clavain` using
the native plugin allowlist. It preserves config bytes outside the plugin section,
unrelated plugin settings, symlinks and file modes. Unsupported YAML structures
and unmanaged adapter targets fail explicitly. It runs no migrations or model
calls. The native plugin
uses `pre_llm_call`, `pre_tool_call`, `on_session_start`, and `subagent_stop`;
`clavain_dispatch` carries role/context/producer to the shared wrapper. Native
`delegate_task` is blocked to prevent silent inheritance. Session and child
observation remain in Hermes telemetry. No profile personalities or credentials
are rewritten. The installed Hermes hook API was inspected; hook registration
alone does not prove behavioral enforcement. Older hosts that ignore blocking
directives are unsupported. See the [Hermes plugin hook contract](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks).

Governed dispatch supplies the shared contract and resolved decision to the child
after context compaction. It verifies the policy hash again before execution and
rejects drift. This is needed for Claude review seats, which intentionally exclude
user settings: that also excludes the global instruction file, as described in
the [Claude Code settings-source contract](https://code.claude.com/docs/en/agent-sdk/claude-code-features).
Resolving a role does not itself establish kernel spawn or budget admission.

Instruction sync reports `instructional`, wrapper calls produce
`dispatch-enforced` receipts, and only a fresh-session probe can establish
behavioral verification. Changing settings does not switch a running parent
model. Report missing tools, unsupported native routing, and absent frontier
access explicitly. Do not claim all hosts verified from a renderer test.

## Calibration and rollout

Use existing `routing_decisions.policy_hash` and `context_json` for decisions,
exclusions, profile, failure class and per-attempt results. The dispatch audit
and existing Interstat/Interspect outcome pipeline retain actual execution,
accepted outcomes, defects, retries and attributable usage. QA must record the
validator model from its receipt, never a hard-coded constant. Unknown usage or
unrun empirical acceptance stays unknown. Calibration may change eligible choices
but cannot relax frontier requirements, reviewer independence, quality floors,
or authority gates.

Run routing, retry, adapter synchronization and host integration tests; retain
fresh-session model/effort receipts. Compare identical contexts from nested repos,
outside Git roots, standalone installs and alternate profiles. Upgrade only the
selected instruction block or adapter. Roll back by selecting the previous
version's policy and rerendering its block; preserve receipts and local content.
Build/release/deployment automation remains independently scheduled on zklw.
