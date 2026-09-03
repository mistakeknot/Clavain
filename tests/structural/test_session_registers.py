"""No hook, command, script, skill or agent keys anything on CLAUDE_SESSION_ID alone.

mk-hxgi found the next-goal receipts keyed on ``CLAUDE_SESSION_ID``, a variable
that exists only after ``hooks/session-start.sh`` wrote it into
``CLAUDE_ENV_FILE``. Claude Code itself exports ``CLAUDE_CODE_SESSION_ID`` into
the Bash tool and hands every hook its ``session_id`` on stdin. A reader that
consults the first register alone degrades to "unknown" in every session whose
start hook did not fire, and "unknown" is a value the claim logic treats as
unclaimed (mk-rd9f).

Accepted forms for a read of the variable:

* the canonical shell chain ``${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-…}}``
  (any innermost fallback, including a further ``${CODEX_SESSION_ID:-…}``);
* the jq chain ``env.CLAUDE_SESSION_ID // env.CLAUDE_CODE_SESSION_ID``;
* an assignment or export, ``CLAUDE_SESSION_ID=…`` (the writer in session-start.sh);
* the helper's own definition in ``hooks/lib.sh``;
* in Go (``cmd/``), only ``sessionRegisterID()`` in ``cmd/clavain-cli/sideband.go``
  may call ``os.Getenv``/``os.LookupEnv`` on either register — every other site
  calls the helper;
* in Python, ``os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID")``
  (the ``os.environ[...]`` and ``os.getenv`` spellings are reads too).

Lines that name the variable without reading it (comments, prose) are not reads.
Hooks holding their stdin payload should prefer ``clavain_session_id "$INPUT"``,
which this test does not enforce: the chain is the floor, the helper is the
better habit.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCANNED_DIRS = ("hooks", "scripts", "commands", "skills", "agents", "cmd")
SCANNED_SUFFIXES = {".sh", ".md", ".py", ".json", ".bash", ".go"}

# A read: the variable dereferenced in shell, jq, Python or Go.
READ = re.compile(
    r"\$\{?CLAUDE_SESSION_ID\b"
    r"|env\.CLAUDE_SESSION_ID\b"
    r"|os\.environ(?:\.get)?\(?\[?[\"']CLAUDE_SESSION_ID[\"']"
    r"|os\.getenv\([\"']CLAUDE_SESSION_ID[\"']"
    r"|os\.(?:Getenv|LookupEnv)\(\"CLAUDE_SESSION_ID\"\)"
)

ACCEPTED = (
    re.compile(r"\$\{CLAUDE_SESSION_ID:-\$\{CLAUDE_CODE_SESSION_ID:-"),
    re.compile(r"env\.CLAUDE_SESSION_ID\s*//\s*env\.CLAUDE_CODE_SESSION_ID"),
    re.compile(r"os\.environ(?:\.get)?\(?\[?[\"']CLAUDE_SESSION_ID[\"']\)?\]?\s*or\s*os\.environ(?:\.get)?\(?\[?[\"']CLAUDE_CODE_SESSION_ID"),
)
ASSIGNMENT = re.compile(r"(^|[^$\w])CLAUDE_SESSION_ID=")

HELPER_FILE = ROOT / "hooks" / "lib.sh"
HELPER_NAME = "clavain_session_id"
GO_HELPER_FILE = ROOT / "cmd" / "clavain-cli" / "sideband.go"
GO_HELPER_NAME = "sessionRegisterID"
GO_READ = re.compile(r"os\.(?:Getenv|LookupEnv)\(\"CLAUDE_(?:CODE_)?SESSION_ID\"\)")


def _scanned_files():
    for d in SCANNED_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in SCANNED_SUFFIXES:
                yield path


def _helper_body_lines():
    """Line numbers (1-based) inside the helper's definition in hooks/lib.sh."""
    lines = HELPER_FILE.read_text(encoding="utf-8").splitlines()
    inside = False
    for n, line in enumerate(lines, 1):
        if line.startswith(f"{HELPER_NAME}() {{"):
            inside = True
        if inside:
            yield n
            if line.rstrip() == "}":
                return


def _go_helper_body_lines():
    """Line numbers (1-based) inside sessionRegisterID() in sideband.go."""
    if not GO_HELPER_FILE.is_file():
        return
    lines = GO_HELPER_FILE.read_text(encoding="utf-8").splitlines()
    inside = False
    for n, line in enumerate(lines, 1):
        if line.startswith(f"func {GO_HELPER_NAME}("):
            inside = True
        if inside:
            yield n
            if line.rstrip() == "}":
                return


