#!/usr/bin/env python3
"""Generate upstream impact summaries from upstreams.json.

Compares lastSyncedCommit to upstream HEAD for each configured upstream and reports:
- commit/file counts
- mapped-file impact (fileMap coverage)
- feature/breaking signals inferred from commit headlines
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

FEATURE_RE = re.compile(
    r"\b(feat|feature|add|support|new|command|tool|workflow|integration|api|mcp)\b",
    re.IGNORECASE,
)
BREAKING_RE = re.compile(
    r"\b(breaking|deprecat|remove|rename|incompatib|migration)\b",
    re.IGNORECASE,
)


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_gh_json(path: str) -> Any:
    result = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed for {path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def repo_from_url(url: str) -> str:
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("https://github.com/"):
        return url.removeprefix("https://github.com/")
    if url.startswith("git@github.com:"):
        return url.removeprefix("git@github.com:")
    return url


def mapped_patterns(upstream: dict[str, Any]) -> list[str]:
    base_path = (upstream.get("basePath") or "").strip("/")
    patterns: list[str] = []
    for source_pattern in upstream.get("fileMap", {}).keys():
        source_pattern = source_pattern.strip("/")
        if base_path:
            patterns.append(f"{base_path}/{source_pattern}")
        else:
            patterns.append(source_pattern)
    return patterns


def matches_any(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def collect_impact(upstream: dict[str, Any]) -> dict[str, Any]:
    name = upstream["name"]
    repo = repo_from_url(upstream["url"])
    branch = upstream.get("branch", "main")
    floating = bool(upstream.get("floating", False)) and not bool(upstream.get("fileMap", {}))

    head = run_gh_json(f"repos/{repo}/commits/{branch}")["sha"]
    base_commit = head if floating else upstream["lastSyncedCommit"]
    compare = run_gh_json(f"repos/{repo}/compare/{base_commit}...{head}")

    changed_files = [entry["filename"] for entry in compare.get("files", [])]
    patterns = mapped_patterns(upstream)
    mapped_changed = [p for p in changed_files if matches_any(p, patterns)]

    commit_entries: list[dict[str, Any]] = []
    feature_commits: list[dict[str, str]] = []
    breaking_signals: list[dict[str, str]] = []

    for commit in compare.get("commits", []):
        headline = commit["commit"]["message"].splitlines()[0].strip()
        short_sha = commit["sha"][:7]
        item = {"sha": short_sha, "headline": headline}
        commit_entries.append(item)
        if FEATURE_RE.search(headline):
            feature_commits.append(item)
        if BREAKING_RE.search(headline):
            breaking_signals.append(item)

    meaningful_change = bool(mapped_changed or feature_commits or breaking_signals)
    if floating:
        meaningful_change = False

    return {
        "name": name,
        "repo": repo,
        "tracking_mode": "floating-head" if floating else "pinned",
        "base_commit": base_commit,
        "head_commit": head,
        "ahead_commits": compare.get("total_commits", 0),
        "changed_file_count": len(changed_files),
        "mapped_changed_count": len(mapped_changed),
        "mapped_changed_files": mapped_changed,
        "feature_signal_count": len(feature_commits),
        "breaking_signal_count": len(breaking_signals),
        "feature_signals": feature_commits[:12],
        "breaking_signals": breaking_signals[:12],
        "top_commits": commit_entries[:15],
        "meaningful_change": meaningful_change,
    }


def to_markdown(report: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append(f"Generated: {utc_now_iso()}")
    lines.append("")
    lines.append("| Upstream | Tracking | Commits | Files Changed | Mapped Changed | Feature Signals | Breaking Signals |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")

    for row in report:
        lines.append(
            "| `{name}` | {tracking_mode} | {ahead_commits} | {changed_file_count} | {mapped_changed_count} | {feature_signal_count} | {breaking_signal_count} |".format(
                **row
            )
        )

    for row in report:
        lines.append("")
        lines.append(f"### `{row['name']}`")
        lines.append(
            f"Base `{row['base_commit'][:7]}` -> Head `{row['head_commit'][:7]}` ({row['ahead_commits']} commits)"
        )

        if row["mapped_changed_files"]:
            lines.append("Mapped file changes:")
            for filename in row["mapped_changed_files"][:15]:
                lines.append(f"- `{filename}`")
        else:
            lines.append("Mapped file changes: none")

        if row["feature_signals"]:
            lines.append("Feature signals:")
            for signal in row["feature_signals"][:8]:
                lines.append(f"- `{signal['sha']}` {signal['headline']}")
        else:
            lines.append("Feature signals: none")

        if row["breaking_signals"]:
            lines.append("Potential breaking signals:")
            for signal in row["breaking_signals"][:6]:
                lines.append(f"- `{signal['sha']}` {signal['headline']}")

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="upstreams.json")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--markdown-out", default="")
    args = parser.parse_args()

    upstreams_path = Path(args.config)
    payload = json.loads(upstreams_path.read_text(encoding="utf-8"))

    report: list[dict[str, Any]] = []
    for upstream in payload.get("upstreams", []):
        try:
            report.append(collect_impact(upstream))
        except Exception as exc:  # pragma: no cover - defensive reporting path
            report.append(
                {
                    "name": upstream.get("name", "unknown"),
                    "repo": repo_from_url(upstream.get("url", "")),
                    "error": str(exc),
                    "ahead_commits": 0,
                    "changed_file_count": 0,
                    "mapped_changed_count": 0,
                    "feature_signal_count": 0,
                    "breaking_signal_count": 0,
                    "mapped_changed_files": [],
                    "feature_signals": [],
                    "breaking_signals": [],
                    "meaningful_change": True,
                }
            )

    output = {"generated_at": utc_now_iso(), "upstreams": report}

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(output, indent=2))

    markdown = to_markdown(report)
    if args.markdown_out:
        Path(args.markdown_out).write_text(markdown, encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
