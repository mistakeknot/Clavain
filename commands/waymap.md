---
name: waymap
description: Chart or work a project's Now / Next / Later roadmap in beads, as bets the coordinator commits, defers or drops
argument-hint: "[\"loose idea\" to chart the project's roadmap, or <roadmap-id> to work one ticket]"
disable-model-invocation: true
---

# Waymap

Keep a project's roadmap as a few bets rather than a dated plan. A roadmap is a
wayfind map of the `roadmap` kind: a beads epic whose tickets are bets and the
research behind them. Each session charts the roadmap or resolves one ticket,
then stops. Waymap never builds anything: a committed bet's work is opened as
children of the bet and run by `/clavain:campaign`, `/clavain:strategy` or a
`/clavain:wayfind` map.

The mechanism is `scripts/wayfind.py`, the same engine as `/clavain:wayfind`.
Read `commands/wayfind.md` for the subcommand exit codes, the lease and the
`--source` checks; this command only adds what the roadmap kind changes.

```bash
WAYFIND="${CLAUDE_PLUGIN_ROOT}/scripts/wayfind.py"
```

## The shape

- **One roadmap per project**, labelled `wayfinder:roadmap`. Projects can share
  one beads database (Aleph, Undersketch and Yaoirioware share the hub), so a
  roadmap also carries `waymap:project:<name>`, set by `chart --project NAME`,
  and `chart` refuses a second open roadmap for the same project. Other
  projects' roadmaps in the same database do not count. A roadmap with no
  project label (charted before scoping) counts against no project: `lint`
  warns, and `adopt-roadmap` (below) labels it.
- **Destination** is one horizon sentence and is the owner's alone. Out of
  scope is the owner's too.
- **Horizons, no dates.** A committed bet carries `waymap:now` or
  `waymap:next`. **Later is fog**: it lives under Not yet specified and is never
  charted as tickets.
- **Seven committed bets at most across Now and Next.** `resolve` refuses an
  eighth commit and `lint` errors if a roadmap is over the cap. A bet frees its
  slot when it is superseded or delivered (it has children and all are closed).
- **A bet is HITL** and resolves to `commit` (with a horizon), `defer` or `drop`.
  A deferred or dropped bet holds no slot and no horizon.
- **A bet's work is its direct children.** Open the work with
  `bd create "<title>" --parent <bet-id>`. `lint` warns when a Now bet has no
  open child.
- `docs/roadmap.md` is generated from the roadmap and the bead progress. Never
  edit it by hand.

`wayfind` enforces: targets change only with `--source`; a bet closes only with
`--source` and `--decision`; a commit needs `--horizon`; the cap; and every rule
`/clavain:wayfind` enforces. Who may decide is on you.

<BEHAVIORAL-RULES>
1. **The coordinator owns routine bets.** Committing, deferring or dropping a
   bet within the destination is the coordinator's call. Cite the basis as
   `--source` (the plan, the evidence, the ruling it follows); the check records
   a source, it does not authenticate one.
2. **The owner decides the rest.** Changes to the Destination or Out of scope,
   a bet that crosses projects, spends money, launches something or changes a
   production destination go to the owner as a decision card. Cite the owner's
   answer as `--source`. Never edit the targets yourself.
3. **Owner questions are batched for a card.** Collect the questions a session
   raises into one decision card, each with options and a recommendation. Never
   leave a question in the thread as the way to ask, and never send one thread
   ask per question.
4. **One HITL ticket per roadmap at a time.** Bets, and revisits, run one after
   another; `wayfind ready` holds the rest. Research and task tickets may run in
   parallel.
5. **Keep Later as fog.** Do not chart a bet you cannot yet name a first child
   for. Chart bets only for Now and Next candidates.
6. **Reverse with a revisit ticket.** Never edit a closed bet. Open a `revisit`
   ticket and resolve it with `--supersedes <bet>`; commit a replacement bet if
   the work continues.
7. **Never hand-edit `docs/roadmap.md`.** Change the roadmap, then render.
</BEHAVIORAL-RULES>

## Pick the mode

- An argument that is a bead ID labelled `wayfinder:roadmap`: **work mode**.
- Anything else: **chart mode**.
- No argument: run
  `bd list --label wayfinder:roadmap --label waymap:project:<project>` for the
  project you are working (the name `chart --project` used). One result is the
  roadmap to work; none means chart mode. Never take a roadmap from the
  unfiltered label: in a shared database it may be another project's.

## Chart mode

1. **Fix the destination.** One horizon sentence and what is out of scope. If
   the owner is not present, put the question on a decision card and stop.
2. **List the candidate bets** for Now and Next as `bet` tickets, plus any
   `research` tickets that decide them. Everything else is fog.
3. **Chart.**
   ```bash
   python3 "$WAYFIND" chart --kind roadmap --project <project> --title "<project> roadmap" \
     --destination "<one sentence>" --out-of-scope-file oos.md \
     --source "<where the owner set it>" --tickets spec.json --dry-run
   ```
   `--project` is required for a roadmap (a short lower-case name such as
   `aleph`; there is no default, since the working directory cannot tell
   which project a shared database is serving). Drop `--dry-run` once the plan
   looks right. Past seven open tickets the command refuses; keep the extras
   as fog. A second roadmap for the same project exits 1.
4. **Stop.** Report the roadmap ID and `wayfind lint` output.

### Adopt a roadmap charted before project scoping

```bash
python3 "$WAYFIND" adopt-roadmap <roadmap> --project <project> [--dry-run]
```

This adds `waymap:project:<project>` to the roadmap and to every ticket under
it, and is safe to rerun. It refuses a roadmap that already belongs to another
project, a plain map, and a project that already has an open roadmap. Other
projects then chart their own with `chart --project`.

## Work mode

1. **Check the roadmap.** Run `python3 "$WAYFIND" lint <roadmap>`. Exit 1 means
   a rule is broken: fix it or report it. Exit 3 is a divergence alarm: report
   it to the owner on a decision card and stop.
2. **Claim one ticket** with `python3 "$WAYFIND" ready <roadmap> --claim`. If the
   frontier is empty or the claim is held, report what blocks it and stop.
3. **Resolve it by type:**
   - `bet`: weigh it against the Destination and the cap. Decide it under rule 1
     or rule 2.
   - `research`: read the findings, or dispatch the research and stop.
   - `task`: do the manual step that unblocks a bet.
   - `revisit`: reverse an earlier decision under rule 6.
4. **Record it.**
   ```bash
   python3 "$WAYFIND" resolve <ticket> --answer-file answer.md \
     --summary "<one line>" --source "<basis>" \
     [--decision commit|defer|drop] [--horizon now|next] [--supersedes <old>]
   ```
   For a bet, `--decision` is required and a commit needs `--horizon`. A failed
   `resolve` can be rerun with the same arguments.
5. **Open the work.** For a committed Now bet, create its first child
   (`bd create "<title>" --parent <bet>`) so Now has a live child. Do not start
   the work in this session.
6. **Render.**
   ```bash
   python3 "$WAYFIND" render <roadmap>
   ```
   This writes `docs/roadmap.md` under the current directory. To run against
   another project directory, put `-C` before the subcommand
   (`python3 "$WAYFIND" -C <dir> render <roadmap>`); after the subcommand it is
   refused. Commit the file with the change that moved the roadmap.
   `render --check` exits 1 when the file is stale, and `--stdout` prints it
   instead.
7. **Stop.** One ticket per session, except research.

## Exit

A roadmap never clears: it is the project's standing plan. Retire it by closing
the epic when the owner ends the effort.
