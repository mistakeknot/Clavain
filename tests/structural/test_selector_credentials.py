"""Tests for scripts/clavain_selector/credentials.py (mk-42j9.7 Task 5).

Every secret-like literal used below is assembled at runtime (never written
as a single literal), per the convention in test_selector_egress.py. These
tests never open the real ``~/.config/jev/secrets.env``: every path used is
rooted in ``tmp_path``, and the loader test explicitly asserts
``CLAVAIN_JEV_SECRETS_FILE`` points into ``tmp_path`` before calling
``credentials.load()``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from selector_helpers import selector_socket_guard  # noqa: F401

from clavain_selector import credentials


def _key(seed: str) -> str:
    """A deterministic, non-literal key-like string."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]


def _write_secrets(path: Path, content: str, *, mode: int = 0o600) -> None:
    path.write_text(content)
    os.chmod(path, mode)


def test_symlink_refused(tmp_path, monkeypatch):
    real = tmp_path / "real.env"
    _write_secrets(real, f"TYPESAFE_API_KEY={_key('sym-real')}\n")
    link = tmp_path / "secrets.env"
    link.symlink_to(real)
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(link))
    assert credentials.secrets_file_path() == link
    with pytest.raises(credentials.CredentialUnavailable):
        credentials.load()


def test_mode_0644_refused(tmp_path, monkeypatch):
    path = tmp_path / "secrets.env"
    _write_secrets(path, f"TYPESAFE_API_KEY={_key('mode-0644')}\n", mode=0o644)
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    with pytest.raises(credentials.CredentialUnavailable):
        credentials.load()


def test_size_zero_refused(tmp_path, monkeypatch):
    path = tmp_path / "secrets.env"
    _write_secrets(path, "")
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    with pytest.raises(credentials.CredentialUnavailable):
        credentials.load()


def test_size_8193_refused(tmp_path, monkeypatch):
    path = tmp_path / "secrets.env"
    padding = "#" + ("x" * 8190) + "\n"
    assert len(padding) == 8192
    content = padding + "y"
    assert len(content) == 8193
    _write_secrets(path, content)
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    with pytest.raises(credentials.CredentialUnavailable):
        credentials.load()


def test_missing_variable_raises(tmp_path, monkeypatch):
    path = tmp_path / "secrets.env"
    _write_secrets(path, f"SOME_OTHER_VAR={_key('missing-var')}\n")
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    with pytest.raises(credentials.CredentialUnavailable):
        credentials.load()


@pytest.mark.parametrize(
    "template",
    [
        "TYPESAFE_API_KEY={key}\n",
        "export TYPESAFE_API_KEY={key}\n",
        'TYPESAFE_API_KEY="{key}"\n',
        "TYPESAFE_API_KEY='{key}'\n",
    ],
)
def test_key_value_forms_parse(tmp_path, monkeypatch, template):
    key_value = _key(template)
    path = tmp_path / "secrets.env"
    _write_secrets(path, template.format(key=key_value))
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    secret = credentials.load()
    assert secret.reveal() == key_value


def test_dollar_paren_taken_literally(tmp_path, monkeypatch):
    path = tmp_path / "secrets.env"
    literal_value = "$(echo not-expanded)"
    _write_secrets(path, f"TYPESAFE_API_KEY={literal_value}\n")
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    secret = credentials.load()
    assert secret.reveal() == literal_value


def test_repr_is_redacted(tmp_path, monkeypatch):
    key_value = _key("repr-redacted")
    path = tmp_path / "secrets.env"
    _write_secrets(path, f"TYPESAFE_API_KEY={key_value}\n")
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    secret = credentials.load()
    assert repr(secret) == "<redacted>"
    assert str(secret) == "<redacted>"
    assert key_value not in repr(secret)
    assert key_value not in str(secret)


def test_environ_unchanged_after_load(tmp_path, monkeypatch):
    key_value = _key("environ-unchanged")
    path = tmp_path / "secrets.env"
    _write_secrets(path, f"TYPESAFE_API_KEY={key_value}\n")
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    credentials.load()
    assert "TYPESAFE_API_KEY" not in os.environ


def test_secrets_file_path_points_into_tmp_path(tmp_path, monkeypatch):
    path = tmp_path / "secrets.env"
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    resolved = credentials.secrets_file_path()
    assert tmp_path in resolved.parents or resolved == path
    assert str(tmp_path) in str(resolved)


def test_custom_key_var(tmp_path, monkeypatch):
    key_value = _key("custom-key-var")
    path = tmp_path / "secrets.env"
    _write_secrets(path, f"MY_CUSTOM_VAR={key_value}\n")
    monkeypatch.setenv("CLAVAIN_JEV_SECRETS_FILE", str(path))
    monkeypatch.setenv("CLAVAIN_JEV_KEY_VAR", "MY_CUSTOM_VAR")
    secret = credentials.load()
    assert secret.reveal() == key_value
