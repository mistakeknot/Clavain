## Acceptance Criteria

All commands run on zklw from a clean checkout of the landed branch. `ART` is the T12 evidence directory. Each result is recorded with commit SHA, host, time and raw exit status. No criterion is satisfied by this document's promises.

1. **The structural selector suite passes with Interstat present and no hidden skips.**

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/ -q -k selector -rs 2>&1 | tee /tmp/selector-structural.txt; test "${PIPESTATUS[0]}" -eq 0 && ! grep -qi "SKIPPED.*interstat" /tmp/selector-structural.txt
   ```

2. **The hook wrapper is fail-open on every path.**

   ```check
   cd /home/mk/projects/.clavain-jev && bats tests/shell/selector_hook.bats
   ```

3. **Default install is unchanged: no hook registration or host-adapter change, and the full existing suites pass with flags unset.** After landing, `git diff origin/main` is trivially clean, so the check also requires that no commit touching those two files mentions the selector or this bead. The per-commit guard remains T7's verify block.

   ```check
   cd /home/mk/projects/.clavain-jev && git diff --quiet origin/main -- hooks/hooks.json config/host-adapters.json && test -z "$(git log --oneline -i --grep=selector --grep=mk-42j9.7 -- hooks/hooks.json config/host-adapters.json)" && env -u CLAVAIN_SELECTOR -u CLAVAIN_SELECTOR_SELFTEST ./tests/run-tests.sh
   ```

4. **Flag off makes no records and touches no credential.** A test proves zero socket attempts and no call to the credential loader; after criterion 3's run no records exist from that time window.

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_orchestrator.py -q -k flag_off && test -z "$(find ~/.clavain/selector/records -newer /tmp/selector-structural.txt -type f 2>/dev/null)"
   ```

5. **Egress refusal opens zero connections, realistic secrets are refused, avoidable false positives are admitted, and admission cannot be bypassed by accident.** For every rule id (including JSON-quoted keys, provider prefixes, Basic auth, cookies, netrc, PGP, package tokens, short and spaced passwords and the high-entropy rule with its path and slug handling), a loopback listener records zero accepted connections; realistic payloads are refused; false-positive fixtures are admitted; a hand-built `AdmittedRequest` fails `verify()` and the client refuses it before connecting.

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_egress.py -q && uv run pytest structural/test_selector_orchestrator.py structural/test_selector_jev_client.py -q -k "egress or refus or only_admitted"
   ```

6. **Every fallback reason resolves to native, in the documented order.**

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_contract.py structural/test_selector_orchestrator.py -q -k "fallback_table or gate_order"
   ```

