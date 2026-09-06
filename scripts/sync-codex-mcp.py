#!/usr/bin/env python3
"""Validate and replace only Clavain's managed MCP tables in Codex TOML."""
import argparse
import copy
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

if sys.version_info < (3, 11):
    raise SystemExit("Managed MCP configuration requires Python 3.11 or newer")
import tomllib

START = b"# BEGIN CLAVAIN MCP SERVERS"
END = b"# END CLAVAIN MCP SERVERS"


def parse(raw):
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        # Never print config contents: a malformed line may contain credentials.
        raise ValueError("Malformed MCP configuration TOML; file unchanged") from None


def span(raw, required=False):
    starts = list(re.finditer(rb"(?m)^" + re.escape(START) + rb"\r?$", raw))
    ends = list(re.finditer(rb"(?m)^" + re.escape(END) + rb"\r?$", raw))
    if not starts and not ends:
        if required:
            raise ValueError("Managed MCP block is missing; file unchanged")
        return None
    if len(starts) != 1 or len(ends) != 1 or starts[0].start() >= ends[0].start():
        raise ValueError("Malformed or duplicated managed MCP markers; file unchanged")
    # Leave the entire original line ending outside the replacement. A bare CR
    # at the end of a sliced TOML comment is not valid TOML.
    end = ends[0].end()
    if raw[end - 1:end] == b"\r":
        end -= 1
    return starts[0].start(), end


def validate_server(server):
    if not isinstance(server, dict):
        raise ValueError("Managed MCP server must be a table")
    transports = [key for key in ("command", "url") if key in server]
    if len(transports) != 1 or not isinstance(server[transports[0]], str) or not server[transports[0]].strip():
        raise ValueError("Managed MCP server needs exactly one nonempty command or URL")
    for key in ("args", "env_vars", "enabled_tools", "disabled_tools"):
        if key in server and (not isinstance(server[key], list) or
                              any(not isinstance(value, str) for value in server[key])):
            raise ValueError("Managed MCP list fields must contain only strings")
    for key in ("env", "http_headers", "env_http_headers"):
        if key in server and (not isinstance(server[key], dict) or
                              any(not isinstance(value, str) for value in server[key].values())):
            raise ValueError("Managed MCP environment and header fields must be string tables")
    if "url" in server and set(server) & {"args", "env", "env_vars", "cwd"}:
        raise ValueError("Managed HTTP MCP server contains stdio-only fields")
    if "command" in server and set(server) & {"http_headers", "env_http_headers", "bearer_token_env_var"}:
        raise ValueError("Managed stdio MCP server contains HTTP-only fields")
    for key in ("enabled", "required"):
        if key in server and not isinstance(server[key], bool):
            raise ValueError("Managed MCP boolean field has the wrong type")
    for key in ("cwd", "bearer_token_env_var"):
        if key in server and not isinstance(server[key], str):
            raise ValueError("Managed MCP string field has the wrong type")


def validate_manifest(path):
    try:
        data = json.loads(path.read_bytes())
    except (ValueError, UnicodeError):
        raise ValueError("Malformed plugin MCP manifest; configuration unchanged") from None
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError("Plugin MCP servers must be an object")
    for name, server in data.get("mcpServers", {}).items():
        if not name or "\n" in name or "\r" in name or not isinstance(server, dict):
            raise ValueError("Invalid plugin MCP server name or definition")
        if set(server) - {"command", "url", "args", "env", "headers", "type"}:
            raise ValueError("Plugin MCP manifest contains fields the installer cannot preserve")
        normalized = dict(server)
        if "headers" in normalized:
            normalized["http_headers"] = normalized.pop("headers")
        kind = normalized.pop("type", None)
        if kind is not None and kind != ("stdio" if "command" in normalized else "http"):
            raise ValueError("Unsupported or conflicting plugin MCP transport type")
        validate_server(normalized)


def tables(block, legacy=False):
    data = parse(block)
    allowed = {"mcp_servers", "mcp"} if legacy else {"mcp_servers"}
    if set(data) - allowed or ("mcp" in data and (
            not isinstance(data["mcp"], dict) or set(data["mcp"]) != {"servers"})):
        raise ValueError("Managed block may contain only supported MCP server tables")
    result = []
    for path in [("mcp_servers",), ("mcp", "servers")]:
        value = data
        for key in path:
            value = value.get(key, {}) if isinstance(value, dict) else None
        if not isinstance(value, dict):
            raise ValueError("Managed MCP servers must be tables")
        for name, server in value.items():
            validate_server(server)
            result.append((path + (name,), server))
    names = [path[-1] for path, _ in result]
    if len(names) != len(set(names)):
        raise ValueError("Managed MCP server is duplicated across schemas")
    return result


