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
        return "x", "exec-model"

    sep.run_eval(CASES[:1], "BODY", 1, 1, ex, lambda c, r, i: 0.5)
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
    assert sep.parse_score("reasons\nSCORE: 1\n\n") == 1.0
    assert sep.parse_score("SCORE: .5") == 0.5


@pytest.mark.parametrize("text", [
    "no score", "SCORE: 7", "SCORE: 1e309", "SCORE: nan", "SCORE: inf", "SCORE: -0.5",
    "SCORE: 0.75garbage", "SCORE: 0.75 extra", "SCORE: 0.5\nmore text after",
    "I would say SCORE: 0.5 here\nfinal", "SCORE: 0.2\nSCORE: 0.9", "SCORE:0.5x", "",
    "the SCORE: 0.5",
])
def test_parse_score_rejects_malformed(text):
    with pytest.raises(ValueError):
        sep.parse_score(text)


def test_judge_failure_is_not_a_measurement():
    def bad_judge(case, response, identity):
        return sep.parse_score("SCORE: 0.5garbage")

    with pytest.raises(ValueError):
        sep.run_eval(CASES[:1], "B", 1, 1, sep.fake_executor, bad_judge)


def test_judge_receives_each_responses_actual_identity():
    def ex(arm, case, body):
        return "x", ("model-inj" if body else "model-base")

    seen = []

    def judge(case, response, identity):
        seen.append(identity)
        return 0.5

    _, runs = sep.run_eval(CASES[:1], "B", 2, 1, ex, judge, seed=3)
    assert sorted(seen) == ["model-base"] * 2 + ["model-inj"] * 2
    assert {r.identity for r in runs if r.arm == "injected"} == {"model-inj"}


def test_blank_executor_identity_fails_closed():
    with pytest.raises(ValueError):
        sep.run_eval(CASES[:1], "B", 1, 1, lambda a, c, b: ("x", " "), lambda c, r, i: 0.5)


@pytest.mark.parametrize("repeats,passes", [(0, 1), (1, 0), (1, -1), (-2, 1)])
def test_counts_below_one_rejected_before_any_run(repeats, passes):
    calls = []

    def ex(arm, case, body):
        calls.append(arm)
        return "x", "m"

    with pytest.raises(ValueError):
        sep.run_eval(CASES, "B", repeats, passes, ex, lambda c, r, i: 0.5)
    assert calls == []


def _receipt(tmp_path, *recs):
    f = tmp_path / "r.jsonl"
    f.write_text("\n".join(__import__("json").dumps(r) for r in recs) + "\n")
    return f


def _rec(**kw):
    base = {"role": "routine-execution", "outcome": "completed", "exit_code": 0,
            "model": "requested-model", "observed_model": "gpt-6.1-sol"}
    base.update(kw)
    return base


def test_receipt_identity_uses_completed_model_after_fallback(tmp_path):
    f = _receipt(tmp_path, _rec(observed_model="claude-sonnet-5-5", outcome="failed", exit_code=1), _rec())
    assert sep.read_receipt_identity(f, "routine-execution") == "gpt-6.1-sol"


def test_receipt_identity_fails_closed(tmp_path):
    with pytest.raises(RuntimeError):
        sep.read_receipt_identity(tmp_path / "missing.jsonl", "routine-execution")
    with pytest.raises(RuntimeError):
        sep.read_receipt_identity(_receipt(tmp_path, _rec(role="other")), "routine-execution")
    with pytest.raises(RuntimeError):
        sep.read_receipt_identity(_receipt(tmp_path, _rec(observed_model="")), "routine-execution")
    with pytest.raises(RuntimeError):
        sep.read_receipt_identity(_receipt(tmp_path, _rec(), _rec(observed_model="other")), "routine-execution")


