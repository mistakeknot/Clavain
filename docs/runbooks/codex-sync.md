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
make codex-doctor-json
```

Restart Codex after `codex-refresh`.

### Autonomous refresh script

Run this in automation for unattended updates:

```bash
bash ~/.codex/clavain/scripts/codex-auto-refresh.sh
```

Defaults:

- Clone path: `$HOME/.codex/clavain`
- Log file: `$HOME/.local/share/clavain/codex-refresh.log`

Common overrides:

```bash
CLAVAIN_DIR="$HOME/src/clavain-codex" \
CLAVAIN_AUTO_REFRESH_LOG="$HOME/Library/Logs/clavain-codex-refresh.log" \
bash ~/.codex/clavain/scripts/codex-auto-refresh.sh
```

#### Cron

```bash
(crontab -l 2>/dev/null; echo "*/30 * * * * bash ~/.codex/clavain/scripts/codex-auto-refresh.sh >> ~/.local/share/clavain/cron.out 2>&1") | crontab -
```

#### systemd timer

```bash
cat > ~/.config/systemd/user/clavain-codex-refresh.service <<'EOF'
[Unit]
Description=Refresh Codex Clavain integration

[Service]
Type=oneshot
ExecStart=%h/.codex/clavain/scripts/codex-auto-refresh.sh
EOF

cat > ~/.config/systemd/user/clavain-codex-refresh.timer <<'EOF'
[Unit]
Description=Run Clavain Codex refresh every hour

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now clavain-codex-refresh.timer
```

#### macOS launchd

```bash
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.local.clavain.codex-refresh.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.local.clavain.codex-refresh</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/bash</string>
    <string>%h/.codex/clavain/scripts/codex-auto-refresh.sh</string>
  </array>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>StandardOutPath</key>
  <string>%h/Library/Logs/clavain-codex-refresh.out</string>
  <key>StandardErrorPath</key>
  <string>%h/Library/Logs/clavain-codex-refresh.err</string>
</dict>
</plist>
EOF

launchctl load -w ~/Library/LaunchAgents/com.local.clavain.codex-refresh.plist
```

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
   make codex-doctor-json
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
   make codex-doctor-json
   ```
3. Spot-check a few generated prompt wrappers:
   ```bash
   ls ~/.codex/prompts/clavain-*.md | head -n 5
   ```

## Upstream Impact + Decision Gate

Two workflows enforce meaningful adaptation for upstream-sync PRs:

- `.github/workflows/upstream-impact.yml`
- `.github/workflows/upstream-decision-gate.yml`

### What they do

1. **Impact report** posts/updates a PR comment with:
   - commit/file churn per upstream
   - mapped-file impact count (from `upstreams.json` mappings)
   - feature/breaking-signal commit headlines
2. **Decision gate** blocks merge unless the PR includes:
   - `docs/upstream-decisions/pr-<PR_NUMBER>.md`
   - `Gate: approved`
   - no remaining `TBD` placeholders

### Human intervention flow (required)

For any upstream-sync PR:

1. Copy template:
   ```bash
   cp docs/templates/upstream-decision-record.md docs/upstream-decisions/pr-<PR_NUMBER>.md
   ```
2. Fill decisions per upstream (`adopt-now`, `defer`, `ignore`) with rationale.
3. If Clavain base workflows are affected, explicitly document decisions under:
   - `## Base Workflow Decisions`
   - `### Base Workflow Change Decisions`
   - Keep `lfg` changes as intentional divergence unless explicitly adopted: Clavain uses `/clavain:sprint` as the canonical pipeline and does not sync `commands/lfg.md` by default.
4. Set `Gate: approved` only after decisions are explicit and actionable.
5. Commit to the PR branch and re-run checks.

## CI Reminder Behavior

If you have reminder automation configured outside this repository, use it to call:

- `make codex-refresh`
- `make codex-doctor-json`
- restart Codex

This repository does not ship reminder workflows by default, so operators should run these checks after Codex-facing edits.

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

## GitHub Web Issue Command (Upstream Sync)

Workflow: `.github/workflows/upstream-sync-issue-command.yml`

On an issue labeled `upstream-sync`, comment:

- `/clavain:upstream-sync` to run real sync (`dry_run=false`)
- `/clavain:upstream-sync --dry-run` to run preview mode

Rules:

- Works only on regular issues (not PRs)
- Trigger user must be `OWNER`, `MEMBER`, or `COLLABORATOR`
- Dispatches `.github/workflows/sync.yml` on `main`

Required repository secrets (GitHub Actions):

- `CODEX_AUTH_JSON` (for Codex CLI jobs)
- `ANTHROPIC_API_KEY` (optional; only needed for Claude review commands)

Populate `CODEX_AUTH_JSON` with the contents of a working `~/.codex/auth.json` from a machine where `codex login status` reports "Logged in using ChatGPT".

Example:

```bash
gh secret set CODEX_AUTH_JSON --repo mistakeknot/Clavain < ~/.codex/auth.json
```

Note: approving Codex in ChatGPT settings is separate from GitHub Actions secrets; both are needed for these workflows.

## Troubleshooting

For interactive troubleshooting, use `make codex-doctor` for human-readable output instead of JSON.

### Existing path blocks symlink

If `~/.agents/skills/clavain` is a real directory/file, move it aside and rerun:

```bash
mv ~/.agents/skills/clavain ~/.agents/skills/clavain.backup.$(date +%s) 2>/dev/null || true
make codex-refresh
```

If you have enabled the legacy link (`CLAVAIN_LEGACY_SKILLS_LINK=1`), also move:

```bash
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
make codex-doctor-json
```
