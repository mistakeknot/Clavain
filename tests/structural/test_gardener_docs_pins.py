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
                      "documented": "17.0.2", "pinned": ["^18.3.1"],
                      "manifests": ["package.json"]}]


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


def test_runs_on_this_repo_and_reports_json(run, project_root):
    result = run(project_root, "--json")
    assert result.returncode == 0  # drift is a warning by default
    report = json.loads(result.stdout)
    assert isinstance(report["drift"], list) and isinstance(report["skipped"], list)


def drift(run, root):
    return json.loads(run(root, "--json").stdout)["drift"]


def test_root_docs_check_nested_manifests_with_or_without_root_manifest(run, tmp_path):
    web = tmp_path / "packages" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text(json.dumps({"dependencies": {"react": "18.3.1"}}))
    (tmp_path / "README.md").write_text("react 17.0.2\n")
    assert [d["doc"] for d in drift(run, tmp_path)] == ["README.md"]
    (tmp_path / "package.json").write_text(json.dumps({"name": "root"}))
    assert [d["doc"] for d in drift(run, tmp_path)] == ["README.md"]


@pytest.mark.parametrize("line", ["React 17.0.2", "react `17.0.2`", "**React** 17.0.2", "REACT@17.0.2",
                                  "react: 17.0.2", "React.js 17.0.2"])
def test_spelling_variants_are_checked(run, tmp_path, line):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18.3.1"}}))
    (tmp_path / "AGENTS.md").write_text(line + "\n")
    assert len(drift(run, tmp_path)) == 1


def test_matching_spelling_variants_are_clean(run, tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18.3.1"}}))
    (tmp_path / "AGENTS.md").write_text("React 18.3.1\nreact `18.3.1`\n**React** 18\n")
    assert drift(run, tmp_path) == []


@pytest.mark.parametrize("spec,documented,warns", [
    ("!=1.2.*", "1.2.3", True),
    ("!=1.2.*", "2.0.0", False),
    (">=1.0.0,!=1.0.0", "1.0.0", True),
    (">=1.0.0,!=1.0.0", "1.0.1", False),
    (">18.0.0", "18.0.0", True),
    (">18.0.0", "18.0.1", False),
    ("==2.0.*", "2.0.7", False),
    ("==2.0.*", "2.1.0", True),
    ("*", "9.9.9", False),
    (">=18.0.0 <20.0.0", "19.0.0", False),
    (">=18.0.0 <20.0.0", "20.1.0", True),
    ("18.x", "18.2", False),
    ("18.x", "17.0.2", True),
    ("^1 || ^3", "3.2.0", False),
    ("^1 || ^3", "2.0.0", True),
    ("^0.2.3", "0.2.9", False),
    ("^0.2.3", "0.3.0", True),
    ("~1.4.5", "1.4.9", False),
    ("~1.4.5", "1.5.0", True),
    ("^18.3.1", "18", False),
    ("^18.3.1", "18.2", True),
])
def test_npm_constraints(run, tmp_path, spec, documented, warns):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"lib": spec}}))
    (tmp_path / "AGENTS.md").write_text(f"lib {documented}\n")
    assert bool(drift(run, tmp_path)) is warns


