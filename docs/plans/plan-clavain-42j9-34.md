---
artifact_type: plan
bead: mk-42j9.34
stage: design
---
## Fix-round changelog

- F1: Steps 4–5 make packet activation explicit, enumerate migrated verdict paths and preserved callers, and require unchanged-argv regressions.
- F2: Step 2 explicitly keeps main-session-authored deliverables on the existing non-packet path; no producer identity or receipt is inferred.
- F3: Steps 4–6 scope out SDD's existing `review-package`, mark baseline provenance unconfirmed, and assign deferred gate deduplication to the coordinator.
- F4: Step 6 starts with a pre-implementation cache-write attribution measurement and makes packet-only cost savings conditional on its result.
- .29 status: The prerequisite now names the unmerged `mk-42j9-29-33-scorecard` branch and the required rebase or merge-first action.

# Standard review packets: implementation plan

**Goal:** Give each fresh plan or pre-landing reviewer complete, bounded,
traceable evidence without the author's transcript. Assemble once per
deliverable revision, reuse across dispatch attempts, and measure whether the
smaller context reduces review cost without losing findings.

**Scope:** Planning only. No implementation, independent approval, empirical
acceptance, commit, push, or publication is implied by this document. Implement
sequentially with `clavain:executing-plans` after independent other-frontier plan
review; the changes share dispatch state and do not benefit from parallel edits.

**Spec and precedents:** mk-42j9.34 and the mk-42j9.33 simplicity ruling supplied
in the task; mk-42j9.29 attribution contract; `/tmp/laneC/astra-review/packet.md`;
`docs/canon/reasoning-routing-dispatch-receipt.json`;
`docs/canon/reasoning-routing-review-receipt.json`. Preserve the example's
acceptance criteria, prior-finding dispositions, focused asks, attachment index,
and bounded fix/delta-review contract. The existing packet is a shape precedent,
not approval of this implementation.

**Architecture:** Add one Python standard-library builder with a typed JSON
input and a Markdown output plus a small integrity manifest. `dispatch.sh`
prepares or verifies that packet only on explicit `--review-input` or
`--review-packet` opt-in, before resolving/executing candidates. Step 5 names
the verdict callers that must opt in within this bead's scope. It delivers the same packet bytes to every
attempt and adds its identity to the existing dispatch audit context.

## Decision context and observed prerequisites

The supplied governed planning decision selects `planning-astra`,
`gpt-6-astra`, `xhigh`, policy profile `default`, with `other-frontier` review.
The selected policy's locally verified SHA256 is
`8d393bf24b6218f1d182eb29f89200faf82e434eeac269751f23c6b2fd98e257`.
Retain the enclosing dispatch's actual producer receipt for review; this
decision record is not a substitute execution receipt.

```json
{
  "reasons": ["foundational-invariants"],
  "rationale": "The default evidence boundary for gated reviews must preserve complete deliverable coverage, executed producer attribution, and independent other-frontier review. A packet omission or identity error can degrade every downstream review.",
  "investigation_active": true
}
```

Inspected base: branch `mk-42j9-34-review-packet`, commit
`04bd7a45378cf3097f87a176f0bddb957100b123`.

- `scripts/dispatch.sh` checks `PLAN_FILE` readability and adds its directory to
  Claude's read roots. It does **not** currently put that file into `PROMPT`.
  `_dispatch_role_profile()` recurses before normal prompt assembly;
  `_run_candidate_with_policy()` can retry the recursive child. Assembly must
  therefore happen in the outer invocation, not inside a backend or retry loop.
- `_role_audit_context()` in `scripts/lib-dispatch-audit.sh` contains the native
  executed-profile evidence. Its current `profile_ref:$route.profile_ref` can
  describe the requested primary while `resolved_profile` describes the executed
  fallback. Do not select a producer from that top-level field.
- **Integration prerequisite requiring coordinator resolution:** this base
  does not contain the brief's mk-42j9.29 `DISPATCH_BEAD_ID_CALLER_EXPORTED`,
  `BEAD_SOURCE`, or dispatch `--bead` handling. The .29 commits
  `cdaa910..17eef4e` exist on `mk-42j9-29-33-scorecard`, not in this worktree's
  HEAD or `main` (`37d10ad`); they are **not landed**. Before implementation,
  the coordinator must rebase this branch onto `mk-42j9-29-33-scorecard`, or
  wait for that branch to merge to `main` and rebase onto the merged base.
  Preserve .29's env/flag/interstat precedence and tests. Do not implement a
  competing attribution mechanism here. This remains a hard prerequisite and
  a disproven checkout premise, escalated in this handoff, not permission to
  redesign .29 or silently assume it is present.
- GitHub repository-ID lookup failed because the API was unreachable; zklw CI
  status failed because the host did not resolve. `bd-hub` is absent, so tracker
  prime/read and the scorecard bead identity could not be verified. These are
  outstanding prerequisites, not evidence of CI migration or tracker completion.

## Acceptance Criteria

Every packet has the fixed sections defined below. Missing required evidence
fails assembly; an explicit `UNRUN` explanation is evidence of missing tests,
never a passing test. No probabilistic selection, model summarizer, statistical
gate, new metrics service, transcript ingestion, or automatic review loop.

Acceptance requires builder integration for `plan-review` and `validation`,
fresh reviewer independence through the existing resolver, and a manual A/B
exercise on at least ten real deliverables. Preserve `dual_review_reasons` and
the required Astra cross-lab review for applicable Claude-produced work. A
capacity substitute remains provisional under existing policy; a packet cannot
waive a stricter requirement. Any escaped defect, or any new P0/P1 finding
attributed to this change, triggers immediate review or rollback. These gates
cannot be waived; cost and other aggregate trends remain advisory.

The baseline supplied by mk is 15 autosigil spec-reviewer Opus sessions, median
$0.49, range $0.29–$1.03. Target median is approximately $0.30 at the same
finding rate. These are supplied measurements and a target, not results of this
planning session. Unknown cost or quality evidence cannot establish acceptance.

## Numbered implementation steps

### 1. Define and test the deterministic builder interface

**Files:** create `scripts/build-review-packet.py`,
`scripts/review-packet-preamble.md`, `tests/shell/test_build_review_packet.bats`,
and `tests/shell/review_packet_helper.bash`. Use temporary fixture repositories
and fake external commands as in `test_calibration_session_end_receipt.bats`;
no model or live tracker calls in tests.

**Tests first:** `packet contains every required section`, `plan packet records
tests unrun explicitly`, `missing criteria or producer evidence fails without
publishing`, `same inputs produce identical bytes`, and `multiple repositories
and beads remain distinguishable`. Assert actual content, source hashes, stdout
path, and failure behavior, not just headings.

**CLI and interfaces:**

- `python3 scripts/build-review-packet.py --input INPUT.json --output-dir DIR`
  prints only the absolute `DIR/<packet_id>/packet.md` path on success. Diagnostics
  go to stderr. Exit 2 means invalid/incomplete input; exit 1 means I/O/tool
  failure. The builder never runs tests, calls a model, or queries session logs.
- `python3 scripts/build-review-packet.py --verify PACKET.md` validates the
  sibling manifest and packet/attachment hashes without rebuilding or querying
  the tracker. It prints the same path on success. It returns no verdict.
- Add `load_input(path) -> dict`, `validate_input(spec) -> None`,
  `build_packet(spec, output_dir) -> Path`, and `verify_packet(path) -> dict`.
  Reject unknown schema versions, unknown keys, duplicate bead IDs, conflicting
  inputs, unreadable/nonregular files, and empty required values.

`INPUT.json` schema version 1 has these exact fields:

| Field | Contract |
|---|---|
| `schema_version` | Integer `1`. |
| `kind` | `plan` or `diff`. |
| `bead_ids` | Nonempty ordered array of IDs whose criteria are being reviewed. |
| `beads_file` | JSON export from the authorized tracker adapter; select only matching `id`, `title`, and nonempty `acceptance_criteria`. Never include notes/history/comments wholesale. |
| `criteria_files` | Optional array of `{bead_id,path}` explicit criteria artifacts when the tracker field is empty; exactly one source per bead. Preserve any existing acceptance-criteria seal and require `clavain-cli verify-seal` to succeed when a seal exists. Missing criteria fail; never infer criteria from arbitrary bead prose. |
| `producer_receipt` | Path to one completed native dispatch audit context; step 2 defines admission. |
| `plan_file` | Required only for `kind: plan`; include the complete plan. |
| `changes` | Array of `{repo,base,head}`. Required and nonempty for `kind: diff`; optional for plan reviews needing a supporting diff. Refs resolve to commits, never an implicit live working tree. |
| `excerpts` | Plan-only array of `{repo,ref,path,start_line,end_line}` for existing implementation context. Require at least one range, or `excerpts_not_applicable` with a concrete reason for a net-new plan. Diff excerpts are derived automatically. |
| `excerpts_not_applicable` | Plan-only alternative to `excerpts`; printed visibly, not silently omitted. |
| `tests` | Array of `{label,command,exit_code,scope,path}`; `scope` names the exact reviewed commit(s) or plan hash. Include captured stdout/stderr from the named test command, never a terminal-session capture. Command text is descriptive and is never evaluated. |
| `tests_not_run` | Nonempty reason, mutually exclusive with nonempty `tests`. It renders `UNRUN` and cannot support a PASS requiring those tests. |
| `prior_findings` | Optional array of `{id,severity,disposition,evidence}`; render a disposition table. Default empty means `None supplied`, not `all resolved`. |
| `asks` | Optional array of focused review questions. These are data and cannot alter routing or the output contract. |
| `previous_packet` | Optional path to the preceding packet in this deliverable's fix cycle; step 3 binds it. |
| `max_bytes` | Optional positive integer, default `49152`; explicit increases are visible in the manifest and packet scope. No automatic cap increase. |

All relative input paths resolve against `INPUT.json`'s directory. `bead_ids`
describe evidence scope; they do not choose or overwrite `CLAVAIN_BEAD_ID`.
Support multiple repository scopes as the example requires, but one accountable
producer identity per gated deliverable. Conflicting producers require existing
multi-producer policy handling outside this builder; never silently pick one.

