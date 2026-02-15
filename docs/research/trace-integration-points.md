# Clavain Companion Plugin Integration Analysis

**Date:** 2026-02-14  
**Scope:** How interpath, interdoc, and interwatch are integrated with Clavain  
**Status:** Complete mapping of wired + declarative structures

---

## Executive Summary

Clavain integrates 5 companion plugins (interflux, interphase, interline, interpath, interwatch) through a consistent 3-part pattern:

1. **Discovery mechanism** — environ vars + plugin cache search in `hooks/lib.sh`
2. **Session detection** — `hooks/session-start.sh` detects companions and reports them
3. **Routing** — Commands delegate to companions via direct invocation or skill references
4. **Health checks** — Doctor checks verify each companion's presence
5. **Shim delegation** — `lib-discovery.sh` and `lib-gates.sh` are shims that delegate to interphase when present

The wiring is **mostly complete** but has several **automation gaps** where manual steps could be eliminated.

---

## 1. Discovery Mechanism

### 1.1 Clavain's Discovery Functions (hooks/lib.sh)

Four discovery functions follow identical pattern:

```bash
_discover_beads_plugin()       # interphase
_discover_interflux_plugin()   # interflux
_discover_interpath_plugin()   # interpath
_discover_interwatch_plugin()  # interwatch
```

**Algorithm:**
1. Check environment variable (e.g., `INTERPHASE_ROOT`, `INTERFLUX_ROOT`)
2. If not set, search plugin cache via `find ... -path '*/<plugin>/*/marker-file'`
3. Return plugin root directory or empty string

**Marker files used:**
- interphase: `hooks/lib-gates.sh`
- interflux: `.claude-plugin/plugin.json`
- interpath: `scripts/interpath.sh`
- interwatch: `scripts/interwatch.sh`

### 1.2 Session-Start Detection (hooks/session-start.sh, lines 77-93)

When session starts, all companions are discovered and reported in injected context:

```bash
interflux_root=$(_discover_interflux_plugin)
if [[ -n "$interflux_root" ]]; then
    companions="${companions}\\n- **interflux**: review engine available (fd-* agents, domain detection, qmd)"
fi

interpath_root=$(_discover_interpath_plugin)
if [[ -n "$interpath_root" ]]; then
    companions="${companions}\\n- **interpath**: product artifact generation (roadmaps, PRDs, vision docs)"
fi

interwatch_root=$(_discover_interwatch_plugin)
if [[ -n "$interwatch_root" ]]; then
    companions="${companions}\\n- **interwatch**: doc freshness monitoring"
fi
```

**Status:** ✅ Fully implemented. Detection is lightweight and graceful.

---

## 2. Injection Points

### 2.1 SessionStart Hook Injection (session-start.sh, lines 160-167)

Every session receives:
- Full `using-clavain` skill content (line 48)
- Companion detection summary (lines 52-93)
- Conventions reminder (line 107)
- Setup hint (line 110)
- Upstream staleness warning (lines 112-124)
- Sprint awareness (lines 126-133)
- Work discovery brief scan (lines 135-146)
- Previous session handoff (lines 148-157)

All injected as JSON `additionalContext` with escaped content.

**Context size:** ~500-1000 lines depending on sprint state and handoff presence.

**Status:** ✅ Fully implemented. Context is deterministically generated and tested.

### 2.2 Shim Delegation (lib-discovery.sh and lib-gates.sh)

Two shim files in Clavain delegate to interphase when available:

**lib-discovery.sh (lines 14-23):**
```bash
if [[ -n "$_BEADS_ROOT" && -f "${_BEADS_ROOT}/hooks/lib-discovery.sh" ]]; then
    source "${_BEADS_ROOT}/hooks/lib-discovery.sh"
else
    # No-op stubs
    discovery_scan_beads() { echo "DISCOVERY_UNAVAILABLE"; }
    infer_bead_action() { echo "brainstorm|"; }
    discovery_log_selection() { return 0; }
fi
```

