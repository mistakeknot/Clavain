---
agent: shell-reviewer
tier: 3
issues:
  - id: P1-1
    severity: P1
    section: "Staleness Detection (Section 3)"
    title: "xargs stat pipeline is unsafe with filenames containing spaces or special characters"
  - id: P1-2
    severity: P1
    section: "Staleness Detection (Section 3)"
    title: "stat -c '%Y' is GNU-only -- fails silently on macOS (stat -f '%m' needed)"
  - id: P1-3
    severity: P1
    section: "Path Resolution (Section 2)"
    title: "find results are unguarded -- if find returns nothing, DISPATCH and REVIEW_TEMPLATE are empty strings"
  - id: P1-4
    severity: P1
    section: "Staleness Detection (Section 3)"
    title: "ls -t piped to tail for oldest file is fragile -- breaks on filenames with newlines and fails without error if no fd-*.md exist"
  - id: P1-5
    severity: P1
    section: "Codex Dispatch Invocation (Section 4)"
    title: "Predictable temp file path /tmp/flux-codex-{agent-name}.md -- race condition and no cleanup"
  - id: P2-1
    severity: P2
    section: "Clodex Mode Detection (Section 1)"
    title: "Uses [ ] (POSIX test) inconsistently -- plan mixes [ ] and implicit bash context"
  - id: P2-2
    severity: P2
    section: "Codex Dispatch Invocation (Section 4)"
    title: "--inject-docs injects CLAUDE.md into every review agent prompt -- redundant for Codex which reads it natively"
  - id: P2-3
    severity: P2
    section: "Path Resolution (Section 2)"
    title: "find traverses entire plugin cache tree twice -- no maxdepth or early termination"
improvements:
  - id: IMP-1
    title: "Add fatal guard after path resolution find commands"
    section: "Path Resolution (Section 2)"
  - id: IMP-2
    title: "Replace xargs stat pipeline with find -newer for staleness check"
    section: "Staleness Detection (Section 3)"
  - id: IMP-3
    title: "Use mktemp for prompt files instead of predictable /tmp paths"
    section: "Codex Dispatch Invocation (Section 4)"
  - id: IMP-4
    title: "Add trap-based cleanup for temp files"
    section: "Codex Dispatch Invocation (Section 4)"
  - id: IMP-5
    title: "Use git-based staleness check exclusively -- drop the stat pipeline"
    section: "Staleness Detection (Section 3)"
  - id: IMP-6
    title: "Drop --inject-docs for review agents or change to --inject-docs=agents"
    section: "Codex Dispatch Invocation (Section 4)"
verdict: needs-changes
---

## Summary

The plan introduces four categories of bash snippets for Codex-based review dispatch in clodex mode. The clodex detection (Section 1) is clean and straightforward. The dispatch invocation (Section 4) correctly matches `dispatch.sh`'s flag interface. However, three areas need attention before implementation: (1) the staleness detection pipeline has a dangerous `xargs stat` chain that breaks on filenames with spaces and uses GNU-only `stat -c`, (2) the `find`-based path resolution has no guard against empty results, and (3) temp file handling uses predictable paths with no cleanup. None of these are critical blockers for a Linux-only deployment, but P1-1 and P1-3 will cause silent failures in realistic conditions.

## Section-by-Section Review

### Section 1: Clodex Mode Detection (Plan lines 83-89)

```bash
if [ -f "{PROJECT_ROOT}/.claude/autopilot.flag" ]; then
  echo "CLODEX_MODE=true"
else
  echo "CLODEX_MODE=false"
fi
```

**Assessment: Adequate.**

This is a simple file-existence check. Compared to the existing `autopilot.sh` (which uses `[[ ]]` consistently), this snippet uses POSIX `[ ]` -- not a bug, but inconsistent with the project's bash style. The curly braces around `{PROJECT_ROOT}` indicate this is a pseudo-code placeholder that Claude will expand at runtime, not literal bash. That is fine.

