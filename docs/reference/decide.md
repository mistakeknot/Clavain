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
  route: {backend: heuristic, mode: shadow}
```

Missing modes default to `off`. The shipped configuration enables `shadow` with
`backend: heuristic` for `flux_triage`, `route`, `review_exit` and
`learned_router`. `flux_triage` controls the live S3 delegation observer;
interflux triage itself has no live observer yet. `CLAVAIN_SELECTOR=off` (case-insensitive, trimmed)
disables the layer before egress, credentials, calls or logging.
`shadow` observes a choice; `enforce` returns
`enforce_disabled` without making a provider call. Unsupported modes remain
off. Backends are `heuristic` (a deterministic baseline agreeing with today's
answer) and `jev` (the existing credential loader, admitted client, shared
breaker and a stable per-project UTC-day budget). The registry's
`decision_models.daily_budget` caps calls, with a conservative maximum of
eight calls per project per UTC day; changing caller session IDs does not reset
it. Over-budget calls fall back to the native choice. This is the design choice
for any future hosted trial; the current heuristic-only trial makes no Jev calls. Its registry entry ships
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

S1 design choice: daily JSONL files have no byte cap or automated retention
during the one-week shadow trial. The hosted-call budget bounds Jev traffic,
but repeated heuristic observations can still grow the log. Monitor local disk
usage during the trial; retention is a prerequisite for sustained rollout.

`observed_outcome` initially is null. Fill it logically by appending an
outcome with the existing `records.append_outcome(decision_id, result,
record_dir=project_root / '.clavain/decisions')`; `records.read_records` joins
these later outcomes without modifying old lines. The existing `ic route
record` subcommand only accepts routing-specific fields, so S1 uses JSONL
to preserve the complete decision contract.

Main-thread delegation call sites record companion observations; see
[delegation-shadow.md](delegation-shadow.md).

## Reading the trial week

Read `<project>/.clavain/decisions/YYYY-MM-DD.jsonl` in each observed project.
Select the seven daily files for the trial week; all globs below cover the
files present. Heuristic agreement is tautological (confidence 1, band accept),
so this week measures observation counts, confidence bands and token estimates,
not real model agreement or realized savings. Jev remains disabled. Native
choices always run, and `CLAVAIN_SELECTOR=off` disables observations entirely.

The common S1 rows identify tracks by SHA256 of the question ID. Count only
completed observations (`reason: shadow_mode`) as agreement; fallback rows
remain separate. This local script reports per-track counts and bands:

```bash
python3 - /absolute/project/root <<'PYTHON'
import collections, hashlib, json, pathlib, sys
tracks = {hashlib.sha256(k.encode()).hexdigest(): k for k in
          ('flux_triage', 'route', 'review_exit', 'learned_router')}
rows = [json.loads(line) for p in sorted(
    (pathlib.Path(sys.argv[1]) / '.clavain/decisions').glob('*.jsonl'))
    for line in p.read_text().splitlines()]
for hashed, track in tracks.items():
    selected = [r for r in rows if r.get('schema') == 'clavain-decide-v1'
                and r.get('question_id') == hashed]
    completed = [r for r in selected if r.get('reason') == 'shadow_mode']
    print(track, dict(count=len(selected), completed=len(completed),
          agreeing=sum(r['native_choice'] == r['decide_answer']['choice']
                       for r in completed),
          bands=dict(collections.Counter(r.get('band') for r in completed))))
PYTHON
```

Read token estimates according to their schema; do not add companion rows to
S1 counts or combine unlike estimates as measured savings:

| Track | Estimate fields and interpretation |
|-------|------------------------------------|
| route | S1 `estimated_claude_tokens_saved`: ceiling of input plus output bytes divided by four and batch size; `observed_claude_tokens_saved` stays zero. |
| flux_triage (delegation) | `clavain-delegation-shadow-v1`: `main_thread_tokens` and `estimated_claude_tokens_saved`; null when unknown. Join S1 by `decision_id`, group by `site`; see delegation-shadow.md. |
| review_exit | `review-exit-observation-v1`: `claude_tokens` is an artifact byte proxy. Later `review-exit-outcome-v1` rows update hypothetical savings; use the latest outcome per decision, never sum cumulative updates. |
| learned_router | `clavain-learned-router-v1`: `estimated_input_tokens` is prompt characters divided by four, rounded up; `estimated_claude_tokens_saved` stays zero when the heuristic keeps the same seat. Join S1 via `s1_decision_id`. |

Unknown estimates stay null. S1 physical-attempt usage is provider accounting,
not Claude savings; heuristic observations make zero provider attempts. Logs
contain hashed identifiers and numeric projections, never raw text or credentials.
