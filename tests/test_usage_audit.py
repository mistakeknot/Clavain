import json
import os
from pathlib import Path
import subprocess


def test_terminal_audit_links_collection_without_changing_process_outcome(tmp_path):
    root = Path(__file__).parents[1]
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    audit = tmp_path / 'audit'
    (bin_dir / 'ic').write_text('#!/bin/sh\nfor arg do case "$arg" in --context=*) printf "%s" "${arg#--context=}" > "$AUDIT_FILE";; esac; done\n')
    (bin_dir / 'codex').write_text('#!/bin/sh\nexit 1\n')
    for path in bin_dir.iterdir(): path.chmod(0o755)
    evidence = tmp_path / 'evidence'
    evidence.mkdir(mode=0o700)
    events = evidence / 'events'
    events.write_text('{"type":"thread.started","thread_id":"native-child"}\n')
    script = r'''
source "$LIBRARY"
_prepare_role_audit() { DISPATCH_ID=d; ATTEMPT_ID=a; }
ROLE=routine-execution ROLE_RESOLVED=true ENGINE=codex MODEL=gpt-5.6-sol VIA=exec
WORKDIR="$TASK_DIR" CLAVAIN_USAGE_OUTPUT_DIR="$EVIDENCE" CLAVAIN_REVIEW_EVENTS="$EVENTS"
RESOLVED_ROUTE_JSON=null RESOLVED_PROFILE_JSON=null
_record_role_routing_decision 7 terminal_error failed
'''
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True, env=os.environ | dict(
        PATH=str(bin_dir) + ':' + os.environ['PATH'], LIBRARY=str(root / 'scripts/lib-dispatch-audit.sh'),
        TASK_DIR=str(tmp_path), EVIDENCE=str(evidence), EVENTS=str(events), AUDIT_FILE=str(audit),
        CLAVAIN_TASK_ENROLLMENT_ID='', CLAVAIN_INTERCORE_DB=''))
    assert result.returncode == 0, result.stderr
    receipt = json.loads(audit.read_text())
    assert receipt['result']['exit_code'] == 7
    assert receipt['result']['failure_class'] == 'terminal_error'
    assert receipt['execution']['event_log'] == str(events)
    reference = receipt['execution']['usage_collection']
    import hashlib
    assert hashlib.sha256(Path(reference['path']).read_bytes()).hexdigest() == reference['sha256']
    manifest = json.loads(Path(reference['path']).read_text())
    assert manifest['phase'] == 'completion'
    assert all(row['status'] == 'unavailable' for row in manifest['observations'])
    assert manifest['native_identity']['thread_id'] == 'native-child'