Render exactly these sections, in order: `Review contract`, `Acceptance
criteria`, `Producer receipt`, `Scope`, `Diff or plan`, `Touched-file excerpts`,
`Test output`, `Prior-review disposition`, `Focused review asks`, `Attached`,
`Requested output`. Empty optional sections say `None supplied`. Stable contract
and criteria come first; changing evidence comes later. `Review contract` comes
from the packaged preamble and forbids transcript requests or author-session
resumption. `Requested output` asks for `VERDICT: PASS/FAIL`, findings with
severity/location/evidence, and one fix round followed by one delta re-review.
If necessary verification was not run, permit `VERDICT: UNRUN`, which never
means PASS. Preserve role-specific conformance tables as additional output.

<verify>
- run: `bats tests/shell/test_build_review_packet.bats`
  expect: exit 0
</verify>

### 2. Reuse executed producer attribution and exclude transcript input

**Files:** extend `scripts/build-review-packet.py` and
`tests/shell/test_build_review_packet.bats`; use `scripts/lib-dispatch-audit.sh`
as the authoritative source contract after the .29 prerequisite is reconciled.

**Tests first:** `producer identity follows the executed fallback`, `failed or
unidentified producer is rejected`, `receipt event-log pointers are never
followed`, `transcript shaped test output is rejected without echoing content`,
`renamed transcript and symlink to a session log are rejected`, and `ordinary
test diagnostics mentioning assistant are accepted`. Include Claude JSONL,
Codex JSONL, a messages-array export, and a Markdown conversation fixture.

Add `load_producer_receipt(path) -> dict` and
`reject_transcript_input(path, content) -> None`. Accept the completed native
audit context exported from `ic --json route list --dispatch=<id>`'s
`context_json`, selecting an explicit successful terminal `attempt_id`, not
the first/latest arbitrary record. Require `state: completed`, `terminal: true`,
`result.exit_code: 0`, nonblank dispatch/attempt IDs, policy hash, and actual
`resolved_profile.profile` plus `execution.backend/model`. Use
`ic --json route identity --model=<identity>` for canonical comparison; never
duplicate alias normalization. Fail on identity disagreements. The review's
producer is this receipt's executed model, not a nested `producer_model` naming
the author of an earlier reviewed artifact, and not the requested profile.

**Main-session scope decision:** plans/diffs authored directly in an interactive
main session have no completed native dispatch receipt. They remain on the
existing **non-packet** review path and are out of scope for this bead's packet
admission and mandatory migration. `commands/plan-review.md`'s
`$PLAN_AUTHOR_MODEL` and `commands/quality-gates.md`'s `$EXECUTOR_MODEL` may
continue serving their current routing contract, but neither is a producer
receipt. Never infer an identity, fabricate an `ic` record, or relabel a session
declaration as executed evidence. Preserve existing independent-review and
identity checks on that path; unknown identity remains unknown. Test both
main-session callers without packet flags and with their original prompt/plan
arguments. An explicit packet opt-in without an admissible native receipt
fails closed; a missing/invalid receipt for a declared native-dispatch producer
must not be reclassified as main-session authorship to escape that failure.

**Representation decision:** embed a small allowlisted projection using the
original native field names, accompanied by the original receipt's SHA256 and
dispatch/attempt IDs. Include `resolved_profile.profile_ref`,
`resolved_profile.profile.{backend,model,model_identity,reasoning_effort}`,
`execution.{backend,model,reasoning_effort}`, `resolved_route.{policy_hash,
classification_reasons,review_requirement,policy_profile}`, `bead_id`,
`checkout`, `state`, and terminal result status. Keep unknown observed effort
unknown. Preserve .29's authoritative bead/source fields in audit records.

Do not embed the entire receipt, follow `execution.event_log`, or copy provider
events into the packet. Those events may contain the transcript. The supplied
canon JSON files are examples of probe/review receipts, not a second producer
receipt API: their `producer_model` and `resolved_model` describe different
actors. A hash-bound projection avoids both identity inversion and duplicating
large usage arrays. Retain the original in the existing attribution store;
the bundle carries the safe projection and original hash, not a raw log copy.

Guard every text source before rendering, including plan, criteria, Git content,
test output, asks, and dispositions. Resolve symlinks and reject known author
session directories (`.claude/projects`, `.codex/sessions`) and raw provider
event/usage-log inputs regardless of filename. Detect parsed conversation
envelopes (`messages` with role/content, Claude user/assistant events, Codex
`response_item` message/reasoning events) and paired anchored conversation
markers (`Human:`/`Assistant:`, `User:`/`Assistant:`, role XML/chat delimiters).
Scan the complete input before applying size limits; reject rather than strip,
because stripping can turn failing evidence into apparent success. Diagnostics
identify the source and rule without printing the rejected text.

The realistic accident is passing a terminal tee/provider JSONL as a test log,
or attaching a session export as "context". The typed allowlist, forbidden
sources, envelope checks, and absence of ambient session discovery address
that accident. They cannot prove that arbitrary unmarked prose was never
copied from a conversation. State that limit; no regex-based claim of perfect
semantic transcript detection and no `--allow-transcript` escape hatch.

