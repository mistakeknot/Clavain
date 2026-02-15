# F11 Coordination Skills — Research Analysis

**Date:** 2026-02-14
**Bead:** Clavain-n23p
**Feature:** F11 from interlock PRD (`docs/prds/2026-02-14-interlock-multi-agent-coordination.md`)

---

## 1. PRD Requirements

From the PRD, F11 acceptance criteria are:
- `coordination-protocol` SKILL.md: reserve -> work -> release workflow, best practices
- `conflict-recovery` SKILL.md: handle blocked edits (check status, work elsewhere, request release, escalate)
- Skills reference MCP tool names for discoverability
- Skills are concise (<100 lines each)

## 2. MCP Tool Names (from F6)

The PRD defines 9 MCP tools in F6:
1. `reserve_files` — reserve files by pattern
2. `release_files` — release specific files
3. `release_all` — release all reservations for this agent
4. `check_conflicts` — check if files are reserved by others
5. `my_reservations` — list current agent's reservations
6. `send_message` — send message to another agent
7. `fetch_inbox` — get messages for this agent
8. `list_agents` — list active agents in the project
9. `request_release` — ask another agent to release reservations

## 3. Commands (from F8)

F8 defines 4 commands that skills should reference:
- `/interlock:join` — register agent
- `/interlock:leave` — deregister agent
- `/interlock:status` — list agents and reservations
- `/interlock:setup` — install intermute + configure

## 4. Companion Plugin Skill Patterns

Examined existing companion skills for structural patterns:

### Pattern: Frontmatter
All companion skills use standard YAML frontmatter with `name` and `description`. Description starts with "Use when..." and describes triggering conditions only (no workflow summary per CSO rules in writing-skills).

### Pattern: Conciseness
The `<100 lines` constraint is strict. Examined existing skills:
- `beads-workflow/SKILL.md` (interphase): 198 lines — this is a complex multi-mode workflow
- `flux-research/SKILL.md` (interflux): 308 lines — orchestration skill with phases
- `artifact-gen/SKILL.md` (interpath): not read but likely moderate

For F11, the constraint is achievable because these are behavioral/protocol skills (teaching agents what to do), not orchestration skills (directing multi-step execution). They're closer to `code-review-discipline/SKILL.md` in nature but much shorter.

### Pattern: MCP Tool References
Skills should reference MCP tool names directly for discoverability. Example from PRD: agents call `reserve_files` MCP tool. The skill should name these tools explicitly so Claude's search finds them.

### Pattern: Quick Reference Tables
Most skills include quick-reference tables for scanning. Good fit for listing MCP tools with brief descriptions.

## 5. Skill Content Design

### coordination-protocol/SKILL.md (~70-90 lines)

**Purpose:** Teach agents the standard reserve -> work -> release workflow.

**Key sections:**
1. Overview — what coordination protocol is, why it matters
2. The Workflow — Before editing: `reserve_files`, do work, after done: `release_files`/`release_all`
3. MCP Tools Quick Reference — table of all 9 tools with 1-line descriptions
4. Best Practices — reserve narrowly, short TTLs, release early, check before reserving
5. Common Mistakes — reserving too broadly, forgetting to release, long TTLs

**CSO keywords:** reserve, release, lock, conflict, multi-agent, coordination, concurrent editing, file reservation, interlock

### conflict-recovery/SKILL.md (~60-80 lines)

**Purpose:** Teach agents what to do when an edit is blocked by another agent's reservation.

**Key sections:**
1. Overview — when you encounter a conflict
2. Recovery Steps — ordered escalation: check status, work elsewhere, request release, wait for expiry, escalate to user
3. Key MCP Tools — subset relevant to recovery: `check_conflicts`, `list_agents`, `request_release`
4. Commands — `/interlock:status` for visibility
5. Common Mistakes — immediately asking for release, not checking expiry time, editing without checking

**CSO keywords:** conflict, blocked, reserved, locked, recovery, workaround, request release, escalate

## 6. Target Repo Structure

Files will be created at:
- `/root/projects/interlock/skills/coordination-protocol/SKILL.md`
- `/root/projects/interlock/skills/conflict-recovery/SKILL.md`

The interlock repo does not exist yet. The plan should note that the repo must be created first (or that these skills are part of the broader interlock plugin creation).

## 7. Implementation Complexity

This is a very simple feature — just two markdown files. No code, no tests beyond optional structural tests. The main risk is exceeding the 100-line limit, which requires disciplined conciseness.

## 8. Dependencies

- F6 (MCP server) defines the tool names referenced by skills
- F8 (commands) defines the command names referenced by skills
- Neither F6 nor F8 needs to be implemented first — skills reference tool/command names as documentation, not runtime dependencies

## 9. Structural Tests (Optional)

If interlock follows Clavain's test pattern, structural tests could verify:
- Skills exist at expected paths
- Skills have valid YAML frontmatter
- Skills are under 100 lines
- Skills reference at least 3 MCP tool names

This is optional for the plan but worth noting.
