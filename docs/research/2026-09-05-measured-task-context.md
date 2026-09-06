# Measured task-context checkpoint results

Keep the existing context policy. These three internal-tooling pairs do not
establish the 20% savings target or justify a general switch to fresh sessions.
Fresh assessments improved two diagnoses but missed relevant companion evidence,
and their token and time results were mixed. This is an assessment experiment,
not a completed whole-task delivery or Astra promotion decision.

## Quality and resource changes

Positive percentages mean the fresh arm used more than the retained arm.
Total input includes cached input. Output includes its reasoning subset; do not
add reasoning tokens a second time. These are native token measures, not Codex
subscription charges or a claim about money saved.

| Objective | Blinded quality judgment, then unblinded | Total input | Uncached input | Output | Native assessment time |
| --- | --- | ---: | ---: | ---: | ---: |
| Installer repair | Fresh diagnosis modestly ahead; both require the same core repairs | +45.2% | -65.1% | +20.5% | +31.3% |
| Complete companion rollout | Tie; both miss relevant defects found by the other | -25.7% | +79.3% | +14.5% | +3.7% |
| Task attribution | Fresh clearly ahead; retained findings are a subset | +101.2% | +21.6% | +155.0% | +122.0% |

All six assessments correctly returned NEEDS REPAIR. The independent Fable
review confirmed the substantive findings by static source tracing. It rated
one installer item as a weak blocker and some companion inconsistencies as
latent rather than active failures. It could not execute reproductions under
its tool permissions, so its conclusions do not constitute an independent test
run or task acceptance.

For the attribution checkpoint, fresh found eight groups of defects; retained
found three of those. The missed issues included transferring usage between
tasks and dropping recorded failed attempts from coverage. For companions, the
retained arm found the plugin/project root conflict and more compact-file path
residues; fresh found the artifact generator's contradictory canonical paths.
Neither companion report alone was sufficient for the complete repair.

## Native usage

The [six assessment rows as CSV](2026-09-05-measured-task-context.csv) contain
only aggregate measurements and coverage labels.

| Objective | Arm | Requests | Uncached input | Cached input | Output | Reasoning subset | Seconds | Native tool calls |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Installer | Retained | 7 | 267,514 | 440,576 | 8,926 | 1,636 | 310.983 | 5 |
| Installer | Fresh | 13 | 93,425 | 934,528 | 10,757 | 4,169 | 408.418 | 12 |
| Companions | Retained | 11 | 62,993 | 1,901,824 | 8,029 | 4,053 | 359.470 | 10 |
| Companions | Fresh | 17 | 112,933 | 1,346,560 | 9,190 | 3,546 | 372.766 | 16 |
| Attribution | Retained | 13 | 176,848 | 1,797,888 | 7,492 | 3,734 | 342.815 | 12 |
| Attribution | Fresh | 28 | 214,984 | 3,757,824 | 19,106 | 10,598 | 760.886 | 27 |

The retained installer total includes a compaction request with 235,899 input
and 3,930 output tokens. Omitting it changes the comparison materially. Each
selected turn reconciles request records with native cumulative usage and the
exact immutable parent prefix for retained-history forks.

Seven setup or failed-attempt rows remain in the private accounting table. One unfinished
fresh installer attempt records 12 requests, 915,019 input tokens and 7,367 output
tokens as a lower bound. Other setup gaps are unknown, not zero. These rows are
excluded from the successful-arm table above but retained in the cohort evidence.

## Comparability and coverage

The three objectives were prospectively enrolled before implementation dispatch
as an internal-tooling cohort. At each checkpoint, the source, factual handoff,
prompt and parent history were frozen. Actual `codex fork` sessions retained
history; fresh sessions received the identical assessment prompt. Installer ran
fresh then retained; companions and attribution ran retained then fresh. Outputs
were sealed before randomized A/B evaluation. The quality verdict was sealed
before opening the blinding key and combining quality with usage.

All pairs used CLI 0.153.4, GPT-6 Astra at xhigh, the default service tier,
workspace-write/on-request permissions, and matching recorded configuration,
instructions and 112-entry effective skill catalogs. Installed configuration
stayed frozen within each pair. Exact serialized tool-schema arrays were not
available, so that part of parity is not demonstrated directly.

Native request coverage for the six selected turns is complete. Task-attribution
coverage remains incomplete: the assessment harness lacks canonical dispatcher
attempt identities, some setup logs are absent, and original coordinator/worker
binary and configuration identities have known gaps. Root integration and repair
turns span objectives and are counted once under `cohort_shared`, without invented
per-task allocations. Dedicated existing Autarch/Flere work receives no retroactive
enrollment credit.

Reread counts and isolated integration-turn totals are unavailable. Tool-call
counts are not reread counts; persisted call/output spans are not CPU time.
Human active minutes require an explicit estimate and remain unknown. Approval
waits do not establish human effort. Pricing coverage, execution completion and
independent task acceptance remain separate from native usage coverage. There
is no complete cohort cost or delivered-work savings claim.

## Evidence and disposition

The published [aggregate CSV](2026-09-05-measured-task-context.csv) accompanies
this report. Supporting evidence remains in private local experiment artifacts
outside this repository: the complete per-arm accounting table, methodology,
verification and hash seals; the three checkpoint seals; and the sealed
independent quality review. These are local evidence references, not repository
paths or publicly accessible downloads. Raw native transcripts and the blinding
key are not included in this publication.

Source corrections and their independent reviews are tracked separately from
these six frozen assessments. Producer publication, consumer installation and
the full human Autarch journey have their own completion gates.

Retain the existing context policy and Astra canary gates. Three tooling
assessments cannot establish broad superiority or whole-task savings. The result
does support using an additional fresh assessment when its chance of finding
missed defects warrants the extra work, while preserving relevant retained
evidence and measuring correction burden.
