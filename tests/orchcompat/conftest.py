"""Collection rules for the orchestration characterization tests.

Tests marked `requires_ic` need the real `ic` binary. Without it they are
deselected and the deselection is announced in the run header, so a missing
binary can never read as a pass. `--orchcompat-require-ic` turns the missing
binary into a hard error (use it wherever the golden is the gate).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchlib  # noqa: E402

_HERE = Path(__file__).resolve().parent
_deselected = []


def pytest_addoption(parser):
    parser.addoption("--orchcompat-require-ic", action="store_true", default=False,
                     help="fail instead of deselect when the real `ic` is missing")


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_ic: needs the real `ic` binary")


def pytest_collection_modifyitems(config, items):
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
    return f"orchcompat: ic={ic or 'NOT FOUND (requires_ic tests will be deselected)'}"


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
