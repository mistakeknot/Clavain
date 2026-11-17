# Hosted shadow observer privacy contract

Route and review-exit observers can use Jev only in shadow mode with an
explicit `privacy_contract: shadow-observer-v1` in their selected policy entry.
This is a design choice for a narrow, reviewable egress boundary. Shipped policy
entries remain off and the `decision_models` registry entry remains disabled.
Learned-router observations remain local: dynamic seat descriptions are outside
this contract.

After review, an operator can replace the applicable policy entry with one line:

```yaml
route: {mode: shadow, backend: jev, privacy_contract: shadow-observer-v1}
```

The equivalent line for `review_exit` enables that observer. The independent
registry gate must also be enabled locally, never by this change. From the
selected plugin root this one-line switch updates only that gate:

```bash
python3 -c 'import json,pathlib; p=pathlib.Path("config/selector-integrations.json"); x=json.loads(p.read_text()); x["integrations"]["decision_models"]["enabled"]=True; p.write_text(json.dumps(x,indent=2)+"\n")'
```

Setting that value back to false disables hosted decisions. `CLAVAIN_SELECTOR=off`
always wins, before any observer configuration read, record or network call.
Changing a heuristic packet's backend after preflight cannot authorize egress.

## Exactly what leaves the machine

The Jev JSON body contains the pinned model `jev-1.13.0`, the fixed
`clavain-selection-v1` schema, point `library`, a frozen task string, the state
below as JSON in `context`, and frozen candidate IDs/descriptions. The fixed
choice-question battery adds `escalate` with its standard return-control criterion.
Fit questions are disabled. No native answer is included in the body.

| Question | Frozen task and candidates | Allowed state |
| --- | --- | --- |
| `route` | Task `Observe native classification`; descriptions equal IDs. `route-4b`: `sprint`, `work`; `route-staleness` and `route-sweep`: `implemented`, `not_implemented`; `sprint-lane-intent`: `contradicts`, `aligned`. | `site_id` from those four names; `subject_sha256`, exactly 64 lowercase hex characters; `input_bytes`, `output_bytes`, integers 0–1,000,000,000; `batch_size`, integer 1–1000. |
| `review_exit` | Task `Could this review round have exited early?`; candidates `exit` / `Exit the review loop`, `continue` / `Continue reviewing`. | `findings`, null or integer 0–1,000,000,000; `loop_hash`, exactly 64 lowercase hex characters. |

Unknown keys, candidate payloads, changed descriptions/tasks, malformed types,
booleans masquerading as counts, unknown contract versions and nonempty sources
are rejected before admission or credential access. The outer packet permits
only the contract marker, question, state, native choice, explicit true egress
authorization and empty sources, plus the existing validated route accounting
metadata. That metadata and the native answer stay local. A selected policy with a contract marker also requires a marked packet;
omitting the request marker cannot restore the generic API. Unmarked generic
`decide` policies retain their separate explicit egress authorization contract.

Both existing `egress.admit()` passes remain: the second scans against the loaded
key too. Ownership, source, credential-pattern and size guards remain intact.
Credentials are loaded using the existing private-file loader, and hosted
observers reject a credential path resolving outside `~/.config/jev/`.
The API key is sent only as the provider authentication header, never as decision
content or a log field. Normal HTTPS transport also exposes connection metadata
to the provider. Raw prompts, classifier responses, file contents, source paths,
usernames and credential values never enter observer decision content.

Before transmission, both `subject_sha256` and `loop_hash` are replaced with
HMAC-SHA256 pseudonyms using a fresh random 32-byte key per call and a field-name
domain prefix. The key is discarded, never persisted or transmitted. The wire
values cannot be linked across calls or dictionary-matched to guessed IDs or
paths. Original hashes remain only in local records for joins; those local
hashes can still be dictionary-matched.
Counts disclose size and findings information. The validator constrains values,
not their provenance; callers must follow the observer interface. No new source
reads or raw-text telemetry are authorized by enabling this switch.

## Measurement and native authority

Every returned decision retains `choice=native_choice` and `fallback=true`.
Confidence and bands are recorded; below the existing 0.8 confidence floor the
reason is `low_confidence`. `shadow_choice` retains the provider's raw proposal
for analysis, including low-confidence proposals and escalation. It never
controls an action. Filter agreement analysis to `reason=shadow_mode` to exclude
abstentions and operational fallbacks that otherwise repeat the native answer.
Heuristic agreement is tautological; hosted disagreement is possible, but route
counts/hashes contain no semantic evidence for choosing a route. Agreement on
this projection cannot establish semantic correctness or justify reduced review.

The shared budget caps logical decisions at eight per Git common directory
per UTC day across route and review-exit (and other hosted observer decisions), even if a
session changes. Lower configured limits still apply. The existing breaker and
deadline remain. Budget slots are consumed before breaker and credential checks,
so refusals can spend a slot without making a network call. A logical call can contain the client's existing bounded retry;
physical attempts are accounted separately. Over-budget, open-breaker, denied
egress and missing credentials all retain native behavior.

Each local `clavain-decide-v1` record includes `privacy_contract`, confidence,
reason, hashed choices and `attempt_records`. The physical-attempt collector
records provider-reported `input_tokens` and `output_tokens`, HTTP status,
timing, hashed request/response/request IDs and usage basis, without content.
`jev_usage_accounting.known_total` sums reported tokens across retries;
`unknown_attempts` and `complete` distinguish missing usage from zero. USD `cost`
stays null because no verified price schedule is configured: token counts are
measured, monetary cost is unknown. Do not infer zero spend from null, an
abandoned request or a non-200 response. Route byte-derived savings remain a
counterfactual proxy; observed savings stay zero because every native call runs.
Review-exit observations join to this accounting through `decision_id`.
Interpret their agreement/exit fields only after joining to a decision with
`reason=shadow_mode`; operational fallbacks are not independent predictions.
