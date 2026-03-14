---
name: bead-sweep
description: Scan open beads for stale trackers that are already implemented — deterministic checks first, LLM verification second
argument-hint: "[--auto-close] [--limit N] [plugin-name]"
---

# Bead Sweep

Find and close beads that track work already done. Uses deterministic code checks first (command files, git history, function grep), then optionally runs LLM verification for ambiguous cases.

<sweep_args> #$ARGUMENTS </sweep_args>

## Parse Arguments

- `--auto-close`: Close confirmed-done beads without asking (default: ask per bead)
- `--limit N`: Max beads to check (default: 50)
- `plugin-name`: Optional — restrict sweep to beads matching this plugin (e.g., "interspect")

## Step 1: Gather Candidates

```bash
# Get all open beads (not epics — those need manual review)
OPEN_BEADS=$(bd list --status=open --json 2>/dev/null) || { echo "Error: bd not available"; exit 1; }

# Filter to non-epic beads
CANDIDATES=$(echo "$OPEN_BEADS" | jq '[.[] | select(.type != "epic")]')

# Optional plugin filter
if [[ -n "$PLUGIN_FILTER" ]]; then
    CANDIDATES=$(echo "$CANDIDATES" | jq --arg p "$PLUGIN_FILTER" '[.[] | select(.title | ascii_downcase | contains($p | ascii_downcase))]')
fi

# Apply limit
CANDIDATES=$(echo "$CANDIDATES" | jq ".[0:${LIMIT:-50}]")

COUNT=$(echo "$CANDIDATES" | jq 'length')
```

Display: `Scanning ${COUNT} open beads for stale trackers...`

## Step 2: Deterministic Pass

Source the discovery library and run `_discovery_check_implemented` on each candidate:

```bash
export DISCOVERY_PROJECT_DIR="."
# Source interphase's lib-discovery.sh (contains _discovery_check_implemented)
INTERPHASE_ROOT=$(find ~/.claude/plugins/cache -path '*/interphase/*/hooks/lib-discovery.sh' 2>/dev/null | head -1)
if [[ -z "$INTERPHASE_ROOT" ]]; then
    INTERPHASE_ROOT=$(find ./interverse/interphase -name 'lib-discovery.sh' -path '*/hooks/*' 2>/dev/null | head -1)
fi
[[ -n "$INTERPHASE_ROOT" ]] && source "$INTERPHASE_ROOT"
```

For each candidate, call `_discovery_check_implemented "$id" "$title"`. Collect hits into two buckets:
- **Confirmed hits**: beads where the deterministic check found evidence (command file, commit reference, function exists)
- **No signal**: beads where deterministic checks found nothing

## Step 3: Report Deterministic Findings

Present confirmed hits in a table:

```
## Deterministic Sweep Results

Found N bead(s) with implementation signals:

| Bead | Title | Signal |
|------|-------|--------|
| iv-xxx | /foo command | command file exists: foo.md |
| iv-yyy | Add _bar_func | function exists in: lib-bar.sh |
| iv-zzz | Fix widget bug | referenced in commit: abc1234 fix widget... |
```

## Step 4: LLM Verification (for deterministic hits)

For each bead with a deterministic signal, read the relevant code to verify:

1. Read the bead description: `bd show <id>`
2. Read the evidence file (command .md, lib function, etc.)
3. Assess: does the implementation match the bead's acceptance criteria?

Classify each as:
- **Done**: Implementation fully covers the bead scope → close it
- **Partial**: Some work done but acceptance criteria not fully met → skip, note what's missing
- **False positive**: Code exists but doesn't actually address this bead → skip

## Step 5: Close or Report

For each **Done** bead:
- If `--auto-close`: `bd close <id> --reason="Bead sweep: <evidence summary>"`
- Otherwise: present and ask for confirmation via AskUserQuestion

For **Partial** beads: report what's missing so the user can decide whether to close or continue the work.

Present final summary:

```
## Sweep Summary

- Scanned: {total} beads
- Signals detected: {signal_count}
- Verified done: {done_count} (closed)
- Partial: {partial_count} (needs review)
- False positive: {fp_count}
- No signal: {no_signal_count} (skipped)
```

## Step 6: Backup

After closing beads:
```bash
bd backup 2>/dev/null || true
```