def test_python_markers_urls_and_ranges(run, tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = [\n'
        '  "requests; python_version >= \'3.11\'",\n'
        '  "pkg @ https://example.com/pkg-2.32.3.tar.gz",\n'
        '  "wide>=1.0,<3",\n  "compat~=1.4.2",\n]\n')
    (tmp_path / "AGENTS.md").write_text("requests 3.11\npkg 2.32.3\nwide 2.5\ncompat 1.4.9\ncompat 1.5\n")
    report = json.loads(run(tmp_path, "--json").stdout)
    assert [(d["name"], d["documented"]) for d in report["drift"]] == [("compat", "1.5")]
    assert any(note.startswith("pkg") or " pkg " in note for note in report["skipped"])


def test_go_single_line_tab_directives_and_replace(run, tmp_path):
    (tmp_path / "go.mod").write_text(
        "module example.com/app\n\ngo\t1.25.0\n\nrequire github.com/spf13/cobra v1.8.0\n"
        "require\tgithub.com/other/lib v1.0.0\n"
        "replace github.com/spf13/cobra => github.com/spf13/cobra v1.9.1\n"
        "replace github.com/other/lib => ../lib\n")
    (tmp_path / "AGENTS.md").write_text("Go 1.25, cobra 1.9.1, lib 9.9.9\ncobra 1.8.0\n")
    report = json.loads(run(tmp_path, "--json").stdout)
    assert [(d["line"], d["name"]) for d in report["drift"]] == [(2, "cobra")]
    assert any("replaced by a local path" in n for n in report["skipped"])


def test_bare_major_exception_binds_to_the_match(run, tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18.3.1"}}))
    (tmp_path / "AGENTS.md").write_text("react 2 times; contact team@example.com\nreact@17\nreact@18\n")
    assert [d["line"] for d in drift(run, tmp_path)] == [2]  # react@18 matches 18.3.1 by prefix


@pytest.mark.parametrize("manifest_spec,line", [
    ("19.0.0-rc.1", "react 19.0.0-rc.1"),
    ("19.0.0", "react 19.0.0-rc.1"),
    ("1.2.3 - 2.3.4", "react 2.0.0"),
    ("owner/repo#v1.2.3", "react 1.2.3"),
])
def test_prereleases_and_unsupported_specs_are_noted_not_guessed(run, tmp_path, manifest_spec, line):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": manifest_spec}}))
    (tmp_path / "AGENTS.md").write_text(line + "\n")
    result = run(tmp_path, "--json", "--strict")
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)["drift"] == []


@pytest.mark.parametrize("quoted,disagrees", [("17.0.2", "packages/api/package.json"),
                                              ("18.3.1", "packages/web/package.json")])
def test_root_doc_flags_a_disagreeing_nested_manifest(run, tmp_path, quoted, disagrees):
    for sub, version in (("web", "17.0.2"), ("api", "18.3.1")):
        (tmp_path / "packages" / sub).mkdir(parents=True)
        (tmp_path / "packages" / sub / "package.json").write_text(
            json.dumps({"dependencies": {"react": version}}))
    (tmp_path / "README.md").write_text(f"react {quoted}\n")
    result = run(tmp_path, "--json", "--strict")
    assert result.returncode == 1
    (found,) = json.loads(result.stdout)["drift"]
    assert found["manifests"] == [disagrees]


def test_prerelease_in_docs_is_not_read_as_its_release(run, tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18.3.1"}}))
    (tmp_path / "AGENTS.md").write_text("react 19.0.0-rc.1 is being trialled\n")
    assert drift(run, tmp_path) == []


def test_nearest_manifest_wins_for_nested_docs(run, tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18.3.1"}}))
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text(json.dumps({"dependencies": {"react": "17.0.2"}}))
    (web / "README.md").write_text("react 17.0.2\n")
    assert drift(run, tmp_path) == []


def test_go_replacements_are_per_source_version(run, tmp_path):
    (tmp_path / "go.mod").write_text(
        "module example.com/app\n\ngo 1.25.0\n\nrequire example.com/lib v1.0.0\n"
        "replace example.com/lib v1.0.0 => example.com/lib v1.1.0\n"
        "replace example.com/lib v2.0.0 => example.com/lib v2.1.0\n")
    (tmp_path / "AGENTS.md").write_text("lib 1.1.0\nlib 1.0.0\n")
    assert [d["line"] for d in drift(run, tmp_path)] == [2]


@pytest.mark.parametrize("content", ["[]", "null", '{"dependencies": ["react"]}', '{"dependencies": 3}'])
def test_odd_manifest_shapes_are_notes(run, tmp_path, content):
    (tmp_path / "package.json").write_text(content)
    (tmp_path / "AGENTS.md").write_text("react 17.0.2\n")
    result = run(tmp_path, "--strict")
    assert result.returncode == 0, result.stderr
    assert "package.json: unreadable" in result.stdout


def test_unreadable_manifest_is_a_note(run, tmp_path):
    (tmp_path / "package.json").write_text("{not json")
    (tmp_path / "AGENTS.md").write_text("react 17.0.2\n")
    result = run(tmp_path, "--strict")
    assert result.returncode == 0
    assert "package.json: unreadable" in result.stdout


def test_missing_root_is_usage_error(run, tmp_path):
    assert run(tmp_path / "nope").returncode == 2
