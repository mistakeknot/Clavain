import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_post_bump_updates_prd_to_target_version(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs").mkdir()
    shutil.copy2(ROOT / "scripts" / "post-bump.sh", tmp_path / "scripts" / "post-bump.sh")
    prd = tmp_path / "docs" / "PRD.md"
    prd.write_text("# Test\n\n**Version:** 0.1.0\n", encoding="utf-8")

    subprocess.run(
        ["bash", str(tmp_path / "scripts" / "post-bump.sh"), "0.1.1"],
        cwd=tmp_path.parent,
        check=True,
    )

    assert "**Version:** 0.1.1" in prd.read_text(encoding="utf-8")
