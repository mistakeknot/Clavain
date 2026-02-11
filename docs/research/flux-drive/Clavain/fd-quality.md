### Findings Index
- P1 | P1-1 | "Naming Conventions" | Command frontmatter name uses underscore instead of kebab-case
- P1 | P1-2 | "Documentation Accuracy" | Hook count and event documentation out of sync with hooks.json
- P1 | P1-3 | "Test Coverage Gaps" | Missing skill name-matches-dirname and command name-matches-filename tests
- P2 | P2-1 | "Shell Script Quality" | check-versions.sh uses weaker strict mode and non-portable shebang
- P2 | P2-2 | "Test Code Duplication" | _parse_frontmatter duplicated across three test modules
- P2 | P2-3 | "Shell Script Quality" | auto-compound.sh uses unescaped heredoc interpolation for JSON output
- IMP | IMP-1 | "Format Divergence" | fd-* agent system prompts lack any output format specification (independently confirmed)
- IMP | IMP-2 | "Documentation Accuracy" | README skills table lists 31 skills, not the claimed 34
Verdict: needs-changes

---

### Summary

The Clavain plugin maintains strong structural consistency across its 70+ component files. Skill directories all use kebab-case and match their frontmatter names. Agent files follow a uniform template with description, model, and example blocks. The 3-tier test suite (427 structural tests, shell bats tests, smoke tests) catches many regressions. However, the review found one concrete naming violation (`generate_command` vs `generate-command`), a documentation drift where hooks.json has 4 event types and 5 hook scripts but all docs claim "3 hooks," missing structural tests for two of the three component types' name-to-file matching, and a shell script that deviates from the project's own strict-mode convention.

---

### Issues Found

#### P1-1: Command frontmatter name uses underscore instead of kebab-case

**File:** `/root/projects/Clavain/commands/generate-command.md`, line 2

The file `generate-command.md` declares `name: generate_command` (underscore) while the filename uses `generate-command` (kebab-case). Every other command in the project uses kebab-case in both the filename and the frontmatter `name` field. This mismatch means the slash command registers as `/clavain:generate_command` rather than `/clavain:generate-command`, which breaks the naming convention documented in AGENTS.md (line 103: "Command `.md` files in `commands/`" with kebab-case examples).

The existing test suite does NOT catch this because `test_commands.py` has `test_command_filenames_kebab_case` (checks the filename) and `test_command_frontmatter_required_fields` (checks that `name` exists) but does NOT have a `test_command_name_matches_filename` test. Compare with `test_agents.py` which DOES have `test_agent_name_matches_filename` at line 84.

**Fix:** Change line 2 of `commands/generate-command.md` from `name: generate_command` to `name: generate-command`.

---

#### P1-2: Hook count and event documentation out of sync with hooks.json

**Files:**
- `/root/projects/Clavain/hooks/hooks.json` (source of truth)
- `/root/projects/Clavain/CLAUDE.md`, line 7
- `/root/projects/Clavain/AGENTS.md`, line 12
- `/root/projects/Clavain/README.md`, lines 7 and 187-191
- `/root/projects/Clavain/.claude-plugin/plugin.json`, line 4

`hooks.json` registers 4 event types (PreToolUse, SessionStart, Stop, SessionEnd) backed by 5 hook scripts (autopilot.sh, session-start.sh, agent-mail-register.sh, auto-compound.sh, dotfiles-sync.sh). All documentation surfaces say "3 hooks" and the README's "Hooks (3)" section at lines 187-191 only documents PreToolUse, SessionStart, and SessionEnd -- completely omitting the `Stop` event and `auto-compound.sh`.

Additionally, AGENTS.md (which is the development guide) does not mention the `Stop` hook, `auto-compound.sh`, or the `auto-compound` concept anywhere. This means a contributor reading AGENTS.md to understand the hook system will not know that a Stop hook exists.

**Fix:** Update the hook count to "5 hooks" (counting scripts) or "4 hook events" across all documentation surfaces. Add a bullet for the Stop hook in README.md's hooks section. Document `auto-compound.sh` in AGENTS.md's hooks section.

---

#### P1-3: Missing skill name-matches-dirname and command name-matches-filename structural tests

**Files:**
- `/root/projects/Clavain/tests/structural/test_skills.py`
- `/root/projects/Clavain/tests/structural/test_commands.py`

The agent test module (`test_agents.py`) includes `test_agent_name_matches_filename` (line 84) that verifies `fm["name"] == agent_file.stem`. Neither `test_skills.py` nor `test_commands.py` have an equivalent test.

For skills, this means a skill with `name: wrong-name` in a directory named `correct-name/` would pass all existing tests. For commands, this is exactly what happened with P1-1 -- the `generate_command` / `generate-command` mismatch was not caught.

Both test files already have the `_parse_frontmatter` helper and parametrized fixtures needed to add these tests. The skill version would assert `fm["name"] == skill_dir.name` and the command version would assert `fm["name"] == cmd_file.stem`.

**Fix:** Add `test_skill_name_matches_dirname` to `test_skills.py` and `test_command_name_matches_filename` to `test_commands.py`, following the pattern from `test_agents.py` lines 84-93.

---

### P2-1: check-versions.sh uses weaker strict mode and non-portable shebang

**File:** `/root/projects/Clavain/scripts/check-versions.sh`, lines 1 and 6

This script uses `#!/bin/bash` (hardcoded path) instead of `#!/usr/bin/env bash` (portable, used by all other scripts in the repo). It also uses `set -e` alone instead of `set -euo pipefail` (used by every other hook and script).

