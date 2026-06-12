---
name: freeze
description: Restrict file edits to declared paths — scope-lock for parallel-session safety
argument-hint: "<path> [path...]"
---

# Freeze — Scope Lock

Restrict Edit/Write/MultiEdit to the declared paths for this project. Everything outside the scope is blocked by a hookify rule until `/clavain:unfreeze`. Use when debugging in a shared repo, running alongside parallel sessions, or executing a plan that should only touch known files.

**Announce:** "Freezing edit scope to: <paths>"

## Steps

### 1. Normalize paths

Take each argument and resolve it to an **absolute path**:
- Relative paths → prefix with CWD
- Strip trailing slashes
- The path does NOT need to exist (freezing to a directory you're about to create is valid — prefix matching covers new files under it)

If no arguments were given, stop with usage: `/clavain:freeze <path> [path...]` — at least one allowed path is required.

### 2. Check for an existing freeze

If `.claude/hookify.freeze-scope.local.md` exists, read its message body to find the current scope and announce the replacement: "Replacing existing freeze (<old paths>) with new scope."

### 3. Write the hookify rule

Build a regex-escaped alternation from the absolute paths. Escape regex metacharacters in each path (`.` → `\.`, etc. — apply Python `re.escape` semantics). Then write `.claude/hookify.freeze-scope.local.md` (create `.claude/` if missing):

```markdown
---
name: freeze-scope
enabled: true
event: file
action: block
conditions:
  - field: file_path
    operator: regex_match
    pattern: ^(?!(<escaped-path-1>|<escaped-path-2>)).*
---

🧊 **FROZEN**: edits are restricted to:
<bulleted list of allowed paths>

This scope lock was set with `/clavain:freeze`. To edit outside it, run `/clavain:unfreeze` or ask the user to lift it. Do NOT work around the block with Bash file mutations.
```

The negative lookahead means: block any file_path that does NOT start with one of the allowed prefixes. Prefix matching is intentional — files *under* an allowed directory pass.

### 4. Reserve via interlock (best-effort)

If the interlock MCP is available, call `reserve_files` with the same path patterns (glob form: `<path>/**` for directories) so parallel sessions see the claim. Failure here is non-fatal — the hookify block is the enforcement layer; the reservation is visibility.

### 5. Confirm

Report the active scope as a short bulleted list, plus:
- "Out-of-scope Edit/Write/MultiEdit will be blocked by hookify."
- "Known limitation: Bash mutations (`sed -i`, `>` redirects, `tee`) are not blocked in v1 — don't use them to bypass the freeze."
- "Lift with `/clavain:unfreeze`."

## Notes

- The rule file is project-local (`.claude/` of CWD) and gitignored by convention (`*.local.md`). Freezing one project does not affect others.
- Re-running `/clavain:freeze` replaces the scope (it does not accumulate). To widen a freeze, re-run with the full desired path list.
