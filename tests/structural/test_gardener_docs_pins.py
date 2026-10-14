"""skills/gardener/scripts/docs-pins.py: drift is a warning and docs are never rewritten."""
import json
import subprocess

import pytest


@pytest.fixture
def run(project_root):
    script = project_root / "skills/gardener/scripts/docs-pins.py"

    def go(root, *args):
        return subprocess.run(["python3", "-I", str(script), "--root", str(root), *args],
                              capture_output=True, text=True, timeout=30)
    return go


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"react": "^18.3.1", "@scope/kit": "~2.4.0"},
        "devDependencies": {"vitest": "workspace:*"},
    }))
    (tmp_path / "go.mod").write_text(
        "module example.com/app\n\ngo 1.25.0\n\nrequire (\n\tgithub.com/spf13/cobra v1.9.1\n)\n")
    return tmp_path


def test_matching_docs_report_nothing(run, repo):
    (repo / "AGENTS.md").write_text("Uses React 18.3.1 and `@scope/kit` 2.4.0, Go 1.25, cobra v1.9.1.\n"
                                    "vitest 9.9.9 is a workspace link, not a pin.\n")
    result = run(repo, "--strict")
    assert result.returncode == 0, result.stdout
    assert "0 drift warning" in result.stdout


def test_drift_is_a_warning_not_a_failure(run, repo):
    (repo / "README.md").write_text("Built on react 17.0.2 with Go 1.24 and cobra@1.8.0.\n")
    before = (repo / "README.md").read_text()
    result = run(repo)
    assert result.returncode == 0
    assert "WARNING README.md:1: react documented as 17.0.2" in result.stdout
    assert "Go documented as 1.24" in result.stdout
    assert "cobra documented as 1.8.0" in result.stdout
    assert (repo / "README.md").read_text() == before  # pinned text stays intact


def test_strict_fails_on_drift(run, repo):
    (repo / "AGENTS.md").write_text("react 17.0.2\n")
    assert run(repo, "--strict").returncode == 1


def test_json_output(run, repo):
    (repo / "AGENTS.md").write_text("line one\nreact 17.0.2\n")
    drift = json.loads(run(repo, "--json").stdout)["drift"]
    assert drift == [{"doc": "AGENTS.md", "line": 2, "name": "react",
                      "documented": "17.0.2", "pinned": ["18.3.1"]}]


def test_nested_manifest_uses_its_own_readme(run, repo):
    pkg = repo / "packages" / "web"
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text(json.dumps({"dependencies": {"left-pad": "1.3.0"}}))
    (pkg / "README.md").write_text("left-pad 1.2.0\n")
    assert "packages/web/README.md:1: left-pad documented as 1.2.0" in run(repo).stdout


def test_node_modules_are_skipped(run, repo):
    junk = repo / "node_modules" / "x"
    junk.mkdir(parents=True)
    (junk / "package.json").write_text(json.dumps({"dependencies": {"zed": "1.0.0"}}))
    (junk / "README.md").write_text("zed 2.0.0\n")
    assert "0 drift warning" in run(repo).stdout


def test_runs_clean_on_this_repo(run, project_root):
    assert run(project_root).returncode == 0


def test_missing_root_is_usage_error(run, tmp_path):
    assert run(tmp_path / "nope").returncode == 2
