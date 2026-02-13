### Findings Index
- P0 | P0-1 | "Design Section: Step 1.0b" | Circular dependency creates fragile initialization sequence
- P0 | P0-2 | "Design Section: Step 1.0b" | Silent failure modes violate Flux-Drive's fail-loud contract
- P0 | P0-3 | "Design Section: Cache Format" | Structural hash collision risk from content concatenation
- P1 | P1-1 | "Design Section: Step 1.0b" | Orphan detection couples agent content to lifecycle decisions
- P1 | P1-2 | "Design Section: Step 1.0b" | Domain shift logic duplicates triage pre-filter
- P1 | P1-3 | "Design Section: Staleness Detection" | Git dependency is project-wide assumption with no fallback path
- P1 | P1-4 | "Design Section: Agent Lifecycle" | Implicit phase sequencing creates race conditions
- IMP | IMP-1 | "Design Section: Step 1.0b" | Extract staleness logic into separate script
- IMP | IMP-2 | "Design Section: Cache Format" | Add version field for cache format evolution
- IMP | IMP-3 | "Design Section: Performance Budget" | Define resource limits for detect-domains.py
- IMP | IMP-4 | "Alternatives Section" | Document why structural signals chosen over semantic analysis
Verdict: needs-changes

### Summary

The integration plan introduces a circular dependency between domain detection and agent generation that creates a fragile initialization sequence where Step 1.0b must handle three distinct responsibilities (staleness, comparison, generation) in one phase. The staleness detection design has silent failure modes that conflict with Flux-Drive's existing fail-loud conventions, and the structural hash implementation has collision risks from naive content concatenation. Agent lifecycle management couples content parsing (reading flux-gen headers) to lifecycle decisions in a way that violates single-responsibility principles. Several edge cases lack defined behavior, and the git-based staleness check assumes project-wide git availability without a viable fallback.

### Issues Found

#### P0-1: Circular dependency creates fragile initialization sequence

**Location**: Design Section 1 (New Step 1.0b in flux-drive SKILL.md)

**Issue**: Step 1.0b creates a circular dependency between three concerns that should be separate:
1. Staleness detection (structural changes since last scan)
2. Domain comparison (old vs new domain lists)
3. Agent generation (creating missing agents)

The proposed flow is: check stale → re-detect → compare domains → check agents → generate. This tightly couples staleness to generation in a single step, making it impossible to:
- Re-detect domains without potentially regenerating agents
- Update agents without checking staleness
- Run generation manually after flux-drive has cached domains

**Evidence from codebase**:
- Current flux-drive SKILL.md (line 67-90) treats domain detection as a pure classification step with no side effects
- Current flux-gen command (lines 11-136) is designed as an explicit, user-initiated generation step
- The SessionStart hook shows Clavain uses dependency injection patterns where components discover dependencies at session start, not at runtime

**Why this is architectural**:
The circular dependency violates the separation of concerns between:
- **Detection** (pure classification, cacheable, idempotent)
- **Comparison** (pure function, no side effects)
- **Generation** (side-effecting, file creation, user consent required)

Mixing these in Step 1.0b means flux-drive can no longer be a pure document reviewer — it becomes a code generator with implicit side effects.

**Impact**:
- Breaks flux-drive's current contract as a read-only review tool
- Makes it impossible to run domain detection without triggering potential file creation
- Creates hidden dependencies between components that should be composable
- Violates the plugin's existing pattern of separating discovery (hooks) from execution (skills)

**Recommended fix**:
Split Step 1.0b into three sequential gates:
1. **Step 1.0b-detect**: Check staleness, re-detect if needed (pure, no generation)
2. **Step 1.0b-compare**: Compare old vs new domains (pure, no generation)
3. **Step 1.0b-offer**: IF domains exist AND no agents → offer to run flux-gen as a blocking subagent call

This makes the generation step explicit and preserves flux-drive's read-only nature unless the user consents.

#### P0-2: Silent failure modes violate Flux-Drive's fail-loud contract

**Location**: Design Section 1 (Step 1.0b substeps 1-2)

