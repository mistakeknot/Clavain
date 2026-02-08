---
name: debate
description: Run a structured Claude↔Codex debate before implementing a complex task
---

# Debate — Structured Cross-AI Discussion

Run a structured 2-round debate between Claude and Codex to explore different approaches before implementing a complex task.

## Usage

The user invokes `/debate [topic]` where topic describes the decision or task to debate.

## Workflow

### 1. Understand the Topic

If the user provides a topic, use it directly. If not, analyze the current conversation context to identify the decision point that needs debate.

Read relevant code files to build context.

### 2. Write Claude's Position (Round 1)

Write your analysis and recommended approach to a position file:

```bash
TOPIC_SLUG="<short-kebab-case-label>"
```

Write the position to `/tmp/debate-claude-position-${TOPIC_SLUG}.md` with this structure:

```markdown
# Claude's Position: [Topic]

## Context
[Brief description of the problem and codebase state]

## Recommended Approach
[Your proposed solution with rationale]

## Trade-offs
[Pros and cons you see]

## Concerns
[Risks, edge cases, or unknowns]

## Key Files
[List of relevant files with brief descriptions]
```

### 3. Dispatch Codex for Independent Analysis (Round 1)

Use debate.sh to get Codex's independent position:

**Resolve script paths first** — `$CLAUDE_PLUGIN_ROOT` is NOT available in the Bash environment:
```bash
DEBATE_SH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/debate.sh' 2>/dev/null | head -1)
[ -z "$DEBATE_SH" ] && DEBATE_SH=$(find ~/projects/Clavain -name debate.sh -path '*/scripts/*' 2>/dev/null | head -1)
```

```bash
bash $DEBATE_SH \
  -C /path/to/project \
  -t "$TOPIC_SLUG" \
  --claude-position /tmp/debate-claude-position-${TOPIC_SLUG}.md \
  -o /tmp/debate-output-${TOPIC_SLUG}.md \
  --rounds 2
```

This runs Codex in `read-only` mode (no file changes) and produces a structured debate output.

### 4. Read and Synthesize

Read the debate output file. Synthesize a final recommendation:

```markdown
## Debate Synthesis: [Topic]

### Areas of Agreement
[Where Claude and Codex align]

### Areas of Disagreement
[Where they differ and why]

### Final Recommendation
[Your synthesis based on both positions]

### Risk Mitigations
[How to address concerns raised by either side]
```

### 5. Oracle Escalation (if warranted)

If the debate involves any of these, escalate to Oracle (GPT-5.2 Pro) for a third opinion:
- Security implications (auth, crypto, data access)
- Multi-system integration (API contracts, protocol changes)
- Performance architecture (algorithms, data structures at scale)
- Fundamental architectural disagreement between Claude and Codex

```bash
DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait \
  -p "Review this architectural debate and provide your recommendation. [debate summary]" \
  -f 'relevant/files/**' \
  --write-output /tmp/oracle-debate-${TOPIC_SLUG}.md
```

After Oracle responds, produce a final synthesis that maps all three positions.

### 6. Present to User

Present the synthesis to the user with clear options:
- Option A (if positions diverged): Claude's approach with Codex's mitigations
- Option B (if positions diverged): Codex's approach with Claude's refinements
- Consensus (if positions aligned): The agreed approach with combined improvements

Ask the user which direction to take before implementing.

## Notes

- Debate is for **decisions**, not execution. After the debate, use normal delegation to implement.
- 2-round maximum prevents debate from costing more than the implementation.
- Codex runs in `read-only` mode during debate — no files are modified.
- Oracle escalation adds ~2-5 minutes. Only use for genuinely complex architectural decisions.