def _bare_reads():
    helper_lines = set(_helper_body_lines())
    go_helper_lines = set(_go_helper_body_lines())
    for path in _scanned_files():
        rel = path.relative_to(ROOT)
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if path.suffix == ".go":
                # Go: any direct read of either register outside the helper is bare,
                # including CLAUDE_CODE_SESSION_ID, so a second chain cannot drift.
                if GO_READ.search(line) and not (path == GO_HELPER_FILE and n in go_helper_lines):
                    if not line.lstrip().startswith("//"):
                        yield f"{rel}:{n}: {line.strip()}"
                continue
            if not READ.search(line):
                continue
            if any(p.search(line) for p in ACCEPTED):
                continue
            if path == HELPER_FILE and n in helper_lines:
                continue
            # An assignment on a line that also reads the variable is still a read.
            if ASSIGNMENT.search(line) and not READ.search(ASSIGNMENT.sub("", line)):
                continue
            yield f"{rel}:{n}: {line.strip()}"


def test_no_bare_session_id_reader():
    offenders = list(_bare_reads())
    assert not offenders, (
        "These lines read CLAUDE_SESSION_ID without falling back to "
        "CLAUDE_CODE_SESSION_ID. Use ${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-<fallback>}}, "
        "the jq form env.CLAUDE_SESSION_ID // env.CLAUDE_CODE_SESSION_ID // <fallback>, "
        'or clavain_session_id "$INPUT" from hooks/lib.sh when the hook holds its stdin:\n  '
        + "\n  ".join(offenders)
    )


def test_helper_is_defined_in_lib():
    text = HELPER_FILE.read_text(encoding="utf-8")
    assert f"{HELPER_NAME}() {{" in text, f"hooks/lib.sh must define {HELPER_NAME}()"
    body = text.split(f"{HELPER_NAME}() {{", 1)[1].split("\n}", 1)[0]
    assert ".session_id" in body, "the helper must read the hook payload's session_id first"
    assert "${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-" in body, (
        "the helper must fall back through both env registers"
    )


def test_go_helper_is_defined():
    text = GO_HELPER_FILE.read_text(encoding="utf-8")
    assert f"func {GO_HELPER_NAME}() string" in text, f"sideband.go must define {GO_HELPER_NAME}()"
    body = text.split(f"func {GO_HELPER_NAME}(", 1)[1].split("\n}", 1)[0]
    assert 'os.Getenv("CLAUDE_SESSION_ID")' in body and 'os.Getenv("CLAUDE_CODE_SESSION_ID")' in body, (
        "the Go helper must read both registers, in that order"
    )


@pytest.mark.parametrize(
    "line,accepted",
    [
        ('SID="${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-unknown}}"', True),
        ('SID="${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-${CODEX_SESSION_ID:-unknown}}}"', True),
        ("session_id:(env.CLAUDE_SESSION_ID // env.CLAUDE_CODE_SESSION_ID // \"unknown\")", True),
        ('echo "export CLAUDE_SESSION_ID=${_session_id}" >> "$CLAUDE_ENV_FILE"', True),
        ("# defaults to CLAUDE_SESSION_ID", True),
        ('SID="${CLAUDE_SESSION_ID:-unknown}"', False),
        ('SID="$CLAUDE_SESSION_ID"', False),
        ("session_id:(env.CLAUDE_SESSION_ID // \"unknown\")", False),
        ('CLAUDE_SESSION_ID="$CLAUDE_SESSION_ID"', False),
        ('sid = os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID") or "unknown"', True),
        ('sid = os.environ.get("CLAUDE_SESSION_ID", "unknown")', False),
        ("sid = os.environ['CLAUDE_SESSION_ID']", False),
        ('sid = os.getenv("CLAUDE_SESSION_ID")', False),
    ],
)
def test_classifier_examples(line, accepted):
    """The rule itself, pinned on examples, so a regex edit cannot loosen it silently."""
    is_read = bool(READ.search(line))
    ok = (
        not is_read
        or any(p.search(line) for p in ACCEPTED)
        or (ASSIGNMENT.search(line) is not None and not READ.search(ASSIGNMENT.sub("", line)))
    )
    assert ok == accepted, f"{line!r}: expected accepted={accepted}, got {ok}"
