# Behavioral Layer Implementation Plan

**Date:** 2026-02-10  
**Status:** Implementation-ready design  
**Scope:** Two-repo change (Clavain + agent-rig) to add behavioral config layer via pointer-based CLAUDE.md inclusion

---

## Executive Summary

This plan implements the behavioral config layer for agent-rig, enabling rigs to ship behavioral conventions and instructions alongside infrastructure. The approach uses **pointer-based inclusion** where `agent-rig install` adds a single line to the project's `CLAUDE.md` pointing to `.claude/rigs/{name}/CLAUDE.md`, avoiding destructive merges while letting the AI agent reconcile multiple instruction sets at runtime.

**Key Innovation:** The agent becomes the merge engine. Instead of programmatically merging unstructured text (lossy and brittle), we install convention files to namespaced locations and let the AI read both the user's instructions and the rig's instructions, using its natural language understanding to reconcile conflicts.

**Scope for v1:** CLAUDE.md and AGENTS.md pointer-based inclusion only. Deferred to v1.1-v1.4: commands, skills, workflows, hooks, settings merge.

---

## Problem Statement

Currently, agent-rig installs **infrastructure** (plugins, MCP servers, tools) but not **behavioral config** (CLAUDE.md conventions, hooks, commands, workflows). This means users get the tooling but miss the disciplines and conventions that make the rig effective.

Example: Clavain ships with conventions around settings hygiene (no heredocs in bash, no multi-line loops), continuous learning (record insights to memory immediately), and workflow patterns (preserve original intent after plan simplification). These are currently in the user's personal `~/.claude/CLAUDE.md` but should ship with the rig.

---

## Design Decision: Pointer-Based Inclusion

### The Pattern

Instead of merging content INTO root-level files, install rig instructions to `.claude/rigs/{name}/CLAUDE.md` and add a **single pointer line** to the project's `CLAUDE.md`:

```markdown
<!-- agent-rig:clavain --> Also read and follow: .claude/rigs/clavain/CLAUDE.md

# My Project

...existing user content stays untouched...
```

### Why This Works

1. **Non-destructive:** User's root file is barely touched (one line added)
2. **Agent-native:** AI agents excel at reconciling natural language instructions
3. **Load order:** Root file content has final authority (user's rules override rig's)
4. **Clean uninstall:** Remove pointer line, delete `.claude/rigs/{name}/`, done
5. **Multi-rig support:** Multiple pointer lines = multiple rigs, agent reconciles all

### Why Not Alternatives

| Approach | Problem | Pointer avoids it |
|----------|---------|-------------------|
| Marker sections | Appended content can conflict with user content | Agent reconciles at runtime |
| Suggested files | User must manually merge | Zero-friction automatic |
| Interactive merge | Complex UX | No interaction needed |
| Platform include paths | Requires upstream changes to Claude Code | Works today |

---

## Architecture

### Repository Structure After Install

```
project/
├── CLAUDE.md                          ← pointer line added here
├── AGENTS.md                          ← pointer line added here (optional)
└── .claude/
    └── rigs/
        └── clavain/
            ├── CLAUDE.md              ← rig's behavioral conventions
            ├── AGENTS.md              ← rig's agent definitions (optional)
            └── install-manifest.json  ← tracks what was installed
```

### Install Manifest Format

Tracks everything installed for clean uninstall:

```json
{
  "rig": "clavain",
  "version": "0.4.16",
  "installedAt": "2026-02-10T12:34:56Z",
  "files": [
    ".claude/rigs/clavain/CLAUDE.md",
    ".claude/rigs/clavain/AGENTS.md"
  ],
  "pointers": [
    {
      "file": "CLAUDE.md",
      "line": "<!-- agent-rig:clavain --> Also read and follow: .claude/rigs/clavain/CLAUDE.md"
    },
    {
      "file": "AGENTS.md", 
      "line": "<!-- agent-rig:clavain --> Also read: .claude/rigs/clavain/AGENTS.md"
    }
  ]
}
```

---

## Implementation Plan

### Part 1: Create Generalized Conventions in Clavain

**Goal:** Extract and generalize conventions from user's personal `~/.claude/CLAUDE.md` into two deliverables:

1. **Full reference doc:** `config/CLAUDE.md` in Clavain repo (what agent-rig installs)
2. **Compact summary:** ~5-10 lines injected by SessionStart hook

