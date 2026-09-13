**Verdict: NEEDS_ATTENTION.** The scoping language is honest and consistent across the three docs and the receipt. No promotion, no green CI, and no task credit is claimed anywhere. The attention items are durable provenance for the publisher review verdict, a reviewed-versus-installed commit gap, and four gauge-design risks. All are fixable before commit or before the first enrollment. I changed nothing.

## Acceptance replay

- **No promotion or all-green claim: PASS.** The runbook says reaching the checkpoint is not automatic promotion, the rereview says this is not completion of the adoption goal, and the receipt records `automatic_promotion: false` with CI as "not green" and ten baseline failures. "Scoped releases complete" in the state line describes publication, not promotion.
- **Zero benchmark/probe credit: PASS.** The receipt carries `estate_task_credit: 0` and excludes the 54 cells, transport probes, and pre-enrollment work including the release itself. The runbook repeats the exclusion.
- **Explicit narrow Mac manual enrollment: PASS on text.** Mode, host scope, and the zklw, Intercom, routine, and interserve exclusions appear in both runbook and receipt. Intercom is a real Sylveste app, not a typo. See M3 for the exposure caveat.
- **Producer/validator independence: PASS per task.** The receipt's route snapshot matches `config/routing.yaml` field for field. The validation role resolves to Fable with Kimi and Sol fallbacks, none of which is Astra, and dispatch.sh requires a producer identity for validator roles. This review is itself Fable on Astra output. See M2 for the checkpoint-level caveat.
- **Durable provenance: NOT MET.** The publisher review verdict lives under a temp directory. See H1, M1, L2.
- **Preserves user scope: PASS on text.** Global installer not run, base config not rewritten, no broad cleanup, and the PR path plus scoped publication are attributed to user authorization. I cannot verify that authorization. The receipt records its basis without a pointer to a decision or session.

## Independent findings

**High**
- **H1. Publisher review verdict is stored in a temp directory.** The receipt points the scoped-publish CLEAN verdict at `/private/tmp/astra-publish.ub2P7R/intercore/.clavain/intercore.db`. That file exists right now, but macOS periodic maintenance removes tmp files after a few days. The runbook's own required gate says verdicts must be durable and queryable, and both docs cite this verdict as release evidence. Copy the store, or export decision 4 with its report, next to the receipt and record its hash before commit.

**Medium**
- **M1. CLEAN was sealed on e99ad8f, but the installed release is 314bfa8.** The receipt records both SHAs honestly. The prose says the publisher review was CLEAN and the publisher is installed at 314bfa8 without saying what changed between them or what re-check covered the delta. State whether the follow-up is docs-only or code, and which check ran on it.
- **M2. The model under test reviews its own checkpoint.** The runbook has the integrator review evidence at the checkpoint, and the integrator role resolves to Astra. Per-task validation is independent, but the aggregate packet mk decides from would be Astra-authored. Route the checkpoint packet through the same sealed different-model validation before mk decides.
- **M3. Measured scope is narrower than exposure.** The interactive base profile is already Astra/xhigh, so every un-enrolled interactive task on this Mac, including this diff and the releases, already runs on Astra with no evidence and no stop condition. Say that plainly, and say whether a high-severity escape in un-enrolled interactive work halts enrollment.
- **M4. The 0.909 stop has no sample floor.** Stopping immediately below 0.909 with failures retained means one failure before the tenth success ends the canary. That contradicts the same paragraph's statement that an insufficient sample cannot establish quality. It also rewards labeling early failures as abandonments, which the receipt counts separately and the runbook never places in the denominator. Apply the ratio at the checkpoint or after a floor, keep the qualitative triggers immediate, and define abandonment.
- **M5. Rerunning the Codex installer would strip working MCP config.** The doctor warning the audit describes is real at `scripts/install-codex.sh:1335`, and the installer's legacy cleanup removes every `[mcp_servers.*]` table on any rerun. If the official schema really is `mcp_servers`, a codex-bootstrap on this Mac mid-canary breaks MCP silently and confounds task results. Add "no installer or codex-bootstrap on the canary host until Sylveste-8nov lands" to the invariants.

**Low**
- **L1. External link unverified.** The audit cites `https://learn.chatgpt.com/docs/extend/mcp` for the MCP schema. Fetching was denied here, and that domain is not where Codex docs have historically lived. Your own discipline requires a live check before commit.
- **L2. Closures and parent are not bound.** The runbook says six beads were closed under signed gates, but neither doc nor receipt names them or the parent adoption bead. Add a closed list to the receipt.
- **L3. Receipt snapshots are asymmetric.** The main-integrator route carries its fallback chain, while the validator and deep profiles do not. The rule that all validator fallbacks differ from the producer is true in routing config but not evidenced in the receipt. The `binary_source` field is undefined; it resolves to the docs-only commit before the version bump.
- **L4. The gate measures a different quantity than its name.** Executors receive a brief by default, so "plan-to-execution success" during the canary is brief-driven and not comparable to a plan-driven pass rate. Enrollment IDs also have no defined scheme, and unique-task counting depends on them.

`★ Insight ─────────────────────────────────────`
- A receipt that points at a store inherits the store's lifetime. Embedding the verdict row, or hashing a copied store, is what makes a receipt self-sufficient.
- Ratio gates without a sample floor punish honest early failures and shift the incentive toward reclassification. Qualitative stops can be immediate; ratios belong at checkpoints.
- Independence rules are about fallbacks, not primaries. A route snapshot only proves the rule if it captures every substitutable chain.
`─────────────────────────────────────────────────`

## Not verified from this sandbox

Every command outside the Clavain checkout and every network tool was denied, so I did not confirm Intercore decision 540, the bead states for kbh5, 8nov, 9niq, and lca, Interflux PR 25 and 26 merge state, CI run 33983525897, the Intercore delta from e99ad8f to 314bfa8, or the external URL. I did confirm locally that both Clavain SHAs resolve, the plugin manifest reads 0.6.308, `--via zaka` and `--producer-identity` exist in dispatch.sh, the collector script exists, and the canary start time is four minutes before my clock check.

