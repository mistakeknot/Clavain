from __future__ import annotations

import hashlib
import fcntl
import json
import os
import resource
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

from native_supervisor_support import (
    DEADLINES_NS,
    INTEGRATION_UNAVAILABLE,
    PREREQUISITE_FAILURE,
    PROTOCOL_VERSION,
    RuntimeTrace,
    blocked_pending_term_preexec,
    build_supervisor,
    default_sigchld_preexec,
    ignored_signal_preexec,
    ignored_sigchld_preexec,
    ignored_term_preexec,
    launcher_argv,
    make_bash_launcher,
    read_event_lines,
    wait_pid_gone,
)


@pytest.fixture(scope="session")
def supervisor_build(tmp_path_factory):
    return build_supervisor(tmp_path_factory.mktemp("native-supervisor-build"))


@pytest.fixture(scope="session")
def supervisor_probe_build(tmp_path_factory):
    build = build_supervisor(tmp_path_factory.mktemp("native-supervisor-probe"), probe=True)
    print(build.provenance.read_text())
    return build


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_failure_cleanup_uses_signal_accepted_after_cleanup_entry(
    supervisor_probe_build, tmp_path, signum
):
    trace = RuntimeTrace(tmp_path / "failure-cleanup.trace")
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "import time;time.sleep(10)",
        supervisor_args=("--fail-after-workload-start",),
        env={**os.environ, **supervisor_probe_build.environment(),
             **trace.environment("failure-signal")},
    )
    try:
        boundary = trace.wait(lambda r: r["kind"] == "failure-pause")
        assert boundary["pid"] == process.pid
        # S is stopped at the actual first cleanup TERM syscall, after entry.
        started = time.monotonic()
        os.kill(process.pid, signum)
        os.kill(process.pid, signal.SIGCONT)
        trace.wait(lambda r: r["kind"] == "accepted", timeout=1)
        process.wait(timeout=2.2)
        assert process.returncode == 128 + signum
        assert time.monotonic() - started < 2.0
    finally:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGCONT)
            process.kill()
            process.wait(timeout=3)
        os.close(events_fd)
        trace.retain()


@pytest.mark.parametrize("signum", [None, signal.SIGINT, signal.SIGTERM])
def test_anchor_readiness_failure_retains_first_accepted_signal(
    supervisor_probe_build, tmp_path, signum
):
    trace = RuntimeTrace(tmp_path / "anchor-failure.trace")
    ready_read, ready_write = os.pipe()
    resume_read, resume_write = os.pipe()
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "raise SystemExit(0)",
        supervisor_args=("--phase-pause", "before-anchor-ready",
                         str(ready_write), str(resume_read)),
        extra_pass_fds=(ready_write, resume_read),
        env={**os.environ, **supervisor_probe_build.environment(), **trace.environment()},
    )
    os.close(ready_write)
    os.close(resume_read)
    try:
        ready, _, _ = select.select([ready_read], [], [], 3)
        assert ready and os.read(ready_read, 1) == b"R"
        started = time.monotonic()
        if signum is not None:
            os.kill(process.pid, signum)
            trace.wait(lambda r: r["kind"] == "accepted", timeout=1)
        os.close(resume_write)
        resume_write = -1
        process.wait(timeout=2.2)
        assert process.returncode == (125 if signum is None else 128 + signum)
        assert time.monotonic() - started < 2.0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        if resume_write >= 0:
            os.close(resume_write)
        os.close(ready_read)
        os.close(events_fd)
        trace.retain()


def test_stalled_q_retirement_accounts_for_each_guardian_before_supervisor_exit(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "q-retirement.trace")
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "raise SystemExit(0)",
        supervisor_args=("--observer-mode", "stalled"),
        env={**os.environ, **supervisor_probe_build.environment(), **trace.environment(),
             "NFS_TEST_G_OBSERVER_STALL": "1"},
    )
    try:
        trace.wait(lambda r: r["text"].startswith("RELEASE 3 2 Q "))
        process.wait(timeout=5)
        records = trace.records()
        guardians = {int(r["text"].split()[3]) for r in records
                     if r["text"].startswith(("GROUP_READY 2 2 ", "GROUP_READY 2 3 "))}
        assert guardians, records
        root_actions = [r for r in records if r["pid"] == process.pid]
        retired = {r["a"] for r in root_actions
                   if (r["kind"] == "kill" and r["b"] == signal.SIGKILL)
                   or r["kind"] == "reap"}
        assert guardians <= retired, f"Q guardians not retired: {guardians - retired}"
        outcomes = {r["a"]: r for r in root_actions if r["kind"] == "retire-state"}
        assert guardians <= outcomes.keys()
        assert all("cleanup=unconfirmed reaped=false generation_closed=false" in outcomes[pid]["text"]
                   for pid in guardians)
        assert all(wait_pid_gone(pid, timeout=0.2) for pid in guardians)
        assert process.returncode == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(events_fd)
        trace.retain()


@pytest.mark.parametrize("mode,expected", [("wrong-start", 1), ("wrong-fixed-start", 125)])
def test_runtime_started_pid_must_equal_registered_held_pid(
    supervisor_probe_build, tmp_path, mode, expected
):
    trace = RuntimeTrace(tmp_path / "started-binding.trace")
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "raise SystemExit(0)",
        env={**os.environ, **supervisor_probe_build.environment(), **trace.environment(mode)},
    )
    try:
        process.wait(timeout=5)
        records = trace.records()
        assert any(r["kind"] == "injected" for r in records)
        assert process.returncode == expected
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=3)
        os.close(events_fd)
        trace.retain()


def test_fixed_reap_permit_uses_received_exit_sequence(supervisor_probe_build, tmp_path):
    trace = RuntimeTrace(tmp_path / "fixed-sequence.trace")
    result = subprocess.run(
        [str(supervisor_probe_build.binary), "--probe-fixed-sequence"],
        env={**os.environ, **trace.environment()}, timeout=3,
    )
    try:
        permit = next(r for r in trace.records() if r["kind"] == "peer-permit")
        assert permit["text"] == "EXIT_PERMIT 5 7 reaped-fixed 9\n"
        assert result.returncode == 0
    finally:
        trace.retain()


@pytest.mark.parametrize("mode,code,forbidden", [
    ("join-denied", 125, "RELEASE 3 "),
    ("anchor-loss-before-w", 125, "RELEASE 3 31 "),
    ("anchor-loss-before-q", 1, "RELEASE 3 2 "),
])
def test_anchor_loss_and_failed_join_never_create_replacement_authority(
    supervisor_probe_build, tmp_path, mode, code, forbidden
):
    trace = RuntimeTrace(tmp_path / "anchor-loss.trace")
    process, events = _spawn_supervised(
        supervisor_probe_build, "raise SystemExit(0)",
        env={**os.environ, **supervisor_probe_build.environment(), **trace.environment(mode)},
    )
    try:
        process.wait(timeout=5)
        rows = trace.records()
        if mode == "join-denied":
            assert any(r["kind"] == "join-denied" for r in rows)
        else:
            loss = next(r for r in rows if r["kind"] == "anchor-lost")
            assert loss["b"] == 1, "The retained H must actually be observed terminated"
            end = next(r for r in rows if r["pid"] == process.pid and r["kind"] == "exit")
            assert end["ns"] - loss["ns"] < 2_000_000_000
        assert sum(r["text"].startswith("ANCHOR_READY 1 33 ") for r in rows) == 1
        assert not any(r["pid"] == process.pid and r["text"].startswith(forbidden) for r in rows)
        assert process.returncode == code
        for r in rows:
            if r["text"].startswith("GROUP_READY 2 "):
                assert wait_pid_gone(int(r["text"].split()[3]), timeout=0.2)
                assert wait_pid_gone(int(r["text"].split()[8]), timeout=0.2)
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=3)
        os.close(events)
        trace.retain()


def test_confirmed_guardian_reap_uses_existing_absolute_reserve(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "permit-delay.trace")
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "raise SystemExit(0)",
        env={**os.environ, **supervisor_probe_build.environment(),
             **trace.environment("permit-delay")},
    )
    try:
        process.wait(timeout=5)
        rows = trace.records()
        delayed = next(r for r in rows if r["kind"] == "permit-delayed")
        reaped = next(r for r in rows if r["pid"] == process.pid and
                      r["kind"] == "reap" and r["a"] == delayed["pid"])
        assert reaped["ns"] - delayed["ns"] >= 80_000_000
        assert process.returncode == 0
        assert not any(r["pid"] == process.pid and r["kind"] == "kill" and
                       r["a"] == delayed["pid"] for r in rows)
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=3)
        os.close(events_fd)
        trace.retain()


def test_diagnostic_drain_waits_for_both_writer_result_and_guardian_exit(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "writer-drain.trace")
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "raise SystemExit(0)",
        env={**os.environ, **supervisor_probe_build.environment(), **trace.environment()},
    )
    try:
        process.wait(timeout=5)
        rows = trace.records()
        assert any(r["text"] == "DRAINED 2 persisted\n" for r in rows)
        assert any(r["pid"] == process.pid and
                   r["text"].startswith("EXIT_PERMIT 5 31 reaped-fixed ") for r in rows)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=3)
        os.close(events_fd)
        trace.retain()


def test_anchor_and_generation_capacity_are_enforced_with_many_live_joins(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "capacity.trace")
    result = subprocess.run(
        [str(supervisor_probe_build.binary), "--probe-capacity"],
        env={**os.environ, **trace.environment()}, timeout=40,
    )
    try:
        rows = trace.records()
        capacity = next(r for r in rows if r["kind"] == "capacity")
        ready = [r["text"].split() for r in rows if r["text"].startswith("GROUP_READY 2 ")]
        assert len({fields[5] for fields in ready}) == 1
        assert {int(fields[2]) for fields in ready} >= set(range(1, 33))
        assert capacity["a"] == 32 and capacity["b"] == 0
        assert result.returncode == 0
    finally:
        trace.retain()


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_ordinary_supervisor_group_signals_retire_every_owned_helper(
    supervisor_probe_build, tmp_path, signum
):
    trace = RuntimeTrace(tmp_path / "group-signal.trace")
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "import time;time.sleep(10)", preexec_fn=os.setsid,
        env={**os.environ, **supervisor_probe_build.environment(), **trace.environment()},
    )
    try:
        trace.wait(lambda r: r["pid"] == process.pid and
                   r["text"].startswith("WORKLOAD_STARTED 1 "))
        started = time.monotonic()
        assert process.poll() is None
        os.killpg(process.pid, signum)
        process.wait(timeout=2.2)
        assert process.returncode == 128 + signum
        rows = trace.records()
        pids = set()
        for r in rows:
            fields = r["text"].split()
            if r["text"].startswith("GROUP_READY 2 "):
                pids.update((int(fields[3]), int(fields[8])))
            elif r["text"].startswith("ANCHOR_READY 1 33 "):
                pids.add(int(fields[4]))
        assert pids and all(wait_pid_gone(pid, timeout=0.1) for pid in pids)
        assert time.monotonic() - started < 2.0
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=3)
        os.close(events_fd)
        trace.retain()


