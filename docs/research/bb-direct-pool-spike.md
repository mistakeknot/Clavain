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
  are retained in `/tmp/clavain-bb-spike/intercore-evidence/intercore.db`. No BB thread was created by this direct
  probe. No child remains to archive.

The pool exposes no supported request-scoped account attribution command.
The manual affinity inspection is spike evidence; production receipts must
retain unknown attribution. A live forced account exhaustion/switch was not
performed; account-before-model ordering is covered by
`tests/routing/role-dispatch-test.sh`. Claude inherits its provider environment,
but a Claude hub canary has not been run. After the exact hub/session tie was
verified, direct Codex pooling became the default on enrolled BB hosts with
the dedicated pool token. `CLAVAIN_BB_DIRECT_POOL=0` selects the legacy path.

**Addendum 2026-09-23: cross-route borrowing.** Codex seats dispatched from a
Claude Code BB thread have no `CODEX_POOL_AUTH_TOKEN`, because BB injects it only
into Codex threads. They therefore fell back to the local `~/.codex` login, which
failed `quota_exhausted` while pooled accounts had headroom. They now borrow the
machine bearer carried as `ANTHROPIC_AUTH_TOKEN` on the pool's Anthropic route.
- Qualification: a live `gpt-6-astra` `codex exec` through
  `/api/v1/plugins/account-pool/http/v1`, authenticated with the borrowed
  bearer, answered from zklw, and `bb pool status` showed the pooled Codex
  account's `lastUsedAt` advance.
- Governed plan-review and cross-lab-review seats then ran through the pool from
  a Claude thread.
- Account attribution stays unknown in receipts, as before.
- The contract (trust assumption, scope, kill switch and threat model) is in
  [bb-integration](../canon/bb-integration.md).
Unknown account attribution blocks budgeted pooled acceptance. This is not a
claim of complete transport parity; independent integration review remains open.

The coordinator supplied the real rollout quota fixture. A subsequent scratch
stdout capture (session `01a0cb55-4e46-7093-8297-107fd705a968`, exit 1)
confirmed the CLI emits `error.message` and `turn.failed.error.message` without
`codex_error_info`. The classifier recognizes the observed anchored provider
message only within those structured envelopes. The exit-zero test is synthetic.
