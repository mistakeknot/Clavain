# GPT-6.2 seat cutover

Source: bead mk-au6a1. Sol seats select `gpt-6.2-sol`; Astra seats select
`gpt-6.2-astra`. Existing efforts, fallback order, frontier floors and
cross-lab reviewer independence stay unchanged. No price, plan, cap or
go-ahead change.

Rollout is blocked on companion bead mk-18k30 for Intercore support for the `gpt-6.2-*` effort ladder.
The installed `ic` at commit `8c82b970` excludes both new IDs when a floor
applies. Foundational plan review of an Opus producer then has no eligible
other-frontier reviewer. The tiny packaged-dispatch canaries returned OK for
both requested IDs, but did not establish floored routing acceptance.

Before rollout:

1. Qualify an Intercore build with the 6.2 effort ladder using
   `tests/routing/gpt62-effort-floor-test.sh` (six cases), then
   `tests/routing/reasoning-contract-test.sh`, including the Opus producer case.
2. Regenerate and review the role-resolution and dispatch goldens with that
   build. The current recorded table captures the installed resolver's
   degraded behavior and is not rollout acceptance.
3. Finish old-ID experiment work before selecting the new package, or launch
   a fresh producer on 6.2 Astra. Experiment admission intentionally binds
   the exact new producer and arm IDs; old receipts remain historical.
4. Refresh readiness evidence using the new exact probe ID. Existing bound
   old-ID readiness evidence does not establish readiness for 6.2 Astra.

Both new IDs warn that model metadata was not found at runtime. Preserve that
caveat even when the requested-ID call succeeds. The new roster names and
slugs are unverified against the pinned benchmark snapshot; the generator
must continue to refuse missing rows. Previous rows remain for attribution.

Keep the routing audit and burn-watch retired lists unchanged while old-ID
sessions remain active. Retirement is a later cutover step, not evidence that
the new seats are ready. Aleph and fleet instruction installation are outside
this repository change.
