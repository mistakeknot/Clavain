"""Direct dispatch integration: stdin, workspace admission and provider errors."""
import json
import os
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_dispatch(tmp_path, events=(), *, git=True, sandbox="workspace-write", stderr="", exit_code=0, budget=False, pool=False, block_intercept=False):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    if git:
        subprocess.run(["git", "init", "-q", str(work)], check=True)
    if block_intercept:
        (work / ".clavain").mkdir()
        (work / ".clavain" / "intercept").write_text("not a directory")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "codex"
    stub.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if '--version' in sys.argv: print('codex-cli 0.153.3'); sys.exit(0)
sys.stdin.read()
Path(os.environ['CALL']).write_text(json.dumps(sys.argv))
if '-o' in sys.argv: Path(sys.argv[sys.argv.index('-o')+1]).write_text('VERDICT: CLEAN')
for event in json.loads(os.environ['EVENTS']): print(json.dumps(event))
print(os.environ['STDERR'], file=sys.stderr)
sys.exit(int(os.environ['EXIT_CODE']))
""")
    stub.chmod(0o755)
    bb = bin_dir/'bb'
    bb.write_text('#!/bin/sh\necho \'{"thread":{"id":"thr_fixture","environment":{"hostId":"host_pda34naxgq"}}}\'\n')
    bb.chmod(0o755)
    env = dict(os.environ, PATH=str(bin_dir)+":"+os.environ["PATH"], CALL=str(tmp_path/"call"),
               EVENTS=json.dumps(events), STDERR=stderr, EXIT_CODE=str(exit_code), CLAVAIN_CONTEXT_GATEWAY_MODE="off",
               CLAVAIN_DISPATCH_FAILURE_FILE=str(tmp_path/"failure"),
               CLAVAIN_BB_DIRECT_POOL="1" if pool else "0", BB_CLI=str(bb), BB_THREAD_ID='thr_fixture',
               BB_SERVER_URL='https://bb.example', CODEX_POOL_AUTH_TOKEN='fixture-only',
               CLAVAIN_REQUIRE_USAGE="1" if budget else "0", CLAVAIN_REVIEW_EVENTS=str(tmp_path/"events"))
    # Keep stdin open deliberately: communicate() would close it and mask the bug.
    p = subprocess.Popen(["bash", str(ROOT/"scripts/dispatch.sh"), "-s", sandbox, "-C", str(work),
                          "-o", str(tmp_path/"out"), "fixture"], env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return p.wait(timeout=5)
    finally:
        p.kill()
        p.wait()
        p.stdin.close()


def test_codex_stdin_is_closed(tmp_path):
    assert run_dispatch(tmp_path) == 0


def test_read_only_non_git_gets_skip_flag(tmp_path):
    assert run_dispatch(tmp_path, git=False, sandbox="read-only") == 0
    assert "--skip-git-repo-check" in json.loads((tmp_path/"call").read_text())


def test_write_non_git_refused_before_provider(tmp_path):
    assert run_dispatch(tmp_path, git=False) != 0
    assert not (tmp_path/"call").exists()


def test_structured_quota_exit_zero(tmp_path):
    event = {"type":"event_msg", "payload":{"type":"task_complete", "error":{"codex_error_info":"usage_limit_exceeded"}}}
    assert run_dispatch(tmp_path, [event]) != 0
    assert (tmp_path/"failure").read_text().strip() == "quota_exhausted"


def test_quoted_quota_is_not_provider_failure(tmp_path):
    event = {"type":"item.completed", "item":{"type":"agent_message", "text":"ERROR: You've hit your usage limit. Quoted task text."}}
    assert run_dispatch(tmp_path, [event]) == 0


def test_stderr_only_usage_limit_is_provider_failure(tmp_path):
    assert run_dispatch(tmp_path, stderr="ERROR: You've hit your usage limit.", exit_code=7) != 0
    assert (tmp_path / "failure").read_text().strip() == "quota_exhausted"


def test_failed_dispatch_persists_redacted_intercept_evidence(tmp_path):
    event = {
        "type": "turn.failed",
        "request_id": "req-fixture",
        "error": {
            "code": "unknown_failure",
            "provider_reason": "seat_exhausted",
            "provider_token": "tok-provider-fixture-secret",
        },
    }
    stderr = "Authorization: Bearer bearer-fixture-secret\ncontact dev@example.test\n"

    assert run_dispatch(tmp_path, [event], stderr=stderr) != 0

    artifacts = list((tmp_path / "work" / ".clavain" / "intercept").glob("*.json"))
    assert len(artifacts) == 1
    raw = artifacts[0].read_text()
    assert "bearer-fixture-secret" not in raw
    assert "tok-provider-fixture-secret" not in raw
    assert "dev@example.test" not in raw
    evidence = json.loads(raw)
    assert evidence["unmapped_provider_fields"] == [
        {
            "event_type": "turn.failed",
            "fields": {
                "request_id": "req-fixture",
                "error": {
                    "code": "unknown_failure",
                    "provider_reason": "seat_exhausted",
                    "provider_token": "[REDACTED]",
                },
            },
        }
    ]
    assert (tmp_path / "work" / ".clavain" / "intercept" / ".gitignore").read_text() == "*\n"
    status = subprocess.run(
        ["git", "-C", str(tmp_path / "work"), "status", "--porcelain", "--", ".clavain/intercept"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert status.stdout == ""


def test_evidence_write_failure_preserves_provider_class(tmp_path):
    event = {
        "type": "task_complete",
        "error": {"codex_error_info": "usage_limit_exceeded"},
    }

    assert run_dispatch(tmp_path, [event], block_intercept=True) != 0
    assert (tmp_path / "failure").read_text().strip() == "quota_exhausted"


def test_denial_dominates_quota(tmp_path):
    events = [{"type":"task_complete", "error":{"codex_error_info":"usage_limit_exceeded"}},
              {"type":"error", "error":{"code":"permission_denied"}}]
    assert run_dispatch(tmp_path, events) != 0
    assert (tmp_path/"failure").read_text().strip() == "terminal_policy"


def test_recovered_codex_error_is_not_terminal(tmp_path):
    events = [{"type":"error", "message":"Transient stream error; reconnecting"},
              {"type":"turn.completed", "usage":{"input_tokens":10,"output_tokens":2}}]
    assert run_dispatch(tmp_path, events) == 0


@pytest.mark.parametrize('code,expected',[
    ('permission_denied','terminal_policy'),
    ('authentication_error','terminal_configuration'),
    ('usage_limit_exceeded','quota_exhausted'),
])
def test_coded_error_is_sticky_after_success(tmp_path,code,expected):
    events=[{'type':'error','error':{'code':code}}, {'type':'turn.completed'}]
    assert run_dispatch(tmp_path,events)!=0
    assert (tmp_path/'failure').read_text().strip()==expected


def test_error_after_success_remains_terminal(tmp_path):
    events = [{"type":"turn.completed"}, {"type":"error", "message":"Stream failed"}]
    assert run_dispatch(tmp_path, events) != 0


def test_success_does_not_erase_failed_turn(tmp_path):
    events = [{"type":"turn.failed", "error":{"code":"permission_denied"}},
              {"type":"turn.completed"}]
    assert run_dispatch(tmp_path, events) != 0
    assert (tmp_path/"failure").read_text().strip() == 'terminal_policy'


def test_budget_error_remains_terminal_accounting(tmp_path):
    assert run_dispatch(tmp_path, [{"type":"task_complete", "error":{"codex_error_info":"usage_limit_exceeded"}}], budget=True) != 0
    assert (tmp_path/"failure").read_text().strip() == "terminal_accounting"


def test_stderr_denial_dominates_quota(tmp_path):
    assert run_dispatch(tmp_path, [{"type":"task_complete", "error":{"codex_error_info":"usage_limit_exceeded"}}],
                        stderr="HTTP 403 Forbidden: policy denied") != 0
    assert (tmp_path/"failure").read_text().strip() == "terminal_policy"


def test_real_rollout_quota_fixture(tmp_path):
    event = json.loads((ROOT / "tests/fixtures/codex-usage-limit-rollout.jsonl").read_text())
    assert run_dispatch(tmp_path, [event]) != 0
    assert (tmp_path/"failure").read_text().strip() == "quota_exhausted"


def test_real_stdout_quota_fixture(tmp_path):
    events=[json.loads(line) for line in (ROOT/'tests/fixtures/codex-usage-limit-stdout.jsonl').read_text().splitlines()]
    assert run_dispatch(tmp_path, events) != 0
    assert (tmp_path/'failure').read_text().strip() == 'quota_exhausted'


def test_pooled_unknown_account_blocks_budget_acceptance(tmp_path):
    assert run_dispatch(tmp_path, pool=True, budget=True) != 0
    assert (tmp_path/'failure').read_text().strip() == 'terminal_accounting'


def test_claude_structured_quota_and_response(tmp_path):
    stub = tmp_path / "claude"
    stub.write_text("#!/usr/bin/env python3\nimport os,sys\nsys.stdin.read()\nprint(os.environ['EVENT'])\n")
    stub.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path)+":"+os.environ["PATH"], CLAVAIN_CONTEXT_GATEWAY_MODE="off",
               CLAVAIN_DISPATCH_FAILURE_FILE=str(tmp_path/"failure"))
    command = ["bash", str(ROOT/"scripts/dispatch.sh"), "--to", "claude", "-C", str(tmp_path), "-o", str(tmp_path/"out"), "fixture"]
    for event, expected in [({"type":"result", "is_error":False,"result":"VERDICT: CLEAN"}, 0),
                            ({"type":"assistant", "error":"usage_limit_exceeded"}, 1)]:
        p = subprocess.run(command, env=env | {"EVENT":json.dumps(event)}, capture_output=True, timeout=10)
        assert p.returncode == expected, p.stderr
        if not expected:
            assert "VERDICT: CLEAN" in (tmp_path/"out").read_text()
        else:
            assert (tmp_path/"failure").read_text().strip() == "quota_exhausted"
