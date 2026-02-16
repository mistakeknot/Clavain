# Token-Efficient Skill Loading Plan — Quality Review

**Date:** 2026-02-15
**Plan:** `/root/projects/Interverse/docs/plans/2026-02-15-token-efficient-skill-loading.md`
**Reviewer:** Flux-drive Quality & Style
**Scope:** Clavain/inter-* plugin ecosystem (Go, Python, Shell)

---

## Executive Summary

**Verdict:** APPROVE with P1 findings for naming and test patterns.

The plan demonstrates solid judgment in choosing LLM summarization over fragile mechanical extraction, and correctly delegates deterministic computation (signal evaluation) to shell pre-computation. Core architecture is sound. Four P1 findings require resolution before execution: naming convention mismatches, bats test pattern gaps, shell script complexity trade-offs, and freshness check mechanism design.

**Key Strengths:**
- Pre-computation strategy (interwatch-scan.sh) correctly moves signal evaluation out of LLM context
- LLM summarization for compact files is the right trade-off vs mechanical extraction
- Hash-based manifest for freshness tracking is proven pattern (mirrors gen-catalog.py)

**Key Risks:**
- Naming convention drift (SKILL-compact.md vs established patterns)
- Shell YAML parsing anti-pattern (Task 1 needs Python or dedicated tool)
- Freshness test pattern incomplete (needs concrete bats implementation)

---

## P0 Findings (Blocking)

None.

---

## P1 Findings (Must Fix Before Ship)

### P1-1: Naming Convention Inconsistency

**Finding:** The plan proposes `SKILL-compact.md`, `.compact-manifest`, and `gen-compact.sh` with the word "compact" throughout. The ecosystem uses **dash-case** for multi-word file components, not bare English words as modifiers.

**Evidence:**
- Existing patterns: `lib-signals.sh`, `lib-gates.sh`, `lib-discovery.sh`, `auto-compound.sh`, `auto-drift-check.sh`, `test_lib_sprint.bats`
- The word "compact" is a descriptive English word, not a namespace or subsystem prefix
- `.compact-manifest` creates a hidden file with no namespace (collision risk)

**Impact:** Violates established naming conventions. Future readers will see `gen-compact.sh` and wonder if "compact" is a subsystem/feature name or a descriptive adjective.

**Recommendation:**
1. **File naming:**
   - `SKILL-compact.md` → **`SKILL.compact.md`** (sub-extension pattern, like `.test.js` or `.spec.ts`)
   - `gen-compact.sh` → **`gen-skill-compact.sh`** (explicit scope in name)
   - `.compact-manifest` → **`.skill-compact-manifest.json`** (namespaced, explicit format)

2. **Rationale:**
   - Sub-extension (`.compact.md`) is a well-known pattern in JS/TS ecosystems for variant files
   - Namespaced manifest (`.skill-compact-manifest.json`) prevents collision with future features
   - Full script name (`gen-skill-compact.sh`) documents what it generates without requiring context

**Alternative:** If sub-extension feels foreign to markdown, use `SKILL-compact.md` but rename manifest and script:
   - `.compact-manifest` → `.skill-compact.manifest` (still namespaced)
   - `gen-compact.sh` → `gen-skill-compact.sh` (explicit scope)

---

### P1-2: Shell YAML Parsing Anti-Pattern

**Finding:** Task 1 specifies "shell script that reads `config/watchables.yaml`" and does YAML parsing in bash. This is an established anti-pattern in the ecosystem.

**Evidence:**
- The ecosystem has **zero** shell scripts doing YAML parsing with bash
- `config/default.yaml` (interject) and `config/flux-drive/domains/index.yaml` (interflux) are both consumed by Python code, not shell
- Python has native YAML support via `pyyaml` or `ruamel.yaml`
- Shell YAML parsing requires `yq` (external dependency) or fragile `sed`/`awk` hacks

**Impact:**
- Fragile: YAML syntax edge cases (multiline strings, nested lists, anchors/aliases) break naive shell parsing
- Maintenance burden: future YAML schema changes require updating shell parsing logic
- Inconsistent with ecosystem: Python is the established tool for structured config parsing

