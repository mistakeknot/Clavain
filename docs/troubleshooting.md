## Troubleshooting

For full plugin and marketplace documentation, see the [official Claude Code plugin guide](https://code.claude.com/docs/en/discover-plugins).

### Plugin install fails with "Source path does not exist"

```
✘ Failed to install plugin "context7@claude-plugins-official": Source path does not exist: <marketplace-cache>
```

The local marketplace clone is stale or corrupted. The official `claude-plugins-official` marketplace is auto-provisioned by Claude Code — remove the cached copy and restart:

```bash
rm -rf ~/.claude/plugins/marketplaces/claude-plugins-official
claude   # restart — Claude Code re-provisions the official marketplace automatically
```

Or refresh from within Claude Code:

```
/plugin marketplace update claude-plugins-official
```

### Dispatch fails with a missing `.../cache/.../clavain/<version>` directory

A long-lived or resumed session resolves its Clavain plugin root once, at start, and keeps it. When an update lands and the old cache directory is pruned, that session still points at the deleted version, so `scripts/dispatch.sh`, `CLAVAIN_SELECTED_ROOT` and skill paths fail with "No such file or directory". Run `/reload-plugins` or start a fresh session; either picks up the version in `~/.claude/plugins/installed_plugins.json`. Do not recreate the old directory: pruned versions can carry retired routing seats.

### Error path shows a different user's home directory

If the error references `<another-user-home>/` instead of your home directory, the marketplace cache was created by a different user account on the same machine. Same fix — remove and restart:

```bash
rm -rf ~/.claude/plugins/marketplaces/claude-plugins-official
```

### Marketplace commands reference

```bash
# Add a marketplace
/plugin marketplace add owner/repo

# List all marketplaces
/plugin marketplace list

# Refresh a marketplace
/plugin marketplace update marketplace-name

# Install a plugin
/plugin install plugin-name@marketplace-name

# Check for errors
/plugin   # then go to the Errors tab
```

### interagency-marketplace not found

If Clavain's companion plugins fail to install, add the marketplace manually:

```
/plugin marketplace add mistakeknot/interagency-marketplace
```
