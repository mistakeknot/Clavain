# Coverage

What the characterization suite pins, and what it does not. A row marked
"not covered" is deliberate; the reason is given, nothing is skipped silently.
Counts are the tests collected per module (230 in all; 229 run on current main, one applies to the older script only).

## Covered

| Behavior | Where | How it is pinned |
|----------|-------|------------------|
| Resolved backend, model, effort, tier, fallbacks, exclusions and floors for each of the 17 dispatch roles, for each reason set (none, each of the five reasons, all five) and each producer identity (none, Opus 5.5, Fable 5.2, OpenAI) | `test_role_resolution.py` (8) | Golden table `role_resolution.json`, keyed by policy sha256; both baseline and main tables recorded |
| Refusals from `ic route dispatch`: review roles without a producer identity, unknown role, unknown classification reason, the reserved `release-authority` role, missing policy file | `test_role_resolution.py`, `test_dispatch_args.py` (real-`ic` tests) | Exit code and message asserted |
| The role list itself | `test_role_resolution.py` | Pinned list; adding or removing a role fails |
| `roster-slugs.yaml` and `roster-families.yaml` as shipped: slug count, families, labs | `test_roster_config.py` (80) | Golden `roster_config.json` |
| Slug-to-family lookup, unmapped model, unknown slug (reported as a gap, not guessed), family identity mismatch, duplicate or provider-prefixed rows, waiver status rules, `ref` rows, `-latest` aliases | `test_roster_config.py` | Synthetic configs through `generate.py` functions |
| Shape validation errors and snapshot freshness | `test_roster_config.py` | Synthetic configs, exact problem text |
| `generate.py` command line: missing flags, missing routing file (exit 2), self-test | `test_roster_config.py` | Subprocess exit code and output |
| `fleet-registry.yaml` readers in `lib-fleet.sh`: list, get, by category/source/role, cost estimate, coverage check, orphaned agents, empty and missing registry | `test_roster_config.py` | Real script with a temp registry and the real registry |
| `route-spawn.sh` argument validation before any lookup | `test_roster_config.py` | Exit code and message |
| Contract renderer: output for each host and selection mode, placeholders, receipt line (`policy SHA256`, `contract SHA256`, package version), profile line, per-host and per-selection hashes | `test_contract_generator.py` (80) | Golden `contract_render.json` from fixed fixtures |
| Contract generator failures: unknown host, missing or malformed inputs, missing template, mutually exclusive policy flags, expected-hash mismatch | `test_contract_generator.py` | Exception type or exit code and message |
| A malformed policy still renders (it is only hashed) | `test_contract_generator.py` | Pinned as current behavior |
| Write, check and dry-run modes; marker handling (duplicates, legacy markers, symlinks, missing directory) | `test_contract_generator.py` | File effects and diff output |
| `check-instruction-contract.sh`: current, missing file, no receipt, version drift, policy drift, content drift, usage errors, renderer error | `test_contract_generator.py` | Exit codes 0/1/2 and drift codes |
| `dispatch.sh --role` argument handling: role validation, optional decision-context file, inline JSON refused, unreadable context, missing `ic`, bead-id charset, incompatible flags, help | `test_dispatch_args.py` (54) | Fake `ic`, `codex`, `claude` on PATH; exit code and message |
| What `dispatch.sh` hands to `ic` and to the seat: policy argument, role, context file, resolved model and effort, claude and codex command lines | `test_dispatch_args.py` | Fake CLIs record their arguments |
| Dispatch receipt: fields, producer and bead, one line per dispatch, failed model exit recorded with that code, started and terminal routing decisions | `test_dispatch_args.py` | JSONL read back; the expected shape (with or without `observed_*`/`usage_*`) is chosen from git history, not from the receipt |
| `--review-scratch` and `--repo` on a non-review role | `test_dispatch_args.py` | Refused (main) or warned and run (baseline), chosen from git history, not from the script text |
| The state files `dispatch.sh` leaves in `/tmp` and the environment it can see | `test_dispatch_args.py` | Asserted per run and deleted by pid; the deletion helper refuses a symlink, a non-regular file or one owned by another user, and its own tests use a temp directory, not `/tmp`; caller's `BASH_ENV`, `ENV`, `INTERBAND_LIB`, `PYTHONPATH`, `CLAVAIN_*` shown not to arrive |
| A shallow checkout when choosing baseline or main expectations | `test_dispatch_args.py` | Raises (does not guess or skip) naming `ORCHCOMPAT_DISPATCH_GEN`; tested with a simulated shallow boundary that cuts off an existing commit, a real `--depth 1` clone, hostile caller `GIT_DIR`, and the explicit override still working |
| The rig's own `git` calls (`git init` of the scratch repo, the ancestry check that picks baseline or main) | `test_dispatch_args.py` | Run with an allowlisted environment, system and global config off, empty template; a hostile caller `GIT_DIR`, `GIT_WORK_TREE`, `GIT_TEMPLATE_DIR`, `GIT_CONFIG_*` or `HOME` config changes neither the scratch repo nor the ancestry answer |
| `ic` answers for the policy that was passed | `test_role_resolution.py`, `test_policy_binding.py` (4) | Returned `policy_hash` equals the sha256 of the policy bytes before any row is compared |
| The strict gate | `test_gate.py` (3) | Child pytest with a PATH missing `yq` or `jq`: errors under `--orchcompat-require-ic`, announced in the header otherwise |
| `dispatch.sh --dry-run` output for every role and reason set | `test_dispatch_args.py` | Golden `dispatch_dry_run.json`, both policies |

