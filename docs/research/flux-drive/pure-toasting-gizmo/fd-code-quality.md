---
agent: fd-code-quality
tier: 1
issues:
  - id: P1-1
    severity: P1
    section: "Change 1 — review-agent.md template"
    title: "Template placeholder naming inconsistent with existing templates"
  - id: P1-2
    severity: P1
    section: "Change 3 — Staleness check script"
    title: "Staleness check bash uses non-portable stat flags and fragile pipeline"
  - id: P1-3
    severity: P1
    section: "Change 2 — Codex dispatch path"
    title: "Task description uses mixed-case section headers breaking dispatch.sh template parser"
  - id: P1-4
    severity: P1
    section: "Change 3 — create-review-agent.md template"
    title: "Template uses lowercase {{PROJECT}} inconsistently and omits Constraints boilerplate"
  - id: P2-1
    severity: P2
    section: "Change 2 — Codex dispatch path"
    title: "Step numbering uses unconventional 2.1-codex format"
  - id: P2-2
    severity: P2
    section: "Change 1 — review-agent.md template"
    title: "Template lacks Phase structure and Final Report section present in all other templates"
  - id: P2-3
    severity: P2
    section: "Change 3 — Staleness check script"
    title: "Two staleness heuristics presented without a clear recommendation on which to implement"
improvements:
  - id: IMP-1
    title: "Align review-agent.md placeholder names to UPPER_SNAKE_CASE matching dispatch.sh parser"
    section: "Change 1 — review-agent.md template"
  - id: IMP-2
    title: "Add a Constraints section matching existing template patterns (no commit, no push, no reformat)"
    section: "Change 1 — review-agent.md template"
  - id: IMP-3
    title: "Replace stat -c with a portable alternative or use the git-based heuristic exclusively"
    section: "Change 3 — Staleness check script"
  - id: IMP-4
    title: "Standardize step numbering to Step 2.2 instead of Step 2.1-codex"
    section: "Change 2 — Codex dispatch path"
  - id: IMP-5
    title: "Add Final Report / verdict section to review-agent.md template for consistency"
    section: "Change 1 — review-agent.md template"
verdict: needs-changes
---

## Summary

The plan proposes a well-scoped integration of Codex dispatch into the flux-drive skill. The overall architecture (flag detection, parallel background dispatch, template-based prompts) is sound and aligns with how clodex already works. However, there are several naming and convention inconsistencies that would cause runtime failures or maintenance friction if shipped as-is. The most critical are: (1) the new `review-agent.md` template uses `{{Mixed_Case}}` placeholder names that are incompatible with `dispatch.sh`'s `^[A-Z_]+:$` section parser, (2) the staleness check bash snippets use GNU-specific `stat -c` without a portable fallback, and (3) the `create-review-agent.md` template deviates from the structural conventions established by `megaprompt.md` and `parallel-task.md`. All issues are fixable with targeted adjustments.

## Section-by-Section Review

### Change 1: review-agent.md Template

**Placeholder naming (P1-1)**

The existing templates use `UPPER_SNAKE_CASE` placeholders exclusively:
- `megaprompt.md`: `{{GOAL}}`, `{{EXPLORE_TARGETS}}`, `{{IMPLEMENT}}`, `{{BUILD_CMD}}`, `{{TEST_CMD}}`
- `parallel-task.md`: `{{PROJECT}}`, `{{TASK}}`, `{{FILES}}`, `{{BUILD_CMD}}`, `{{TEST_CMD}}`, `{{CRITERIA}}`

The proposed `review-agent.md` uses:
- `{{PROJECT}}` -- matches existing convention
- `{{AGENT_IDENTITY}}` -- matches convention
- `{{REVIEW_PROMPT}}` -- matches convention
- `{{OUTPUT_FILE}}` -- matches convention
- `{{AGENT_NAME}}` -- matches convention
- `{{TIER}}` -- matches convention