#### What to Include (Generalized)

From `~/.claude/CLAUDE.md`, extract these sections and remove personal/server-specific details:

**Core Disciplines:**
- **Tool usage:** Prefer Read/Edit/Grep over Bash; Read before Edit; never edit blind
- **Settings hygiene:** Never use heredocs in Bash tool calls, never use multi-line loops, never inline long prompts, keep commands short/wildcard-friendly
- **Git workflow:** Trunk-based development, commit to main, no feature branches unless asked
- **Continuous learning:** Record insights to memory immediately when discovering bugs, gotchas, architectural facts, user corrections
- **Workflow patterns:** After plan simplification, preserve cut research in "Original Intent" section with trigger-to-feature mappings
- **Documentation standards:** Every project needs CLAUDE.md (short) + AGENTS.md (comprehensive)

**Exclude (Personal):**
- Oracle server-specific setup (DISPLAY, CHROME_PATH, NoVNC IPs)
- Plugin development workflow (marketplace names, repo paths)
- Server infrastructure (ethics-gradient, Hetzner, mutagen)
- Cross-repo workflows (intermute/Autarch)
- Task tracking preferences (beads vs file-todos)

#### File: `config/CLAUDE.md`

**Location:** `/root/projects/Clavain/config/CLAUDE.md` (NEW)

**Structure:**
```markdown
# Clavain Engineering Discipline

General-purpose conventions for disciplined software engineering with AI coding agents.

## Tool Usage Discipline

- **Prefer Read/Edit/Grep over Bash** for file operations
- **Always Read before Edit** — never edit blind
- **Use Write tool, then reference** — avoid inline content in Bash

## Settings Hygiene

Project `.claude/settings.local.json` files accumulate permission bloat. Prevent it:

- **Never use heredocs in Bash tool calls.** Write with Write tool first, then reference.
- **Never use multi-line loops in Bash.** Use one-liners or write temp scripts.
- **Never inline long prompts.** Write to file, then reference.
- **Keep Bash commands short and wildcard-friendly.**

## Git Workflow

- **Trunk-based development:** Commit directly to main branch
- Do NOT create feature branches or worktrees unless explicitly asked
- If a skill suggests branching, commit to main instead

## Continuous Learning

Proactively write to project memory when you learn something reusable:

**Record immediately when:**
- Discover a subtle bug — root cause, why it was hard to spot, fix pattern
- Hit library/framework gotcha — behavior contradicting docs
- Find architectural fact — how components connect, what's entangled
- Get corrected by user — preferences, conventions to follow
- Solve debugging puzzle — steps that worked, dead ends to skip

**What to record:**
- One-line lesson with enough context
- Links to files/lines if relevant  
- The "why" — not just "do X" but "do X because Y"

**Where:**
- `MEMORY.md` for quick-reference facts (keep under 200 lines)
- Separate topic files for detailed notes, linked from MEMORY.md

## Workflow Patterns

**Preserve Original Intent:** After plan simplification (YAGNI, cut features), don't delete research:
1. Simplify the implementation
2. Add "Original Intent" section preserving cut content
3. Include trigger-to-feature mapping for future iterations

Research shouldn't be repeated. The mapping tells future developers WHEN to add complexity, not just WHAT.

## Documentation Standards

Every project needs two docs:
- **CLAUDE.md** — Minimal quick reference (architecture, decisions)
- **AGENTS.md** — Comprehensive dev guide (setup, troubleshooting, workflows)

Keep CLAUDE.md short. Details belong in AGENTS.md.
```

**Character count:** ~2,100 characters (~350 tokens) — compact but complete.

---

### Part 2: Add SessionStart Hook Injection

**Goal:** Add compact behavioral summary to what session-start.sh already injects.

**File:** `/root/projects/Clavain/hooks/session-start.sh`

**Current behavior:** Injects `using-clavain` skill content + companion detection + upstream staleness warning

**Change:** Add behavioral summary BEFORE the using-clavain content

**New section to add (after line 60, before EOF cat):**

```bash
# Compact behavioral reminder (full rules in config/CLAUDE.md installed by agent-rig)
behavioral_summary="\\n\\n**Clavain Conventions (Quick Reference):**\\n- Prefer Read/Edit/Grep over Bash\\n- Settings hygiene: No heredocs, no multi-line loops, keep commands short\\n- Trunk-based dev: Commit to main, no branches\\n- Record insights to memory immediately (MEMORY.md)\\n- Preserve Original Intent after plan simplification"
```