def _stub_dispatch(tmp_path, model):
    """A stand-in dispatch.sh: writes the reply and a receipt, logs its args."""
    stub = tmp_path / "dispatch.sh"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "out=''; role=''\n"
        "while [ $# -gt 0 ]; do case $1 in -o) out=$2; shift;; --role) role=$2; shift;;"
        " --producer-identity) echo \"$2\" >> \"$STUB_LOG\"; shift;; esac; shift; done\n"
        "printf 'reply\\nSCORE: 0.5\\n' > \"$out\"\n"
        "printf '{\"role\":\"%s\",\"outcome\":\"completed\",\"exit_code\":0,\"model\":\"requested\",\"observed_model\":\"" + model + "\"}\\n'"
        " \"$role\" >> \"$CLAVAIN_DISPATCH_RECEIPT_FILE\"\n")
    stub.chmod(0o755)
    return stub


def test_real_dispatch_path_binds_judge_to_receipt_identity(tmp_path, monkeypatch):
    log = tmp_path / "log"
    monkeypatch.setenv("STUB_LOG", str(log))
    stub = _stub_dispatch(tmp_path, "gpt-6.1-sol")
    ex, judge = sep.make_dispatch_callables(stub, "routine-execution", "cross-lab-review", 30)
    text, ident = ex("injected", CASES[0], "BODY")
    assert ident == "gpt-6.1-sol"
    assert judge(CASES[0], text, ident) == 0.5
    assert log.read_text().split() == ["gpt-6.1-sol"]


def test_duplicate_case_ids_rejected(tmp_path):
    f = tmp_path / "c.json"
    f.write_text('[{"id":"a","prompt":"p","rubric":"r"},{"id":"a","prompt":"q","rubric":"r"}]')
    with pytest.raises(ValueError, match="duplicate"):
        sep.load_cases(f)


def test_cli_rejects_zero_judge_passes(tmp_path, capsys):
    skill = tmp_path / "SKILL.md"
    skill.write_text("x")
    rc = sep.main(["--skill", str(skill), "--cases", str(ROOT / "tests/skill-evals/paired/ship.json"),
                   "--judge-passes", "0", "--fake-executor", "--fake-judge"])
    assert rc == 1 and capsys.readouterr().out == ""


def test_parser_builds_without_docstring(monkeypatch):
    monkeypatch.setattr(sep, "__doc__", None)
    assert sep.build_parser().description


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


def test_receipt_identity_ignores_requested_model_and_rejects_unknown(tmp_path):
    f = _receipt(tmp_path, _rec(model="claude-sonnet-5-5", observed_model="gpt-6.1-sol"))
    assert sep.read_receipt_identity(f, "routine-execution") == "gpt-6.1-sol"  # mismatch: observed wins
    agree = _receipt(tmp_path, _rec(model="m", observed_model="m"))
    assert sep.read_receipt_identity(agree, "routine-execution") == "m"
    for bad in ("unknown", "UNKNOWN", None):
        rec = _rec(observed_model=bad)
        with pytest.raises(RuntimeError):
            sep.read_receipt_identity(_receipt(tmp_path, rec), "routine-execution")
    rec = _rec()
    del rec["observed_model"]  # only the requested model is present
    with pytest.raises(RuntimeError):
        sep.read_receipt_identity(_receipt(tmp_path, rec), "routine-execution")


@pytest.mark.parametrize("text", [
    "reasons\nSCORE: 0.5\n\nVERDICT: PASS",
    "reasons\nSCORE: 0.5\nVERDICT: PASS WITH NOTES\n",
    "reasons\nSCORE: 0.5\n\nVERDICT: FAIL",
])
def test_score_before_dispatch_verdict_line(text):
    assert sep.parse_score(text) == 0.5


@pytest.mark.parametrize("text", [
    "SCORE: 0.5\nSCORE: 0.6\nVERDICT: PASS",
    "SCORE: 0.5\ntrailing\nVERDICT: PASS",
    "VERDICT: PASS",
    "SCORE: 0.5\nVERDICT: PASS\nmore",
    "SCORE: 0.5 VERDICT: PASS",
    "SCORE: 1e309\nVERDICT: PASS",
])
def test_verdict_suffix_keeps_strictness(text):
    with pytest.raises(ValueError):
        sep.parse_score(text)


def test_verdict_line_matches_dispatch_contract_text():
    src = (ROOT / "scripts/dispatch.sh").read_text()
    for word in ("VERDICT: PASS", "VERDICT: PASS WITH NOTES", "VERDICT: FAIL"):
        assert word in src
        assert sep._VERDICT_LINE_RE.fullmatch(word)
