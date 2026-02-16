# Debate Mode

## When to Suggest

Count complexity signals -- if 3+ apply, suggest debate:

| Signal | Example |
|--------|---------|
| Multiple valid approaches | "middleware or decorators" |
| Architectural implications | New patterns, cross-cutting concerns |
| Security-sensitive | Auth, crypto, permissions |
| API contract changes | Public interfaces, protocols |
| Performance-critical | Hot loops, data structures at scale |
| Ambiguous requirements | User intent unclear |

**Always ask the user first.**

## Running a Debate

1. Write position to `/tmp/debate-claude-position-${TOPIC}.md`
2. Dispatch:

```bash
DEBATE_SH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/debate.sh' 2>/dev/null | head -1)
[ -z "$DEBATE_SH" ] && DEBATE_SH=$(find ~/projects/Clavain -name debate.sh -path '*/scripts/*' 2>/dev/null | head -1)

bash $DEBATE_SH -C $PROJECT_DIR -t $TOPIC \
  --claude-position /tmp/debate-claude-position-${TOPIC}.md \
  -o /tmp/debate-output-${TOPIC}.md --rounds 2
```

3. Read output, synthesize, present options to user

## 2-Round Maximum
Capped to prevent debate costing more than implementation.
