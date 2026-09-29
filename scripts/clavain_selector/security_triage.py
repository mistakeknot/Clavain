"""Security-review triage preparer (mk-42j9.9), SHADOW ONLY.

At the `pre_tool` point for a proposed file edit, offers Jev three candidates
about how much security scrutiny the edit deserves:

* `keep_native_review`    -- nothing unusual; the native review runs as usual.
* `light_check_suffices`  -- low-risk edit; measurement-only, never authorized.
* `raise_scrutiny`        -- security-sensitive edit; the ONLY id the
                             integration's authorize policy allows.

The guarantee this module exists to keep: Jev may only ever ESCALATE. No
candidate here stands for cancelling, skipping, weakening or pre-approving a
review, and nothing in this module reads or changes the external
security-guidance plugin. `raise_scrutiny` can at most become a Claude Code
`ask` prompt, and only if an operator later rules the integration out of
shadow (the shipped registry entry is `shadow_only`, so active is downgraded
to shadow). `light_check_suffices` is recorded so a later measurement pass can
compare Jev's would-be triage with what the native review found; it carries a
precondition that can never be met, so it can never be emitted either.

Pure and side-effect free: no file reads, no network, no environment.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from clavain_selector.adapters.base import HostEvent
from clavain_selector.contract import Candidate, Point

NAME = "security_triage"
INTEGRATION = "security_triage"

KEEP_NATIVE = "keep_native_review"
LIGHT_CHECK = "light_check_suffices"
RAISE_SCRUTINY = "raise_scrutiny"

# The closed vocabulary. There is deliberately no skip/cancel/approve/allow id,
# and `tests/structural/test_selector_security_triage.py` pins that.
VOCABULARY = frozenset({KEEP_NATIVE, LIGHT_CHECK, RAISE_SCRUTINY})

# The only id the registry `authorize` policy may name.
AUTHORIZED_IDS = (RAISE_SCRUTINY,)

EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

# The measurement-only candidates carry this precondition. Nothing ever
# satisfies it (`selector` row 12 requires an empty precondition list), so
# even a mis-edited authorize policy cannot emit them.
NEVER_EMITTED = "measurement_only"

_EXCERPT_CHARS = 4_000
_PATH_CHARS = 240

# Deterministic host-side facts handed to Jev as context. Names only; the
# matched text is never included.
_SIGNALS = (
    ("auth", re.compile(r"\b(auth\w*|login|password|passwd|session|jwt|oauth|token|credential\w*)\b", re.I)),
    ("secrets", re.compile(r"\b(secret\w*|api[_-]?key|private[_-]?key|bearer)\b", re.I)),
    ("crypto", re.compile(r"\b(crypto\w*|hmac|sha\d*|md5|aes|rsa|cipher|encrypt\w*|decrypt\w*|random)\b", re.I)),
    ("shell", re.compile(r"\b(subprocess|os\.system|popen|exec\w*|eval|shell\s*=\s*true|child_process)\b", re.I)),
    ("sql", re.compile(r"\b(select\s.+\sfrom|insert\s+into|update\s.+\sset|delete\s+from|execute\()", re.I)),
    ("deserialize", re.compile(r"\b(pickle|yaml\.load|marshal|unserialize|deserializ\w*)\b", re.I)),
    ("network", re.compile(r"\b(https?://|socket|listen\(|bind\(|0\.0\.0\.0|cors|tls|ssl|verify\s*=\s*false)\b", re.I)),
    ("permissions", re.compile(r"\b(chmod|chown|sudo|setuid|permission\w*|allowlist|denylist|acl)\b", re.I)),
    ("path", re.compile(r"(\.\./|\brealpath\b|\bsymlink\b|\bpath\.join\b)", re.I)),
)


# Fail closed on anything credential-shaped. `egress.scan_text` catches
# high-entropy tokens but not short or multi-line values (`API_KEY = "abc123"`,
# `password = (\n "x"\n)`, heredocs, lookalike characters), and a per-line
# redaction cannot promise to catch them all. So when the edit text names a
# credential at all, or carries key material or URL userinfo, the excerpt is
# withheld entirely. Jev still gets the file, size and the host_signals names
# (computed from the original text), which is what the triage needs.
_CREDENTIAL_NAME = re.compile(
    r"secret|token|passw|passphrase|pwd|api[_\-\s]?key|private[_\-\s]?key|credential|bearer|authorization|auth[_\-]?key",
    re.I,
)
_KEY_MATERIAL = re.compile(
    r"-----BEGIN [A-Z ]*-----|\bssh-(?:rsa|ed25519|dss)\b|\becdsa-sha2-|\bAKIA[0-9A-Z]{8,}|<<-?\s*['\"]?\w+",
    re.I,
)
_URL_USERINFO = re.compile(r"://[^/\s:@]+:[^/\s@]+@")
OMITTED = "<excerpt omitted: credential-shaped content>"


def _excerpt(text: str) -> str:
    # NFKC folds width/compatibility lookalikes; strip zero-width and format
    # characters that could split a name; anything left unrecognised stays
    # subject to egress.scan_text as the second gate.
    folded = "".join(
        ch for ch in unicodedata.normalize("NFKC", text) if unicodedata.category(ch) not in ("Cf", "Cc") or ch in "\n\t"
    )
    if _CREDENTIAL_NAME.search(folded) or _KEY_MATERIAL.search(folded) or _URL_USERINFO.search(folded):
        return OMITTED
    return text[:_EXCERPT_CHARS]


def vocabulary(project_root: Path | None = None) -> frozenset[str]:
    return VOCABULARY


def _edit_text(tool_name: str, tool_input: Mapping[str, Any]) -> str:
    """The text the edit would introduce; empty when the shape is unknown."""
    parts: list[str] = []
    if tool_name == "Write":
        parts.append(tool_input.get("content"))
    elif tool_name == "Edit":
        parts.append(tool_input.get("new_string"))
    elif tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        if isinstance(edits, (list, tuple)):
            for item in edits:
                if isinstance(item, Mapping):
                    parts.append(item.get("new_string"))
    elif tool_name == "NotebookEdit":
        parts.append(tool_input.get("new_source"))
    return "\n".join(p for p in parts if isinstance(p, str))


def _absolute_path(raw: str, project_root: Path | None) -> str:
    """A relative edit path is relative to the project, not the hook's cwd."""
    path = Path(raw)
    if not path.is_absolute() and project_root is not None:
        path = Path(project_root) / path
    return str(path)


