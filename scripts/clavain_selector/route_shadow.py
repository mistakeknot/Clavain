"""S2 observer. Called asynchronously after the native classifier.

Only closed site/choice identifiers, SHA256 IDs and byte counts enter this
process. No classification text, prompt, file contents or subject names do.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clavain_selector import observer_privacy


SITES = {
    'route-4b': ('sprint', 'work'),
    'route-staleness': ('implemented', 'not_implemented'),
    'route-sweep': ('implemented', 'not_implemented'),
    'sprint-lane-intent': ('contradicts', 'aligned'),
}


def observe(*, site, native_choice, subject_sha256, input_bytes, output_bytes,
            plugin_root, config, project_root, batch_size=1):
    """No result is returned or interpreted; all operational failures are silent."""
    try:
        if os.environ.get('CLAVAIN_SELECTOR', '').strip().lower() == 'off':
            return
        # Load exactly the selected YAML. Missing dependency/config fails closed.
        import yaml
        config = Path(config).resolve()
        routing = yaml.safe_load(config.read_text())
        policy = routing['decision_models']['route']
        hosted = observer_privacy.enabled(policy)
        if policy.get('mode') != 'shadow' or (policy.get('backend') != 'heuristic' and not hosted):
            return
        if type(site) is not str or site not in SITES:
            return
        if type(native_choice) is not str or native_choice not in SITES[site]:
            return
        if type(subject_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', subject_sha256):
            return
        if any(type(v) is not int or not 0 <= v <= 10**9 for v in (input_bytes, output_bytes)):
            return
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            return
        divisor = 4 * batch_size
        metadata = dict(site_sha256=hashlib.sha256(site.encode()).hexdigest(),
                        subject_sha256=subject_sha256, input_bytes=input_bytes,
                        output_bytes=output_bytes, batch_size=batch_size, estimate_method=1,
                        estimated_claude_tokens_saved=(input_bytes + output_bytes + divisor - 1) // divisor,
                        observed_claude_tokens_saved=0)
        obj = dict(question=dict(id='route', text='Observe native classification',
                                 candidates=[dict(id=c, description=c) for c in SITES[site]]),
                   state=dict(site_id=site, subject_sha256=subject_sha256,
                              input_bytes=input_bytes, output_bytes=output_bytes, batch_size=batch_size),
                   native_choice=native_choice, egress_allowed=False, sources=[],
                   observation_metadata=metadata)
        if hosted:
            obj.update(privacy_contract=observer_privacy.VERSION, egress_allowed=True)
        plugin_root = Path(plugin_root).resolve()
        binary = plugin_root / 'bin' / 'clavain-cli'
        # Prefer the bundled binary; no fallback once a launched process fails.
        command = str(binary) if binary.is_file() and os.access(binary, os.X_OK) else 'clavain-cli'
        subprocess.run([command, 'decide', '--plugin-root', str(plugin_root),
                        '--config', str(config), '--project-root', str(Path(project_root).resolve())],
                       input=json.dumps(obj).encode(), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=6, check=False)
    except Exception:
        pass


class _SilentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError


def main():
    try:
        parser = _SilentParser()
        for name in ('site', 'native-choice', 'subject-sha256', 'plugin-root', 'config', 'project-root'):
            parser.add_argument('--' + name, required=True)
        for name in ('input-bytes', 'output-bytes'):
            parser.add_argument('--' + name, required=True, type=int)
        parser.add_argument('--batch-size', type=int, default=1)
        observe(**vars(parser.parse_args()))
    except (Exception, SystemExit):
        pass


if __name__ == '__main__':
    main()