7. **Records never contain task, context, payload, raw output or key material; refused records carry no summaries; the selector never records `applied: selected`.**

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_records.py structural/test_selector_jev_client.py structural/test_selector_orchestrator.py -q -k "forbidden or leak or refused_record or applied or emits_never_selects"
   ```

8. **One real, authorized Jev shadow round trip produced a valid schema-v1 record and native behavior,** and no record in the run has `applied` other than `native`.

   ```check
   python3 - "$ART/records" <<'PY'
   import json, pathlib, sys
   recs = [json.loads(l) for p in pathlib.Path(sys.argv[1]).glob("*.jsonl") for l in p.read_text().splitlines() if l.strip()]
   live = [r for r in recs if r["mode"] == "shadow" and r["integration"] == "selftest" and r["selector"].get("http_status") == 200]
   assert live, "no live shadow record"
   r = live[0]
   assert r["schema_version"] == 1 and r["selector"]["model_returned"] == "jev-1.13.0"
   assert r["egress"]["verdict"] == "admitted" and r["applied"] == "native"
   assert r["result"]["kind"] in ("selected", "abstained") and r["selector"]["latency_ms"] > 0
   assert r["candidates"] and len(r["candidates"]) <= 16
   assert all(x["applied"] in ("native", "emitted") for x in recs), "unexpected applied value"
   assert not any(x["applied"] == "emitted" for x in recs), ".7 must not emit"
   print("ok", r["decision_id"], r["result"], r["selector"]["latency_ms"])
   PY
   ```

9. **Live latency is within budget over distinct inputs:** p95 ≤1000ms and ≤10% of 30 calls exceed 1500ms (wrapper timeouts counted as over-deadline), across at least 5 distinct request bodies.

   ```check
   python3 /home/mk/projects/.clavain-jev/scripts/clavain-select.py records --record-dir "$ART/latency" --latency-summary --assert-p95-ms 1000 --assert-over-deadline-frac 0.10 --assert-distinct-inputs 5
   ```

10. **Burn ledger reconciles with burn-report on a real Claude session (unexplained delta within tolerance) and with the compaction-excluded final cumulative on a real Codex rollout (no `session_cumulative_mismatch`),** and reports invalidation, expiry and compaction separately.

    ```check
    test -f "$ART/burn-claude.json" && test -f "$ART/burn-codex.json" && python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); x=json.load(open(sys.argv[2])); cc=c["consistency"]; xc=x["consistency"]; assert cc["reconciled"] and abs(cc["unexplained"]) <= cc["tolerance"]; assert xc["matches_final_cumulative_excluding_compaction"] and not xc["session_cumulative_mismatch"]; assert {"invalidation","expiry","compaction_or_reset"} <= set(c["events"]) and {"invalidation","expiry","compaction_or_reset"} <= set(x["events"])' "$ART/burn-claude.json" "$ART/burn-codex.json"
    ```

11. **The eval refuses unsealed or changed labels, scores the holdout once against its first seal (disjointness by case content hash), reports shortlist recall separately, has a counts-only offline egress scan, and the selftest set runs all three arms with zero forbidden selections.**

    ```check
    cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_eval.py -q -rA 2>&1 | tee /tmp/selector-eval.txt; test "${PIPESTATUS[0]}" -eq 0 && python3 -c 'import re,sys; s=open(sys.argv[1]).read(); miss=[t for t in ("holdout_first_seal_only","holdout_scored_once","holdout_refused_on_changed_floors","shortlist_recall_reported","egress_scan_counts_only") if not re.search(r"^PASSED \S+::test_"+t+r"\b",s,re.M)]; print("missing:",miss) if miss else None; sys.exit(1 if miss else 0)' /tmp/selector-eval.txt
    ```

12. **The canon doc matches the host matrix and names every fallback reason and the retention terms.**

    ```check
    cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_docs.py -q
    ```

13. **The Intercore disposition is recorded and export is idempotent.** The `requires_ic` idempotency test runs (not skipped). Either the inventory says `export-safe: yes` and the live `selector_decision_v1` count (from `ic --json events tail --all`, since `ic` 0.3.5 has no `events list`) is nonzero after the first export and unchanged after the second, or it says `no` and names a filed Intercore bead with export off.

    ```check
    cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_ic_export.py -q -rs 2>&1 | tee /tmp/selector-ic.txt; test "${PIPESTATUS[0]}" -eq 0 && ! grep -q SKIPPED /tmp/selector-ic.txt && f=$(ls /home/mk/projects/.clavain-jev/docs/research/jev/*interspect-consumer-inventory.md) && grep -Eq 'export-safe: (yes|no)' "$f" && { { grep -q 'export-safe: yes' "$f" && test "$(cat "$ART/ic-count-1.txt")" -gt 0 && cmp -s "$ART/ic-count-1.txt" "$ART/ic-count-2.txt"; } || grep -Eq 'export-safe: no.*(bead|Bead) [A-Za-z0-9.-]+' "$f"; }
    ```

14. **Independent review is recorded** with reviewer identity, model, whether it was other-frontier or provisional same-model, and verdict, on bead mk-42j9.7 (checked by reading the bead notes; not automatable here).

15. **The operator CLI works and `doctor` never opens the secrets file;** the latency probe rotates at least 5 distinct inputs.

    ```check
    cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_cli.py -q
    ```

16. **High-entropy false positives are measured where the rule is on.** The offline `post_tool_output` calibration over real tool output (T12 step 8) sampled at least 500 blocks, and the high-entropy-only refusal fraction is ≤0.03 and the total refusal fraction is ≤0.10. A failure triggers the egress calibration escalation and blocks .10's `post_tool_output` use; it does not block landing .7.

    ```check
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["point"]=="post_tool_output" and d["sampled"]>=500, d.get("sampled"); assert d["high_entropy_only_frac"]<=0.03 and d["refused_frac"]<=0.10, (d["high_entropy_only_frac"], d["refused_frac"]); print("ok", d["sampled"], d["refused_frac"], d["high_entropy_only_frac"])' "$ART/egress-offline.json"
    ```

