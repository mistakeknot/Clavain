---
name: wayfind
description: Chart or work a decision map in beads for an effort whose destination is known but whose route spans many sessions
argument-hint: "[\"loose idea\" to chart a new map, or <map-id> to work one ticket]"
disable-model-invocation: true
---

# Wayfind

Plan an effort whose destination you can name but whose route you can't yet
see. A map is a beads epic of decision tickets. Each session charts the map or
resolves one ticket, then stops. Wayfind never builds anything: a cleared map
goes to `/clavain:strategy`.

Adapted from the wayfinder skill in mattpocock/skills (MIT License, Copyright
(c) 2026 Matt Pocock). The mechanism is `scripts/wayfind.py`; this command is
the loop that uses it.

```bash
WAYFIND="${CLAUDE_PLUGIN_ROOT}/scripts/wayfind.py"
```

<BEHAVIORAL-RULES>
1. **The owner sets the targets.** Destination, Out of scope and any
   permission to build change only through the owner's answer: a live reply,
   a decision-card pick or a recorded ruling, cited as `--source`. Never edit
   them yourself, and never read a Notes line as permission to execute.
2. **Questions go out in batches.** Grilling sends one round at a time,
   holding only questions that don't depend on each other, each with options
   and a recommendation. If the owner is present, ask in the thread. If not,
   send the round as one escalation through the project's usual channel.
3. **One HITL ticket per map at a time.** Grilling and prototype tickets run
   one after another; `wayfind ready` holds the rest. Research and task
   tickets may run in parallel.
4. **The owner picks prototype variants.** An agent's choice is a
   recommendation, never the resolution.
5. **Chart near, keep the rest as fog.** Create only tickets on the frontier
   now or one hop from it. Leave everything else under Not yet specified.
6. **Reverse with a revisit ticket.** Never edit a closed ticket. Open a
   `revisit` ticket, block the affected work on it, and resolve it with
   `--supersedes`.
</BEHAVIORAL-RULES>

## Pick the mode

- An argument that is a bead ID labelled `wayfinder:map`: **work mode**.
- Anything else: **chart mode**.
- No argument: run `bd list --label wayfinder:map` and ask which map to work.

## Chart mode

1. **Fix the destination.** Grill until the destination is one bounded
   sentence ("a spec for X", not "V1 of X"), plus what is out of scope. The
   owner's answer is the source.
2. **Check for fog.** If every question can be answered in this session, say so
   and hand off to `/clavain:brainstorm` or `/clavain:strategy` instead.
3. **Write the spec.** List frontier tickets (types: `grilling`, `prototype`,
   `research`, `task`), with `blocked_by` keys, and add the rest as fog.
   Size each ticket to one session.
4. **Chart.**
   ```bash
   python3 "$WAYFIND" chart --title "<short>" --destination-file dest.md \
     --out-of-scope-file oos.md --source "<where the owner set it>" \
     --tickets spec.json --dry-run
   ```
   Drop `--dry-run` once the plan looks right. Past seven open tickets the
   command refuses; keep the extras as fog.
5. **Start research.** Dispatch each research ticket through packaged
   `dispatch.sh --role scout` with `reasons: ["unresolved-success-criteria"]`.
   Findings go to `docs/research/<map-id>/<ticket-id>.md`.
6. **Stop.** Report the map ID and `wayfind lint` output.

## Work mode

1. **Check the map.** Run `python3 "$WAYFIND" lint <map>`. Exit 1 means a rule
   is broken: fix it or report it. Exit 3 is a divergence alarm: report it to
   the owner and stop.
2. **Claim one ticket** with `python3 "$WAYFIND" ready <map> --claim`. If the
   frontier is empty, report what blocks it and stop.
3. **Resolve it by type:**
   - `grilling`: send the round (rule 2). Resolve only on the owner's answer.
   - `prototype`: build the variants somewhere disposable, present them, and
     wait for the owner's pick.
   - `research`: read the findings, or dispatch the research and stop.
   - `task`: do the manual step that unblocks a decision.
   - `revisit`: grill the reversal like a grilling ticket.
4. **Record it.**
   ```bash
   python3 "$WAYFIND" resolve <ticket> --answer-file answer.md \
     --summary "<one line>" [--source "<owner's answer>"] [--supersedes <old>]
   ```
   Use `--invalidated` when the question no longer applies.
5. **Graduate fog.** For each fog item the answer made precise, add a ticket
   with `chart --map <map> --tickets next.json`, listing the item under
   `graduate`. Close out-of-scope items; they never graduate.
6. **Stop.** One ticket per session, except research.

## Exit

When `wayfind lint` reports `cleared`, run `/clavain:strategy <map-id>`. It
reads the closed decision tickets as its brainstorm input. `/clavain:campaign`
refuses map epics, because decision tickets are not build work.
