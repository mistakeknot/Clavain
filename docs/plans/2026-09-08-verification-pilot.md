# Verification reliability pilot

Implements the independently reviewed user plan, tracked by `Sylveste-5ewg`.
Related work: `Sylveste-uo7b` (gauge/seat enforcement) and `sylveste-xoki.2`
(broader receipts) remain open. CI prerequisite: workspace `mk-ag2s.25`, immutable
repository `1151593132`. Lean startup (`sylveste-z55b`) follows this pilot.

## Contract

Extract the existing orchestrator verifier into a small runner and CLI. Preserve
`VerificationStep` and valid `<verify>` syntax. Validate the entire specification
before running anything: malformed or partial entries, duplicate identifiers,
unknown fields and unsupported expectations fail closed. `contains "text"`
requires exit zero and matching complete output; `exit N` permits deliberate
nonzero exits. No scheduler, central database, result cache, or automatic repair
of prerequisites is introduced.

Per-task manifests may declare required checks, paths, dependency revisions,
untracked inputs, executable identities, fixed-vector version probes, timeouts,
output limits and pytest JUnit count assertions. Defaults: 600 seconds and
64 MiB combined output per check. Explicit Bash uses `-e -o pipefail`, closed
stdin and bounded process-group cleanup. Operational errors cause no model
repair or capability strike; assertion failures retain bounded repair.

| Outcome | Pipeline |
|---|---|
| Checks pass | Independent review; machine evidence eligible |
| Completed assertion fails | Existing bounded repair loop |
| Timeout | Failed verification, operational timeout; stop |
| Contract, prerequisite, launch, persistence, containment, cancellation failure | UNVERIFIABLE, task error; no repair |
| Explicitly optional empty checks | Independent review, no machine acceptance or vetting |
| Required empty checks | Task error |

## Evidence

Use symlink-safe private directories outside source and declared dependency
trees. Persist complete output and hashes before atomically writing the receipt
and emitting `VerificationStep`. Include run/task/attempt, manifest hash,
command/expectation, timing, exit, artifact hashes and declared executable
inventory. Do not claim to observe every executable a shell invokes.

Fingerprint HEAD, index/staged state, tracked bytes/modes/symlink targets and
declared untracked inputs before and after checks, including dependencies.
Stable dirty work is allowed and recorded; changes invalidate evidence. Summary
is capped at 6,000 characters with failure excerpts and artifact references;
assertions use complete output. A named pytest JUnit parser requires one fresh,
consistent report, positive executed coverage and zero skips by default.

## Implementation and verification sequence

1. Write regression tests for false passes, contract rejection and prerequisites.
2. Implement runner, CLI, private evidence and source binding.
3. Exercise descendants, escaped descriptors, cancellation, oversized output,
   failed writes, stale/zero JUnit reports and source drift; preserve dirty work.
4. Obtain routing-worker ownership before editing `scripts/orchestrate.py`.
   Integrate structured outcomes; leave model-policy files untouched.
5. Run installed adapter on focused Clavain and isolated Beads transport tests
   on the Mac. Obtain independent QA; resolve required CI via `mk-ag2s.25`,
   preserving two fresh guests at one SHA and applicable live canary gates.
6. Publish observed output-size reduction, verification-related model turns,
   repairs, usage coverage and quality outcomes. API cost estimates do not
   measure subscription allowance. Unknown or negative efficiency stays explicit.

Receipts record what ran; independent review, required CI, live acceptance and
publication authority remain separate. Broader rollout, capability removal,
passing-result caching and lean startup implementation are outside this release.

**Alignment:** stronger evidence and fewer avoidable model repairs.
**Risk:** incomplete checks may appear authoritative; explicit coverage, source
binding and independent acceptance constrain that risk.