## Not covered

| Behavior | Reason |
|----------|--------|
| `route-spawn.sh` resolution path (which seat is chosen once arguments pass) | Reads live pool state through `bb`; a faithful fake would restate the script. Only the argument validation is pinned. |
| A real model launch from `dispatch.sh`, seat output handling, streaming, timeouts | Launches a model; the fakes record arguments and exit. |
| Persisting a routing decision in the real `ic` state database | A real `ic` cannot persist it under a temp HOME; non-dry runs use the fake `ic`, and the real `ic` is exercised only by dry resolution. |
| `dispatch.sh` pool selection and headroom (`CLAVAIN_BB_DIRECT_POOL`, `CLAVAIN_POOL_HEADROOM`) | Depends on live account-pool state; switched off in the rig. |
| The context gateway (`CLAVAIN_CONTEXT_GATEWAY_MODE`) | Off in the rig; separate subsystem. |
| Role resolution in Go (`compose.go`, effort-floor code inside `ic`) | Lives in the `ic` binary, outside this repository; covered only through its observable output in the role table. |
| Hooks that read the roster or contract at session start | Need a running host session; the generator and checker they call are covered. |
| Installing a rendered contract into a host's real instruction file | Writes outside the temp dirs by design; write and check modes are covered on temp copies. |
| `generate.py` truth-table case `repo-routing-end-to-end` | Stale at baseline and main (the shipped self-test reports 58 of 59). Pinned as is, not fixed; see Open items. |
| Isolation of `/tmp/clavain-dispatch-<pid>.*` from the host | The script hard-codes the path and may not be edited here. Not isolated: asserted and deleted per run (see `README.md`, Hermeticity). |
| Windows and macOS behavior | These scripts are Linux automation here; no cross-platform run was made. |

## Open items

* The stale truth-table case above: fixing `tests/fixtures/roster/truth-table.json`
  (or the generator) needs one deliberate edit to
  `test_cli_self_test_shipped_table_fails_only_the_stale_case`.
* The later neutral-defaults slice owns changing the role table's expected
  values; it sets `ORCHCOMPAT_POLICY` and `ORCHCOMPAT_GOLDEN_POLICY` rather than
  editing the goldens (see `README.md`).
