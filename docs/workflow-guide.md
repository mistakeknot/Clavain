# Workflow guide

## Workflow

For simple requests, `/sprint add user export feature` orchestrates the full lifecycle: brainstorm, plan, review the plan with multiple subagents, implement, review the implementation, resolve issues, and run quality gates. The human focuses on the usual suspects: product strategy, user pain points, and finding new [leverage points](https://donellameadows.org/archives/leverage-points-places-to-intervene-in-a-system/).

For **new projects** (or existing projects you want to bring into the ecosystem), start with `/project-onboard`: it introspects the repo, asks a few questions, then sets up beads tracking, CLAUDE.md/AGENTS.md, docs structure, observability, and seeds initial content via interpath. After that, `/sprint` handles the development lifecycle.

For more complex endeavors, each piece works standalone. The following review of the `/sprint` lifecycle provides a brief explanation of all the different parts of Clavain:

### The `/sprint` lifecycle

The current [sprint command](../commands/sprint.md) defines ten phases:
brainstorm → strategy → write plan → plan review → execute → test → quality
gates → resolve → reflect → ship. It runs these in order and stops at approval
checkpoints or failures. Each phase writes artifacts that later phases can inspect.

The original lifecycle description used standalone commands to explain the same
work: `/brainstorm` articulates requirements and user journeys; `/strategy`
structures a PRD and tracking beads; `/write-plan` produces an implementation
plan; `/work` executes it; `/interflux:flux-drive` reviews relevant artifacts;
`/clavain:clavain-review` reviews code; `/resolve` handles findings; and
`/quality-gates` checks readiness before shipping. Optional interserve mode
routes implementation to Codex instead of local execution. See the current
command definition for the exact sequence rather than treating this list as a
second sprint algorithm.

### Auto-proceed authorization

By default every irreversible op — `bd close`, `git push`, `bash .beads/push.sh`, `ic publish --patch` — prompts for confirmation. Inside a vetted `/clavain:work` or `/clavain:sprint` flow that's redundant friction; the discipline already ran tests, review, and quality gates. The auto-proceed authz layer lets those vetted ops proceed without a prompt, logs every decision to a per-project audit table, and keeps `confirm` as the floor for everything else.

**Install (one-time):**

```bash
mkdir -p ~/.clavain
cp /path/to/Clavain/config/policy.yaml.example ~/.clavain/policy.yaml
```

**Run a sprint as usual.** `/clavain:sprint` persists vetting signals (`vetted_at`, `vetted_sha`, `tests_passed`, `sprint_or_work_flow`) as bead labels after tests and after quality gates pass. At ship time the gate wrappers read those signals and proceed automatically when the policy's `requires` block is satisfied.

**Inspect decisions:**

```bash
clavain-cli policy list                # effective merged policy + sha256 hash
clavain-cli policy audit --since=1d    # recent auto/confirmed/blocked decisions
clavain-cli policy explain bead-close --bead=iv-xyz
clavain-cli policy lint                # spec invariants + gate-coverage check
clavain-cli policy doctor --require-signer --project-root="$PWD"
```

Spec: `canon/policy-merge.md` (merge order, allow_override, mode floors) and `canon/authz-cross-project-consistency.md` (cross-repo op semantics). Wrappers live in `scripts/gates/`; the `.clavain/gates/` registry declares which ops have wrappers so `policy lint` can flag any gate without a matching rule.

#### Signing audit records (v1.5)

Every gate wrapper records and signs one exact authorization row with Ed25519 before running the irreversible operation, so audit failure cannot produce an unaudited side effect. `policy audit --verify` checks every signed row plus the schema-36 legacy anchor against the project pubkey and exits non-zero on any mismatch.

**One-time bootstrap on the canonical signer:**

```bash
bash /path/to/Clavain/scripts/authz-init.sh
```

That script preflights an established ledger before migration, installs `~/.clavain/policy.yaml` from the example if absent, and generates `.clavain/keys/authz-project.{key,pub}` (mode 0400 / 0444) only when neither half exists. Only a DB created by that invocation gets its fresh migration markers bulk-signed; a signed empty legacy manifest is created only after preflight proves the legacy set is empty. It never repairs or auto-anchors established unsigned history: bootstrap stops and prints the read-only inspection command so an operator can review the exact count and digest first. A public-only checkout is treated as a verifier and is never overwritten with a new identity.

For Sylveste, run the signing bootstrap only on the canonical signing host. The canonical signing host is the sole canonical signer and owns the writable authorization ledger. Mac is verifier-only and receives the committed public key, signed legacy manifest, and signed DB snapshot; verify that snapshot with `clavain-cli policy doctor --project-root="$PWD"` and `clavain-cli policy audit --verify --project-root="$PWD"`.

For a reviewed nonempty migration, inspect first, compare the proposal independently on signer and verifier snapshots, then create the artifact once on the canonical signing host with the exact values:

```bash
clavain-cli policy anchor-legacy --inspect --project-root="$PWD"
clavain-cli policy anchor-legacy --expect-count=<n> --expect-digest=<sha256> --project-root="$PWD"
```

**Day-to-day:**

```bash
clavain-cli policy audit --verify            # walk + verify every row; exit 1 on any failure
clavain-cli policy verify --json             # same, emits per-row JSON report
clavain-cli policy doctor --require-signer   # DB/schema/keypair preflight
clavain-cli policy quarantine --before-key=<fp> --reason="..."  # record key-compromise event
```

The private key is never committed. In the Sylveste topology it remains on the canonical signing host and must not be copied to Mac until real ledger replication with a single canonical write path or a remote signer exists. The pubkey (`.clavain/keys/authz-project.pub`) and signed manifest (`.clavain/keys/authz-legacy-manifest.json`) are committed so every verifier agrees on the identity and exact legacy set. The gate wrappers pin one `CLAVAIN_AUTHZ_PROJECT_ROOT` for check, token, record, and sign operations. Any signer-required operation initiated on Mac must be handed off to the canonical signing host and executed against its canonical checkout and ledger; do not satisfy the gate with a local fallback DB or a second private-key copy.

`policy rotate-key` refuses retained signed history because normal verification currently loads only the active public key and rows do not store a signer key ID. Rotation remains available only before the first signature; retained histories require a multi-key verification migration or an explicit re-signing procedure.

Trust claim is **tamper-evident-post-write**, not tamper-proof: an attacker who can invoke the gate CLI with the key readable can forge signatures. Detection works against direct-SQL mutations, backup tampering, and history-rewrite attempts by anyone who cannot invoke the CLI. Full model: `canon/authz-signing-trust-model.md`. Payload spec: `canon/authz-signing-payload.md`.

### Reviewing things with `/flux-drive`

`/flux-drive`, named after the [Flux Review](https://read.fluxcollective.org/), is the most versatile standalone command. You can point it at a file, a plan, or an entire repo and it determines which reviewer agents are relevant for the given context. It selects from three categories of review agents:

- **Project Agents**: Per-project `fd-*.md` agents that live in your repo and know your specific codebase (bootstrapped via Codex when interserve mode is active)
- **Plugin Agents**: Built-in reviewer agents that auto-detect project docs: when CLAUDE.md/AGENTS.md exist, they provide codebase-aware analysis; otherwise they fall back to general best practices
- **Cross-AI (Oracle)**: model-diverse perspective on complex decisions

It only launches what's relevant. A simple markdown doc might get 2 agents; a full repo review might get 8. The agents run in parallel in the background, and you get a synthesized report with findings prioritized by severity. Over time, flux-drive builds a knowledge layer from review findings: patterns discovered in one review are injected as context into future reviews.

When Oracle is part of the review, `flux-drive` chains into the **interpeer stack**: comparing what Claude-based agents found against what the Oracle lane found, flagging disagreements, and optionally escalating critical decisions to a full multi-model council.

### Cross-Agent review with `/interpeer`

Different models and agents genuinely see different things, and the disagreements between them are often more valuable than what either finds alone. Cross-agent review with `/interpeer` is especially valuable after a `flux-drive` run.

The `/interpeer` stack escalates in depth:

| Mode | What it does | Speed |
|------|-------------|-------|
| `/interpeer` | Quick Claude↔Codex second opinion | Seconds |
| `/interpeer deep` | Oracle analysis with prompt optimization and human review | Minutes |
| `/interpeer council` | Full LLM Council: multi-model consensus | Slow |
| `/interpeer mine` | Post-processor: turns disagreements into tests and specs | N/A |

`/interpeer` defaults to quick mode: it auto-detects whether you're running in Claude Code or Codex CLI and calls the other one. For deeper analysis, `deep` mode builds optimized prompts for Oracle and shows you the enhanced prompt before sending. `council` mode runs a full multi-model review when the stakes are high: critical architecture or security decisions where you want genuine consensus, not just one model's opinion.

`mine` mode is particularly useful for complex, ambiguous contexts. It takes the *disagreements* between models and converts them into concrete artifacts: tests that would prove one side right, spec clarifications that would resolve ambiguity, and stakeholder questions that surface hidden assumptions.

### Token efficiency with `/interserve`

Because Codex CLI has far higher usage limits than Claude Code, `/interserve` lets Claude orchestrate while Codex does the heavy lifting. Claude reads, plans, and writes detailed prompts: then dispatches to Codex agents for implementation. Claude crafts a megaprompt, dispatches it, reads the verdict from Codex, and decides if it's acceptable. Claude plays the tech lead, Codex plays the engineering team.

For multi-task work, `/interserve` parallelizes naturally. Five independent changes get five Codex agents dispatched simultaneously. Claude collects the results and commits.

### Structured debate

`/debate` runs a structured 2-round argument between Claude and Codex before implementing a complex task. Each writes an independent position, then responds to the other's. If they fundamentally disagree on architecture or security, Oracle gets called in as a tiebreaker. The output is a synthesis with clear options for you to choose from.

Worth running before any architectural decision with genuine uncertainty. The debate itself costs less than building the wrong thing.
