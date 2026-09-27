"""Tests for scripts/clavain_selector/questions.py (mk-42j9.7 Task R6a)."""

from __future__ import annotations

import copy
import random

import pytest
from selector_helpers import selector_socket_guard  # noqa: F401

import clavain_selector.contract as contract
import clavain_selector.questions as questions
from clavain_selector.questions import (
    ESCALATE_CRITERION,
    ESCALATE_ID,
    QUESTION_SET_VERSION,
    ChoiceQuestion,
    NoulQuestion,
    QuestionBattery,
    build_battery,
    questions_sha256,
)

# The canonical order of {"a": ..., "b": ...} under contract.canonical_order,
# computed once when this test was written and pinned as literals below.
_TWO_VIEWS = [
    {"id": "a", "description": "Do A."},
    {"id": "b", "description": "Do B."},
]
_TWO_ORDER = ["a", "b"]
_HASH_FIT_TRUE = "4d25f926d5d1bbf7d3005ec03cc40a3961137be3b4c777bff17736f75296db7c"
_HASH_FIT_FALSE = "04840323ade9e97da07fee791cf4c9999f49a70a54182588c543d610822dde3a"

_FIVE_IDS = ["e", "d", "c", "b", "a"]
_FIVE_ORDER = ["b", "a", "e", "d", "c"]


def _canonical_views(views):
    salt = contract.order_salt([v["id"] for v in views])
    import hashlib

    return sorted(
        views,
        key=lambda v: (hashlib.sha256((salt + "\0" + v["id"]).encode("utf-8")).hexdigest(), v["id"]),
    )


def test_two_view_canonical_order_pinned():
    ordered = _canonical_views(_TWO_VIEWS)
    assert [v["id"] for v in ordered] == _TWO_ORDER


def test_five_id_canonical_order_pinned():
    views = [{"id": i, "description": f"Do {i}."} for i in _FIVE_IDS]
    ordered = _canonical_views(views)
    assert [v["id"] for v in ordered] == _FIVE_ORDER


def test_questions_golden():
    ordered = _canonical_views(_TWO_VIEWS)
    battery_true = build_battery(ordered, fit_questions=True)
    battery_false = build_battery(ordered, fit_questions=False)
    assert battery_true.sha256 == _HASH_FIT_TRUE
    assert battery_false.sha256 == _HASH_FIT_FALSE
    assert battery_true.sha256 != battery_false.sha256


def test_build_battery_shape():
    ordered = _canonical_views(_TWO_VIEWS)
    battery = build_battery(ordered, fit_questions=True)
    assert battery.version == QUESTION_SET_VERSION
    assert [cid for cid, _ in battery.select.criteria] == _TWO_ORDER + [ESCALATE_ID]
    assert battery.select.criteria[-1] == (ESCALATE_ID, ESCALATE_CRITERION)
    assert [fit.candidate_id for fit in battery.fits] == _TWO_ORDER
    for index, fit in enumerate(battery.fits):
        assert fit.key == f"fit_{index}"
        assert fit.candidate_id in fit.instructions or "`" + fit.candidate_id + "`" in fit.instructions

    wire = battery.to_wire()
    assert wire["select"]["type"] == "choice"
    assert set(wire["select"]["criteria"].keys()) == {"a", "b", ESCALATE_ID}
    assert wire["fit_0"]["type"] == "noul"
    assert wire["fit_1"]["type"] == "noul"


def test_build_battery_no_fit_questions():
    ordered = _canonical_views(_TWO_VIEWS)
    battery = build_battery(ordered, fit_questions=False)
    assert battery.fits == ()
    wire = battery.to_wire()
    assert "fit_0" not in wire
    assert "select" in wire


def test_build_battery_rejects_empty():
    with pytest.raises(ValueError):
        build_battery([], fit_questions=True)


def test_build_battery_rejects_too_many():
    views = [{"id": f"c{i}", "description": "d"} for i in range(17)]
    ordered = _canonical_views(views)
    with pytest.raises(ValueError):
        build_battery(ordered, fit_questions=True)