<verify>
- run: `bats tests/shell/test_build_review_packet.bats`
  expect: exit 0
</verify>

### 3. Bind complete changes, bounded excerpts, and immutable reuse

**Files:** extend `scripts/build-review-packet.py`,
`tests/shell/test_build_review_packet.bats`, and `tests/shell/review_packet_helper.bash`.
Store generated bundles beneath existing ignored `.clavain/reviews/packets/`;
do not add a second ledger or modify `.gitignore`.

**Tests first:** `context excludes distant unchanged code`, `all changed lines
survive`, `add delete rename and mode changes retain scope`, `binary or submodule
changes fail explicitly`, `oversize evidence is never silently truncated`,
`tampered packet or attachment fails verification`, `branch movement changes
packet identity`, `retry reuses the exact bundle`, and `delta binds its parent
and cannot masquerade as full review`.

Add `collect_changes(changes) -> list`, `collect_excerpts(changes, ranges) -> list`,
`render_packet(evidence) -> bytes`, and `publish_packet(evidence, output_dir) -> Path`.

- Resolve refs with `git rev-parse --verify <ref>^{commit}`. Use argv arrays,
  reject option-like refs, disable external diff/textconv, and use NUL-delimited
  name/status enumeration. Generate a complete `git diff --no-ext-diff
  --no-textconv --no-color --no-renames --unified=0 BASE HEAD --` for each scope.
  Deliberately represent renames as deletion/addition to avoid similarity
  heuristics. Include every file, mode change, and changed line; never select
  only the "important" hunks or apply an extension filter.
- For each zero-context hunk, obtain source from `git show COMMIT:PATH`; emit
  the eight unchanged lines before and after the hunk, with commit/path/line
  labels. Use the base side for deletions, head side for additions, and both
  sides where surrounding text differs. Merge overlapping ranges, omit changed
  lines already present in the complete diff, and sort by scope/path/line. A
  wholly new/deleted file is fully present in the diff; label that fact rather
  than repeating its contents. Plan ranges are exact, limited to 80 lines each,
  from explicit immutable refs; reject out-of-range requests.
- Do not traverse symlink blobs. Record their target text as changed content.
  Reject binary/submodule changes as unsupported evidence with named paths;
  require an explicit separately reviewed evidence contract before extending
  v1 to them. Never pass a text-only packet off as a complete review of those
  changes. Require clean tracked state when the reviewer is expected to replay
  tests at a scope's `head`; a mismatch is an error, not an implicit diff source.
- Count final UTF-8 packet bytes, including metadata. Default limit is 48 KiB.
  Exceeding it fails before publishing or dispatch. Print per-section byte
  counts so the operator can remove duplicated context or explicitly increase
  `max_bytes` while retaining the entire scope. Never truncate a plan, criterion,
  failing log, or changed line to hit a cost target. Test command/exit status and
  exact scope are always visible; supplied output remains evidence to verify,
  not proof that the builder executed the command.
- Canonicalize an identity manifest containing builder schema/preamble hash,
  kind, ordered bead/criteria hashes, resolved commit IDs, excerpt ranges, test
  metadata/hashes, producer receipt hash/attempt ID, asks/dispositions, parent
  packet ID, and byte limit. Exclude session IDs of the reviewer, timestamps,
  output locations, and absolute host paths from the identity calculation.
  `packet_id` is its SHA256. Write `packet.md`, `manifest.json`, and the exact
  sanitized evidence files into a temporary sibling directory, then publish
  atomically. `manifest.json` includes `packet_id`, `packet_sha256`,
  `packet_bytes`, `inputs`, `producer_identity`, and `attachments` with relative
  paths/hashes. Reject escaping paths/symlinks during verification. Identical
  input returns the verified existing path without changing file contents or
  mtimes; a corrupted existing bundle fails instead of being overwritten.
- This is artifact reuse, not verdict caching. A corrected deliverable produces
  a new packet. `previous_packet` verifies the parent and fixes the original
  full-review scope; for diff re-review each new base must equal its parent's
  reviewed head, every prior scope must be carried forward, and the new packet
  shows the fix delta plus all prior-finding dispositions. For plan re-review,
  include the revised complete plan and identify its parent hash. A changed
  criterion, producer, or newly expanded scope requires a fresh full review,
  not a purported delta approval. The coordinator composes the original review
  and delta verdict; this builder never marks the final combined tree approved.

<verify>
- run: `bats tests/shell/test_build_review_packet.bats`
  expect: exit 0
</verify>

### 4. Make explicit packet opt-in the review dispatch boundary

**Files:** modify `scripts/dispatch.sh` and `scripts/lib-dispatch-audit.sh`;
create `tests/shell/dispatch_review_packet.bats`; extend
`tests/shell/dispatch_claude_seat.bats`, which already covers `--plan` readability
and Claude `--add-dir`. `dispatch_parser.bats` tests JSONL events, not plan input.