The placeholder names themselves are actually `UPPER_SNAKE_CASE`, so they are syntactically compatible. However, in the task description section of the plan (Change 2), the section headers used to populate these placeholders are written as mixed-case labels like `AGENT_IDENTITY:`, `REVIEW_PROMPT:`, `AGENT_NAME:`, `OUTPUT_FILE:`, and `TIER:`. These *do* match the `^[A-Z_]+:$` regex in `dispatch.sh` line 204. I initially flagged this as a mismatch, but on closer inspection, the keys are all uppercase with underscores. The real issue is subtler: the task description in Change 2 also includes headers like `PROJECT:` with trailing content on the same line (`{project name} -- review task (read-only)`). The dispatch.sh parser expects the header line to contain ONLY the key followed by a colon (e.g., `PROJECT:` on its own line, with the value on subsequent lines). The plan's example puts the value on the same line as the header, which would cause the parser to capture an empty value and lose the inline content.

**Structural deviation (P2-2)**

Both existing templates follow a clear pattern:
- `megaprompt.md`: Goal, Phase 1 (Explore), Phase 2 (Implement), Phase 3 (Verify), Final Report, Constraints
- `parallel-task.md`: Task, Relevant Files, Success Criteria, Constraints, Environment

The proposed `review-agent.md` has: Project, Your Agent Identity, Review Task, Output, Constraints. It omits:
- No Phase structure (Explore/Analyze/Write) that would mirror megaprompt's Explore/Implement/Verify
- No Final Report/Verdict section (megaprompt has `VERDICT: CLEAN | NEEDS_ATTENTION`)
- The Constraints section exists but is much shorter than the other templates

For review tasks, a phased structure would improve reliability: Phase 1 (Explore the codebase), Phase 2 (Analyze against the review prompt), Phase 3 (Write findings to output file). A verdict line in the output would also help flux-drive's synthesis step detect whether the agent completed successfully.

**Missing boilerplate in Constraints**

The existing templates include specific protective constraints:
- "Do not reformat unchanged code"
- "Keep it minimal"
- "Do NOT commit or push"

The review template includes "Do NOT modify any source code" and "Do NOT commit or push" but is missing the explicit minimal-output guidance. For a review template this is less critical, but the "Be concrete -- reference specific sections, lines, files" directive currently appears after the Constraints heading, mixing behavioral guidance with hard constraints.

### Change 2: Codex Dispatch Path in flux-drive SKILL.md

**Step numbering (P2-1)**

The plan introduces `Step 2.1.1` and `Step 2.1-codex` as new step names. The existing flux-drive SKILL.md uses a clean hierarchical numbering:
- Step 1.0, 1.1, 1.2, 1.3 (Phase 1)
- Step 2.0, 2.1 (Phase 2)
- Step 3.0, 3.1, 3.2, 3.3, 3.4, 3.5 (Phase 3)
- Step 4.1, 4.2, 4.3, 4.4, 4.5 (Phase 4)

`Step 2.1-codex` breaks this pattern. A cleaner approach would be to restructure Phase 2 as:
- Step 2.0: Prepare output directory (unchanged)
- Step 2.1: Detect dispatch mode (the flag check)
- Step 2.2: Launch agents (Task dispatch -- existing content, conditional on CLODEX_MODE=false)
- Step 2.3: Launch agents (Codex dispatch -- new content, conditional on CLODEX_MODE=true)

This preserves the integer hierarchy.

**Task description format (P1-3)**

As noted above, the task description example in the plan shows values on the same line as the header:

```
PROJECT:
{project name} -- review task (read-only)
```

This is actually fine -- the value is on the next line. But looking more carefully at the plan's example block:

```markdown
PROJECT:
{project name} -- review task (read-only)

AGENT_IDENTITY:
{paste the agent's system prompt / description from the agent .md file}
```

This format IS compatible with dispatch.sh's parser. The parser reads `^[A-Z_]+:$` and accumulates all subsequent lines until the next header. The blank lines between sections are trimmed. So this is correct. I'm downgrading the concern -- the format works.

However, there is still a real issue: the plan does not mention that flux-drive needs to write these section headers as separate lines. If a future editor of the SKILL.md puts the value on the same line as the header (e.g., `PROJECT: my-project`), the parser would miss it entirely because it matches `^([A-Z_]+):$` (the colon must be at end-of-line). The SKILL.md should include a note: "Each section header (PROJECT:, AGENT_IDENTITY:, etc.) must be on its own line with no trailing text."

**Path resolution duplication**

The path resolution block for `DISPATCH` and `REVIEW_TEMPLATE` duplicates the same `find` pattern already in the clodex SKILL.md's Step 0. This is not an error -- flux-drive needs to resolve paths independently since it may be invoked without loading clodex. But it would be cleaner to note that this is deliberately duplicated for independence.

### Change 3: create-review-agent.md Template and Staleness Check

**Staleness check bash quality (P1-2)**

The plan presents two staleness heuristics. The first uses `stat -c '%Y'`:

```bash
OLDEST_AGENT=$(ls -t .claude/agents/fd-*.md 2>/dev/null | tail -1)
CHANGED=$(find . -name "CLAUDE.md" -o -name "AGENTS.md" -o -name "*.go" \
  -o -name "*.py" -o -name "*.ts" -o -name "*.rs" \
  | xargs stat -c '%Y %n' 2>/dev/null \
  | awk -v ref="$(stat -c '%Y' "$OLDEST_AGENT")" '$1 > ref {print $2}')
```

Issues:
1. `stat -c` is GNU coreutils syntax. On macOS/BSD, the equivalent is `stat -f '%m'`. While the project runs on Linux (the env says `linux`), Clavain is a plugin that users install on any platform. Portable bash should use `date -r` or test with `[ file1 -nt file2 ]`.
2. `ls -t ... | tail -1` parses `ls` output, which is fragile with filenames containing newlines or special characters. The fd-* agent names are controlled (kebab-case), so this is low-risk in practice, but it is still a code quality anti-pattern.
3. The `find` command uses `-o` without grouping parentheses, which means the implicit `-print` only applies to the last `-name` clause. This is a common `find` gotcha. It should be `find . \( -name "CLAUDE.md" -o -name "AGENTS.md" -o ... \) -print`.
4. The `xargs stat` pipeline silently swallows errors with `2>/dev/null`, making debugging difficult.

The second (git-based) heuristic is cleaner:

```bash
cat .claude/agents/.fd-agents-commit 2>/dev/null  # e.g. "abc123"
git rev-parse HEAD                                  # e.g. "def456"
git diff --stat abc123..HEAD -- CLAUDE.md AGENTS.md docs/ARCHITECTURE.md
```

This is portable, reliable, and leverages git (which is guaranteed to exist since clodex requires a `.git` root). The plan should recommend this approach exclusively and drop the `stat`-based heuristic.

**Two heuristics without resolution (P2-3)**

The plan presents both approaches as alternatives ("Simpler heuristic:") but does not specify which one the implementation should use. The SKILL.md needs a single definitive approach. The git-based approach is clearly better (portable, deterministic, uses the commit hash already stored by the creation agent).

**create-review-agent.md template (P1-4)**

The template uses `{{PROJECT}}` which matches the convention. But it lacks several elements present in the other templates:

1. No Constraints section matching the pattern in `megaprompt.md` and `parallel-task.md`. The constraints are embedded inline ("Create 2-3 agents, no more", "Do NOT commit or push") but not under a `## Constraints` heading.
2. No Final Report / verdict output format. The creation agent should report what it created so flux-drive can verify.
3. The template includes a bash code block for writing `.fd-agents-commit`, but this is a raw `git rev-parse HEAD` redirect. It should use error handling: `git rev-parse HEAD > .claude/agents/.fd-agents-commit 2>/dev/null || echo "unknown"`.

### Change 4: See Also Reference

This is a one-line addition and follows the existing pattern in the Integration section of flux-drive SKILL.md. No issues.

### Agent File Naming Conventions

The plan proposes creating Tier 2 agents as `.claude/agents/fd-*.md` with kebab-case names starting with `fd-`. This is consistent with:
- Existing Tier 1 agents: `fd-architecture`, `fd-code-quality`, `fd-performance`, `fd-security`, `fd-user-experience`
- The `fd-` prefix convention is preserved
- kebab-case naming matches AGENTS.md conventions

The creation template correctly specifies `fd-{domain}` format. No naming issues here.

## Issues Found

**P1-1: Template placeholder naming / task description format risk**
The task description format in Change 2 is technically compatible with `dispatch.sh`, but the SKILL.md should explicitly document that section headers must be on their own line (matching `^[A-Z_]+:$`). Without this note, future edits could easily break the template assembly. The template itself correctly uses `UPPER_SNAKE_CASE` placeholders.

