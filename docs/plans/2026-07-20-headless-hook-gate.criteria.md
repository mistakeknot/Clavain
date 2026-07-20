## Acceptance Criteria

1. The detector exists, parses, and fails open outside claude.
   ```check
   cd ~/projects/Sylveste/os/Clavain && bash -n hooks/lib-headless.sh && bash -n hooks/auto-stop-actions.sh && bash -c 'source hooks/lib-headless.sh; clavain_is_headless; [ $? -eq 1 ]' && echo detector-failopen-ok
   ```
2. The Stop hook gates on it before any block emission: the gate appears before the stop-sentinel claim and calls `clavain_is_headless`.
   ```check
   cd ~/projects/Sylveste/os/Clavain && awk '/clavain_is_headless/{h=NR} /INTERCORE_STOP_DEDUP_SENTINEL/{s=NR; exit} END{exit !(h && s && h<s)}' hooks/auto-stop-actions.sh && echo gate-before-sentinel-ok
   ```
3. The active plugin cache carries the identical fix (both files byte-equal to the repo).
   ```check
   CACHE=$(ls -d ~/.claude/plugins/cache/interagency-marketplace/clavain/*/hooks | sort -V | tail -1) && diff -q ~/projects/Sylveste/os/Clavain/hooks/lib-headless.sh "$CACHE/lib-headless.sh" && diff -q ~/projects/Sylveste/os/Clavain/hooks/auto-stop-actions.sh "$CACHE/auto-stop-actions.sh" && echo cache-mirrored-ok
   ```
4. E2E: a headless probe from the goal-active FLUXrig cwd returns the model's actual reply.
   ```check
   cd ~/projects/FLUXrig && OUT=$(timeout 120 claude -p 'Reply with exactly: PROBE-OK' --model claude-haiku-4-5-20251001 2>/dev/null | tail -1) && [ "$OUT" = "PROBE-OK" ] && echo probe-a-clean
   ```
5. E2E: a headless probe from a neutral non-repo cwd returns the model's actual reply.
   ```check
   D=$(mktemp -d) && cd "$D" && OUT=$(timeout 120 claude -p 'Reply with exactly: PROBE-OK' --model claude-haiku-4-5-20251001 2>/dev/null | tail -1) && [ "$OUT" = "PROBE-OK" ] && echo probe-b-clean
   ```
