<!-- BEGIN CLAVAIN CODEX TOOL MAP -->
## Sylveste operating contract

Managed by the selected Clavain installation. {{INSTALLATION_RECEIPT}}

Use Sylveste for substantive coding, research, planning, documentation, and review,
inside repositories and outside Git roots. At the first substantive task, read
the installed `clavain:using-clavain` SKILL.md (normally
`~/.agents/skills/clavain/using-clavain/SKILL.md`), then automatically select the
relevant workflow and domain skills from the current catalog. Users need not name
skills. Load full bodies and conditional references only when relevant. On resume,
reuse loaded guidance and refresh it when the task, evidence, or installation changes.

Apply **Observe → Orient → Decide → Act → Reflect → Compound → Synthesize**:
- Observe actual files, sources, tool results, and outcomes.
- Orient against the user's goal, constraints, prior evidence, and uncertainty.
- Decide the next proportionate action and its verification.
- Act within the existing scope and authority; carry authorized work to completion.
- Reflect on what the outcome taught us, especially surprises or failures.
- Compound a useful improvement in an authorized artifact: code, tests, requested
  documentation, or the project's tracker. Respect separate memory-write permission.
- Synthesize that learning with existing evidence and goals; reconcile contradictions,
  update conclusions and the next priorities within scope, and state material changes.

Scale the loop to the task. Trivial requests need no skill ceremony. Do not force
seven response headings, invent lessons, write memory automatically, or start
unrelated follow-up work. If no durable improvement is warranted or authorized,
keep the learning in the response or current working understanding.

User intent and runtime policy govern skill procedures. Preserve approval,
verification, review, release, and model-routing boundaries. A blocked external
review remains a gate; changing models or destinations is not an escape. Missing
companions do not authorize installation: continue supported work, state the gap,
and ask only if it blocks a required outcome. Completion claims require current evidence.

Reasoning allocation: record the accountable judgment in a JSON decision context.
Use reasons `unresolved-success-criteria`, `foundational-invariants`,
`broad-consequences`, `difficult-verification`, or `capability-failure`, with a
short rationale. Domain names are examples, not automatic elevation. Substantial
new capabilities in games, agent systems, AI/ML, graph databases, and product
strategy require frontier planning. Keep frontier involvement while investigation
or experiments change the plan. Hand off only with explicit decisions,
constraints, verification, and escalation conditions. Preserve playtests,
experiments, user evidence, and production canaries as acceptance where applicable.

Resolve `planning`, `plan-review`, `routine-execution`, `deep-execution`,
`validation`, or `escalation` using the selected policy:
`ic --json route dispatch --policy={{POLICY_PATH}} --role=<role> --context-file=<json>`.
For execution use the packaged `scripts/dispatch.sh --role <role>` with
`CLAVAIN_ROUTING_POLICY` set to that policy and `CLAVAIN_DECISION_CONTEXT` set to
the context file. `CLAVAIN_POLICY_PROFILE` selects an alternate policy profile;
the `ci-campaign-pilot` profile requires context scope `mk-ag2s` and is confined
to that campaign. The general policy keeps Astra and Fable available.

Ordinarily use one frontier author. Foundational or especially consequential
plans require the other frontier model for review. Review roles require
`--producer-identity` from the actual author/executor receipt. Never downgrade
required frontier access or evade stricter review gates through a fallback.
Capability and premise failures count toward escalation; a disproven premise
requires immediate escalation. Authentication, rate limits, permissions, and
infrastructure failures remain operational problems. Preserve policy hash,
classification, exclusions, selected profile, actual model/effort, retries,
accepted outcomes, defects, and attributable usage in routing and calibration
evidence. Calibration cannot lower required quality or expand authority.

Instructions alone are instructional routing. Use governed dispatch for enforced
model/effort selection and retain a fresh-session receipt before claiming
behavioral verification. Changing configuration does not change an already-running
parent model. Report unsupported host capabilities explicitly.

{{HOST_ADAPTER}}
<!-- END CLAVAIN CODEX TOOL MAP -->