The existing `autopilot.sh` references `$CLAUDE_PROJECT_DIR` from the hook environment. This snippet uses `{PROJECT_ROOT}` which is a flux-drive variable resolved earlier in the SKILL.md. No conflict -- different contexts (hook vs. skill execution).

One minor observation: the snippet echoes `CLODEX_MODE=true` but does not actually set a variable. This is pseudo-code for the LLM orchestrator, not a real script, so this is acceptable in context. The LLM reads the output and branches accordingly.

### Section 2: Path Resolution (Plan lines 103-108)

```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
[ -z "$DISPATCH" ] && DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)

REVIEW_TEMPLATE=$(find ~/.claude/plugins/cache -path '*/clavain/*/skills/clodex/templates/review-agent.md' 2>/dev/null | head -1)
[ -z "$REVIEW_TEMPLATE" ] && REVIEW_TEMPLATE=$(find ~/projects/Clavain -path '*/skills/clodex/templates/review-agent.md' 2>/dev/null | head -1)
```

**Assessment: Needs improvement.**

**What works:**
- The fallback chain (plugin cache first, then local project) is a sound pattern.
- stderr suppression (`2>/dev/null`) prevents noise if the cache directory does not exist.
- The `head -1` prevents multiple matches from causing issues.

**What does not:**
- **No fatal guard (P1-3).** If both `find` commands return no results for both the plugin cache and local project searches, `$DISPATCH` and `$REVIEW_TEMPLATE` are empty strings. The subsequent `bash "$DISPATCH" --template "$REVIEW_TEMPLATE" ...` would execute `bash "" --template "" ...`, which in `set -e` mode would fail with an obscure error like `bash: : No such file or directory`. The plan should include:
  ```bash
  [ -z "$DISPATCH" ] && { echo "ERROR: dispatch.sh not found in plugin cache or ~/projects/Clavain" >&2; exit 1; }
  [ -z "$REVIEW_TEMPLATE" ] && { echo "ERROR: review-agent.md template not found" >&2; exit 1; }
  ```
- **No maxdepth on find (P2-3).** The plugin cache can be deep. Adding `-maxdepth 8` or similar would prevent unnecessary traversal. This is a performance nit, not a correctness issue.
- **Quoting is correct.** The `$DISPATCH` and `$REVIEW_TEMPLATE` variables are properly quoted in the `[ -z "$DISPATCH" ]` test and in the dispatch invocation. No issues here.

### Section 3: Staleness Detection (Plan lines 206-219)

This section contains two alternative approaches. I review both.

#### Alternative A: The stat pipeline (lines 206-209)

```bash
OLDEST_AGENT=$(ls -t .claude/agents/fd-*.md 2>/dev/null | tail -1)
CHANGED=$(find . -name "CLAUDE.md" -o -name "AGENTS.md" -o -name "*.go" -o -name "*.py" -o -name "*.ts" -o -name "*.rs" | xargs stat -c '%Y %n' 2>/dev/null | awk -v ref="$(stat -c '%Y' "$OLDEST_AGENT")" '$1 > ref {print $2}')
```

**Assessment: Multiple safety issues.**

1. **`xargs stat` with unquoted filenames (P1-1).** The `find | xargs stat` pipeline is the textbook shell safety violation. Any filename containing a space, quote, or newline will cause `stat` to receive incorrect arguments. The `find` invocation searches for `*.go`, `*.py`, `*.ts`, `*.rs` across the entire tree -- in a real project, these might be inside `node_modules/` or vendor directories with exotic names. The correct approach is `find ... -print0 | xargs -0 stat ...`, but even that only mitigates the issue -- see below.

2. **`stat -c '%Y'` is GNU-only (P1-2).** On macOS/BSD, `stat` uses `-f '%m'` for modification time. The plan does not specify the target platform. Since this server is Linux (`uname -s` returns `Linux`), this works *here*, but the plan does not document this as a Linux-only assumption. If Codex agents run on macOS runners in CI, this fails silently -- `stat -c` on BSD `stat` is a flag for a different purpose and would return unexpected output.

