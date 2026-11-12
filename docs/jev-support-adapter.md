# Advisory support checks

`python3 scripts/clavain-select.py support-json` reads one request described by
`schemas/selector-support-request.v1.schema.json` and writes one receipt described
by `schemas/selector-support-record.v1.schema.json`. Every ordinary outcome exits
zero; argument errors exit two. An interruption emits accounting before it is
re-raised.

The fixed labels are `supported`, `not_supported`, and `unclear`. Callers supply
their descriptions and an abstention threshold. A tie abstains; confidence equal
to the threshold labels. `unclear` is a semantic answer. Errors have no label.

This is evaluation only. Store and compare labels offline; always apply the native
result. A label must never change a review, gate, merge, or seat decision.

The registry entry is disabled with zero session and daily budgets. The flag also
defaults off. Live qualification and its budget values require owner approval.
An active flag is coerced to shadow, and no default seat or destination changes.
Disable the flag or pin the preceding version to roll back.

Each source must be a regular tracked file in an owned Git checkout at the
specified HEAD revision. Paths are relative to the checkout, spans use inclusive
one-based lines, and hashes cover the exact UTF-8 bytes including ending newlines.
Symlinks and sources outside Git are refused. Checkout bytes must equal the Git
blob; checkout filters and line-ending conversions can therefore cause refusal.

Receipts retain hashes and closed metadata, never claims, source text, raw
provider model names, request IDs, exception messages, or Retry-After strings.
Only a valid HTTP 200 usage object supplies reported usage. Non-200 usage remains
unknown even if the body looks like usage. Every physical attempt is recorded;
unfinished attempts remain unknown. A startup exception never proves an attempt
was not sent. If startup never launched a worker, one in-flight slot can remain
reserved until process exit.

The selector and support checker retry at most once, with the existing 100 ms
delay and Retry-After veto. Exceptions retry only before any request byte was
sent. Read-phase failures do not retry. Selector receipts replace the raw returned
model with `model_returned_matches` and `model_returned_sha256`.

Burn consumers use `ledger(..., selector_accounting=..., selector_weights=...)`.
Weights must be explicit positive finite input/output prices with a validated
source name. Unknown usage or missing weights makes the bound unbounded.
`cost_bound_passes` accepts only bounded results. The deprecated `selector_usage`
keyword remains display-only for one release; it cannot establish a cost bound.

Run `scripts/qualify-support-adapter.sh` for dummy-only tests in a network
namespace with no active interfaces. The runner fails if isolation is unavailable.
These tests fail outside that namespace. Run the existing selector client,
records, burn, flags, and egress regression tests separately; those use loopback
sockets. When running the remaining structural suite outside the namespace,
exclude the five `test_selector_support*.py` qualification modules and report
their separately executed counts.
