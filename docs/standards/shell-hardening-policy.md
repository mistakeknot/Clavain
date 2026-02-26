# Shell Hardening Policy

## Scope

All `.sh` files under `os/clavain/hooks/` and `os/clavain/scripts/`.

## Rules

### Entry-point scripts — MUST use strict mode

Files that are **executed directly** (not sourced) must begin with:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

This includes:
- All hook entry points registered in `hooks/hooks.json`
- All scripts in `scripts/` that aren't prefixed with `lib-`
- Thin wrapper scripts (even if they immediately `exec`)

**Why:** Strict mode catches unhandled errors (`-e`), unset variables (`-u`), and broken pipe chains (`-o pipefail`) before they cause silent data corruption or partial execution.

### Sourced libraries — MUST NOT use strict mode

Files that are **sourced** (`source lib-foo.sh`) must NOT set `set -euo pipefail`. They must include this comment on line 2:

```bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
```

Sourced libraries include:
- `hooks/lib.sh`, `hooks/lib-*.sh`
- `scripts/lib-*.sh`

**Why:** Sourced files share the caller's shell process. Enabling `set -e` in a library would change the error behavior for the entire calling script — any function returning non-zero would kill the parent hook. Libraries use fail-safe patterns (`|| return 0`, `|| true`) instead.

### Shellcheck directives

When suppressing a warning, use a standalone directive comment on the line before:

```bash
# shellcheck disable=SC2034
hash="${line%% *}"
```

Never place directives after code on the same line (SC1126 violation).

## CI Enforcement

The `Tier 0 — Shell lint (shellcheck)` step in `.github/workflows/test.yml` runs shellcheck on all entry-point files. Library files are excluded via the `! -name 'lib-*'` filter.

Local: `make shellcheck` from the `os/clavain/` directory.

### Severity

CI uses `--severity=warning`. Errors and warnings fail the build. Info and style notices are allowed.

## Exception Process

If a script legitimately needs to suppress a shellcheck warning:

1. Add `# shellcheck disable=SCXXXX` on the line before the flagged code
2. The directive is self-documenting — no additional comment required for well-known codes (SC2034, SC2086, etc.)
3. For unusual suppressions, add a brief reason comment on a separate line above the directive

## Checklist for New Scripts

- [ ] Shebang: `#!/usr/bin/env bash`
- [ ] Strict mode: `set -euo pipefail` (entry points only)
- [ ] Sourced library comment (libraries only)
- [ ] Passes `shellcheck --severity=warning --shell=bash`
- [ ] No `local` outside functions
- [ ] Quotes around variable expansions (`"$var"`, not `$var`)
