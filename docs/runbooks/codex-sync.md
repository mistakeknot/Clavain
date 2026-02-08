# Codex Sync Runbook

Operational runbook for keeping Codex installs aligned with active Clavain development and upstream sync merges.

## Scope

Use this runbook whenever:

- `main` receives Clavain changes from Claude/Codex sessions
- Upstream sync PRs are merged (`sync.yml`)
- Codex-facing files change (`skills/`, `commands/`, `.codex/`, `scripts/dispatch.sh`, `scripts/debate.sh`, `scripts/install-codex.sh`)

## Fast Path

From the Clavain repo root:

```bash
git pull --rebase origin main
make codex-refresh
make codex-doctor
```

Restart Codex after `codex-refresh`.

## Daily Operator Flow

1. Pull latest main:
   ```bash
   git pull --rebase origin main
   ```
2. Refresh Codex install:
   ```bash
   make codex-refresh
   ```
3. Validate links and wrappers:
   ```bash
   make codex-doctor
   ```
4. Restart Codex CLI.

## After Upstream Sync Merge

When `.github/workflows/sync.yml` merges upstream content:

1. Pull latest main:
   ```bash
   git pull --rebase origin main
   ```
2. Run:
   ```bash
   make codex-refresh
   make codex-doctor
   ```
3. Spot-check a few generated prompt wrappers:
   ```bash
   ls ~/.codex/prompts/clavain-*.md | head -n 5
   ```

## CI Reminder Behavior

Workflow: `.github/workflows/codex-refresh-reminder.yml`

- Trigger: every push to `main`
- If Codex-facing files changed, the workflow writes a commit comment reminder to run:
  - `make codex-refresh`
  - `make codex-doctor`
  - restart Codex

This does not mutate repo content; it is an operator reminder only.

Workflow: `.github/workflows/codex-refresh-reminder-pr.yml`

- Trigger: PR activity against `main` (`opened`, `reopened`, `synchronize`, `labeled`)
- Scope: upstream-sync PRs (label, branch name, or title match)
- Behavior: upserts one PR comment reminding operators to run refresh steps after merge

## GitHub Web PR Agent Commands

Workflow: `.github/workflows/pr-agent-commands.yml`

Use PR conversation comments to trigger read-only agent reviews:

- `/clavain:claude-review [optional focus text]`
- `/clavain:codex-review [optional focus text]`
- `/clavain:dual-review [optional focus text]` (runs both)

Rules:

- Works only on PR comments (not regular issues)
- Trigger user must be `OWNER`, `MEMBER`, or `COLLABORATOR`
- Jobs run in read-only review mode and post results as PR comments
- This is review-only automation (no code-writing workflow yet)

Required repository secrets (GitHub Actions):

- `CODEX_AUTH_JSON` (for Codex CLI jobs)
- `ANTHROPIC_API_KEY` (for Claude jobs)

Populate `CODEX_AUTH_JSON` with the contents of a working `~/.codex/auth.json` from a machine where `codex login status` reports "Logged in using ChatGPT".

Example:

```bash
gh secret set CODEX_AUTH_JSON --repo mistakeknot/Clavain < ~/.codex/auth.json
```

Note: approving Codex in ChatGPT settings is separate from GitHub Actions secrets; both are needed for these workflows.

## Troubleshooting

### Existing path blocks symlink

If `~/.agents/skills/clavain` or `~/.codex/skills/clavain` is a real directory/file, move it aside and rerun:

```bash
mv ~/.agents/skills/clavain ~/.agents/skills/clavain.backup.$(date +%s) 2>/dev/null || true
mv ~/.codex/skills/clavain ~/.codex/skills/clavain.backup.$(date +%s) 2>/dev/null || true
make codex-refresh
```

### Prompt wrappers are stale/missing

```bash
make codex-refresh
ls ~/.codex/prompts/clavain-*.md | wc -l
```

### Need clean uninstall/reinstall

```bash
bash scripts/install-codex.sh uninstall
make codex-refresh
make codex-doctor
```