def test_signal_at_actual_stalled_q_during_normal_cleanup(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "normal-q-signal.trace")
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "raise SystemExit(0)",
        supervisor_args=("--observer-mode", "stalled"),
        env={**os.environ, **supervisor_probe_build.environment(), **trace.environment()},
    )
    try:
        started_report = trace.wait(lambda r: r["text"].startswith("WORKLOAD_STARTED 3 2 "))
        q_pid = int(started_report["text"].split()[3])
        trace.wait(lambda r: r["pid"] == q_pid and r["kind"] == "stall-enter")
        started = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=2.2)
        assert process.returncode == 143
        assert time.monotonic() - started < 2.0
        assert wait_pid_gone(q_pid, timeout=0.1)
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=3)
        os.close(events_fd)
        trace.retain()


def _assert_writer_at_blocked_output(pid: int) -> None:
    # Ready is emitted only after W has received its first bytes, immediately
    # before write. With the test's filled pipe and retained reader, a sleeping
    # single-threaded W here is waiting in that write (or stopped by TOSTOP).
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        state = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="],
                               capture_output=True, text=True, timeout=1).stdout.strip()
        if state.startswith(("S", "T")):
            return
        time.sleep(0.002)
    raise AssertionError(f"W {pid} did not reach blocked output")


@pytest.mark.parametrize("mode", ["q-registration-failure", "permit-stall", "invented-observed", "stale-observed"])
def test_runtime_protocol_failure_retires_retained_children(
    supervisor_probe_build, tmp_path, mode
):
    trace = RuntimeTrace(tmp_path / "protocol-retirement.trace")
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "raise SystemExit(0)",
        env={**os.environ, **supervisor_probe_build.environment(), **trace.environment(mode)},
    )
    try:
        process.wait(timeout=5)
        records = trace.records()
        root = [r for r in records if r["pid"] == process.pid]
        if mode == "q-registration-failure":
            boundary = next(r for r in records if r["kind"] == "q-held")
            child = boundary["pid"]
            kills = [r for r in root if r["kind"] == "kill" and r["b"] == signal.SIGKILL]
            before, after = [r for r in kills if r["a"] == -child]
            pid_kill = next(r for r in kills if r["a"] == child)
            assert before["ns"] <= pid_kill["ns"] <= after["ns"]
            assert not any(r["text"].startswith("RELEASE 3 2 Q") for r in root)
        elif mode == "permit-stall":
            boundary = next(r for r in records if r["kind"] == "permit-stall")
            child = boundary["pid"]
            assert any(r["kind"] == "kill" and r["a"] == child and r["b"] == 9
                       for r in root)
            assert process.returncode == 1
        else:
            assert any(r["kind"] == "injected" for r in records)
            assert not any(" observed " in r["text"] and r["text"].startswith("EXIT_PERMIT")
                           for r in root)
            assert process.returncode == 1
        for reap in (r for r in root if r["kind"] == "reap"):
            assert not any(r["kind"] == "kill" and abs(r["a"]) == reap["a"] and
                           r["ns"] > reap["ns"] for r in root)
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=3)
        os.close(events_fd)
        trace.retain()


def test_delayed_registration_read_cannot_grant_release_after_cutoff(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "late-registration.trace")
    process, events = _spawn_supervised(
        supervisor_probe_build, "import time;time.sleep(10)",
        env={**os.environ, **supervisor_probe_build.environment(),
             **trace.environment("late-registration")},
    )
    try:
        delayed = trace.wait(lambda r: r["kind"] == "reg-delayed")
        trace.wait(lambda r: r["kind"] == "reg-peer-held")
        # Deliberately hold the completed read beyond the fixed registration
        # allowance. Late readiness cannot resurrect registration authority.
        time.sleep(1.05)
        os.kill(process.pid, signal.SIGCONT)
        trace.wait(lambda r: r["pid"] == process.pid and
                   (r["text"].startswith("RELEASE 3 1 ") or r["kind"] == "exit"), timeout=3)
        assert not any(r["pid"] == process.pid and r["text"].startswith("RELEASE 3 1 ")
                       for r in trace.records())
        process.wait(timeout=3)
        assert process.returncode == 1
        guardian = int(delayed["text"].split()[3])
        assert wait_pid_gone(guardian, timeout=0.2)
    finally:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGCONT)
            process.kill(); process.wait(timeout=3)
        os.close(events)
        trace.retain()


def test_simulated_recycled_owner_identity_never_authorizes_numeric_signals(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "lost-owner.trace")
    result = subprocess.run([str(supervisor_probe_build.binary), "--probe-lost-owner"],
                            env={**os.environ, **trace.environment("lost-owner")}, timeout=4)
    try:
        rows = trace.records()
        lost = next(r for r in rows if r["kind"] == "identity-lost")
        done = next(r for r in rows if r["kind"] == "lost-owner-done")
        assert not any(r["kind"] == "kill" and abs(r["a"]) == lost["a"] and
                       lost["ns"] <= r["ns"] <= done["ns"] for r in rows)
        assert result.returncode == 0
    finally:
        trace.retain()


def test_partial_control_line_at_eof_is_rejected(supervisor_probe_build, tmp_path):
    trace = RuntimeTrace(tmp_path / "partial-eof.trace")
    result = subprocess.run([str(supervisor_probe_build.binary), "--probe-partial-eof"],
                            env={**os.environ, **trace.environment()}, timeout=3)
    try:
        assert any(r["kind"] == "partial-eof" and r["a"] == -1 for r in trace.records())
        assert result.returncode == 0
    finally:
        trace.retain()


def test_orphaned_writer_terminal_error_retains_unavailable_output(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "orphan-writer.trace")
    master, slave = os.openpty()
    before = termios.tcgetattr(slave)
    expected = list(before)
    expected[3] |= termios.TOSTOP
    termios.tcsetattr(slave, termios.TCSANOW, expected)
    flags = fcntl.fcntl(slave, fcntl.F_GETFL)
    resume_read, resume_write = os.pipe()

    def terminal():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
        os.tcsetpgrp(slave, os.getpgrp())

    process = subprocess.Popen(
        [str(supervisor_probe_build.binary), "--probe-orphan-writer", str(slave), str(resume_read)],
        env={**os.environ, **trace.environment()}, pass_fds=(slave, resume_read),
        preexec_fn=terminal,
    )
    os.close(resume_read)
    try:
        trace.wait(lambda r: r["kind"] == "orphan-finished", timeout=2)
        rows = trace.records()
        orphaned = next(r for r in rows if r["kind"] == "orphan-ready")
        assert any(r["pid"] == orphaned["b"] and r["kind"] == "write-error" and
                   r["ns"] > orphaned["ns"] for r in rows)
        assert any(r["text"] == "DRAINED 2 unavailable\n" for r in rows)
        assert wait_pid_gone(orphaned["b"], timeout=1)
        assert termios.tcgetattr(slave) == expected
        assert fcntl.fcntl(slave, fcntl.F_GETFL) == flags
        os.write(resume_write, b"C\n")
        process.wait(timeout=2)
        assert process.returncode == 0
    finally:
        os.close(resume_write)
        if process.poll() is None:
            process.kill(); process.wait(timeout=2)
        trace.retain()
        os.close(slave); os.close(master)


def test_late_exit_permit_cannot_reopen_guardian_after_absolute_cutoff(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "late-permit.trace")
    result = subprocess.run(
        [str(supervisor_probe_build.binary), "--probe-late-permit"],
        env={**os.environ, **trace.environment("late-permit")}, timeout=5,
    )
    try:
        rows = trace.records()
        cutoff = next(r for r in rows if r["kind"] == "hard-cutoff")
        assert any(r["kind"] == "guard-paused" for r in rows)
        permit = next(r for r in rows if r["text"].startswith("EXIT_PERMIT 5 7 "))
        assert permit["ns"] > cutoff["a"]
        assert not any(r["text"].startswith("GUARD_EXITING 5 7 ") for r in rows)
        assert result.returncode == 0
    finally:
        trace.retain()


def test_late_observed_completion_is_not_accepted_as_current_proof(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "late-observed.trace")
    process, events_fd = _spawn_supervised(
        supervisor_probe_build, "raise SystemExit(0)",
        env={**os.environ, **supervisor_probe_build.environment(),
             **trace.environment("late-observed")},
    )
    try:
        trace.wait(lambda r: r["kind"] == "late-observed")
        # Deliberate descheduling past the one-second Q request deadline, after
        # actual response and reap receipt. This cannot renew the enclosing D.
        time.sleep(1.05)
        os.kill(process.pid, signal.SIGCONT)
        process.wait(timeout=3)
        rows = trace.records()
        assert not any(r["pid"] == process.pid and
                       r["text"] == "EXIT_PERMIT 5 1 observed 1\n" for r in rows)
        retired = next(r for r in rows if r["pid"] == process.pid and r["text"] == "RETIRED 1\n")
        group = next(r for r in rows if r["text"].startswith("GROUP_READY 2 1 "))
        pid = int(group["text"].split()[3])
        assert not any(r["pid"] == process.pid and r["kind"] == "kill" and
                       r["a"] == -pid and r["ns"] > retired["ns"] for r in rows)
    finally:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGCONT)
            process.kill(); process.wait(timeout=3)
        os.close(events_fd)
        trace.retain()


def test_private_strict_c11_build_records_reproducible_provenance(supervisor_build):
    record = json.loads(supervisor_build.provenance.read_text())
    argv = record["compiler_argv"]
    assert Path(argv[0]).is_absolute()
    assert argv[1:6] == ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror"]
    assert "-D_POSIX_C_SOURCE=200809L" in argv
    assert record["protocol_version"] == PROTOCOL_VERSION
    assert record["eligibility"] == "fixture-only-ineligible"
    assert record["binary_sha256"] == hashlib.sha256(supervisor_build.binary.read_bytes()).hexdigest()
    assert record["source_sha256"] == hashlib.sha256(supervisor_build.source.read_bytes()).hexdigest()
    assert record["descriptor_limits"] == {
        "soft": resource.getrlimit(resource.RLIMIT_NOFILE)[0],
        "hard": resource.getrlimit(resource.RLIMIT_NOFILE)[1],
    }
    assert len(record["load_average"]) == 3
    assert all(isinstance(value, float) for value in record["load_average"])
    assert stat_mode(supervisor_build.binary) == 0o700
    assert stat_mode(supervisor_build.provenance) == 0o600


def test_private_build_is_byte_reproducible(supervisor_build, tmp_path):
    rebuilt = build_supervisor(tmp_path / "second-build")
    assert rebuilt.record["source_sha256"] == supervisor_build.record["source_sha256"]
    assert rebuilt.record["binary_sha256"] == supervisor_build.record["binary_sha256"]


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin descriptor inventory")
def test_high_limit_sparse_inherited_descriptors_do_not_leak_or_break_startup(
    supervisor_build, tmp_path
):
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < 65_536:
        pytest.skip(f"requires an inherited high descriptor limit; observed soft={soft}")
    assert supervisor_build.record["descriptor_limits"] == {"soft": soft, "hard": hard}
    source_fd = os.open("/dev/null", os.O_RDONLY)
    inherited = []
    output = tmp_path / "sparse-fds.json"
    try:
        for minimum in (
            min(65_536, soft - 64),
            min(131_072, soft - 32),
        ):
            fd = fcntl.fcntl(source_fd, fcntl.F_DUPFD, minimum)
            os.set_inheritable(fd, True)
            inherited.append(fd)
        code = (
            "import fcntl,json;"
            f"fds={inherited!r};"
            "open_fds=[];"
            "exec(\"for fd in fds:\\n try:\\n  fcntl.fcntl(fd,fcntl.F_GETFD);open_fds.append(fd)\\n except OSError:\\n  pass\");"
            f"open({str(output)!r},'w').write(json.dumps(open_fds))"
        )
        started = time.monotonic()
        process, event_read = _spawn_supervised(
            supervisor_build, code, extra_pass_fds=tuple(inherited)
        )
        try:
            _wait_for_event(event_read, "WORKLOAD_STARTED ", timeout=3)
            startup_elapsed = time.monotonic() - started
            process.wait(timeout=5)
            read_event_lines(event_read)
            assert process.returncode == 0
            assert startup_elapsed < 3.0
            assert json.loads(output.read_text()) == []
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)
            os.close(event_read)
    finally:
        os.close(source_fd)
        for fd in inherited:
            os.close(fd)


