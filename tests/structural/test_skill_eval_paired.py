"""Tests for scripts/skill-eval-paired.py; no model calls."""
import importlib.util
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("skill_eval_paired", ROOT / "scripts/skill-eval-paired.py")
sep = importlib.util.module_from_spec(_spec)
sys.modules["skill_eval_paired"] = sep
_spec.loader.exec_module(sep)

CASES = [
    {"id": "a", "prompt": "p", "rubric": "r"},
    {"id": "b", "prompt": "p", "rubric": "r"},
]


def test_pairing_has_both_arms_per_case_and_repeat():
    runs = sep.build_pairs(CASES, 3)
    assert len(runs) == 2 * 3 * 2
    for case in ("a", "b"):
        for repeat in range(3):
            arms = sorted(r.arm for r in runs if r.case_id == case and r.repeat == repeat)
            assert arms == ["baseline", "injected"]


def test_pairing_rejects_zero_repeats():
    with pytest.raises(ValueError):
        sep.build_pairs(CASES, 0)


def test_blind_ids_unique_and_hide_arm():
    runs = sep.build_pairs(CASES, 3)
    sep.assign_blind_ids(runs, seed=1)
    ids = [r.blind_id for r in runs]
    assert len(set(ids)) == len(ids)
    assert not any("inject" in i or "base" in i for i in ids)


def test_judge_prompt_has_no_arm_or_skill_label():
    text = sep.judge_prompt(CASES[0], "resp")
    assert "inject" not in text.lower() and "skill" not in text.lower()


def test_executor_injection_only_in_injected_arm():
    seen = {}

    def ex(arm, case, body):
        seen[arm] = body
        return "x"

    sep.run_eval(CASES[:1], "BODY", 1, 1, ex, lambda c, r: 0.5)
    assert seen == {"injected": "BODY", "baseline": None}


def _runs(inj_scores, base_scores):
    runs = []
    for i, (a, b) in enumerate(zip(inj_scores, base_scores)):
        runs.append(sep.Run("c", i, "injected", scores=list(a)))
        runs.append(sep.Run("c", i, "baseline", scores=list(b)))
    return runs


def test_lift_and_sigma_math():
    # paired diffs: 0.5, 0.3, 0.7 -> mean 0.5, sd 0.2, se 0.2/sqrt(3)
    m = sep.compute_metrics(_runs([[0.9], [0.8], [1.0]], [[0.4], [0.5], [0.3]]), 100)
    assert m["lift"] == pytest.approx(0.5)
    assert m["lift_sigma"] == pytest.approx(0.2 / math.sqrt(3))
    assert m["bytes"] == 100


def test_single_pair_sigma_is_zero():
    m = sep.compute_metrics(_runs([[1.0]], [[0.0]]), 1)
    assert m["lift"] == 1.0 and m["lift_sigma"] == 0.0


def test_judge_sigma_pooled_over_regrades():
    # run 1 scores 0.4,0.6 (var 0.02); run 2 scores 0.5,0.5 (var 0) -> pooled 0.01
    runs = [sep.Run("c", 0, "injected", scores=[0.4, 0.6]),
            sep.Run("c", 0, "baseline", scores=[0.5, 0.5])]
    m = sep.compute_metrics(runs, 0)
    assert m["judge_sigma"] == pytest.approx(math.sqrt(0.01))
    # regrades average inside a run: lift uses mean 0.5 vs 0.5
    assert m["lift"] == pytest.approx(0.0)


def test_metric_line_format():
    lines = sep.format_metric_lines(
        {"lift": 0.5, "lift_sigma": 0.1, "bytes": 1637, "judge_sigma": 0.02})
    assert lines == [
        "METRIC lift=0.500000",
        "METRIC lift_sigma=0.100000",
        "METRIC bytes=1637",
        "METRIC judge_sigma=0.020000",
    ]


def test_parse_score():
    assert sep.parse_score("reasons\nSCORE: 0.75") == 0.75
    with pytest.raises(ValueError):
        sep.parse_score("no score")
    with pytest.raises(ValueError):
        sep.parse_score("SCORE: 7")


def test_cli_fake_end_to_end(tmp_path, capsys):
    skill = tmp_path / "SKILL.md"
    skill.write_text("hello skill")
    rc = sep.main(["--skill", str(skill), "--cases", str(ROOT / "tests/skill-evals/paired/ship.json"),
                   "--repeats", "3", "--fake-executor", "--fake-judge", "--seed", "7"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "METRIC lift=0.750000"
    assert "METRIC bytes=11" in out
    assert "METRIC judge_sigma=0.000000" in out


def test_cli_missing_dispatch_is_error(tmp_path, capsys):
    skill = tmp_path / "SKILL.md"
    skill.write_text("x")
    rc = sep.main(["--skill", str(skill), "--cases", str(ROOT / "tests/skill-evals/paired/ship.json"),
                   "--dispatch", str(tmp_path / "nope.sh")])
    assert rc == 1
