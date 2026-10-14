---
name: gardener
description: Use for repository upkeep — turning a recurring bad pattern into a lint rule before cleaning it up, shrink-only baselines, one-dependency-family commits, and a docs-pins check for versions quoted in AGENTS.md and READMEs.
---

# Gardener

Keep a repository clean by making the wrong pattern fail, not by asking people to remember it. Adapted from the rat-stack gardener loop for our stack: Go, TypeScript, registered CI and beads. Source: bead mk-w2s2i.

**Announce:** "I'm using the gardener skill for repository upkeep."

Read the repository's `AGENTS.md` first. Work in a clean clone off the default branch, never in a checkout holding someone else's uncommitted files. Every task is a bead before work starts.

## Where to put a correction

Use the strongest option that applies, in this order:

1. The codebase itself: change types or APIs so the wrong version is hard to write.
2. Static analysis: a lint rule or a test that fails on the pattern.
3. Rules in `AGENTS.md`.
4. A skill.
5. A style guide.

Fall back to prose only when none of the stronger options can catch the pattern.

## Rules

1. **Add the lint rule before the cleanup.** When you see a bad pattern or tech debt, write the rule or test that fails on it first, and watch it fail (break it once on purpose). Then fix every existing instance so the rule starts at zero findings. If the cleanup is too big for one commit, land the rule with a baseline equal to today's count and lower the baseline in the same commit as each cleanup. The rule is what keeps the cleanup from decaying.
2. **Baselines only shrink.** If some findings must stay for now, record them as a baseline: a count or a list checked into the repo. A check fails when the live count is above the baseline and also when the baseline is above the live count (so the file is lowered in the same change). Never raise a baseline, never loosen a rule or add an ignore to make a gate pass.
3. **One dependency family per commit.** Packages that move together (a runtime and its adapters, a framework and its plugins) change in one commit, separate from every other dependency and from cleanup. A regression then traces to one library. Let the package manager write lockfiles; never edit one by hand.
4. **Dependency bumps go through the existing upstream-sync process.** This skill does not decide to bump. Use `clavain:upstream-sync-engine` and the owner's sign-off; the gardener only keeps the documented text in step once a bump has been approved.
5. **Documented versions must match manifests.** Run the docs-pins check (below) on every pass and in the same commit as any pin change.
6. **Delete what nothing uses.** Git keeps history. Remove unused exports, duplicate implementations of a supported pattern, and tests that assert nothing.
7. **One reason per commit, one gap per PR.** A gap's PR may hold its rule, its cleanup and its baseline reductions as separate commits, in that order. A dependency family, an unrelated cleanup or a second gap never rides along.

## Stack notes

- **Go:** put new rules in `go vet` analyzers, `staticcheck`/`golangci-lint` config, or an ordinary `_test.go` that walks the source (the way a figures test walks docs). Baselines live beside the test as a plain count.
- **TypeScript:** prefer the repo's configured linter (for example oxlint or ESLint) with a fixture test per rule. Count escapes (`as any`, `as unknown as`, `eslint-disable`, `@ts-ignore`) with a command and keep the count in a shrink-only baseline.
- **CI:** gates run through the repo's registered checks. A gardening change is not done until the required checks pass in fresh isolated guests at the exact commit. Do not add a GitHub Actions dependency to run a new rule.
- **Beads:** one bead per gardening task; name the bead in the commit and the PR.

## Docs-pins check

`scripts/docs-pins.py` in this skill compares versions quoted in `AGENTS.md` and `README.md` (at the root and beside each manifest) with `package.json`, `go.mod` and `pyproject.toml`. A nested document answers to the nearest manifest, in its directory or above, that pins the name; a root document answers to the root manifest when it pins the name, otherwise to every nested manifest that does. It compares plain versions only. Anything else (ranges, wildcards, comparators, `||`, URLs, VCS refs, `workspace:`, tags, prereleases, local `replace` paths, unreadable manifests, and a name pinned with differing specs in one manifest) is listed as a note, not guessed at. It follows the same idea as a figures test that reads numbers in the docs and compares them with the code, but it is reusable across repositories and reports drift as a **warning**: it prints `WARNING <doc>:<line>: <name> documented as X, manifest pins Y (manifest file)` and exits 0. It never rewrites a document.

`SKILL_DIR` is the directory this `SKILL.md` was loaded from; `REPO` is the repository being gardened, which need not contain this skill.

```sh
python3 -I "$SKILL_DIR/scripts/docs-pins.py" --root "$REPO"            # warnings, exit 0
python3 -I "$SKILL_DIR/scripts/docs-pins.py" --root "$REPO" --strict   # exit 1 on drift
python3 -I "$SKILL_DIR/scripts/docs-pins.py" --root "$REPO" --json
```

A documented `1.25` matches a pinned `1.25.3` (whole-component prefix, either direction); a `^` or `~` pin is compared by its base version (`^18.3.1` is compared as `18.3.1`). Names are matched in any case, as written (Python names are not normalized), with markdown marks around the version. Resolve a warning by editing the prose to the manifest value, in the same commit as the pin change; do not edit a manifest to match stale prose. A repository may promote the check to a failing test with `--strict` once its drift is zero; that is the repository owner's call.

## Report

End a gardening pass with:

- each pin the owner approved to move, from and to (none, if you did not move any);
- docs-pins warnings found and resolved;
- lint rules or tests added, and the findings each one removed;
- baselines before and after (numbers from commands you ran);
- anything left undone.

For a measured, scorecard-driven round (every number from a command, one gap per PR), see [references/scorecard.md](references/scorecard.md).