def without_managed(data, managed):
    data = copy.deepcopy(data)
    for path, expected in managed:
        parent = data
        ancestors = []
        for key in path[:-1]:
            if not isinstance(parent, dict) or key not in parent:
                raise ValueError("Managed marker context is ambiguous; file unchanged")
            ancestors.append((parent, key))
            parent = parent[key]
        if not isinstance(parent, dict) or parent.get(path[-1]) != expected:
            raise ValueError("Managed server conflicts with surrounding configuration")
        del parent[path[-1]]
        for parent, key in reversed(ancestors):
            if parent[key] == {}:
                del parent[key]
    # Explicit empty MCP parent declarations have the same server semantics as
    # absent parents. Their original bytes remain untouched outside the block.
    if isinstance(data.get("mcp"), dict) and data["mcp"].get("servers") == {}:
        del data["mcp"]["servers"]
    for key in ("mcp", "mcp_servers"):
        if data.get(key) == {}:
            del data[key]
    return data


def replacement(old, block, check=False, remove=False):
    old_data = parse(old)
    bounds = span(old, required=check)
    managed = []
    if bounds:
        managed = tables(old[bounds[0]:bounds[1]], legacy=not check)
    old_unmanaged = without_managed(old_data, managed)
    if remove:
        if not bounds:
            return old
        new = old[:bounds[0]] + old[bounds[1]:]
        desired = []
    else:
        block = block.rstrip(b"\r\n")
        block_bounds = span(block, required=True)
        if block_bounds != (0, len(block)):
            raise ValueError("Source block must consist only of managed MCP content")
        desired = tables(block)
        if bounds:
            new = old[:bounds[0]] + block + old[bounds[1]:]
        else:
            separator = b"\n\n" if old and not old.endswith(b"\n") else b"\n" if old else b""
            new = old + separator + block + b"\n"
    try:
        new_data = parse(new)
    except ValueError:
        raise ValueError("Managed MCP content conflicts with surrounding configuration; file unchanged") from None
    if without_managed(new_data, desired) != old_unmanaged:
        raise ValueError("MCP update would change unrelated configuration; file unchanged")
    if check and dict(managed) != dict(desired):
        raise ValueError("Managed MCP tables differ from the source manifest")
    return new


def preserve_permissions(source, destination):
    if sys.platform == "darwin":
        # macOS copyfile.h: COPYFILE_SECURITY = COPYFILE_STAT | COPYFILE_ACL.
        # chmod alone drops ACL allow/deny entries when replacing the inode.
        library = ctypes.CDLL(None, use_errno=True)
        copyfile = library.copyfile
        copyfile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_uint32]
        copyfile.restype = ctypes.c_int
        if copyfile(os.fsencode(source), os.fsencode(destination), None, 3) != 0:
            raise OSError(ctypes.get_errno(), "Unable to preserve MCP configuration permissions")
    else:
        shutil.copystat(source, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--validate-manifest", type=Path)
    parser.add_argument("--block", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--check", action="store_true")
    flags.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    if args.validate_manifest:
        validate_manifest(args.validate_manifest)
        return
    if args.file is None:
        parser.error("--file is required")
    if not args.remove and args.block is None:
        parser.error("--block is required unless removing the managed block")
    target = args.file.resolve(strict=args.file.is_symlink())
    if target.exists() and not target.is_file():
        raise ValueError("MCP configuration target must be a regular file")
    old = target.read_bytes() if target.exists() else b""
    block = args.block.read_bytes() if args.block else b""
    new = replacement(old, block, args.check, args.remove)
    if args.check or args.dry_run or old == new:
        return
    if not target.parent.is_dir():
        raise ValueError("MCP configuration directory must already exist")
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
    fd, name = tempfile.mkstemp(prefix=".clavain-mcp-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(new)
            stream.flush()
            os.chmod(name, mode)
            if target.exists():
                preserve_permissions(target, name)
            os.fsync(stream.fileno())
        if args.file.resolve(strict=args.file.is_symlink()) != target or (
                target.read_bytes() if target.exists() else b"") != old:
            raise ValueError("MCP configuration changed during sync; retry after inspection")
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error))