**lib-gates.sh (lines 14-30):**
```bash
if [[ -n "$_BEADS_ROOT" && -f "${_BEADS_ROOT}/hooks/lib-gates.sh" ]]; then
    source "${_BEADS_ROOT}/hooks/lib-gates.sh"
else
    # Safe no-op stubs — all return success, never block
    is_valid_transition() { return 1; }
    check_phase_gate() { return 0; }
    advance_phase() { return 0; }
fi
```

**Status:** ✅ Fully implemented. Graceful degradation when interphase absent.

**Used by:**
- `lfg.md` — calls `discovery_scan_beads`, `infer_bead_action`, `discovery_log_selection`
- `lfg.md` — calls `advance_phase` after each step

---

## 3. Routing to Companion Plugins

### 3.1 Alias Commands (deep-review.md)

Some Clavain commands are aliases to companion commands:

| Clavain Command | Companion Command | Type |
|-----------------|-------------------|------|
| `/clavain:deep-review` | `/interflux:flux-drive` | Alias (in help.md) |
| `/clavain:cross-review` | `/clavain:interpeer` | Alias (in help.md) |
| `/clavain:full-pipeline` | `/clavain:lfg` | Alias (in help.md) |

**deep-review.md (line 8):**
```
Use the `interflux:flux-drive` skill to review the document or directory specified by the user.
```

This is a delegation, not an implementation.

**Status:** ✅ Fully implemented in 3 commands.

### 3.2 Routing Tables (skills/using-clavain/references/routing-tables.md)

Comprehensive routing tables reference companion plugins:

**Layer 1 (Stage):**
| Stage | Primary Commands |
|-------|-----------------|
| Review (docs) | `flux-drive` → `/interflux:flux-drive` |
| Execute | `/lfg` uses work discovery via `/interphase` |
| Ship | Uses `/interflux:fd-safety` for final gates |

**Layer 2 (Domain):**
| Domain | Agents |
|--------|--------|
| Docs | `interflux:research:framework-docs-researcher`, `interflux:research:learnings-researcher` |
| Research | `interflux:research:best-practices-researcher`, `interflux:research:repo-research-analyst` |

**Layer 3 (Concern):**
| Concern | Agent |
|---------|--------|
| Architecture | `interflux:fd-architecture` |
| Security | `interflux:fd-safety` |
| Correctness | `interflux:fd-correctness` |
| Data integrity | `data-migration-expert` (in Clavain) |

**Status:** ✅ Fully implemented. 27 direct references to interflux agents.

### 3.3 Command Delegation (lfg.md)

`/lfg` (the flagship workflow) gates execution on `/interflux:flux-drive`:

**Line 108:**
```bash
`/interflux:flux-drive <plan-file-from-step-3>`
```

**Line 122:**
```
Gate blocked: plan must be reviewed first. Run /interflux:flux-drive on the plan...
```

This is a **hard requirement** — `lfg` cannot progress without flux-drive review.

**Status:** ✅ Fully implemented. Gate enforcement built in.

---

## 4. Doctor Checks (commands/doctor.md)

### 4.1 Companion Health Checks

Doctor runs 5 companion checks:

**3b — Beads Lifecycle (interphase):**
```bash
if ls ~/.claude/plugins/cache/*/interphase/*/hooks/lib-gates.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interphase: installed"
else
  echo "interphase: not installed (phase tracking disabled)"
fi
```

**3c — Statusline (interline):**
```bash
if ls ~/.claude/plugins/cache/*/interline/*/scripts/statusline.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interline: installed"
else
  echo "interline: not installed (statusline rendering unavailable)"
fi
```

**3d — Artifact Generation (interpath):**
```bash
if ls ~/.claude/plugins/cache/*/interpath/*/scripts/interpath.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interpath: installed"
else
  echo "interpath: not installed (product artifact generation unavailable)"
fi
```

**3e — Doc Freshness (interwatch):**
```bash
if ls ~/.claude/plugins/cache/*/interwatch/*/scripts/interwatch.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interwatch: installed"
else
  echo "interwatch: not installed (doc drift detection unavailable)"
fi
```

**Status:** ✅ Fully implemented. Each companion has a check with install instructions.

---

## 5. Setup (commands/setup.md)

### 5.1 Required Plugins Installation