**Updated additionalContext output (line 66):**

```bash
"additionalContext": "You have Clavain.${behavioral_summary}\n\n**Below is the full content of your 'clavain:using-clavain' skill...\n\n${using_clavain_escaped}${companion_context}${upstream_warning}"
```

**Total addition:** ~5 lines of bash, ~120 tokens in output

**Rationale:** SessionStart runs every session. Keep it TINY — the full conventions doc lives in `config/CLAUDE.md` which agent-rig installs to `.claude/rigs/clavain/CLAUDE.md` and the pointer in project's `CLAUDE.md` ensures it's always read.

---

### Part 3: Update Clavain's agent-rig.json

**Goal:** Add `behavioral` field pointing to the config docs

**File:** `/root/projects/Clavain/agent-rig.json`

**Change:** Add new top-level field after `environment` section:

```json
  "behavioral": {
    "claude-md": {
      "source": "config/CLAUDE.md",
      "description": "Engineering discipline conventions"
    },
    "agents-md": {
      "source": "AGENTS.md",
      "description": "Clavain agent definitions and workflows"
    }
  },
```

**v1.1+ (future):** Add `dependedOnBy` to indicate hooks/commands that depend on these conventions:

```json
    "claude-md": {
      "source": "config/CLAUDE.md",
      "description": "Engineering discipline conventions",
      "dependedOnBy": ["hooks.SessionStart", "commands/commit"]
    }
```

---

### Part 4: Extend agent-rig Schema

**Goal:** Add `behavioral` field to AgentRigSchema

**File:** `/root/projects/agent-rig/src/schema.ts`

**Changes:**

1. **Add Behavioral schema (after ExternalTool, before Platforms):**

```typescript
// --- Behavioral config ---

const BehavioralClaude = z.object({
  source: z.string().describe("Path to CLAUDE.md file in rig repo"),
  description: z.string().optional(),
  dependedOnBy: z.array(z.string()).optional().describe("Commands/hooks that depend on these conventions"),
});

const BehavioralAgents = z.object({
  source: z.string().describe("Path to AGENTS.md file in rig repo"),
  description: z.string().optional(),
});

const Behavioral = z.object({
  "claude-md": BehavioralClaude.optional(),
  "agents-md": BehavioralAgents.optional(),
});
```

2. **Add to AgentRigSchema (after environment, before platforms):**

```typescript
  // Layer 5: Behavioral configuration
  behavioral: Behavioral.optional(),
```

**Rationale:** v1 only implements CLAUDE.md and AGENTS.md. Future versions add commands, skills, workflows, hooks, settings (v1.1-v1.4 from brainstorm).

---

### Part 5: Add PlatformAdapter Method

**Goal:** Add `installBehavioral()` to adapter interface

**File:** `/root/projects/agent-rig/src/adapters/types.ts`

**Change:**

```typescript
export interface PlatformAdapter {
  name: string;
  detect(): Promise<boolean>;
  installPlugins(rig: AgentRig): Promise<InstallResult[]>;
  disableConflicts(rig: AgentRig): Promise<InstallResult[]>;
  addMarketplaces(rig: AgentRig): Promise<InstallResult[]>;
  verify(rig: AgentRig): Promise<InstallResult[]>;
  installBehavioral(rig: AgentRig, rigDir: string): Promise<InstallResult[]>;  // NEW
}
```

**Parameters:**
- `rig` — The parsed manifest
- `rigDir` — Absolute path to rig repo (for reading source files)

---

### Part 6: Implement Pointer Install in ClaudeCodeAdapter

**Goal:** Copy behavioral source files to `.claude/rigs/{name}/` and add pointer lines to root files

**File:** `/root/projects/agent-rig/src/adapters/claude-code.ts`

**New imports:**

```typescript
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";
```

**New method (add after verify()):**

