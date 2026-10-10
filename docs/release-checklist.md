# Release checklist

Steps that follow a Clavain release. Tagging and publishing stay with the
release owner; this list covers what happens after publish.

## After publish

1. **Instruction-contract check.** On each machine that runs Clavain, run the
   check against every host instruction file that carries the managed block:

   ```bash
   CLAVAIN_SELECTED_ROOT=<installPath> \
     scripts/check-instruction-contract.sh --host claude --file ~/.claude/CLAUDE.md
   ```

   It prints one JSON object and exits 0 when current, 1 when drifted (the
   `drift` list names `version`, `policy-hash`, `block-content`, `no-receipt` or
   `file-missing`), 2 on usage or runtime errors. The policy hash is compared,
   not only the version.

   If it reports drift, message the instruction-file steward with the new
   version so they open the resync PR.

2. **Mac peer (advisory).** Offer mk a Mac pull script, a fast-forward pull of
   dotfiles plus the plugin refresh, for the Mac peer. It is an offer only; the
   Mac catches up on its own schedule if mk declines.
