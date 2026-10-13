# asks

Pure library (not wired into hooks) for inter-thread messaging, modeled on
joelhooks/rat-king `pi-ratking` `asks.ts` and `attend.ts`.

- `Journal`: ask lifecycle `pending -> nudged (due) -> answered (reply) -> closed (ack)`.
  Illegal transitions return `ErrIllegalTransition`. Persistence (`Load`/`Save`)
  and clock (`Now`) are injected ports; `Marshal`/`Unmarshal` give the JSON
  format. Asks return immediately; `DueBy` is optional and an ask without it
  is never nudged. Replies must match both ask id and sender `Did`.
- `Attend(Arrival) Verdict`: `Now | Next | Later(window) | Never` plus a
  `Reason` of facts (to/cc/ask/reply/relay/digest). Copies that are not asks
  and not relayed are quiet (`Next`), or `Later(window)` with a digest.
  `Never` is reserved for caller suppression rules; the base intent does not
  produce it.

Tests: `go test ./asks` from `os/Clavain/cmd/clavain-cli` (exhaustive arrival
properties, exhaustive + randomized state-machine model, journal-vs-model run).
Source: beads mk-lyscb/mk-taovl, design choice.
