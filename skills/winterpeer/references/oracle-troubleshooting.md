# Oracle Troubleshooting Reference

## What is Oracle?

**Oracle is a CLI tool** (not a website) that automates ChatGPT in a browser. It bundles your prompt + files, opens Chrome, pastes into ChatGPT, waits for the response, and returns it.

- **Repository**: https://github.com/steipete/oracle
- **Install**: `npm install -g @steipete/oracle`
- **Requires**: ChatGPT Pro subscription ($200/month) OR `OPENAI_API_KEY`

## Common Mistakes

| Mistake | Correct Approach |
|---------|------------------|
| Searching for "winterpeer" as a binary | winterpeer is a skill, not a command. Use Oracle CLI. |
| Using `--models` without API keys | Browser mode is the default. Only use `--models` if you have `OPENAI_API_KEY`. |
| Navigating to "oracle.do" or similar | Oracle is a CLI tool, not a website. Run `oracle` in terminal. |
| Using codex instead of oracle | Codex CLI is a different tool. winterpeer uses Oracle. |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "oracle: command not found" | Install: `npm install -g @steipete/oracle` |
| Oracle hangs | Check `oracle status --hours 1`, recover with `oracle session <id>` |
| "OPENAI_API_KEY not set" | Use browser mode (default) instead of `-e api` |
| Browser mode slow | Normal - can take 1-10 minutes. Add `-e api` if you have the key. |
| Token limit exceeded | Use `--dry-run --files-report` to preview, reduce files |
| Chrome doesn't open | Oracle needs Chrome installed and accessible |

## Session Recovery

Oracle saves sessions for recovery:

```bash
# View recent sessions
oracle status --hours 1 --limit 10

# Reattach to running session
oracle session <session-id>

# Replay completed session
oracle session <session-id> --render
```

## Command Reference

```bash
# CHECK: Is Oracle installed?
which oracle || echo "Install: npm install -g @steipete/oracle"

# PREVIEW: Check token count before sending
oracle --dry-run --files-report -p "[prompt]" -f 'files'

# DEFAULT: Browser mode (uses ChatGPT Pro subscription)
oracle -p "[prompt]" -f 'files' --wait --write-output /tmp/council-gpt.md

# OPTIONAL: API mode (faster, requires OPENAI_API_KEY)
oracle -p "[prompt]" -f 'files' -e api --wait --write-output /tmp/council-gpt.md

# RECOVERY: If Oracle fails or hangs
oracle status --hours 1            # View recent sessions
oracle session <id>                # Reattach to running session
oracle session <id> --render       # Replay completed session
```