Setup installs all 5 companions from `interagency-marketplace`:

```bash
claude plugin install interphase@interagency-marketplace
claude plugin install interline@interagency-marketplace
claude plugin install interpath@interagency-marketplace
claude plugin install interwatch@interagency-marketplace
claude plugin install interdoc@interagency-marketplace
```

Plus 8 other required plugins (context7, agent-sdk-dev, etc.).

**Status:** ✅ Fully implemented. Setup is comprehensive.

### 5.2 Post-Install Verification

After installation, setup verifies companions:

```bash
echo "interline: $(ls ~/.claude/plugins/cache/*/interline/*/scripts/statusline.sh 2>/dev/null | head -1 >/dev/null && echo 'installed' || echo 'not installed')"
echo "oracle: $(command -v oracle >/dev/null 2>&1 && echo 'installed' || echo 'not installed')"
echo "beads: $(ls .beads/ 2>/dev/null | head -1 >/dev/null && echo 'configured' || echo 'not configured')"
```

**Status:** ✅ Fully implemented.

---

## 6. Cross-References in Documentation

### 6.1 PRD.md (Section 4.4 — Companion Plugins)

Companions are formally declared as part of the product:

```markdown
| Companion | What it does | Status |
|-----------|-------------|--------|
| **interflux** | Multi-agent review + research engine (7 fd-* agents, 5 research agents, 2 skills, 2 MCP servers) | Shipped |
| **interphase** | Phase tracking, gates, and work discovery | Shipped |
| **interline** | Statusline renderer (dispatch state, bead context, phase, clodex mode) | Shipped |
| **interpath** | Product artifact generation (roadmaps, PRDs, vision docs, changelogs, status reports) | Shipped |
| **interwatch** | Doc freshness monitoring (drift detection, confidence scoring, auto-refresh) | Shipped |
```

**Status:** ✅ Fully documented in PRD.

### 6.2 Vision.md (Section "The inter-* constellation")

Vision declares the companion extraction pattern:

```markdown
| Companion | Crystallized Insight | Status |
|---|---|---|
| interphase | Phase tracking and gates are generalizable | Shipped |
| interflux | Multi-agent review is generalizable | Shipped |
| interline | Statusline rendering is generalizable | Shipped |
| interpath | Product artifact generation is generalizable | Shipped |
| interwatch | Doc freshness monitoring is generalizable | Shipped |
```

**Status:** ✅ Fully documented in Vision.

### 6.3 Roadmap.md

Roadmap explicitly states:

```markdown
Clavain is a general-purpose engineering discipline plugin for Claude Code — 27 skills, 5 agents, 36 commands, 7 hooks, 1 MCP server. Five companion plugins shipped (interflux, interphase, interline, interpath, interwatch); four more planned.
```

**Status:** ✅ Fully documented in Roadmap.

### 6.4 CLAUDE.md

Clavain's local instructions list companions:

```markdown
Companions: `interphase` (phase tracking, gates, discovery), `interline` (statusline renderer), `interflux` (multi-agent review + research engine).
```

⚠️ **INCOMPLETE:** Only lists 3 companions; missing interpath and interwatch.

**Status:** ⚠️ Partially implemented.

---

## 7. Hook Integration

### 7.1 SessionStart Hook (hooks/session-start.sh)

- Discovers all companions (lines 77-93)
- Detects beads and surfaces health warnings (lines 56-70)
- Detects Oracle for cross-AI review (lines 72-75)
- Injects companion context (lines 101-104)

**Status:** ✅ Fully implemented.

### 7.2 PostToolUse Hook (auto-publish.sh)

Auto-publishes plugin after `git push` on main.

**Usage:** Used by plugin developers. When they push Clavain or a companion, auto-publish triggers.

**Status:** ✅ Fully implemented. Only relevant for plugin devs.

### 7.3 Stop Hook (auto-compound.sh)

Auto-triggers knowledge compounding after non-trivial sessions.

**Usage:** Captures learnings when commit weight + resolution weight >= 3.

**Status:** ✅ Fully implemented. Applies to all projects using Clavain.

### 7.4 Session Handoff (session-handoff.sh)