**Issue**: The design specifies silent fallbacks for multiple failure modes:
- detect-domains.py exit 2 (script error) → "skip, proceed without domain agents"
- Domain profile file doesn't exist → "skip that domain silently"
- detect-domains.py not available (path issue) → "Skip Step 1.0b entirely, log warning"

**Evidence from codebase**:
- flux-drive SKILL.md Phase 1 Step 1.0a (line 82-85) treats detection failures as explicit conditions with defined exit codes
- launch.md Step 2.1a (lines 67-68) specifies: "Fallback: If the domain profile file doesn't exist or can't be read, skip that domain silently. Do NOT block agent launch on domain profile failures."

This establishes a precedent for silent failures, but the integration plan extends it to **generation decisions** — a side-effecting operation, not a pure read.

**Why this is architectural**:
Silent failures for read operations (loading profiles) are acceptable — missing data means proceed with defaults. Silent failures for **write operations** (agent generation) violate architectural boundaries:
- User expects flux-drive to either review OR fail loudly
- Silent skipping of generation means users get inconsistent behavior (agents appear sometimes, not others)
- No audit trail for why agents weren't generated

**Impact**:
- Users will see "0 generated" in the flux-drive status line but won't know if it's because:
  - Agents already exist
  - Detection failed
  - Domain profiles are missing
  - Scripts aren't executable
- Debugging becomes opaque — "it just didn't generate" with no error
- Violates principle of least surprise

**Recommended fix**:
1. **Differentiate read vs write failures**: Silent skip for read (profile loading), explicit error for write (agent generation)
2. **Add a generation log**: When Step 1.0b skips generation, write reason to `{PROJECT_ROOT}/.claude/flux-drive-gen.log`
3. **Show summary in flux-drive output**: "Domain check: 1 domain detected, generation skipped (reason: script error)"

This preserves the fail-soft behavior for reads while making generation decisions auditable.

#### P0-3: Structural hash collision risk from content concatenation

**Location**: Design Section 4 (Cache format update)

**Issue**: The structural hash design specifies "concatenated contents of all STRUCTURAL_FILES that exist." This creates collision risks and implementation ambiguity:
- **Order dependency**: Is it `package.json + Cargo.toml` or sorted alphabetically? Plan doesn't specify.
- **Collision risk**: Two different projects with similar `package.json` and `Cargo.toml` could hash to the same value if order isn't deterministic.
- **Missing files handling**: Plan says "excludes missing files from hash" but doesn't define behavior when a file is deleted (is that a content change or a structural change?).

**Evidence from codebase**:
- detect-domains.py (lines 84-92) already has a `write_cache` function that writes deterministic YAML
- The script uses `dt.date.today().isoformat()` for timestamps (line 89), showing a pattern of deterministic serialization
- STRUCTURAL_FILES list includes wildcard patterns like `"*.gd"` (from domain index, line 39) but the hash design doesn't address how globs map to actual files

**Why this is architectural**:
Hash collisions in cache invalidation break the staleness contract:
- False negatives (hash matches when structure changed) → outdated agents used in reviews
- False positives (hash differs when structure unchanged) → unnecessary re-detection

Both violate the performance budget (Section 5: < 100ms for hash compare, < 10s for re-detection).

**Impact**:
- Structural changes may not trigger re-detection (user adds `go.mod`, hash collides with old state)
- Non-structural changes may trigger re-detection (user reformats `package.json`, hash changes)
- Edge cases like file deletions have undefined behavior

**Recommended fix**:
1. **Use deterministic serialization**: Hash a JSON object with sorted keys: `{"files": {"Cargo.toml": hash(content), "package.json": hash(content)}, "version": 1}`
2. **Per-file hashing**: Hash each file individually, combine with sorted concatenation
3. **Define deletion semantics**: File deletion → key removed from hash input → triggers re-detection
4. **Fallback to git**: If hash computation fails, fall back to git log method (already specified in Section 2)

This eliminates collision risk and makes behavior deterministic.

#### P1-1: Orphan detection couples agent content to lifecycle decisions