```typescript
  async installBehavioral(rig: AgentRig, rigDir: string): Promise<InstallResult[]> {
    const results: InstallResult[] = [];
    if (!rig.behavioral) return results;

    const rigInstallDir = join(process.cwd(), ".claude", "rigs", rig.name);
    await mkdir(rigInstallDir, { recursive: true });

    const installManifest = {
      rig: rig.name,
      version: rig.version,
      installedAt: new Date().toISOString(),
      files: [] as string[],
      pointers: [] as Array<{ file: string; line: string }>,
    };

    // Install CLAUDE.md
    if (rig.behavioral["claude-md"]) {
      const sourcePath = join(rigDir, rig.behavioral["claude-md"].source);
      const destPath = join(rigInstallDir, "CLAUDE.md");
      const destRelative = `.claude/rigs/${rig.name}/CLAUDE.md`;

      try {
        const content = await readFile(sourcePath, "utf-8");
        await writeFile(destPath, content, "utf-8");
        installManifest.files.push(destRelative);

        // Add pointer to project CLAUDE.md
        const projectClaudeMd = join(process.cwd(), "CLAUDE.md");
        const pointerLine = `<!-- agent-rig:${rig.name} --> Also read and follow: ${destRelative}`;
        
        let projectContent = "";
        if (existsSync(projectClaudeMd)) {
          projectContent = await readFile(projectClaudeMd, "utf-8");
        }

        // Check if pointer already exists
        if (!projectContent.includes(`<!-- agent-rig:${rig.name} -->`)) {
          const updatedContent = pointerLine + "\n\n" + projectContent;
          await writeFile(projectClaudeMd, updatedContent, "utf-8");
          installManifest.pointers.push({ file: "CLAUDE.md", line: pointerLine });
        }

        results.push({
          component: "behavioral:claude-md",
          status: "installed",
          message: rig.behavioral["claude-md"].description,
        });
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        results.push({
          component: "behavioral:claude-md",
          status: "failed",
          message,
        });
      }
    }

    // Install AGENTS.md (same pattern)
    if (rig.behavioral["agents-md"]) {
      const sourcePath = join(rigDir, rig.behavioral["agents-md"].source);
      const destPath = join(rigInstallDir, "AGENTS.md");
      const destRelative = `.claude/rigs/${rig.name}/AGENTS.md`;

      try {
        const content = await readFile(sourcePath, "utf-8");
        await writeFile(destPath, content, "utf-8");
        installManifest.files.push(destRelative);

        // Add pointer to project AGENTS.md (create if missing)
        const projectAgentsMd = join(process.cwd(), "AGENTS.md");
        const pointerLine = `<!-- agent-rig:${rig.name} --> Also read: ${destRelative}`;
        
        let projectContent = "";
        if (existsSync(projectAgentsMd)) {
          projectContent = await readFile(projectAgentsMd, "utf-8");
        }

        if (!projectContent.includes(`<!-- agent-rig:${rig.name} -->`)) {
          const updatedContent = pointerLine + "\n\n" + projectContent;
          await writeFile(projectAgentsMd, updatedContent, "utf-8");
          installManifest.pointers.push({ file: "AGENTS.md", line: pointerLine });
        }

        results.push({
          component: "behavioral:agents-md",
          status: "installed",
          message: rig.behavioral["agents-md"].description,
        });
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        results.push({
          component: "behavioral:agents-md",
          status: "failed",
          message,
        });
      }
    }

    // Write install manifest
    const manifestPath = join(rigInstallDir, "install-manifest.json");
    await writeFile(manifestPath, JSON.stringify(installManifest, null, 2), "utf-8");

    return results;
  }
```

**Error handling:** Graceful degradation — if behavioral install fails, infrastructure still succeeds.

---

### Part 7: Wire Up Install Command

**Goal:** Call `adapter.installBehavioral()` during install flow

**File:** `/root/projects/agent-rig/src/commands/install.ts`

**Changes:**

1. **Update installCommand signature to pass rigDir:**

The `dir` variable (line 127) already holds the rig directory after cloning. Pass it to behavioral install.

2. **Add behavioral install phase (after conflict disable, before tools):**

Insert at line ~188 (after conflictResults, before toolResults):

```typescript
  // Install behavioral config (CLAUDE.md, AGENTS.md pointers)
  if (rig.behavioral) {
    console.log(chalk.bold("\n--- Behavioral Configuration ---"));
    for (const adapter of activeAdapters) {
      const behavioralResults = await adapter.installBehavioral(rig, dir);
      printResults(`${adapter.name} Behavioral`, behavioralResults);
    }
  }
```

3. **Update dry-run output** (line 166, in printInstallPlan):

