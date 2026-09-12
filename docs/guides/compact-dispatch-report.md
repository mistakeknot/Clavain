# Compact Codex dispatch reports

`scripts/dispatch.sh --report compact` emits one deterministic JSON object on
stdout while retaining the complete Codex evidence. The default remains
`--report full`; omitting `--report` preserves the existing output and exit
behavior.

Compact mode is opt-in, supports only one-shot Codex `exec` dispatches, and
requires `-o/--output-last-message`. Other backends and `--via` transports are
rejected before launch.

```bash
bash scripts/dispatch.sh --report compact \
  -C /path/to/project \
  -o /tmp/dispatch-last-message.md \
  "Run the requested check"
```

The `-o` file is still the original full last message. Its `.summary` and
`.verdict` sidecars keep their existing formats, so review and verification
consumers do not receive the compact JSON in place of their source evidence.
The compact JSON is written to stdout and is at most 4096 UTF-8 bytes including
its trailing newline.

For every compact attempt, dispatch creates a fresh mode-0700 directory named
`.clavain-dispatch-compact.*` beneath the output file's parent. Mode-0600 files
retain the raw JSONL stdout stream, stderr, last message, summary, verdict,
outcome metadata, `process.json`, and any available resolved-route or receipt evidence. The
manifest lists logical artifact names in sorted order with status, final size,
and SHA-256. Its own SHA-256 is carried by the report rather than written into
the manifest.

The report distinguishes the backend process code from the dispatcher code.
On cancellation, the supervisor signals the native process group and allows
two seconds before escalating termination. It records the reaped backend's
actual exit separately from the dispatcher's cancellation code. An unavailable
process status remains unknown. Normal completion drains the event stream to
EOF without imposing this cancellation deadline.
If a descendant escapes that process group and retains the event pipe, the
supervisor limits its final drain to 50 ms or 1 MiB, closes the pipe, and marks
capture incomplete. It cannot establish that an escaped descendant stopped.
Malformed or contradictory native events make native coverage incomplete and
counter values explicitly unknown; a parent session ID is never substituted
for a native `thread.started` ID. Missing, inconsistent, or nonregular required
artifacts make the presentation unusable and point recovery to the full
artifacts in the output parent. Such a report is not an approval signal.

Optional fields degrade only as whole fields, in this order: diagnostics,
counters, native identity, artifact paths. Text and UTF-8 bytes are never
truncated. If even the recovery path cannot fit, the renderer emits an unusable
report with the fixed recovery text `full artifacts in output parent` and keeps
the manifest digest.

To verify a sealed attempt and reproduce its presentation without a model call:

```bash
python3 scripts/dispatch_report.py replay \
  --artifacts-dir /tmp/.clavain-dispatch-compact.EXAMPLE
```

Replay returns zero only when every available manifest entry still has its
sealed type, size, and digest and the stored outcome is usable. It emits an
unusable report and returns nonzero when evidence is missing, nonregular, or
changed.