def test_linux_conditional_branch_has_strict_c11_compile_seam(supervisor_build):
    result = subprocess.run(
        [
            str(supervisor_build.compiler),
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-D_POSIX_C_SOURCE=200809L",
            "-D_GNU_SOURCE",
            "-DNFS_TEST_LINUX_BRANCH",
            "-pthread",
            "-fsyntax-only",
            str(supervisor_build.source),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


@pytest.mark.parametrize(
    "script",
    [
        'source "$1"; NATIVE_FIXTURE_ROOT="$3"; native_fixture_run "$2"',
        'source "$1"\nNATIVE_FIXTURE_ROOT="$3"\nnative_fixture_run "$2"   \n',
    ],
)
def test_launcher_recognizes_only_exact_final_fixture_command(
    supervisor_build, tmp_path, script
):
    launcher = make_bash_launcher(supervisor_build, tmp_path / "bin")
    marker = tmp_path / "orchestrator-ran"
    guarded = f'touch {marker}; {script}'
    result = subprocess.run(
        launcher_argv(launcher, guarded),
        env={**os.environ, **supervisor_build.environment()},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == INTEGRATION_UNAVAILABLE
    assert not marker.exists()


@pytest.mark.parametrize(
    "script",
    [
        'printf "%s" \'native_fixture_run "$2"\'',
        '# native_fixture_run "$2"\nprintf safe',
        'cat <<EOF\nnative_fixture_run "$2"\nEOF',
        'native_fixture_run "$2"; printf trailing',
        'native_fixture_run "$3"',
    ],
)
def test_launcher_passes_quoted_commented_heredoc_and_nonfinal_forms_to_real_bash(
    supervisor_build, tmp_path, script
):
    launcher = make_bash_launcher(supervisor_build, tmp_path / "bin")
    result = subprocess.run(
        launcher_argv(launcher, script),
        env={**os.environ, **supervisor_build.environment()},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != INTEGRATION_UNAVAILABLE


def test_unrecognized_launcher_command_executes_the_captured_real_bash(
    supervisor_build, tmp_path
):
    launcher = make_bash_launcher(supervisor_build, tmp_path / "bin")
    marker = tmp_path / "real-bash-ran"
    result = subprocess.run(
        launcher_argv(launcher, f"printf real-bash > {marker}"),
        env={**os.environ, **supervisor_build.environment()},
        timeout=5,
    )
    assert result.returncode == 0
    assert marker.read_text() == "real-bash"


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        ("printf path-launch", 0),
        ('native_fixture_run "$2"', INTEGRATION_UNAVAILABLE),
    ],
)
def test_literal_path_launcher_authenticates_running_image(
    supervisor_build, tmp_path, script, expected
):
    launcher = make_bash_launcher(supervisor_build, tmp_path / "bin")
    env = {**os.environ, **supervisor_build.environment()}
    env["PATH"] = f"{launcher.parent}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        ["bash", "-c", script, "fixture", "library", "spec", "root"],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == expected
    if expected == 0:
        assert result.stdout == "path-launch"


def test_launcher_fails_closed_when_provenance_does_not_match(supervisor_build, tmp_path):
    launcher = make_bash_launcher(supervisor_build, tmp_path / "bin")
    env = {**os.environ, **supervisor_build.environment()}
    env["NFS_EXPECTED_BINARY_SHA256"] = "0" * 64
    result = subprocess.run(
        launcher_argv(launcher, 'native_fixture_run "$2"'), env=env, timeout=5
    )
    assert result.returncode == PREREQUISITE_FAILURE


@pytest.mark.parametrize("preexec", [ignored_signal_preexec, ignored_term_preexec])
def test_inherited_ignored_signal_fails_before_any_work(supervisor_build, preexec):
    event_read, event_write = os.pipe()
    result = subprocess.run(
        [
            str(supervisor_build.binary),
            "--test-supervise",
            "--event-fd",
            str(event_write),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ],
        env={**os.environ, **supervisor_build.environment()},
        pass_fds=(event_write,),
        preexec_fn=preexec,
        timeout=5,
    )
    os.close(event_write)
    events = read_event_lines(event_read)
    os.close(event_read)
    assert result.returncode == PREREQUISITE_FAILURE
    assert not any(line.startswith("GROUP_READY ") for line in events)


@pytest.mark.parametrize("preexec", [ignored_signal_preexec, ignored_term_preexec])
def test_compatibility_launcher_rejects_inherited_ignored_signals(
    supervisor_build, tmp_path, preexec
):
    launcher = make_bash_launcher(supervisor_build, tmp_path / "bin")
    result = subprocess.run(
        launcher_argv(launcher, 'native_fixture_run "$2"'),
        env={**os.environ, **supervisor_build.environment()},
        preexec_fn=preexec,
        timeout=5,
    )
    assert result.returncode == PREREQUISITE_FAILURE


def test_compatibility_launcher_normalizes_ignored_sigchld_before_helpers(
    supervisor_build, tmp_path
):
    launcher = make_bash_launcher(supervisor_build, tmp_path / "bin")
    result = subprocess.run(
        launcher_argv(launcher, 'native_fixture_run "$2"'),
        env={**os.environ, **supervisor_build.environment()},
        preexec_fn=ignored_sigchld_preexec,
        restore_signals=False,
        timeout=5,
    )
    assert result.returncode == INTEGRATION_UNAVAILABLE


def test_pending_blocked_term_is_accepted_after_handler_install_without_work(supervisor_build):
    event_read, event_write = os.pipe()
    result = subprocess.run(
        [
            str(supervisor_build.binary),
            "--test-supervise",
            "--event-fd",
            str(event_write),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ],
        env={**os.environ, **supervisor_build.environment()},
        pass_fds=(event_write,),
        preexec_fn=blocked_pending_term_preexec,
        timeout=5,
    )
    os.close(event_write)
    events = read_event_lines(event_read)
    os.close(event_read)
    assert result.returncode == 128 + signal.SIGTERM
    assert not any(line.startswith("GROUP_READY ") for line in events)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_default_signal_before_handler_install_creates_no_worker(supervisor_build, signum):
    ready_read, ready_write = os.pipe()
    resume_read, resume_write = os.pipe()
    event_read, event_write = os.pipe()
    process = subprocess.Popen(
        [
            str(supervisor_build.binary),
            "--test-supervise",
            "--event-fd",
            str(event_write),
            "--pause-before-handlers",
            str(ready_write),
            str(resume_read),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ],
        env={**os.environ, **supervisor_build.environment()},
        pass_fds=(ready_write, resume_read, event_write),
    )
    os.close(ready_write)
    os.close(resume_read)
    os.close(event_write)
    assert os.read(ready_read, 1) == b"R"
    os.kill(process.pid, signum)
    process.wait(timeout=3)
    os.close(ready_read)
    os.close(resume_write)
    events = read_event_lines(event_read)
    os.close(event_read)
    assert process.returncode == -signum
    assert not any(line.startswith("GROUP_READY ") for line in events)


def _spawn_supervised(
    supervisor_build, code: str, *, supervisor_args=(), env=None, extra_pass_fds=(),
    preexec_fn=None, restore_signals=True
):
    event_read, event_write = os.pipe()
    process = subprocess.Popen(
        [
            str(supervisor_build.binary),
            "--test-supervise",
            "--event-fd",
            str(event_write),
            *supervisor_args,
            "--",
            sys.executable,
            "-c",
            code,
        ],
        env=env or {**os.environ, **supervisor_build.environment()},
        pass_fds=(event_write, *extra_pass_fds),
        preexec_fn=preexec_fn,
        restore_signals=restore_signals,
    )
    os.close(event_write)
    return process, event_read


@pytest.mark.parametrize(
    ("preexec_fn", "inherited"),
    [
        (default_sigchld_preexec, "default"),
        (ignored_sigchld_preexec, "ignored"),
    ],
)
def test_sigchld_is_default_before_helpers_and_normal_exit_status_is_retained(
    supervisor_build, preexec_fn, inherited
):
    process, event_read = _spawn_supervised(
        supervisor_build,
        "raise SystemExit(23)",
        preexec_fn=preexec_fn,
        restore_signals=False,
    )
    process.wait(timeout=5)
    events = read_event_lines(event_read)
    os.close(event_read)
    prerequisite = (
        f"SIGCHLD_PREREQUISITE inherited={inherited} "
        "inherited_no_cldwait=false current=default "
        "current_no_cldwait=false before_helpers=true"
    )
    assert prerequisite in events
    assert events.index(prerequisite) < next(
        index for index, line in enumerate(events) if line.startswith("ANCHOR_READY ")
    )
    assert process.returncode == 23


def test_guardian_registration_quiescence_and_pinned_identity(supervisor_build):
    process, event_read = _spawn_supervised(supervisor_build, "raise SystemExit(7)")
    process.wait(timeout=5)
    events = read_event_lines(event_read)
    os.close(event_read)
    ready = next(line for line in events if line.startswith("GROUP_READY ")).split()
    started = next(line for line in events if line.startswith("WORKLOAD_STARTED ")).split()
    observed = next(line for line in events if line.startswith("OBSERVED ")).split()
    retired = next(line for line in events if line.startswith("RETIRED ")).split()
    assert process.returncode == 7
    assert ready[1] == started[1] == observed[1] == retired[1]
    assert ready[2] == ready[3]
    assert ready[2] != ready[4]
    assert observed[2] == "confirmed"
    assert events.index(" ".join(observed)) < events.index(" ".join(retired))


def test_anchor_preserves_supervisor_group_and_guardian_moves_before_release(
    supervisor_build,
):
    process, event_read = _spawn_supervised(
        supervisor_build, "import time;time.sleep(0.05)"
    )
    process.wait(timeout=5)
    events = read_event_lines(event_read)
    os.close(event_read)
    anchor = next(line for line in events if line.startswith("ANCHOR_READY ")).split()
    ready = next(line for line in events if line.startswith("GROUP_READY ")).split()
    # ANCHOR_READY anchor_pid guard_pgid sid s_pgid
    assert anchor[1] == anchor[2]
    assert anchor[2] != anchor[4]
    # GROUP_READY generation guardian payload guard sid identity held
    assert ready[2] == ready[3]
    assert ready[4] == anchor[2]
    assert ready[5] == anchor[3]
    assert ready[2] != ready[4]
    assert process.returncode == 0


@pytest.mark.parametrize("session_leader", [False, True])
def test_supervisor_retains_inherited_group_and_session(
    supervisor_build, session_leader
):
    process, event_read = _spawn_supervised(
        supervisor_build,
        "import time;time.sleep(0.05)",
        preexec_fn=os.setsid if session_leader else None,
    )
    expected_pgid = os.getpgid(process.pid)
    expected_sid = os.getsid(process.pid)
    process.wait(timeout=5)
    events = read_event_lines(event_read)
    os.close(event_read)
    anchor = next(line for line in events if line.startswith("ANCHOR_READY ")).split()
    ready = next(line for line in events if line.startswith("GROUP_READY ")).split()
    assert process.returncode == 0
    assert int(anchor[3]) == expected_sid
    assert int(anchor[4]) == expected_pgid
    assert int(ready[5]) == expected_sid


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_anchor_ignores_int_and_term_for_its_full_lifetime(
    supervisor_build, signum
):
    process, event_read = _spawn_supervised(
        supervisor_build, "import time;time.sleep(0.15)"
    )
    anchor, pending = _wait_for_event(event_read, "ANCHOR_READY ")
    anchor_pid = int(anchor.split()[1])
    os.kill(anchor_pid, signum)
    process.wait(timeout=5)
    pending.decode("ascii")
    read_event_lines(event_read)
    os.close(event_read)
    assert process.returncode == 0
    assert wait_pid_gone(anchor_pid, timeout=2)


def test_workload_does_not_inherit_registration_signal_mask(supervisor_build, tmp_path):
    output = tmp_path / "mask.json"
    code = (
        "import json,signal;"
        f"open({str(output)!r},'w').write(json.dumps(sorted(int(s) for s in signal.pthread_sigmask(signal.SIG_BLOCK, []))))"
    )
    process, event_read = _spawn_supervised(supervisor_build, code)
    process.wait(timeout=5)
    read_event_lines(event_read)
    os.close(event_read)
    assert process.returncode == 0
    blocked = json.loads(output.read_text())
    assert int(signal.SIGINT) not in blocked
    assert int(signal.SIGTERM) not in blocked


def test_workload_descriptor_allowlist_excludes_supervisor_channels(
    supervisor_build, tmp_path
):
    output = tmp_path / "workload-fds.json"
    code = (
        "import fcntl,json;"
        "fds=[];"
        "exec(\"for fd in range(64):\\n try:\\n  fcntl.fcntl(fd,fcntl.F_GETFD);fds.append(fd)\\n except OSError:\\n  pass\");"
        f"open({str(output)!r},'w').write(json.dumps(fds))"
    )
    process, event_read = _spawn_supervised(supervisor_build, code)
    process.wait(timeout=5)
    read_event_lines(event_read)
    os.close(event_read)
    assert process.returncode == 0
    assert json.loads(output.read_text()) == [0, 1, 2]


def _wait_for_event(fd: int, prefix: str, timeout: float = 5.0) -> tuple[str, bytes]:
    deadline = time.monotonic() + timeout
    pending = b""
    while time.monotonic() < deadline:
        readable, _, _ = select.select([fd], [], [], max(0.0, deadline - time.monotonic()))
        if not readable:
            break
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        pending += chunk
        while b"\n" in pending:
            raw, pending = pending.split(b"\n", 1)
            line = raw.decode("ascii")
            if line.startswith(prefix):
                return line, pending
    raise AssertionError(f"event {prefix!r} not received")


def test_wait_for_event_timeout_is_real_when_writer_remains_open():
    read_fd, write_fd = os.pipe()
    started = time.monotonic()
    try:
        with pytest.raises(AssertionError, match="not received"):
            _wait_for_event(read_fd, "NEVER ", timeout=0.05)
    finally:
        os.close(read_fd)
        os.close(write_fd)
    assert time.monotonic() - started < 0.5


def test_first_signal_owns_fixed_deadline_and_only_supervisor_signals_group(
    supervisor_build, tmp_path
):
    ready = tmp_path / "signal-handlers-ready"
    code = (
        "import signal,time,pathlib;"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "signal.signal(signal.SIGINT,signal.SIG_IGN);"
        f"pathlib.Path({str(ready)!r}).write_text('ready');"
        "time.sleep(10)"
    )
    process, event_read = _spawn_supervised(supervisor_build, code)
    _, pending = _wait_for_event(event_read, "WORKLOAD_STARTED ")
    deadline = time.monotonic() + 3
    while not ready.exists():
        assert process.poll() is None
        assert time.monotonic() < deadline
        time.sleep(0.005)
    started = time.monotonic()
    os.kill(process.pid, signal.SIGINT)
    time.sleep(0.05)
    os.kill(process.pid, signal.SIGTERM)
    process.wait(timeout=3)
    elapsed = time.monotonic() - started
    events = pending.decode("ascii").splitlines() + read_event_lines(event_read)
    os.close(event_read)
    accepted = [line for line in events if line.startswith("SIGNAL_ACCEPTED ")]
    sent = [line.split() for line in events if line.startswith("SIGNAL_GROUP ")]
    assert process.returncode == 128 + signal.SIGINT
    assert elapsed < 1.8
    assert len(accepted) == 1 and accepted[0].split()[1] == str(signal.SIGINT)
    assert [int(parts[3]) for parts in sent] == [signal.SIGTERM, signal.SIGKILL]
    assert len({parts[1] for parts in sent}) == 1
    term_ns, kill_ns = (int(parts[4]) for parts in sent)
    accepted_ns = int(accepted[0].split()[2])
    assert term_ns >= accepted_ns
    assert 300_000_000 <= kill_ns - accepted_ns <= 500_000_000


def test_fork_during_shutdown_is_killed_before_signal_retirement(
    supervisor_build, tmp_path
):
    ready = tmp_path / "fork-on-term.ready"
    child_file = tmp_path / "fork-on-term.pid"
    code = f"""
import os, pathlib, signal, time
def on_term(_signum, _frame):
    child = os.fork()
    if child == 0:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        pathlib.Path({str(child_file)!r}).write_text(str(os.getpid()))
        time.sleep(10)
        os._exit(0)
signal.signal(signal.SIGTERM, on_term)
pathlib.Path({str(ready)!r}).write_text("ready")
time.sleep(10)
"""
    process, event_read = _spawn_supervised(supervisor_build, code)
    _wait_for_event(event_read, "WORKLOAD_STARTED ")
    deadline = time.monotonic() + 3
    while not ready.exists():
        assert process.poll() is None
        assert time.monotonic() < deadline
        time.sleep(0.005)
    os.kill(process.pid, signal.SIGTERM)
    process.wait(timeout=3)
    events = read_event_lines(event_read)
    os.close(event_read)
    assert process.returncode == 128 + signal.SIGTERM
    assert child_file.exists()
    assert wait_pid_gone(int(child_file.read_text()), timeout=2)
    retired_index = next(i for i, line in enumerate(events) if line.startswith("RETIRED "))
    assert not any(line.startswith("SIGNAL_GROUP ") for line in events[retired_index + 1 :])


def test_guardian_lifetime_pipe_cleans_group_after_supervisor_sigkill(supervisor_build):
    code = "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);signal.signal(signal.SIGINT,signal.SIG_IGN);time.sleep(10)"
    process, event_read = _spawn_supervised(supervisor_build, code)
    line, _ = _wait_for_event(event_read, "WORKLOAD_STARTED ")
    workload_pid = int(line.split()[2])
    os.kill(process.pid, signal.SIGKILL)
    process.wait(timeout=3)
    os.close(event_read)
    assert process.returncode == -signal.SIGKILL
    assert wait_pid_gone(workload_pid, timeout=2)


def test_guardian_process_exit_is_not_blocked_by_stalled_observer_thread(
    supervisor_build,
):
    env = {**os.environ, **supervisor_build.environment()}
    env["NFS_TEST_G_OBSERVER_STALL"] = "1"
    stalled_read, stalled_write = os.pipe()
    unused_read, unused_write = os.pipe()
    process, event_read = _spawn_supervised(
        supervisor_build,
        "raise SystemExit(0)",
        supervisor_args=("--observer-mode", "stalled", "--phase-pause",
                         "observer-stalled", str(stalled_write), str(unused_read)),
        extra_pass_fds=(stalled_write, unused_read),
        env=env,
    )
    os.close(stalled_write)
    os.close(unused_read)
    ready, pending = _wait_for_event(event_read, "GROUP_READY ")
    guardian_pid, workload_pid = int(ready.split()[2]), int(ready.split()[7])
    _, pending = _wait_for_event_with_pending(
        event_read, pending, "WORKLOAD_STARTED ", timeout=3
    )
    available, _, _ = select.select([stalled_read], [], [], 3)
    assert available and os.read(stalled_read, 1) == b"R"
    os.close(stalled_read)
    os.close(unused_write)
    started = time.monotonic()
    os.kill(process.pid, signal.SIGKILL)
    process.wait(timeout=3)
    pending.decode("ascii")
    os.close(event_read)
    assert process.returncode == -signal.SIGKILL
    assert wait_pid_gone(workload_pid, timeout=2)
    assert wait_pid_gone(guardian_pid, timeout=2)
    assert time.monotonic() - started < 2.0


@pytest.mark.parametrize("shape", ["siblings", "nested"])
def test_guardian_parent_loss_kills_all_term_ignoring_descendants(
    supervisor_build, tmp_path, shape
):
    pids = tmp_path / f"{shape}.pids"
    ready = tmp_path / f"{shape}.ready"
    if shape == "siblings":
        body = f"""
import os, signal, time
for _ in range(2):
    child = os.fork()
    if child == 0:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        with open({str(pids)!r}, "a") as handle:
            handle.write(str(os.getpid()) + "\\n")
        time.sleep(10)
        os._exit(0)
open({str(ready)!r}, "w").write("ready")
time.sleep(10)
"""
        expected = 2
    else:
        body = f"""
import os, signal, time
child = os.fork()
if child == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with open({str(pids)!r}, "a") as handle:
        handle.write(str(os.getpid()) + "\\n")
    grandchild = os.fork()
    if grandchild == 0:
        with open({str(pids)!r}, "a") as handle:
            handle.write(str(os.getpid()) + "\\n")
        open({str(ready)!r}, "w").write("ready")
        time.sleep(10)
        os._exit(0)
    time.sleep(10)
    os._exit(0)
time.sleep(10)
"""
        expected = 2
    process, event_read = _spawn_supervised(supervisor_build, body)
    descendant_pids = []
    try:
        deadline = time.monotonic() + 3
        while True:
            assert process.poll() is None
            assert time.monotonic() < deadline
            if ready.exists() and pids.exists():
                pid_records = pids.read_text()
                if pid_records.endswith("\n"):
                    candidates = [int(value) for value in pid_records.splitlines()]
                    if len(candidates) == expected and len(set(candidates)) == expected:
                        descendant_pids = candidates
                        break
            time.sleep(0.005)
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
        assert process.returncode == -signal.SIGKILL
        assert all(wait_pid_gone(pid, timeout=2) for pid in descendant_pids)
    finally:
        try:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3)
        finally:
            os.close(event_read)


def test_parent_loss_after_workload_exit_keeps_guardian_until_descendant_stops(
    supervisor_build, tmp_path
):
    descendant_file = tmp_path / "post-quiesce-descendant.pid"
    quiesce_read, quiesce_write = os.pipe()
    unused_read, unused_write = os.pipe()
    code = (
        "import os,pathlib,signal,time;"
        "pid=os.fork();"
        f"pathlib.Path({str(descendant_file)!r}).write_text(str(pid)) if pid else None;"
        "(signal.signal(signal.SIGTERM,signal.SIG_IGN),time.sleep(10)) if not pid else None;"
        "raise SystemExit(0)"
    )
    process, event_read = _spawn_supervised(
        supervisor_build, code, supervisor_args=("--observer-mode", "stalled",
            "--phase-pause", "after-quiesce", str(quiesce_write), str(unused_read)),
        extra_pass_fds=(quiesce_write, unused_read),
    )
    os.close(quiesce_write)
    os.close(unused_read)
    _, pending = _wait_for_event(event_read, "ANCHOR_READY ")
    ready, pending = _wait_for_event_with_pending(
        event_read, pending, "GROUP_READY ", timeout=3
    )
    guardian_pid = int(ready.split()[2])
    _, pending2 = _wait_for_event_with_pending(
        event_read, pending, "WORKLOAD_EXIT ", timeout=3
    )
    available, _, _ = select.select([quiesce_read], [], [], 3)
    assert available and os.read(quiesce_read, 1) == b"R"
    os.close(quiesce_read)
    os.close(unused_write)
    assert descendant_file.exists()
    descendant_pid = int(descendant_file.read_text())
    started = time.monotonic()
    os.kill(process.pid, signal.SIGKILL)
    process.wait(timeout=3)
    pending2.decode("ascii")
    os.close(event_read)
    assert process.returncode == -signal.SIGKILL
    assert wait_pid_gone(descendant_pid, timeout=2)
    assert wait_pid_gone(guardian_pid, timeout=2)
    assert time.monotonic() - started < 2.0


def _wait_for_event_with_pending(
    fd: int, pending: bytes, prefix: str, timeout: float = 5.0
) -> tuple[str, bytes]:
    deadline = time.monotonic() + timeout
    data = pending
    while time.monotonic() < deadline:
        while b"\n" in data:
            raw, data = data.split(b"\n", 1)
            line = raw.decode("ascii")
            if line.startswith(prefix):
                return line, data
        readable, _, _ = select.select([fd], [], [], max(0.0, deadline - time.monotonic()))
        if not readable:
            break
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        data += chunk
    raise AssertionError(f"event {prefix!r} not received")


def test_ordinary_group_sigkill_with_session_leader_preserves_cleanup_owners(
    supervisor_build
):
    writer_ready_read, writer_ready_write = os.pipe()
    process, event_read = _spawn_supervised(
        supervisor_build,
        "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(10)",
        supervisor_args=("--writer-ready-fd", str(writer_ready_write)),
        extra_pass_fds=(writer_ready_write,),
        preexec_fn=os.setsid,
    )
    os.close(writer_ready_write)
    anchor, pending = _wait_for_event(event_read, "ANCHOR_READY ")
    ready, pending = _wait_for_event_with_pending(
        event_read, pending, "GROUP_READY ", timeout=3
    )
    guardian_pid, workload_pid = int(ready.split()[2]), int(ready.split()[7])
    writer_ready, _, _ = select.select([writer_ready_read], [], [], 3)
    assert writer_ready
    writer_pid, writer_guardian_pid, _ = map(
        int, os.read(writer_ready_read, 96).decode("ascii").split()
    )
    anchor_pid = int(anchor.split()[1])
    started = time.monotonic()
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=3)
    os.close(event_read)
    os.close(writer_ready_read)
    assert process.returncode == -signal.SIGKILL
    assert all(
        wait_pid_gone(pid, timeout=2)
        for pid in (guardian_pid, workload_pid, writer_pid, writer_guardian_pid, anchor_pid)
    )
    assert time.monotonic() - started < 2.0