3. **`ls -t ... | tail -1` for oldest file (P1-4).** Parsing `ls` output is fragile. If no `fd-*.md` files exist, `ls` writes nothing to stdout, `tail -1` returns empty, and `$OLDEST_AGENT` is empty. The subsequent `stat -c '%Y' "$OLDEST_AGENT"` then calls `stat -c '%Y' ""`, which fails. More subtly, if an `fd-*.md` filename contains a newline (unlikely but possible), `ls -t | tail -1` returns a truncated path.

4. **The `find -o` chain lacks grouping.** The `find . -name "CLAUDE.md" -o -name "AGENTS.md" -o -name "*.go" ...` needs explicit grouping with `\(` and `\)` to be correct when combined with other predicates. As written, `find` will apply `-print` only to the last `-name` predicate on some implementations, because `-o` has lower precedence than implicit `-and -print`. This is a classic `find` gotcha. It should be:
   ```bash
   find . \( -name "CLAUDE.md" -o -name "AGENTS.md" -o -name "*.go" -o -name "*.py" -o -name "*.ts" -o -name "*.rs" \) -print0
   ```

#### Alternative B: The git-based check (lines 213-218)

```bash
cat .claude/agents/.fd-agents-commit 2>/dev/null  # e.g. "abc123"
git rev-parse HEAD                                  # e.g. "def456"
git diff --stat abc123..HEAD -- CLAUDE.md AGENTS.md docs/ARCHITECTURE.md
```

**Assessment: Much better, with minor issues.**

- The git-based approach avoids all the filesystem timestamp issues. It compares commits, which is exactly the right abstraction for "has the project changed structurally?"
- **Unvalidated commit hash.** The value from `.fd-agents-commit` is used directly in `git diff --stat abc123..HEAD`. If the file contains garbage or is empty, `git diff` will fail with a non-zero exit. Under `set -e`, this would abort the entire flux-drive run. The plan should validate the hash:
  ```bash
  AGENTS_COMMIT=$(cat .claude/agents/.fd-agents-commit 2>/dev/null)
  if [ -z "$AGENTS_COMMIT" ] || ! git cat-file -e "$AGENTS_COMMIT" 2>/dev/null; then
    # Commit unknown or invalid -- force regeneration
    REGENERATE=true
  fi
  ```
- **The plan says "If the diff is non-empty, regenerate."** This is the right heuristic, but the snippet does not actually capture the diff output for programmatic checking. It runs `git diff --stat` which outputs to stdout -- the orchestrating LLM reads this and decides. For a bash-only implementation, you would check `git diff --quiet abc123..HEAD -- CLAUDE.md AGENTS.md` (exit code 0 = no changes, 1 = changes).

**Recommendation: Use Alternative B exclusively. Drop Alternative A.** The stat pipeline is error-prone and the git approach is both simpler and more correct.

### Section 4: Codex Dispatch Invocation (Plan lines 138-144)

```bash
bash "$DISPATCH" \
  --template "$REVIEW_TEMPLATE" \
  --prompt-file /tmp/flux-codex-{agent-name}.md \
  -C "$PROJECT_ROOT" \
  -o /tmp/flux-codex-result-{agent-name}.md \
  -s workspace-write \
  --inject-docs
```

**Assessment: Functional but has safety and correctness concerns.**

**Flag interface compatibility with dispatch.sh:**

I verified each flag against `/root/projects/Clavain/scripts/dispatch.sh`:

| Flag | Supported | Notes |
|------|-----------|-------|
| `--template <FILE>` | Yes (line 49, 122-125) | Reads template, parses `KEY:` sections from prompt, substitutes `{{KEY}}` |
| `--prompt-file <FILE>` | Yes (line 48, 117-120) | Reads prompt from file |
| `-C <DIR>` | Yes (line 37, 79-82) | Sets working directory |
| `-o <FILE>` | Yes (line 38, 84-87) | Output last message |
| `-s <MODE>` | Yes (line 39, 89-92) | Sandbox mode |
| `--inject-docs` | Yes (line 42-46, 104-106) | Defaults to "claude" scope |

