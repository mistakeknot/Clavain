"""Tests for scripts/clavain_selector/adapters/ (mk-42j9.7 Task 6).

Only synthetic fixture data (tests/fixtures/selector/claude/*.json) is used;
no real transcript text is read or printed.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from selector_helpers import make_candidate, selector_socket_guard  # noqa: F401

from clavain_selector.adapters import (
    BbAdapter,
    ClaudeCodeAdapter,
    CodexAdapter,
    FingerprintUnavailable,
    HermesAdapter,
    HostEvent,
    KimiAdapter,
    LAUNCH_ARGV_TEMPLATE,
    Outcome,
    PiAdapter,
    PointUnreachable,
    authorize_by_policy,
    emitted_outcome,
    fingerprint_paths,
    gate_mode,
    launch_argv_ok,
    load_matrix,
)
from clavain_selector.adapters import base as adapters_base
from clavain_selector import contract
from clavain_selector.contract import (
    AuthorizationPolicy,
    FallbackReason,
    Point,
    Provenance,
    ValidatedCandidates,
    payload_sha256,
)

_FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "selector"


def _validated_for(
    candidate,
    *others,
    integration: str = "selftest",
    point: Point = Point.POST_TOOL_OUTPUT,
) -> ValidatedCandidates:
    """A minimal, well-formed `ValidatedCandidates` wrapping `candidate` (and
    any `others`), with a binding computed the same way `validated_candidates`
    would -- so `authorize_by_policy`/`emitted_outcome` exercise the real
    payload-hash check rather than a hand-waved stand-in."""
    candidates = contract.canonical_order((candidate, *others))
    return ValidatedCandidates(
        integration=integration,
        point=point,
        candidates=candidates,
        request_sha256="0" * 64,
        bindings=tuple((c.id, payload_sha256(c.payload)) for c in candidates),
        provenance=Provenance.OPERATOR,
    )

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "selector" / "claude"

_VALID_STATUSES = {"reachable", "partial", "unreachable", "unverified"}
_VALID_EVIDENCE_LEVELS = {"first_hand", "binary", "clavain_code", "sylveste_code", "docs", "none"}
_ALL_HOSTS = {"claude-code", "codex", "hermes", "kimi", "pi", "bb"}
_ALL_POINTS = {
    Point.LAUNCH_PROFILE,
    Point.PROMPT_SUBMIT,
    Point.PRE_TOOL,
    Point.POST_TOOL_OUTPUT,
    Point.PRE_COMPACT,
    Point.SESSION_START,
    Point.SKILL_LOADING,
}

_FORBIDDEN_SNIPPETS = ('"permissionDecision": "allow"', '"decision": "approve"', "updatedInput")


def _read_fixture(name: str) -> bytes:
    return (_FIXTURE_DIR / name).read_bytes()


def _hash_text(value: str) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------


def test_matrix_complete():
    matrix = load_matrix()
    assert set(matrix.keys()) == _ALL_HOSTS
    for host, points in matrix.items():
        assert set(points.keys()) == _ALL_POINTS, host
        for point, cap in points.items():
            assert cap.status in _VALID_STATUSES, (host, point)
            assert cap.evidence_level in _VALID_EVIDENCE_LEVELS, (host, point)
            assert isinstance(cap.mechanism, str)
            assert isinstance(cap.limits, str)
            assert cap.verified_on
            assert cap.verified_at

    claude = matrix["claude-code"]
    assert claude[Point.PRE_TOOL].status == "partial"
    assert claude[Point.PRE_TOOL].evidence_level == "binary"
    assert "adapters never emit updatedInput or allow" in claude[Point.PRE_TOOL].limits
    assert claude[Point.LAUNCH_PROFILE].evidence_level == "first_hand"

    kimi = matrix["kimi"]
    assert kimi[Point.PROMPT_SUBMIT].evidence_level == "sylveste_code"

    assert matrix["bb"][Point.PRE_TOOL].status == "unreachable"
    assert matrix["bb"][Point.PROMPT_SUBMIT].status == "unreachable"
    assert matrix["bb"][Point.POST_TOOL_OUTPUT].status == "unreachable"
    assert matrix["bb"][Point.LAUNCH_PROFILE].status == "reachable"
    assert matrix["kimi"][Point.POST_TOOL_OUTPUT].status == "unverified"
    assert matrix["hermes"][Point.PRE_COMPACT].status == "unverified"
    assert matrix["hermes"][Point.POST_TOOL_OUTPUT].evidence_level == "first_hand"


@pytest.mark.parametrize(
    "adapter_cls, host_name",
    [
        (CodexAdapter, "codex"),
        (HermesAdapter, "hermes"),
        (KimiAdapter, "kimi"),
        (PiAdapter, "pi"),
        (BbAdapter, "bb"),
    ],
)
def test_stub_capabilities_match_matrix(adapter_cls, host_name):
    matrix = load_matrix()
    adapter = adapter_cls()
    assert adapter.capabilities() == matrix[host_name]


def test_unreachable_raises():
    with pytest.raises(PointUnreachable):
        BbAdapter().parse_event(Point.PRE_TOOL, b"{}")
    with pytest.raises(PointUnreachable):
        KimiAdapter().parse_event(Point.POST_TOOL_OUTPUT, b"{}")


# ---------------------------------------------------------------------------
# Claude Code adapter: render()
# ---------------------------------------------------------------------------


def test_render_never_allows():
    adapter = ClaudeCodeAdapter()
    pre_tool_event = adapter.parse_event(Point.PRE_TOOL, _read_fixture("pre_tool.json"))
    post_tool_event = adapter.parse_event(Point.POST_TOOL_OUTPUT, _read_fixture("post_tool.json"))
    candidate = make_candidate(id="cand-a", payload="replacement text")
    validated = _validated_for(candidate)
    emitted = emitted_outcome(candidate, validated, mode="active")

    outcomes = [
        Outcome(kind="shadow"),
        Outcome(kind="native", fallback_reason=FallbackReason.POINT_UNREACHABLE.value),
        Outcome(kind="native", fallback_reason=FallbackReason.EGRESS_REFUSED.value),
        Outcome(kind="native", fallback_reason=FallbackReason.LOW_CONFIDENCE.value),
        Outcome(kind="native", fallback_reason=FallbackReason.UNAUTHORIZED.value),
        emitted,
    ]
    for point, event in (
        (Point.LAUNCH_PROFILE, pre_tool_event),
        (Point.PRE_TOOL, pre_tool_event),
        (Point.POST_TOOL_OUTPUT, post_tool_event),
    ):
        for outcome in outcomes:
            rendered = adapter.render(point, outcome, event).decode("utf-8")
            for snippet in _FORBIDDEN_SNIPPETS:
                assert snippet not in rendered, (point, outcome.kind, snippet)


def test_post_tool_render_shape():
    adapter = ClaudeCodeAdapter()
    event = adapter.parse_event(Point.POST_TOOL_OUTPUT, _read_fixture("post_tool.json"))
    assert isinstance(event.tool_response, str)

    candidate = make_candidate(id="cand-shape", payload="replacement text")
    validated = _validated_for(candidate, point=Point.POST_TOOL_OUTPUT)
    outcome = emitted_outcome(candidate, validated, mode="active")
    rendered = json.loads(adapter.render(Point.POST_TOOL_OUTPUT, outcome, event))
    replacement = rendered["hookSpecificOutput"]["updatedToolOutput"]
    assert isinstance(replacement, type(event.tool_response))
    assert replacement == "replacement text"

    record = {
        "result": {"kind": "selected", "candidate_id": "cand-shape"},
        "candidates": [{"id": "cand-shape", "payload_sha256": _hash_text("replacement text")}],
    }
    original_next_event = HostEvent(
        point=Point.POST_TOOL_OUTPUT, session_id="sess-fake-0001", tool_response=event.tool_response
    )
    selected_next_event = HostEvent(
        point=Point.POST_TOOL_OUTPUT, session_id="sess-fake-0001", tool_response="replacement text"
    )
    assert adapter.acknowledge(record, original_next_event) == "original"
    assert adapter.acknowledge(record, selected_next_event) == "selected"


def test_shadow_render_is_empty():
    adapter = ClaudeCodeAdapter()
    pre_tool_event = adapter.parse_event(Point.PRE_TOOL, _read_fixture("pre_tool.json"))
    post_tool_event = adapter.parse_event(Point.POST_TOOL_OUTPUT, _read_fixture("post_tool.json"))
    shadow = Outcome(kind="shadow")
    assert adapter.render(Point.PRE_TOOL, shadow, pre_tool_event) == b""
    assert adapter.render(Point.POST_TOOL_OUTPUT, shadow, post_tool_event) == b""


def test_launch_render_does_not_execute(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("render() must never execute a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)

    adapter = ClaudeCodeAdapter()
    candidate = make_candidate(id="profile-x", payload=[*LAUNCH_ARGV_TEMPLATE, "profile-x"])
    validated = _validated_for(candidate, point=Point.LAUNCH_PROFILE)
    outcome = emitted_outcome(candidate, validated, mode="active")
    event = HostEvent(point=Point.LAUNCH_PROFILE, session_id="sess-fake-0001")
    rendered = json.loads(adapter.render(Point.LAUNCH_PROFILE, outcome, event))
    assert isinstance(rendered["argv"], list)
    assert rendered["argv"][0] == "claude"
    assert "profile-x" in rendered["argv"]


def test_active_requires_first_hand():
    matrix = load_matrix()
    codex_launch = matrix["codex"][Point.LAUNCH_PROFILE]
    assert codex_launch.status == "reachable"
    assert codex_launch.evidence_level == "docs"
    assert gate_mode(codex_launch, "shadow") is None
    assert gate_mode(codex_launch, "active") == FallbackReason.POINT_UNREACHABLE

    claude_launch = matrix["claude-code"][Point.LAUNCH_PROFILE]
    assert claude_launch.evidence_level == "first_hand"
    assert gate_mode(claude_launch, "active") is None

    bb_pre_tool = matrix["bb"][Point.PRE_TOOL]
    assert gate_mode(bb_pre_tool, "shadow") == FallbackReason.POINT_UNREACHABLE


def test_parse_event_fixtures():
    adapter = ClaudeCodeAdapter()
    pre_event = adapter.parse_event(Point.PRE_TOOL, _read_fixture("pre_tool.json"))
    assert pre_event.tool_name == "Bash"
    assert pre_event.session_id == "sess-fake-0001"
    assert pre_event.tool_input["command"] == "echo hello"

    post_event = adapter.parse_event(Point.POST_TOOL_OUTPUT, _read_fixture("post_tool.json"))
    assert post_event.tool_name == "Bash"
    assert post_event.session_id == "sess-fake-0001"
    assert post_event.tool_response == "hello\n"


# ---------------------------------------------------------------------------
# fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint(tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("alpha")
    f2.write_text("beta")

    fp1 = fingerprint_paths([f1, f2])
    fp2 = fingerprint_paths([f1, f2])
    assert fp1 == fp2

    # Same-size, same-second rewrite with different content: restoring the
    # mtime afterward must not hide the change (content hash differs).
    st_before = f1.stat()
    f1.write_text("ALPHA")
    os.utime(f1, ns=(st_before.st_atime_ns, st_before.st_mtime_ns))
    fp3 = fingerprint_paths([f1, f2])
    assert fp3 != fp1

    # Replace-by-rename changes the inode even if content matches again.
    f1_new = tmp_path / "a_new.txt"
    f1_new.write_text("ALPHA")
    os.replace(f1_new, f1)
    fp4 = fingerprint_paths([f1, f2])
    assert fp4 != fp3

    # A missing file is fingerprinted as missing, not skipped.
    missing = tmp_path / "missing.txt"
    fp_with_missing = fingerprint_paths([f1, f2, missing])
    fp_without = fingerprint_paths([f1, f2])
    assert fp_with_missing != fp_without


def test_fingerprint_too_many_paths_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters_base, "FINGERPRINT_MAX_PATHS", 2)
    f1 = tmp_path / "a.txt"
    f1.write_text("alpha")
    with pytest.raises(FingerprintUnavailable):
        fingerprint_paths([f1, f1, f1])


def test_fingerprint_oversized_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters_base, "FINGERPRINT_MAX_BYTES", 4)
    big = tmp_path / "big.txt"
    big.write_text("way more than four bytes")
    with pytest.raises(FingerprintUnavailable):
        fingerprint_paths([big])


def test_fingerprint_lstat_seam_failure_raises(tmp_path, monkeypatch):
    f1 = tmp_path / "a.txt"
    f1.write_text("alpha")

    def _boom_lstat(path):
        raise PermissionError("simulated lstat failure")

    monkeypatch.setattr(adapters_base, "_lstat", _boom_lstat)
    with pytest.raises(FingerprintUnavailable):
        fingerprint_paths([f1])


def test_fingerprint_dev_ino_swap_retries_then_raises(tmp_path, monkeypatch):
    """If a path's (dev, ino) never stabilizes between lstat and open, the
    fingerprint must raise -- never silently fingerprint a moving target."""
    f1 = tmp_path / "a.txt"
    f1.write_text("alpha")

    real_lstat = os.lstat
    calls = {"n": 0}

    class _FakeStat:
        def __init__(self, real):
            self.st_mode = real.st_mode
            self.st_size = real.st_size
            self.st_mtime_ns = real.st_mtime_ns
            self.st_dev = real.st_dev
            # Every lstat() call reports a different, ever-increasing inode,
            # so it can never match the inode `fstat()` sees after `open()`.
            calls["n"] += 1
            self.st_ino = real.st_ino + calls["n"]

    def _swapping_lstat(path):
        return _FakeStat(real_lstat(path))

    monkeypatch.setattr(adapters_base, "_lstat", _swapping_lstat)
    with pytest.raises(FingerprintUnavailable):
        fingerprint_paths([f1])
    # The seam was actually exercised (not short-circuited some other way).
    assert calls["n"] >= 2


def test_fingerprint_read_race_retries_then_matches_settled_entry(tmp_path, monkeypatch):
    """A file that changes content, size, and mtime while it is being read
    must be retried once on the same descriptor (plan:364). The resulting
    entry must equal the entry a fresh, unhurried read of the now-settled
    file would produce -- never a torn mix of pre-mutation identity fields
    and post-mutation content (the row-12 race a re-reviewer reproduced
    against the pre-fix implementation)."""
    f1 = tmp_path / "a.txt"
    f1.write_text("stable-content")
    st0 = f1.stat()

    real_fstat = os.fstat
    calls = {"n": 0}

    def _flicker_once(fd):
        calls["n"] += 1
        pre = real_fstat(fd)
        if calls["n"] == 1:
            # Mutate on disk right after the file is opened (and its
            # identity confirmed) but before it settles for reading --
            # reproducing a write landing mid-fingerprint. Report the
            # *pre*-mutation stat, matching what a real fstat() would have
            # returned had it been called an instant earlier. The mtime is
            # forced strictly forward by an explicit offset rather than
            # relying on wall-clock advancement, which the filesystem's
            # clock resolution may not guarantee between two closely spaced
            # writes.
            f1.write_text("mutated-content-longer")
            os.utime(f1, ns=(st0.st_atime_ns, st0.st_mtime_ns + 1_000_000))
        return pre

    monkeypatch.setattr(os, "fstat", _flicker_once)
    entry = adapters_base._entry_for_path(f1)
    monkeypatch.undo()

    settled_entry = adapters_base._entry_for_path(f1)
    assert entry == settled_entry
    # The retry path (a second fstat call) was actually exercised.
    assert calls["n"] >= 2


def test_fingerprint_read_race_persistently_unstable_raises(tmp_path, monkeypatch):
    """If a file keeps changing across the single retry the plan allows
    (:364), the fingerprint must raise -- row 12 must take the
    fingerprint-failure fallback and never emit for a target that never
    settles."""
    f1 = tmp_path / "a.txt"
    f1.write_text("stable-content")
    st0 = f1.stat()

    real_fstat = os.fstat
    calls = {"n": 0}

    def _flicker_always(fd):
        calls["n"] += 1
        pre = real_fstat(fd)
        # Mutate before every fstat call, including the post-read check on
        # the retried pass -- the content never settles. Each mutation's
        # mtime is forced strictly forward by an explicit offset rather
        # than relying on wall-clock advancement between closely spaced
        # writes, which the filesystem's clock resolution may not
        # distinguish.
        f1.write_text(f"mutated-content-{calls['n']}")
        os.utime(f1, ns=(st0.st_atime_ns, st0.st_mtime_ns + calls["n"] * 1_000_000))
        return pre

    monkeypatch.setattr(os, "fstat", _flicker_always)
    with pytest.raises(FingerprintUnavailable):
        adapters_base._entry_for_path(f1)
    # The retry path was actually exercised, not short-circuited.
    assert calls["n"] >= 2


def test_fingerprint_retry_read_stays_within_remaining_budget(tmp_path, monkeypatch):
    """The retry pass must spend only what is left of the read budget, not
    the whole budget again (plan steps 5-7): a file that grows between the
    passes must not let one path read ~2x its allowance (a reviewer probe read
    16 + 25 = 41 bytes against a 32-byte budget before raising)."""
    f1 = tmp_path / "a.txt"
    f1.write_bytes(b"a" * 16)
    st0 = f1.stat()

    real_fstat = os.fstat
    calls = {"n": 0}

    def _grow_after_first_pass(fd):
        calls["n"] += 1
        if calls["n"] == 2:
            # The post-read check of pass 1: the file grows to 25 bytes and
            # its mtime moves, so pass 1 is unstable and a retry is taken.
            f1.write_bytes(b"a" * 25)
            os.utime(f1, ns=(st0.st_atime_ns, st0.st_mtime_ns + 1_000_000))
        return real_fstat(fd)

    phase = adapters_base.FingerprintPhase()
    monkeypatch.setattr(adapters_base, "FINGERPRINT_MAX_BYTES", 32)
    monkeypatch.setattr(os, "fstat", _grow_after_first_pass)
    with pytest.raises(FingerprintUnavailable):
        fingerprint_paths([f1], phase=phase)
    monkeypatch.undo()

    assert calls["n"] >= 2
    # Budget 32 plus the single over-limit probe byte, never 16 + 25.
    assert phase.bytes_read <= 32 + 1


def test_fingerprint_unavailable_results_never_compare_equal(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters_base, "FINGERPRINT_MAX_BYTES", 1)
    big = tmp_path / "big.txt"
    big.write_text("more than one byte")
    with pytest.raises(FingerprintUnavailable):
        fingerprint_paths([big])
    with pytest.raises(FingerprintUnavailable):
        fingerprint_paths([big])
    # Both calls raised rather than returning any string at all -- there is
    # no marker value for a caller to accidentally compare as "equal".


# ---------------------------------------------------------------------------
# launch_argv_ok / emitted_outcome
# ---------------------------------------------------------------------------


def test_launch_argv_ok_true_for_non_launch_points():
    candidate = make_candidate(id="cand-a", payload="anything at all")
    validated = _validated_for(candidate, point=Point.POST_TOOL_OUTPUT)
    assert launch_argv_ok(candidate, validated) is True


def test_launch_argv_ok_requires_exact_template_at_launch_profile():
    good = make_candidate(id="profile-x", payload=[*LAUNCH_ARGV_TEMPLATE, "profile-x"])
    validated_good = _validated_for(good, point=Point.LAUNCH_PROFILE)
    assert launch_argv_ok(good, validated_good) is True

    wrong_id = make_candidate(id="profile-x", payload=[*LAUNCH_ARGV_TEMPLATE, "someone-else"])
    validated_wrong = _validated_for(wrong_id, point=Point.LAUNCH_PROFILE)
    assert launch_argv_ok(wrong_id, validated_wrong) is False

    not_a_list = make_candidate(id="profile-x", payload="claude plugin enable --scope local profile-x")
    validated_str = _validated_for(not_a_list, point=Point.LAUNCH_PROFILE)
    assert launch_argv_ok(not_a_list, validated_str) is False


def test_emitted_outcome_rejects_bad_launch_payload():
    candidate = make_candidate(id="profile-x", payload="not the template")
    validated = _validated_for(candidate, point=Point.LAUNCH_PROFILE)
    with pytest.raises(ValueError):
        emitted_outcome(candidate, validated, mode="active")


def test_emitted_outcome_rejects_unbound_candidate():
    bound = make_candidate(id="cand-a", payload="x")
    validated = _validated_for(bound, point=Point.POST_TOOL_OUTPUT)
    unbound = make_candidate(id="cand-b", payload="y")
    with pytest.raises(ValueError):
        emitted_outcome(unbound, validated, mode="active")


def test_emitted_outcome_produces_consistent_outcome():
    candidate = make_candidate(id="cand-a", payload="replacement text")
    validated = _validated_for(candidate, point=Point.POST_TOOL_OUTPUT)
    outcome = emitted_outcome(candidate, validated, mode="active")
    assert outcome.kind == "emitted"
    assert outcome.payload_sha256 == hashlib.sha256(outcome.render_bytes).hexdigest()
    assert outcome.payload_sha256 == outcome.binding_sha256


def test_outcome_post_init_rejects_inconsistent_emitted_outcome():
    with pytest.raises(ValueError):
        Outcome(kind="emitted", mode="active", render_bytes=b'"x"', payload_sha256="deadbeef", binding_sha256="deadbeef")
    with pytest.raises(ValueError):
        Outcome(
            kind="emitted",
            mode="active",
            render_bytes=b'"x"',
            payload_sha256=hashlib.sha256(b'"x"').hexdigest(),
            binding_sha256="not-the-same-hash",
        )
    with pytest.raises(ValueError):
        Outcome(kind="emitted", mode="active")


# ---------------------------------------------------------------------------
# authorize_by_policy
# ---------------------------------------------------------------------------


def _policy(**overrides) -> AuthorizationPolicy:
    kwargs = dict(integration="selftest", point=Point.POST_TOOL_OUTPUT)
    kwargs.update(overrides)
    return AuthorizationPolicy(**kwargs)


def test_authorize_by_policy_allows_when_everything_matches():
    candidate = make_candidate(id="cand-a", payload="x")
    validated = _validated_for(candidate, point=Point.POST_TOOL_OUTPUT)
    policy = _policy(allow_all=True)
    assert authorize_by_policy(candidate, validated, policy) is True


def test_authorize_by_policy_denies_when_not_a_member_of_validated_candidates():
    member = make_candidate(id="cand-a", payload="x")
    validated = _validated_for(member, point=Point.POST_TOOL_OUTPUT)
    # A separate object that merely has the same id/payload is not `member`
    # by identity, so it must be denied even though every field matches.
    lookalike = make_candidate(id="cand-a", payload="x")
    policy = _policy(allow_all=True)
    assert authorize_by_policy(lookalike, validated, policy) is False


def test_authorize_by_policy_denies_on_integration_or_point_mismatch():
    candidate = make_candidate(id="cand-a", payload="x")
    validated = _validated_for(candidate, point=Point.POST_TOOL_OUTPUT, integration="selftest")
    wrong_integration = _policy(integration="other", point=Point.POST_TOOL_OUTPUT, allow_all=True)
    wrong_point = _policy(integration="selftest", point=Point.PRE_TOOL, allow_all=True)
    assert authorize_by_policy(candidate, validated, wrong_integration) is False
    assert authorize_by_policy(candidate, validated, wrong_point) is False


def test_authorize_by_policy_deny_ids_wins_over_allow_all():
    candidate = make_candidate(id="cand-a", payload="x")
    validated = _validated_for(candidate, point=Point.POST_TOOL_OUTPUT)
    policy = _policy(allow_all=True, deny_ids=frozenset({"cand-a"}))
    assert authorize_by_policy(candidate, validated, policy) is False


def test_authorize_by_policy_allow_ids_and_allow_id_prefixes():
    candidate = make_candidate(id="safe-cand", payload="x")
    validated = _validated_for(candidate, point=Point.POST_TOOL_OUTPUT)
    denied_policy = _policy(allow_all=False, allow_ids=frozenset(), allow_id_prefixes=())
    assert authorize_by_policy(candidate, validated, denied_policy) is False

    by_id = _policy(allow_ids=frozenset({"safe-cand"}))
    assert authorize_by_policy(candidate, validated, by_id) is True

    by_prefix = _policy(allow_id_prefixes=("safe-",))
    assert authorize_by_policy(candidate, validated, by_prefix) is True


def test_authorize_by_policy_denies_on_payload_binding_mismatch():
    candidate = make_candidate(id="cand-a", payload="x")
    validated = _validated_for(candidate, point=Point.POST_TOOL_OUTPUT)
    # Swap in a candidate with the same id but a different payload, still
    # `is` a member of `validated.candidates` by construction here -- this
    # simulates a stale/edited payload whose hash no longer matches the
    # binding computed at validation time.
    tampered = make_candidate(id="cand-a", payload="tampered")
    object.__setattr__(validated, "candidates", (tampered,))
    policy = _policy(allow_all=True)
    assert authorize_by_policy(tampered, validated, policy) is False


# ---------------------------------------------------------------------------
# authorize() bodies: AST allowlist -- no adapter may read self/global state
# ---------------------------------------------------------------------------

_ALLOWED_AUTHORIZE_GLOBAL_NAMES = frozenset({"authorize_by_policy", "contract", "any", "dict", "isinstance", "len"})


def _find_functions(tree: ast.AST, *, names: frozenset[str] | None = None):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if names is None or node.name in names:
                yield node


def _adapter_authorize_bodies():
    """Every `authorize` method body found in the shipped adapters."""
    import clavain_selector.adapters.claude_code as claude_code_mod
    import clavain_selector.adapters.stubs as stubs_mod

    found = []
    for mod in (claude_code_mod, stubs_mod):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=mod.__file__)
        for fn in _find_functions(tree, names=frozenset({"authorize"})):
            found.append((mod.__name__, fn))
    return found


def _is_authorize_by_policy_delegate(fn: ast.FunctionDef) -> bool:
    """True iff `fn`'s body is exactly `return authorize_by_policy(chosen, validated, policy)`."""
    if len(fn.body) != 1:
        return False
    stmt = fn.body[0]
    if not isinstance(stmt, ast.Return) or stmt.value is None:
        return False
    call = stmt.value
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "authorize_by_policy"):
        return False
    arg_names = [a.id for a in call.args if isinstance(a, ast.Name)]
    return arg_names == ["chosen", "validated", "policy"] and not call.keywords