**Recommendation:**
1. **Write `scripts/interwatch-scan.py` instead of `interwatch-scan.sh`**
   - Read YAML with `pyyaml` or `ruamel.yaml`
   - Call shell commands (`bd list`, `git diff`, etc.) via `subprocess.run()`
   - Output JSON to stdout (same contract as plan)

2. **Rationale:**
   - `gen-catalog.py` is the established precedent — Python script reading structured metadata and emitting JSON
   - Python is already a dependency (interject, interflux MCP servers, test suites)
   - Better error messages (YAML parse errors with line numbers)

3. **Keep shell for simple tasks:**
   - If watchables config is trivial (single file, flat list), a bash script with hardcoded paths is acceptable
   - Move to Python when YAML complexity grows

**Alternative:** Use `yq` (pre-installed or document as dependency) and accept the trade-off. This is viable if the YAML structure is guaranteed simple and shell invocation overhead matters.

---

### P1-3: Freshness Test Pattern Incomplete

**Finding:** Task 7 describes freshness tests ("verify source file hashes match manifest") but provides no concrete bats test example or reference to existing hash-checking patterns.

**Evidence:**
- No existing bats tests check file hashes against manifests
- `gen-catalog.py` has `--check` mode but no bats test coverage for drift detection
- The plan references "test validates freshness" but doesn't specify the assertion pattern

**Impact:**
- Ambiguous implementation contract: does `gen-compact.sh --check` exit 1 on drift, or output JSON?
- Risk of incomplete test: without a reference pattern, the test might check file existence but not hash correctness

**Recommendation:**
1. **Specify the bats test pattern explicitly in Task 7:**
   ```bash
   @test "compact freshness: SKILL-compact.md is fresh for doc-watch" {
       run bash scripts/gen-skill-compact.sh --check skills/doc-watch
       assert_success  # exits 0 if fresh, 1 if drift
   }

   @test "compact freshness: manifest detects source file change" {
       local tmpdir
       tmpdir=$(mktemp -d)
       cp -r skills/doc-watch "$tmpdir/"
       bash scripts/gen-skill-compact.sh "$tmpdir/doc-watch"  # generate fresh manifest
       echo "# drift" >> "$tmpdir/doc-watch/phases/detect.md"
       run bash scripts/gen-skill-compact.sh --check "$tmpdir/doc-watch"
       assert_failure  # exits 1 on detected drift
       rm -rf "$tmpdir"
   }
   ```

2. **Define `--check` behavior in Task 5:**
   - `gen-skill-compact.sh <skill-dir>` → regenerates compact file, updates manifest
   - `gen-skill-compact.sh --check <skill-dir>` → exits 0 if fresh, 1 if drift, 2 on error
   - Mirror `gen-catalog.py --check` pattern for consistency

3. **Document hash algorithm:**
   - Use `sha256sum` or `md5sum` (sha256 preferred for future-proofing)
   - Store in manifest as `{"file": "phases/detect.md", "hash": "sha256:abc123..."}`

---

### P1-4: LLM Summarization Quality Variance

**Finding:** The plan delegates compact file generation to LLM summarization (Task 5) but provides no quality gate or validation mechanism beyond manual review.

**Evidence:**
- Prompt template is generic: "Keep: algorithm steps, decision points, output contracts. Remove: examples, rationale, verbose descriptions."
- No correctness check: what if the LLM drops a critical decision point or misinterprets an algorithm step?
- No regeneration trigger: if source files change, who reviews the regenerated compact file?

**Impact:**
- Risk: compact file omits a critical step (e.g., flux-drive scoring formula edge case)
- Risk: LLM introduces subtle misinterpretation (changes "MUST" to "SHOULD")
- Risk: compact file drifts over time as source is edited but compact is never re-reviewed

**Recommendation:**
1. **Add a review checkpoint to Task 5:**
   - After generating each compact file, run `/flux-drive` on the compact file itself
   - Review prompt: "Does this compact file preserve the correctness of the original algorithm? Are any critical decision points missing?"