@pytest.mark.parametrize("owner", ["anchor", "guardian"])
def test_retained_owner_failure_cleans_payload_without_group_reuse(
    supervisor_build, owner
):
    process, event_read = _spawn_supervised(
        supervisor_build,
        "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(10)",
    )
    anchor, pending = _wait_for_event(event_read, "ANCHOR_READY ")
    ready, pending = _wait_for_event_with_pending(
        event_read, pending, "GROUP_READY ", timeout=3
    )
    _, pending = _wait_for_event_with_pending(
        event_read, pending, "WORKLOAD_STARTED ", timeout=3
    )
    anchor_pid = int(anchor.split()[1])
    guardian_pid = int(ready.split()[2])
    workload_pid = int(ready.split()[7])
    os.kill(anchor_pid if owner == "anchor" else guardian_pid, signal.SIGKILL)
    process.wait(timeout=3)
    pending.decode("ascii")
    os.close(event_read)
    assert process.returncode == 1
    assert wait_pid_gone(workload_pid, timeout=2)
    assert wait_pid_gone(guardian_pid, timeout=2)
    assert wait_pid_gone(anchor_pid, timeout=2)


def test_ignored_sigchld_guardian_loss_cleans_term_ignoring_descendant(
    supervisor_build,
):
    process, event_read = _spawn_supervised(
        supervisor_build,
        "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(10)",
        preexec_fn=ignored_sigchld_preexec,
        restore_signals=False,
    )
    anchor_pid = guardian_pid = workload_pid = None
    try:
        state, pending = _wait_for_event(event_read, "SIGCHLD_PREREQUISITE ")
        assert state == (
            "SIGCHLD_PREREQUISITE inherited=ignored inherited_no_cldwait=false "
            "current=default current_no_cldwait=false before_helpers=true"
        )
        anchor, pending = _wait_for_event_with_pending(
            event_read, pending, "ANCHOR_READY ", timeout=3
        )
        ready, pending = _wait_for_event_with_pending(
            event_read, pending, "GROUP_READY ", timeout=3
        )
        _, pending = _wait_for_event_with_pending(
            event_read, pending, "WORKLOAD_STARTED ", timeout=3
        )
        anchor_pid = int(anchor.split()[1])
        guardian_pid = int(ready.split()[2])
        workload_pid = int(ready.split()[7])
        assert process.poll() is None
        os.kill(guardian_pid, signal.SIGKILL)
        process.wait(timeout=3)
        pending.decode("ascii")
        assert process.returncode == 1
        assert wait_pid_gone(workload_pid, timeout=2)
        assert wait_pid_gone(guardian_pid, timeout=2)
        assert wait_pid_gone(anchor_pid, timeout=2)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(event_read)


