#!/usr/bin/env python3
"""Replace only the Clavain block, following existing instruction symlinks."""
import argparse
import difflib
import os
from pathlib import Path
import stat
import tempfile

START = b'<!-- BEGIN CLAVAIN CODEX TOOL MAP -->'
END = b'<!-- END CLAVAIN CODEX TOOL MAP -->'


def replace_block(old, block):
    if block.count(START) != 1 or block.count(END) != 1 or not block.startswith(START) or not block.endswith(END):
        raise ValueError('Invalid source instruction block')
    starts, ends = old.count(START), old.count(END)
    if starts == ends == 0:
        return old + (b'\n\n' if old and not old.endswith(b'\n') else b'\n' if old else b'') + block + b'\n'
    if starts != 1 or ends != 1 or old.index(START) > old.index(END):
        raise ValueError('Malformed or duplicated managed markers; file unchanged')
    return old[:old.index(START)] + block + old[old.index(END) + len(END):]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--block', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    # Resolve before replacing, so dotfiles symlinks remain symlinks. Refuse a
    # dangling link rather than guessing where a missing installation belongs.
    target = args.file.resolve(strict=args.file.is_symlink())
    if target.exists() and not target.is_file():
        raise ValueError('Instruction target must be a regular file')
    if not target.parent.is_dir():
        raise ValueError('Instruction target directory must already exist')
    old = target.read_bytes() if target.exists() else b''
    block = args.block.read_bytes().rstrip(b'\r\n')
    new = replace_block(old, block)
    if new == old:
        if not args.dry_run:
            print(f'Managed instructions already up to date: {args.file}')
        return
    if args.dry_run:
        print(''.join(difflib.unified_diff(old.decode(errors='replace').splitlines(True), new.decode(errors='replace').splitlines(True),
                                         fromfile=str(args.file), tofile=str(args.file))), end='')
        return
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
    fd, name = tempfile.mkstemp(prefix='.clavain-instructions-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(new)
            stream.flush()
            os.chmod(name, mode)
            os.fsync(stream.fileno())
        # Refuse to overwrite a concurrent edit or a retargeted symlink.
        if args.file.resolve(strict=args.file.is_symlink()) != target or (target.read_bytes() if target.exists() else b'') != old:
            raise ValueError('Instructions changed during sync; retry after inspection')
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(f'Updated managed instructions: {args.file}')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error))
