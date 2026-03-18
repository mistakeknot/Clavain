"""Structural checks for Codex installer manifests and shell wrappers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _write_skill(skill_dir: Path, name: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill\n---\n# {name}\n",
        encoding="utf-8",
    )


def _write_stub_clavain_source(source_dir: Path) -> None:
    (source_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (source_dir / "skills").mkdir(exist_ok=True)
    (source_dir / "commands").mkdir(exist_ok=True)
    (source_dir / "README.md").write_text("# Stub Clavain\n", encoding="utf-8")
    (source_dir / "scripts" / "install-codex.sh").write_text(
        """#!/usr/bin/env bash
set -euo pipefail

action="${1:-}"
if [[ "$action" == "doctor" ]]; then
  if [[ " $* " == *" --json "* ]]; then
    echo '{"status":"ok"}'
  else
    echo "Doctor checks passed."
  fi
  exit 0
fi

exit 0
""",
        encoding="utf-8",
    )
    (source_dir / "scripts" / "install-codex.sh").chmod(0o755)
    (source_dir / "agent-rig.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "recommended": [
                        {"source": "tool-time@interagency-marketplace"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def test_codex_manifest_uses_agents_skills_path(project_root):
    """Active and example manifests should advertise Codex native skill discovery."""
    manifests = [project_root / "agent-rig.json"]
    # Monorepo example manifest — only exists in full Demarch checkout, not standalone CI
    repo_root = project_root.parent.parent
    example = repo_root / "core" / "agent-rig" / "examples" / "clavain" / "agent-rig.json"
    if example.exists():
        manifests.append(example)

    for manifest_path in manifests:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["platforms"]["codex"]["skillsDir"] == "~/.agents/skills/clavain"
        assert data["platforms"]["codex"]["installScript"] == "scripts/install-codex-interverse.sh"


def test_interverse_doctor_skips_expected_override_collision(project_root, tmp_path):
    """Doctor should stay quiet when auto-discovery duplicates an explicit override."""
    script = project_root / "scripts" / "install-codex-interverse.sh"
    source_dir = tmp_path / "clavain"
    clone_root = tmp_path / "clones"
    skills_dir = tmp_path / "skills"

    _write_stub_clavain_source(source_dir)

    repo_dir = clone_root / "tool-time"
    (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
    _write_skill(repo_dir / "skills" / "tool-time", "tool-time")
    _write_skill(repo_dir / "skills" / "tool-time-codex", "tool-time")

    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "tool-time").symlink_to(repo_dir / "skills" / "tool-time-codex")

    result = subprocess.run(
        [
            "bash",
            str(script),
            "doctor",
            "--source",
            str(source_dir),
            "--clone-root",
            str(clone_root),
            "--skills-dir",
            str(skills_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ok"
    assert "skipping skill link name collision" not in result.stderr