**Location**: Design Section 3 (Agent lifecycle management, Orphan detection)

**Issue**: The orphan detection algorithm requires reading agent file headers to extract domain names:
```
For each .claude/agents/fd-*.md:
  1. Read the file header: "Generated by /flux-gen from the {domain-name} domain profile"
  2. If {domain-name} is NOT in the current detected domains → Mark as orphaned
```

This couples **file content parsing** (reading headers) to **lifecycle decisions** (what to do with orphaned agents). Violations:
- flux-gen writes a specific header format that orphan detection depends on → tight coupling
- If a user edits the header, the agent is no longer recognized as flux-gen-generated → brittle
- If flux-gen changes the header format in the future, orphan detection breaks → fragile versioning

**Evidence from codebase**:
- flux-gen command (lines 69-107) defines the template with a header comment
- The header is user-editable ("Customize this file for your project's specific needs" — line 73)
- No version marker or structured frontmatter to indicate generation provenance

**Why this is architectural**:
Lifecycle management should use **structured metadata**, not brittle text parsing. The current design:
- Assumes header text never changes (user edits, template evolution)
- Has no fallback if header is missing or malformed
- Requires regex/string matching instead of structured data

This is an anti-pattern: coupling component behavior to unstructured text in another component's output.

**Impact**:
- Users who customize agent headers break orphan detection
- Future template changes require updating both flux-gen and flux-drive
- No way to distinguish "user-created fd-*.md" from "flux-gen-created fd-*.md" if header is removed

**Recommended fix**:
1. **Add YAML frontmatter to generated agents**:
   ```yaml
   ---
   generated_by: flux-gen
   domain: game-simulation
   version: 1
   customized: false
   ---
   ```
2. **Orphan detection reads frontmatter**, not header text
3. **On first user edit**, set `customized: true` → orphan detection skips it (user ownership)
4. **flux-gen checks frontmatter** before overwriting (respect `customized: true`)

This decouples content from lifecycle and supports user customization.

#### P1-2: Domain shift logic duplicates triage pre-filter

**Location**: Design Section 1 (Step 1.0b substep 3c)

**Issue**: Step 1.0b substep 3c specifies:
```
c. If agents exist BUT domains changed:
   - Identify orphaned agents (domain removed)
   - Identify missing agents (new domain added)
   - Generate only new agents (don't touch existing)
```

This logic **duplicates** the triage pre-filter in Step 1.2a (SKILL.md lines 153-177), which already filters agents by domain signals:
- Step 1.2a filters fd-game-design unless `game-simulation` domain is detected
- Step 1.0b substep 3c filters agents by domain for generation decisions

**Evidence from codebase**:
- SKILL.md Step 1.2a (lines 163-166): "Game filter: Skip fd-game-design unless Step 1.0a detected `game-simulation` domain OR the document/project mentions game..."
- Domain profiles (game-simulation.md lines 16-67) define injection criteria per agent — this is already a filtering mechanism

**Why this is architectural**:
The triage filter and the generation filter are **the same concern** — "which agents are relevant for this domain?" Implementing it in two places creates:
- **Duplication risk**: If triage filter logic changes, generation filter must also change
- **Drift risk**: The two filters can diverge, leading to inconsistent behavior (agent generated but never used)
- **Maintenance burden**: Two places to update when adding new domains

**Impact**:
- Adding a new domain requires updating both Step 1.0b and Step 1.2a
- Filters can drift (one updated, other forgotten) → orphaned agents or missing agents
- No single source of truth for "which agents apply to which domains"

**Recommended fix**:
1. **Extract domain-to-agent mapping** into a separate config file:
   ```yaml
   # config/flux-drive/domain-agent-map.yaml
   game-simulation:
     required: [fd-architecture, fd-correctness, fd-quality]
     recommended: [fd-game-design, fd-performance]
     generated: [fd-simulation-kernel, fd-game-systems]
   ```
2. **Both triage and generation read from the same map**
3. **Step 1.2a pre-filter**: reads `required + recommended` from map
4. **Step 1.0b generation**: reads `generated` from map