Generates `.clavain/scratch/handoff.md` for incomplete work.

**Status:** ✅ Fully implemented. Injected into next session via session-start.

**Status:** ✅ Fully implemented.

### 7.5 Dotfiles Sync (dotfiles-sync.sh)

On SessionEnd, syncs dotfile changes.

**Status:** ✅ Fully implemented. Relevant for workspace sync.

---

## 8. interdoc Wiring (interwatch Integration)

### 8.1 interdoc Marker Discovery

interwatch discovers interdoc via marker file:

**File:** `/root/projects/interdoc/scripts/interdoc-generator.sh`

```bash
#!/usr/bin/env bash
# Marker file for interwatch generator discovery.
# Presence of this file signals that interdoc can handle AGENTS.md generation
# requests from interwatch's drift-detection framework.
echo "interdoc-generator marker"
```

**Status:** ✅ Marker exists and is discoverable.

### 8.2 interwatch Watchables Configuration

interwatch monitors 4 documents:

**File:** `/root/projects/interwatch/config/watchables.yaml`

```yaml
watchables:
  - name: roadmap
    path: docs/roadmap.md
    generator: interpath:artifact-gen
    generator_args: { type: roadmap }

  - name: prd
    path: docs/PRD.md
    generator: interpath:artifact-gen
    generator_args: { type: prd }

  - name: vision
    path: docs/vision.md
    generator: interpath:artifact-gen
    generator_args: { type: vision }

  - name: agents-md
    path: AGENTS.md
    generator: interdoc:interdoc
    generator_args: {}
```

**Generator mapping:**
- `interpath:artifact-gen` → generates product docs (roadmap, PRD, vision)
- `interdoc:interdoc` → generates AGENTS.md

**Status:** ✅ Fully configured. interwatch knows to call interdoc for AGENTS.md generation.

### 8.3 Signals Monitored

For AGENTS.md, interwatch watches for:
- `file_renamed` (weight 3)
- `file_deleted` (weight 3)
- `file_created` (weight 2)
- `commits_since_update` (weight 1, threshold 20)

Staleness threshold: 14 days.

**Status:** ✅ Fully configured.

---

## 9. interpath Configuration

### 9.1 Artifact Generation Integration

interpath is referenced in:

1. **Routing tables** (`skills/using-clavain/references/routing-tables.md`, line 28):
   ```
   | Check doc freshness | `/interwatch:watch` or `/interwatch:status` |
   | Generate a roadmap | `/interpath:roadmap` |
   | Generate a PRD | `/interpath:prd` |
   ```

2. **Session-start** (lines 84-86):
   ```bash
   interpath_root=$(_discover_interpath_plugin)
   if [[ -n "$interpath_root" ]]; then
       companions="${companions}\\n- **interpath**: product artifact generation (roadmaps, PRDs, vision docs)"
   fi
   ```

3. **Watchables config** (lines 4, 24, 40):
   Maps roadmap, PRD, vision to `interpath:artifact-gen` generator.

**Status:** ✅ Fully integrated.

---

## 10. Automation Gaps (What's NOT Wired)

### 10.1 Critical Gap: CLAUDE.md Incomplete

**Issue:** `/root/projects/Clavain/CLAUDE.md` lists only 3 companions:

```markdown
Companions: `interphase` (phase tracking, gates, discovery), 
`interline` (statusline renderer), `interflux` (multi-agent review + research engine).
```

**Missing:** interpath, interwatch

**Impact:** New developers reading CLAUDE.md won't know about product artifact generation or doc freshness monitoring.

**Fix:** Update CLAUDE.md line 6 to include all 5 companions.

---

### 10.2 Gap: interwatch Not Auto-Triggered

**Issue:** interwatch is discovered and reported in session-start, but **no hook automatically runs interwatch checks** or triggers doc refreshes.

**Current state:**
- interwatch exists and can be manually invoked (`/interwatch:watch`)
- Watchables config is complete (`roadmap`, `prd`, `vision`, `agents-md`)
- Staleness thresholds are set (7-30 days)

**Missing:**
- No scheduled checks (e.g., on `/lfg` completion, on upstream-sync)
- No auto-refresh hook (e.g., when PRD is stale, auto-regenerate with interpath)

