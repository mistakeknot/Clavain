## Acceptance Criteria

All commands run on zklw from a clean checkout of the landed branch. `ART` is the T11 evidence directory. Each result is recorded with commit SHA, host, time and raw exit status. No criterion is satisfied by this document's promises.

1. **The structural selector suite passes with Interstat present and no hidden skips.**

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/ -q -k selector -rs 2>&1 | tee /tmp/selector-structural.txt; test "${PIPESTATUS[0]}" -eq 0 && ! grep -q "SKIPPED.*interstat" /tmp/selector-structural.txt
   ```

2. **The hook wrapper is fail-open on every path.**

   ```check
   cd /home/mk/projects/.clavain-jev && bats tests/shell/selector_hook.bats
   ```

3. **Default install is unchanged: no hook registration or host-adapter change, and the full existing suites pass with flags unset.**

   ```check
   cd /home/mk/projects/.clavain-jev && git diff --quiet origin/main -- hooks/hooks.json config/host-adapters.json && env -u CLAVAIN_SELECTOR -u CLAVAIN_SELECTOR_SELFTEST ./tests/run-tests.sh
   ```

4. **Flag off makes no records and touches no credential.** A test proves zero socket attempts and no call to the credential loader; after criterion 3's run no records exist from that time window.

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_orchestrator.py -q -k flag_off && test -z "$(find ~/.clavain/selector/records -newer /tmp/selector-structural.txt -type f 2>/dev/null)"
   ```

5. **Egress refusal opens zero connections.** For every rule id, a loopback listener records zero accepted connections.

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_egress.py structural/test_selector_orchestrator.py -q -k "egress or refus"
   ```

6. **Every fallback reason resolves to native, in the documented order.**

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_contract.py structural/test_selector_orchestrator.py -q -k "fallback_table or gate_order"
   ```

7. **Records never contain task, context, payload, raw output or key material.**

   ```check
   cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_records.py structural/test_selector_jev_client.py -q -k "forbidden or leak"
   ```

8. **One real, authorized Jev shadow round trip produced a valid schema-v1 record and native behavior.**

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
   print("ok", r["decision_id"], r["result"], r["selector"]["latency_ms"])
   PY
   ```

9. **Live latency is within budget:** p95 ≤1000ms and ≤10% of 30 calls exceed 1500ms.

   ```check
   python3 /home/mk/projects/.clavain-jev/scripts/clavain-select.py records --record-dir "$ART/latency" --latency-summary --assert-p95-ms 1000 --assert-over-deadline-frac 0.10
   ```

10. **Burn ledger matches burn-report on a real Claude session and the final cumulative total on a real Codex rollout,** and reports invalidation, expiry and compaction separately.

    ```check
    test -f "$ART/burn-claude.json" && test -f "$ART/burn-codex.json" && python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); x=json.load(open(sys.argv[2])); assert c["consistency"]["matches_burn_report"] and x["consistency"]["matches_final_cumulative"]; assert {"invalidation","expiry","compaction_or_reset"} <= set(c["events"])' "$ART/burn-claude.json" "$ART/burn-codex.json"
    ```

11. **The eval refuses unsealed or changed labels, and the selftest set runs all three arms with zero forbidden selections.**

    ```check
    cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_eval.py -q
    ```

12. **The canon doc matches the host matrix and names every fallback reason and the retention terms.**

    ```check
    cd /home/mk/projects/.clavain-jev/tests && uv run pytest structural/test_selector_docs.py -q
    ```

13. **The Intercore disposition is recorded.** Either the inventory says `export-safe: yes` and an exported `selector_decision_v1` event is visible once, or it says `no` and names a filed Intercore bead with export off.

    ```check
    f=$(ls /home/mk/projects/.clavain-jev/docs/research/jev/*interspect-consumer-inventory.md) && grep -Eq 'export-safe: (yes|no)' "$f" && { grep -q 'export-safe: yes' "$f" && ic events list --source interspect --json | grep -c selector_decision_v1 | grep -qx 1 || grep -Eq 'export-safe: no.*(bead|Bead) [A-Za-z0-9.-]+' "$f"; }
    ```

14. **Independent review is recorded** with reviewer identity, model, whether it was other-frontier or provisional same-model, and verdict, on bead mk-42j9.7 (checked by reading the bead notes; not automatable here).

