# Review early-exit shadow observations

`review_exit` stays `mode: off` in routing.yaml. Only `mode: shadow`
observes; enforce is inert. The selector global off switch also disables it.
The round runner and quality-gates command launch the observer after the
native decision, with detached stdin/stdout/stderr. No result is consumed.
The CLI subprocess has a six-second timeout. Egress is always false; tests
use the heuristic. Hosted registry settings and budgets are unchanged.

Set `REVIEW_EXIT_LOOP_ID` to one stable identifier for a change across heads
and rounds. Round runner defaults to bead-or-repository plus base; override
when bases change or multiple changes share that default. Quality gates
requires a loop ID or bead, and the native decision in `REVIEW_EXIT_NATIVE`.
Supply callbacks in round order; concurrent callbacks for the same loop may
miss a later-outcome join. Different loop IDs are independent.

The S1 record in `.clavain/decisions/YYYY-MM-DD.jsonl` holds hashed question,
candidates and choices, confidence and native application. Companion
`review-exit-observation-v1` rows join by `decision_id` and contain only a
hashed loop ID, random observation ID, numeric counts/estimates and booleans.
`native_agreement` compares shadow and native; heuristic agreement is
tautological and supplies no evidence of calibrated prediction quality.

Each later callback appends `review-exit-outcome-v1` for previous decisions
in that loop. Use the last outcome for each decision. `could_exit` is true
only when all observed later rounds explicitly reported zero findings;
unknown or unparsed findings remain null. It is provisional until the loop
has completed. No later observation means unknown, not successful early exit.
Panel PASS is zero; all other panel verdicts remain unknown. Gate verdicts
use explicit nonnegative `findings_count` values, including minor findings.

`estimated_claude_tokens_saved` sums estimates for later rounds with zero
findings. The method is ceil(total UTF-8 artifact bytes / 4): panel prompts
plus reviewer responses, or gate verdict JSON files. This is a conservative
artifact-size proxy for counterfactual Claude tokens, even when another lab
performed the review. It excludes hidden context, tool traffic, cache effects
and gate prompts, and is not measured usage or actual savings. Unknown
estimates are excluded and `token_estimate_complete` is false. Observations
start with savings zero. Do not sum cumulative outcome rows or overlapping
decision windows; for a loop use the selected hypothetical exit's last row.
For missed-finding evaluation compare `shadow_exit` against `could_exit`;
any later finding invalidates a proposed exit. Unknown outcomes are excluded.

LOG ONLY: all existing quality, grounding, review and escalation rules apply.
