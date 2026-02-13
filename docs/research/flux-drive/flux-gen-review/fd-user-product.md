### Findings Index
- P0 | P0-1 | "Discoverability" | flux-gen missing from /help command
- P0 | P0-2 | "Error Recovery" | No guidance for "no domains detected" failure scenario
- P1 | P1-1 | "First-Time Flow" | Missing onboarding context about when/why to use flux-gen
- P1 | P1-2 | "Integration Clarity" | Generated agents are passive until next flux-drive run
- P1 | P1-3 | "Confirmation UX" | AskUserQuestion options lack clear consequences
- P1 | P1-4 | "Edge Case Handling" | No guidance for partial agent spec coverage
- P2 | P2-1 | "Success Feedback" | Report lacks immediate next action guidance
- IMP | IMP-1 | "Error Messages" | detect-domains.py exit code 1 has no user-facing message
- IMP | IMP-2 | "Discoverability" | No link from flux-drive to flux-gen when domains detected
- IMP | IMP-3 | "Agent Quality" | Generated agent templates are verbose and repetitive
- IMP | IMP-4 | "User Confidence" | No preview of what will be generated before confirmation
- IMP | IMP-5 | "Documentation Gap" | AGENTS.md and doctor.md don't mention flux-gen
Verdict: needs-changes

---

### Summary

The flux-gen user experience has significant discoverability and error recovery gaps. A new user has no path to discover this command exists — it's absent from `/help`, undocumented in AGENTS.md, and never suggested by flux-drive even when domains are detected. The "no domains detected" error path provides no recovery guidance beyond a manual domain specification example. The confirmation prompt lacks clear consequences (what happens if I overwrite? what if I skip?), and the success report doesn't tell users how to actually use the generated agents. Generated agent files work correctly but are verbose with repetitive boilerplate that could be extracted to references. The integration between flux-gen and flux-drive is passive — users must manually run flux-drive after generation to see the agents activate, with no prompt suggesting this.

---

### Issues Found

**P0-1: flux-gen missing from /help command** (Discoverability)
- **Evidence**: commands/help.md lists 37 commands across 6 categories (Daily Drivers, Explore, Plan, Execute, Review, Ship, Debug, Meta). flux-gen does not appear in any category.
- **Impact**: New users have zero path to discover this command exists. The only discovery routes are:
  1. Reading routing-tables.md (3400+ lines, requires knowing to look there)
  2. Stumbling across the command file while browsing the repo
  3. Someone telling them about it
- **User scenario**: User runs `/flux-drive` on their game project. Review completes with core fd-* agents but misses game-specific issues. User wonders "how do I get domain-specific reviewers?" and runs `/help` — flux-gen is not listed. User gives up or asks for help externally.
- **Expected behavior**: flux-gen should be listed in the Meta or Review section of `/help` with a one-line description: "Generate project-specific domain review agents"
- **Severity**: P0 — blocks discovery for 100% of new users who don't already know the command exists

**P0-2: No guidance for "no domains detected" failure scenario** (Error Recovery)
- **Evidence**: commands/flux-gen.md line 28 shows the error message:
  ```
  > No domains detected for this project. You can specify a domain manually: `/flux-gen game-simulation`
  ```
  This message provides one example but:
  - Doesn't list available domain names (user must guess or browse files)
  - Doesn't explain WHY no domains were detected (too small? wrong file structure? missing keywords?)
  - Doesn't offer a recovery path beyond manual specification
  - Doesn't tell user how to see all available domains
- **User scenario**: User runs `/flux-gen` in a new Rust CLI project with 3 source files. Detection returns exit code 1 (no domains). User sees "you can specify a domain manually: `/flux-gen game-simulation`" and thinks:
  - "What domains are available?"
  - "Is my project too small to detect?"
  - "Should I add files/keywords to trigger detection instead of manually specifying?"
  - "How do I know which domain fits my project?"
  None of these questions have answers in the error message.
- **Expected behavior**: Error message should:
  1. List available domain names: "Available domains: game-simulation, web-api, cli-tool, data-pipeline, ..."
  2. Suggest viewing domain profiles: "See config/flux-drive/domains/ for domain signals"
  3. Offer to proceed without domains: "Or run `/flux-drive` to use core agents without domain specialization"
- **Severity**: P0 — dead-end error message forces users to abandon the command or seek external help

