# Code Quality Review: evaluation harness

**Date:** 2026-02-15
**Scope:** `/root/projects/Interverse/os/clavain/galiana/eval.py`
**Comparison files:** `analyze.py`, `experiment.py`

## Executive Summary

**Overall assessment:** Strong Python idioms and solid error handling. Three P0 issues require immediate attention (duplicate code, inconsistent type annotations, missing error context). Several P1 improvements would enhance maintainability.

**Key strengths:**
- Excellent subprocess error handling with timeouts and capture
- Good use of type hints on function signatures
- Consistent module-level organization and clear separation of concerns
- Pythonic constructs (list comprehensions, defaultdict, early returns)

**Key weaknesses:**
- 86 lines of exact code duplication with experiment.py (normalize_title, titles_match, title matching logic)
- Type hint inconsistencies across the codebase (missing on local vars, inconsistent union notation)
- Silent exception handling hides failure modes in several critical paths

---

## P0 Findings (Correctness & Maintainability)

### P0-1: Critical Code Duplication (86 lines)

**Location:** Lines 199-226, 228-386

**Issue:** Three functions (`normalize_title`, `titles_match`, `compute_baseline_metrics` title matching logic) are exact duplicates between file and experiment.py. This is 86 lines of duplicated code that will drift over time.

**Evidence:**
```python
# Lines 199-203
def normalize_title(title: str) -> set[str]:
    """Normalize finding title to word set (lowercase, no punctuation)."""
    cleaned = re.sub(r'[^\w\s]', ' ', title.lower())
    return {word for word in cleaned.split() if word}

# experiment.py lines 184-189 (identical)
```

**Impact:** Bug fixes or threshold adjustments must be applied twice. Already a maintenance burden with 3 files using this logic.

**Fix:** Extract to shared `utils.py` module:
```python
# galiana/utils.py
def normalize_title(title: str) -> set[str]:
    """Normalize finding title to word set (lowercase, no punctuation)."""
    cleaned = re.sub(r'[^\w\s]', ' ', title.lower())
    return {word for word in cleaned.split() if word}

def titles_match(t1: str, t2: str, threshold: float = 0.6) -> bool:
    """Check if two titles match via word overlap."""
    words1 = normalize_title(t1)
    words2 = normalize_title(t2)
    if not words1 or not words2:
        return False
    overlap = len(words1 & words2)
    min_len = min(len(words1), len(words2))
    return (overlap / min_len) > threshold if min_len > 0 else False

# Then import in both files:
from .utils import normalize_title, titles_match
```

**Lines to remove:** 199-226
**Lines to remove from experiment.py:** 184-204

---

### P0-2: Inconsistent Type Annotations

**Location:** Lines 263-264, 75-89, multiple functions

**Issue:** Type annotations are inconsistent across the module:
1. Local variables sometimes have type hints (line 263: `passed: bool`), sometimes don't (line 147: `all_findings` inferred)
2. `load_topologies()` returns `dict` but analyze.py uses `dict[str, Any]`
3. Mixed union syntax (`str | None` vs `Optional[str]`)

**Evidence:**
```python
# Line 75 - returns bare dict
def load_topologies() -> dict:
    """Read topologies.json from same directory as this script."""

# analyze.py line 81 - returns dict[str, Any] for same operation
def load_telemetry_events(...) -> tuple[list[dict[str, Any]], dict[str, str]]:

# Lines 263-264 - explicit local var annotations
passed = False
actual: int | str = 0
expected: int | str = ""
```

**Impact:** Reduced type safety, harder to catch bugs during development, confusing for contributors.

**Fix:**
```python
# Consistent return types
def load_topologies() -> dict[str, Any]:
    """Read topologies.json from same directory as this script."""

# Remove unnecessary local var annotations (Python convention)
# Lines 263-264 should be:
passed = False
actual = 0  # type will be inferred from safe_rate usage
expected = ""
```

**Style note:** Python convention is to omit type hints on local variables unless the type is ambiguous. The explicit `int | str` on line 263-264 is unusual and suggests the variable is doing too much (polymorphic by severity check type).

---

### P0-3: Missing Error Context in Silent Failure Paths

**Location:** Lines 186-188, 461-463, 505-507

**Issue:** Three critical paths catch exceptions and print warnings but lose stack traces and failure context:

