"""Egress guard (mk-42j9.7 Task 2).

Implements the plan's "Egress guard" section: `admit()` scans a
`SelectionRequest`'s selector-visible text (task, context, and each
candidate's id and description) against a pattern set of credential and
source rules, and refuses the whole request on any hit. A refusal never
carries the matched text, a candidate id or a candidate summary -- only rule
ids.

Admission is an accidental-bypass guard, not a security boundary: any code
running in the same Python process can read this module's private key and
mint a tag, so it stops mistakes (a call path that forgets `admit()`, a
hand-built request in a test or a dependent's adapter), not hostile code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from clavain_selector.contract import MAX_REQUEST_BYTES, Point, SelectionRequest

# ---------------------------------------------------------------------------
# Admission tag: an accidental-bypass guard (Key links / Egress guard section)
# ---------------------------------------------------------------------------

_EGRESS_KEY = secrets.token_bytes(32)


@dataclass(frozen=True)
class Refusal:
    """The whole-request refusal produced by `admit()`.

    `rule_ids` are the egress rule ids that matched, in table order, with no
    duplicates. `detail` is a bounded, text-free description (rule ids only)
    -- never the matched text, a candidate id or a candidate summary.
    """

    rule_ids: tuple[str, ...]
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.detail:
            object.__setattr__(self, "detail", "egress rule(s) matched: " + ", ".join(self.rule_ids))


@dataclass(frozen=True)
class AdmittedRequest:
    """A request cleared to reach `JevClient.call`.

    `body` is the canonical, egress-scanned bytes for this selection (schema,
    point, integration, task, context and candidate `{id, description}`
    views only -- never a candidate's `payload`). `tag` is an HMAC over
    `sha256` under a module-private per-process key; only `admit()` can
    compute a valid tag, so a hand-built `AdmittedRequest` -- even one with a
    correct `sha256` for its `body` -- fails `verify()`.
    """

    body: bytes
    sha256: str
    tag: bytes


def _compute_tag(body_sha256: str) -> bytes:
    return hmac.new(_EGRESS_KEY, body_sha256.encode("ascii"), hashlib.sha256).digest()


def verify(admitted: AdmittedRequest) -> bool:
    """Recompute the body hash and check the tag with a constant-time compare."""
    if not isinstance(admitted, AdmittedRequest):
        return False
    body = admitted.body
    sha256 = admitted.sha256
    tag = admitted.tag
    if not isinstance(body, (bytes, bytearray)) or not isinstance(sha256, str) or not isinstance(tag, (bytes, bytearray)):
        return False
    expected_hash = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(expected_hash, sha256):
        return False
    expected_tag = _compute_tag(sha256)
    return hmac.compare_digest(expected_tag, bytes(tag))


def _build_body(request: SelectionRequest) -> bytes:
    """The canonical admitted-content envelope: exactly what was scanned.

    `Task 5` (the Jev client) wraps this into the full Jev wire request
    (`model`, `questions.fit_i`, ...); this function owns only the part that
    egress has cleared to leave the process.
    """
    point_value = request.point.value if isinstance(request.point, Point) else request.point
    payload = {
        "schema": "clavain-selection-v1",
        "point": point_value,
        "integration": request.integration,
        "task": request.task,
        "context": request.context,
        "candidates": [c.selector_view() for c in request.candidates],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------------------
# Shared regex fragments (Egress guard section, the block after the rule table)
# ---------------------------------------------------------------------------

_KEY_ANCHOR = r'(?<![A-Za-z0-9])["\']?(?:[\w.-]*[_.-])?'
_KEY_PWD = r'pwd(?!["\']?[ \t]*[:=][ \t]*["\']?~?/)'
_SEP = r'["\']?[ \t]*[:=][ \t]*'
_EXCL = (
    r'(?![{\[<($])(?!["\'][{\[<$(])'
    r'(?!["\']?(?:true|false|null|none|required|optional)\b)'
    r'(?!["\']?(?-i:your[-_][a-z_-]+|(?:example|placeholder)(?:[-_][a-z_-]+)?|redacted|REDACTED|EXAMPLE|PLACEHOLDER)["\']?(?:[\s,;}]|$))'
    r'(?!["\']?(?-i:[A-Z0-9_]*(?:YOUR_[A-Z0-9_]*|_HERE))["\']?(?:[\s,;}]|$))'
    r'(?!["\']?\*{3,})'
    r'(?!\d+(?:[\s"\',;}]|$))'
    r'(?![^\s"\',;}()]*\()'
)
_VALUE8 = r'(?:(?P<q1>["\'])(?!\s)[^"\'\n]{8,}(?P=q1)|[^\s"\',;}()]{8,})'
_VALUE1 = r'(?:(?P<q2>["\'])[^"\'\n]+(?P=q2)|[^\s"\',;}()]+)'

_KEY_ALTERNATION = (
    r'(?:api[_-]?key|apikey|secret|access[_-]?key|auth[_-]?token|token|'
    rf'passw(?:or)?d|passphrase|pass|{_KEY_PWD}|private[_-]?key|session[_-]?key|'
    r'account[_-]?key|credential)s?'
)
_PWD_KEY_ALTERNATION = rf'(?:passw(?:or)?d|passphrase|{_KEY_PWD})s?'


# ---------------------------------------------------------------------------
# Rule table (Egress guard section)
# ---------------------------------------------------------------------------

_TEXT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("cred.aws_key", re.compile(r'\b(AKIA|ASIA)[A-Z0-9]{16}\b')),
    ("cred.aws_secret", re.compile(r'(?i)["\']?aws_secret_access_key["\']?\s*[:=]\s*["\']?[^\s"\',;}]+')),
    ("cred.github_token", re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{20,}')),
    ("cred.gitlab_token", re.compile(r'\bglpat-[A-Za-z0-9_-]{20,}')),
    ("cred.anthropic_key", re.compile(r'\bsk-ant-[A-Za-z0-9_-]{20,}')),
    ("cred.openai_style_key", re.compile(r'\bsk-(?:proj-|svcacct-|admin-)?(?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]{20,}')),
    ("cred.stripe_key", re.compile(r'\b[rsp]k_(?:live|test)_[A-Za-z0-9]{16,}')),
    ("cred.google_api_key", re.compile(r'\bAIza[0-9A-Za-z_-]{35}')),
    ("cred.vault_token", re.compile(r'\bhvs\.[A-Za-z0-9_-]{20,}')),
    ("cred.azure_account_key", re.compile(r'AccountKey=[A-Za-z0-9+/=]{20,}|SharedAccessSignature=')),
    ("cred.gcp_service_account", re.compile(r'"type"\s*:\s*"service_account"|"private_key_id"\s*:\s*"[^"]+"')),
    ("cred.slack_token", re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}')),
    ("cred.private_key", re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----')),
    ("cred.package_token", re.compile(r'\bnpm_[A-Za-z0-9]{36}\b|\bpypi-AgEI[A-Za-z0-9_-]{50,}')),
    ("cred.netrc", re.compile(
        r'(?im)^[ \t]*(?:machine[ \t]+\S+|default)(?:\s+login\s+\S+)?(?:\s+account\s+\S+)?\s+password\s+\S+'
    )),
    ("cred.jwt", re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}')),
    ("cred.assignment", re.compile(
        rf'(?i){_KEY_ANCHOR}{_KEY_ALTERNATION}{_SEP}{_EXCL}{_VALUE8}'
    )),
    ("cred.password_assignment", re.compile(
        rf'(?i){_KEY_ANCHOR}{_PWD_KEY_ALTERNATION}{_SEP}{_EXCL}'
        r'(?!(?:files|compat|systemd|sss|ldap|nis|db)\b)(?!["\']{2})' + _VALUE1
    )),
    ("cred.bearer", re.compile(
        rf'(?i)\b(?:proxy-)?authorization[ \t]*:[ \t]*bearer[ \t]+{_EXCL}\S{{8,}}'
        rf'|\bbearer[ \t]+{_EXCL}[A-Za-z0-9._~+/=-]{{20,}}'
    )),
    ("cred.basic_auth", re.compile(r'(?i)\b(?:proxy-)?authorization[ \t]*:[ \t]*basic[ \t]+[A-Za-z0-9+/=]{8,}')),
    ("cred.cookie", re.compile(
        r'(?i)\b(?:set-)?cookie[ \t]*:[^\n]*?[\w.-]*(?:session|sess|sid|token|auth|jwt)[\w.-]*=[^;\s]{16,}'
    )),
    ("cred.url_userinfo", re.compile(r'[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@')),
]


# ---------------------------------------------------------------------------
# cred.high_entropy (Egress guard section, `cred.high_entropy` row)
# ---------------------------------------------------------------------------

_ESCAPE_RE = re.compile(r'\\[ntr"\\/u]')
_UUID_RE = re.compile(
    r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
)
_RUN_RE = re.compile(r'[A-Za-z0-9+/=_.:\\~-]{32,}')
_SSH_KEY_TYPE_TAIL_RE = re.compile(
    r'(?:ssh-rsa|ssh-dss|ssh-ed25519|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|'
    r'ecdsa-sha2-nistp521|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)'
    r'[ \t]+\Z'
)
_DATA_URI_TAIL_RE = re.compile(r';base64,\Z')
_WORD_LIKE_RE = re.compile(r'\A(?:[A-Za-z]+|[0-9]{1,8}|[a-z]{1,4}[0-9][a-z0-9]{0,5})\Z')
_FILENAME_SEG_RE = re.compile(r'\A[\w-]+\.[A-Za-z0-9]{1,6}\Z')
_DOTTED_NAME_BODY_RE = re.compile(r'\A(?:\.?[\w-]+(?:\.[\w-]+)+|\.[\w-]+)\Z')
_GREP_LINE_SUFFIX_RE = re.compile(r'\A(?P<name>.+?)(?::\d+:?)?\Z')
_SCORE_RUN_RE = re.compile(r'[A-Za-z0-9+/=_-]{32,}')
_PURE_LOWER_HEX_RE = re.compile(r'\A[0-9a-f]+\Z')

_ENTROPY_MIN_BITS = 4.2


def _is_word_like(segment: str) -> bool:
    return bool(_WORD_LIKE_RE.match(segment))


def _is_slug(segment: str) -> bool:
    parts = re.split(r'[-_]', segment)
    parts = [p for p in parts if p]
    if len(parts) < 3:
        return False
    word_like = sum(1 for p in parts if _is_word_like(p))
    return word_like >= 0.75 * len(parts)


def _is_filename(segment: str) -> bool:
    return bool(_FILENAME_SEG_RE.match(segment))


def _dotted_name_ok(segment: str) -> bool:
    match = _GREP_LINE_SUFFIX_RE.match(segment)
    body = match.group("name") if match else segment
    if not body or "=" in body:
        return False
    return bool(_DOTTED_NAME_BODY_RE.match(body))


def _is_path_like(run: str) -> bool:
    if run.startswith("/") or run.startswith("~/") or run.startswith("./") or run.startswith("../"):
        return True
    seps = run.count("/") + run.count("\\")
    if seps == 0:
        return False
    if seps >= 3:
        return True
    segments = re.split(r'[/\\]', run)
    if any(_dotted_name_ok(seg) for seg in segments if seg):
        return True
    non_empty = [seg for seg in segments if seg]
    if non_empty and all(_is_word_like(seg) or _is_slug(seg) or _is_filename(seg) for seg in non_empty):
        return True
    return False


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    length = len(s)
    counts = Counter(s)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def _score_candidate(piece: str) -> bool:
    """True when `piece` (a run of the scoring alphabet, >=32 chars) refuses."""
    if _PURE_LOWER_HEX_RE.match(piece):
        return False
    if _is_slug(piece):
        return False
    has_upper = any(c.isupper() for c in piece)
    has_lower = any(c.islower() for c in piece)
    has_digit = any(c.isdigit() for c in piece)
    if not (has_upper and has_lower and has_digit):
        return False
    return _shannon_entropy(piece) >= _ENTROPY_MIN_BITS


def _high_entropy_hit(text: str) -> bool:
    if not text:
        return False
    # Step 1: JSON-escaped newlines/quotes/slashes become a space.
    working = _ESCAPE_RE.sub(" ", text)
    # Step 5 (applied early, equivalent for this rule's purposes): canonical
    # UUIDs never form part of a scored run.
    working = _UUID_RE.sub(" ", working)

    for match in _RUN_RE.finditer(working):
        run = match.group(0)
        start = match.start()
        prefix = working[:start]

        # Step 3: skip whole runs that are public keys/hashes, not secrets.
        if run.startswith("h1:"):
            continue
        if run.startswith(("sha256-", "sha384-", "sha512-")):
            continue
        if _SSH_KEY_TYPE_TAIL_RE.search(prefix):
            continue
        if _DATA_URI_TAIL_RE.search(prefix):
            continue

        # Step 4: split on `.`/`:` always, and on `/`/`\` when path-like.
        split_pattern = r'[./\\:]' if _is_path_like(run) else r'[.:]'
        for piece in re.split(split_pattern, run):
            # Step 6: score each remaining run of the (narrower) scoring alphabet.
            for sub_match in _SCORE_RUN_RE.finditer(piece):
                if _score_candidate(sub_match.group(0)):
                    return True
    return False


# ---------------------------------------------------------------------------
# scan_text
# ---------------------------------------------------------------------------

_HIGH_ENTROPY_DEFAULT_POINTS = frozenset({Point.POST_TOOL_OUTPUT.value, Point.PRE_COMPACT.value})


def _point_value(point: Point | str) -> str:
    return point.value if isinstance(point, Point) else str(point)


def scan_text(text: str, point: Point | str, *, high_entropy: bool | None = None) -> list[str]:
    """Every credential rule over `text`, returning matched rule ids only.

    `high_entropy` overrides the point-based default (on for
    `post_tool_output`/`pre_compact`, opt-in elsewhere via the integration
    registry's `high_entropy: true`).
    """
    if not text:
        return []
    hits: list[str] = []
    for rule_id, pattern in _TEXT_RULES:
        if pattern.search(text):
            hits.append(rule_id)

    if high_entropy is None:
        entropy_on = _point_value(point) in _HIGH_ENTROPY_DEFAULT_POINTS
    else:
        entropy_on = high_entropy
    if entropy_on and _high_entropy_hit(text):
        hits.append("cred.high_entropy")

    return hits


# ---------------------------------------------------------------------------
# Source and project-owner checks
# ---------------------------------------------------------------------------

_DENYLISTED_HOME_TOP = frozenset({".ssh", ".aws", ".gnupg"})
_ALLOWED_OWNERS = frozenset({"mistakeknot", "gensysven"})


def _is_env_file(name: str) -> bool:
    return name == ".env" or (name.startswith(".env.") and len(name) > len(".env."))


def _source_rule(path: Path, project_root: Path | None) -> str | None:
    try:
        resolved = Path(path).resolve()
    except OSError:
        return "src.denylisted_path"

    if _is_env_file(resolved.name):
        return "src.denylisted_path"

    home = Path(os.path.expanduser("~")).resolve()
    try:
        rel_parts = resolved.relative_to(home).parts
    except ValueError:
        rel_parts = ()
    if rel_parts:
        if rel_parts[0] in _DENYLISTED_HOME_TOP:
            return "src.denylisted_path"
        if rel_parts[0] == ".config":
            if len(rel_parts) >= 2 and rel_parts[1] == "jev":
                return "src.denylisted_path"
            if any(part.startswith("secrets") for part in rel_parts[1:]):
                return "src.denylisted_path"

    if project_root is not None:
        try:
            resolved.relative_to(Path(project_root).resolve())
        except ValueError:
            return "src.outside_project"
    else:
        return "src.outside_project"

    return None


_OWNER_CACHE_LOCK = threading.Lock()
_SSH_GITHUB_RE = re.compile(r'\Agit@github\.com:([^/]+)/')
_HTTPS_GITHUB_RE = re.compile(r'\Ahttps://github\.com/([^/]+)/')
_REMOTE_ORIGIN_HEADER_RE = re.compile(r'\A\[remote\s+"origin"\]\Z', re.IGNORECASE)


def _state_dir() -> Path:
    return Path(os.environ.get("CLAVAIN_STATE_DIR") or os.path.expanduser("~/.clavain")).expanduser()


def _owner_cache_path() -> Path:
    return _state_dir() / "selector" / "owner-cache.json"


def _read_owner_cache() -> dict:
    try:
        return json.loads(_owner_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_owner_cache(cache: dict) -> None:
    path = _owner_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp_path = path.with_name(path.name + f".tmp-{os.getpid()}")
        tmp_path.write_text(json.dumps(cache), encoding="utf-8")
        tmp_path.replace(path)
    except OSError:
        pass


def _resolve_git_config_path(root_path: Path) -> Path | None:
    git_entry = root_path / ".git"
    try:
        if git_entry.is_file():
            content = git_entry.read_text(encoding="utf-8").strip()
            if not content.lower().startswith("gitdir:"):
                return None
            gitdir = Path(content.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = root_path / gitdir
            gitdir = gitdir.resolve()
            commondir_file = gitdir / "commondir"
            if commondir_file.is_file():
                common = Path(commondir_file.read_text(encoding="utf-8").strip())
                if not common.is_absolute():
                    common = gitdir / common
                config_path = common.resolve() / "config"
            else:
                config_path = gitdir / "config"
        elif git_entry.is_dir():
            config_path = git_entry / "config"
        else:
            return None
    except OSError:
        return None
    return config_path if config_path.is_file() else None


def _parse_origin_owner(config_text: str) -> str | None:
    in_origin = False
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if line.startswith("["):
            in_origin = bool(_REMOTE_ORIGIN_HEADER_RE.match(line))
            continue
        if not in_origin:
            continue
        match = re.match(r'\Aurl\s*=\s*(.+?)\s*\Z', line, re.IGNORECASE)
        if not match:
            continue
        url = match.group(1).strip()
        owner_match = _SSH_GITHUB_RE.match(url) or _HTTPS_GITHUB_RE.match(url)
        return owner_match.group(1) if owner_match else None
    return None


def project_owner(root: str | Path) -> str | None:
    """The GitHub owner of `root`'s `origin` remote, with no subprocess.

    Reads `<root>/.git` directly (following a worktree's `gitdir:` pointer
    and `commondir`), parses `[remote "origin"] url = ...`, and caches the
    result per session keyed by `(resolved root, config st_mtime_ns)`. Any
    read or parse error, or the absence of an origin, resolves to `None`
    (the caller maps that to `proj.unowned`).
    """
    try:
        root_path = Path(root).resolve()
    except OSError:
        return None

    config_path = _resolve_git_config_path(root_path)
    if config_path is None:
        return None
    try:
        mtime_ns = config_path.stat().st_mtime_ns
    except OSError:
        return None

    cache_key = f"{root_path}:{mtime_ns}"
    with _OWNER_CACHE_LOCK:
        cache = _read_owner_cache()
        if cache_key in cache:
            return cache[cache_key]
        try:
            config_text = config_path.read_text(encoding="utf-8")
        except OSError:
            return None
        owner = _parse_origin_owner(config_text)
        cache[cache_key] = owner
        _write_owner_cache(cache)
        return owner


# ---------------------------------------------------------------------------
# admit()
# ---------------------------------------------------------------------------

def admit(
    request: SelectionRequest,
    *,
    key_literal: str | None = None,
    high_entropy: bool | None = None,
) -> "AdmittedRequest | Refusal":
    """Whole-request refusal on any egress rule hit; otherwise an `AdmittedRequest`.

    Scans the task, the context, and each candidate's id and description
    (`scan_text`), checks the loaded-key literal when supplied, checks
    declared sources against the denylist and `project_root`, checks the
    project's `origin` owner, and checks the serialized body size. A hit on
    any rule refuses the whole request; only rule ids are recorded.
    """
    texts: list[str] = [request.task, request.context]
    for candidate in request.candidates:
        texts.append(candidate.id)
        texts.append(candidate.description)

    hits: list[str] = []

    def _add(rule_id: str | None) -> None:
        if rule_id and rule_id not in hits:
            hits.append(rule_id)

    for text in texts:
        for rule_id in scan_text(text, request.point, high_entropy=high_entropy):
            _add(rule_id)

    if key_literal:
        if any(text and key_literal in text for text in texts):
            _add("cred.loaded_key")

    for source in request.sources:
        _add(_source_rule(Path(source), request.project_root))

    if request.project_root is not None:
        owner = project_owner(request.project_root)
        if owner not in _ALLOWED_OWNERS:
            _add("proj.unowned")

    body = _build_body(request)
    if len(body) > MAX_REQUEST_BYTES:
        _add("size.over_limit")

    if hits:
        return Refusal(rule_ids=tuple(hits))

    body_sha256 = hashlib.sha256(body).hexdigest()
    tag = _compute_tag(body_sha256)
    return AdmittedRequest(body=body, sha256=body_sha256, tag=tag)
