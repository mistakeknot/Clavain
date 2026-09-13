#!/usr/bin/env python3
"""Activate only Clavain in one Hermes profile, preserving unrelated config bytes.

Run with the selected Hermes virtualenv's Python; PyYAML is required. This does
not invoke Hermes, providers, models, migrations, or the full config writer.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import tempfile

try:
    import yaml
except ImportError:
    raise SystemExit('PyYAML is required; run with the selected Hermes virtualenv Python')


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                if key in result:
                    raise ValueError('Duplicate YAML mapping key; config unchanged')
                result[key] = self.construct_object(value_node, deep=deep)
            except TypeError:
                raise ValueError('Unsupported YAML mapping key; config unchanged') from None
        return result


def rewrite_config(raw):
    text = raw.decode('utf-8')
    try:
        tokens = list(yaml.scan(text))
        if any(isinstance(t, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)) for t in tokens):
            raise ValueError('YAML anchors and aliases are unsupported; config unchanged')
        root = yaml.compose(text)
        data = yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as error:
        # YAML exception strings can contain config values. Report location only.
        mark = getattr(error, 'problem_mark', None)
        location = f' at line {mark.line+1}, column {mark.column+1}' if mark else ''
        raise ValueError('Malformed YAML'+location+'; config unchanged') from None
    if root is None and not raw:
        data = {}
    elif not isinstance(root, yaml.MappingNode) or root.flow_style:
        raise ValueError('Hermes config must be an ordinary block mapping; config unchanged')
    if not all(isinstance(key, str) for key in data):
        raise ValueError('Hermes config keys must be strings; config unchanged')
    plugins = data.get('plugins', {})
    if not isinstance(plugins, dict) or not all(isinstance(key, str) for key in plugins):
        raise ValueError('plugins must be an ordinary block mapping; config unchanged')
    for key in ('enabled', 'disabled'):
        value = plugins.get(key)
        if value is not None and (not isinstance(value, list) or not all(isinstance(x, str) for x in value)):
            raise ValueError(f'plugins.{key} must be a list of plugin names or null; config unchanged')
    section = None
    if root is not None:
        for index, (key, value) in enumerate(root.value):
            if key.value == 'plugins':
                if not isinstance(value, yaml.MappingNode) or value.flow_style or key.start_mark.column:
                    raise ValueError('Flow or indented plugins mappings are unsupported; config unchanged')
                section = (index, key, value)
                break
    updated = dict(plugins)
    enabled = list(plugins.get('enabled') or [])
    if 'clavain' not in enabled:
        enabled.append('clavain')
    updated['enabled'] = enabled
    if isinstance(plugins.get('disabled'), list):
        updated['disabled'] = [name for name in plugins['disabled'] if name != 'clavain']
    if section is not None and updated == plugins:
        return raw
    newline = '\r\n' if '\r\n' in text else '\n'
    replacement = yaml.safe_dump({'plugins': updated}, sort_keys=False, allow_unicode=True).replace('\n', newline)
    if section is not None:
        index, key, value = section
        lines = text.splitlines(keepends=True)
        start_line = key.start_mark.line
        end_line = (root.value[index+1][0].start_mark.line if index+1 < len(root.value)
                    else root.end_mark.line + bool(root.end_mark.column))
        # Keep trailing comments and whitespace outside the replaced block.
        while end_line > start_line+1 and (not lines[end_line-1].strip() or lines[end_line-1].lstrip().startswith('#')):
            end_line -= 1
        start = key.start_mark.index
        end = sum(map(len, lines[:end_line]))
        return (text[:start]+replacement+text[end:]).encode('utf-8')
    end_tokens = [t for t in tokens if isinstance(t, yaml.tokens.DocumentEndToken)]
    insert = end_tokens[0].start_mark.index if end_tokens else len(text)
    prefix = text[:insert]
    separator = newline if prefix and not prefix.endswith('\n') else ''
    return (prefix+separator+replacement+text[insert:]).encode('utf-8')


def config_snapshot(path):
    target = path.resolve(strict=path.is_symlink())
    if target.exists() and not target.is_file():
        raise ValueError('Hermes config target must be a regular file')
    info = target.stat() if target.exists() else None
    return (target, path.readlink() if path.is_symlink() else None,
            (info.st_ino, info.st_mtime_ns, info.st_mode) if info else None,
            target.read_bytes() if info else b'')


def link_snapshot(path):
    if path.is_symlink():
        info = path.lstat()
        return (str(path.readlink()), info.st_ino, info.st_mtime_ns)
    if path.exists():
        raise ValueError('Refusing to replace unmanaged plugins/clavain; expected an adapter symlink')
    return None


def prepare(source, home):
    source, home = source.resolve(strict=True), home.resolve(strict=True)
    if not home.is_dir():
        raise ValueError('Selected Hermes profile must be an existing directory')
    adapter = source/'adapters/hermes'
    if not (adapter/'plugin.yaml').is_file() or not (adapter/'__init__.py').is_file():
        raise ValueError('Selected Clavain installation does not contain the Hermes adapter')
    plugins_dir = home/'plugins'
    if plugins_dir.exists() and not plugins_dir.is_dir():
        raise ValueError('Hermes plugins path must be a directory')
    link = plugins_dir/'clavain'
    link_before = link_snapshot(link)
    if link_before and Path(link_before[0]).parts[-2:] != ('adapters', 'hermes'):
        raise ValueError('Refusing to retarget an unmanaged plugins/clavain symlink')
    config = home/'config.yaml'
    before = config_snapshot(config)
    proposed = rewrite_config(before[3])
    link_current = link.is_symlink() and link.resolve() == adapter.resolve()
    return dict(source=source, home=home, adapter=adapter, link=link, link_before=link_before,
                config=config, config_before=before, proposed=proposed,
                link_current=link_current, config_current=proposed == before[3])


def assert_unchanged(plan):
    if config_snapshot(plan['config']) != plan['config_before'] or link_snapshot(plan['link']) != plan['link_before']:
        raise ValueError('Hermes profile changed during sync; retry after inspection')


def apply(plan):
    assert_unchanged(plan)
    if plan['link_current'] and plan['config_current']:
        return
    plan['link'].parent.mkdir(exist_ok=True)
    target, _, old_info, _ = plan['config_before']
    config_temp = None
    try:
        if not plan['config_current']:
            fd, name = tempfile.mkstemp(prefix='.clavain-config-', dir=target.parent)
            config_temp = Path(name)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(plan['proposed'])
                stream.flush()
                os.fchmod(stream.fileno(), stat.S_IMODE(old_info[2]) if old_info else 0o600)
                os.fsync(stream.fileno())
        with tempfile.TemporaryDirectory(prefix='.clavain-link-', dir=plan['link'].parent) as temp:
            link_temp = Path(temp)/'adapter'
            link_temp.symlink_to(plan['adapter'], target_is_directory=True)
            assert_unchanged(plan)
            if not plan['link_current']:
                os.replace(link_temp, plan['link'])
            if config_temp is not None:
                os.replace(config_temp, target)
                config_temp = None
    finally:
        if config_temp is not None:
            config_temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--home', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    plan = prepare(args.source, args.home)
    current = plan['config_current'] and plan['link_current']
    if not args.check and not args.dry_run:
        apply(plan)
    print(json.dumps(dict(source=str(plan['source']), profile_home=str(plan['home']),
                          current=current if args.check or args.dry_run else True,
                          config_change=not plan['config_current'], link_change=not plan['link_current'],
                          dry_run=args.dry_run, native_discovery_verified=False,
                          parent_model_changed=False), sort_keys=True))
    return 1 if args.check and not current else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, UnicodeError) as error:
        raise SystemExit(str(error))
