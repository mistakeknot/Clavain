# Oracle Escalation

Escalate to Oracle (GPT-5.2 Pro) for security, multi-system integration, performance architecture, or irreconcilable Claude<->Codex disagreement:

```bash
DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait \
  -p "Review this technical decision. [summary]" \
  -f 'relevant/files/**' \
  --write-output /tmp/oracle-clodex-${TOPIC}.md
```

After Oracle: map all three positions, synthesize, present to user.