def test_stalled_diagnostic_output_cannot_extend_cancellation_cutoff(
    supervisor_build,
):
    event_read, event_write = os.pipe()
    writer_ready_read, writer_ready_write = os.pipe()
    os.set_blocking(event_write, False)
    try:
        while True:
            os.write(event_write, b"x" * 4096)
    except BlockingIOError:
        pass
    os.set_blocking(event_write, True)
    process = subprocess.Popen(
        [
            str(supervisor_build.binary),
            "--test-supervise",
            "--event-fd",
            str(event_write),
            "--writer-ready-fd",
            str(writer_ready_write),
            "--",
            sys.executable,
            "-c",
            "import time;time.sleep(10)",
        ],
        env={**os.environ, **supervisor_build.environment()},
        pass_fds=(event_write, writer_ready_write),
    )
    os.close(writer_ready_write)
    try:
        assert os.get_blocking(event_write)
        ready, _, _ = select.select([writer_ready_read], [], [], 3)
        assert ready and os.read(writer_ready_read, 96)
        started = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=2.2)
        assert time.monotonic() - started < 2.0
        assert process.returncode == 128 + signal.SIGTERM
        assert os.get_blocking(event_write)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(event_write)
        os.close(event_read)
        os.close(writer_ready_read)


def test_diagnostic_overflow_reports_sticky_loss_when_writer_recovers(
    supervisor_build,
):
    event_read, event_write = os.pipe()
    writer_ready_read, writer_ready_write = os.pipe()
    os.set_blocking(event_write, False)
    fill = b"FILL\n" * 800
    try:
        while True:
            os.write(event_write, fill)
    except BlockingIOError:
        pass
    os.set_blocking(event_write, True)
    process = subprocess.Popen(
        [
            str(supervisor_build.binary),
            "--test-supervise",
            "--event-fd",
            str(event_write),
            "--writer-ready-fd",
            str(writer_ready_write),
            "--flood-diagnostics",
            "--",
            sys.executable,
            "-c",
            "import time;time.sleep(0.3)",
        ],
        env={**os.environ, **supervisor_build.environment()},
        pass_fds=(event_write, writer_ready_write),
    )
    os.close(writer_ready_write)
    try:
        readable, _, _ = select.select([writer_ready_read], [], [], 3)
        assert readable and os.read(writer_ready_read, 96)
        time.sleep(0.1)
        os.set_blocking(event_read, False)
        data = bytearray()
        deadline = time.monotonic() + 5
        while process.poll() is None and time.monotonic() < deadline:
            try:
                data.extend(os.read(event_read, 65536))
            except BlockingIOError:
                time.sleep(0.005)
        process.wait(timeout=1)
        while True:
            try:
                chunk = os.read(event_read, 65536)
            except BlockingIOError:
                break
            if not chunk:
                break
            data.extend(chunk)
        assert process.returncode == 0
        losses = [
            line for line in data.decode("ascii").splitlines()
            if line.startswith("DIAG_LOSS ")
        ]
        assert losses, data[-2000:]
        assert any(int(line.split()[1]) > 0 for line in losses)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(writer_ready_read)
        os.close(event_write)
        os.close(event_read)


def test_blocked_writer_and_guardian_die_after_abrupt_supervisor_loss(
    supervisor_build,
):
    event_read, event_write = os.pipe()
    writer_ready_read, writer_ready_write = os.pipe()
    os.set_blocking(event_write, False)
    try:
        while True:
            os.write(event_write, b"x" * 4096)
    except BlockingIOError:
        pass
    os.set_blocking(event_write, True)
    process = subprocess.Popen(
        [
            str(supervisor_build.binary),
            "--test-supervise",
            "--event-fd",
            str(event_write),
            "--writer-ready-fd",
            str(writer_ready_write),
            "--",
            sys.executable,
            "-c",
            "import time;time.sleep(10)",
        ],
        env={**os.environ, **supervisor_build.environment()},
        pass_fds=(event_write, writer_ready_write),
    )
    os.close(writer_ready_write)
    try:
        ready, _, _ = select.select([writer_ready_read], [], [], 3)
        assert ready
        writer_pid, guardian_pid, payload_pgid = map(
            int, os.read(writer_ready_read, 96).decode("ascii").split()
        )
        assert guardian_pid == payload_pgid
        _assert_writer_at_blocked_output(writer_pid)
        started = time.monotonic()
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
        assert process.returncode == -signal.SIGKILL
        assert wait_pid_gone(writer_pid, timeout=2)
        assert wait_pid_gone(guardian_pid, timeout=2)
        assert time.monotonic() - started < 2.0
        assert os.get_blocking(event_write)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(writer_ready_read)
        # Keep the blocked reader open through every owned-process assertion.
        os.close(event_write)
        os.close(event_read)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_signal_during_blocked_writer_drain_sets_final_signal_exit(
    supervisor_build, signum
):
    event_read, event_write = os.pipe()
    writer_ready_read, writer_ready_write = os.pipe()
    drain_ready_read, drain_ready_write = os.pipe()
    os.set_blocking(event_write, False)
    try:
        while True:
            os.write(event_write, b"x" * 4096)
    except BlockingIOError:
        pass
    os.set_blocking(event_write, True)
    process = subprocess.Popen(
        [
            str(supervisor_build.binary),
            "--test-supervise",
            "--event-fd",
            str(event_write),
            "--writer-ready-fd",
            str(writer_ready_write),
            "--writer-drain-ready-fd",
            str(drain_ready_write),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ],
        env={**os.environ, **supervisor_build.environment()},
        pass_fds=(event_write, writer_ready_write, drain_ready_write),
    )
    os.close(writer_ready_write)
    os.close(drain_ready_write)
    try:
        ready, _, _ = select.select([writer_ready_read], [], [], 3)
        assert ready and os.read(writer_ready_read, 96)
        ready, _, _ = select.select([drain_ready_read], [], [], 5)
        assert ready and os.read(drain_ready_read, 1) == b"R"
        started = time.monotonic()
        os.kill(process.pid, signum)
        process.wait(timeout=2.2)
        assert process.returncode == 128 + signum
        assert time.monotonic() - started < 2.0
        assert os.get_blocking(event_write)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(writer_ready_read)
        os.close(drain_ready_read)
        os.close(event_write)
        os.close(event_read)


