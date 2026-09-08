#!/usr/bin/env python3
"""Probe an installed Hermes hook runtime in a fresh profile, without LLM calls."""
import argparse
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--hermes-source', type=Path, required=True)
args = p.parse_args()
with tempfile.TemporaryDirectory(prefix='clavain-hermes-probe-') as home:
    os.environ['HERMES_HOME'] = home
    # Exercise native user-plugin discovery without loading unrelated providers.
    bundled = Path(home)/'empty-bundled'
    bundled.mkdir()
    os.environ['HERMES_BUNDLED_PLUGINS'] = str(bundled)
    sys.path.insert(0, str(args.hermes_source.resolve()))
    from hermes_cli.plugins import get_plugin_manager, get_pre_tool_call_block_message
    from tools.registry import registry
    root = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, str(root/'scripts/sync-hermes-adapter.py'),
                    '--source', str(root), '--home', home], check=True, capture_output=True)
    manager = get_plugin_manager()
    manager.discover_and_load()
    plugin = next(p for p in manager.list_plugins() if p['name'] == 'clavain')
    assert plugin['enabled'] and not plugin['error'], plugin
    blocked = get_pre_tool_call_block_message('delegate_task', {}, session_id='isolated-probe')
    assert blocked and 'inherit' in blocked
    assert get_pre_tool_call_block_message('read_file', {}) is None
    context = manager.invoke_hook('pre_llm_call', model='unchanged-parent')
    assert 'frontier' in context[0]['context']
    assert registry.get_entry('clavain_dispatch', scope=manager.scope_key) is not None
    print(json.dumps(dict(host='hermes', native_discovery_verified=True, native_hook_verified=True, delegation_blocked=True,
                         tool_registered=True, parent_model_changed=False, model_execution_verified=False)))