def test_every_adapter_authorize_delegates_verbatim():
    bodies = _adapter_authorize_bodies()
    assert bodies, "expected at least one authorize() method to check"
    for modname, fn in bodies:
        assert _is_authorize_by_policy_delegate(fn), (
            f"{modname}.{fn.name} authorize() must be exactly "
            f"'return authorize_by_policy(chosen, validated, policy)'"
        )


def _body_nodes(fn: ast.AST):
    """Walk only `fn`'s body statements -- never its signature (parameter
    annotations, defaults, decorators, or return annotation), so type names
    like `Candidate` or `bool` used purely as annotations are never mistaken
    for runtime global reads."""
    for stmt in fn.body:
        yield from ast.walk(stmt)


def _names_read_in(fn: ast.AST) -> set[str]:
    """Every bare Name (Load context) and attribute-root Name read within
    `fn`'s body (signature annotations are excluded -- see `_body_nodes`)."""
    names: set[str] = set()
    for node in _body_nodes(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        if isinstance(node, ast.Attribute) and node.attr in ("_last",):
            names.add("<self-attribute-read>")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            names.add("<getattr-call>")
    return names


def test_authorize_by_policy_source_has_no_disallowed_global_reads():
    source = Path(adapters_base.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=adapters_base.__file__)
    (fn,) = list(_find_functions(tree, names=frozenset({"authorize_by_policy"})))
    params = {a.arg for a in fn.args.args}
    read = _names_read_in(fn)
    # Every Name read must be either a parameter, a locally-bound name, or on
    # the allowlist (the shared `contract` module and a short list of
    # builtins) -- never some other module global.
    local_assigns = {
        node.id
        for node in _body_nodes(fn)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    disallowed = read - params - local_assigns - _ALLOWED_AUTHORIZE_GLOBAL_NAMES
    assert disallowed <= {"chosen", "validated", "policy"}, disallowed


def test_authorize_self_state_fixture_is_rejected_by_the_checker():
    """The negative fixture's every `authorize*`-named function violates the
    allowlist rule (self-state, a module global, or a helper call) -- the
    checker used above must actually catch each shape, not just pass on the
    real adapters by coincidence."""
    fixture_path = _FIXTURES_ROOT / "authorize_self_state.py"
    source = fixture_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(fixture_path))

    violations = 0
    for fn in _find_functions(tree):
        if not fn.name.startswith("authorize"):
            continue
        if fn.name == "authorize_by_policy":
            continue
        if _is_authorize_by_policy_delegate(fn):
            continue  # would be fine; none of the fixture's functions are.
        violations += 1

    assert violations >= 4, "expected every authorize* method in the negative fixture to violate the shape check"

    # And the module-level `authorize_by_policy`-shaped function in the
    # fixture must fail the disallowed-global-reads check, the same way the
    # real one (checked above) passes it.
    (bad_fn,) = [
        fn for fn in _find_functions(tree, names=frozenset({"authorize_by_policy_reads_module_global"}))
    ]
    params = {a.arg for a in bad_fn.args.args}
    local_assigns = {
        node.id
        for node in ast.walk(bad_fn)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    read = _names_read_in(bad_fn)
    disallowed = read - params - local_assigns - _ALLOWED_AUTHORIZE_GLOBAL_NAMES
    assert disallowed - {"chosen", "validated", "policy"}, "fixture function must read a disallowed global"