def test_tostop_stops_writer_without_changing_terminal_or_ofd_state(
    supervisor_build,
):
    master_fd, slave_fd = os.openpty()
    writer_ready_read, writer_ready_write = os.pipe()
    terminal_before = termios.tcgetattr(slave_fd)
    terminal_with_tostop = list(terminal_before)
    terminal_with_tostop[3] |= termios.TOSTOP
    termios.tcsetattr(slave_fd, termios.TCSANOW, terminal_with_tostop)
    ofd_flags = fcntl.fcntl(slave_fd, fcntl.F_GETFL)

    def establish_controlling_terminal():
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.tcsetpgrp(slave_fd, os.getpgrp())

    process = subprocess.Popen(
        [
            str(supervisor_build.binary),
            "--test-supervise",
            "--event-fd",
            str(slave_fd),
            "--writer-ready-fd",
            str(writer_ready_write),
            "--",
            sys.executable,
            "-c",
            "import time;time.sleep(10)",
        ],
        env={**os.environ, **supervisor_build.environment()},
        pass_fds=(slave_fd, writer_ready_write),
        preexec_fn=establish_controlling_terminal,
    )
    os.close(writer_ready_write)
    try:
        readable, _, _ = select.select([writer_ready_read], [], [], 3)
        assert readable
        writer_pid, writer_guardian_pid, _ = map(
            int, os.read(writer_ready_read, 96).decode("ascii").split()
        )
        deadline = time.monotonic() + 3
        writer_stopped = False
        while time.monotonic() < deadline:
            state = subprocess.run(
                [
                    str(supervisor_build.binary),
                    "--test-process-stopped",
                    str(writer_pid),
                ],
                timeout=1,
            )
            writer_stopped = state.returncode == 0
            if writer_stopped:
                break
            time.sleep(0.01)
        assert writer_stopped
        assert termios.tcgetattr(slave_fd) == terminal_with_tostop
        assert fcntl.fcntl(slave_fd, fcntl.F_GETFL) == ofd_flags

        started = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=2.2)
        assert process.returncode == 128 + signal.SIGTERM
        assert time.monotonic() - started < 2.0
        assert wait_pid_gone(writer_pid, timeout=2)
        assert wait_pid_gone(writer_guardian_pid, timeout=2)
        assert fcntl.fcntl(slave_fd, fcntl.F_GETFL) == ofd_flags
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(writer_ready_read)
        os.close(slave_fd)
        os.close(master_fd)


def test_stalled_provenance_worker_cannot_block_cancellation(supervisor_build, tmp_path):
    stalled_source = tmp_path / "stalled-source"
    os.mkfifo(stalled_source)
    env = {**os.environ, **supervisor_build.environment()}
    env["NFS_SOURCE_PATH"] = str(stalled_source)
    process, event_read = _spawn_supervised(
        supervisor_build,
        "raise SystemExit(0)",
        env=env,
    )
    try:
        time.sleep(0.1)
        started = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=2.2)
        assert time.monotonic() - started < 2.0
        assert process.returncode == 128 + signal.SIGTERM
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(event_read)


def test_stalled_verifier_is_guarded_before_blocking_provenance_io(
    supervisor_build, tmp_path
):
    stalled_source = tmp_path / "guarded-stalled-source"
    os.mkfifo(stalled_source)
    ready_read, ready_write = os.pipe()
    env = {**os.environ, **supervisor_build.environment()}
    env["NFS_SOURCE_PATH"] = str(stalled_source)
    env["NFS_VERIFIER_READY_FD"] = str(ready_write)
    process, event_read = _spawn_supervised(
        supervisor_build,
        "raise SystemExit(0)",
        env=env,
        extra_pass_fds=(ready_write,),
    )
    os.close(ready_write)
    try:
        ready, _, _ = select.select([ready_read], [], [], 2)
        assert ready
        worker_pid, guardian_pid, payload_pgid = map(
            int, os.read(ready_read, 96).decode("ascii").split()
        )
        assert guardian_pid == payload_pgid
        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
        assert process.returncode == -signal.SIGKILL
        assert wait_pid_gone(worker_pid, timeout=2)
        assert wait_pid_gone(guardian_pid, timeout=2)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(ready_read)
        os.close(event_read)


def test_signal_pending_at_registration_boundary_prevents_release(
    supervisor_build,
):
    ready_read, ready_write = os.pipe()
    resume_read, resume_write = os.pipe()
    process, event_read = _spawn_supervised(
        supervisor_build,
        "import pathlib;pathlib.Path('/dev/null').exists()",
        supervisor_args=(
            "--pause-before-release",
            str(ready_write),
            str(resume_read),
        ),
        extra_pass_fds=(ready_write, resume_read),
    )
    os.close(ready_write)
    os.close(resume_read)
    try:
        readable, _, _ = select.select([ready_read], [], [], 2)
        assert readable and os.read(ready_read, 1) == b"R"
        os.kill(process.pid, signal.SIGTERM)
        os.write(resume_write, b"C")
        process.wait(timeout=2.2)
        events = read_event_lines(event_read)
        assert process.returncode == 128 + signal.SIGTERM
        assert not any(line.startswith("WORKLOAD_STARTED ") for line in events)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(ready_read)
        os.close(resume_write)
        os.close(event_read)


def test_anchor_loss_at_main_pre_release_boundary_denies_release(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "anchor-loss-pre-release.trace")
    marker = tmp_path / "workload-ran"
    ready_read, ready_write = os.pipe()
    resume_read, resume_write = os.pipe()
    process, event_read = _spawn_supervised(
        supervisor_probe_build,
        f"import pathlib;pathlib.Path({str(marker)!r}).write_text('ran')",
        supervisor_args=(
            "--pause-before-release",
            str(ready_write),
            str(resume_read),
        ),
        extra_pass_fds=(ready_write, resume_read),
        env={**os.environ, **supervisor_probe_build.environment(), **trace.environment()},
    )
    os.close(ready_write)
    os.close(resume_read)
    try:
        readable, _, _ = select.select([ready_read], [], [], 3)
        assert readable and os.read(ready_read, 1) == b"R"
        anchor = trace.wait(lambda row: row["text"].startswith("ANCHOR_READY 1 33 "))
        anchor_pid = int(anchor["text"].split()[4])
        group = trace.wait(lambda row: row["text"].startswith("GROUP_READY 2 1 "))
        guardian_pid = int(group["text"].split()[3])
        held_pid = int(group["text"].split()[8])
        assert process.poll() is None
        if sys.platform == "darwin":
            process_events = select.kqueue()
            try:
                watch = select.kevent(
                    anchor_pid,
                    filter=select.KQ_FILTER_PROC,
                    flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                    fflags=select.KQ_NOTE_EXIT,
                )
                process_events.control([watch], 0, 0)
                os.kill(anchor_pid, signal.SIGKILL)
                exited = process_events.control(None, 1, 1)
                assert exited and exited[0].ident == anchor_pid
            finally:
                process_events.close()
        else:
            os.kill(anchor_pid, signal.SIGKILL)
            deadline = time.monotonic() + 1
            state = ""
            while time.monotonic() < deadline:
                stat = Path(f"/proc/{anchor_pid}/stat")
                if stat.is_file():
                    value = stat.read_text()
                    state = value[value.rfind(")") + 2]
                    if state == "Z":
                        break
                time.sleep(0.005)
            assert state == "Z"
        started = time.monotonic()
        os.write(resume_write, b"C")
        process.wait(timeout=2.2)
        rows = trace.records()
        root = [row for row in rows if row["pid"] == process.pid]
        assert any(
            row["kind"] == "waitid" and row["a"] == anchor_pid and row["b"] != 0
            for row in root
        )
        assert not any(row["text"].startswith("RELEASE 3 1 ") for row in root)
        assert not any(
            row["text"].startswith("WORKLOAD_STARTED 3 1 ") for row in rows
        )
        assert not marker.exists()
        assert process.returncode == 1
        assert time.monotonic() - started < 2.0
        assert wait_pid_gone(guardian_pid, timeout=0.2)
        assert wait_pid_gone(held_pid, timeout=0.2)
    finally:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGCONT)
            process.kill()
            process.wait(timeout=3)
        os.close(ready_read)
        os.close(resume_write)
        os.close(event_read)
        trace.retain()


@pytest.mark.parametrize(
    "phase",
    [
        "before-anchor-ready",
        "before-group",
        "group-formed",
        "child-held",
        "group-migrated",
    ],
)
def test_cancellation_wins_at_anchor_and_guardian_bootstrap_boundaries(
    supervisor_build, tmp_path, phase
):
    ready_read, ready_write = os.pipe()
    resume_read, resume_write = os.pipe()
    marker = tmp_path / f"executed-{phase}"
    process, event_read = _spawn_supervised(
        supervisor_build,
        f"import pathlib;pathlib.Path({str(marker)!r}).write_text('executed')",
        supervisor_args=(
            "--phase-pause",
            phase,
            str(ready_write),
            str(resume_read),
        ),
        extra_pass_fds=(ready_write, resume_read),
    )
    os.close(ready_write)
    os.close(resume_read)
    try:
        readable, _, _ = select.select([ready_read], [], [], 3)
        assert readable and os.read(ready_read, 1) == b"R"
        started = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        os.write(resume_write, b"C")
        process.wait(timeout=2.2)
        events = read_event_lines(event_read)
        assert process.returncode == 128 + signal.SIGTERM
        assert time.monotonic() - started < 2.0
        assert not marker.exists()
        assert not any(line.startswith("WORKLOAD_STARTED ") for line in events)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(ready_read)
        os.close(resume_write)
        os.close(event_read)


