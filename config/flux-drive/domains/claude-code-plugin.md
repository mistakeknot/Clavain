# Claude Code Plugin Domain Profile

## Detection Signals

Primary signals (strong indicators):
- Directories: `.claude-plugin/`, `skills/`, `agents/`, `commands/`, `hooks/`
- Files: `plugin.json`, `SKILL.md`, `marketplace.json`
- Frameworks: (Claude Code plugin system)
- Keywords: `subagent_type`, `PreToolUse`, `PostToolUse`, `SessionStart`, `CLAUDE_PLUGIN_ROOT`, `AskUserQuestion`, `frontmatter`

Secondary signals (supporting):
- Directories: `config/`, `scripts/`, `references/`
- Files: `settings.json`, `*.md` (with YAML frontmatter), `bump-version.sh`
- Keywords: `skill_description`, `additionalContext`, `hook_event`, `tool_name`, `CLAUDE_TOOL_USE_ID`

## Injection Criteria

When `claude-code-plugin` is detected, inject these domain-specific review bullets into each core agent's prompt.

### fd-architecture

- Check that skills, agents, and commands have clear boundaries (skills = loaded context, agents = spawnable subagents, commands = user-invocable actions)
- Verify that hooks are stateless and fast (<5 seconds) — they run on every tool call and block the agent
- Flag skills with mixed concerns — a skill should teach ONE workflow, not combine unrelated instructions
- Check that agent definitions specify tools restrictions (not every agent needs Bash/Write access)
- Verify that the plugin doesn't duplicate Claude Code built-in functionality (e.g., reimplementing /help or /status)

### fd-safety

- Check that hooks don't execute user-provided content as shell commands (injection via tool arguments)
- Verify that SessionStart hooks don't read or expose secrets from the environment (hooks output goes to context)
- Flag agents that are granted unrestricted Bash access without justification (principle of least privilege)
- Check that plugin scripts don't modify files outside the project directory unless explicitly documented
- Verify that hook scripts validate all environment variables before use (CLAUDE_TOOL_USE_* may be empty or malformed)

### fd-correctness

- Check that frontmatter in skill/command/agent markdown files is valid YAML and contains required fields
- Verify that hook exit codes follow the convention (0=allow, 2=block with message, other=passthrough)
- Flag race conditions in hooks that read/write shared state files (multiple hooks may run concurrently)
- Check that SKILL.md instructions reference actual tool names and agent types that exist in the environment
- Verify that command markdown files don't have conflicting trigger patterns (two commands matching the same user input)

### fd-quality

- Check that every skill has a clear one-line description in its frontmatter (used for routing and help text)
- Verify consistent naming conventions (kebab-case for files, namespace:name for commands, descriptive agent names)
- Flag overly long SKILL.md files — instructions injected into context consume tokens; keep under 100 lines with references
- Check that agent prompts include example outputs and success criteria (not just "review the code")
- Verify that commands have descriptive help text that appears in /help listings

### fd-performance

- Check that SessionStart hooks avoid expensive operations (network calls, large file scans) — they delay every session start
- Flag skills that inject large reference documents inline instead of using file references (token budget waste)
- Verify that hook scripts use early-exit patterns (check relevant conditions first, skip processing for unrelated events)
- Check that agents specify max_turns constraints appropriate to their task (don't let simple lookups run 20 turns)
- Flag plugins with more than 50 skills/commands — routing overhead grows with count, prefer fewer well-designed skills

### fd-user-product

- Check that the plugin has a discoverable help system (using-* skill or /help command that lists available features)
- Verify that new users can find the right command in <30 seconds (clear naming, categorization, or routing skill)
- Flag skills that require deep knowledge of the plugin internals to use (instructions should be self-contained)
- Check that error messages from hooks explain what went wrong and how to fix it (not just "hook failed")
- Verify that the plugin works with a fresh Claude Code installation (no undocumented dependencies on other plugins or tools)

## Agent Specifications

These are domain-specific agents that `/flux-gen` can generate for Claude Code plugin projects. They complement (not replace) the core fd-* agents.

### fd-plugin-structure

Focus: Manifest correctness, file organization, frontmatter validation, naming conventions, cross-reference integrity.

Key review areas:
- plugin.json schema compliance and completeness
- Frontmatter field validation across all markdown files
- Cross-references between skills, agents, and commands
- File naming and directory structure conventions
- Version consistency across plugin.json and marketplace.json

### fd-prompt-engineering

Focus: Skill instruction clarity, agent prompt effectiveness, token efficiency, routing accuracy.

Key review areas:
- Instruction clarity and unambiguity
- Token budget optimization (inline vs referenced content)
- Routing table accuracy (triggers match intended use cases)
- Agent prompt specificity (clear success criteria, example outputs)
- Skill composition patterns (when skills reference other skills)
