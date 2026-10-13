# records

Pure library (not wired into hooks): opt-in, metadata-only turn/friction records
and a daily usage digest, modeled on joelhooks/rat-king `pi-ratking`
`turn-record.ts`. Off unless `CLAVAIN_TURN_RECORDS` is truthy or the config
switch is set (explicit falsey env wins). Every string is a short code token and
decoding rejects unknown fields, so no content field can exist.

Tests: `go test ./records` from `os/Clavain/cmd/clavain-cli` (default-off,
switch matrix, schema rejection, fuzzed-secret no-persist property, digest).
Source: beads mk-yda6d/mk-nwphk, design choice.
