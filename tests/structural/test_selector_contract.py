"""Tests for scripts/clavain_selector/contract.py (mk-42j9.7 Task 1, Task R6a)."""

from __future__ import annotations

import ast
import hashlib
import json
import random
from pathlib import Path

import pytest
from selector_helpers import make_candidate, make_request, selector_socket_guard  # noqa: F401

import clavain_selector.contract as contract
from clavain_selector.contract import (
    FALLBACK_TABLE,
    AuthorizationPolicy,
    FallbackReason,
    NonCanonicalOrder,
    Point,
    Provenance,
    RejectReason,
    SessionRef,
    ValidatedCandidates,
    ValidationContext,
    canonical_order,
    canonical_request_body,
    candidate_sort_key,
    order_salt,
    payload_sha256,
    pre_eligibility,
    request_sha256,
    require_canonical,
    revalidate,
    validate_request,
    validated_candidates,
)


def test_candidate_id_pattern():
    assert validate_request(make_request(candidates=(make_candidate(id="a"),))) is None
    assert validate_request(make_request(candidates=(make_candidate(id="x.y-z_1"),))) is None
    assert validate_request(make_request(candidates=(make_candidate(id="a" * 64),))) is None

    assert validate_request(make_request(candidates=(make_candidate(id=""),))) == FallbackReason.INVALID_INPUT
    assert validate_request(make_request(candidates=(make_candidate(id="a" * 65),))) == FallbackReason.INVALID_INPUT
    assert validate_request(make_request(candidates=(make_candidate(id="a b"),))) == FallbackReason.INVALID_INPUT
    assert validate_request(make_request(candidates=(make_candidate(id="escalate"),))) == FallbackReason.INVALID_INPUT
    dup = (make_candidate(id="same"), make_candidate(id="same"))
    assert validate_request(make_request(candidates=dup)) == FallbackReason.INVALID_INPUT


def test_limits():
    long_task = make_request(task="x" * 12_001)
    assert validate_request(long_task) == FallbackReason.INVALID_INPUT

    long_context = make_request(context="x" * 40_001)
    assert validate_request(long_context) == FallbackReason.INVALID_INPUT

    too_many = tuple(make_candidate(id=f"c{i}") for i in range(17))
    assert validate_request(make_request(candidates=too_many)) == FallbackReason.INVALID_INPUT

    long_description = make_request(candidates=(make_candidate(description="x" * 2001),))
    assert validate_request(long_description) == FallbackReason.INVALID_INPUT

    assert validate_request(make_request(candidates=())) == FallbackReason.NO_CANDIDATES


def test_selector_view_omits_payload():
    canary = "CANARY-SECRET-PAYLOAD-VALUE"
    candidate = make_candidate(payload={"secret": canary})
    view = candidate.selector_view()
    assert set(view.keys()) == {"id", "description"}
    assert canary not in json.dumps(view)


def test_fallback_table_complete():
    assert set(FALLBACK_TABLE.keys()) == set(FallbackReason)
    assert len(FallbackReason) == 27
    for reason, row in FALLBACK_TABLE.items():
        assert row.applied == "native"
        assert isinstance(row.counts_toward_breaker, bool)
        assert isinstance(row.writes_record, bool)


def test_pre_eligibility():
    ctx = ValidationContext(now_ms=1_000, current_revision="rev-1", current_read_set_fingerprints={}, authorized=True)
    valid = (make_candidate(id="a"), make_candidate(id="b"))
    assert pre_eligibility(valid, ctx) is None

    expired = (make_candidate(id="a"), make_candidate(id="b", expires_at_ms=500))
    assert pre_eligibility(expired, ctx) == FallbackReason.STALE_BEFORE_SELECT