```python
# Line 186-188
except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
    print(f"WARN: Agent {agent_name} failed: {e}", file=sys.stderr)
    continue

# Line 461-463
except (OSError, subprocess.SubprocessError) as e:
    print(f"WARN: interbench scoring failed: {e}", file=sys.stderr)
    return None

# Line 505-507
except (OSError, subprocess.SubprocessError) as e:
    print(f"WARN: regression detection failed: {e}", file=sys.stderr)
    return []
```

**Impact:** When evaluations fail, users get no actionable debugging information. Silent failures hide systemic issues (e.g., path problems, permission errors, broken shadow-review.sh).

**Fix:** Add structured logging with context:
```python
import traceback

# Line 186-188 replacement
except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
    print(f"WARN: Agent {agent_name} failed: {e}", file=sys.stderr)
    if os.getenv("GALIANA_DEBUG"):
        traceback.print_exc()
    # Log to results for post-mortem
    all_findings.append({
        "title": f"Agent {agent_name} execution failed",
        "severity": "P3",
        "section": "infrastructure",
        "description": f"Agent failed with {type(e).__name__}: {e}"
    })
    continue
```

**Alternative:** Use Python `logging` module for structured severity levels:
```python
import logging
logger = logging.getLogger(__name__)

# Then replace prints with:
logger.warning("Agent %s failed", agent_name, exc_info=True)
```

---

## P1 Findings (Code Quality & Patterns)

### P1-1: Hard-coded Magic Numbers

**Location:** Lines 169, 239, 225, 664

**Issue:** Timeout (300s), threshold (0.6), recall threshold (0.85) are hard-coded.

**Evidence:**
```python
# Line 169
timeout=300,  # 5 minute timeout per agent

# Line 225 (threshold parameter default)
def titles_match(t1: str, t2: str, threshold: float = 0.6) -> bool:

# Line 664
if recall is not None and recall < 0.85:
```

**Impact:** Requires code changes to tune behavior. Different fixtures may need different thresholds.

**Fix:** Move to config or CLI args:
```python
# Top of file
DEFAULT_AGENT_TIMEOUT = 300
DEFAULT_TITLE_MATCH_THRESHOLD = 0.6
RECALL_ALERT_THRESHOLD = 0.85

# Or add CLI args
parser.add_argument("--timeout", type=int, default=300, help="Agent timeout in seconds")
parser.add_argument("--recall-threshold", type=float, default=0.85, help="Recall warning threshold")
```

---

### P1-2: Inconsistent Error Handling Patterns vs Sibling Files

**Location:** Lines 58-63 (load_fixtures), 88-92 (load_topologies)

**Issue:** `load_fixtures` returns empty list on missing directory (line 41), but `load_topologies` exits on missing file (line 86). Inconsistent with analyze.py which uses empty returns for optional data.

**Evidence:**
```python
# Line 40-41
if not golden_dir.exists():
    return fixtures  # Empty list

# Line 84-86
if not topology_file.exists():
    print(f"ERROR: {topology_file} not found", file=sys.stderr)
    sys.exit(1)  # Hard exit
```

**Impact:** Unexpected behavior differences. `load_topologies` prevents dry-run from working if topologies.json is missing.

**Fix:** Align with analyze.py pattern — return empty dict for missing topologies, let caller decide if it's fatal:
```python
def load_topologies() -> dict[str, Any]:
    """Read topologies.json from same directory as this script."""
    script_dir = Path(__file__).parent
    topology_file = script_dir / "topologies.json"

    if not topology_file.exists():
        return {}

    try:
        return json.loads(topology_file.read_text())
    except json.JSONDecodeError as e:
        print(f"WARN: Invalid JSON in {topology_file}: {e}", file=sys.stderr)
        return {}

# Then in main():
all_topologies = load_topologies()
if not all_topologies:
    print("ERROR: No topologies defined in topologies.json", file=sys.stderr)
    sys.exit(1)
```

---

### P1-3: Overly Complex Property Check Logic

**Location:** Lines 228-319 (check_properties function, 91 lines)

**Issue:** Single function handles 4 different property types with nested conditionals. Hard to extend for new property types.

**Impact:** Adding new property types requires modifying this function. Difficult to test individual property types in isolation.

