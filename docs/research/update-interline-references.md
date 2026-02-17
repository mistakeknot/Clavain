# Analysis: Bulk Rename clodex -> interserve in interline Plugin

**Date:** 2026-02-16
**Scope:** interline plugin files + live config/installed script

## Summary

Renamed all references from `clodex`/`Clodex`/`CLODEX` to `interserve`/`Interserve`/`INTERSERVE` across 7 files in the interline plugin and its installed copies.

## Files Modified

### 1. `/root/projects/Interverse/plugins/interline/scripts/statusline.sh` (source)
~30 replacements across these categories:
- **Config variable**: `cfg_clodex_label` -> `cfg_interserve_label`
- **Config path**: `.labels.clodex` -> `.labels.interserve`
- **Shell variable**: `clodex_label` -> `interserve_label`
- **Default value**: `:-Clodex` -> `:-Interserve`
- **Function name**: `_il_clodex_rainbow` -> `_il_interserve_rainbow`
- **JSON path (jq)**: `.colors.clodex` -> `.colors.interserve`
- **Config path**: `.layers.clodex` -> `.layers.interserve`
- **Flag file**: `clodex-toggle.flag` -> `interserve-toggle.flag`
- **Shell variable**: `clodex_suffix` -> `interserve_suffix`
- **Comments**: `clodex mode` -> `interserve mode`, function description comments
- **Case pattern**: `clodex*)` -> `interserve*)` in transcript skill-to-phase mapping

### 2. `/root/.claude/statusline.sh` (installed copy)
Identical changes as the source statusline.sh above.

### 3. `/root/projects/Interverse/plugins/interline/scripts/install.sh`
- JSON key `"clodex"` -> `"interserve"` (in colors, layers sections of default config)
- JSON value `"Clodex"` -> `"Interserve"` (in labels section of default config)

### 4. `/root/projects/Interverse/plugins/interline/commands/statusline-setup.md`
- Config table entries: `colors.clodex`, `layers.clodex`, `labels.clodex` -> `colors.interserve`, `layers.interserve`, `labels.interserve`
- Display text: `Clodex label` -> `Interserve label`, `clodex mode` -> `interserve mode`
- Default values: `"Clodex"` -> `"Interserve"`
- JSON example: `"clodex": 44` -> `"interserve": 44`

### 5. `/root/projects/Interverse/plugins/interline/CLAUDE.md`
- JSON config examples: `"clodex"` -> `"interserve"`, `"Clodex"` -> `"Interserve"`
- Color/layer/label paths: `colors.clodex`, `labels.clodex` -> `colors.interserve`, `labels.interserve`
- Priority layer description: `Clodex mode` -> `Interserve mode`, `clodex toggle flag` -> `interserve toggle flag`

### 6. `/root/projects/Interverse/plugins/interline/docs/plans/2026-02-12-statusline-improvements.md`
- All `clodex` references -> `interserve` (lowercase only; file had no capitalized variants)

### 7. `/root/.claude/interline.json` (live config)
- JSON keys: `"clodex"` -> `"interserve"` (in colors, layers sections)
- JSON values: `"Clodex"` -> `"Interserve"` (in labels section)

## Validation

All files passed post-edit validation:
- `bash -n statusline.sh` (both source and installed) -- syntax OK
- `bash -n install.sh` -- syntax OK
- `jq . interline.json` -- valid JSON
- `grep -ri 'clodex'` across all files -- zero remaining references

## Naming Conventions Applied

| Pattern | Before | After |
|---------|--------|-------|
| lowercase (vars, JSON keys, functions) | `clodex` | `interserve` |
| Title case (labels, display text) | `Clodex` | `Interserve` |
| ALL CAPS (env vars) | `CLODEX` | `INTERSERVE` |
| File names | `clodex-toggle.flag` | `interserve-toggle.flag` |

Note: No `CLODEX` (all-caps) references existed in these files, so only lowercase and title-case patterns were applied.

## Downstream Considerations

- The `clodex-toggle.flag` -> `interserve-toggle.flag` rename means any existing `.claude/clodex-toggle.flag` files in project directories will no longer be detected. The clavain toggle command that creates this flag file also needs to be updated separately (it lives in the clavain plugin, not interline).
- The installed copy at `~/.claude/statusline.sh` was updated in-place. A re-install via `bash install.sh` would also produce the correct output since the source was updated.
- Plugin cache copies (in `~/.claude/plugins/cache/`) still have old references but those are managed by plugin versioning and will be replaced on next install/update.
