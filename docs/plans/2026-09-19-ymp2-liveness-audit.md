# Sylveste-ymp2 — freeze the authorization, explain the baseline, then rebuild the decision as code

> **Revision 3, 2026-09-19.** Revision 1 rejected by Astra. Revision 2 rejected by Astra *and* Fable, independently, on different briefs. Both rejections converged on the same redesign, and the consumer-side baseline — which neither earlier revision included and which costs one read-only command — changed the question. This is not an edit of revision 2; the shape is different.

## The baseline, first, because it moves the target

`clavain-cli policy audit` on **zklw**, the canonical host:

| op | rows | modes | empty `vetted_sha` | empty `policy_match` |
|---|---|---|---|---|
| `bead-close` | 20 | auto 8 · confirmed 9 · blocked 3 | **20 of 20** | 3 |
| `ic-publish-patch` | 44 | **auto 44** | — | — |
| `bd-push-dolt` | 200 | auto 171 · confirmed 8 · blocked 21 | — | — |
| `git-push-main` | **0** | — | — | — |

**Every recorded bead-close on the canonical host carried no vetting evidence, and eight of them auto-proceeded anyway.** The policy requires `vetted_sha_matches_head: true` (`config/policy.yaml.example:29-37`), and `vetted_sha` is empty in 20 of 20 rows. Patch publication has auto-proceeded 44 times out of 44.

The epic asked whether an *empty verdict directory* produces a clean stamp. Production's answer is larger and prior: **the evidence field has been empty in every recorded close, and the gate proceeded regardless.** Either the rule is not evaluated, or an empty SHA satisfies `vetted_sha_matches_head`, or the signal arrives by environment variable and is never recorded. Revision 3 does not guess which — **explaining these rows is the first work item**, because every downstream design depends on the answer.

`git-push-main` having **zero rows** independently confirms the correction already recorded: `Sylveste-zfz8` step 5 ("the push gate auto-proceeds") is wrong.

## Why revision 2 died

- **Fixing the `verdict_parse_all` bug alone is a regression.** The accidental `exit 1` is the only thing currently stopping an `ERROR` verdict from `fd-safety` — a *crashed security reviewer* — from being stamped clean. Reproduced both ways: today the fence dies before the stamp; with the one-line fix it stamps. The bug is load-bearing, so "Stages 0–2 ship first" was exactly backwards.
- **Production runs each markdown fence in a fresh shell.** `verdict_count_by_status` is undefined there; `2>/dev/null` hides it and `|| echo 0` converts it to a clean count. Reproduced: one `NEEDS_ATTENTION` on disk, fence reports `needs_attention=0`. A fence cannot hold this guarantee, and a canary that runs fences together in one shell models an execution that never happens.
- **`vetted_at` already means tests, by contract.** The policy comment says "verified **tests pass** within the last 60 minutes on the same HEAD SHA". Revision 2 silently redefined it as "review accepted" — an authorization change, not a bugfix. The canon it cites as authority, `docs/canon/policy-merge.md`, **does not exist**.
- **Stage 2's severity claim was unsupported.** `verify-synthesis-grounding.sh:124` reads `# No findings to ground — vacuously OK`: the checker validates that synthesized findings are *grounded in* reviewer findings. It catches **invention, not suppression** — a synthesis dropping every reviewer P0 exits 0, `--strict` included. That gap is `Sylveste-ywqs`, and nothing in revision 2 filled it.

## Approach

### Stage A — mitigate the ship-class bypass (immediate, independent, lands first)

`quality-gates.md:54`: `DIFF_LINES < 20 && CHANGED_FILES == 1` runs one `fd-quality` agent and **skips Phases 2–3**, including the mandatory ship-class `fd-safety` enforcement that `flux-engine/SKILL.md:246` declares non-optional. Astra reproduced selection with an 8-line single-file hook edit.

Add the ship-class test **before** the shortcut branch and exclude any matching diff from it. This is a few lines, it is not entangled with anything below, and Astra's ruling stands: filing it is not defensible, because the bypass sits inside the path being repaired.

### Stage B — explain the baseline (read-only; gates everything after it)

Determine why 20 of 20 closes recorded an empty `vetted_sha` while 8 auto-proceeded. Read `evaluator.go:119` against the live `~/.clavain/policy.yaml`, and check whether `_common.sh:130`'s env-var preference means the value arrives inherited and is never written to the audit row. **Do not design further until this is answered** — if the rule is not evaluated at all, the entire stamp path is decoration and most of the work below is aimed at the wrong thing.