```typescript
  const behavioralCount = rig.behavioral
    ? Object.keys(rig.behavioral).filter(k => rig.behavioral![k as keyof typeof rig.behavioral]).length
    : 0;
  if (behavioralCount > 0) {
    console.log(`  ${chalk.blue("Configure")} behavioral config (${behavioralCount} files)`);
    if (rig.behavioral?.["claude-md"]) {
      console.log(chalk.dim(`    CLAUDE.md ← ${rig.behavioral["claude-md"].source}`));
    }
    if (rig.behavioral?.["agents-md"]) {
      console.log(chalk.dim(`    AGENTS.md ← ${rig.behavioral["agents-md"].source}`));
    }
  }
```

---

### Part 8: Add CodexAdapter Stub

**Goal:** Codex doesn't use CLAUDE.md, so return empty results

**File:** `/root/projects/agent-rig/src/adapters/codex.ts`

**Add method:**

```typescript
  async installBehavioral(rig: AgentRig, rigDir: string): Promise<InstallResult[]> {
    // Codex uses .codex/AGENTS.md, not .claude/rigs/ — skip for now
    return [];
  }
```

**Rationale:** v1 focuses on Claude Code. Codex behavioral layer is a separate design question.

---

### Part 9: Add Tests

**Goal:** Validate schema accepts behavioral field

**File:** `/root/projects/agent-rig/src/schema.test.ts`

**Add test (after existing tests):**

```typescript
  it("validates behavioral configuration", () => {
    const manifest = {
      name: "test-rig",
      version: "1.0.0",
      description: "Test rig with behavioral config",
      author: "testuser",
      behavioral: {
        "claude-md": {
          source: "config/CLAUDE.md",
          description: "Engineering conventions",
        },
        "agents-md": {
          source: "AGENTS.md",
          description: "Agent definitions",
        },
      },
    };
    const result = AgentRigSchema.safeParse(manifest);
    assert.ok(
      result.success,
      `Validation failed: ${JSON.stringify(result.error?.issues)}`,
    );
  });

  it("validates behavioral with dependedOnBy", () => {
    const manifest = {
      name: "test-rig",
      version: "1.0.0",
      description: "Test rig",
      author: "testuser",
      behavioral: {
        "claude-md": {
          source: "config/CLAUDE.md",
          dependedOnBy: ["hooks.PreToolUse", "commands/commit"],
        },
      },
    };
    const result = AgentRigSchema.safeParse(manifest);
    assert.ok(result.success);
  });
```

---

### Part 10: Update Examples

**Goal:** Add behavioral field to examples/clavain/agent-rig.json

**File:** `/root/projects/agent-rig/examples/clavain/agent-rig.json`

**Add after environment section:**

```json
  "behavioral": {
    "claude-md": {
      "source": "config/CLAUDE.md",
      "description": "Engineering discipline conventions"
    },
    "agents-md": {
      "source": "AGENTS.md",
      "description": "Clavain agent definitions and workflows"
    }
  },
```

**Note:** This is the EXAMPLE manifest. The real one is `/root/projects/Clavain/agent-rig.json`.

---

## Verification Strategy

### Phase 1: Schema Validation (agent-rig)

```bash
cd /root/projects/agent-rig
pnpm test                                    # Run all tests including new behavioral tests
pnpm build                                    # Verify TypeScript compiles
node dist/index.js validate examples/clavain # Validate example manifest
```

**Expected:** All tests pass, example manifest validates.

### Phase 2: Clavain Config Creation

```bash
cd /root/projects/Clavain
# After creating config/CLAUDE.md:
wc -l config/CLAUDE.md                       # Should be ~80-100 lines
grep -c "^##" config/CLAUDE.md               # Should have 6-8 sections

# Verify agent-rig.json validates:
cd /root/projects/agent-rig
node dist/index.js validate /root/projects/Clavain
```

**Expected:** Manifest with behavioral field validates successfully.

### Phase 3: SessionStart Hook Update

```bash
cd /root/projects/Clavain
bash -n hooks/session-start.sh              # Syntax check
bash hooks/session-start.sh | jq .          # Verify JSON output
```

**Expected:** Valid JSON with behavioral summary in additionalContext.

### Phase 4: Local Install Test

```bash
cd /tmp/test-project
git init
/root/projects/agent-rig/dist/index.js install /root/projects/Clavain --yes
```

**Verify created files:**
```bash
ls -la .claude/rigs/clavain/
cat .claude/rigs/clavain/install-manifest.json
head -3 CLAUDE.md                            # Should have pointer line
head -3 AGENTS.md                            # Should have pointer line
```