**Opportunity:** Could add PostToolUse hook that:
1. Runs `interwatch status` after major workflows (`lfg`, `upstream-sync`)
2. Reports staleness to user
3. Optionally auto-triggers interpath regeneration for stale product docs

---

### 10.3 Gap: interdoc Not Automatically Called

**Issue:** interdoc is mapped in watchables.yaml but not automatically invoked.

**Current state:**
- Watchables defines `generator: interdoc:interdoc` for AGENTS.md
- interdoc marker file exists
- No mechanism to trigger interdoc on file changes

**Missing:**
- No hook or command that calls interdoc when agents/commands/skills change
- AGENTS.md drift detection is passive (interwatch reports staleness, doesn't fix it)

**Opportunity:** Could add:
1. PostToolUse hook that detects skill/agent/command file writes
2. Automatically calls `interpath` (via Clavain) to re-run, then commits AGENTS.md
3. Or, add `/interwatch:refresh` command that calls interwatch to find stale docs and interpath/interdoc to regenerate them

---

### 10.4 Gap: Companion Plugin Installation Not Automated

**Issue:** `/setup` requires manual `claude plugin install` commands.

**Current state:**
- Setup.md lists 7 install commands (lines 30-38)
- User must run them manually or copy-paste

**Missing:**
- No bash script that runs all installs atomically
- No detection of already-installed versions

**Opportunity:** Could refactor setup to:
1. Loop through plugin list
2. Check if each is installed (via `ls ~/.claude/plugins/cache/*/plugin-name/...`)
3. Only install if missing
4. Report summary

---

### 10.5 Gap: Cross-Plugin Health Summary Incomplete

**Issue:** Doctor checks companions individually but doesn't synthesize findings.

**Current state:**
- Doctor runs 5 companion checks (3b-3e)
- Each check reports pass/fail/missing

**Missing:**
- No recommendation if multiple companions are missing
- No summary of "you have 4/5 companions installed"
- No check for companion version mismatches

**Opportunity:** Could add:
1. Companion count in doctor summary
2. Version check (compare installed vs latest in marketplace)
3. Suggest companion extraction path (e.g., "You have interflux + interpath, consider extracting intercraft next")

---

### 10.6 Gap: No Phase Tracking Without interphase

**Issue:** Phase tracking gates (`check_phase_gate`, `advance_phase`) are no-ops if interphase is absent.

**Current state:**
- Shims provide safe no-ops (never block)
- `lfg` calls `advance_phase` after each step
- If interphase is absent, phase tracking silently skips

**Missing:**
- No warning that phase tracking is disabled
- No suggestion to install interphase
- No way to see which phases a bead has passed through

**Opportunity:** Could:
1. Add warning in session-start if interphase is missing (similar to beads doctor warning, line 66-68)
2. Add phase-tracking status to doctor output
3. Suggest installing interphase if phase-aware workflows are used

---

### 10.7 Gap: Upstream Sync Doesn't Check Companion Updates

**Issue:** Upstream sync checks Clavain's upstreams but not companion plugin updates.

**Current state:**
- `scripts/upstream-check.sh` monitors 6 upstreams (superpowers, compound-engineering, oracle, beads, etc.)
- No mechanism to check if companion plugins have updates in marketplace

**Missing:**
- No check for `interflux@interagency-marketplace` version updates
- No check for `interpath@interagency-marketplace` version updates

**Opportunity:** Could:
1. Add marketplace version check to upstream-check
2. Report if companion versions lag behind marketplace
3. Suggest `claude plugin update <companion>` commands

---

### 10.8 Gap: No Companion Dependency Graph

**Issue:** Companions have implicit dependencies but no declarative specification.

**Current state:**
- `lfg` depends on interphase (work discovery, phase tracking)
- `lfg` depends on interflux (plan review gating)
- But no manifest or configuration declares these

**Missing:**
- No way to know which companions are critical vs optional
- No dependency resolution in setup

**Opportunity:** Could:
1. Add `dependencies` field to plugin.json
2. Declare `interphase` and `interflux` as critical
3. Have setup warn if critical companions fail to install

---

## 11. Wiring Summary

### What IS Implemented

✅ Discovery mechanism (4 functions in lib.sh, env var + cache search)  
✅ Session-start detection (all 5 companions detected and reported)  
✅ Routing (commands delegate to companions)  
✅ Doctor checks (3b-3e verify companion presence)  
✅ Setup (manual install commands listed)  
✅ Shim delegation (lib-discovery.sh, lib-gates.sh)  
✅ Watchables config (interwatch knows about roadmap, prd, vision, agents-md)  
✅ interdoc marker (discovery file exists)  
✅ Routing tables (27 references to interflux agents)  
✅ Cross-documentation (PRD, vision, roadmap all reference companions)

### What is INCOMPLETE or GAP-PRONE

⚠️ CLAUDE.md missing interpath + interwatch from companion list  
⚠️ No auto-trigger for interwatch checks after major workflows  
⚠️ No auto-call to interdoc/interpath for doc refresh  
⚠️ Setup requires manual plugin install commands  
⚠️ No companion version checking in upstream sync  
⚠️ No companion dependency declaration in plugin.json  
⚠️ No warning if interphase is missing but phase-aware workflows are used  
⚠️ No cross-plugin health synthesis in doctor output  

---

## 12. Recommended Automation Sequence

### Priority 1: Documentation Fix (5 minutes)
1. Update CLAUDE.md to list all 5 companions
2. Add brief descriptions for interpath and interwatch

### Priority 2: Auto-Trigger interwatch (30 minutes)
1. Create new PostToolUse hook: `check-doc-freshness.sh`
2. Trigger after `/lfg` completion and `/upstream-sync`
3. Run `interwatch status` and report results
4. Optionally suggest `/interwatch:refresh` for stale docs

### Priority 3: Automated Setup (45 minutes)
1. Refactor setup.md into companion plugin install loop
2. Check if already installed before running
3. Report summary of installed vs skipped

### Priority 4: Upstream Integration (1 hour)
1. Add marketplace version check to upstream-check.sh
2. Report companion version differences
3. Suggest update commands

### Priority 5: Dependency Declaration (1 hour)
1. Add `dependencies` field to plugin.json
2. Declare interphase + interflux as critical
3. Update setup to verify critical dependencies

---

## 13. Files Involved

**Clavain Core:**
- `hooks/lib.sh` — 4 discovery functions
- `hooks/session-start.sh` — Detection + injection
- `hooks/lib-discovery.sh` — Shim (interphase delegation)
- `hooks/lib-gates.sh` — Shim (interphase delegation)
- `commands/doctor.md` — Health checks 3b-3e
- `commands/setup.md` — Installation instructions
- `skills/using-clavain/references/routing-tables.md` — Routing reference
- `CLAUDE.md` — ⚠️ Incomplete (missing 2 companions)
- `docs/PRD.md` — ✅ Complete
- `docs/vision.md` — ✅ Complete
- `docs/roadmap.md` — ✅ Complete

**Companion Plugins:**
- `interwatch/config/watchables.yaml` — 4 watchables, 2 generators (interpath, interdoc)
- `interdoc/scripts/interdoc-generator.sh` — Marker file
- `interflux/config/flux-drive/domains/` — 11 domain profiles

**Tests:**
- `tests/structural/test_discovery.py` — Tests lib-discovery.sh + lfg.md
- `tests/structural/test_commands.py` — 36 command count guard

---

## 14. Conclusion

The companion plugin ecosystem is **well-wired at the core**:
- Discovery is automatic and robust
- Session injection is deterministic
- Routing is explicit in documentation and commands
- Health checks are comprehensive
- Graceful degradation via shims ensures Clavain works even if companions are missing

However, there are **clear automation opportunities** that would reduce manual steps and improve visibility:
1. Auto-trigger doc freshness checks
2. Auto-call doc regenerators
3. Declare companion dependencies
4. Sync marketplace versions in upstream checks
5. Synthesize cross-plugin health in doctor

The gaps are not critical — they're quality-of-life improvements that would make the system more discoverable and self-maintaining.

