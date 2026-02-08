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

# engineering-docs Skill

**Purpose:** Automatically document solved problems to build searchable institutional knowledge with category-based organization (enum-validated problem types).

## Overview

This skill captures problem solutions immediately after confirmation, creating structured documentation that serves as a searchable knowledge base for future sessions.

**Organization:** Single-file architecture - each problem documented as one markdown file in its symptom category directory (e.g., `docs/solutions/performance-issues/n-plus-one-briefs.md`). Files use YAML frontmatter for metadata and searchability.

---

## 7-Step Documentation Capture

### Step 1: Detect Confirmation

**Auto-invoke after phrases:**

- "that worked"
- "it's fixed"
- "working now"
- "problem solved"
- "that did it"

**OR manual:** `/clavain:compound` command

**Non-trivial problems only:**

- Multiple investigation attempts needed
- Tricky debugging that took time
- Non-obvious solution
- Future sessions would benefit

**Skip documentation for:**

- Simple typos
- Obvious syntax errors
- Trivial fixes immediately corrected

### Step 2: Gather Context

Extract from conversation history:

**Required information:**

- **Module name**: Which module or component had the problem
- **Symptom**: Observable error/behavior (exact error messages)
- **Investigation attempts**: What didn't work and why
- **Root cause**: Technical explanation of actual problem
- **Solution**: What fixed it (code/config changes)
- **Prevention**: How to avoid in future

**Environment details:**

- Language/framework version
- OS version
- File/line references

**BLOCKING REQUIREMENT:** If critical context is missing (module name, exact error, or resolution steps), ask user and WAIT for response before proceeding to Step 3:

```
I need a few details to document this properly:

1. Which module had this issue? [ModuleName]
2. What was the exact error message or symptom?

[Continue after user provides details]
```

### Step 3: Check Existing Docs

Search docs/solutions/ for similar issues:

```bash
# Search by error message keywords
grep -r "exact error phrase" docs/solutions/

# Search by symptom category
ls docs/solutions/[category]/
```

**IF similar issue found:**

THEN present decision options:

```
Found similar issue: docs/solutions/[path]

What's next?
1. Create new doc with cross-reference (recommended)
2. Update existing doc (only if same root cause)
3. Other

Choose (1-3): _
```

WAIT for user response, then execute chosen action.

**ELSE** (no similar issue found):

Proceed directly to Step 4 (no user interaction needed).

### Step 4: Generate Filename

Format: `[sanitized-symptom]-[module]-[YYYYMMDD].md`

**Sanitization rules:**

- Lowercase
- Replace spaces with hyphens
- Remove special characters except hyphens
- Truncate to reasonable length (< 80 chars)

**Examples:**

- `missing-include-BriefSystem-20251110.md`
- `parameter-not-saving-state-EmailProcessing-20251110.md`
- `webview-crash-on-resize-Assistant-20251110.md`

### Step 5: Validate YAML Schema (Blocking)

**CRITICAL:** All docs require validated YAML frontmatter with enum validation.

#### Validation Gate: YAML Schema (Blocking)

**Validate against schema:**
Load `schema.yaml` and classify the problem against the enum values defined in [yaml-schema.md](./references/yaml-schema.md). Ensure all required fields are present and match allowed values exactly.

**BLOCK if validation fails:**

```
❌ YAML validation failed

Errors:
- problem_type: must be one of schema enums, got "compilation_error"
- severity: must be one of [critical, high, medium, low], got "invalid"
- symptoms: must be array with 1-5 items, got string

Please provide corrected values.
```

**GATE ENFORCEMENT:** Do NOT proceed to Step 6 (Create Documentation) until YAML frontmatter passes all validation rules defined in `schema.yaml`.


### Step 6: Create Documentation

**Determine category from problem_type:** Use the category mapping defined in [yaml-schema.md](./references/yaml-schema.md) (lines 49-61).

**Create documentation file:**

```bash
PROBLEM_TYPE="[from validated YAML]"
CATEGORY="[mapped from problem_type]"
FILENAME="[generated-filename].md"
DOC_PATH="docs/solutions/${CATEGORY}/${FILENAME}"

# Create directory if needed
mkdir -p "docs/solutions/${CATEGORY}"

# Write documentation using template from assets/resolution-template.md
# (Content populated with Step 2 context and validated YAML frontmatter)
```

**Result:**
- Single file in category directory
- Enum validation ensures consistent categorization

**Create documentation:** Populate the structure from `assets/resolution-template.md` with context gathered in Step 2 and validated YAML frontmatter from Step 5.

### Step 7: Cross-Reference & Critical Pattern Detection

If similar issues found in Step 3:

**Update existing doc:**

```bash
# Add Related Issues link to similar doc
echo "- See also: [$FILENAME]($REAL_FILE)" >> [similar-doc.md]
```

**Update new doc:**
Already includes cross-reference from Step 6.

**Update patterns if applicable:**

If this represents a common pattern (3+ similar issues):

```bash
# Add to docs/solutions/patterns/common-solutions.md
cat >> docs/solutions/patterns/common-solutions.md << 'EOF'

## [Pattern Name]

**Common symptom:** [Description]
**Root cause:** [Technical explanation]
**Solution pattern:** [General approach]

**Examples:**
- [Link to doc 1]
- [Link to doc 2]
- [Link to doc 3]
EOF
```

**Critical Pattern Detection (Optional Proactive Suggestion):**

