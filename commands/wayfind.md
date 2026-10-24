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

Every subcommand exits 0 on success, 1 when a map rule refuses the request
or `lint` finds an error, 2 on a usage error, a bad spec or a bd failure, and
3 when `lint` raises a divergence alarm.

`wayfind` enforces some rules and the rules below only guide others. It
enforces: targets change only with `--source`; HITL tickets (grilling,
prototype, revisit) close only with `--source`; a revisit closes only with
`--supersedes` naming a resolved decision of the same map; a blocked ticket
cannot close; `chart` refuses past the open-ticket cap; `ready` hands out one
HITL ticket per map at a time, because whoever claims one also claims the map
epic itself as a lease. `resolve` frees the lease only when the holder runs
it; if another session resolves the ticket, the holder's next `ready` reuses
the lease. Batching questions, keeping fog far, and leaving prototype picks to
the owner are on you.

Decisions live on the tickets, not in the map body: `resolve` posts a
resolution record as a comment on the ticket it closes, and
`wayfind lint <map> --json` lists them under `decisions`. Only `chart` writes
the map body. `chart` and `resolve` hold an exclusive lock on the map (a
file in the private 0700 directory `~/.local/state/clavain-wayfind`, the same
whatever XDG variables a process sees, never in the repository), so wayfind
writes to one map take turns and a rule such as the bet cap holds under
concurrency; a write that waits over five minutes, or finds the lock directory or file
owned by someone else or open to writes, fails with exit 2. Creating a map
also takes the new map's lock before it adds tickets and rechecks the cap
under it. A bd
write made outside wayfind is not locked: `chart` rereads the body before
writing and checks the write afterwards, so that is detected, not prevented:
rerun the chart that reports it. The `--source` checks detect an edit made
without a cited source; they do not authenticate the source.

<BEHAVIORAL-RULES>
1. **The owner sets the targets.** Destination, Out of scope and any
   permission to build change only through the owner's answer: a live reply,
   a decision-card pick or a recorded ruling, cited as `--source`. Never edit
   them yourself, and never read a Notes line as permission to execute.
2. **Questions go out in batches.** Grilling sends one round at a time,
   holding only questions that don't depend on each other, each with options
   and a recommendation. If the owner is present, ask in the thread. If not,
   send the round as one escalation through the project's usual channel.
3. **One HITL ticket per map at a time.** Grilling, prototype and revisit
   tickets run one after another; `wayfind ready` holds the rest. Research
   and task tickets may run in parallel.
4. **The owner picks prototype variants.** An agent's choice is a
   recommendation, never the resolution.
5. **Chart near, keep the rest as fog.** Create only tickets on the frontier
   now or one hop from it. Leave everything else under Not yet specified.
6. **Reverse with a revisit ticket.** Never edit a closed ticket. Open a
   `revisit` ticket, block the affected work on it, and resolve it with the
   owner's answer as `--source` and `--supersedes <old ticket>`.
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
5. **Start research.** Dispatch only the research tickets listed in the
   `frontier` of `python3 "$WAYFIND" ready <map> --json`; a blocked research
   ticket waits. Use packaged `dispatch.sh --role scout` with
   `reasons: ["unresolved-success-criteria"]`. Findings go to
   `docs/research/<map-id>/<ticket-id>.md`.
6. **Stop.** Report the map ID and `wayfind lint` output.

## Work mode

1. **Check the map.** Run `python3 "$WAYFIND" lint <map>`. Exit 1 means a rule
   is broken: fix it or report it. Exit 3 is a divergence alarm: report it to
   the owner and stop.
2. **Claim one ticket** with `python3 "$WAYFIND" ready <map> --claim`. If you
   already hold a ticket on the map (a crashed session, say), it resumes that
   one instead. If the frontier is empty or the claim is held, report what
   blocks it and stop. To free a ticket someone abandoned, run
   `bd update <ticket> --status open --assignee ""`; free an abandoned map
   lease (lint warns about it) the same way with the map ID. bd lets the same
   actor claim twice, so parallel sessions need distinct `--actor` names.
3. **Resolve it by type:**
   - `grilling`: send the round (rule 2). Resolve only on the owner's answer.
   - `prototype`: build the variants somewhere disposable, present them, and
     wait for the owner's pick.
   - `research`: read the findings, or dispatch the research and stop.
   - `task`: do the manual step that unblocks a decision.
   - `revisit`: grill the reversal like a grilling ticket; the owner's
     answer is the source.
4. **Record it.**
   ```bash
   python3 "$WAYFIND" resolve <ticket> --answer-file answer.md \
     --summary "<one line>" [--source "<owner's answer>"] [--supersedes <old>]
   ```
   `--source` is required for grilling, prototype and revisit tickets, and
   `--supersedes` for a revisit. Use `--invalidated` when the question no
   longer applies. If `resolve` fails part way, rerun it with the same
   arguments: it finishes the missing steps and refuses a different answer,
   summary, source or `--supersedes`. To change a recorded decision, open a
   revisit ticket.
5. **Graduate fog.** For each fog item the answer made precise, add a ticket
   with `chart --map <map> --tickets next.json`, listing the item under
   `graduate`. Close out-of-scope items; they never graduate.
6. **Stop.** One ticket per session, except research.

## Exit

When `wayfind lint` reports `cleared`, run `/clavain:strategy <map-id>`. It
reads the closed decision tickets and their resolution records as its
brainstorm input. `/clavain:campaign`
refuses map epics, because decision tickets are not build work.