This eliminates duplication and creates a single source of truth.

#### P1-3: Git dependency is project-wide assumption with no fallback path

**Location**: Design Section 2 (detect-domains.py: Add `--check-stale` flag)

**Issue**: The staleness detection relies on git:
- Section 2: "Uses git to find changes since `detected_at` in the cache"
- Section 9 Edge Cases: "No .git directory → Always re-detect (no staleness check possible)"
- Performance budget: "git log --since=... --diff-filter=ACDR" (Section 2)

This assumes:
1. The project is a git repository
2. Git history is available and reliable
3. The user hasn't rebased/squashed since last detection

**Evidence from codebase**:
- detect-domains.py (line 367-369) checks `project.is_dir()` but does NOT check for `.git`
- Domain detection index.yaml (lines 1-454) defines signals based on **files and directories**, not git history
- flux-drive SKILL.md Step 1.0 (line 31) derives `PROJECT_ROOT` as "nearest ancestor directory containing .git, OR INPUT_DIR" — git is optional

This shows flux-drive already supports non-git projects (fallback to INPUT_DIR), but the staleness detection plan has no equivalent fallback.

**Why this is architectural**:
Assuming git project-wide creates a **platform dependency** that violates the domain detection's design as a filesystem-based classifier. The plan's only fallback is "always re-detect" which:
- Violates the performance budget (re-detection should be rare, not on every run)
- Penalizes non-git projects with 10s overhead on every flux-drive invocation
- Has no middle ground (could use mtime-based staleness instead)