All flags are valid. The `--template` + `--prompt-file` combination is explicitly supported -- `dispatch.sh` reads the prompt file first (line 175), then if `--template` is set, treats the prompt content as the task description containing `KEY:` sections (line 190-248).

**Issues:**

1. **Predictable temp file paths (P1-5).** `/tmp/flux-codex-{agent-name}.md` and `/tmp/flux-codex-result-{agent-name}.md` are predictable. On a shared system, another user could create a symlink at that path pointing elsewhere. More practically, if flux-drive is run twice concurrently for different projects, the second run overwrites the first run's prompt files. Use `mktemp`:
   ```bash
   prompt_file="$(mktemp "/tmp/flux-codex-${agent_name}-XXXXXX.md")"
   ```
   Since each agent dispatch is a separate Bash call, each gets its own scope. However, the plan dispatches agents from the LLM layer (parallel Bash calls), so the LLM would need to generate unique filenames. At minimum, append `$$` or a UUID.

2. **No cleanup of temp files.** The plan does not mention cleaning up `/tmp/flux-codex-*.md` files after agents complete. Over time, these accumulate. A cleanup step in Phase 3 (after synthesis) would be prudent:
   ```bash
   rm -f /tmp/flux-codex-*.md /tmp/flux-codex-result-*.md
   ```
   (This is safe because the glob is specific enough to not hit unrelated files.)

3. **`--inject-docs` appropriateness (P2-2).** The bare `--inject-docs` flag defaults to scope `claude`, which injects `CLAUDE.md` from the `-C` working directory into the prompt. For review agents dispatched via Codex, this means `CLAUDE.md` content is prepended to the assembled prompt. The `dispatch.sh` script notes (line 43): "CLAUDE.md only (recommended -- Codex reads AGENTS.md natively)". The question is whether Codex also reads `CLAUDE.md` natively. Looking at the dispatch script, it only warns about AGENTS.md redundancy (line 287), implying CLAUDE.md is *not* read natively by Codex. So `--inject-docs` (which injects CLAUDE.md) is appropriate for ensuring the review agent has project context.

   However, for review agents that already receive a full task description including project context in the `{{PROJECT}}` template variable, the injected CLAUDE.md may be redundant and consume tokens. Consider making this conditional: use `--inject-docs` only for agents that do not already receive project context in their prompt.

4. **Template placeholders must match task description keys.** The review-agent.md template (plan lines 42-71) uses placeholders: `{{PROJECT}}`, `{{AGENT_IDENTITY}}`, `{{REVIEW_PROMPT}}`, `{{OUTPUT_FILE}}`, `{{AGENT_NAME}}`, `{{TIER}}`. The task description file format (plan lines 113-131) uses matching headers: `PROJECT:`, `AGENT_IDENTITY:`, `REVIEW_PROMPT:`, `AGENT_NAME:`, `TIER:`, `OUTPUT_FILE:`. The regex in dispatch.sh (`^([A-Z_]+):$`) matches all of these. **This is correct.**

### Section 5: Agent Bootstrap (Plan lines 189-191)

```bash
git rev-parse HEAD > .claude/agents/.fd-agents-commit
```

**Assessment: Clean.** This is a simple, correct command. The only consideration is whether `.claude/agents/` exists before writing -- but the create-review-agent template (which runs before this line) creates `fd-*.md` files in that directory, so it must already exist. No issue.

## Issues Found

### P1-1: xargs stat pipeline is unsafe with filenames containing spaces or special characters
**Section:** Staleness Detection, Alternative A (plan line 209)
**Severity:** P1