def test_revalidate_each_reason():
    ctx = ValidationContext(
        now_ms=1_000, current_revision="rev-1", current_read_set_fingerprints={"a": "fp-1"}, authorized=True
    )
    candidates = (make_candidate(id="a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1"),)

    assert revalidate(candidates, "unknown", ctx) == RejectReason.INVALID_ID

    stale_rev = (make_candidate(id="a", prepared_at_revision="rev-0", read_set_fingerprint="fp-1"),)
    assert revalidate(stale_rev, "a", ctx) == RejectReason.STALE_REVISION

    stale_read_set_ctx = ValidationContext(
        now_ms=1_000, current_revision="rev-1", current_read_set_fingerprints={"a": "fp-0"}, authorized=True
    )
    stale_read_set = (make_candidate(id="a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1"),)
    assert revalidate(stale_read_set, "a", stale_read_set_ctx) == RejectReason.STALE_READ_SET

    expired = (make_candidate(id="a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1", expires_at_ms=1),)
    assert revalidate(expired, "a", ctx) == RejectReason.EXPIRED

    assert revalidate(candidates, "a", ctx, preconditions_met=False) == RejectReason.UNMET_PRECONDITION

    unauthorized_ctx = ValidationContext(
        now_ms=1_000, current_revision="rev-1", current_read_set_fingerprints={"a": "fp-1"}, authorized=False
    )
    assert revalidate(candidates, "a", unauthorized_ctx) == RejectReason.UNAUTHORIZED

    assert revalidate(candidates, "a", ctx) is None

    # Per-candidate fingerprints: candidate "b" can be current while "a" is
    # stale, and each is judged only against its own entry in the mapping.
    multi_ctx = ValidationContext(
        now_ms=1_000,
        current_revision="rev-1",
        current_read_set_fingerprints={"a": "fp-1", "b": "fp-stale"},
        authorized=True,
    )
    multi_candidates = (
        make_candidate(id="a", prepared_at_revision="rev-1", read_set_fingerprint="fp-1"),
        make_candidate(id="b", prepared_at_revision="rev-1", read_set_fingerprint="fp-current"),
    )
    assert revalidate(multi_candidates, "a", multi_ctx) is None
    assert revalidate(multi_candidates, "b", multi_ctx) == RejectReason.STALE_READ_SET


def test_point_and_reject_reason_values_are_stable_strings():
    assert Point.LIBRARY.value == "library"
    assert Point.LAUNCH_PROFILE.value == "launch_profile"
    assert {r.value for r in RejectReason} == {
        "invalid_id", "stale_revision", "stale_read_set", "expired", "unmet_precondition", "unauthorized",
    }


def test_session_ref_is_frozen():
    ref = SessionRef(host_session_id="sess-1")
    assert ref.bead_id is None


# ---------------------------------------------------------------------------
# Task R6a: canonical order, request-body single source, question identity
# ---------------------------------------------------------------------------


def test_salt_dedup():
    assert order_salt(["a", "b", "a"]) == order_salt(["b", "a"])
    assert order_salt(["a", "b", "a"]) == order_salt(["a", "b"])
    assert order_salt(["a", "b"]) != order_salt(["a", "c"])


def test_canonical_order():
    ids = ["zeta", "alpha", "mu", "beta"]
    candidates = tuple(make_candidate(id=i) for i in ids)

    forward = canonical_order(candidates)
    reversed_order = canonical_order(tuple(reversed(candidates)))
    assert [c.id for c in forward] == [c.id for c in reversed_order]

    rng = random.Random(1234)
    for _ in range(5):
        shuffled = list(candidates)
        rng.shuffle(shuffled)
        permuted = canonical_order(tuple(shuffled))
        assert [c.id for c in permuted] == [c.id for c in forward]

    # Independently recompute the expected order from the formula itself.
    salt = order_salt(ids)
    expected_ids = sorted(ids, key=lambda i: (hashlib.sha256((salt + "\0" + i).encode("utf-8")).hexdigest(), i))
    assert [c.id for c in forward] == expected_ids

    # Changing the id set changes the salt, and can change the order.
    other = tuple(make_candidate(id=i) for i in ["zeta", "alpha", "mu", "gamma"])
    other_order = canonical_order(other)
    assert order_salt([c.id for c in candidates]) != order_salt([c.id for c in other])
    # (Not asserting the two orders differ -- that depends on hash luck --
    # only that the salts genuinely differ, i.e. depend on the id set.)
    assert len(other_order) == 4