**P1-2: Staleness check uses non-portable bash**
The `stat -c` syntax is GNU-only. The `find` command lacks grouping parentheses. The `ls | tail` pattern is fragile. The git-based alternative in the same section is superior and should be the sole approach.

**P1-3: Task description inline value risk**
The plan's task description example could be misinterpreted by someone reading the SKILL.md as allowing `KEY: value` on a single line. The dispatch.sh parser requires `KEY:` alone on the line. A clarifying note is needed.

**P1-4: create-review-agent.md template structural gaps**
Missing `## Constraints` heading (breaks template pattern), no final report format, and the git command lacks error handling.

**P2-1: Unconventional step numbering**
`Step 2.1-codex` breaks the integer hierarchy used throughout the rest of the SKILL.md.

**P2-2: review-agent.md lacks Phase structure**
No Explore/Analyze/Write phases or Final Report, deviating from the patterns established by megaprompt.md and parallel-task.md.

**P2-3: Two staleness heuristics without recommendation**
Both the file-timestamp and git-commit approaches are presented as alternatives. The implementation needs exactly one.

## Improvements Suggested

**IMP-1: Align placeholder naming and add parser documentation**
In the flux-drive SKILL.md Codex dispatch section, add a note: "Each section header (PROJECT:, AGENT_IDENTITY:, etc.) must be on its own line with the colon at end-of-line. Values go on subsequent lines. This matches dispatch.sh's `^[A-Z_]+:$` parser." The template placeholders themselves are already correctly named.

**IMP-2: Add Constraints section to review-agent.md following existing pattern**
Move the inline constraints into a proper `## Constraints (ALWAYS INCLUDE)` section, mirroring `parallel-task.md`:
```markdown
## Constraints (ALWAYS INCLUDE)
- Do NOT modify any source code
- Do NOT commit or push
- ONLY create the output file specified above
- Read files as needed to inform your review
- Be concrete -- reference specific sections, lines, files
```

**IMP-3: Use git-based staleness check exclusively**
Drop the `stat -c` / `find` / `xargs` pipeline. Use only:
```bash
AGENTS_COMMIT=$(cat .claude/agents/.fd-agents-commit 2>/dev/null || echo "")
if [ -z "$AGENTS_COMMIT" ]; then
  # No commit recorded -- regenerate
  STALE=true
else
  DIFF=$(git diff --stat "$AGENTS_COMMIT"..HEAD -- CLAUDE.md AGENTS.md docs/ARCHITECTURE.md 2>/dev/null || echo "error")
  if [ -n "$DIFF" ]; then
    STALE=true
  fi
fi
```

**IMP-4: Use integer step numbering**
Rename `Step 2.1.1` to `Step 2.1` (Detect dispatch mode), existing Step 2.1 to `Step 2.2` (Task dispatch), and `Step 2.1-codex` to `Step 2.3` (Codex dispatch).

**IMP-5: Add Phase structure and Final Report to review-agent.md**
Restructure the template body to include:
```markdown
## Phase 1: Explore
Read the project's CLAUDE.md and AGENTS.md. Examine the files relevant to your focus area.

## Phase 2: Analyze
Apply your agent identity and review prompt to the document/codebase. Identify issues and improvements.

## Phase 3: Write Report
Write your findings to: {{OUTPUT_FILE}}
[YAML frontmatter format]

## Final Report
After writing the file, confirm:
AGENT: {{AGENT_NAME}}
OUTPUT: {{OUTPUT_FILE}}
VERDICT: COMPLETE | INCOMPLETE [reason]
```

This mirrors megaprompt.md's Explore/Implement/Verify/Final Report structure.

## Overall Assessment

The plan is architecturally sound -- the flag-based detection, parallel Codex dispatch via background Bash, and template-based prompting all follow established patterns in the codebase. The issues found are all in the details: naming conventions, bash portability, structural consistency with existing templates, and ambiguity in the staleness check approach. None of these are blocking design problems; they are P1/P2 polish items that should be addressed before implementation to avoid runtime failures (especially P1-2 and P1-3) and to maintain the high consistency standard the Clavain codebase currently achieves. Verdict: **needs-changes** -- address the P1 items before implementing.