**Tests first:** `packet opt-in requires complete evidence before backend start`,
`plan flag cannot bypass opted-in packet validation`, `packet reaches Claude stdin and
Codex prompt exactly once`, `fallback and pool retry reuse one packet`,
`producer flag mismatch fails before resolution`, `resolved child verifies
packet without rebuilding`, `context gateway cannot expand review evidence`,
`audit records bind each attempt to the packet`, `review roles without packet
flags retain their existing argv and prompt behavior`, and `nonreview plan
behavior is unchanged`. Use real packet fixtures and fake `ic`/backends; count
builder build invocations and compare hashes across attempts. Exercise each
unmigrated caller named in step 5, not just a generic nonreview role.

Add `REVIEW_INPUT`, `REVIEW_PACKET`, and `REVIEW_PACKET_JSON`; CLI flags
`--review-input FILE` and `--review-packet FILE`, with both separated and equals
forms. Add `_dispatch_prepare_review_packet()` and
`_dispatch_verify_review_packet()`. Activate **only** when the caller passes
`--review-input` or `--review-packet`; role names alone never activate packet
mode. Permit opt-in for `plan-review`, `validation`, and `cross-lab-review`;
reject packet flags on unsupported roles. Without either flag, preserve the
existing `--plan`, `--prompt-file`, `--template`, and positional-prompt path
on all roles, including these three. Do not infer opt-in from a model name,
legacy `--tier`, producer identity, or the presence of a plan.

In packet mode, the outer invocation must supply exactly one of `--review-input`
for automatic build or `--review-packet` for explicit reuse. Reject conflicting
packet flags and an additional `--plan`; explain that a raw plan belongs in
`INPUT.json.plan_file`. A bare `--plan` remains a legacy input, never a packet
alias. Mandatory adoption is enforced at the specific eligible verdict call
sites in step 5, not by rejecting every non-packet review dispatch.

For opted-in calls, prepare after argument parsing and .29 bead attribution, before the outer
`_dispatch_role_profile()` call and before its missing-producer check. Set
`PRODUCER_IDENTITY` from the verified receipt; if the caller supplied it,
canonicalize through `ic route identity` and require equality. Do not override
the decision context, policy selection/hash/profile, resolver exclusions,
reviewer order, effort floors, or capacity-substitute rules. Require an explicit
nonblank decision context for the gated review. Packet metadata is not allowed
to downgrade its reasons.

Only in packet mode, filter `--review-input` and `--review-packet` from
`ROLE_PASSTHROUGH`; add exactly one canonical `--review-packet` path and set
`PLAN_FILE` to that path in the resolved child. `_run_candidate_with_policy()`
receives those same arguments on every pool/fallback attempt. Each child
verifies hashes once before backend execution; it never reassembles, rereads a
live bead, or changes packet content. Explicit `--role-resolved` cannot bypass
this verification. Dry-run performs the same input checks but runs no model.

For opted-in packet calls, assemble `PROMPT` from the verified packet bytes even
when no positional prompt exists. Reject positional prompts, `--prompt-file`,
`--template`, `--inject-docs`, images, and arbitrary backend passthrough that
could append context or resume an author session. Migrate focused questions to
`asks`. Skip `_apply_context_gateway()` for verified packets so tldrs does not
append another ad hoc context packet. Keep the selected governed contract and
resolved route delivery, existing sandbox/read-root behavior, Claude user-setting
exclusion, and mutation detection. Do not advertise filesystem confinement:
this change prevents automatic transcript delivery, not every possible file
read by an already-authorized reviewer tool.

In `_role_audit_context()`, add only `review_packet: {packet_id,sha256,path,
kind,previous_packet_id,producer_receipt_sha256}` when present. Retain all
existing .29 attribution, lifecycle, usage, policy, and executed-profile fields.
Set this before `started` is recorded, and persist it unchanged at termination.
No packet content is copied into the audit store. Existing records without the
field remain readable. This field binds attempts to evidence; it is not a new
producer receipt or approval record.

Gate scheduling remains the coordinator's responsibility. The intended packet
workflow is one full review per deliverable, then the allowed delta review;
retrying capacity is not a new gate. A second required cross-lab reviewer
consumes the same packet as part of that gate. Step 3 enforces artifact reuse
by content identity, **not once-per-deliverable review admission**. Automated
gate deduplication is deferred, owned by the mk-42j9.34 coordinator, who must
record its follow-up/disposition in the existing tracker before claiming a
scheduling saving. Do not claim this builder eliminates per-session reviews.
Do not introduce SessionStart/SessionEnd hooks or suppress a genuinely
requested fresh review because a prior PASS exists. The packet's one-fix plus
one-delta contract does not replace SDD's out-of-scope five-round contract.

<verify>
- run: `bats tests/shell/test_build_review_packet.bats tests/shell/dispatch_review_packet.bats tests/shell/dispatch_claude_seat.bats`
  expect: exit 0
- run: `bash -n scripts/dispatch.sh scripts/lib-dispatch-audit.sh`
  expect: exit 0
</verify>

### 5. Migrate consumers and exercise actual routing invariants

