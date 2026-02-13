#!/usr/bin/env python3
"""Detect project domains using signals from flux-drive domain index.

Scans directories, files, build-system dependencies, and source keywords
to classify a project into one or more domains (e.g. game-simulation,
web-api, ml-pipeline).  Results are cached at {PROJECT}/.claude/flux-drive.yaml.

Exit codes:
    0  Domains detected (or cache is fresh when --check-stale)
    1  No domains detected (caller should use LLM fallback)
    2  Fatal error
    3  Cache is stale (structural changes detected) — only with --check-stale
    4  No cache exists — only with --check-stale
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Error: pyyaml is required – install with: pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = PLUGIN_ROOT / "config" / "flux-drive" / "domains" / "index.yaml"

# Weights for signal categories
W_DIR = 0.3
W_FILE = 0.2
W_FRAMEWORK = 0.3
W_KEYWORD = 0.2

# Source extensions to scan for keyword signals
SOURCE_EXTENSIONS = {".py", ".go", ".rs", ".ts", ".js", ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".gd", ".dart"}

# Current cache format version — bump when schema changes
CACHE_VERSION = 1

# Files whose presence/absence/content indicates structural project changes
STRUCTURAL_FILES = {
    "package.json", "Cargo.toml", "go.mod", "pyproject.toml",
    "requirements.txt", "Gemfile", "build.gradle", "build.gradle.kts",
    "project.godot", "pom.xml", "CMakeLists.txt", "Makefile",
}

# File extensions indicating structural project type changes (new tech stack)
STRUCTURAL_EXTENSIONS = {
    ".gd", ".tscn", ".unity", ".uproject",
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

class DomainSpec:
    """Parsed domain entry from index.yaml."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.profile: str = raw["profile"]
        self.min_confidence: float = float(raw.get("min_confidence", 0.3))
        signals = raw.get("signals", {})
        self.directories: list[str] = signals.get("directories", [])
        self.files: list[str] = signals.get("files", [])
        self.frameworks: list[str] = signals.get("frameworks", [])
        self.keywords: list[str] = signals.get("keywords", [])


def load_index(path: Path) -> list[DomainSpec]:
    """Load domain definitions from index.yaml."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [DomainSpec(d) for d in data["domains"]]


# ---------------------------------------------------------------------------
# Structural hash
# ---------------------------------------------------------------------------

def compute_structural_hash(project: Path) -> str:
    """Compute deterministic hash of structural files.

    For each file in sorted(STRUCTURAL_FILES):
      - If file exists: sha256(file_contents)
      - If file missing: sentinel "__absent__"
    Concatenate "filename:hash\\n" pairs, hash the result.
    Returns "sha256:{hex}" prefixed string.
    """
    parts: list[str] = []
    for name in sorted(STRUCTURAL_FILES):
        fpath = project / name
        if fpath.is_file():
            try:
                content = fpath.read_bytes()
                file_hash = hashlib.sha256(content).hexdigest()
            except OSError:
                file_hash = "__absent__"
        else:
            file_hash = "__absent__"
        parts.append(f"{name}:{file_hash}")
    combined = "\n".join(parts) + "\n"
    overall = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return f"sha256:{overall}"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def read_cache(path: Path) -> dict[str, Any] | None:
    """Read existing cache file. Returns None if absent or unparseable."""
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("domains"):
            return data
    except Exception:
        pass
    return None


def write_cache(path: Path, results: list[dict[str, Any]], structural_hash: str | None = None) -> None:
    """Write detection results as YAML cache with atomic rename.

    Uses temp-file-and-rename pattern to prevent corruption from
    interrupted writes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "cache_version": CACHE_VERSION,
        "domains": results,
        "detected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if structural_hash is not None:
        payload["structural_hash"] = structural_hash
    header = "# Auto-detected by flux-drive. Edit to override.\n"
    content = (header + yaml.dump(payload, default_flow_style=False, sort_keys=False)).encode("utf-8")

    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, content)
        os.fsync(fd)
        os.close(fd)
        os.rename(tmp_path, str(path))  # atomic on POSIX
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------

