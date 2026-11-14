"""Shared integrity and filesystem checks for one-use round decisions."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import pwd
import stat
from datetime import datetime


class DecisionRefused(ValueError):
    """A readable decision is unsafe, inapplicable, or already consumed."""


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value)


def validate(data):
    fields = {"schema_version", "decision_id", "bead", "head", "accepted_failures",
              "authority", "ruling", "decided_at", "mac"}
    if not isinstance(data, dict) or set(data) != fields:
        raise DecisionRefused("invalid decision fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise DecisionRefused("unsupported decision schema")
    if not identifier(data["bead"]) or not identifier(data["decision_id"]):
        raise DecisionRefused("invalid decision identity")
    if not isinstance(data["head"], str) or not re.fullmatch(r"[0-9a-f]{40}", data["head"]):
        raise DecisionRefused("invalid decision head")
    if type(data["accepted_failures"]) is not int or data["accepted_failures"] < 3:
        raise DecisionRefused("invalid accepted failure count")
    if data["authority"] != "vizier":
        raise DecisionRefused("decision authority must be vizier")
    for field in ("ruling", "decided_at"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise DecisionRefused("missing decision procedure fields")
    try:
        if datetime.fromisoformat(data["decided_at"]).utcoffset() is None:
            raise ValueError()
    except ValueError:
        raise DecisionRefused("invalid decision date") from None
    if not isinstance(data["mac"], str) or not re.fullmatch(r"[0-9a-f]{64}", data["mac"]):
        raise DecisionRefused("invalid decision MAC")


def secure_read(path, *, key=False):
    # Inspect the opened inode too, avoiding a path-stat/open replacement race.
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o022 or (key and stat.S_IMODE(info.st_mode) != 0o600)):
        raise DecisionRefused("unsafe key file" if key else "unsafe decision file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if ((opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
                or not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid()
                or opened.st_mode & 0o022
                or (key and stat.S_IMODE(opened.st_mode) != 0o600)):
            raise DecisionRefused("file changed or unsafe permissions")
        return stream.read()


def key_bytes():
    # Pin the authority key to the account home, independent of receipt-path
    # redirection or caller-controlled HOME/XDG_STATE_HOME settings.
    path = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/clavain/review-round-decision.key"
    key = secure_read(Path(path), key=True)
    if not key:
        raise DecisionRefused("empty decision key")
    return key


def mac(data, key):
    payload = {k: v for k, v in data.items() if k != "mac"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def claim(reviews, bead, head, failures, *, check_only=False):
    if not identifier(bead):
        raise DecisionRefused("invalid bead")
    directory = reviews / "round-limits/decisions"
    path = directory / f"{bead}.json"
    try:
        raw = secure_read(path)
    except FileNotFoundError:
        raise DecisionRefused("no recorded decision") from None
    data = json.loads(raw)
    validate(data)
    if not head or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise DecisionRefused("no exact review head")
    if data["bead"] != bead or data["head"] != head:
        raise DecisionRefused("decision bead or head mismatch")
    if data["accepted_failures"] != failures:
        raise DecisionRefused("decision failure count mismatch")
    if not hmac.compare_digest(data["mac"], mac(data, key_bytes())):
        raise DecisionRefused("decision MAC mismatch")
    # A digest keeps marker names bounded; identical IDs always claim one inode.
    marker = directory / (hashlib.sha256(data["decision_id"].encode()).hexdigest() + ".consumed")
    if check_only:
        if os.path.lexists(marker):
            raise DecisionRefused("decision already consumed; a new decision is needed (including after a capacity failure)")
        return data["decision_id"]
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise DecisionRefused("decision already consumed; a new decision is needed (including after a capacity failure)") from None
    os.close(fd)
    return data["decision_id"]
