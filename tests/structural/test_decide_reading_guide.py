"""Exercise the copyable reading guide with corrupt and out-of-window rows."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def test_reading_guide_skips_malformed_and_old_rows(tmp_path):
    root = Path(__file__).resolve().parents[2]
    doc = (root / 'docs/reference/decide.md').read_text()
    script = doc.split("<<'PYTHON'\n", 1)[1].split('\nPYTHON', 1)[0]
    directory = tmp_path / '.clavain/decisions'
    directory.mkdir(parents=True)
    now = dt.datetime.now(dt.timezone.utc)
    row = dict(schema='clavain-decide-v1', question_id=hashlib.sha256(b'route').hexdigest(),
               created_at=now.isoformat(), reason='shadow_mode', native_choice='work',
               decide_answer={'choice': 'work'}, band='accept')
    malformed = [None, [], 42, dict(row, decide_answer=None),
                 {k: v for k, v in row.items() if k != 'native_choice'}]
    rows = [row, dict(row, created_at=(now-dt.timedelta(days=8)).isoformat()), *malformed]
    (directory / 'synthetic.jsonl').write_text('broken\n' + '\n'.join(map(json.dumps, rows)))
    result = subprocess.run([sys.executable, '-', str(tmp_path)], input=script,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "route {'count': 1, 'completed': 1, 'agreeing': 1" in result.stdout
