"""CLI entry point: python3 -m clavain_sync sync [--upstream NAME] [--dry-run] [--auto] [--no-ai] [--report [FILE]]"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .classify import Classification, classify_file
from .config import load_config, Upstream
from .filemap import resolve_local_path
from .git_ops import (
    commit_is_reachable,
    count_new_commits,
    fetch_and_reset,
    get_ancestor_content,
    get_changed_files,
    get_head_commit,
)
from .namespace import apply_replacements
from .report import SyncReport
from .resolve import analyze_conflict
from .state import update_synced_commit

# Colors (respects NO_COLOR env)
if os.environ.get("NO_COLOR"):
    RED = GREEN = YELLOW = CYAN = BOLD = NC = ""
else:
    RED, GREEN, YELLOW, CYAN = "\033[0;31m", "\033[0;32m", "\033[0;33m", "\033[0;36m"
    BOLD, NC = "\033[1m", "\033[0m"


def find_upstreams_dir(project_root: Path) -> Path:
    """Find the upstreams clone directory."""
    work_dir = project_root / ".upstream-work"
    if work_dir.is_dir():
        return work_dir
    default = Path("/root/projects/upstreams")
    if default.is_dir():
        return default
    print(f"ERROR: No upstreams directory found. Run scripts/clone-upstreams.sh first.", file=sys.stderr)
    sys.exit(1)


def apply_file(upstream_content: str, local_file: Path, namespace_replacements: dict[str, str]) -> None:
    """Write upstream content to local path, applying namespace replacements."""
    local_file.parent.mkdir(parents=True, exist_ok=True)
    content = apply_replacements(upstream_content, namespace_replacements)
    local_file.write_text(content)


def sync_upstream(
    upstream: Upstream,
    *,
    project_root: Path,
    upstreams_dir: Path,
    config_path: Path,
    namespace_replacements: dict[str, str],
    protected_files: set[str],
    deleted_files: set[str],
    blocklist: list[str],
    mode: str,
    use_ai: bool,
    report: SyncReport,
) -> list[str]:
    """Sync a single upstream. Returns list of modified local file paths."""
    clone_dir = upstreams_dir / upstream.name
    if not (clone_dir / ".git").is_dir():
        print(f"  {RED}Clone not found at {clone_dir}{NC}")
        return []

    # Fetch latest
    fetch_and_reset(clone_dir, upstream.branch)
    head_commit = get_head_commit(clone_dir)
    head_short = head_commit[:7]

    if head_commit == upstream.last_synced_commit:
        print(f"  {GREEN}No new commits (HEAD: {head_short}){NC}")
        return []

    if not commit_is_reachable(clone_dir, upstream.last_synced_commit):
        print(f"  {RED}Last synced commit {upstream.last_synced_commit} not reachable — skipping{NC}")
        return []

    new_count = count_new_commits(clone_dir, upstream.last_synced_commit)
    print(f"  {CYAN}{new_count} new commits{NC} ({upstream.last_synced_commit[:7]} → {head_short})")

    # Get changed files
    diff_path = upstream.base_path if upstream.base_path else "."
    changed_files = get_changed_files(clone_dir, upstream.last_synced_commit, diff_path)

    if not changed_files:
        print("  No mapped files changed")
        if mode != "dry-run":
            update_synced_commit(config_path, upstream.name, head_commit)
        return []

    modified: list[str] = []
    counts = {"copy": 0, "auto": 0, "keep": 0, "conflict": 0, "skip": 0, "review": 0}

    for status, filepath in changed_files:
        if status == "D":
            continue

        # Strip basePath prefix
        if upstream.base_path and filepath.startswith(f"{upstream.base_path}/"):
            filepath = filepath[len(upstream.base_path) + 1:]

        # Resolve to local path
        local_path = resolve_local_path(filepath, upstream.file_map)
        if local_path is None:
            continue

        # Read contents using git object store for snapshot isolation
        # (avoids TOCTOU race if another process modifies the clone)
        local_full = project_root / local_path
        local_content = local_full.read_text() if local_full.is_file() else None
        upstream_content = get_ancestor_content(
            clone_dir, head_commit, upstream.base_path, filepath
        )
        if upstream_content is None:
            continue  # File listed in diff but not readable at commit
        ancestor_content = get_ancestor_content(
            clone_dir, upstream.last_synced_commit, upstream.base_path, filepath
        )

        # Classify
        classification = classify_file(
            local_path=local_path,
            local_content=local_content,
            upstream_content=upstream_content,
            ancestor_content=ancestor_content,
            protected_files=protected_files,
            deleted_files=deleted_files,
            namespace_replacements=namespace_replacements,
            blocklist=blocklist,
        )

        report.add_entry(local_path, classification)

        if classification in (Classification.SKIP_PROTECTED, Classification.SKIP_DELETED, Classification.SKIP_NOT_PRESENT):
            reason = classification.value.split(":", 1)[1]
            print(f"  {YELLOW}SKIP{NC}  {local_path:<50} ({reason})")
            counts["skip"] += 1

        elif classification == Classification.COPY:
            print(f"  {GREEN}COPY{NC}  {local_path}")
            counts["copy"] += 1
            if mode != "dry-run":
                apply_file(upstream_content, local_full, namespace_replacements)
                modified.append(local_path)

        elif classification == Classification.AUTO:
            print(f"  {GREEN}AUTO{NC}  {local_path:<50} (upstream-only change)")
            counts["auto"] += 1
            if mode != "dry-run":
                apply_file(upstream_content, local_full, namespace_replacements)
                modified.append(local_path)

        elif classification == Classification.KEEP_LOCAL:
            print(f"  {GREEN}KEEP{NC}  {local_path:<50} (local-only changes)")
            counts["keep"] += 1

        elif classification == Classification.CONFLICT:
            print(f"  {RED}CONFLICT{NC} {local_path}")
            counts["conflict"] += 1

            if mode == "dry-run":
                pass  # No action
            elif mode == "auto" and use_ai:
                print("           Analyzing with AI...")
                upstream_transformed = apply_replacements(upstream_content, namespace_replacements)
                ancestor_transformed = apply_replacements(ancestor_content or "", namespace_replacements)
                ai_result = analyze_conflict(
                    local_path=local_path,
                    local_content=local_content or "",
                    upstream_content=upstream_transformed,
                    ancestor_content=ancestor_transformed,
                    blocklist=blocklist,
                )
                report.add_ai_decision(local_path, ai_result.decision, ai_result.risk, ai_result.rationale)

                if ai_result.decision == "accept_upstream" and ai_result.risk == "low":
                    apply_file(upstream_content, local_full, namespace_replacements)
                    modified.append(local_path)
                    print(f"           {GREEN}AI: accept_upstream (risk: low) — auto-applied{NC}")
                elif ai_result.decision == "keep_local" and ai_result.risk == "low":
                    print(f"           {GREEN}AI: keep_local (risk: low) — preserved{NC}")
                else:
                    print(f"           {YELLOW}AI: {ai_result.decision} (risk: {ai_result.risk}) — skipped{NC}")
            elif mode == "auto":
                print(f"           {YELLOW}(skipped in --auto --no-ai mode){NC}")
            # Interactive mode: would need tty handling (not implemented in first iteration)

        elif classification.value.startswith("REVIEW"):
            reason = classification.value.split(":", 1)[1]
            print(f"  {CYAN}REVIEW{NC} {local_path:<50} ({reason})")
            counts["review"] += 1

    print(f"  Summary: {GREEN}{counts['copy']} copied{NC}, {GREEN}{counts['auto']} auto{NC}, "
          f"{GREEN}{counts['keep']} kept{NC}, {RED}{counts['conflict']} conflict{NC}, "
          f"{YELLOW}{counts['skip']} skipped{NC}, {CYAN}{counts['review']} review{NC}")

    # Update lastSyncedCommit
    if mode != "dry-run":
        update_synced_commit(config_path, upstream.name, head_commit)

    return modified


def run_contamination_check(
    modified_files: list[str],
    project_root: Path,
    blocklist: list[str],
    namespace_replacements: dict[str, str],
) -> int:
    """Check modified files for blocklist terms and raw namespace patterns."""
    print(f"\n{BOLD}─── Contamination Check ───{NC}")
    found = 0

    for file_path in modified_files:
        full = project_root / file_path
        if not full.is_file():
            continue
        content = full.read_text()

        for term in blocklist:
            if term in content:
                print(f"  {RED}WARN{NC} {file_path} contains blocklisted term: {BOLD}{term}{NC}")
                found += 1

        for old in namespace_replacements:
            if old in content:
                print(f"  {RED}WARN{NC} {file_path} still contains raw namespace: {BOLD}{old}{NC}")
                found += 1

    if found == 0:
        print(f"  {GREEN}No contamination detected{NC}")
    else:
        print(f"  {RED}{found} contamination warning(s){NC}")

    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Clavain upstream sync")
    sub = parser.add_subparsers(dest="command")

    sync_parser = sub.add_parser("sync", help="Sync upstreams to local")
    sync_parser.add_argument("--dry-run", action="store_true", help="Preview only")
    sync_parser.add_argument("--auto", action="store_true", help="Non-interactive (CI)")
    sync_parser.add_argument("--upstream", type=str, default="", help="Sync single upstream")
    sync_parser.add_argument("--no-ai", action="store_true", help="Disable AI conflict analysis")
    sync_parser.add_argument("--report", nargs="?", const=True, default=False, help="Generate report")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "sync":
        # Resolve paths
        script_dir = Path(__file__).resolve().parent.parent
        project_root = script_dir.parent
        config_path = project_root / "upstreams.json"
        upstreams_dir = find_upstreams_dir(project_root)

        if args.dry_run:
            mode = "dry-run"
        elif args.auto:
            mode = "auto"
        else:
            mode = "interactive"

        # Load config
        cfg = load_config(config_path)

        print(f"\n{BOLD}═══ Clavain Upstream Sync ═══{NC}")
        print(f"Mode: {CYAN}{mode}{NC}  AI: {not args.no_ai}  Report: {bool(args.report)}")
        print(f"Upstreams dir: {upstreams_dir}\n")

        all_modified: list[str] = []
        report = SyncReport()

        for upstream in cfg.upstreams:
            if args.upstream and upstream.name != args.upstream:
                continue

            print(f"{BOLD}─── {upstream.name} ───{NC}")
            modified = sync_upstream(
                upstream,
                project_root=project_root,
                upstreams_dir=upstreams_dir,
                config_path=config_path,
                namespace_replacements=cfg.namespace_replacements,
                protected_files=cfg.protected_files,
                deleted_files=cfg.deleted_files,
                blocklist=cfg.blocklist,
                mode=mode,
                use_ai=not args.no_ai,
                report=report,
            )
            all_modified.extend(modified)
            print()

        # Contamination check
        if all_modified:
            run_contamination_check(all_modified, project_root, cfg.blocklist, cfg.namespace_replacements)

        # Summary
        print(f"\n{BOLD}═══ Summary ═══{NC}")
        if mode == "dry-run":
            print(f"  {YELLOW}(dry-run — no files were modified){NC}")

        # Report
        if args.report:
            output = report.generate()
            if isinstance(args.report, str):
                Path(args.report).write_text(output)
                print(f"\n  Report written to: {CYAN}{args.report}{NC}")
            else:
                print(output)


if __name__ == "__main__":
    main()
