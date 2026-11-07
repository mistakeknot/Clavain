"""Role resolution is bound to the policy file that was passed.

`resolve_role` asserts that the policy_hash `ic` reports is the sha256 of the
policy bytes before it normalizes the answer. These tests use a fake `ic`, so
they run without the real binary and prove the assertion itself.
"""
import json

import pytest

import orchlib as o


def _fake_ic(tmp_path, policy_hash):
    answer = {"profile_ref": "p", "profile": {"backend": "claude", "model": "m",
                                              "reasoning_effort": "high"},
              "policy_hash": policy_hash}
    path = tmp_path / "ic"
    o.write_exec(path, "#!/bin/sh\ncat <<'JSON'\n%s\nJSON\n" % json.dumps(answer))
    return str(path)


def test_matching_policy_hash_is_accepted(tmp_path):
    policy = tmp_path / "policy.yaml"
    policy.write_text("version: 1\n")
    ic = _fake_ic(tmp_path, o.policy_sha256(policy))
    (tmp_path / "home").mkdir()
    out = o.resolve_role(ic, policy, "routine-execution", (), None, tmp_path / "home")
    assert out["rc"] == 0 and out["profile_ref"] == "p"


@pytest.mark.parametrize("reported", ["0" * 64, "", None])
def test_a_different_or_missing_policy_hash_fails(tmp_path, reported):
    policy = tmp_path / "policy.yaml"
    policy.write_text("version: 1\n")
    ic = _fake_ic(tmp_path, reported)
    (tmp_path / "home").mkdir()
    with pytest.raises(AssertionError, match="different policy"):
        o.resolve_role(ic, policy, "routine-execution", (), None, tmp_path / "home")
