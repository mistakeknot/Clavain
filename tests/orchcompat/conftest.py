"""Collection rules for the orchestration characterization tests.

Tests marked `requires_ic` need the real `ic` binary. Without it they are
deselected and the deselection is announced in the run header, so a missing
binary can never read as a pass. The fleet-reader tests need `yq` (and the
dispatch tests need `jq`); without `yq` they are skipped and the skip is
announced the same way.

`--orchcompat-require-ic` is the strict gate: it turns a missing `ic`, `yq` or
`jq` into a hard error instead of a deselection or skip. Use it wherever the
golden is the gate.
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchlib  # noqa: E402

_HERE = Path(__file__).resolve().parent
_deselected = []


def pytest_addoption(parser):
    parser.addoption("--orchcompat-require-ic", action="store_true", default=False,
                     help="strict gate: fail instead of deselect/skip when `ic`, `yq` or `jq` is missing")


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_ic: needs the real `ic` binary")


def _missing_tools():
    return [t for t in ("yq", "jq") if shutil.which(t) is None]


def pytest_collection_modifyitems(config, items):
    if config.getoption("--orchcompat-require-ic"):
        missing = _missing_tools()
        if missing:
            raise pytest.UsageError(
                "orchcompat strict gate: required tool(s) not on PATH: " + ", ".join(missing))
    if orchlib.real_ic():
        return
    if config.getoption("--orchcompat-require-ic"):
        raise pytest.UsageError("orchcompat: `ic` not found (set ORCHCOMPAT_IC or put it on PATH)")
    keep = []
    for item in items:
        if _HERE in Path(str(item.fspath)).parents and "requires_ic" in item.keywords:
            _deselected.append(item.nodeid)
        else:
            keep.append(item)
    if _deselected:
        config.hook.pytest_deselected(items=[i for i in items if i.nodeid in _deselected])
        items[:] = keep


def pytest_report_header(config):
    ic = orchlib.real_ic()
    missing = _missing_tools()
    note = f"; MISSING {', '.join(missing)} (dependent tests skipped or failing)" if missing else ""
    return f"orchcompat: ic={ic or 'NOT FOUND (requires_ic tests will be deselected)'}{note}"


def pytest_terminal_summary(terminalreporter):
    if _deselected:
        terminalreporter.write_line(
            f"orchcompat: DESELECTED {len(_deselected)} requires_ic test(s): `ic` not found",
            yellow=True)


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h