**Expected structure:**
```
.claude/
  rigs/
    clavain/
      CLAUDE.md              ← copied from Clavain/config/CLAUDE.md
      AGENTS.md              ← copied from Clavain/AGENTS.md
      install-manifest.json  ← tracks install
CLAUDE.md                    ← pointer line added at top
AGENTS.md                    ← pointer line added at top
```

**Verify pointer lines:**
```bash
head -1 CLAUDE.md
# Should output: <!-- agent-rig:clavain --> Also read and follow: .claude/rigs/clavain/CLAUDE.md

head -1 AGENTS.md  
# Should output: <!-- agent-rig:clavain --> Also read: .claude/rigs/clavain/AGENTS.md
```

### Phase 5: Claude Code Session Test

```bash
cd /tmp/test-project
claude
```

**In session, check:**
1. System context includes pointer file content (both user's and rig's CLAUDE.md)
2. SessionStart hook output includes behavioral summary
3. Agent follows conventions (use Read before Edit, settings hygiene, etc.)

**Test pointer resolution:**
```
User: "What are the behavioral conventions for this project?"
Expected: Agent reads both CLAUDE.md (with pointer) and .claude/rigs/clavain/CLAUDE.md
```

### Phase 6: Multi-Rig Test

Install two rigs to verify pointer stacking:

```bash
cd /tmp/test-multi
git init
agent-rig install mistakeknot/Clavain --yes
agent-rig install someorg/other-rig --yes  # hypothetical

head -5 CLAUDE.md
# Should show both pointer lines:
# <!-- agent-rig:clavain --> Also read and follow: .claude/rigs/clavain/CLAUDE.md
# <!-- agent-rig:other-rig --> Also read and follow: .claude/rigs/other-rig/CLAUDE.md
```

---

## Edge Cases & Error Handling

### Scenario 1: CLAUDE.md doesn't exist

**Behavior:** Create it with just the pointer line

```typescript
if (!existsSync(projectClaudeMd)) {
  await writeFile(projectClaudeMd, pointerLine + "\n", "utf-8");
}
```

### Scenario 2: Pointer line already exists

**Behavior:** Skip adding duplicate (already handled via `includes` check)

### Scenario 3: Source file missing in rig

**Behavior:** Log failure, continue with other behavioral installs

**Implementation:** Try/catch around readFile with failure result

### Scenario 4: .claude/rigs/ directory doesn't exist

**Behavior:** Create it with `mkdir recursive: true` (already in implementation)

### Scenario 5: Install manifest write fails

**Behavior:** Behavioral files installed but not tracked — degrades gracefully

**Risk:** Uninstall won't work cleanly. Accept for v1, improve in v1.1.

### Scenario 6: Rig has no behavioral field

**Behavior:** Skip behavioral install phase entirely (already handled via `if (!rig.behavioral)`)

---

## File-by-File Change Summary

### Clavain Repository

| File | Change | Lines | Complexity |
|------|--------|-------|------------|
| `config/CLAUDE.md` | **NEW** — Generalized conventions doc | ~100 | Low |
| `hooks/session-start.sh` | Add behavioral summary injection | ~5 | Trivial |
| `agent-rig.json` | Add `behavioral` field | ~8 | Trivial |

**Total:** 1 new file, 2 edits, ~113 lines

### agent-rig Repository

| File | Change | Lines | Complexity |
|------|--------|-------|------------|
| `src/schema.ts` | Add Behavioral schema types | ~25 | Low |
| `src/adapters/types.ts` | Add `installBehavioral()` method | ~1 | Trivial |
| `src/adapters/claude-code.ts` | Implement behavioral install | ~110 | Medium |
| `src/adapters/codex.ts` | Add stub method | ~4 | Trivial |
| `src/commands/install.ts` | Wire up behavioral phase + dry-run | ~15 | Low |
| `src/schema.test.ts` | Add behavioral validation tests | ~35 | Low |
| `examples/clavain/agent-rig.json` | Add behavioral field | ~8 | Trivial |

**Total:** 0 new files, 7 edits, ~198 lines

**Combined:** 1 new file, 9 edits, ~311 lines of changes

---

## Dependencies & Sequencing

### Critical Path

