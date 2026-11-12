"""Namespace qualification stays explicit without losing selector coverage."""
import ast
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
STRUCTURAL = ROOT / "tests/structural"


def namespace_modules(directory):
    required = set()
    for path in directory.glob("test_*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            imported = isinstance(node, ast.ImportFrom) and any(
                name.name == "require_netns" for name in node.names
            )
            argument = isinstance(node, ast.arg) and node.arg == "require_netns"
            marked = (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "usefixtures"
                and any(isinstance(arg, ast.Constant) and arg.value == "require_netns" for arg in node.args)
            )
            if imported or argument or marked:
                required.add(path.name)
    return required


def default_ignored():
    tree = ast.parse((STRUCTURAL / "conftest.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "collect_ignore"
            for target in node.targets
        ):
            return set(ast.literal_eval(node.value))
    return set()


def runner_modules():
    script = (ROOT / "scripts/qualify-support-adapter.sh").read_text()
    return {
        Path(word).name
        for word in shlex.split(script.replace("\\\n", " "), comments=True)
        if word.startswith("tests/structural/") and word.endswith(".py")
    }


def test_namespace_modules_have_both_explicit_runner_and_default_exclusion():
    required = namespace_modules(STRUCTURAL)
    assert required, "namespace qualification inventory must not be empty"
    assert default_ignored() == required, "every namespace module must be excluded, and no ordinary module may be excluded"
    assert runner_modules() == required, "every namespace module must run through the qualification runner"


def test_namespace_inventory_finds_new_fixture_usage(tmp_path):
    (tmp_path / "test_imported.py").write_text("from support_helpers import require_netns\n")
    (tmp_path / "test_argument.py").write_text("def test_example(require_netns): pass\n")
    (tmp_path / "test_marked.py").write_text('pytestmark = pytest.mark.usefixtures("require_netns")\n')
    (tmp_path / "test_ordinary.py").write_text('def test_example(): assert "require_netns"\n')
    assert namespace_modules(tmp_path) == {"test_imported.py", "test_argument.py", "test_marked.py"}


def collect(*paths):
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--tb=short", "--collect-only", "-q", *paths],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return {Path(line.split("::", 1)[0]).name for line in result.stdout.splitlines() if "::" in line}


def test_default_collection_keeps_every_non_namespace_selector_module():
    collected = collect("tests/structural")
    selectors = {path.name for path in STRUCTURAL.glob("test_selector*.py")}
    required = namespace_modules(STRUCTURAL)
    assert collected.isdisjoint(required)
    assert selectors - required <= collected


def test_explicit_qualification_modules_still_collect():
    names = runner_modules()
    assert collect(*(str(STRUCTURAL / name) for name in sorted(names))) == names


def test_runner_fails_when_unshare_is_missing(tmp_path):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "dirname").symlink_to(shutil.which("dirname"))
    called = tmp_path / "python-called"
    python = binaries / "python3"
    python.write_text(f"#!/bin/sh\nprintf called > {shlex.quote(str(called))}\nexit 0\n")
    python.chmod(0o755)
    env = {"PATH": str(binaries), "HOME": str(tmp_path), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts/qualify-support-adapter.sh")],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 127
    assert "unshare" in result.stderr
    assert not called.exists()
