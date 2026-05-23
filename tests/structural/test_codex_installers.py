"""Structural checks for Codex installer manifests and shell wrappers."""

from __future__ import annotations

import json
import os
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
    # Monorepo example manifest — only exists in full Sylveste checkout, not standalone CI
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
        env={
            **os.environ,
            "CODEX_HOME": str(tmp_path / "codex"),
            "CODEX_PROMPTS_DIR": str(tmp_path / "codex" / "prompts"),
        },
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ok"
    assert "skipping skill link name collision" not in result.stderr


def test_interflux_codex_skill_links_use_engine_frontmatter_names(project_root, tmp_path):
    """Interflux Codex links should follow current SKILL.md names, not stale paths."""
    script = project_root / "scripts" / "install-codex-interverse.sh"
    source_dir = tmp_path / "clavain"
    clone_root = tmp_path / "clones"
    skills_dir = tmp_path / "skills"

    _write_stub_clavain_source(source_dir)
    (source_dir / "agent-rig.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "recommended": [
                        {"source": "interflux@interagency-marketplace"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    repo_dir = clone_root / "interflux"
    (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
    _write_skill(repo_dir / "skills" / "flux-drive", "flux-engine")
    _write_skill(repo_dir / "skills" / "flux-review", "flux-review-engine")

    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "flux-engine").symlink_to(repo_dir / "skills" / "flux-drive")
    (skills_dir / "flux-review-engine").symlink_to(repo_dir / "skills" / "flux-review")

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
            "--no-prompts",
            "--json",
        ],
        capture_output=True,
        env={
            **os.environ,
            "CODEX_HOME": str(tmp_path / "codex"),
            "CODEX_PROMPTS_DIR": str(tmp_path / "codex" / "prompts"),
        },
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "ok"

    companions = data["interverse_companions"]["companions"]
    interflux_links = {
        companion["link_name"]: companion["skill_path"]
        for companion in companions
        if companion["plugin"] == "interflux"
    }
    assert interflux_links == {
        "flux-engine": str(repo_dir / "skills" / "flux-drive"),
        "flux-review-engine": str(repo_dir / "skills" / "flux-review"),
    }


def test_interverse_codex_doctor_filters_companions_by_profile(project_root, tmp_path):
    """Default Codex profile should stay small; optional profiles are explicit."""
    script = project_root / "scripts" / "install-codex-interverse.sh"
    source_dir = tmp_path / "clavain"
    clone_root = tmp_path / "clones"
    skills_dir = tmp_path / "skills"

    _write_stub_clavain_source(source_dir)
    (source_dir / "agent-rig.json").write_text(
        json.dumps(
            {
                "plugins": {
                    "recommended": [
                        {"source": "interphase@interagency-marketplace"},
                        {"source": "interflux@interagency-marketplace"},
                    ],
                    "profiles": {
                        "default": ["interphase@interagency-marketplace"],
                        "review": ["interflux@interagency-marketplace"],
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    interphase = clone_root / "interphase"
    (interphase / ".git").mkdir(parents=True, exist_ok=True)
    _write_skill(interphase / "skills" / "beads-workflow", "beads-workflow")

    interflux = clone_root / "interflux"
    (interflux / ".git").mkdir(parents=True, exist_ok=True)
    _write_skill(interflux / "skills" / "flux-drive", "flux-engine")

    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "beads-workflow").symlink_to(interphase / "skills" / "beads-workflow")
    (skills_dir / "flux-engine").symlink_to(interflux / "skills" / "flux-drive")

    env = {
        **os.environ,
        "CODEX_HOME": str(tmp_path / "codex"),
        "CODEX_PROMPTS_DIR": str(tmp_path / "codex" / "prompts"),
    }

    default_result = subprocess.run(
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
            "--profile",
            "default",
            "--no-prompts",
            "--json",
        ],
        capture_output=True,
        env=env,
        text=True,
        timeout=20,
        check=False,
    )

    assert default_result.returncode == 0, default_result.stderr
    default_data = json.loads(default_result.stdout)
    assert default_data["interverse_companions"]["profile"] == "default"
    assert [plugin["name"] for plugin in default_data["interverse_companions"]["selected_plugins"]] == ["interphase"]

    review_result = subprocess.run(
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
            "--profile",
            "review",
            "--no-prompts",
            "--json",
        ],
        capture_output=True,
        env=env,
        text=True,
        timeout=20,
        check=False,
    )

    assert review_result.returncode == 0, review_result.stderr
    review_data = json.loads(review_result.stdout)
    assert review_data["interverse_companions"]["profile"] == "review"
    assert [plugin["name"] for plugin in review_data["interverse_companions"]["selected_plugins"]] == ["interflux"]


def test_claude_modpack_uses_default_profile_with_optional_packs(project_root, tmp_path):
    """Claude Code modpack install should not install the full recommended set by default."""
    script = project_root / "scripts" / "modpack-install.sh"
    env = {**os.environ, "HOME": str(tmp_path)}

    default_result = subprocess.run(
        ["bash", str(script), "--dry-run", "--quiet"],
        capture_output=True,
        env=env,
        text=True,
        timeout=20,
        check=False,
    )

    assert default_result.returncode == 0, default_result.stderr
    default_data = json.loads(default_result.stdout)
    assert "interphase@interagency-marketplace" in default_data["would_install"]
    assert "interflux@interagency-marketplace" not in default_data["would_install"]

    review_result = subprocess.run(
        ["bash", str(script), "--dry-run", "--quiet", "--profile=review"],
        capture_output=True,
        env=env,
        text=True,
        timeout=20,
        check=False,
    )

    assert review_result.returncode == 0, review_result.stderr
    review_data = json.loads(review_result.stdout)
    assert "interflux@interagency-marketplace" in review_data["would_install"]


def test_codex_update_checker_fallback_excludes_archived_intersense(project_root):
    """Jq-less fallback companion checks should not resurrect archived plugins."""
    script = (project_root / "scripts" / "check-install-updates.sh").read_text(encoding="utf-8")
    fallback = script.split("cat <<'EOF'", 1)[1].split("EOF", 1)[0]

    assert "intersense" not in fallback
