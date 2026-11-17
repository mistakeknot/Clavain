# Route shadow observations (S2)

S2 adds log-only observers after four existing Haiku classifiers. Native
classification, defaults, foreground checks, background sweep timing, caches,
questions and strategic contradiction escalation still decide all behavior.
Every observer is launched asynchronously with stdin, stdout and stderr
redirected to `/dev/null`. Never wait for it or use its return value.

The observer reads the selected routing YAML (`CLAVAIN_ROUTING_POLICY`, or
the plugin's `config/routing.yaml`, passed explicitly by command instructions).
Only `decision_models.route: {mode: shadow, backend: heuristic}` admits a call.
Off, enforce, unknown modes, missing or malformed configuration, and configured
hosted backends are inert before subprocess execution or logging.
`CLAVAIN_SELECTOR=off`, trimmed and case-insensitive, disables the observer
before reading configuration. Defaults and other tracks remain unchanged/off.
Python needs PyYAML to read configuration; an unavailable dependency is silent
and inert. No installation is attempted.

Call after the native result, supplying only closed identifiers, counts and
hashes computed in caller memory. Example (the hash below is illustrative):

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/clavain_selector/route_shadow.py" \
  --site route-4b --native-choice work \
  --subject-sha256 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --input-bytes 1200 --output-bytes 100 \
  --plugin-root "$CLAUDE_PLUGIN_ROOT" \
  --config "${CLAVAIN_ROUTING_POLICY:-$CLAUDE_PLUGIN_ROOT/config/routing.yaml}" \
  --project-root "$PWD" </dev/null >/dev/null 2>&1 &
```

| Static site ID | Exact normalized choices |
| --- | --- |
| `route-4b` | `sprint`, `work` |
| `route-staleness` | `implemented`, `not_implemented` |
| `route-sweep` | `implemented`, `not_implemented` |
| `sprint-lane-intent` | `contradicts`, `aligned` |

Normalize exact `/sprint` or `/work` strings for 4b, and actual JSON booleans
for the other sites. Malformed results are skipped, retaining all existing
native fallback behavior. The subject is SHA256 of the bead ID, or of the
description for text-mode 4b. Never send the subject's raw text. No native
classification prompt, response, reason, plan or lane intent is passed to the
observer, persisted or sent to a provider. Counts include the complete native
prompt and response UTF8 bytes, computed without writing their text to disk.
Missing counts or hashes mean skip the observation.

Command instructions apply an eligibility gate before any measurement work or
helper launch: inspect the already available routing policy and silently do
nothing unless route mode is exactly `shadow`, the backend is `heuristic` and
the global kill is not `off`. If the configuration is not already known, only a
normal configuration read is allowed, never a measurement or helper subprocess.
Observe only when exact byte counts, the normalized native choice and the
subject hash are already in hand from host telemetry. No new count, hash or
computation tool calls, no guessing or estimating, no heredocs and no raw text
interpolated into shell code; otherwise skip silently. The savings figure the
observer computes from the supplied exact counts remains an estimate. For the
staleness sweep, only fresh Haiku results arriving within the existing five
second wait are observed; late results and cache hits are dropped, with no
follow-up, polling or completion tracking.

Current hosts may not expose exact byte counts or hashes, so skipping can be
the common outcome. An empty or sparse log is therefore not evidence about
classifier quality, routing quality or the feature's value.
Hashes are pseudonyms: unsalted hashes of enumerable bead IDs or guessed
descriptions can be matched by dictionary search. Private log permissions
provide the confidentiality boundary.

The observer runs `clavain-cli decide` using the bundled
`<plugin-root>/bin/clavain-cli` when it is a regular executable file, otherwise
bare `clavain-cli` from `PATH`. The choice is made once before the call; there
is no fallback if the selected process fails, so the call stays bounded. It is invoked with question ID `route`, site-specific
candidates, explicit plugin/config/project roots, `egress_allowed: false` and
`sources: []`. Its state contains only numeric counts, a SHA256 subject ID and
a static site ID, so there are no source files to declare. CLI output is
discarded and never parsed; `subprocess.run` has a six-second timeout. All
exceptions are silent. S1 also refuses hosted backends when this opt-in
metadata is present, covering a configuration change between reads.

Read local `.clavain/decisions/YYYY-MM-DD.jsonl` using the S1 record reader or
JSONL tools. S1's private permissions, locked append and symlink protection
still apply. `site_sha256` hashes the static site ID above; `subject_sha256`
identifies the subject. Question, candidate and choice IDs are also SHA256.
Compute hashes locally when filtering; raw identifiers cannot be searched in
the log. Compare `native_choice == decide_answer.choice` for agreement.
Confidence is already recorded by S1. Heuristic agreement is tautological:
the heuristic repeats the supplied native choice. It demonstrates plumbing,
privacy and accounting only; it provides no independent quality evidence.

Each S2 record carries plain `estimated_claude_tokens_saved` and
`observed_claude_tokens_saved` (always zero). `estimate_method: 1` names the
UTF8-byte counterfactual method: `ceil((input_bytes + output_bytes) / 4)`.
For a sweep, pass `--batch-size N` and full batch byte counts for each bead;
method 1 apportions equally as `ceil((input_bytes + output_bytes) / (4*N))`.
Rounding shares can overstate the aggregate by up to N-1 tokens. Counts do
not measure tokenization, cache effects, billed tokens or actual avoided calls.
All native calls still run, so observed savings remain zero.

The opt-in `observation_metadata` object in S1 has a closed key set:
`site_sha256`, `subject_sha256`, `input_bytes`, `output_bytes`, `batch_size`,
`estimate_method`, `estimated_claude_tokens_saved`, `observed_claude_tokens_saved`.
Hashes must be 64 lowercase hex characters. Numeric fields must be actual
integers (not booleans), bounded 0–1,000,000,000; batch size is 1–1000, method
is exactly 1, savings must match the formula, and observed savings must be zero.
Invalid metadata is rejected before recording; no arbitrary text is accepted.
Existing S1 callers without metadata keep their current behavior. S1's trial
logs still have no automatic retention or byte cap; monitor disk use.
