---
artifact_type: plan
bead: Sylveste-364
stage: design
requirements:
  - Sylveste-364: Stop hooks must not inject prompt turns into headless sessions
---
# Headless-Session Hook Gate Implementation Plan

**Bead:** Sylveste-364
**Goal:** Clavain's Stop hook (`auto-stop-actions.sh`, all four tiers: goal-cadence / compound / dispatch / drift) must detect non-interactive `claude -p` sessions and exit without emitting `decision:"block"` — in print mode the injected reason becomes a fed prompt turn and the model's answer to it replaces the reply the caller asked for.

**Reproduced (2026-07-20, this Mac):** `claude -p 'Reply with exactly: PROBE-OK'` returns hook chatter instead of PROBE-OK in BOTH a goal-active cwd (goal-cadence flavored) and a neutral scratch cwd — plugin-wide, not goal-scoped. The two user-level Stop hooks (`git-uncommitted-nudge.sh`, `canongraph-run-bridge.py`) never block (verified) — `auto-stop-actions.sh` is the sole injector.

**Detection design:** hooks run as descendants of the claude process, so its argv is visible via `ps`. Walk up to 8 ancestors; on the first argv containing `claude`, report headless iff it carries `-p`/`--print`. **Fail-open:** any ps/parse failure reports "not headless" so interactive behavior can never be lost by a detector bug.

**Deploy note:** the live hooks run from the installed plugin cache (`~/.claude/plugins/cache/interagency-marketplace/clavain/<ver>/hooks/`), not the repo — the fix lands in the repo (canonical) AND is mirrored into the active cache version for immediate effect; future plugin releases carry it normally.

---

## Task 1: `hooks/lib-headless.sh` + gate in `auto-stop-actions.sh`

**Files:** Create `hooks/lib-headless.sh`; modify `hooks/auto-stop-actions.sh` (gate near top, before the stop-sentinel claim).

`lib-headless.sh`:

```bash
#!/usr/bin/env bash
# lib-headless.sh — detect non-interactive (claude -p / --print) sessions.
#
# Stop hooks that emit decision:"block" inject their reason as a NEW PROMPT
# TURN. Interactively a human sees the result; in a headless `claude -p` run
# the model's answer to the injected turn REPLACES the reply the caller asked
# for (observed live 2026-07-20: a scripted data pass lost 44/45 responses to
# hook chatter — Sylveste-364). Turn-injecting hooks must no-op when headless.
#
# Fail-open: on any error report "not headless" (return 1) so interactive
# behavior is never lost to a detector bug.

clavain_is_headless() {
    local pid=$$ args
    for _ in 1 2 3 4 5 6 7 8; do
        pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ') || return 1
        [[ -z "$pid" || "$pid" == "0" || "$pid" == "1" ]] && return 1
        args=$(ps -o args= -p "$pid" 2>/dev/null) || return 1
        if [[ "$args" == *claude* ]]; then
            case " $args " in
                *" -p "*|*" --print "*) return 0 ;;
            esac
            return 1   # found the claude ancestor and it is interactive
        fi
    done
    return 1
}
```

Gate in `auto-stop-actions.sh`, inserted immediately after the jq guard and before `INPUT=$(cat)`:

```bash
# Headless guard (Sylveste-364): a decision:"block" in a `claude -p` run is
# fed back as a prompt turn and REPLACES the caller's reply — never inject
# into non-interactive sessions.
source "${BASH_SOURCE[0]%/*}/lib-headless.sh" 2>/dev/null || true
if declare -F clavain_is_headless >/dev/null 2>&1; then
    if clavain_is_headless; then
        exit 0
    fi
fi
```

## Task 2 (ORCHESTRATOR): mirror to active plugin cache + E2E probes

1. Copy both files into the installed cache version's `hooks/` (the PreToolUse cache guard may require doing this via `cp`, which is the intent — a deliberate mirror of a repo commit, recorded in the bead).
2. Probe A (goal-active cwd) and Probe B (neutral scratch cwd): `claude -p 'Reply with exactly: PROBE-OK' --model claude-haiku-4-5-20251001` must output exactly `PROBE-OK`.
3. Negative control: `bash -c 'source hooks/lib-headless.sh; clavain_is_headless'` from a plain shell (no claude ancestor) exits 1 — proves the detector does not fire outside claude, i.e. interactive sessions keep their hooks (their claude ancestor lacks `-p`).

---

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