**P1-1: Missing onboarding context about when/why to use flux-gen** (First-Time Flow)
- **Evidence**: commands/flux-gen.md line 9 states "Generate project-specific `fd-*` review agents... These agents complement the core flux-drive plugin agents with deeper, domain-specific review expertise."
  - This explains WHAT flux-gen does but not WHEN or WHY
  - No guidance on "should I run this immediately?" vs "wait until after first review?"
  - No explanation of the value proposition: what do domain agents catch that core agents miss?
- **User scenario**: User discovers flux-gen (somehow). Reads the description. Wonders:
  - "Should I run this now or after my first review?"
  - "What will these agents do that the core agents don't?"
  - "Is this a one-time setup or something I run repeatedly?"
  - "What's the cost? (time, token usage, complexity)"
- **Expected behavior**: Add a "When to Use" section at the top:
  ```markdown
  ## When to Use

  Run `/flux-gen` once per project to generate domain-specific review agents tailored to your codebase. These agents complement the 7 core fd-* agents by providing deeper review criteria for your project's domain (e.g., game-specific balance checks, web API security patterns).

  **Run this:**
  - After your first flux-drive review if you notice domain-specific gaps
  - When starting a new project in a specialized domain (games, ML, embedded systems)
  - When your project evolves into a new domain (CLI tool becomes web API)

  **Skip this:**
  - If your project is small/experimental (core agents are sufficient)
  - If no domain is detected and you can't identify which domain fits
  ```
- **Severity**: P1 — users can discover and use the command, but lack context to make an informed decision about whether/when to use it

**P1-2: Generated agents are passive until next flux-drive run** (Integration Clarity)
- **Evidence**:
  - commands/flux-gen.md line 125: "To use them in a review: /flux-drive <target>"
  - No indication in the success report that agents are NOT automatically active
  - No prompt to run flux-drive after generation
- **User scenario**: User runs `/flux-gen`, sees "Generated 2 project-specific agents", assumes they are now active. Continues working on the project. Later, when reviewing code, expects the domain agents to be included but they aren't (because user hasn't run flux-drive yet).
- **Expected behavior**: Success report should explicitly state:
  ```
  These agents will be included in your NEXT flux-drive review.
  To activate them now: /flux-drive <target>
  ```
- **Severity**: P1 — causes user confusion about when agents become active, but doesn't block usage entirely

**P1-3: AskUserQuestion options lack clear consequences** (Confirmation UX)
- **Evidence**: commands/flux-gen.md lines 54-57:
  ```
  - Option 1: "Generate N new agents (skip M existing)" (Recommended)
  - Option 2: "Regenerate all (overwrite existing)"
  - Option 3: "Cancel"
  ```
  These labels describe WHAT happens but not the CONSEQUENCES:
  - Option 1: What happens to existing agents? Are they preserved forever? What if they're stale?
  - Option 2: What customizations will be lost? Can I recover them?
  - No guidance on WHEN to choose each option
- **User scenario**: User has previously generated agents and customized them. Runs `/flux-gen` again (maybe domain profiles were updated). Sees the three options. Wonders:
  - "If I choose Option 1, will my customizations be preserved?"
  - "If domain profiles were updated, how do I get the new criteria without losing my edits?"
  - "Should I manually merge changes or just regenerate?"
- **Expected behavior**: Enhance option descriptions with consequences:
  ```
  - Option 1: "Generate N new agents (preserve your M existing customized agents)" (Recommended — keeps your edits)
  - Option 2: "Regenerate all (OVERWRITES your customizations — you'll need to re-apply them)"
  - Option 3: "Cancel (no changes)"
  ```
  Also add guidance before the prompt:
  ```
  Note: If domain profiles have been updated since last generation, existing agents won't reflect the new criteria. Consider backing up .claude/agents/ before choosing Option 2.
  ```
- **Severity**: P1 — users can make an informed guess, but lack confidence that they're choosing correctly

**P1-4: No guidance for partial agent spec coverage** (Edge Case Handling)
- **Evidence**: commands/flux-gen.md line 42: "If the domain profile has no Agent Specifications section, skip it and note this to the user."
  - "Note this to the user" is vague — what should the note say?
  - No example of what happens when a domain has only 1 agent spec but core agents already cover that area
