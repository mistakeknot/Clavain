"""Catalog freshness check for generated component metadata."""

import subprocess


def test_catalog_is_fresh(project_root):
    """gen-catalog --check should pass when catalog/docs counts are up to date."""
    result = subprocess.run(
        ["python3", "scripts/gen-catalog.py", "--check"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        "Catalog drift detected. Run `python3 scripts/gen-catalog.py` to refresh.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
