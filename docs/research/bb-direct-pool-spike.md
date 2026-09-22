# Direct Codex pool spike — 2026-09-22

Plan B rev 2, bead sylveste-8252.3. A scratch `plan-review` dispatch with
producer `claude-fable-5-1`, read-only sandbox and no tool request completed
through Astra/xhigh. No accounts, routing profiles or pool settings changed.

The installed BB provider supplies explicit Codex provider configuration as
well as environment variables. The responses base URL must end in
`/api/v1/plugins/account-pool/http/v1`. Authentication uses the
`x-bb-account-pool-token` header sourced from `CODEX_POOL_AUTH_TOKEN`; the
parent BB token is never substituted. The adapter mirrors that contract.

Evidence:

- Dispatch attempt `15b81165-f3af-4855-b5e3-7f6e8d103526` has started/completed
  Intercore records with `transport=direct-pooled`, sandbox `read-only` and
  `account=unknown`.
- Codex emitted session `01a0cb43-b48c-7321-a81f-efaf8f254dca`, a final
  `VERDICT: CLEAN`, and usage of 24,687 input tokens (12,160 cached), 172 output
  tokens (162 reasoning).
- A read-only query of the hub's `pool_affinity` table found the exact key
  `["codex","host_pda34naxgq","session:01a0cb43-b48c-7321-a81f-efaf8f254dca"]`
  at epoch milliseconds `1790116608441`. This proves hub traffic, unlike a
  concurrent aggregate utilization change.
- Raw output and report reside in `/tmp/clavain-bb-spike/`; Intercore records
  are in `/tmp/.clavain/intercore.db`. No BB thread was created by this direct
  probe. No child remains to archive.

The pool exposes no supported request-scoped account attribution command.
The manual affinity inspection is spike evidence; production receipts must
retain unknown attribution. A live forced account exhaustion/switch was not
performed; account-before-model ordering is covered by
`tests/routing/role-dispatch-test.sh`. Claude inherits its provider environment,
but a Claude hub canary has not been run. The direct pool path remains an
explicit `CLAVAIN_BB_DIRECT_POOL=1` opt-in until these acceptance gaps and the
integration review are resolved. This is a staged implementation, not a
claim of complete transport parity.

The real quota fixture is a Codex rollout event, supplied by the coordinator;
the exit-zero regression is synthetic. A direct stdout capture was blocked
before launch by read-only Codex state and is not a quota fixture.
