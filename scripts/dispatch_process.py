#!/usr/bin/env python3
"""Run one compact dispatch backend and retain its actual process status."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import selectors
import stat
import subprocess
import sys
import time


TERMINATION_GRACE_SECONDS = 2.0


def _write_private(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _normalized_returncode(returncode: int | None) -> int | None:
    if returncode is None:
        return None
    return 128 - returncode if returncode < 0 else returncode


def run(args: argparse.Namespace) -> int:
    received: list[int] = []

    def interrupted(signum: int, _frame: object) -> None:
        if not received:
            received.append(signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)

    capture_error: list[str] = []
    capture_forced_termination = False
    killed = False
    returncode: int | None = None
    with args.stderr.open("wb") as stderr_handle, args.events.open("wb", buffering=0) as events_handle:
        os.chmod(args.stderr, 0o600)
        os.chmod(args.events, 0o600)
        review_handle = None
        process: subprocess.Popen[bytes] | None = None
        selector: selectors.BaseSelector | None = None
        try:
            if args.review_events is not None:
                try:
                    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
                    descriptor = os.open(args.review_events, flags, 0o600)
                    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                        os.close(descriptor)
                        raise OSError("review event destination is not a regular file")
                    review_handle = os.fdopen(descriptor, "wb", buffering=0)
                except OSError as error:
                    capture_error.append(str(error))
            process = subprocess.Popen(
                args.command,
                stdout=subprocess.PIPE,
                stderr=stderr_handle,
                start_new_session=True,
            )
            assert process.stdout is not None
            stdout_fd = process.stdout.fileno()
            os.set_blocking(stdout_fd, False)
            selector = selectors.DefaultSelector()
            selector.register(stdout_fd, selectors.EVENT_READ)
            stdout_open = True
            termination_sent_at: float | None = None
            termination_pending = False
            while returncode is None or stdout_open or termination_pending:
                for _key, _mask in selector.select(timeout=0.02):
                    try:
                        chunk = os.read(stdout_fd, 65536)
                    except BlockingIOError:
                        continue
                    except OSError:
                        # Primary capture failure must take the cleanup path;
                        # treating it as EOF could leave a live backend group.
                        raise
                    if chunk:
                        try:
                            events_handle.write(chunk)
                        except OSError as error:
                            capture_error.append(str(error))
                            capture_forced_termination = True
                            selector.unregister(stdout_fd)
                            process.stdout.close()
                            stdout_open = False
                            if termination_sent_at is None:
                                try:
                                    os.killpg(process.pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass
                                termination_sent_at = time.monotonic()
                                termination_pending = True
                            continue
                        if review_handle is not None:
                            try:
                                review_handle.write(chunk)
                            except OSError as error:
                                capture_error.append(str(error))
                                review_handle.close()
                                review_handle = None
                    else:
                        selector.unregister(stdout_fd)
                        process.stdout.close()
                        stdout_open = False

                returncode = process.poll()
                now = time.monotonic()
                if received and termination_sent_at is None:
                    try:
                        os.killpg(process.pid, received[0])
                    except ProcessLookupError:
                        pass
                    termination_sent_at = now
                    termination_pending = True
                elif termination_pending and termination_sent_at is not None and now - termination_sent_at >= TERMINATION_GRACE_SECONDS:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                        killed = True
                    except ProcessLookupError:
                        pass
                    termination_pending = False
            selector.close()
            selector = None
            returncode = process.wait()
        except Exception as error:
            capture_error.append(f"supervisor failure: {error}")
            capture_forced_termination = True
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
                while process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    killed = True
                except ProcessLookupError:
                    pass
                try:
                    returncode = process.wait(timeout=TERMINATION_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    returncode = None
            if selector is not None:
                selector.close()
        finally:
            if review_handle is not None:
                review_handle.close()

    backend_code = _normalized_returncode(returncode)
    signal_code = 128 + received[0] if received else None
    _write_private(
        args.status,
        {
            "backend_process_code": backend_code,
            "wrapper_signal_code": signal_code,
            "capture_status": "failed" if capture_error else "complete",
            "capture_errors": capture_error,
            "termination_escalated": killed,
        },
    )
    if signal_code is not None:
        return signal_code
    if capture_forced_termination:
        return 1
    if capture_error:
        return 1 if backend_code == 0 else int(backend_code or 1)
    return int(backend_code or 0)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--events", type=Path, required=True)
    result.add_argument("--stderr", type=Path, required=True)
    result.add_argument("--status", type=Path, required=True)
    result.add_argument("--review-events", type=Path)
    result.add_argument("command", nargs=argparse.REMAINDER)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        print("dispatch_process: missing backend command", file=sys.stderr)
        return 2
    try:
        return run(args)
    except (OSError, ValueError) as error:
        try:
            _write_private(
                args.status,
                {"backend_process_code": None, "wrapper_signal_code": None, "capture_status": "failed", "capture_errors": [str(error)], "termination_escalated": False},
            )
        except OSError:
            pass
        print(f"dispatch_process: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
