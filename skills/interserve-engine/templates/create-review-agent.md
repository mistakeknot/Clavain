You are bootstrapping project-specific review agents for {{PROJECT}}.

## Task
Create 2-3 specialized review agent files in .claude/agents/ that are tailored to this project's architecture and concerns.

## Phase 1: Explore
1. Read CLAUDE.md and AGENTS.md to understand the project
2. Examine directory structure (ls key directories)
3. Identify languages used (file extensions)

## Phase 2: Identify Domains
Identify the project's 2-3 most important review domains.
Examples: for a Go API → "api-design", "data-model", "auth-flow"
          for a plugin → "skill-quality", "hook-safety", "agent-routing"

## Phase 3: Create Agents
For each domain, create `.claude/agents/fd-{domain}.md` following this format:

---
name: fd-{domain}
description: "Project-specific {domain} reviewer for {project}."
model: inherit
---

## First Step (MANDATORY)
Before any analysis, read these files:
1. CLAUDE.md in the project root
2. AGENTS.md in the project root (if it exists)

## Review Approach
[Write domain-specific review instructions grounded in THIS project's architecture]

## Output Format
[Standard flux-drive frontmatter + prose format]

## Final Step
After creating all agent files, write the content hash:

sha256sum CLAUDE.md AGENTS.md 2>/dev/null | sha256sum | cut -d' ' -f1 > .claude/agents/.fd-agents-hash

Then list what was created:
CREATED: fd-{domain1}.md, fd-{domain2}.md, fd-{domain3}.md
VERDICT: COMPLETE | INCOMPLETE [reason]

## Constraints (ALWAYS INCLUDE)
- Create 2-3 agents, no more
- Each agent must start with "First Step: read CLAUDE.md and AGENTS.md"
- Use kebab-case names starting with fd-
- Do NOT commit or push
- Do NOT modify any existing files
