# Beads Plugin Skill File Changes Analysis

**Date**: 2026-02-10  
**Analysis Scope**: 258 commits since last sync (eb1049ba → HEAD)  
**Sync Commit**: eb1049ba - "fix(sqlite): make Close() idempotent to prevent WAL retry deadlock (bd-4ri)"

## Executive Summary

Of 258 commits in the beads upstream since Clavain's last sync, **only 2 skill files changed**:
1. `claude-plugin/skills/beads/resources/CLI_REFERENCE.md` - Updated documentation
2. `claude-plugin/skills/beads/resources/TROUBLESHOOTING.md` - Minor fix

**Risk Level**: LOW — Only documentation changes, no breaking changes to skill structure or behavior.

## Changed Files

### 1. CLI_REFERENCE.md

**Type**: Documentation update  
**Changes**: 3 new sections added

#### Added Sections:

**a) External Reference Examples (v0.9.2+)**
```markdown
# Create with external reference (v0.9.2+)
bd create "Fix login" -t bug -p 1 --external-ref "gh-123" --json  # Short form
bd create "Fix login" -t bug -p 1 --external-ref "https://github.com/org/repo/issues/123" --json  # Full URL
bd create "Jira task" -t task -p 1 --external-ref "jira-PROJ-456" --json  # Custom prefix
```

**b) Update External Reference Examples (v0.9.2+)**
```markdown
# Update external reference (v0.9.2+)
bd update <id> --external-ref "gh-456" --json           # Short form
bd update <id> --external-ref "jira-PROJ-789" --json    # Custom prefix
```

**c) Find Beads Issue by External Reference**
```markdown
# Find beads issue by external reference
bd list --json | jq -r '.[] | select(.external_ref == "gh-123") | .id'
```

**d) External References Documentation Section**
```markdown
## External References

The `--external-ref` flag (v0.9.2+) links beads issues to external trackers:

- Supports short form (`gh-123`) or full URL (`https://github.com/...`)
- Portable via JSONL - survives sync across machines
- Custom prefixes work for any tracker (`jira-PROJ-456`, `linear-789`)
```

**Impact**: These additions document the v0.9.2+ `--external-ref` feature which allows linking beads issues to external issue trackers (GitHub, Jira, Linear, etc.). This is a non-breaking addition that enhances functionality.

### 2. TROUBLESHOOTING.md

**Type**: Minor bugfix  
**Change**: One line fix

**Before**:
```bash
brew upgrade bd
```

**After**:
```bash
brew upgrade beads
```

**Impact**: Corrects the Homebrew package name from `bd` to `beads` for the upgrade command. This is a documentation fix for users following troubleshooting steps.

## Related Upstream Commits

The external-ref feature has a commit history in beads:

| Commit | Message |
|--------|---------|
| e6be7dd3 | feat: Add external_ref field for linking to external issue trackers |
| 9de98cf1 | Add --clear-duplicate-external-refs flag to bd import |
| 57b6ea60 | fix: add external_ref support to daemon mode RPC (fixes #303) (#304) |
| 3ed8a78a | Merge pull request #1549 from maphew/fix/doc-issues-1523-1339 |
| 53c1561d | docs: fix #1523 and #1339/#1337 - ready docs and external-ref |
| 18c7c9a2 | test: add 19 integration tests for bd update edge cases (dolt-test-4f0) |

The feature is mature (multiple commits testing edge cases, daemon RPC support, import conflict handling).

## Action Items for Clavain

1. **Update Clavain's copy** of `claude-plugin/skills/beads/resources/CLI_REFERENCE.md`:
   - Add 3 new example sections for external-ref usage
   - Add "External References" documentation section
   - Keep existing content intact

2. **Update Clavain's copy** of `claude-plugin/skills/beads/resources/TROUBLESHOOTING.md`:
   - Change `brew upgrade bd` → `brew upgrade beads` (line ~55)

3. **No action needed for**:
   - Skill entry point (SKILL.md)
   - Skill command registration
   - Skill behavior or logic

## Risk Assessment

- **Breaking Changes**: None
- **Documentation Accuracy**: The updates fix an outdated Homebrew command
- **Feature Coverage**: The CLI_REFERENCE.md additions document stable v0.9.2+ features
- **Backward Compatibility**: All changes are additive; existing examples still work

## Recommendation

**Sync these documentation updates into Clavain.** The changes are low-risk documentation improvements that will keep Clavain's beads skill docs in sync with the upstream feature set.

The external-ref feature is mature and tested; documenting it in the CLI reference is appropriate for a general-purpose engineering plugin like Clavain.
