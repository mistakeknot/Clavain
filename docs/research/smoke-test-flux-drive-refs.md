# Smoke Test: Flux Drive Reference Extraction

**Date:** 2026-02-13
**Test Type:** Read-only verification of reference pointers and content validation
**Tester:** Claude Code

---

## Test Results

### Check 1: "### Scoring Examples" heading in SKILL.md
**Status:** ✅ PASS

**Location:** `/root/projects/Clavain/skills/flux-drive/SKILL.md`, line 329

**Content:**
```markdown
### Scoring Examples

Read `references/scoring-examples.md` for 4 worked examples covering different document types and domain configurations, plus thin-section threshold definitions.
```

**Findings:**
- Heading exists at the expected line
- Reference pointer correctly points to `references/scoring-examples.md`
- Pointer is a Read instruction (not a direct link)
- Pointer is correctly relative to skill directory

---

### Check 2: Content verification of scoring-examples.md
**Status:** ✅ PASS

**File:** `/root/projects/Clavain/skills/flux-drive/references/scoring-examples.md`

**Required Content Verification:**

| Content | Location | Status |
|---------|----------|--------|
| "Plan reviewing Go API changes" | Line 7 | ✅ Found |
| "Thin section thresholds" | Line 63 (heading) | ✅ Found |

**Full Context - "Plan reviewing Go API changes":**
```
**Plan reviewing Go API changes (project has CLAUDE.md, web-api domain detected):**

Slot ceiling: 4 (base) + 0 (single file) + 1 (1 domain) = 5 slots. Stage 1: top 2 (40% of 5, rounded up).
```

**Full Context - "Thin section thresholds":**
```
**Thin section thresholds:**
- **thin**: <5 lines or <3 bullet points — agent with adjacent domain should cover this
- **adequate**: 5-30 lines or 3-10 bullet points — standard review depth
- **deep**: 30+ lines or 10+ bullet points — validation only, don't over-review
```

---

### Check 3: "## Agent Roster" heading in SKILL.md
**Status:** ✅ PASS

**Location:** `/root/projects/Clavain/skills/flux-drive/SKILL.md`, line 387

**Content:**
```markdown
## Agent Roster

Read `references/agent-roster.md` for the full agent roster including:
- Project Agents (`.claude/agents/fd-*.md`)
- Plugin Agents (7 core fd-* agents with subagent_type mappings)
- Cross-AI (Oracle CLI invocation, error handling, slot rules)
```

**Findings:**
- Heading exists at the expected line
- Reference pointer correctly points to `references/agent-roster.md`
- Pointer is a Read instruction
- Pointer is correctly relative to skill directory
- Descriptive context explains what will be found in the reference file

---

### Check 4: Content verification of agent-roster.md
**Status:** ✅ PASS

**File:** `/root/projects/Clavain/skills/flux-drive/references/agent-roster.md`

**Required Content Verification:**

| Content | Location | Status |
|---------|----------|--------|
| "clavain:review:fd-architecture" | Line 21 | ✅ Found |
| "oracle --wait --timeout 1800" | Line 47 | ✅ Found |

**Full Context - "clavain:review:fd-architecture":**
```
| fd-architecture | clavain:review:fd-architecture | Module boundaries, coupling, patterns, anti-patterns, complexity |
```
Located in the "Plugin Agents" section, mapping agent names to their subagent_type identifiers.

**Full Context - "oracle --wait --timeout 1800":**
```bash
env DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait --timeout 1800 \
  --write-output {OUTPUT_DIR}/oracle-council.md.partial \
  -p "Review this {document_type} for {review_goal}. Focus on: issues a Claude-based reviewer might miss. Provide numbered findings with severity." \
  -f "{INPUT_FILE or key files}" && \
```
Located in the "Cross-AI (Oracle)" section, demonstrating proper Oracle CLI invocation with environment variables, clean output capture, and timeout handling.

---

## Orchestrator Simulation Summary

The flux-drive orchestrator performs the following reference extraction workflow:

1. **Phase 1, Step 1.2**: Reads main SKILL.md
2. **At line 329**: Encounters "### Scoring Examples" with Read pointer
3. **Loads reference**: Reads `references/scoring-examples.md`
4. **Validates content**: Confirms "Plan reviewing Go API changes" (line 7) and "Thin section thresholds" (line 63)
5. **At line 387**: Encounters "## Agent Roster" with Read pointer
6. **Loads reference**: Reads `references/agent-roster.md`
7. **Validates content**: Confirms "clavain:review:fd-architecture" (line 21) and Oracle invocation pattern with "--timeout 1800" (line 47)

---

## Key Findings

### File Structure Validation
- **Pointer consistency:** All Read instructions use relative paths (e.g., `references/scoring-examples.md`)
- **Navigation pattern:** SKILL.md → references/* is a clean two-level hierarchy
- **Completeness:** All references mentioned in SKILL.md actually exist and are accessible

### Content Validation
1. **Scoring Examples** (4 worked examples):
   - ✅ Go API plan (web-api domain)
   - ✅ Python CLI README (cli-tool domain)
   - ✅ User onboarding PRD (web-api domain)
   - ✅ Game project plan (game-simulation domain with /flux-gen agents)
   - ✅ Thin section threshold definitions included

2. **Agent Roster** (3 agent categories):
   - ✅ Project Agents (`.claude/agents/fd-*.md` bootstrap)
   - ✅ Plugin Agents (7 core fd-* agents with subagent_type mappings)
   - ✅ Cross-AI (Oracle CLI with proper environment setup, `--wait`, `--timeout 1800`, `--write-output` for browser mode, no external `timeout` wrapper)

### Critical Details Verified
- Oracle invocation uses `--write-output` (not stdout redirect) for browser mode compatibility
- Oracle timeout is internal (`--timeout 1800`) not external wrapper
- Environment variables (`DISPLAY=:99`, `CHROME_PATH`) are properly set
- All agent names use `clavain:review:` namespace prefix
- Error handling is documented (fallback on Oracle failure, continue without Phase 4)

---

## Test Outcome

**Overall:** ✅ **ALL CHECKS PASS**

All reference pointers are correctly implemented and all referenced content exists and contains the expected search terms. The flux-drive skill reference extraction system is functioning as designed.