```
1. agent-rig schema changes → validates behavioral field
2. Clavain config/CLAUDE.md creation → content to install
3. Clavain agent-rig.json update → points to config/CLAUDE.md
4. agent-rig adapter implementation → installs files
5. agent-rig install command wiring → executes install
6. Clavain SessionStart hook update → injects summary
```

### Parallel Work

Can be done independently:
- Clavain config/CLAUDE.md content writing
- agent-rig schema + test changes
- agent-rig adapter implementation (once schema done)

### Testing Sequence

```
1. Unit tests (schema validation)
2. Build verification (TypeScript compiles)
3. Manifest validation (examples/clavain validates)
4. Local install test (file creation)
5. Session integration test (pointer resolution)
```

---

## Rollout Plan

### Stage 1: Merge to Main (Both Repos)

1. **agent-rig:** Schema + adapter + tests
2. **Clavain:** config/CLAUDE.md + agent-rig.json + hook update

**Verification:** Local install test passes

### Stage 2: Publish agent-rig

```bash
cd /root/projects/agent-rig
npm version patch
npm publish
```

### Stage 3: Publish Clavain

```bash
cd /root/projects/Clavain
bash scripts/bump-version.sh 0.4.17
# Pushes to git, updates interagency-marketplace
```

### Stage 4: Dogfood

Install Clavain via agent-rig in a fresh project, use for 1-2 days, verify behavioral conventions apply.

### Stage 5: Announce

Document in README and AGENTS.md:
- What behavioral layer does
- How pointer-based inclusion works
- How to inspect before installing

---

## Future Enhancements (v1.1+)

From brainstorm doc, deferred to future versions:

| Version | Feature | Complexity |
|---------|---------|------------|
| v1.1 | Namespaced commands/skills/workflows | Low |
| v1.2 | Load order control (`agent-rig reorder`) | Low |
| v1.3 | Settings deep merge with tracking | Medium |
| v1.4 | Hook scripts + registration | Medium |
| v1.5 | Uninstall reverses all changes | Medium |
| v2.0 | Profiles, variants, compat patches | High |

**Trigger for v1.1:** User feedback that commands/skills are more important than CLAUDE.md

**Trigger for v1.3:** Settings conflicts between rigs become common

**Trigger for v2.0:** Multi-rig adoption reaches critical mass

---

## Risks & Mitigations

### Risk 1: Pointer line gets accidentally deleted

**Impact:** Rig conventions no longer loaded

**Mitigation:** 
- Install manifest tracks pointer line
- `agent-rig verify` command (future) checks integrity
- Comment format makes it obvious it's managed

### Risk 2: User edits .claude/rigs/{name}/CLAUDE.md

**Impact:** Changes lost on reinstall

**Mitigation:**
- Add warning comment at top of installed file:
  ```markdown
  <!-- INSTALLED BY AGENT-RIG - DO NOT EDIT -->
  <!-- Edit in source repo and reinstall to update -->
  ```

### Risk 3: Agent ignores pointer line

**Impact:** Behavioral conventions not followed

**Likelihood:** Very low — agents reliably follow "also read" instructions

**Mitigation:** SessionStart hook injection provides fallback reminder

### Risk 4: Two rigs with conflicting conventions

**Impact:** Agent gets contradictory instructions

**Mitigation:**
- Root file has final authority (user can override)
- Future: `conflicts` field for rigs (like plugins)
- Future: `agent-rig reorder` to control precedence

### Risk 5: Install manifest not written

**Impact:** Uninstall can't clean up

**Mitigation:** Accept for v1, improve in v1.5 (uninstall command)

---

## Open Questions (For Review)