**Impact**:
- Non-git projects (prototypes, downloaded zips, CI environments with shallow clones) pay 10s re-detection cost every time
- Users in git repos with complex histories (large monorepos, frequent rebases) get unreliable staleness checks
- No incremental improvement path (can't add mtime fallback without redesigning)

**Recommended fix**:
1. **Three-tier staleness strategy**:
   - **Tier 1 (structural hash)**: Already in plan (Section 4), fast but coarse
   - **Tier 2 (git log)**: Current plan, medium speed, fine-grained
   - **Tier 3 (mtime fallback)**: If no git, check mtime of STRUCTURAL_FILES vs `detected_at`
2. **Fallback ladder**: Try hash → git → mtime → always-stale
3. **Document assumptions**: "Git provides best staleness accuracy, mtime is conservative fallback"

This removes git as a hard dependency while preserving fast-path optimization.

#### P1-4: Implicit phase sequencing creates race conditions

**Location**: Design Section 1 (Step 1.0b positioning in flux-drive)

**Issue**: The plan specifies Step 1.0b as "Insert between Step 1.0a (domain classification) and Step 1.1 (document analysis)". This creates an implicit sequencing requirement:
- Step 1.0a must complete before 1.0b (needs domain list)
- Step 1.0b must complete before 1.2 (triage needs generated agents)
- Step 1.1 is independent (document analysis doesn't need agents)

But the plan doesn't address:
- What happens if Step 1.0b generates agents **after** Step 1.2 has already read the agent roster?
- How does the triage table (Step 1.2) discover newly-generated agents?

**Evidence from codebase**:
- SKILL.md lines 382-389 define the Agent Roster section, which reads `.claude/agents/fd-*.md` files
- The roster is read **once** during Phase 1 (no refresh mechanism)
- launch.md (lines 159-173) shows agents are dispatched based on the roster from Step 1.2

**Why this is architectural**:
The implicit dependency graph is:
```
1.0a (detect) → 1.0b (generate) → 1.1 (analyze) → 1.2 (triage roster) → 2.x (launch)
```

But if Step 1.0b writes files **during** Phase 1, and Step 1.2 reads files **during** Phase 1, there's a race:
- Optimistic case: 1.0b completes before 1.2 reads roster → agents appear
- Pessimistic case: 1.2 reads roster before 1.0b writes files → agents missing

The plan doesn't specify whether the roster read is before or after generation.

**Impact**:
- Newly-generated agents may not appear in the triage table
- User sees "Domain check: 2 agents generated" but triage table shows 0 Project Agents
- Requires restart to pick up generated agents (breaks single-session workflow)

**Recommended fix**:
1. **Explicit sequencing in SKILL.md**: "Step 1.0b runs before the Agent Roster section (Step 1.2a)"
2. **Add a roster refresh after 1.0b**: If agents were generated, re-read `.claude/agents/` before triage
3. **Or: Move generation before Phase 1 entirely** (SessionStart hook generates agents based on cached domains)

Option 3 is cleanest but requires moving generation out of flux-drive.

### Improvements Suggested

#### IMP-1: Extract staleness logic into separate script

**Rationale**: The staleness detection logic in Section 2 is complex enough to warrant its own script, similar to how domain detection is a separate `detect-domains.py`.

**Suggestion**: Create `scripts/check-domain-staleness.py`:
- Takes PROJECT_ROOT and cache path as arguments
- Exits with codes: 0 (fresh), 1 (stale), 2 (error)
- Encapsulates structural hash computation, git log parsing, mtime fallback
- Can be tested independently (unit tests for hash computation, git log parsing)

**Benefits**:
- flux-drive SKILL.md Step 1.0b becomes a thin wrapper (call script, handle exit codes)
- Staleness logic can evolve without editing SKILL.md
- Easier to test edge cases (hash collisions, git errors, missing files)

#### IMP-2: Add version field for cache format evolution

**Rationale**: The cache format update in Section 4 adds `structural_hash` but doesn't define how to handle cache format changes in the future.

**Suggestion**: Add a `cache_version` field:
```yaml
cache_version: 1
domains: [...]
detected_at: '2026-02-12'
structural_hash: 'a1b2c3d4'
```

When detect-domains.py reads the cache:
- If `cache_version` is missing or < current → treat as stale (force re-detect)
- If `cache_version` > current → error (cache from future version)

**Benefits**:
- Enables schema evolution (can add fields without breaking old caches)
- Prevents silent corruption from cache format mismatch
- Standard practice for versioned file formats

#### IMP-3: Define resource limits for detect-domains.py

**Rationale**: Section 5 (Performance budget) specifies time budgets (<100ms for hash, <500ms for git, <10s for detection) but not resource limits.

**Suggestion**: Add resource constraints to the design:
- **File scan depth**: Max 2 levels (already implicit in gather_files, line 121-136)
- **Keyword scan limit**: Max 5 files (already in gather_keywords, line 258)
- **Max domains detected**: Cap at 5 (prevents pathological cases where every domain matches)

Document these in the script's docstring and test them explicitly (unit test with a project that matches all 11 domains).

**Benefits**:
- Prevents runaway resource usage on large codebases
- Makes performance characteristics predictable
- Easier to reason about worst-case behavior

#### IMP-4: Document why structural signals chosen over semantic analysis

**Rationale**: The Alternatives section (Section 8) doesn't explain why structural file/directory signals were chosen over semantic analysis (e.g., LLM-based classification or keyword density scoring).

**Suggestion**: Add to Section 8:
> ### E: Semantic/LLM-based domain detection
> Rejected. Would be more accurate but violates the <10s performance budget. Structural signals (files, frameworks, directories) are deterministic and cache-friendly. If structural signals are insufficient, users can manually set `override: true` in the cache.

**Benefits**:
- Documents the trade-off (speed vs accuracy)
- Explains why the current approach is "good enough"
- Sets expectations for when users should override

### Overall Assessment

The integration plan tackles a real usability problem (manual flux-gen invocation) but introduces architectural complexity that conflicts with Flux-Drive's existing separation of concerns. The circular dependency between detection and generation, silent failure modes for side-effecting operations, and implicit phase sequencing create fragile coupling. The staleness detection design is sound in principle but has collision risks and assumes git availability. Most critical: mixing read-only analysis (flux-drive) with file generation (flux-gen) in a single step violates the single-responsibility principle and makes the system harder to reason about. Recommend splitting Step 1.0b into explicit gates (detect, compare, offer-to-generate) and extracting lifecycle logic into structured metadata.
<\!-- flux-drive:complete -->