def _parse_iso_datetime(s: str) -> dt.datetime | None:
    """Parse an ISO 8601 datetime string, returning None on failure."""
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s)
    except (ValueError, TypeError):
        # Fall back to date-only format from v0 caches
        try:
            d = dt.date.fromisoformat(s)
            return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)
        except (ValueError, TypeError):
            return None


def _check_stale_tier1(project: Path, cache: dict[str, Any]) -> int | None:
    """Tier 1: Structural hash comparison (<100ms).

    Returns:
        0 if hash matches (fresh)
        3 if hash differs (stale)
        None if hash missing from cache (try next tier)
    """
    cached_hash = cache.get("structural_hash")
    if not cached_hash or not isinstance(cached_hash, str):
        return None
    current_hash = compute_structural_hash(project)
    if current_hash == cached_hash:
        return 0
    return 3


def _check_stale_tier2(project: Path, cache: dict[str, Any], dry_run: bool = False) -> int | None:
    """Tier 2: Git log check (<500ms).

    Returns:
        0 if no structural changes since detection (fresh)
        3 if structural changes found (stale)
        None if git unavailable (try next tier)
    """
    git_dir = project / ".git"
    if not git_dir.exists():
        return None

    detected_at = cache.get("detected_at", "")
    parsed = _parse_iso_datetime(str(detected_at))
    if parsed is None:
        return 3  # can't compare without a timestamp

    since_str = parsed.isoformat()

    # Check additions, modifications, copies, deletions (not renames — handled separately)
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since_str}", "--diff-filter=ACDM",
             "--name-only", "--format=", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(project),
        )
        if result.returncode != 0:
            return None  # git error, fall to tier 3
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    changed_files = {line.strip() for line in result.stdout.splitlines() if line.strip()}

    triggers: list[str] = []
    for f in changed_files:
        basename = os.path.basename(f)
        if basename in STRUCTURAL_FILES:
            triggers.append(f"structural file: {f}")
        _, ext = os.path.splitext(f)
        if ext in STRUCTURAL_EXTENSIONS:
            triggers.append(f"structural extension: {f}")

    # Check renames separately
    try:
        rename_result = subprocess.run(
            ["git", "log", f"--since={since_str}", "--diff-filter=R",
             "--name-status", "--format=", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(project),
        )
        if rename_result.returncode == 0:
            for line in rename_result.stdout.splitlines():
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    old_name = os.path.basename(parts[1])
                    new_name = os.path.basename(parts[2])
                    old_structural = old_name in STRUCTURAL_FILES
                    new_structural = new_name in STRUCTURAL_FILES
                    if old_structural != new_structural:
                        triggers.append(f"structural rename: {parts[1]} -> {parts[2]}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # rename check is best-effort

    if dry_run and triggers:
        for t in triggers:
            print(f"  Trigger: {t}")

    return 3 if triggers else 0


def _check_stale_tier3(project: Path, cache: dict[str, Any]) -> int:
    """Tier 3: Mtime fallback for non-git projects.

    Returns:
        0 if no structural files newer than detection (fresh)
        3 if any structural file is newer (stale)
    """
    detected_at = cache.get("detected_at", "")
    parsed = _parse_iso_datetime(str(detected_at))
    if parsed is None:
        return 3  # can't compare without a timestamp

    # Convert to epoch for mtime comparison
    detected_epoch = parsed.timestamp()

    for name in STRUCTURAL_FILES:
        fpath = project / name
        if fpath.is_file():
            try:
                if fpath.stat().st_mtime > detected_epoch:
                    return 3
            except OSError:
                pass

    return 0


def check_stale(project: Path, cache_path: Path, dry_run: bool = False) -> int:
    """Check if cached domain detection is stale.

    Returns exit code:
        0 — cache is fresh (or override: true)
        3 — cache is stale
        4 — no cache exists
    """
    cache = read_cache(cache_path)
    if cache is None:
        if dry_run:
            print("No cache found.")
        return 4

    # override: true short-circuits before any computation
    if cache.get("override"):
        if dry_run:
            print("Cache has override: true — never stale.")
        return 0

    # cache_version missing or outdated
    version = cache.get("cache_version")
    if version is None or (isinstance(version, int) and version < CACHE_VERSION):
        if dry_run:
            print(f"Cache version {version} < {CACHE_VERSION} — stale (format upgrade needed).")
        return 3

    # Tier 1: Hash check
    if dry_run:
        cached_hash = cache.get("structural_hash", "(none)")
        current_hash = compute_structural_hash(project)
        print(f"Tier 1 (hash): {cached_hash} → {current_hash}")
    tier1 = _check_stale_tier1(project, cache)
    if tier1 is not None:
        if dry_run:
            print(f"  Verdict: {'FRESH' if tier1 == 0 else 'STALE'}")
        return tier1

    # Tier 2: Git log
    if dry_run:
        print(f"Tier 2 (git): checking changes since {cache.get('detected_at', '(unknown)')}")
    tier2 = _check_stale_tier2(project, cache, dry_run=dry_run)
    if tier2 is not None:
        if dry_run:
            print(f"  Verdict: {'FRESH' if tier2 == 0 else 'STALE'}")
        return tier2

    # Tier 3: Mtime fallback
    if dry_run:
        print("Tier 3 (mtime): checking file modification times")
    tier3 = _check_stale_tier3(project, cache)
    if dry_run:
        print(f"  Verdict: {'FRESH' if tier3 == 0 else 'STALE'}")
    return tier3


# ---------------------------------------------------------------------------
# Signal gatherers
# ---------------------------------------------------------------------------

def gather_directories(project: Path, signals: list[str]) -> float:
    """Fraction of directory signals that exist under project root."""
    if not signals:
        return 0.0
    try:
        existing = {e.name for e in project.iterdir() if e.is_dir()}
    except OSError:
        return 0.0
    # Signals can be nested like "ai/behavior" — check with /
    matches = 0
    for sig in signals:
        if "/" in sig:
            if (project / sig).is_dir():
                matches += 1
        elif sig in existing:
            matches += 1
    return matches / len(signals)


def gather_files(project: Path, signals: list[str]) -> float:
    """Fraction of file-pattern signals matching in project root + 1-level subdirs."""
    if not signals:
        return 0.0
    # Collect filenames from root and immediate subdirectories
    filenames: set[str] = set()
    try:
        for entry in project.iterdir():
            if entry.is_file():
                filenames.add(entry.name)
            elif entry.is_dir() and not entry.name.startswith("."):
                try:
                    for child in entry.iterdir():
                        if child.is_file():
                            filenames.add(child.name)
                except OSError:
                    pass
    except OSError:
        return 0.0

    matches = sum(1 for sig in signals if any(fnmatch.fnmatch(f, sig) for f in filenames))
    return matches / len(signals)


def _parse_package_json_deps(project: Path) -> set[str]:
    """Extract dependency names from package.json."""
    pkg = project / "package.json"
    if not pkg.exists():
        return set()
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        deps: set[str] = set()
        for key in ("dependencies", "devDependencies"):
            section = data.get(key, {})
            if isinstance(section, dict):
                deps.update(section.keys())
        return deps
    except Exception:
        return set()


def _parse_cargo_toml_deps(project: Path) -> set[str]:
    """Extract dependency names from Cargo.toml."""
    cargo = project / "Cargo.toml"
    if not cargo.exists():
        return set()
    try:
        data = tomllib.loads(cargo.read_text(encoding="utf-8"))
        deps: set[str] = set()
        for key in ("dependencies", "dev-dependencies", "build-dependencies"):
            section = data.get(key, {})
            if isinstance(section, dict):
                deps.update(section.keys())
        return deps
    except Exception:
        return set()


def _parse_go_mod_deps(project: Path) -> set[str]:
    """Extract module paths from go.mod require block."""
    gomod = project / "go.mod"
    if not gomod.exists():
        return set()
    try:
        text = gomod.read_text(encoding="utf-8")
        deps: set[str] = set()
        # Match require ( ... ) blocks
        for block in re.findall(r"require\s*\((.*?)\)", text, re.DOTALL):
            for line in block.strip().splitlines():
                parts = line.strip().split()
                if parts and not parts[0].startswith("//"):
                    deps.add(parts[0].split("/")[-1].lower())
        # Single-line requires: require github.com/foo/bar v1.0
        for match in re.findall(r"^require\s+(\S+)", text, re.MULTILINE):
            deps.add(match.split("/")[-1].lower())
        return deps
    except Exception:
        return set()


def _parse_pyproject_deps(project: Path) -> set[str]:
    """Extract dependency names from pyproject.toml."""
    pyproj = project / "pyproject.toml"
    if not pyproj.exists():
        return set()
    try:
        data = tomllib.loads(pyproj.read_text(encoding="utf-8"))
        deps: set[str] = set()
        # PEP 621: [project.dependencies]
        for dep in data.get("project", {}).get("dependencies", []):
            name = re.split(r"[>=<!\[; ]", dep)[0].strip().lower()
            if name:
                deps.add(name)
        # Poetry: [tool.poetry.dependencies]
        section = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        if isinstance(section, dict):
            deps.update(k.lower() for k in section if k.lower() != "python")
        return deps
    except Exception:
        return set()


def _parse_requirements_txt(project: Path) -> set[str]:
    """Extract package names from requirements.txt."""
    req = project / "requirements.txt"
    if not req.exists():
        return set()
    try:
        deps: set[str] = set()
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-")):
                name = re.split(r"[>=<!\[; ]", line)[0].strip().lower()
                if name:
                    deps.add(name)
        return deps
    except Exception:
        return set()


def gather_frameworks(project: Path, signals: list[str]) -> float:
    """Fraction of framework signals found in build-system dependency lists."""
    if not signals:
        return 0.0
    all_deps: set[str] = set()
    all_deps.update(_parse_package_json_deps(project))
    all_deps.update(_parse_cargo_toml_deps(project))
    all_deps.update(_parse_go_mod_deps(project))
    all_deps.update(_parse_pyproject_deps(project))
    all_deps.update(_parse_requirements_txt(project))
    # Normalise for comparison: lowercase, strip hyphens/underscores
    normalised = {d.replace("-", "").replace("_", "") for d in all_deps}
    matches = sum(
        1
        for sig in signals
        if sig.replace("-", "").replace("_", "") in normalised
    )
    return matches / len(signals)


def gather_keywords(project: Path, signals: list[str], limit: int = 5) -> float:
    """Fraction of keyword signals found in up to *limit* source files."""
    if not signals:
        return 0.0
    # Collect candidate source files (breadth-first, skip hidden dirs)
    source_files: list[Path] = []
    try:
        for entry in sorted(project.iterdir()):
            if entry.is_file() and entry.suffix in SOURCE_EXTENSIONS:
                source_files.append(entry)
            elif entry.is_dir() and not entry.name.startswith("."):
                try:
                    for child in sorted(entry.iterdir()):
                        if child.is_file() and child.suffix in SOURCE_EXTENSIONS:
                            source_files.append(child)
                            if len(source_files) >= limit * 3:
                                break
                except OSError:
                    pass
            if len(source_files) >= limit * 3:
                break
    except OSError:
        return 0.0

    source_files = source_files[:limit]
    if not source_files:
        return 0.0

    # Read and search
    combined = ""
    for sf in source_files:
        try:
            combined += sf.read_text(encoding="utf-8", errors="ignore") + "\n"
        except OSError:
            pass

    if not combined:
        return 0.0

    combined_lower = combined.lower()
    matches = sum(1 for kw in signals if kw.lower() in combined_lower)
    return matches / len(signals)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_domain(dir_score: float, file_score: float, fw_score: float, kw_score: float) -> float:
    """Compute weighted average across signal categories."""
    return dir_score * W_DIR + file_score * W_FILE + fw_score * W_FRAMEWORK + kw_score * W_KEYWORD


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def detect(project: Path, domains: list[DomainSpec], skip_keywords_threshold: bool = True) -> list[dict[str, Any]]:
    """Run detection and return list of detected domain dicts."""
    results: list[dict[str, Any]] = []

    for spec in domains:
        d = gather_directories(project, spec.directories)
        f = gather_files(project, spec.files)
        fw = gather_frameworks(project, spec.frameworks)

        # Performance shortcut: skip keyword scan if already confident
        preliminary = d * W_DIR + f * W_FILE + fw * W_FRAMEWORK
        if skip_keywords_threshold and preliminary >= spec.min_confidence:
            kw = 0.0
            confidence = preliminary
        else:
            kw = gather_keywords(project, spec.keywords)
            confidence = score_domain(d, f, fw, kw)

        if confidence >= spec.min_confidence:
            results.append({
                "name": spec.profile,
                "confidence": round(confidence, 2),
            })

    # Sort descending by confidence; mark highest as primary
    results.sort(key=lambda r: r["confidence"], reverse=True)
    if results:
        results[0]["primary"] = True
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect project domains from flux-drive domain index signals.",
    )
    parser.add_argument("project_root", type=Path, help="Path to the project to scan")
    parser.add_argument(
        "--index-yaml",
        type=Path,
        default=DEFAULT_INDEX,
        help=f"Path to index.yaml (default: {DEFAULT_INDEX})",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=None,
        help="Override cache location (default: {PROJECT_ROOT}/.claude/flux-drive.yaml)",
    )
    parser.add_argument("--no-cache", action="store_true", help="Force re-scan even if cache exists")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON instead of YAML")
    parser.add_argument("--check-stale", action="store_true", help="Check if cache is stale (exit 0=fresh, 3=stale, 4=none)")
    parser.add_argument("--dry-run", action="store_true", help="With --check-stale: show diagnostic details")
    args = parser.parse_args()

    project = args.project_root.resolve()
    if not project.is_dir():
        print(f"Error: {project} is not a directory", file=sys.stderr)
        return 2

    cache_path = (args.cache_path or project / ".claude" / "flux-drive.yaml").resolve()

    # --check-stale mode: just check and exit
    if args.check_stale:
        return check_stale(project, cache_path, dry_run=args.dry_run)

    index_path = args.index_yaml.resolve()
    if not index_path.exists():
        print(f"Error: index.yaml not found at {index_path}", file=sys.stderr)
        return 2

    # Cache check
    if not args.no_cache:
        cached = read_cache(cache_path)
        if cached is not None:
            results = cached["domains"]
            if args.json_output:
                print(json.dumps({"domains": results, "detected_at": cached.get("detected_at", "")}, indent=2))
            else:
                print(yaml.dump({"domains": results, "detected_at": cached.get("detected_at", "")}, default_flow_style=False, sort_keys=False), end="")
            return 0

    # Even with --no-cache, respect override: true (user intent, not staleness)
    if args.no_cache:
        cached = read_cache(cache_path)
        if cached is not None and cached.get("override"):
            results = cached["domains"]
            if args.json_output:
                print(json.dumps({"domains": results, "detected_at": cached.get("detected_at", "")}, indent=2))
            else:
                print(yaml.dump({"domains": results, "detected_at": cached.get("detected_at", "")}, default_flow_style=False, sort_keys=False), end="")
            return 0

    # Run detection
    domains = load_index(index_path)
    results = detect(project, domains)

    if not results:
        return 1

    # Compute structural hash for cache
    structural_hash = compute_structural_hash(project)

    # Write cache and output
    write_cache(cache_path, results, structural_hash=structural_hash)
    output = {"domains": results, "detected_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if args.json_output:
        print(json.dumps(output, indent=2))
    else:
        print(yaml.dump(output, default_flow_style=False, sort_keys=False), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
