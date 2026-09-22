# BB execution-seat canary — 2026-09-22

Bead sylveste-8252.6. Ran the real dispatch wrapper with `--role deep-execution
--via bb`, a clean scratch source worktree and an isolated Intercore database.
The prompt requested only `plan-b-seat-canary.txt`, no commits or other work.

- Source commit: `e8059a69064a81f83494a3cfaf10e8659494d81e`.
- BB child: `thr_ae2b9me6ra`, parent/lifecycle owner `thr_bnkfysi3gf`.
- Request: `creq_p23nqffpfc`; matching turn: `da459efe58-t1`.
- Turn completed; the exported worktree HEAD equals the pinned source commit.
- Exported untracked tar contains exactly `plan-b-seat-canary.txt`, with
  `BB scratch canary` as its content. Patch/tar hashes are retained in
  `/tmp/clavain-bb-seat-live/result.md.receipt.json` and the Intercore mapping.
- Stop was confirmed, export recorded, then archive completed. BB reports
  `archivedAt=1790117907447`. No live seat remains.
- Scoped total usage: 84,890 input tokens, 232 output tokens; cache-read tokens
  are a subset, 56,064. Raw BB usage is retained without normalization guesses.

The adapter returned nonzero with `terminal_bb_evidence`. Actual model, effort
and effective permission remain `unknown`: the installed BB events expose
requested settings but do not attest those execution fields. Copying the
requested values would misrepresent evidence. Provider automatic retries also
have no supported per-seat disable control; the adapter stops on an observed
retry or model fallback, but cannot prevent the provider from initiating one.
These are BB capability gaps, not completed acceptance criteria.

The source and result paths are scratch resources. The child was archived;
the temporary source worktree can be removed after review. The code under
review is the supervising Clavain branch, not the canary child's scratch diff.
