# Create Tier-1 Beads: Correctness Issues

## Task

Create three P0 task beads for correctness-related improvements to the Clavain agent lifecycle and completion protocol.

## Execution Log

### 1. Universal Completion Protocol (Clavain-8xs)

```
bd create --title="Add universal completion protocol: atomic rename + run scoping" --type=task --priority=0
```

- **Result:** Created successfully as `Clavain-8xs`
- **Priority:** P0
- **Status:** open

### 2. Retry/Stub Race Guard (Clavain-r5t)

```
bd create --title="Guard agent lifecycle: re-check before retry/stub, never overwrite non-stub" --type=task --priority=0
```

- **Result:** Created successfully as `Clavain-r5t`
- **Priority:** P0
- **Status:** open

### 3. Foreground Retry Timeout (Clavain-563)

```
bd create --title="Add timeout to foreground retry in Step 2.3 (5 min cap)" --type=task --priority=0
```

- **Result:** Created successfully as `Clavain-563`
- **Priority:** P0
- **Status:** open

## Verification

`bd list` confirmed all three P0 tasks appear at the top of the issue list:

```
○ Clavain-563 [● P0] [task] - Add timeout to foreground retry in Step 2.3 (5 min cap)
○ Clavain-r5t [● P0] [task] - Guard agent lifecycle: re-check before retry/stub, never overwrite non-stub
○ Clavain-8xs [● P0] [task] - Add universal completion protocol: atomic rename + run scoping
○ Clavain-amz [● P1] [task] - Template Step 3.5 synthesis report with same rigor as agent prompt template
○ Clavain-690 [● P1] [task] - Surface per-agent completion ticks during 3-5 min wait
○ Clavain-27u [● P2] [feature] - Replace YAML frontmatter with rigid markdown Findings Index + central findings.json
```

## Notes

- All three issues were created without descriptions. The `bd` tool warned about this but proceeded.
- The `beads.role` is not configured for this project (warning on each create). Running `bd init` would resolve this.
- Total open P0 tasks is now 3; total open issues is 6.
