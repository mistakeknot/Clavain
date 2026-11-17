# Decision observations (S1)

`clavain-cli decide` reads one JSON object from stdin and prints one JSON
answer. Set `CLAVAIN_DIR` to the plugin installation, or pass `--plugin-root`.
`--config` selects routing.yaml; `--project-root` selects the project whose
egress policy and local shadow log apply (default: current directory).

```json
{
  "question": {
    "id": "route",
    "text": "Choose a route for this task",
    "candidates": [
      {"id": "plan", "description": "Plan the work"},
      {"id": "build", "description": "Implement the work"}
    ]
  },
  "state": {"kind": "documentation", "size": "small"},
  "native_choice": "build",
  "egress_allowed": false,
  "sources": []
}
```

The caller supplies today's answer as `native_choice`, which must name a
candidate. State must be a JSON object. Candidate limits, identifiers and
descriptions follow the existing selector contract. `sources` lists files
from which state was derived: declare all such sources so the egress guard
can refuse protected files. `egress_allowed` defaults to false; callers must
leave it false for state that cannot leave the machine. Setting it true does
not bypass `egress.admit()`, including ownership, secret and source checks.

Configure each question ID under `decision_models`:

```yaml
decision_models:
  route: {backend: heuristic, mode: off}
```

Modes default to `off`. `CLAVAIN_SELECTOR=off` (case-insensitive, trimmed)
disables the layer before egress, credentials, calls or logging.
`shadow` observes a choice; `enforce` returns
`enforce_disabled` without making a provider call. Unsupported modes remain
off. Backends are `heuristic` (a deterministic baseline agreeing with today's
answer) and `jev` (the existing credential loader, admitted client, shared
breaker and a stable per-project UTC-day budget). The registry's
`decision_models.daily_budget` caps calls, with a conservative maximum of
eight; changing caller session IDs does not reset it. Its registry entry ships
with `enabled: false`; hosted shadow observations also require explicitly
enabling that entry, in addition to the per-question shadow mode and egress
permission. Existing integration defaults are unchanged. Clef, Clairic and other backends
return `unsupported_backend`; S1 implements no free-tier backend.

The output includes `choice`, `shadow_choice`, `probs`, `confidence`, `backend`, `band`,
`reason`, `latency_ms` and the existing attempt accounting when observed.
Bands are `accept` at confidence >=0.8, `review` at >=0.6 and <0.8, and
`escalate` below 0.6. Abstention, timeout and provider failure return a fallback
reason. **Every S1 answer has `fallback: true`, including confident shadow
answers.** `choice` always holds `native_choice`. `shadow_choice` holds the
observation, including an abstaining `escalate` answer; `probs` and
`confidence` describe that observation. Callers always continue today's behavior. A backend observation
never authorizes an action or skipping a review. There are no sprint hooks
in this slice.

Jev defaults to a 1500 ms deadline, configurable per question with
`deadline_ms` (clamped by the existing client to 1–5000 ms). The Go wrapper
bounds the whole helper execution to six seconds and returns native fallback
if Python, configuration or the helper is unavailable. Invalid input also
returns a fallback; callers retain responsibility for their existing path.

Shadow observations append through the existing locked record writer into
`.clavain/decisions/YYYY-MM-DD.jsonl`, with private file permissions. The
record contains a decision UUID, the question and candidate IDs and both
answers encoded as SHA256 identifiers, the distribution, confidence, backend,
latency and physical-attempt token accounting. Hash identifiers before
comparing caller data with a record. State, descriptions, prompt text and
credentials are not recorded. Monetary `cost` is null: the typed Jev client
exposes tokens, not a monetary price. Unknown attempt usage stays unknown.
The writer pins directory descriptors and refuses symlinked directories or
day files below the project; it never follows those links to chmod targets.

Before starting the trial, install a release whose `clavain-cli` supports
`decide`. Verify the installed CLI with
`echo '{}' | clavain-cli decide --config /dev/null` (the command reads its
request from stdin): it must return `reason: off`. The one-week shadow trial starts only after
that prerequisite passes. Zero rows before then means the observer is not
wired, not that no events occurred.

Trial log design choice: project decision JSONL files have an 8 MiB total
byte cap across all days. The locked size check includes the pending line;
when full, observations return `record_unwritable` without appending. Native
fallback continues unchanged. There is no automatic deletion or rotation.

`observed_outcome` initially is null. Fill it logically by appending an
outcome with the existing `records.append_outcome(decision_id, result,
record_dir=project_root / '.clavain/decisions')`; `records.read_records` joins
these later outcomes without modifying old lines. The existing `ic route
record` subcommand only accepts routing-specific fields, so S1 uses JSONL
to preserve the complete decision contract.

Main-thread delegation call sites record companion observations; see
[delegation-shadow.md](delegation-shadow.md).