- **User scenario**: User's project detects `cli-tool` domain. The cli-tool profile has Agent Specifications for `fd-cli-ergonomics` only. flux-gen generates 1 agent. User wonders:
  - "Is that all? Should there be more?"
  - "Are the core agents enough for CLI projects, or am I missing something?"
  - "Why does game-simulation have 3 agents but cli-tool has 1?"
- **Expected behavior**: When a domain has partial/no agent specs, include context in the report:
  ```
  Domain: cli-tool (0.45)
    - fd-cli-ergonomics: Command-line UX patterns, flag design, help text quality

  Note: This domain profile defines 1 specialized agent. Core agents (fd-architecture, fd-quality, etc.) cover other CLI concerns like correctness and performance.
  ```
  If a domain has NO agent specs:
  ```
  Domain: embedded-systems (0.52)
    - (No specialized agents defined for this domain)

  Note: Core agents will still review your code. Consider customizing .claude/agents/ manually if you need embedded-specific review criteria.
  ```
- **Severity**: P1 — creates uncertainty about whether generation was successful/complete

**P2-1: Success report lacks immediate next action guidance** (Success Feedback)
- **Evidence**: commands/flux-gen.md lines 115-129 show the success report ends with:
  ```
  To use them in a review: /flux-drive <target>
  To regenerate: /flux-gen (existing agents are preserved unless you choose overwrite)
  ```
  - "To use them" is vague — use them on what? The current plan? A file? The whole repo?
  - No guidance on immediate next steps: "Try them now" vs "they'll be used automatically later"
- **User scenario**: User generates agents for their game project. Sees the success report. Wonders:
  - "Should I run flux-drive on something right now to test them?"
  - "What's a good test case to verify they work?"
  - "Will they be used automatically next time I run flux-drive, or do I need to do something?"
- **Expected behavior**: Add concrete next action to the report:
  ```
  Next steps:
  1. Customize: Edit .claude/agents/fd-*.md files to add project-specific patterns
  2. Test: Run `/flux-drive docs/plans/<your-plan>.md` to see domain agents in action
  3. Refine: After your first review, adjust agent focus areas based on findings quality
  ```
- **Severity**: P2 — users can figure this out, but adding explicit guidance improves time-to-value

---

### Improvements Suggested

**IMP-1: detect-domains.py exit code 1 has no user-facing message** (Error Messages)
- **Current behavior**: scripts/detect-domains.py exits with code 1 when no domains detected, but the only output is the cache file (empty domains list). The flux-gen command must interpret the exit code and construct its own error message.
- **Improvement**: Make detect-domains.py write a user-facing message to stderr on exit code 1:
  ```python
  if not detected_domains:
      print("No domains detected. Available domains:", file=sys.stderr)
      print("  " + ", ".join(d.profile for d in specs), file=sys.stderr)
      print("Run with a specific domain: /flux-gen <domain-name>", file=sys.stderr)
      sys.exit(1)
  ```
  This way the error message is consistent whether invoked from flux-gen or run manually for debugging.
- **Value**: Reduces duplication, improves error message quality, helps users debug detection failures

**IMP-2: No link from flux-drive to flux-gen when domains detected** (Discoverability)
- **Current behavior**: flux-drive detects domains in Step 1.0a, uses them to score agents, but never tells the user "you could generate domain-specific agents with /flux-gen"
- **Improvement**: In the flux-drive triage output (Phase 1, Step 1.2), add a note after domain detection:
  ```
  Domain detected: game-simulation (0.65)

  Tip: Generate specialized agents for this domain with `/flux-gen`
  Already have domain agents? They'll be included in triage automatically.
  ```
  Only show this tip if:
  - Domains detected with confidence >= 0.3
  - `.claude/agents/fd-*.md` does NOT already exist (to avoid nagging users who already generated agents)
- **Value**: Creates a discovery path from the primary review workflow (flux-drive) to the agent generation command

**IMP-3: Generated agent templates are verbose and repetitive** (Agent Quality)
- **Current behavior**: Generated agents repeat the same boilerplate across all agents:
  - Lines 8-16: "First Step (MANDATORY)" — identical in every agent
  - Lines 28-34: "How to Review" — identical in every agent
  - Lines 36-40: "Focus Rules" — nearly identical, only domain name changes
  - Lines 22-26: Key review areas all say "Examine this aspect carefully. Look for concrete evidence..." — identical phrasing 5 times per agent