def _relative_path(absolute: str, project_root: Path | None) -> str:
    path = Path(absolute)
    if project_root is not None:
        try:
            return str(path.resolve().relative_to(Path(project_root).resolve()))
        except (ValueError, OSError):
            pass
    return path.name


def _signals(text: str, path: str) -> list[str]:
    haystack = f"{path}\n{text}"
    return [name for name, pattern in _SIGNALS if pattern.search(haystack)]


def _candidates(revision: str) -> tuple[Candidate, ...]:
    return (
        Candidate(
            id=KEEP_NATIVE,
            description=(
                "Nothing unusual about this edit. The native security review runs exactly as it "
                "would anyway; no extra attention is needed."
            ),
            payload={"triage": KEEP_NATIVE},
            prepared_at_revision=revision,
            preconditions=(NEVER_EMITTED,),
        ),
        Candidate(
            id=LIGHT_CHECK,
            description=(
                "A low-risk edit (documentation, comments, formatting, renames or tests only) where "
                "a light check would be enough. Recorded for measurement only; it changes nothing."
            ),
            payload={"triage": LIGHT_CHECK},
            prepared_at_revision=revision,
            preconditions=(NEVER_EMITTED,),
        ),
        Candidate(
            id=RAISE_SCRUTINY,
            description=(
                "A security-sensitive edit (authentication, secrets, cryptography, shell or SQL "
                "construction, deserialization, permissions, network exposure or path handling) "
                "that deserves a human's closer look before it is applied."
            ),
            payload={"triage": RAISE_SCRUTINY},
            prepared_at_revision=revision,
        ),
    )


def build(event: HostEvent | None, project_root: Path | None):
    """Turn a projected `pre_tool` edit event into the triage candidates.

    Raises `NotPrepared` (no egress, no record) for anything that is not a
    well-formed file edit, so a malformed or unrelated event is inert.
    """
    from clavain_selector.preparers import NotPrepared, PreparedInput

    if event is None or event.tool_name not in EDIT_TOOLS:
        raise NotPrepared("not a file-edit tool event")
    tool_input = event.tool_input
    if not isinstance(tool_input, Mapping):
        raise NotPrepared("tool_input is not a mapping")
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw_path, str) or not raw_path:
        raise NotPrepared("edit has no file path")

    raw_path = _absolute_path(raw_path, project_root)
    text = _edit_text(event.tool_name, tool_input)
    rel = _relative_path(raw_path, project_root)[:_PATH_CHARS]
    signals = _signals(text, rel)
    digest = hashlib.sha256(f"{event.tool_name}\0{raw_path}\0{text}".encode("utf-8")).hexdigest()

    excerpt = _excerpt(text)
    context = "\n".join(
        (
            f"tool: {event.tool_name}",
            f"file: {rel}",
            f"new_text_chars: {len(text)}",
            f"new_text_lines: {text.count(chr(10)) + (1 if text else 0)}",
            f"host_signals: {', '.join(signals) if signals else 'none'}",
            "new_text_excerpt:",
            excerpt,
        )
    )
    return PreparedInput(
        task=(
            "A coding agent proposes the file edit described below. Choose how much security "
            "scrutiny it deserves, or escalate if unsure. The native security review always "
            "runs regardless of your choice."
        ),
        context=context,
        candidates=_candidates(digest),
        task_revision=digest,
        sources=(raw_path,),
    )