Also write the missing `docs/canon/policy-merge.md`, or remove the two citations that point at it (`sprint.md:371`, `work.md:132`).

### Stage C — freeze review-derived automatic authorization

Before any traversal repair, make the affected ops not auto-proceed on review-derived signals: a policy diff moving `bead-close` and `ic-publish-patch` to `confirm`, or adding the missing requirement. This is what makes the Stage-D regression impossible, and it is reversible in one commit.

It must not break ordinary work. `work.md:122` runs quality-gates only for risky changes, so an ordinary `/work` bead has no review path at all; `gate_prompt_or_abort` aborts with no tty (`_common.sh:316-318`) and agents never have one. The callers that would break — `bead-sweep.md:68`, `campaign.md:209,215`, `landing-a-change/SKILL.md:121`, `ship/SKILL.md:44`, `bead-land.sh`, `bead-close-shipped.sh`, `lib-sprint.sh:33` — are named here so the freeze is designed with them, not discovered by them. **Shadow first:** record what the stricter rule *would* have decided for N closes before enforcing.

### Stage D — move the decision into one executable

A single `scripts/gates/review-evidence.sh` (or `clavain-cli` subcommand, following `quality-gate-run` in `cmd/clavain-cli/quality_gates.go:32`), called from the markdown as **one line**. `bead-close.sh` is already this pattern and `scripts/runtime-evidence-canary.sh:508` already exercises it for real.

This is the load-bearing change: it is what makes the logic testable at all, because the canary then runs the same file production runs. Only inside it do the traversal fixes belong — the `verdict_parse_all` return, the `NEEDS_VERIFICATION`/`ERROR`/`FAILED` statuses, exit 0/1/3. The `verdict_parse_all` fix **must not land before Stage C**, for the regression reason above.

**One owner for the gate decision.** `quality-gates.md:324` advances the phase internally, before `sprint.md:400` reads verdicts and `:413` re-runs `enforce-gate "shipping"`. Both reviewers found this independently. Pick one site; the evidence decision must precede every phase mutation, not follow one.

### Stage E — the reviewer manifest (cross-repo; needs a publish order)

"Complete reviewer set" is decidable, but not from the verdict directory. Flux-drive already knows: `AGENT_NAMES` (`flux-engine/phases/launch.md:372`) and `agents_launched`/`agents_completed`/`agents_failed` (`interflux/docs/spec/core/synthesis.md:216`). The reader receives only a directory.

Persist a **dispatch-owned manifest** — expected reviewers, mandatory reviewers, attempt UUID, input digest — finalized *after* expansion, since reviewers can be added mid-run (`flux-engine/phases/expansion.md:100`). Never reconstruct expectations from whichever results happen to exist.

**Three repos, and the publish order matters.** The verdict writer is intersynth's agent sourcing **intersynth's own drifted copy** of `lib-verdict.sh` (no `session_id`, no `phase`); there are seven copies of that file on this disk. The transport fix lives in interflux. Clavain only reads. Editing Clavain's copy edits a file the writer never loads — which would produce a new loop that is built, green in its own suite, and dead. Retire the duplicate so one copy remains; name interflux → intersynth → Clavain as the order; add one installed-runtime assertion that a verdict written by the real synthesizer carries the identity fields.

Also migrate the direct writers that bypass `verdict_write` entirely (`quality-gates.md:209,266`) — requiring new fields without migrating them makes legitimate evidence unverifiable, and excluding them loses their vetoes.

### Stage F — the canary, where it actually runs

With the decision in an executable, the canary is a normal test of a normal program. Land it in the **zklw verification contract** (`tests/verification-pilot.json`) as a **second `checks[]` entry with its own report** — the `min_executed: 200` floor is per check and measures `pilot.xml`, and the runner accepts only the `pytest-junit` count parser (`scripts/verification_runner.py:145`), so a bats command does not raise that count. Add its toolchain to `prerequisites.executables`. Coordinate through `mk-ag2s.25` (in_progress, repo id 1151593132); do not create a duplicate migration task. Specify the **scheduling trigger**, not just one execution at the implementation commit.

### Stage G — separate the signals, then re-enable

Keep `vetted_*` meaning tests. Add `reviewed_at` / `reviewed_sha`, and a policy `requires:` key that is on for `/sprint` and off for `/work`, so requiring review is an explicit reviewable policy diff rather than a silent redefinition. Lift Stage C's freeze only after completeness, severity, freshness, gate-result consumption and **both** authorization readers pass their acceptance checks.

