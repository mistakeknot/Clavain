---
name: engineering-docs
description: Use when capturing a solved problem as categorized documentation with YAML frontmatter for fast lookup
allowed-tools:
  - Read # Parse conversation context
  - Write # Create resolution docs
  - Bash # Create directories
  - Grep # Search existing docs
preconditions:
  - Problem has been solved (not in-progress)
  - Solution has been verified working
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same 7-step documentation capture workflow in a single file. -->

# engineering-docs Skill

**Purpose:** Document solved problems as searchable institutional knowledge in category-organized single-file markdown with enum-validated YAML frontmatter.

---

## 7-Step Documentation Capture

### Step 1: Detect Confirmation

Auto-invoke after: "that worked", "it's fixed", "working now", "problem solved", "that did it" — OR via `/clavain:compound`.

**Non-trivial only** (multiple attempts, tricky debugging, non-obvious solution). Skip typos, obvious syntax errors, trivial fixes.

### Step 2: Gather Context

Extract from conversation:
- **Module name**, **symptom** (exact error), **investigation attempts**, **root cause**, **solution**, **prevention**
- Env details: language/framework version, OS, file:line refs

**BLOCKING:** If module name, exact error, or resolution steps are missing, ask and WAIT:
```
I need a few details to document this properly:
1. Which module had this issue? [ModuleName]
2. What was the exact error message or symptom?
[Continue after user provides details]
```

### Step 3: Check Existing Docs

```bash
grep -r "exact error phrase" docs/solutions/
ls docs/solutions/[category]/
```

If similar found, present and WAIT:
```
Found similar issue: docs/solutions/[path]
1. Create new doc with cross-reference (recommended)
2. Update existing doc (only if same root cause)
3. Other
Choose (1-3): _
```

If no match, proceed to Step 4 without user interaction.

### Step 4: Generate Filename

Format: `[sanitized-symptom]-[module]-[YYYYMMDD].md` — lowercase, hyphens for spaces, no special chars, <80 chars.

Examples: `missing-include-BriefSystem-20251110.md`, `webview-crash-on-resize-Assistant-20251110.md`

### Step 5: Validate YAML Schema (Blocking)

Load `schema.yaml` and classify against enums in [yaml-schema.md](./references/yaml-schema.md). All required fields must be present and match allowed values exactly.

**BLOCK until valid:**
```
❌ YAML validation failed
Errors:
- problem_type: must be one of schema enums, got "compilation_error"
- severity: must be one of [critical, high, medium, low], got "invalid"
- symptoms: must be array with 1-5 items, got string
Please provide corrected values.
```

### Step 6: Create Documentation

- Determine category from problem_type using mapping in [yaml-schema.md](./references/yaml-schema.md) (lines 49-61)
- `mkdir -p "docs/solutions/${CATEGORY}"` then write file using `assets/resolution-template.md`
- **Provenance fields** (always include): `lastConfirmed` (YYYY-MM-DD), `provenance` (`independent` or `primed`), `review_count: 0`

### Step 7: Cross-Reference & Critical Pattern Detection

If similar issues found in Step 3, add `- See also: [$FILENAME]($REAL_FILE)` to the similar doc.

If 3+ similar issues exist, append to `docs/solutions/patterns/common-solutions.md`:
```
## [Pattern Name]
**Common symptom:** [Description]
**Root cause:** [Technical explanation]
**Solution pattern:** [General approach]
**Examples:** [links]
```

**Critical pattern hint** (if severity=critical, affects multiple modules or foundational stage, non-obvious): add note in decision menu — `💡 This might be worth adding to Required Reading (Option 2)`. **NEVER auto-promote.**

When user selects Option 2, use `assets/critical-pattern-template.md` and number sequentially in `docs/solutions/patterns/critical-patterns.md`.

---

## Decision Menu After Capture

Present and WAIT for response:
```
✓ Solution documented
File: docs/solutions/[category]/[filename].md

What's next?
1. Continue workflow (recommended)
2. Add to Required Reading — promote to critical-patterns.md
3. Link related issues
4. Add to existing skill
5. Create new skill
6. View documentation
7. Other
```

**Option 1:** Return to calling workflow.

**Option 2:** Extract pattern → format as ❌ WRONG / ✅ CORRECT with code → add to `docs/solutions/patterns/critical-patterns.md` → cross-reference → confirm.

**Option 3:** Prompt for filename/description → search → add cross-reference to both docs → confirm.

**Option 4:** Prompt for skill name → determine which reference file (resources.md, patterns.md, examples.md) → add link + description → confirm.

**Option 5:** Prompt for skill name → create skill directory + SKILL.md → create reference files with this solution → confirm.

**Option 6:** Display created doc → present menu again.

**Option 7:** Ask what they'd like to do.

---

## Integration Points

- Invoked by: `/clavain:compound`, manual trigger, confirmation phrase detection
- Invokes: nothing (terminal skill)
- All context must be in conversation history before invocation

---

## Success Criteria

- YAML frontmatter validated (all required fields, correct formats)
- File created in `docs/solutions/[category]/[filename].md`
- Enum values match `schema.yaml` exactly
- Code examples in solution section
- Cross-references added if related issues found
- User presented with decision menu and action confirmed

## Error Handling

| Error | Action |
|---|---|
| Missing context | Ask user, don't proceed until critical info provided |
| YAML validation failure | Show specific errors, BLOCK until valid |
| Similar issue ambiguity | Present matches, let user choose |
| Module not in docs | Warn but don't block; suggest adding |

## Quality Checklist

**Good:** exact error messages, file:line refs, observable symptoms, failed attempts, technical explanation (why not just what), code examples, prevention guidance, cross-references.

**Bad:** vague descriptions, missing technical details, no version/file context, unexplained code dumps, no prevention, no cross-references.
