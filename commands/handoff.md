---
name: handoff
description: Generate a concise session handoff summary as a dated markdown file
argument-hint: "[focus area or notes]"
---

# Session Handoff

Generate a compact, high-signal handoff file at `docs/handoffs/YYYY-MM-DD-<topic-slug>.md`. That file is the artifact — the user copies it into the next session when they want to resume.

**Announce:** "Generating handoff summary..."

## What to include

Scan the full conversation and write exactly these sections, in this order. Bullets only. Absolute file paths. No padding.

### 1. Directive
The most important section. A direct instruction to the next agent.
- Lead with: `> Your job is to [X]. Start by [Y]. Verify with [Z].`
- Name files to edit, tests to run, commands to verify
- If multiple possible next steps, pick the highest-priority one as primary; list alternatives as `Fallback:` items
- Include blockers or open decisions the next session must resolve
- If beads are in progress, list IDs and status (e.g., `Sylveste-abc1 — in_progress, claimed`)
- If a long-running process is active (downloads, builds), include the check/restart command

### 2. Dead ends
What was tried and didn't work. Highest-signal section for preventing wasted effort.
- Format: `[approach] — [why it failed or was abandoned]`
- Include partial approaches that were promising but dropped, and why
- Omit the section entirely if nothing failed this session

### 3. Non-obvious context
Things a new session can't derive from `git log`, `git status`, or CLAUDE.md:
- Why approach A was chosen over B
- Gotchas discovered (workarounds, config quirks, tool behavior)
- In-memory state: env vars set, processes running, temporary config
- Key file paths for work in progress (absolute paths)

## What to OMIT

A new session will run `git log`, `git status`, and read CLAUDE.md. Do not repeat:
- Commit hashes, branch name, last commit
- List of files changed
- What's working vs broken if obvious from running tests
- Architecture or conventions already in CLAUDE.md

## Write the file

Create `docs/handoffs/YYYY-MM-DD-<topic-slug>.md` with frontmatter. Create the directory if missing.

```markdown
---
date: YYYY-MM-DD
session: <first 8 chars of CLAUDE_SESSION_ID or "unknown">
topic: <2-5 word topic>
beads: [list of bead IDs touched this session]
---

## Session Handoff — YYYY-MM-DD <brief topic>

### Directive
> Your job is to [specific task]. Start by [first action]. Verify with [command].
- Beads: [IDs and status, if any]
- Dependency chain: [if relevant]

### Dead Ends
- [approach] — [why it failed]

### Context
- [non-obvious decision or gotcha]
- [key file paths]
```

Do NOT prune old handoffs — they serve as long-term session history.

After writing, print only the absolute path of the file. The user copies the file into their next session when they want to resume; no other output is needed.

## Rules

- The Directive is the lead section — a new session receiving this handoff should start working immediately without asking "what should I do?"
- Do NOT pad with pleasantries, summaries of what was done, or generic advice
- Do NOT duplicate what git or CLAUDE.md already provide
- DO include session-specific knowledge that dies when this conversation closes
- If the user provides a focus area argument, weight the summary toward that topic
- Multi-agent safe: each invocation writes a uniquely-named dated file, never a shared `latest.md` symlink or memory slot