The `find ... | xargs stat -c '%Y %n'` pipeline will break on any filename containing whitespace, quotes, or backslashes. In a typical project with `node_modules/`, vendor directories, or files with spaces, this produces incorrect stat results and potentially operates on the wrong files. The concrete failure: a file named `my project/CLAUDE.md` would cause `stat` to receive two arguments: `my` and `project/CLAUDE.md`, both of which fail.

### P1-2: stat -c '%Y' is GNU-only
**Section:** Staleness Detection, Alternative A (plan line 209)
**Severity:** P1

`stat -c '%Y'` is a GNU coreutils flag. On macOS/BSD, the equivalent is `stat -f '%m'`. If any Codex agents or CI runners execute this on macOS, it fails silently -- `stat -c` on BSD `stat` is not a valid flag combination and exits non-zero, but stderr is suppressed by `2>/dev/null`. The `2>/dev/null` suppression makes this particularly insidious -- the pipeline silently returns empty results, and staleness detection concludes "nothing changed."

### P1-3: find results for DISPATCH and REVIEW_TEMPLATE are unguarded
**Section:** Path Resolution (plan lines 104-108)
**Severity:** P1

If `find` returns no results for both the plugin cache and local project searches, `$DISPATCH` and `$REVIEW_TEMPLATE` are empty strings. The subsequent `bash "$DISPATCH" --template "$REVIEW_TEMPLATE" ...` executes `bash "" --template "" ...`, which fails with an unhelpful error message. No explicit guard or fatal check exists after the resolution block.

### P1-4: ls -t piped to tail for oldest file is fragile
**Section:** Staleness Detection, Alternative A (plan line 207)
**Severity:** P1

`ls -t .claude/agents/fd-*.md 2>/dev/null | tail -1` has two failure modes: (a) if no `fd-*.md` files match the glob, `ls` outputs nothing and `$OLDEST_AGENT` is empty, causing `stat -c '%Y' ""` to fail; (b) filenames containing newlines (rare but possible) would cause `tail -1` to return a truncated path.

### P1-5: Predictable temp file paths with no cleanup
**Section:** Codex Dispatch Invocation (plan lines 133, 140-142)
**Severity:** P1

The plan uses `/tmp/flux-codex-{agent-name}.md` as prompt file paths. These are predictable and not unique per invocation. Concurrent flux-drive runs would overwrite each other's prompt files. There is no cleanup step -- temp files accumulate indefinitely in `/tmp`.

### P2-1: Inconsistent use of [ ] vs [[ ]]
**Section:** Clodex Mode Detection (plan line 84)
**Severity:** P2

The detection snippet uses `[ -f "..." ]` (POSIX test) while the existing `autopilot.sh` and `dispatch.sh` use `[[ ]]` (bash conditional). This is not a bug -- `[ -f ]` works fine -- but inconsistency within a project invites confusion about which shell features are acceptable.

### P2-2: --inject-docs may be redundant for review agents with full prompt context
**Section:** Codex Dispatch Invocation (plan line 144)
**Severity:** P2