def test_canonical_order_duplicate_ids_full_tie_break():
    dup = (
        make_candidate(id="same", description="first", payload="p1"),
        make_candidate(id="same", description="second", payload="p2"),
    )
    ordered = canonical_order(dup)
    assert len(ordered) == 2
    # require_canonical on the canonicalized duplicate-id tuple must not raise:
    # the tie is broken by the full candidate_sort_key, not left ambiguous.
    require_canonical(ordered)


def test_require_canonical():
    ids = ["zeta", "alpha", "mu", "beta"]
    candidates = tuple(make_candidate(id=i) for i in ids)
    ordered = canonical_order(candidates)

    require_canonical(ordered)  # does not raise

    with pytest.raises(NonCanonicalOrder):
        require_canonical(tuple(reversed(ordered)))

    # Still raises even if canonical_order itself is patched to be a no-op:
    # require_canonical must never call canonical_order internally.
    import unittest.mock as mock

    with mock.patch.object(contract, "canonical_order", lambda cs: tuple(cs)):
        with pytest.raises(NonCanonicalOrder):
            require_canonical(tuple(reversed(ordered)))

    # Accepts selector views (id/description mappings), not just Candidates.
    views = [c.selector_view() for c in ordered]
    require_canonical(views)
    with pytest.raises(NonCanonicalOrder):
        require_canonical(list(reversed(views)))

    # A tie between two views (no way to break it) always raises.
    tied_views = [{"id": "same", "description": "a"}, {"id": "same", "description": "b"}]
    with pytest.raises(NonCanonicalOrder):
        require_canonical(tied_views)


def test_payload_sha256_single_source():
    assert payload_sha256("abc") == payload_sha256("abc")
    assert payload_sha256({"a": 1, "b": [1, 2, 3]}) == payload_sha256({"b": [1, 2, 3], "a": 1})
    assert payload_sha256(None) == hashlib.sha256(b"null").hexdigest()

    for bad in (("tuple", "not", "json"), {1, 2, 3}, {1: "int key"}, float("nan")):
        with pytest.raises(ValueError):
            payload_sha256(bad)

    from clavain_selector.adapters import claude_code

    for value in ("hello", {"a": 1}, [1, "two", None, True], None, 3.5, 7):
        assert claude_code._hash_payload(value) == payload_sha256(value)