1. **Pointer line position:** Top of file vs bottom? → **Top** (higher precedence, visible)
2. **Comment format:** `<!-- agent-rig:name -->` vs `[agent-rig:name]`? → **HTML comment** (markdown-invisible)
3. **AGENTS.md optional or required?** → **Optional** (some rigs don't ship agents)
4. **dependedOnBy enforcement:** Warning only or block install? → **Warning only** (v1)
5. **Multi-rig reconciliation:** Should agent-rig detect conflicts? → **No** (v1), agent handles it

---

## Success Metrics

### Technical

- Schema validates behavioral field ✓
- Install creates `.claude/rigs/{name}/` structure ✓
- Pointer lines added to root files ✓
- Install manifest tracks everything ✓
- No breaking changes to existing installs ✓

### User Experience

- `agent-rig install` shows behavioral config in dry-run
- Installed conventions visible in Claude Code session
- Agent follows behavioral conventions without explicit reminders
- Clean separation: user's CLAUDE.md vs rig's conventions

### Adoption

- Clavain ships with generalized conventions
- Other rig authors add behavioral fields
- Users report behavioral layer adds value

---

## Critical Files for Implementation

See final section of this document.

---

## Appendix A: Extracted Conventions from User's CLAUDE.md

**Sections to generalize:**

1. **Tool Usage Preferences** (lines 26-29)
   - Prefer Read/Edit/Grep over Bash
   - Always Read before Edit
   - (Remove: uv run for Python — project-specific)

2. **Settings Hygiene** (lines 82-94)
   - Never use heredocs in Bash
   - Never use multi-line loops
   - Never inline long prompts
   - Keep commands short/wildcard-friendly
   - (All generalizable — core discipline)

3. **Git Workflow** (lines 21-24)
   - Trunk-based development
   - Commit to main
   - No feature branches unless asked
   - (Fully generalizable)

4. **Continuous Learning** (lines 49-66)
   - Record immediately when discovering bugs, gotchas, corrections
   - What to record: lesson + context + why
   - Where: MEMORY.md for quick facts, topic files for details
   - (Fully generalizable)

5. **Workflow Patterns** (lines 96-100)
   - Preserve Original Intent after simplification
   - Trigger-to-feature mappings
   - (Fully generalizable)

6. **Documentation Standards** (lines 15-19)
   - Every project needs CLAUDE.md + AGENTS.md
   - CLAUDE.md short, AGENTS.md comprehensive
   - (Fully generalizable)

**Sections to exclude:**

- Oracle setup (lines 31-47) — server-specific
- Plugin development (lines 72-80) — Clavain meta-workflow
- Persistent task tracking (lines 68-70) — personal preference

---

## Appendix B: SessionStart Hook Injection Strategy

**Current injection (~2000 tokens):**
- Full `using-clavain/SKILL.md` content (~1800 tokens)
- Companion detection (~100 tokens)
- Upstream staleness warning (~100 tokens)

**Adding behavioral summary (~120 tokens):**
- 5-6 bullet points
- High-value reminders only
- Full rules in config/CLAUDE.md (via pointer)

**Total: ~2120 tokens** — still reasonable for session start

**Rationale:** Hook provides immediate context, pointer provides deep reference. Agent can ignore hook summary if already following conventions, but always has full docs via pointer.

---

## Appendix C: Install Manifest Schema

```typescript
interface InstallManifest {
  rig: string;              // Rig name
  version: string;          // Rig version at install time
  installedAt: string;      // ISO timestamp
  files: string[];          // Relative paths created
  pointers: Array<{         // Pointer lines added
    file: string;           // Target file (CLAUDE.md, AGENTS.md)
    line: string;           // Exact line added
  }>;
}
```

**Location:** `.claude/rigs/{name}/install-manifest.json`

**Used by:** Future `agent-rig uninstall` command

---

## Appendix D: Dry-Run Output (Example)

```
Agent Rig Installer

Installing clavain v0.4.16 — General-purpose engineering discipline rig

  Detected: claude-code

Install Plan:
  Install 9 plugins
  Disable 8 conflicting plugins
  Configure 3 MCP servers
  Configure behavioral config (2 files)
    CLAUDE.md ← config/CLAUDE.md
    AGENTS.md ← AGENTS.md
  Skip 4 optional tools (check commands)
  Platforms: claude-code

Proceed with installation? [y/N]
```

**After install:**

```
--- claude-code ---

Marketplaces
  OK  marketplace:interagency-marketplace

Plugins
  OK  plugin:clavain@interagency-marketplace — The core Clavain plugin
  OK  plugin:context7@claude-plugins-official — Runtime doc fetching via MCP
  ...

Conflicts Disabled
  OFF  conflict:code-review@claude-plugins-official — Duplicates Clavain review agents
  ...

--- Behavioral Configuration ---

claude-code Behavioral
  OK  behavioral:claude-md — Engineering discipline conventions
  OK  behavioral:agents-md — Clavain agent definitions and workflows

--- Verification ---

claude-code Health
  OK  mcp:mcp-agent-mail — healthy

clavain v0.4.16 installed successfully.

Restart your Claude Code session to activate all changes.
```