The `--inject-docs` flag prepends `CLAUDE.md` to the prompt. Review agents already receive project context via the `{{PROJECT}}` template variable. Injecting `CLAUDE.md` adds token overhead that may be unnecessary. For large `CLAUDE.md` files (>20KB, which triggers dispatch.sh's own warning), this could push prompts past optimal size.

### P2-3: find traversals lack maxdepth constraint
**Section:** Path Resolution (plan lines 104-108)
**Severity:** P2

The `find` commands search `~/.claude/plugins/cache` and `~/projects/Clavain` without `-maxdepth`. The plugin cache can contain many plugin versions with deep directory trees. Adding `-maxdepth 8` (or similar) would prevent unnecessary traversal without affecting correctness.

## Improvements Suggested

### IMP-1: Add fatal guard after path resolution find commands

After the fallback `find` chain for both `DISPATCH` and `REVIEW_TEMPLATE`, add an explicit failure:
```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' -maxdepth 8 2>/dev/null | head -1)
[ -z "$DISPATCH" ] && DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' -maxdepth 4 2>/dev/null | head -1)
[ -z "$DISPATCH" ] && { echo "ERROR: dispatch.sh not found in plugin cache or ~/projects/Clavain" >&2; exit 1; }
```

### IMP-2: Replace xargs stat pipeline with find -newer for staleness check

Instead of the fragile `find | xargs stat | awk` pipeline, use `find -newer` which is POSIX-compliant and handles all filenames safely:
```bash
OLDEST_AGENT=$(find .claude/agents -maxdepth 1 -name 'fd-*.md' -print 2>/dev/null | head -1)
if [ -n "$OLDEST_AGENT" ]; then
  CHANGED=$(find . \( -name "CLAUDE.md" -o -name "AGENTS.md" \) -newer "$OLDEST_AGENT" -print 2>/dev/null | head -5)
fi
```
This is POSIX-compliant, handles spaces in filenames, and avoids the `stat -c` portability issue entirely.

### IMP-3: Use mktemp for prompt files instead of predictable /tmp paths

Replace `/tmp/flux-codex-{agent-name}.md` with:
```bash
prompt_file="$(mktemp "/tmp/flux-codex-${agent_name}-XXXXXX.md")"
```
This prevents collisions between concurrent runs and eliminates the symlink attack vector on shared systems.

### IMP-4: Add trap-based cleanup for temp files

Add a cleanup step in Phase 3 (after synthesis reads all results) or use a temp directory:
```bash
FLUX_TMPDIR="$(mktemp -d /tmp/flux-codex-XXXXXX)"
trap 'rm -rf "$FLUX_TMPDIR"' EXIT
# Then use $FLUX_TMPDIR/agent-name.md for prompt files
```
This ensures cleanup even if the orchestrating session crashes.

### IMP-5: Use git-based staleness check exclusively

The plan already provides a git-based alternative (lines 213-218) that is simpler, more robust, and avoids all the filesystem timestamp issues. Drop Alternative A (the stat pipeline) entirely and use only the git approach. Add validation of the stored commit hash:
```bash
AGENTS_COMMIT=$(cat .claude/agents/.fd-agents-commit 2>/dev/null)
if [ -z "$AGENTS_COMMIT" ] || ! git cat-file -e "$AGENTS_COMMIT" 2>/dev/null; then
  # Commit unknown or invalid -- force regeneration
  REGENERATE=true
else
  if ! git diff --quiet "$AGENTS_COMMIT"..HEAD -- CLAUDE.md AGENTS.md docs/ARCHITECTURE.md 2>/dev/null; then
    REGENERATE=true
  fi
fi
```

### IMP-6: Make --inject-docs conditional on agent type

For Tier 1 and Tier 2 agents that already receive rich project context in the `{{PROJECT}}` and `{{AGENT_IDENTITY}}` template variables, consider omitting `--inject-docs` to save tokens. For Tier 3 generic agents that lack project context in their identity, `--inject-docs` adds genuine value. The dispatch invocation could be:
```bash
# Tier 3: generic agent, needs project context injection
bash "$DISPATCH" --template "$REVIEW_TEMPLATE" --prompt-file "$prompt_file" \
  -C "$PROJECT_ROOT" -o "$output_file" -s workspace-write --inject-docs

# Tier 1/2: already has project context in agent identity
bash "$DISPATCH" --template "$REVIEW_TEMPLATE" --prompt-file "$prompt_file" \
  -C "$PROJECT_ROOT" -o "$output_file" -s workspace-write
```

## Overall Assessment

The plan's dispatch architecture is sound. The flag interface matches `dispatch.sh` correctly, the template/task-description key format aligns with the parser's regex, and the clodex detection is clean. The two areas that need changes before implementation are: (1) dropping the stat-based staleness detection in favor of the git-based approach (which the plan already offers as an alternative), and (2) adding guards for empty `find` results and using `mktemp` for temp files. These are straightforward fixes that do not change the plan's architecture. Verdict: **needs-changes** -- all issues are fixable without redesign.