def test_build_battery_rejects_duplicate_id():
    views = [{"id": "a", "description": "x"}, {"id": "a", "description": "y"}]
    with pytest.raises(ValueError):
        build_battery(views, fit_questions=True)


def test_build_battery_rejects_escalate_id():
    views = _canonical_views([{"id": "escalate", "description": "x"}, {"id": "b", "description": "y"}])
    with pytest.raises(ValueError):
        build_battery(views, fit_questions=True)


def test_build_battery_requires_canonical_order():
    ordered = _canonical_views(_TWO_VIEWS)
    reversed_views = list(reversed(ordered))
    with pytest.raises(contract.NonCanonicalOrder):
        build_battery(reversed_views, fit_questions=True)


def test_build_battery_permutation_invariant():
    views = [{"id": i, "description": f"Do {i}."} for i in _FIVE_IDS]
    ordered = _canonical_views(views)
    battery = build_battery(ordered, fit_questions=True)

    rng = random.Random(99)
    for _ in range(5):
        shuffled = list(views)
        rng.shuffle(shuffled)
        canon = _canonical_views(shuffled)
        other_battery = build_battery(canon, fit_questions=True)
        assert other_battery.sha256 == battery.sha256


def test_escalate_criterion_is_module_level_and_used_at_call_time(monkeypatch):
    ordered = _canonical_views(_TWO_VIEWS)
    original = build_battery(ordered, fit_questions=False).sha256

    monkeypatch.setattr(questions, "ESCALATE_CRITERION", "A different escalate criterion text.")
    patched = build_battery(ordered, fit_questions=False).sha256
    assert patched != original


def test_hand_built_battery_validates_escalate_last():
    criteria = ((ESCALATE_ID, ESCALATE_CRITERION), ("a", "Do A."))
    select = ChoiceQuestion(key="select", criteria=criteria)
    with pytest.raises(ValueError):
        QuestionBattery(version=QUESTION_SET_VERSION, fit_questions=False, select=select, fits=())


def test_hand_built_battery_validates_fit_correspondence():
    criteria = (("a", "Do A."), ("b", "Do B."), (ESCALATE_ID, ESCALATE_CRITERION))
    select = ChoiceQuestion(key="select", criteria=criteria)
    wrong_fits = (NoulQuestion(key="fit_0", candidate_id="b", instructions="x"),)
    with pytest.raises(ValueError):
        QuestionBattery(version=QUESTION_SET_VERSION, fit_questions=True, select=select, fits=wrong_fits)


def test_hand_built_battery_reorder_changes_hash():
    criteria_ab = (("a", "Do A."), ("b", "Do B."), (ESCALATE_ID, ESCALATE_CRITERION))
    criteria_ba = (("b", "Do B."), ("a", "Do A."), (ESCALATE_ID, ESCALATE_CRITERION))

    battery_ab = QuestionBattery(
        version=QUESTION_SET_VERSION,
        fit_questions=False,
        select=ChoiceQuestion(key="select", criteria=criteria_ab),
        fits=(),
    )
    battery_ba = QuestionBattery(
        version=QUESTION_SET_VERSION,
        fit_questions=False,
        select=ChoiceQuestion(key="select", criteria=criteria_ba),
        fits=(),
    )
    assert battery_ab.sha256 != battery_ba.sha256
    # But the wire-format questions dict alone (order-insignificant JSON
    # object keys) is identical -- only `candidate_order` distinguishes them.
    assert battery_ab.to_wire() == battery_ba.to_wire()


def test_questions_sha256_matches_property():
    ordered = _canonical_views(_TWO_VIEWS)
    battery = build_battery(ordered, fit_questions=True)
    assert questions_sha256(battery) == battery.sha256


def test_build_battery_never_mutates_input_views():
    ordered = _canonical_views(_TWO_VIEWS)
    before = copy.deepcopy(ordered)
    build_battery(ordered, fit_questions=True)
    assert ordered == before