@pytest.mark.parametrize("failure", ["guardian", "supervisor"])
def test_stopped_held_child_cannot_escape_registration_cleanup(
    supervisor_build, tmp_path, failure
):
    release_ready_read, release_ready_write = os.pipe()
    release_resume_read, release_resume_write = os.pipe()
    marker = tmp_path / f"held-executed-{failure}"
    process, event_read = _spawn_supervised(
        supervisor_build,
        f"import pathlib;pathlib.Path({str(marker)!r}).write_text('executed')",
        supervisor_args=(
            "--pause-before-release",
            str(release_ready_write),
            str(release_resume_read),
        ),
        extra_pass_fds=(release_ready_write, release_resume_read),
    )
    os.close(release_ready_write)
    os.close(release_resume_read)
    try:
        ready, _, _ = select.select([release_ready_read], [], [], 3)
        assert ready and os.read(release_ready_read, 1) == b"R"
        group, _ = _wait_for_event(event_read, "GROUP_READY ")
        fields = group.split()
        guardian_pid, held_pid = int(fields[2]), int(fields[7])
        os.kill(held_pid, signal.SIGSTOP)
        started = time.monotonic()
        if failure == "guardian":
            os.kill(guardian_pid, signal.SIGKILL)
            os.write(release_resume_write, b"C")
            process.wait(timeout=3)
            assert process.returncode == 1
        else:
            os.kill(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
            assert process.returncode == -signal.SIGKILL
        assert wait_pid_gone(held_pid, timeout=2)
        assert wait_pid_gone(guardian_pid, timeout=2)
        assert time.monotonic() - started < 2.0
        assert not marker.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        os.close(release_ready_read)
        os.close(release_resume_write)
        os.close(event_read)


def test_supervisor_failure_cleans_released_workload_group(
    supervisor_probe_build, tmp_path
):
    trace = RuntimeTrace(tmp_path / "failure-readiness.trace")
    descendant = tmp_path / "failure-descendant.pid"
    ready = tmp_path / "failure-descendant.ready"
    code = (
        "import os,signal,time,pathlib;"
        "pid=os.fork();"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN) if not pid else None;"
        f"pathlib.Path({str(descendant)!r}).write_text(str(os.getpid())) if not pid else None;"
        f"ready_path=pathlib.Path({str(ready)!r}) if not pid else None;"
        "ready_tmp=ready_path.with_name(f'.{ready_path.name}.{os.getpid()}.tmp') "
        "if not pid else None;"
        "ready_tmp.write_text(str(os.getpid())) "
        "if not pid and signal.getsignal(signal.SIGTERM) == signal.SIG_IGN else None;"
        "ready_tmp.replace(ready_path) "
        "if not pid and signal.getsignal(signal.SIGTERM) == signal.SIG_IGN else None;"
        "time.sleep(10)"
    )
    process, event_read = _spawn_supervised(
        supervisor_probe_build,
        code,
        supervisor_args=("--fail-after-workload-start",),
        env={
            **os.environ,
            **supervisor_probe_build.environment(),
            **trace.environment("failure-signal"),
        },
    )
    try:
        # S stops before its first failure-cleanup TERM. Its fixed deadline keeps
        # elapsing, so readiness can release failure without renewing the budget.
        boundary = trace.wait(lambda record: record["kind"] == "failure-pause")
        assert boundary["pid"] == process.pid
        readiness_due = int(boundary["ns"]) + DEADLINES_NS["cancel-observe-end"]
        while not ready.exists():
            assert process.poll() is None
            assert time.monotonic_ns() < readiness_due
            time.sleep(0.005)
        descendant_pid = int(descendant.read_text())
        assert int(ready.read_text()) == descendant_pid
        assert time.monotonic_ns() < readiness_due
        process.send_signal(signal.SIGCONT)
        process.wait(timeout=3)
        assert process.returncode == 1
        assert wait_pid_gone(descendant_pid, timeout=2)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGCONT)
            process.kill()
            process.wait(timeout=3)
        os.close(event_read)
        trace.retain()


def test_fragmented_observer_result_is_received_and_reaped(supervisor_build):
    process, event_read = _spawn_supervised(
        supervisor_build,
        "raise SystemExit(0)",
        supervisor_args=("--observer-mode", "fragmented"),
    )
    process.wait(timeout=5)
    events = read_event_lines(event_read)
    os.close(event_read)
    assert process.returncode == 0
    assert any(line.startswith("OBSERVER_REAPED ") for line in events)
    assert any(line.startswith("OBSERVED 1 confirmed ") for line in events)


def test_stalled_observer_is_bounded_by_existing_cancellation_cutoff(supervisor_build):
    process, event_read = _spawn_supervised(
        supervisor_build,
        "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(10)",
        supervisor_args=("--observer-mode", "stalled"),
    )
    _, pending = _wait_for_event(event_read, "WORKLOAD_STARTED ")
    started = time.monotonic()
    os.kill(process.pid, signal.SIGTERM)
    process.wait(timeout=2.2)
    events = pending.decode("ascii").splitlines() + read_event_lines(event_read)
    os.close(event_read)
    assert process.returncode == 128 + signal.SIGTERM
    assert time.monotonic() - started < 2.0
    assert any(line == "OBSERVER_STATE 1 released" for line in events)


@pytest.mark.parametrize("mode", ["denied", "incomplete", "stalled"])
def test_unconfirmed_observation_never_closes_or_accepts_generation(
    supervisor_build, mode
):
    process, event_read = _spawn_supervised(
        supervisor_build,
        "raise SystemExit(0)",
        supervisor_args=("--observer-mode", mode),
    )
    process.wait(timeout=5)
    events = read_event_lines(event_read)
    os.close(event_read)
    assert process.returncode == 1
    assert any(line == "OBSERVER_STATE 1 released" for line in events)
    result = next(line for line in events if line.startswith("CLEANUP_RESULT "))
    assert " unconfirmed " in result
    assert "reaped=false" in result
    assert "generation_closed=false" in result


def test_late_observer_message_is_rejected_after_identity_retirement(supervisor_build):
    active = subprocess.run(
        [
            str(supervisor_build.binary),
            "--test-observer-message",
            "active",
            "7",
            "3",
            "7",
            "3",
        ],
        timeout=5,
    )
    result = subprocess.run(
        [
            str(supervisor_build.binary),
            "--test-observer-message",
            "retired",
            "7",
            "3",
            "7",
            "3",
        ],
        timeout=5,
    )
    assert active.returncode == 0
    assert result.returncode == 2


@pytest.mark.parametrize(
    ("role", "revoked", "done", "own_seq", "expected_gen", "incoming_gen", "kind", "ref", "valid"),
    [
        ("test-workload", 1, 1, 4, 3, 3, "observed", 7, True),
        ("test-workload", 0, 1, 4, 3, 3, "observed", 7, False),
        ("test-workload", 1, 1, 4, 3, 2, "observed", 7, False),
        ("W", 1, 1, 4, 3, 3, "reaped-fixed", 4, True),
        ("Q", 1, 1, 4, 3, 3, "reaped-fixed", 4, True),
        ("verifier", 1, 1, 4, 3, 3, "reaped-fixed", 4, True),
        ("test-workload", 1, 1, 4, 3, 3, "reaped-fixed", 4, False),
        ("W", 1, 0, 4, 3, 3, "reaped-fixed", 4, False),
        ("W", 1, 1, 4, 3, 3, "reaped-fixed", 5, False),
    ],
)
def test_exit_permit_proof_is_generation_role_and_sequence_bound(
    supervisor_build,
    role,
    revoked,
    done,
    own_seq,
    expected_gen,
    incoming_gen,
    kind,
    ref,
    valid,
):
    result = subprocess.run(
        [
            str(supervisor_build.binary),
            "--test-exit-proof",
            role,
            str(revoked),
            str(done),
            str(own_seq),
            str(expected_gen),
            str(incoming_gen),
            kind,
            str(ref),
        ],
        timeout=5,
    )
    assert (result.returncode == 0) is valid


def test_observer_refuses_live_group_even_with_pinned_identity(supervisor_build):
    process, event_read = _spawn_supervised(supervisor_build, "import time;time.sleep(10)")
    ready, pending = _wait_for_event(event_read, "GROUP_READY ")
    fields = ready.split()
    result = subprocess.run(
        [
            str(supervisor_build.binary),
            "--test-observe",
            fields[1],
            fields[3],
            fields[4],
            fields[2],
            fields[5],
        ],
        timeout=5,
    )
    os.kill(process.pid, signal.SIGTERM)
    process.wait(timeout=3)
    pending.decode("ascii")
    read_event_lines(event_read)
    os.close(event_read)
    assert result.returncode == 2


def test_normal_cleanup_terms_then_kills_live_descendant_at_fixed_gap(
    supervisor_build, tmp_path
):
    descendant_file = tmp_path / "descendant.pid"
    code = (
        "import os,pathlib,signal,time;"
        "pid=os.fork();"
        f"pathlib.Path({str(descendant_file)!r}).write_text(str(pid)) if pid else None;"
        "(signal.signal(signal.SIGTERM,signal.SIG_IGN),time.sleep(10)) if not pid else None;"
        "raise SystemExit(0)"
    )
    process, event_read = _spawn_supervised(supervisor_build, code)
    process.wait(timeout=5)
    events = read_event_lines(event_read)
    os.close(event_read)
    descendant_pid = int(descendant_file.read_text())
    sent = [line.split() for line in events if line.startswith("NORMAL_SIGNAL_GROUP ")]
    assert process.returncode == 0
    assert [int(parts[3]) for parts in sent] == [signal.SIGTERM, signal.SIGKILL]
    term_ns, kill_ns = (int(parts[4]) for parts in sent)
    assert 300_000_000 <= kill_ns - term_ns <= 500_000_000
    assert wait_pid_gone(descendant_pid, timeout=2)


def _wire_blob(
    nonce: str,
    payload: bytes,
    *,
    seq: int = 2,
    transfer: int = 41,
    kind: int = 2,
    chunks: tuple[int, ...] = (),
) -> bytes:
    digest = hashlib.sha256(payload).hexdigest()
    control = (
        f"HELLO 1 {PROTOCOL_VERSION} {nonce} O {os.getpid()} supervised 0\n"
        f"BLOB_BEGIN {seq} preparation O {transfer} {len(payload)} {digest}\n"
        f"BLOB_ACCEPT 1 O {transfer}\n"
    ).encode("ascii")
    header = struct.Struct("!4sIII")
    frames = bytearray(control)
    offset = 0
    for size in chunks:
        chunk = payload[offset : offset + size]
        offset += len(chunk)
        frames.extend(header.pack(b"NFS1", kind, transfer, len(chunk)))
        frames.extend(chunk)
    final = payload[offset:]
    if final:
        frames.extend(header.pack(b"NFS1", kind, transfer, len(final)))
        frames.extend(final)
    frames.extend(header.pack(b"NFS1", kind, transfer, 0))
    return bytes(frames)


def _run_wire(supervisor_build, wire: bytes, chunks: tuple[int, ...] = ()): 
    process = subprocess.Popen(
        [str(supervisor_build.binary), "--test-validate-wire", "O", "a" * 32],
        stdin=subprocess.PIPE,
    )
    assert process.stdin is not None
    if chunks:
        offset = 0
        for size in chunks:
            process.stdin.write(wire[offset : offset + size])
            process.stdin.flush()
            offset += size
        process.stdin.write(wire[offset:])
    else:
        process.stdin.write(wire)
    process.stdin.close()
    process.wait(timeout=5)
    return process.returncode


