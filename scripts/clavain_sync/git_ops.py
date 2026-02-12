"""Git operations via subprocess — fetch, diff, show ancestor content."""
from __future__ import annotations

import subprocess
from pathlib import Path


def fetch_and_reset(clone_dir: Path, branch: str) -> None:
    """Fetch origin and hard-reset to latest."""
    subprocess.run(
        ["git", "-C", str(clone_dir), "fetch", "origin", "--quiet"],
        capture_output=True, check=False,
    )
    subprocess.run(
        ["git", "-C", str(clone_dir), "reset", "--hard", f"origin/{branch}", "--quiet"],
        capture_output=True, check=False,
    )


def get_head_commit(clone_dir: Path) -> str:
    """Return full HEAD commit hash."""
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def commit_is_reachable(clone_dir: Path, commit: str) -> bool:
    """Check if a commit exists in the repo."""
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "cat-file", "-e", commit],
        capture_output=True, check=False,
    )
    return result.returncode == 0


def count_new_commits(clone_dir: Path, since_commit: str) -> int:
    """Count commits between since_commit and HEAD."""
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-list", "--count", f"{since_commit}..HEAD"],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())


def get_changed_files(clone_dir: Path, since_commit: str, diff_path: str = ".") -> list[tuple[str, str]]:
    """Return list of (status, filepath) changed since commit.

    Status is one of: A (added), M (modified), D (deleted).
    """
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "diff", "--name-status", since_commit, "HEAD", "--", diff_path],
        capture_output=True, text=True, check=False,
    )
    entries = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            entries.append((parts[0], parts[1]))
    return entries


def get_ancestor_content(clone_dir: Path, commit: str, base_path: str, filepath: str) -> str | None:
    """Get file content at a specific commit. Returns None if not found."""
    full_path = f"{base_path}/{filepath}" if base_path else filepath
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "show", f"{commit}:{full_path}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout
