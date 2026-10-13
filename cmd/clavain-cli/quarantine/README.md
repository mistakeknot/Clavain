# quarantine

Pure library (not wired into hooks), modeled on joelhooks/rat-king `pi-ratking`
`quarantine.ts`. When an input cannot be parsed or verified, `Store.Handle`
writes `<seq>.json` (seq, id, source, reason code, byte length, timestamp;
never the body), skips the item and advances `cursor.json` (monotonic).
`Summarize(dir).Line()` gives `quarantined:N latest:<reason>` for a status line.
The body is never persisted: `Handle` only measures it and passes it to the
verifier, and source/reason/id must be code tokens, so free text cannot reach disk. Non-`Failure` verifier errors map to
`unverifiable` because error text can echo input.

Tests: `go test ./quarantine` (fuzzed-secret no-persist property, token
rejection, summary, cursor model vs. reference max).
Source: beads mk-yda6d/mk-nwphk, design choice.