- **Example**: fd-plugin-structure.md is 41 lines, but only ~10 lines are unique (Focus, Key review areas bullets). The other 31 lines are boilerplate.
- **Improvement**:
  1. Extract boilerplate to a reference file: `.claude/agents/README.md` or `fd-agent-guidelines.md`
  2. Generate minimal agent files:
     ```markdown
     # fd-plugin-structure — Claude Code Plugin Domain Reviewer

     > See fd-agent-guidelines.md for review methodology and output format

     Focus: Manifest correctness, file organization, frontmatter validation, naming conventions, cross-reference integrity

     ## Key Review Areas
     - plugin.json schema compliance and completeness
     - Frontmatter field validation across all markdown files
     - Cross-references between skills, agents, and commands
     - File naming and directory structure conventions
     - Version consistency across plugin.json and marketplace.json
     ```
     This reduces 41 lines to ~14 lines (66% reduction) while preserving all unique content.
  3. Generate the README.md once with full guidelines, reference it from each agent
- **Value**:
  - Reduces generated file size (easier to read, faster to customize)
  - Makes unique content (Focus + Key areas) stand out
  - Updates to guidelines can be centralized instead of regenerating all agents
  - Lowers token budget for Project Agents in flux-drive (currently ~41 lines × N agents pasted into every agent's prompt)

**IMP-4: No preview of what will be generated before confirmation** (User Confidence)
- **Current behavior**: flux-gen shows:
  ```
  For each agent to be generated:
  - If the file already exists, skip it
  - Present which agents exist vs which will be created

  Use AskUserQuestion to confirm
  ```
  But doesn't show WHICH agents will be created or WHAT their focus areas are.
- **User scenario**: User runs `/flux-gen` for the first time. Sees "Generate 2 new agents (skip 0 existing)" but doesn't know:
  - Which 2 agents?
  - What do they review?
  - Are they relevant to my project?
- **Improvement**: Before the AskUserQuestion prompt, show a preview:
  ```
  Will generate these agents for claude-code-plugin domain:

  fd-plugin-structure
    Focus: Manifest correctness, file organization, frontmatter validation

  fd-prompt-engineering
    Focus: Skill instruction clarity, agent prompt effectiveness

  Generate 2 new agents?
  ```
- **Value**: Builds user confidence that generation will produce relevant, useful agents. Allows users to cancel if the agents don't match their expectations.

**IMP-5: flux-gen undocumented in AGENTS.md and doctor.md** (Documentation Gap)
- **Current behavior**:
  - AGENTS.md does not mention flux-gen (grep returned no results)
  - commands/doctor.md does not check for or recommend flux-gen
  - No "Getting Started" guide that suggests running flux-gen as part of setup
- **Improvement**:
  1. Add to AGENTS.md Quick Start section:
     ```markdown
     ## Quick Start

     1. Install: `/clavain:setup`
     2. Health check: `/clavain:doctor`
     3. Generate domain agents: `/clavain:flux-gen` (optional, for specialized domains)
     4. First review: `/clavain:flux-drive docs/plans/<your-plan>.md`
     ```
  2. Add to doctor.md checks:
     ```bash
     # Check 3d: Domain-specific agents
     if [[ -f .claude/flux-drive.yaml ]] && ! ls .claude/agents/fd-*.md 2>/dev/null; then
       echo "  ⚠️  Domains detected but no domain agents generated"
       echo "      Tip: Run /flux-gen to create specialized review agents"
     fi
     ```
  3. Add to help.md under Meta section:
     ```
     | `/clavain:flux-gen` | Generate project-specific domain review agents |
     ```
- **Value**: Creates multiple discovery paths (docs, health check, help command) instead of relying on users to stumble across the command

---

### Overall Assessment

flux-gen is functionally complete and generates correct agents, but the user experience has critical discoverability and error recovery gaps. New users have no path to discover the command exists (P0-1), and the "no domains detected" error provides no actionable recovery path (P0-2). The confirmation flow lacks consequence clarity (P1-3), and the success report doesn't guide users toward immediate next actions (P1-2, P2-1). Generated agents work but are verbose with repetitive boilerplate (IMP-3). Addressing P0 issues (help.md listing, error message improvement) and P1 issues (onboarding context, integration clarity, confirmation UX) would bring this from "hard to discover" to "easy to find and use confidently."

<!-- flux-drive:complete -->