**Files:** update governed invocation guidance in `commands/plan-review.md`,
`commands/quality-gates.md`, and `docs/canon/reasoning-routing-operations.md`.
Add opted-in fixture cases in `tests/routing/role-dispatch-test.sh`,
`tests/routing/role-dispatch-integration-test.sh`,
`tests/routing/plan-review-capacity-test.sh`,
`tests/routing/validation-sol-fallback-test.sh`,
`tests/shell/dispatch_claude_settings.bats`, and
`tests/shell/dispatch_codex_uv_no_sync.bats` using the shared packet helper;
retain their non-packet compatibility cases. Add focused assertions to
`tests/routing/reasoning-contract-test.sh` and
`tests/structural/test_orchestrate_pattern_f.py`.

**Mandatory packet callers:** after the shadow acceptance exercise, require
explicit opt-in at these verdict boundaries for native-dispatch-authored
deliverables with the completed producer receipt from step 2:

- `commands/plan-review.md:80`: the independent plan verdict uses
  `--review-input`; the parallel lens reviewers retain their current prompts.
- `commands/quality-gates.md`, Phase 2b: the conformance verdict uses
  `--review-input`/`--review-packet` when reviewing an explicitly selected,
  committed deliverable. Require the checkout to match the declared reviewed
  head, with no tracked or untracked review-scope changes, before and after
  validation; bind tests and results to that head. The existing live-working-tree
  invocation at line 223 stays on its current non-packet path. Do not silently
  substitute HEAD for dirty/uncommitted work, auto-commit it, or change what the
  live validator judges. Commit-bound packet validation is a distinct documented
  path, not a transparent replacement for live-tree conformance.
- `docs/canon/reasoning-routing-operations.md`: the required cross-lab verdict
  accompanying either eligible gated path uses `--role cross-lab-review
  --review-packet` with the **same** packet, producer, and scope. This requirement
  does not apply to unrelated invocations of the same role.

Main-session-authored deliverables remain non-packet under step 2 even at these
call sites. Invalid/missing required native evidence blocks the eligible packet
path instead of silently falling back. Tests must show each eligible verdict
caller emits a packet flag and each explicit exception retains its old argv.

**Unmigrated callers and regression coverage:** in
`tests/shell/dispatch_review_packet.bats`, capture and replay each caller's
existing argv against fake backends with neither packet flag; assert unchanged
prompt/template and plan/read-root delivery, zero builder calls, and no new
producer-receipt requirement. Cover each of the following, including the
main-session plan-review and conformance exceptions above:

- Pattern F `scripts/orchestrate.py:2669`: preserve `--role validation
  --producer-identity P --plan PLAN -C WORKTREE --prompt-file PROMPT -o REPORT`,
  including tool-applied plans without a producer dispatch receipt. Keep its
  `VERDICT`/`CRITERION`/`RECEIPT`/`BEYOND THE GAUGE` parser contract; assert the
  unchanged argv and parsed result in `test_orchestrate_pattern_f.py` too.
  `skills/executing-plans/references/pattern-f-contracts.md:58` stays unchanged.
- `skills/subagent-driven-development/SKILL.md:60–61`: task validation and
  re-review retain their current prompt/package arguments and up to five fix
  rounds; the dispatcher must not inject the packet output/stopping contract.
- Companion interflux `skills/flux-engine/phases/launch-codex.md:94–104`:
  preserve each parallel validation lens's `--template`/`--prompt-file` persona
  argv and rendered prompt. Capture representative actual calls in local
  fixtures; no companion choreography or repository edits are in scope.
- `commands/quality-gates.md:223`: preserve the live-working-tree prompt and
  its current arguments, including a dirty-tree fixture proving dispatch does
  not require commit refs or assemble a packet. Assert the current criterion
  table and `CONFORMANCE` contract as well as backend invocation.

**Existing packager:** `skills/subagent-driven-development/scripts/review-package`
already assembles per-task commits, stat, and a `-U10` diff. It and SDD's
review cadence remain out of scope: this bead migrates the named deliverable
verdicts, not per-task reviews with a different stopping contract. Do not replace
that script or create a second SDD package. If the baseline turns out to be SDD,
its cost population cannot establish savings for these migrated paths (step 6).

**Tests first:** a real-policy plan-review rejects the producer as reviewer;
a `dual_review_reasons` context retains `other-frontier` requirements;
Claude-produced foundational work still requires its eligible Astra reviewer;
a capacity walk never creates or approves a new packet; and the existing .29
env/`--bead`/interstat provenance cases remain unchanged. Preserve all original
routing/seat assertions and legacy inputs, adding valid packet inputs only to
opted-in cases. Do not get tests
green by skipping missing packet checks or replacing the real policy with a
permissive mock. Inventory other callers with a role-call search; add an
unchanged-argv case for each unmigrated caller rather than forcing migration.
Tests must also reject bad packets without retrying through the legacy path.

Document two canonical calls: `dispatch.sh --role plan-review --review-input
INPUT.json ...` and `dispatch.sh --role validation --review-packet PACKET.md ...`,
using the same selected policy/context. Explain tracker export through `bd-hub`
on Clavain and the authorized hub tracker on zklw; never fall back to the fenced
tracker. Reuse sealed acceptance criteria and the existing producer receipt
export. Preserve `CONFORMANCE: PASS/FAIL` and criterion tables in quality-gates
output in addition to `VERDICT`; do not replace its existing receipt/identity
checks with packet validity. Update only the governed-review boundary, not the
companion review-pool choreography or routing policy.