Add the source-side freshness fix here (`quality-gates.md:113` copies with plain `cp`, then checks `-ot` on the copy it just made; reproduced passing a 7-hour-old review), the directory/filename transport reconciliation including the uncopied mandatory `fd-safety.${FLUX_RUN_UUID}.md` (`:161`), the `gate_populate_vetting` inherited-authority refusal plus the no-bead-context refusal in `ic-publish-patch.sh:27`, and the typed gate result consumed structurally rather than printed — `Autarch/pkg/clavain/intent.go:52` unmarshals the whole stdout buffer.

### Stage H — name the systemic defect

Fable counted it: **72 `|| true` across 16 LLM-executed markdown files, 35 in `sprint.md`/`quality-gates.md`/`work.md`, 17 of the exact form `bd set-state … || true`.** The rule: **markdown may call gates; it may not implement them.** Add a structural lint with an allowlist forbidding error suppression on any line that writes state, artifacts, or phase. Replace `tests/vetting-writes_test.sh` with that lint in the same commit — its "four keys in all three flows" invariant already fails today and contradicts Stage G.

## Ordering

**A → B → C** before anything else touches behaviour. A is independent and urgent; B may invalidate parts of D–G; C makes D safe. D → E → F → G → H thereafter. The stages are separate commits but **only A, B and C are independently safe activation boundaries** — the rest change what the gate accepts and must land behind the freeze.

## Explicitly not claimed

- Stage D/E do **not** supply a deterministic severity check. The grounding checker is directional and `synthesize-review.md:61` still assigns status by prose. **Either `Sylveste-ywqs` lands, or automatic authorization stays disabled.** Revision 2 claimed Stage 2 covered this; it did not.
- One manual planted-P0 traversal demonstrates one traversal, not reliable aggregation. Redesigned per Astra: inert synthetic marker, asserted present in the generated diff (`quality-gates.md:74` diffs working tree and index against HEAD, so a committed defect on a clean branch is invisible), intended path confirmed to run, `fd-safety` confirmed complete, refusal attributed to the planted finding rather than broken transport. Schedule after Stage D.
- `Sylveste-smw4` (no writer for `landed_changes`) and `Sylveste-c53i` (publication authority) remain out of scope.

## Bead corrections to apply

- `Sylveste-zfz8`: step 5 is wrong — `git-push-main.sh:56` never calls `gate_populate_vetting`, and the audit shows zero rows for that op. Real consumers: `bead-close.sh:129`, `ic-publish-patch.sh:28`, plus `bd-push-dolt.sh:45` reading `CLAVAIN_SPRINT_OR_WORK` straight from the environment. Also: three unevaluated returns in `cmdEnforceGate`, not four — `phase.go:~355` sets shadow mode and continues.
- `Sylveste-0ru1`: a directory mismatch is prior to and independent of the filename mismatch — producer appends `-{RUN_HASH}` (`flux-engine/SKILL.md:128`), consumer reconstructs unsuffixed (`quality-gates.md:107`).
- File the ship-class shortcut bypass as its own bead (Stage A fixes it; the record should still exist).

## Verification

- **A:** the 8-line single-file hook fixture no longer selects the shortcut; `fd-safety` runs.
- **B:** a written explanation of the 20 empty-`vetted_sha` rows, naming which of the three hypotheses holds, with the evaluator path traced.
- **C:** shadow log shows N closes and what the stricter rule would have decided; every named caller still completes.
- **D:** the executable returns 0/1/3 correctly for missing, empty, all-CLEAN, `NEEDS_ATTENTION`, `ERROR`, `NEEDS_VERIFICATION`, malformed and stale-prior-run fixtures — and `ERROR` does **not** stamp, which is the regression this ordering exists to prevent.
- **E:** a verdict written by the real synthesizer, from the installed plugin, carries the identity fields.
- **F:** a zklw job shows the new check executed with its own report, on a stated trigger.
- **G:** pre-seeded bead state **and** environment, read through `bead-close.sh`, yield **no automatic authorization**; an hour-old source is refused; `clavain-cli intent submit` emits exactly one JSON document on every gate path.
- Go checks run from `cmd/clavain-cli` — the module lives there (`cmd/clavain-cli/go.mod:1`).
- Lands in **mistakeknot/Clavain**, **mistakeknot/interflux**, **mistakeknot/intersynth**. `os/Clavain` and `core/intercore` are independent clones inside the Sylveste tree (`git ls-files os/Clavain` returns 0). Nothing lands in Sylveste.
- Do **not** drive this with `/clavain:sprint`: Step 7 is the code under repair.