**Fix:** Extract property type handlers:
```python
def check_min_findings(findings: list[dict], min_count: int) -> tuple[bool, int, str]:
    """Check minimum findings count."""
    actual_count = len(findings)
    return (actual_count >= min_count, actual_count, f">={min_count}")

def check_severity_threshold(findings: list[dict], severity: str, min_count: int) -> tuple[bool, int, str]:
    """Check findings meet severity threshold."""
    threshold_level = SEVERITY_ORDER.get(severity.upper())
    if threshold_level is None:
        return (False, 0, "invalid severity")

    count = sum(
        1 for f in findings
        if SEVERITY_ORDER.get(str(f.get("severity", "")).upper(), 999) <= threshold_level
    )
    return (count >= min_count, count, f">={min_count} at {severity}+")
```

---

### P1-4: Unused Function Parameter

**Location:** Line 117 (run_fixture_evaluation)

**Issue:** `script_dir` parameter is passed but never used except to pass to shadow script lookup (line 142), which could use `__file__`.

**Fix:** Remove parameter and compute internally:
```python
def run_fixture_evaluation(
    fixture: dict,
    topology_name: str,
    topology_agents: list[str],
    project_dir: Path
) -> dict:
    """Run fixture evaluation with specified topology."""
    script_dir = Path(__file__).parent
    shadow_script = script_dir / "shadow-review.sh"
    ...
```

---

### P1-5: Misleading Variable Name

**Location:** Line 428 (score_via_interbench)

**Issue:** Variable `lines` suggests multiple lines, but it's filtered to non-empty lines and then only the last element is used. Name doesn't match usage.

**Fix:** Rename to clarify intent:
```python
# Parse run ID from last non-empty line
output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
if not output_lines:
    return None
run_id = output_lines[-1]
```

---

### P1-6: Missing Docstring Details

**Location:** Lines 322-332 (compute_baseline_metrics)

**Issue:** Docstring doesn't explain the P0/P1 filtering behavior or the title matching algorithm.

**Fix:** Expand docstring:
```python
def compute_baseline_metrics(
    findings: list[dict],
    baseline_findings: list[dict]
) -> dict:
    """Compute overlap metrics vs baseline using fuzzy title matching.

    Filters baseline to P0/P1 findings only, then matches actual findings
    to baseline using word overlap (60% threshold). Computes recall as
    (matched baseline / total baseline P0+P1) and precision as
    (matched actual / total actual).

    Args:
        findings: Actual findings from evaluation run (all severities)
        baseline_findings: Expected findings from baseline.json

    Returns:
        Dict with recall, precision, unique_discoveries, false_positive_rate,
        total_findings, p0_findings, p1_findings. Recall/precision are None
        if baseline is empty.
    """
```

---

### P1-7: Regression Detection Not Implemented

**Location:** Lines 711-714

**Issue:** Regression detection is a no-op with a comment saying "not fully implemented". The CLI flag `--previous-run` is accepted but ignored.

**Fix:** Either remove the flag or implement basic regression detection. Current state is misleading.

---

## Comparison with Sibling Files

### analyze.py

**Similarities:**
- Both use `iter_jsonl` helper (minor duplication, acceptable)
- Both use `Path.home() / ".clavain"` for output files

**Differences:**
- analyze.py has comprehensive type hints on all functions; file is inconsistent (see P0-2)
- analyze.py uses logging-style structured comments; file uses print statements
- analyze.py has better docstrings with example values

**Verdict:** File should adopt analyze.py's type hint discipline.

### experiment.py

**Similarities:**
- Exact code duplication (see P0-1) for title matching logic
- Both use `run_shadow_review` pattern

**Differences:**
- experiment.py has `classify_task_type` logic that this file doesn't need
- This file has property checking logic that experiment.py doesn't need

**Verdict:** Refactor common code to shared module (see P0-1 fix).

---

## Summary Statistics

- **Total lines reviewed:** 796
- **Total findings:** 10 (3 P0, 7 P1, 0 P2)
- **Code duplication:** 86 lines (10.8% of file)
- **Functions reviewed:** 15

**Conclusion:** Well-structured with strong Python idioms, but suffers from code duplication (P0-1) and inconsistent type safety (P0-2). Fixing the P0 issues would bring it to production quality. The P1 issues are primarily about long-term maintainability and can be addressed incrementally.