After focused red/green cycles, run the routing scripts named below and the
repository shell/structural suites. Establish failures on the reconciled base
before attributing regressions; the old example packet's baseline failures are
historical, not an exemption for this branch. Recheck immutable GitHub ID and
zklw fleet status when available. Use the registered zklw checks; add no GitHub
Actions dependency. Leave CI prerequisites outstanding if unavailable.

<verify>
- run: `bash tests/routing/role-dispatch-test.sh`
  expect: exit 0
- run: `bash tests/routing/role-dispatch-integration-test.sh`
  expect: exit 0
- run: `bash tests/routing/plan-review-capacity-test.sh`
  expect: exit 0
- run: `bash tests/routing/validation-sol-fallback-test.sh`
  expect: exit 0
- run: `bash tests/routing/reasoning-contract-test.sh`
  expect: exit 0
- run: `bash tests/run-tests.sh`
  expect: exit 0
</verify>

### 6. Run the manual cost/finding comparison and retain hard quality gates

**Pre-implementation measurement — run before building anything in steps 1–5:**
the dispatch path used by the supplied 15 autosigil spec-reviewer sessions is
**unconfirmed**. Recover their existing session/dispatch/attempt IDs and join
the retained usage rows and invocation metadata to identify whether each used
SDD `review-package`, a plan verdict, conformance, or another path. Do not assume
the label "spec-reviewer" means one of the migrated verdicts. Record the caller
path per row; leave unavailable provenance unknown. If the population is SDD,
report it separately and establish a baseline for the actual in-scope verdict
paths before attributing savings to this builder.

For each of those 15 rows, split the reported `cache_creation_input_tokens`
between review evidence and the fixed harness prefix (system prompt, tools,
CLAUDE.md), using the existing usage data and retained input/cache-block
metadata. Report evidence bytes and harness-prefix bytes alongside their
attributed cache-write token counts, total provider USD, and any residual or
unknown component. Aggregate usage alone does not identify those components:
use available block accounting/boundaries, label estimates or bounds explicitly,
and do not equate byte fractions with exact token fractions. If retained inputs
or attribution are unavailable, mark the split unconfirmed and keep the cost
claim unproven. This is operator-side measurement, never transcript attachment
to a reviewer or new usage infrastructure.

If the fixed prefix dominates cache writes, packet-size reduction alone cannot
be claimed to reach approximately $0.30: downgrade the cost claim to **"packet
size is one contributing factor, not sufficient on its own"** pending the
measurement and a supported cost breakdown. Keep that qualification while the
split is unknown as well. Eight-line excerpts versus SDD's existing `-U10`
context are only a small reduction, not evidence of a large saving. Preserve
the acceptance target; do not present it as a forecast or alter harness/provider
settings in this bead. Record the measurement and its limitations in the
one-time results artifact below before implementation starts.

**Files/artifacts:** document the procedure in
`docs/canon/reasoning-routing-operations.md`; put the one-time results in
`docs/research/review-packet-mk-42j9-34-ab.md` and link them from mk-42j9.34 and
the existing scorecard bead after its ID is recovered. Do not create a new
scorecard service, statistical engine, or per-session gate.

**Verification first:** before rollout, use the step-4 fake-backend test to
prove that retry receipts share a packet identity, changed deliverables do not,
and missing usage stays unknown. That verifies accounting joins only. It does
not satisfy the real-review acceptance exercise.

The proposed evidence-size reduction comes from complete small-context diffs plus eight-line
excerpts instead of full files, a compact receipt projection, no author
transcript/ambient docs/tldrs expansion, and the 48 KiB default bound. Keep the
preamble/criteria byte-stable across the initial and fix reviews, with volatile
evidence later. This offers cache reuse on the same provider/model; it does not
guarantee cache hits, especially with fresh sessions, different models, or
changed governed prefixes. Do not change provider settings, model, or effort
to manufacture a saving. A byte budget is not a token-price proof; the measured
prefix/evidence split above determines how much cost this mechanism can affect.

Use the next **ten distinct real deliverables** eligible for step 5's native-receipt,
packet-scope plan-review/validation paths
as paired manual A/B cases (at least twenty review executions). A is the
existing hand-assembled, transcript-free practice; B is the generated packet.
Both see the same deliverable, criteria, producer receipt, tests, reviewer model,
effort, policy, and available tools. Randomize/alternate which arm runs first,
use fresh independent sessions, and do not expose the other arm's findings.
Avoid extra fix rounds: adjudicate both outputs, then use the existing single
fix plus delta-review allowance. These A/B duplicates are a temporary rollout
exercise, not an added permanent gate per session. Until the comparison finishes,
keep the established review path authoritative; compare B in shadow, or run A
with the retained pre-change dispatcher under the same routing policy. After
acceptance, make opt-in mandatory at step 5's eligible verdict call sites;
do not add a packet-bypass flag there. The enumerated legacy callers and
main-session/live-tree exceptions keep their non-packet behavior.

