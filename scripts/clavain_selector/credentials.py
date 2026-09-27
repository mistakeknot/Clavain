"""Credential loader for the Jev client (mk-42j9.7 Task 5).

Implements the plan's Jev client bullet on credentials: open
``~/.config/jev/secrets.env`` (override ``CLAVAIN_JEV_SECRETS_FILE``) with
``O_RDONLY|O_NOFOLLOW``; ``fstat`` must show a regular file owned by the
effective uid, mode with no group/other bits, size 1..8192. Parse
``KEY=value``, ``export KEY=value``, single- or double-quoted values;
comments and blank lines are ignored; there is no shell expansion. Extract
only the variable named by ``CLAVAIN_JEV_KEY_VAR`` (default
``TYPESAFE_API_KEY``). Returns a ``SecretStr``-style wrapper whose
``repr``/``str`` are ``"<redacted>"``.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SECRETS_FILE = "~/.config/jev/secrets.env"
DEFAULT_KEY_VAR = "TYPESAFE_API_KEY"

_MIN_SIZE = 1
_MAX_SIZE = 8192

_LINE_RE = re.compile(r'^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=(.*)$')


class CredentialUnavailable(Exception):
    """The Jev API key could not be loaded (row 8 of the fallback table).

    Covers a missing secrets file, a symlink, an owner/mode/size that fails
    the checks above, and a secrets file that parses but does not define the
    requested variable.
    """


@dataclass(frozen=True)
class SecretStr:
    """A credential value that never prints itself.

    ``repr()`` and ``str()`` are always ``"<redacted>"`` -- including when a
    ``SecretStr`` is embedded in another object's repr, an exception message
    built with an f-string, or a log/assert failure line -- so the loaded
    key cannot leak through an accidental print, log or traceback. Use
    ``reveal()`` to get the actual value, only at the point it must be sent
    (the ``Authorization`` header).
    """

    _value: str

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:  # noqa: D105 - intentionally uninformative
        return "<redacted>"

    def __str__(self) -> str:  # noqa: D105 - intentionally uninformative
        return "<redacted>"


def secrets_file_path() -> Path:
    override = os.environ.get("CLAVAIN_JEV_SECRETS_FILE")
    raw = override if override else DEFAULT_SECRETS_FILE
    return Path(raw).expanduser()


def key_var_name() -> str:
    return os.environ.get("CLAVAIN_JEV_KEY_VAR") or DEFAULT_KEY_VAR


def _parse_value(raw: str) -> str:
    """Strip surrounding whitespace, then a single matching quote pair.

    No shell expansion of any kind: a literal ``$(...)`` or ``${...}`` in the
    value is returned exactly as written.
    """
    stripped = raw.strip()
    if len(stripped) >= 2 and stripped[0] in ("'", '"'):
        quote = stripped[0]
        end = stripped.find(quote, 1)
        if end != -1:
            return stripped[1:end]
    return stripped


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        key, raw_value = match.group(1), match.group(2)
        values[key] = _parse_value(raw_value)
    return values


def _open_and_check(path: Path) -> bytes:
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise CredentialUnavailable(f"could not open secrets file {path}: {exc}") from exc
    try:
        try:
            st = os.fstat(fd)
        except OSError as exc:
            raise CredentialUnavailable(f"could not stat secrets file {path}: {exc}") from exc

        if not stat.S_ISREG(st.st_mode):
            raise CredentialUnavailable(f"secrets file {path} is not a regular file")
        if st.st_uid != os.geteuid():
            raise CredentialUnavailable(f"secrets file {path} is not owned by the effective uid")
        if stat.S_IMODE(st.st_mode) & (stat.S_IRWXG | stat.S_IRWXO):
            raise CredentialUnavailable(f"secrets file {path} has group or other permission bits set")
        if not (_MIN_SIZE <= st.st_size <= _MAX_SIZE):
            raise CredentialUnavailable(
                f"secrets file {path} has size {st.st_size}, expected {_MIN_SIZE}..{_MAX_SIZE}"
            )

        data = b""
        remaining = st.st_size
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            data += chunk
            remaining -= len(chunk)
        return data
    finally:
        os.close(fd)


def load(*, path: Path | None = None, key_var: str | None = None) -> SecretStr:
    """Load the Jev API key, raising ``CredentialUnavailable`` on any failure.

    Never mutates ``os.environ``: the secrets file is parsed independently
    and only the requested variable's value is returned.
    """
    file_path = path if path is not None else secrets_file_path()
    var_name = key_var if key_var is not None else key_var_name()

    data = _open_and_check(file_path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialUnavailable(f"secrets file {file_path} is not valid UTF-8: {exc}") from exc

    values = _parse_env(text)
    if var_name not in values:
        raise CredentialUnavailable(f"variable {var_name!r} is not defined in {file_path}")
    return SecretStr(values[var_name])
