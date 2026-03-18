---
name: handoff
description: Generate a concise session handoff summary for pasting into a new conversation
argument-hint: "[focus area or notes]"
---

# Session Handoff

Generate a compact, high-signal summary of this session that the user can paste into a new conversation to restore context fast.

**Announce:** "Generating handoff summary..."

## What to include

Scan the full conversation and produce a markdown block covering exactly these sections:

### 1. What was done
- Bullet list of concrete changes made (files created/edited, commands run, features built)
- Include commit hashes if any commits were made this session

### 2. Current state
- What's working, what's broken, what's partially done
- Any running processes, open PRs, or pending operations
- Current branch and last commit

### 3. What's next
- Immediate next steps the user would likely pick up
- Any blockers, open questions, or decisions deferred

### 4. Key context
- Non-obvious decisions made and why (things a new session wouldn't infer from code alone)
- Gotchas encountered and workarounds applied
- Relevant file paths for the work in progress

## Format

Output the handoff as a single fenced code block (```markdown) so the user can copy it cleanly. Keep it under 60 lines. Prefer terse bullet points over prose. Use absolute file paths.

```markdown
## Session Handoff — [date] [brief topic]

### Done
- ...

### Current State
- ...

### Next Steps
- ...

### Key Context
- ...
```

## Rules

- Do NOT pad with generic advice or pleasantries
- Do NOT include information the new session can derive from `git log`, `git status`, or reading CLAUDE.md
- DO include session-specific knowledge that would be lost: why you chose approach A over B, what you tried that failed, config that only exists in memory
- If the user provides a focus area argument, weight the summary toward that topic
- If beads are in progress, include their IDs and status
