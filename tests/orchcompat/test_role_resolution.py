"""Role x reason routing table, pinned against golden/role_resolution.json.

For each of the 17 dispatch roles, each decision-context reason set (none, the
five single reasons, all five) and each producer identity (none, an Anthropic
model, an OpenAI model), the real `ic route dispatch` resolves the role from
the policy passed explicitly. The normalized result (backend, model, effort,
tier, fallbacks, exclusions, floors, refusals) is compared with the golden.

The golden is keyed by the policy's sha256. A policy whose hash is recorded is
compared exactly. S8 sets ORCHCOMPAT_POLICY to the policy built from neutral
defaults plus the operator overlay and ORCHCOMPAT_GOLDEN_POLICY to the recorded
hash it must equal; an unrecorded hash with no override fails rather than guess.
"""
import json
import os

import pytest

import orchlib as o

pytestmark = pytest.mark.requires_ic

GOLDEN = json.loads((o.GOLDEN / "role_resolution.json").read_text())["policies"]


def _expected_table():
    pinned = os.environ.get("ORCHCOMPAT_GOLDEN_POLICY")
    sha = pinned or o.policy_sha256(o.policy_under_test())
    if sha not in GOLDEN:
        pytest.fail(
            f"policy sha256 {sha} has no recorded table; recorded: {sorted(GOLDEN)}. "
            "Regenerate with tests/orchcompat/gen_golden.py and review the diff, "
            "or set ORCHCOMPAT_GOLDEN_POLICY to the recorded hash it must equal.")
    return GOLDEN[sha]


@pytest.fixture(scope="module")
def actual_table(tmp_path_factory):
    return o.role_table(o.real_ic(), o.policy_under_test(), tmp_path_factory.mktemp("home"))


def test_every_case_matches_golden(actual_table):
    expected = _expected_table()
    assert set(actual_table) == set(expected), "case set changed (roles or reasons added/removed)"
    drift = {k: (expected[k], actual_table[k]) for k in expected if expected[k] != actual_table[k]}
    assert not drift, "routing decisions changed:\n" + "\n".join(
        f"{k}\n  golden: {json.dumps(e, sort_keys=True)}\n  actual: {json.dumps(a, sort_keys=True)}"
        for k, (e, a) in sorted(drift.items())[:10])


def test_table_covers_every_role_and_reason():
    expected = _expected_table()
    for role in o.ROLES:
        for reasons in o.REASON_SETS:
            for producer in o.PRODUCERS:
                assert o.case_key(role, reasons, producer) in expected


def test_policy_roles_are_the_pinned_role_list():
    import yaml
    roles = yaml.safe_load(o.policy_under_test().read_text())["dispatch"]["roles"]
    assert sorted(roles) == sorted(o.ROLES), "a role was added or removed: extend orchlib.ROLES and regenerate"


@pytest.mark.parametrize("role", ["validation", "cross-lab-review", "plan-review"])
def test_review_roles_refuse_without_producer(role, home):
    got = o.resolve_role(o.real_ic(), o.policy_under_test(), role, (), None, home)
    assert got["rc"] == 1 and "requires --producer-identity" in got["error"]


def test_unknown_role_and_unknown_reason_are_refused(home):
    ic, pol = o.real_ic(), o.policy_under_test()
    assert o.resolve_role(ic, pol, "no-such-role", (), None, home) == {
        "rc": 1, "error": 'role "no-such-role": no dispatch profile found'}
    got = o.resolve_role(ic, pol, "planning", ("bogus",), None, home)
    assert got == {"rc": 1, "error": 'unknown classification reason "bogus"'}


def test_missing_policy_file_is_refused(home, tmp_path):
    got = o.resolve_role(o.real_ic(), tmp_path / "absent.yaml", "planning", (), None, home)
    assert got["rc"] != 0