def test_fragmented_bounded_control_and_frame_round_trip(supervisor_build):
    payload = b"verified fixture provenance"
    wire = _wire_blob("a" * 32, payload, transfer=41, chunks=(3, 5, 7))
    assert _run_wire(supervisor_build, wire, (1, 2, 3, 5, 8, 13, 21)) == 0


def test_stalled_wire_producer_is_bounded_without_waiting_for_eof(supervisor_build):
    nonce = "a" * 32
    process = subprocess.Popen(
        [str(supervisor_build.binary), "--test-validate-wire", "O", nonce],
        stdin=subprocess.PIPE,
    )
    assert process.stdin is not None
    process.stdin.write(
        (
            f"HELLO 1 {PROTOCOL_VERSION} {nonce} O {os.getpid()} supervised 0\n"
            f"BLOB_BEGIN 2 preparation O 41 4 {'0' * 64}\n"
        ).encode("ascii")
    )
    process.stdin.flush()
    started = time.monotonic()
    try:
        process.wait(timeout=2.0)
        assert process.returncode == 2
        assert time.monotonic() - started < 1.5
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        process.stdin.close()


@pytest.mark.parametrize(
    "wire",
    [
        (
            f"HELLO 1 {PROTOCOL_VERSION} {'a' * 32} O {os.getpid()} supervised 0\n"
            f"HELLO 2 {PROTOCOL_VERSION} {'a' * 32} O {os.getpid()} supervised 0\n"
        ).encode(),
        (
            f"HELLO 1 {PROTOCOL_VERSION} {'a' * 32} G {os.getpid()} monotonic 1\n"
            "WORKLOAD_EXIT 2 1 invented 7 reaped\n"
        ).encode(),
        (
            f"HELLO 1 {PROTOCOL_VERSION} {'a' * 32} O {os.getpid()} supervised 0\n"
            "AUTH 2 started evidence\n"
        ).encode(),
        (
            f"HELLO 1 {PROTOCOL_VERSION} {'a' * 32} O {os.getpid()} supervised 0\n"
            "DIAG 2 code phase value\x00trailing\n"
        ).encode(),
    ],
)
def test_foundation_wire_rejects_repeated_hello_bad_enums_unsupported_and_nul(
    supervisor_build, wire
):
    assert _run_wire(supervisor_build, wire) == 2


def test_foundation_wire_enforces_sequence_start_role_clock_pid_and_order(supervisor_build):
    nonce = "a" * 32
    native_clock = "uptime-raw" if sys.platform == "darwin" else "monotonic"
    invalid_wires = [
        f"HELLO 2 {PROTOCOL_VERSION} {nonce} O {os.getpid()} supervised 0\n",
        f"HELLO 1 {PROTOCOL_VERSION} {nonce} G {os.getpid()} supervised 0\n",
        f"HELLO 1 {PROTOCOL_VERSION} {nonce} G 2147483648 {native_clock} 1\n",
        (
            f"HELLO 1 {PROTOCOL_VERSION} {nonce} G {os.getpid()} {native_clock} 1\n"
            "WORKLOAD_EXIT 2 1 exit 0 reaped\n"
        ),
        (
            f"HELLO 1 {PROTOCOL_VERSION} {nonce} G {os.getpid()} {native_clock} 1\n"
            f"GROUP_READY 2 1 {os.getpid()} {os.getpid()} {os.getpid()} identity\n"
            "WORKLOAD_STARTED 3 1 42\n"
            "WORKLOAD_EXIT 4 1 invented 7 reaped\n"
        ),
    ]
    for wire in invalid_wires:
        assert _run_wire(supervisor_build, wire.encode("ascii")) == 2


@pytest.mark.parametrize(
    "wire",
    [
        f"HELLO 01 {PROTOCOL_VERSION} {'a' * 32} O 1 supervised 0\n",
        f"HELLO +1 {PROTOCOL_VERSION} {'a' * 32} O 1 supervised 0\n",
        f"HELLO  1 {PROTOCOL_VERSION} {'a' * 32} O 1 supervised 0\n",
        f"HELLO\t1 {PROTOCOL_VERSION} {'a' * 32} O 1 supervised 0\n",
        f" HELLO 1 {PROTOCOL_VERSION} {'a' * 32} O 1 supervised 0\n",
    ],
)
def test_control_grammar_rejects_noncanonical_numbers_and_spacing(
    supervisor_build, wire
):
    assert _run_wire(supervisor_build, wire.encode("ascii")) == 2


def test_control_line_bound_is_256_bytes_including_newline(supervisor_build):
    hello = (
        f"HELLO 1 {PROTOCOL_VERSION} {'a' * 32} O {os.getpid()} supervised 0\n"
    )
    prefix = "DIAG 2 code phase "
    valid = prefix + "v" * (256 - len(prefix) - 1) + "\n"
    invalid = prefix + "v" * (257 - len(prefix) - 1) + "\n"
    assert len(valid.encode("ascii")) == 256
    assert len(invalid.encode("ascii")) == 257
    assert _run_wire(supervisor_build, (hello + valid).encode("ascii")) == 0
    assert _run_wire(supervisor_build, (hello + invalid).encode("ascii")) == 2


def test_blob_data_requires_explicit_accept_transition(supervisor_build):
    wire = _wire_blob("a" * 32, b"payload")
    begin = wire.index(b"BLOB_BEGIN")
    accept = wire.index(b"BLOB_ACCEPT")
    frame = wire.index(b"NFS1")
    without_accept = wire[:accept] + wire[frame:]
    assert begin < accept < frame
    assert _run_wire(supervisor_build, without_accept) == 2


def test_more_than_eight_processed_messages_is_not_a_queue_overflow(supervisor_build):
    wire = (
        f"HELLO 1 {PROTOCOL_VERSION} {'a' * 32} O {os.getpid()} supervised 0\n"
        + "".join(f"DIAG {seq} code phase value\n" for seq in range(2, 12))
    ).encode()
    assert _run_wire(supervisor_build, wire) == 0


@pytest.mark.parametrize(
    "mutator",
    [
        lambda wire: wire.replace(b"NFS1", b"BAD!", 1),
        lambda wire: wire[:-1],
        lambda wire: wire.replace(b"HELLO 1 ", b"HELLO 2 ", 1),
        lambda wire: wire.replace(b" aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa O ", b" bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb O ", 1),
        lambda wire: wire.replace(b" O ", b" P ", 1),
        lambda wire: wire.replace(b" supervised 0\n", b" wrong-clock 0\n", 1),
        lambda wire: wire.replace(b" supervised 0\n", b" supervised 1\n", 1),
    ],
)
def test_malformed_fragmented_wire_fails_closed(supervisor_build, mutator):
    assert _run_wire(supervisor_build, mutator(_wire_blob("a" * 32, b"payload")), (7, 4, 1)) != 0


def test_oversized_wire_fails_closed(supervisor_build):
    oversized = (
        f"HELLO 1 {PROTOCOL_VERSION} {'a' * 32} O {os.getpid()} supervised 0\n"
        f"BLOB_BEGIN 2 build O 1 {1024 * 1024 + 1} {'0' * 64}\n"
    ).encode()
    assert _run_wire(supervisor_build, oversized) != 0


@pytest.mark.parametrize(("stage", "nanoseconds"), DEADLINES_NS.items())
def test_compiled_deadlines_are_fixed(supervisor_build, stage, nanoseconds):
    result = subprocess.run(
        [str(supervisor_build.binary), "--test-deadline", stage, str(nanoseconds)], timeout=5
    )
    assert result.returncode == 0


@pytest.mark.parametrize(
    "line",
    [
        "4321 (worker name (nested)) S 1 4321 4321 0 -1 0 0 0 0 0 0 0 0 0 0 0 0 0 998877 0 0",
        "4321 (right)paren) Z 1 4321 4321 0 -1 0 0 0 0 0 0 0 0 0 0 0 0 0 998877 0 0",
    ],
)
def test_linux_stat_parser_handles_parenthesized_names_on_every_platform(supervisor_build, line):
    state = line[line.rfind(")") + 2]
    result = subprocess.run(
        [
            str(supervisor_build.binary),
            "--test-parse-linux-stat",
            "4321",
            state,
            "4321",
            "4321",
            "998877",
        ],
        input=line.encode(),
        timeout=5,
    )
    assert result.returncode == 0


def test_linux_stat_parser_rejects_malformed_or_mismatched_identity(supervisor_build):
    result = subprocess.run(
        [
            str(supervisor_build.binary),
            "--test-parse-linux-stat",
            "4321",
            "S",
            "4321",
            "4321",
            "998877",
        ],
        input=b"4321 (unterminated S 1 4321",
        timeout=5,
    )
    assert result.returncode != 0


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin inventory contract")
def test_darwin_observer_treats_wrong_leader_identity_as_uncertain(supervisor_build):
    child = subprocess.Popen(
        [sys.executable, "-c", "import os,time;os.setsid();time.sleep(5)"]
    )
    try:
        time.sleep(0.05)
        result = subprocess.run(
            [
                str(supervisor_build.binary),
                "--test-observe",
                "1",
                str(child.pid),
                str(child.pid),
                str(child.pid),
                "wrong-start-identity",
            ],
            timeout=5,
        )
        assert result.returncode == 2
    finally:
        child.kill()
        child.wait(timeout=3)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux task census")
def test_linux_zombie_leader_with_live_thread_never_confirms_cleanup(
    supervisor_build, tmp_path
):
    helper_source = tmp_path / "zombie-leader.c"
    helper_binary = tmp_path / "zombie-leader"
    helper_source.write_text(
        "#include <pthread.h>\n"
        "#include <unistd.h>\n"
        "static void *worker(void *unused) {(void)unused;sleep(10);return 0;}\n"
        "int main(void) {pthread_t thread;if(pthread_create(&thread,0,worker,0))return 2;"
        "if(write(1,\"R\",1)!=1)return 3;pthread_exit(0);}\n"
    )
    compiled = subprocess.run(
        [
            str(supervisor_build.compiler),
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pthread",
            str(helper_source),
            "-o",
            str(helper_binary),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert compiled.returncode == 0, (compiled.stdout, compiled.stderr)
    helper = subprocess.Popen(
        [str(helper_binary)], stdout=subprocess.PIPE, start_new_session=True
    )
    try:
        assert helper.stdout is not None and helper.stdout.read(1) == b"R"
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            leader_stat = Path(f"/proc/{helper.pid}/stat").read_text()
            leader_state = leader_stat[leader_stat.rfind(")") + 2]
            tasks = list(Path(f"/proc/{helper.pid}/task").iterdir())
            if leader_state == "Z" and len(tasks) > 1:
                break
            time.sleep(0.01)
        else:
            pytest.fail("thread-group leader did not become zombie with a live task")
        owner_stat = Path("/proc/self/stat").read_text()
        owner_identity = owner_stat[owner_stat.rfind(")") + 2 :].split()[19]
        observe = [
            str(supervisor_build.binary),
            "--test-observe",
            "1",
            str(helper.pid),
            str(helper.pid),
            str(os.getpid()),
            owner_identity,
        ]
        assert subprocess.run(observe, timeout=5).returncode == 2
        os.killpg(helper.pid, signal.SIGKILL)
        helper.wait(timeout=3)
        assert subprocess.run(observe, timeout=5).returncode == 0
    finally:
        if helper.poll() is None:
            os.killpg(helper.pid, signal.SIGKILL)
            helper.wait(timeout=3)