Pull evidence from these **existing** sources:

- Native routing records: `ic --json route list --dispatch=<id>`;
  parse `context_json` for dispatch/attempt IDs, executed profile/model/effort,
  `bead_id`, `resolved_route.policy_hash`, `execution.event_log`, and
  `result.output_path`. The new `review_packet` field supplies only the join to B's
  evidence. Keep failed attempts and count their actual known cost.
- Normal Claude dispatch: the `execution.event_log` points to
  `<output>.provider-events.<id>.jsonl`, retained by `dispatch.sh`. Extract the
  final `type: result` event's `total_cost_usd` when present and its `usage`
  fields. For per-message accounting deduplicate by session plus provider
  message ID, as the canon receipts specify; do not sum repeated stream events
  or add final cumulative totals to their own constituents. Provider logs are
  read by the operator for accounting only, never attached to review packets.
- If the existing `CLAVAIN_REQUIRE_USAGE=1` path is used, use terminal
  `usage.cumulative` rows in `CLAVAIN_REVIEW_EVENTS` keyed by
  `dispatch_id`/`invocation_id`/`session_id`; require `complete: true` and take
  the final cumulative row, not their sum. `scripts/claude_usage.py` retains raw
  events at `<events>.<invocation_id>.raw.jsonl` for the final provider cost.
- Record existing token fields `input_tokens`, `output_tokens`,
  `cache_creation_input_tokens`, and `cache_read_input_tokens`; for Codex use
  `turn.completed.usage.{input_tokens,output_tokens,cached_input_tokens}` from
  its retained events. Codex tokens do not establish an Opus dollar comparison.
  Missing provider USD is `unknown` unless the existing scorecard already has
  an explicit, versioned conversion; invent no price table here.
- Findings come from each `result.output_path`, its `.verdict` sidecar, and
  existing conformance `.clavain/verdicts/plan-conformance.json.findings_count`
  where applicable. General reviews have no universal numeric finding count:
  manually adjudicate distinct valid defects, severity, duplicates, false
  positives, and escapes using the existing scorecard rules. Count findings
  across fix rounds once by defect; receipt example `nonblocking_findings`
  is not a complete all-severity count.

For each arm report median USD per initial review and total USD per accepted
deliverable including retries/delta review. Compare B's Opus median with paired
A; compare with the supplied $0.49 baseline only if its dispatch population is
confirmed comparable, otherwise label it separately. Report progress toward
approximately $0.30 without attributing fixed-prefix costs to evidence size.
Compare paired valid-finding sets and findings per deliverable, separating plan
from diff reviews and different models. Ten reviews with zero defects do not
prove equal detection. Record B-only/A-only misses and investigate them instead
of treating similar totals as proof. Keep acceptance pending if the scorecard,
source baseline, usage, or quality evidence is unavailable or inconclusive.

Apply the nonwaivable single-event triggers: an escaped defect or new P0/P1
attributed to packet omission, misattribution, or dispatch integration stops
promotion immediately for review or rollback. Other trends are advisory. Rollback
reverts the packet integration commit(s), restores the established manual
evidence path, and retains all packets/receipts/findings. It never disables
independent review, changes the routing policy, or discards failed evidence.

## Open questions for reviewer

- Is the proposed 48 KiB default with complete-diff overflow failure practical
  enough, or will frequent explicit increases erase the intended cost reduction?
- Does the executed-receipt projection match the unmerged .29 branch's shape and
  its exported-bead provenance? Complete the coordinator's rebase/merge-first
  prerequisite before coding.
- Scrutinize the explicit opt-in boundary and rejection of arbitrary prompts
  only inside packet mode. Are mandatory verdict callers and main-session,
  live-tree, Pattern F, SDD, and interflux exceptions covered by the migration
  and unchanged-argv fixtures, including the required cross-lab verdict?
- Are the transcript-envelope rules precise enough to catch accidental log
  attachment without blocking source tests that quote conversation fixtures?
  Unmarked pasted prose remains a caller-provenance limitation, not a solved
  detection problem.
- Confirm the existing scorecard bead, access to the 15 baseline rows, and the
  paired ten-deliverable exercise before spending on it. Does delta-scope
  composition retain every applicable original review and stricter cross-lab
  gate through the final reviewed head?

## Handoff and outstanding gates

This plan has been checked against the named local source paths and supplied
brief, but has not received independent approval. The coordinator must bind
this plan's hash to the enclosing actual Astra producer receipt and obtain the
required other-frontier plan review through the selected policy before code is
written. Use the established manual packet practice to review the builder's own
plan; do not depend on an unimplemented builder or self-review for admission.

Keep frontier involvement while resolving the attribution prerequisite, evidence
boundary, and review findings. Two demonstrated capability/criteria failures
require escalation; a disproven premise requires immediate escalation. Quota,
authentication, network, and missing-tool failures are operational, not capability
strikes. Implementation tests, fresh independently scheduled CI, actual independent
review, and the real A/B exercise remain outstanding. No release or landing
authority is granted by a successful packet build or by this planning handoff.