If this issue has automatic indicators suggesting it might be critical:
- Severity: `critical` in YAML
- Affects multiple modules OR foundational stage (Stage 2 or 3)
- Non-obvious solution

Then in the decision menu (Step 8), add a note:
```
💡 This might be worth adding to Required Reading (Option 2)
```

But **NEVER auto-promote**. User decides via decision menu (Option 2).

**Template for critical pattern addition:**

When user selects Option 2 (Add to Required Reading), use the template from `assets/critical-pattern-template.md` to structure the pattern entry. Number it sequentially based on existing patterns in `docs/solutions/patterns/critical-patterns.md`.

---

### Decision Gate: Post-Documentation

## Decision Menu After Capture

After successful documentation, present options and WAIT for user response:

```
✓ Solution documented

File created:
- docs/solutions/[category]/[filename].md

What's next?
1. Continue workflow (recommended)
2. Add to Required Reading - Promote to critical patterns (critical-patterns.md)
3. Link related issues - Connect to similar problems
4. Add to existing skill - Add to a learning skill (e.g., engineering-docs)
5. Create new skill - Extract into new learning skill
6. View documentation - See what was captured
7. Other
```

**Handle responses:**

**Option 1: Continue workflow**

- Return to calling skill/workflow
- Documentation is complete

**Option 2: Add to Required Reading** ⭐ PRIMARY PATH FOR CRITICAL PATTERNS

User selects this when:
- System made this mistake multiple times across different modules
- Solution is non-obvious but must be followed every time
- Foundational requirement (threading, APIs, core architecture, etc.)

Action:
1. Extract pattern from the documentation
2. Format as ❌ WRONG vs ✅ CORRECT with code examples
3. Add to `docs/solutions/patterns/critical-patterns.md`
4. Add cross-reference back to this doc
5. Confirm: "✓ Added to Required Reading. All subagents will see this pattern before code generation."

**Option 3: Link related issues**

- Prompt: "Which doc to link? (provide filename or describe)"
- Search docs/solutions/ for the doc
- Add cross-reference to both docs
- Confirm: "✓ Cross-reference added"

**Option 4: Add to existing skill**

User selects this when the documented solution relates to an existing learning skill:

Action:
1. Prompt: "Which skill? (engineering-docs, etc.)"
2. Determine which reference file to update (resources.md, patterns.md, or examples.md)
3. Add link and brief description to appropriate section
4. Confirm: "✓ Added to [skill-name] skill in [file]"

Example: For Hotwire Native Tailwind variants solution:
- Add to `engineering-docs/references/resources.md` under "Project-Specific Resources"
- Add to `engineering-docs/references/examples.md` with link to solution doc

**Option 5: Create new skill**

User selects this when the solution represents the start of a new learning domain:

Action:
1. Prompt: "What should the new skill be called? (e.g., stripe-billing, email-processing)"
2. Create the skill directory structure with SKILL.md following plugin conventions
3. Create initial reference files with this solution as first example
4. Confirm: "✓ Created new [skill-name] skill with this solution as first example"

**Option 6: View documentation**

- Display the created documentation
- Present decision menu again

**Option 7: Other**

- Ask what they'd like to do


---

## Integration Points

**Invoked by:**
- /clavain:compound command (primary interface)
- Manual invocation in conversation after solution confirmed
- Can be triggered by detecting confirmation phrases like "that worked", "it's fixed", etc.

**Invokes:**
- None (terminal skill - does not delegate to other skills)

**Handoff expectations:**
All context needed for documentation should be present in conversation history before invocation.


---

## Success Criteria

Documentation is successful when ALL of the following are true:

- ✅ YAML frontmatter validated (all required fields, correct formats)
- ✅ File created in docs/solutions/[category]/[filename].md
- ✅ Enum values match schema.yaml exactly
- ✅ Code examples included in solution section
- ✅ Cross-references added if related issues found
- ✅ User presented with decision menu and action confirmed


---

## Error Handling

**Missing context:**

- Ask user for missing details
- Don't proceed until critical info provided

**YAML validation failure:**

- Show specific errors
- Present retry with corrected values
- BLOCK until valid

**Similar issue ambiguity:**

- Present multiple matches
- Let user choose: new doc, update existing, or link as duplicate

**Module not in modules documentation:**

- Warn but don't block
- Proceed with documentation
- Suggest: "Add [Module] to modules documentation if not there"

---

## Execution Guidelines

**MUST do:**
- Validate YAML frontmatter (BLOCK if invalid per Step 5 validation gate)
- Extract exact error messages from conversation
- Include code examples in solution section
- Create directories before writing files (`mkdir -p`)
- Ask user and WAIT if critical context missing

**MUST NOT do:**
- Skip YAML validation (validation gate is blocking)
- Use vague descriptions (not searchable)
- Omit code examples or cross-references

---

## Quality Guidelines

**Good documentation has:**

- ✅ Exact error messages (copy-paste from output)
- ✅ Specific file:line references
- ✅ Observable symptoms (what you saw, not interpretations)
- ✅ Failed attempts documented (helps avoid wrong paths)
- ✅ Technical explanation (not just "what" but "why")
- ✅ Code examples (before/after if applicable)
- ✅ Prevention guidance (how to catch early)
- ✅ Cross-references (related issues)

**Avoid:**

- ❌ Vague descriptions ("something was wrong")
- ❌ Missing technical details ("fixed the code")
- ❌ No context (which version? which file?)
- ❌ Just code dumps (explain why it works)
- ❌ No prevention guidance
- ❌ No cross-references

---

