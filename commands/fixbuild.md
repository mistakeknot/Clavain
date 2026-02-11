---
name: fixbuild
description: Run build, capture error, fix it, re-run — fast loop for type errors and build failures without heavyweight debugging
argument-hint: "[optional: build command, e.g. 'go build ./...' or 'npm run build']"
---

# Fix Build

Lightweight build-error fast path. For type errors, missing imports, and straightforward build failures — not complex bugs.

## Build Command

<build_cmd> #$ARGUMENTS </build_cmd>

If no build command provided, auto-detect from project:

```bash
# Detect build system (check in order)
ls go.mod 2>/dev/null        # → go build ./...
ls Cargo.toml 2>/dev/null    # → cargo build
ls package.json 2>/dev/null  # → npm run build (or tsc if tsconfig.json exists)
ls pyproject.toml 2>/dev/null # → uv run python -m py_compile (or pytest --collect-only)
ls Makefile 2>/dev/null      # → make
```

If multiple build systems detected, pick the most specific (go.mod > Makefile).

## Loop (max 5 attempts)

For each attempt:

### 1. Run Build

```bash
# Run the build command, capture both stdout and stderr
```

If build succeeds (exit 0): report success and stop.

### 2. Parse Errors

Extract from build output:
- **File paths** with line numbers
- **Error messages** (type mismatch, undefined reference, missing import, syntax error)

Read only the failing file(s). Don't read the whole codebase.

### 3. Fix

Apply the minimal fix. Common patterns:
- Missing import → add it
- Type mismatch → fix the type
- Undefined symbol → check for typo, add declaration, or fix reference
- Syntax error → fix syntax

**Do not refactor.** Fix the error and nothing else.

### 4. Re-run Build

Go back to step 1 with the next attempt.

## Escalation

After 5 failed attempts, stop and say:

> Build still failing after 5 fix attempts. This looks like a deeper issue — consider using `/clavain:repro-first-debugging` for systematic investigation.

Do NOT keep looping. Five attempts means the problem isn't a simple build error.

## Important

- **This is not debugging.** Don't investigate root causes, don't add logging, don't run tests. Just fix the build error.
- **Minimal diffs.** Each fix should be 1-5 lines. If a fix requires more than 10 lines, it's probably not a build error.
- **Don't touch passing code.** Only modify files that appear in the error output.