The weaker `set -e` (without `-u` and `-o pipefail`) means:
- Unset variable references silently expand to empty strings instead of failing
- Pipe failures are masked (only the exit code of the last command in a pipe is checked)

The structural test `test_hook_entry_points_have_set_euo_pipefail` only covers hook entry points, not scripts in `scripts/`. This script falls through the test gap.

**Fix:** Change line 1 to `#!/usr/bin/env bash` and line 6 to `set -euo pipefail`. Verify no unquoted variable expansions rely on the permissive behavior.

---

### P2-2: _parse_frontmatter duplicated across three test modules

**Files:**
- `/root/projects/Clavain/tests/structural/test_skills.py`, line 10
- `/root/projects/Clavain/tests/structural/test_agents.py`, line 9
- `/root/projects/Clavain/tests/structural/test_commands.py`, line 10

The identical `_parse_frontmatter(path)` function (split on `---`, yaml.safe_load the middle section, return tuple) is copy-pasted across all three test modules. If the frontmatter parsing logic needs to change (e.g., handling edge cases in YAML parsing), it must be updated in three places.

`conftest.py` already provides shared fixtures for paths and file lists but does not provide a shared frontmatter parser.

**Fix:** Move `_parse_frontmatter` to `conftest.py` (or a `helpers.py` module in the test directory) and import it in all three test files.

---

### P2-3: auto-compound.sh uses unescaped heredoc interpolation for JSON output

**File:** `/root/projects/Clavain/hooks/auto-compound.sh`, lines 81-86

```bash
cat <<EOF
{
  "decision": "block",
  "reason": "${REASON}"
}
EOF
```

The `$REASON` variable is interpolated into an unquoted heredoc (`<<EOF`, not `<<'EOF'`). While `REASON` currently contains only a hardcoded string with controlled `$SIGNALS` values (commit, resolution, investigation, bead-closed, insight), the pattern is fragile. If the string ever contains a double-quote, backslash, or dollar sign, the JSON output breaks.

Compare with `autopilot.sh` which handles this correctly: it uses `jq` for JSON construction when available and falls back to a heredoc with single-quoted delimiter (`<<'ENDJSON'`) containing only static text.

The practical risk is low today since `SIGNALS` only takes hardcoded values. But this diverges from the safer pattern already established in the same codebase.

**Fix:** Use `jq -n --arg` for JSON construction (like autopilot.sh), or at minimum use `escape_for_json` from `lib.sh` on `REASON` before interpolation.

---

### Improvements Suggested

#### IMP-1: fd-* agent system prompts lack any output format specification (independently confirmed)

**Files:** All 6 fd-* agent files under `/root/projects/Clavain/agents/review/`:
- `fd-architecture.md`
- `fd-safety.md`
- `fd-correctness.md`
- `fd-quality.md`
- `fd-user-product.md`
- `fd-performance.md`

**Observation (independently confirmed):** The fd-* agent system prompts define review approach and focus areas but contain zero specification of the expected output format (Findings Index, severity levels, verdict, section structure). The output format is defined only in `skills/flux-drive/phases/shared-contracts.md` and injected at runtime by the flux-drive orchestrator.

This means:
1. When these agents are dispatched outside flux-drive (e.g., via `/clavain:review` or `/clavain:quality-gates`), they have no output format guidance and will produce freeform output
2. The agents are entirely dependent on the caller to inject format requirements, creating a tight coupling between the agent and its dispatcher
3. Any new dispatcher that invokes these agents must know to inject the shared-contracts format

This is the "Documentation-implementation format divergence" pattern from the knowledge context. I independently confirmed it by reading all six fd-* agent files and verifying none contain references to "Findings Index," "verdict," "P0/P1/P2," or the `.md.partial` completion protocol.

**Suggestion:** Add a minimal output format section to each fd-* agent system prompt that defines the Findings Index structure, severity levels, and completion protocol. The flux-drive orchestrator can still override or supplement this, but the agents should be self-contained enough to produce structured output when dispatched from any context.

---

#### IMP-2: README skills table lists 31 skills, not the claimed 34

**File:** `/root/projects/Clavain/README.md`, lines 99-142

The skills table in the README lists skills in named groups (Core Lifecycle, Code Discipline, Multi-Agent, Cross-AI, Knowledge & Docs, Plugin Development, Utilities). Counting the individual skills listed gives 31 entries. The missing skills from the full set of 34 are:

- `prompterpeer` (cross-AI prompt optimization)
- `splinterpeer` (cross-AI disagreement mining)
- `winterpeer` (LLM council review)

These three peer review skills are part of the interpeer stack but are not listed individually in the README table. The README describes `interpeer` with its 4 modes (quick, deep, council, mine), but the individual skill files for `prompterpeer`, `splinterpeer`, and `winterpeer` exist in the skills directory and are counted toward the "34 skills" claim. Either add them to the table or note that they are sub-skills of interpeer.

---

### Overall Assessment

Clavain demonstrates strong quality discipline for a 70+ component plugin: consistent kebab-case naming, uniform frontmatter structure, comprehensive test coverage, and clean namespace migration. The issues found are concrete and fixable -- one naming violation, one documentation drift from a recent hook addition, and test coverage gaps that mirror the naming bug they failed to catch. The shell scripts are well-structured with proper strict mode, with one exception. The main improvement opportunity is making the fd-* agents self-contained with respect to output format, reducing their dependency on caller-injected contracts.

<!-- flux-drive:complete -->