2. **Establish a regeneration policy:**
   - Compact files are **committed to git** as derived artifacts
   - On source file change, `gen-skill-compact.sh` detects drift (via manifest) and blocks the commit
   - Developer must regenerate compact file and review the diff before committing

3. **Add structural validation:**
   - Compact files must include specific markers (e.g., "## Algorithm", "## Output Contract")
   - `gen-skill-compact.sh` checks for these markers and warns if missing

4. **Document the trade-off:**
   - Compact files are a 90% solution — edge cases require reading full SKILL.md
   - Add to compact file footer: "For edge cases, debugging, or full rationale, read SKILL.md and phase files"

---

## P2 Findings (Nice to Have)

### P2-1: Manifest Location Hidden File Anti-Pattern

**Finding:** `.compact-manifest` is a hidden dotfile in the skill directory. The ecosystem doesn't use hidden files for derived artifacts.

**Evidence:**
- `docs/catalog.json` is visible, not hidden
- `.beads/`, `.claude/`, `.git/` are hidden because they're **directories** containing state, not single-file artifacts

**Recommendation:**
- Rename to `compact-manifest.json` (no leading dot)
- Or place in a subdirectory: `skills/doc-watch/.artifacts/compact-manifest.json`

**Trade-off:** Leading dot keeps it out of casual `ls` output. This is minor — accept either choice, just document the decision.

---

### P2-2: Pre-computation Script Shell vs Python Trade-off Not Justified

**Finding:** The PRD chooses shell for `interwatch-scan.sh` without discussing the Python alternative. This is inconsistent with P1-2 (YAML parsing) but deserves its own finding.

**Context:**
- Signal evaluation involves: git commands, SQLite queries (`bd list`), file existence checks, version string parsing
- Shell is well-suited for **git/file operations** but awkward for **structured output** (JSON construction)
- Python is well-suited for **JSON/YAML** but adds subprocess overhead for every `git`/`bd` call

**Recommendation:**
- **If watchables config is hardcoded or trivial:** Shell script is fine
- **If watchables config is YAML:** Python script (consistent with P1-2)
- **Hybrid approach:** Shell script that sources a generated mapping from `config/watchables.yaml` (Python reads YAML, emits shell vars, shell sources it)

**Rationale:** The plan should explicitly discuss this trade-off instead of defaulting to shell.

---

### P2-3: Compact File Loader Convention is Weak Enforcement

**Finding:** Task 6 proposes a markdown comment convention (`<!-- compact: SKILL-compact.md -->`) to signal compact mode, but this is **advisory only** — the agent must choose to follow it.

**Evidence:**
- The plan says "This is a convention, not enforcement — the agent chooses to follow it"
- No mechanism prevents the agent from ignoring the compact file and reading the full phase chain
- No token budget tracking to verify compact loading is actually happening

**Impact:**
- Risk: agent ignores the convention and loads full SKILL.md anyway, wasting tokens
- Risk: no measurement of success — did the token overhead actually drop?

**Recommendation:**
1. **Add observability to Task 6:**
   - Modify `using-clavain` skill routing table to explicitly document compact mode
   - Add a log line in SessionStart hook: "Loaded SKILL-compact.md for flux-drive (364 lines saved)"

2. **Establish a measurement baseline:**
   - Before implementing, log token counts for a `/sprint` pipeline
   - After implementing, re-run and verify token reduction matches PRD targets

3. **Alternative enforcement (future work):**
   - Skill tool could accept a `compact: true` parameter
   - Claude Code platform change (out of scope for v1)

---

## Verdict

**APPROVE with mandatory P1 fixes.**

The plan is architecturally sound and demonstrates good judgment in choosing LLM summarization and pre-computation. Four P1 findings (naming, YAML parsing, freshness tests, LLM quality gates) must be resolved before execution. After fixes, this plan is ready to implement.

**Estimated fix effort:** 1-2 hours (mostly spec clarification, no design changes needed).