def test_request_body_single_source():
    request = make_request(candidates=(make_candidate(id="b"), make_candidate(id="a")))
    body = canonical_request_body(request)
    assert request_sha256(request) == hashlib.sha256(body).hexdigest()

    import clavain_selector.egress as egress

    assert egress._build_body(request) == body

    import clavain_selector.records as records
    from clavain_selector.contract import Provenance

    block = records._request_block(
        request,
        len(request.candidates),
        question_set_version="v",
        questions_sha256=None,
        provenance=Provenance.OPERATOR,
        preparer=None,
    )
    assert block["sha256"] == request_sha256(request)
    assert block["bytes"] == len(body)

    assert not hasattr(records, "_canonical_request_body")
    assert not hasattr(records, "_sha256_payload")

    # contract.py imports nothing from the clavain_selector package itself.
    contract_source = Path(contract.__file__).read_text(encoding="utf-8")
    tree = ast.parse(contract_source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("clavain_selector"):
            raise AssertionError(f"contract.py must not import from the package: {node.module}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("clavain_selector"), alias.name


# ---------------------------------------------------------------------------
# Task R6b: ValidatedCandidates / validated_candidates
# ---------------------------------------------------------------------------


def test_validated_candidates_happy_path():
    request = make_request(candidates=(make_candidate(id="b"), make_candidate(id="a")))
    bindings = tuple((c.id, payload_sha256(c.payload)) for c in request.candidates)
    vc = validated_candidates(request, bindings=bindings, provenance=Provenance.OPERATOR)
    assert vc.integration == request.integration
    assert vc.point == request.point
    assert vc.request_sha256 == request_sha256(request)
    assert vc.candidates == request.candidates
    assert vc.bindings == bindings
    assert vc.provenance is Provenance.OPERATOR


def test_validated_candidates_rejects_bindings_mismatch():
    request = make_request(candidates=(make_candidate(id="a"),))
    wrong_bindings = (("a", "0" * 64),)
    with pytest.raises(ValueError):
        validated_candidates(request, bindings=wrong_bindings, provenance=Provenance.OPERATOR)


def test_validated_candidates_rejects_structurally_invalid_request():
    invalid_request = make_request(candidates=())
    with pytest.raises(ValueError):
        validated_candidates(invalid_request, bindings=(), provenance=Provenance.OPERATOR)


def test_validated_candidates_post_init_rejects_hand_built_bad_shapes():
    good_candidate = make_candidate(id="a")
    good_bindings = ((good_candidate.id, payload_sha256(good_candidate.payload)),)

    # Too many / too few candidates.
    with pytest.raises(ValueError):
        ValidatedCandidates(
            integration="selftest", point=Point.LIBRARY, candidates=(), request_sha256="0" * 64,
            bindings=(), provenance=Provenance.OPERATOR,
        )

    # Duplicate ids.
    dup = (make_candidate(id="same"), make_candidate(id="same"))
    with pytest.raises(ValueError):
        ValidatedCandidates(
            integration="selftest", point=Point.LIBRARY, candidates=dup, request_sha256="0" * 64,
            bindings=(("same", "0" * 64), ("same", "0" * 64)), provenance=Provenance.OPERATOR,
        )

    # Invalid id pattern.
    bad_id = make_candidate(id="has a space")
    with pytest.raises(ValueError):
        ValidatedCandidates(
            integration="selftest", point=Point.LIBRARY, candidates=(bad_id,), request_sha256="0" * 64,
            bindings=(("has a space", payload_sha256(bad_id.payload)),), provenance=Provenance.OPERATOR,
        )

    # Reserved id.
    reserved = make_candidate(id="escalate")
    with pytest.raises(ValueError):
        ValidatedCandidates(
            integration="selftest", point=Point.LIBRARY, candidates=(reserved,), request_sha256="0" * 64,
            bindings=(("escalate", payload_sha256(reserved.payload)),), provenance=Provenance.OPERATOR,
        )

    # Non-canonical order.
    a = make_candidate(id="a")
    b = make_candidate(id="b")
    ordered = canonical_order((a, b))
    if ordered == (a, b):
        ordered = (b, a)  # force the reversed, non-canonical order
    else:
        ordered = (a, b)
    with pytest.raises(NonCanonicalOrder):
        ValidatedCandidates(
            integration="selftest", point=Point.LIBRARY, candidates=ordered, request_sha256="0" * 64,
            bindings=tuple((c.id, payload_sha256(c.payload)) for c in ordered), provenance=Provenance.OPERATOR,
        )

    # bindings ids don't match candidates ids.
    with pytest.raises(ValueError):
        ValidatedCandidates(
            integration="selftest", point=Point.LIBRARY, candidates=(good_candidate,), request_sha256="0" * 64,
            bindings=(("different-id", good_bindings[0][1]),), provenance=Provenance.OPERATOR,
        )

    # Sanity: the good shape passes.
    ValidatedCandidates(
        integration="selftest", point=Point.LIBRARY, candidates=(good_candidate,), request_sha256="0" * 64,
        bindings=good_bindings, provenance=Provenance.OPERATOR,
    )


def test_authorization_policy_defaults():
    policy = AuthorizationPolicy(integration="selftest", point=Point.LIBRARY)
    assert policy.allow_all is False
    assert policy.allow_ids == frozenset()
    assert policy.allow_id_prefixes == ()
    assert policy.deny_ids == frozenset()


# ---------------------------------------------------------------------------
# Order-guard AST checker
# ---------------------------------------------------------------------------

_GUARDED_NAMES = {"require_canonical", "canonical_order"}


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    parent_of: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_of[id(child)] = node
    return parent_of


def _is_allowlisted_eval_binding(node: ast.Attribute, parent: ast.AST | None, parent_of: dict[int, ast.AST], filename: str) -> bool:
    """The sole allowlisted non-call binding: `eval._REFERENCE_CANONICAL_ORDER = contract.canonical_order`.

    Only at module scope, only in a file literally named `eval.py`, only for
    that exact attribute name on both sides.
    """
    if Path(filename).name != "eval.py":
        return False
    if node.attr != "canonical_order":
        return False
    if not isinstance(parent, ast.Assign):
        return False
    if len(parent.targets) != 1:
        return False
    target = parent.targets[0]
    if not (
        isinstance(target, ast.Attribute)
        and target.attr == "_REFERENCE_CANONICAL_ORDER"
        and isinstance(target.value, ast.Name)
        and target.value.id == "eval"
    ):
        return False
    grandparent = parent_of.get(id(parent))
    return isinstance(grandparent, ast.Module)


def _check_order_guard_source(source: str, filename: str) -> list[str]:
    violations: list[str] = []
    tree = ast.parse(source, filename=filename)
    parent_of = _build_parent_map(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _GUARDED_NAMES:
                    violations.append(f"{filename}:{node.lineno}: imports {alias.name!r} by name")

        elif isinstance(node, ast.Attribute) and node.attr in _GUARDED_NAMES:
            if not (isinstance(node.value, ast.Name) and node.value.id == "contract"):
                continue
            parent = parent_of.get(id(node))
            is_call_func = isinstance(parent, ast.Call) and parent.func is node
            if is_call_func:
                continue
            if _is_allowlisted_eval_binding(node, parent, parent_of, filename):
                continue
            violations.append(f"{filename}:{node.lineno}: contract.{node.attr} used outside a direct call")

        elif isinstance(node, ast.Name) and node.id in _GUARDED_NAMES and isinstance(node.ctx, ast.Load):
            parent = parent_of.get(id(node))
            if isinstance(parent, ast.Attribute):
                continue
            violations.append(f"{filename}:{node.lineno}: bare name {node.id!r} used")

        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "contract"
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in _GUARDED_NAMES
        ):
            violations.append(f"{filename}:{node.lineno}: getattr(contract, {node.args[1].value!r})")

    return violations


_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "scripts" / "clavain_selector"
_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "selector"


def test_order_guard_module_calls():
    violations: list[str] = []
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        if path.name == "contract.py":
            continue
        violations.extend(_check_order_guard_source(path.read_text(encoding="utf-8"), str(path)))
    assert violations == []

    negative = _FIXTURES_DIR / "order_guard_import.py"
    negative_violations = _check_order_guard_source(negative.read_text(encoding="utf-8"), str(negative))
    assert len(negative_violations) >= 5

    second_module = _FIXTURES_DIR / "order_guard_second_module.py"
    second_violations = _check_order_guard_source(second_module.read_text(encoding="utf-8"), str(second_module))
    assert second_violations

    allowed_source = (
        "import clavain_selector.contract as contract\n\n"
        "eval._REFERENCE_CANONICAL_ORDER = contract.canonical_order\n"
    )
    assert _check_order_guard_source(allowed_source, "eval.py") == []

    other_name_source = (
        "import clavain_selector.contract as contract\n\n"
        "eval._SOMETHING_ELSE = contract.canonical_order\n"
    )
    assert _check_order_guard_source(other_name_source, "eval.py") != []

    nested_source = (
        "import clavain_selector.contract as contract\n\n"
        "def f():\n"
        "    eval._REFERENCE_CANONICAL_ORDER = contract.canonical_order\n"
    )
    assert _check_order_guard_source(nested_source, "eval.py") != []

    elsewhere_source = (
        "import clavain_selector.contract as contract\n\n"
        "eval._REFERENCE_CANONICAL_ORDER = contract.canonical_order\n"
    )
    assert _check_order_guard_source(elsewhere_source, "not_eval.py") != []
