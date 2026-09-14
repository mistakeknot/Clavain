from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "scripts/native-fixture-supervisor.c"
PROTOCOL_VERSION = 33
INTEGRATION_UNAVAILABLE = 78
PREREQUISITE_FAILURE = 125
DEADLINES_NS = {
    "bootstrap": 3_000_000_000,
    "guardian-registration": 1_000_000_000,
    "preparation": 8_000_000_000,
    "finalizer-ready": 3_000_000_000,
    "started-auth": 10_000_000_000,
    "append-result": 5_000_000_000,
    "intent-begin": 5_000_000_000,
    "send-intent-auth": 10_000_000_000,
    "start-protocol": 5_000_000_000,
    "protocol-verified": 10_000_000_000,
    "verified-native-request": 1_000_000_000,
    "native-ready": 2_000_000_000,
    "descriptor-ack": 1_000_000_000,
    "native-input": 10_000_000_000,
    "operation": 120_000_000_000,
    "operation-backstop": 122_000_000_000,
    "operation-checkpoint": 2_000_000_000,
    "normal-cleanup": 2_000_000_000,
    "observation": 1_000_000_000,
    "seal": 3_000_000_000,
    "handoff-finish": 3_000_000_000,
    "finish-auth": 3_000_000_000,
    "terminal-worker": 5_000_000_000,
    "readback-export": 3_000_000_000,
    "finish-exit": 3_000_000_000,
    "ancillary-shutdown": 2_000_000_000,
    "writer-drain": 1_000_000_000,
    "cancel-kill-native": 350_000_000,
    "cancel-kill-workers": 500_000_000,
    "cancel-evidence-stop": 1_350_000_000,
    "cancel-evidence-kill": 1_500_000_000,
    "cancel-observe-end": 1_650_000_000,
    "cancel-writer-end": 1_700_000_000,
    "cancel-target-exit": 1_750_000_000,
    "cancel-hard-cutoff": 1_800_000_000,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute_compiler() -> Path:
    candidates = (
        (Path("/usr/bin/clang"),) if sys.platform == "darwin" else ()
    ) + (Path("/usr/bin/cc"), Path("/usr/bin/gcc"), Path("/usr/bin/clang"))
    for candidate in candidates:
        if candidate.is_absolute() and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise AssertionError("no absolute platform C compiler is available")


def _real_bash() -> Path:
    selected = shutil.which("bash")
    if selected is None:
        raise AssertionError("real Bash is unavailable")
    resolved = Path(selected).resolve()
    if not resolved.is_absolute() or not resolved.is_file():
        raise AssertionError("real Bash did not resolve to a regular absolute path")
    return resolved


def signal_dispositions() -> dict[str, str]:
    result: dict[str, str] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        disposition = signal.getsignal(signum)
        if disposition is signal.SIG_IGN:
            label = "ignored"
        elif disposition is signal.SIG_DFL:
            label = "default"
        else:
            label = "handler"
        result[signal.Signals(signum).name] = label
    return result


@dataclass(frozen=True)
class SupervisorBuild:
    binary: Path
    source: Path
    compiler: Path
    real_bash: Path
    provenance: Path
    record: dict[str, object]

    def environment(self) -> dict[str, str]:
        return {
            "NFS_REAL_BASH": str(self.real_bash),
            "NFS_SOURCE_PATH": str(self.source),
            "NFS_EXPECTED_BINARY_SHA256": str(self.record["binary_sha256"]),
            "NFS_EXPECTED_SOURCE_SHA256": str(self.record["source_sha256"]),
            "NFS_EXPECTED_BASH_SHA256": str(self.record["bash_sha256"]),
            "NFS_PROTOCOL_VERSION": str(PROTOCOL_VERSION),
        }


def build_supervisor(private_dir: Path, *, probe: bool = False) -> SupervisorBuild:
    if not SOURCE.is_file():
        raise AssertionError(f"supervisor source missing: {SOURCE}")
    private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(private_dir, 0o700)
    compiler = _absolute_compiler()
    real_bash = _real_bash()
    binary = private_dir / "native-fixture-supervisor"
    translation_unit = SOURCE
    if probe:
        translation_unit = private_dir / "runtime-probe.c"
        translation_unit.write_text(RUNTIME_PROBE.replace("@SOURCE@", str(SOURCE)))
    feature = "-D_DARWIN_C_SOURCE" if sys.platform == "darwin" else "-D_GNU_SOURCE"
    argv = [
        str(compiler),
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-D_POSIX_C_SOURCE=200809L",
        feature,
        "-pthread",
        str(translation_unit),
        "-o",
        str(binary),
        "-pthread",
    ]
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    os.chmod(binary, 0o700)
    version = subprocess.run(
        [str(compiler), "--version"], capture_output=True, text=True, timeout=10, check=True
    ).stdout
    bash_version = subprocess.run(
        [str(real_bash), "--version"], capture_output=True, text=True, timeout=10, check=True
    ).stdout.splitlines()[0]
    record: dict[str, object] = {
        "schema": 1,
        "eligibility": "fixture-only-ineligible",
        "protocol_version": PROTOCOL_VERSION,
        "source": str(SOURCE),
        "source_sha256": sha256_file(SOURCE),
        "binary": str(binary),
        "binary_sha256": sha256_file(binary),
        "compiler": str(compiler),
        "compiler_sha256": sha256_file(compiler),
        "compiler_argv": argv,
        "compiler_version": version,
        "real_bash": str(real_bash),
        "bash_sha256": sha256_file(real_bash),
        "bash_version": bash_version,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "descriptor_limits": {
            "soft": resource.getrlimit(resource.RLIMIT_NOFILE)[0],
            "hard": resource.getrlimit(resource.RLIMIT_NOFILE)[1],
        },
        "load_average": list(os.getloadavg()),
        "python": sys.executable,
        "inherited_signal_dispositions": signal_dispositions(),
        "translation_unit_sha256": sha256_file(translation_unit),
        "runtime_probe": probe,
    }
    provenance = private_dir / "provenance.json"
    provenance.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    os.chmod(provenance, 0o600)
    return SupervisorBuild(binary, SOURCE, compiler, real_bash, provenance, record)


def make_bash_launcher(build: SupervisorBuild, directory: Path) -> Path:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    launcher = directory / "bash"
    launcher.symlink_to(build.binary)
    return launcher


def launcher_argv(launcher: Path, script: str) -> list[str]:
    return [str(launcher), "-c", script, "fixture", "library", "spec", "root"]


def read_event_lines(fd: int, timeout: float = 5.0) -> list[str]:
    deadline = time.monotonic() + timeout
    data = bytearray()
    os.set_blocking(fd, False)
    while time.monotonic() < deadline:
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            time.sleep(0.005)
            continue
        if not chunk:
            break
        data.extend(chunk)
    return data.decode("ascii").splitlines()


def wait_pid_gone(pid: int, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        time.sleep(0.01)
    return False


def ignored_signal_preexec() -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def ignored_term_preexec() -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)


def default_sigchld_preexec() -> None:
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)


def ignored_sigchld_preexec() -> None:
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)


def blocked_pending_term_preexec() -> None:
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
    os.kill(os.getpid(), signal.SIGTERM)


# Compile the real foundation into a syscall-observing test executable. The
# shared, bounded trace survives forks/execs and remains readable when W is
# blocked. Only the test executable interposes these calls; the ordinary build
# and its provenance are kept separately. No PID from a trace conveys authority
# to signal it: tests signal only their retained Popen child.
RUNTIME_PROBE = r'''
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <time.h>
#include <poll.h>
#include <stdint.h>
#include <stddef.h>
static ssize_t probe_write(int, const void *, size_t);
static int probe_kill(pid_t, int);
static pid_t probe_waitpid(pid_t, int *, int);
static int probe_waitid(idtype_t, id_t, siginfo_t *, int);
static int probe_nanosleep(const struct timespec *, struct timespec *);
static ssize_t probe_read(int, void *, size_t);
static int probe_poll(struct pollfd *, nfds_t, int);
static int probe_setpgid(pid_t, pid_t);
#define write probe_write
#define kill probe_kill
#define waitpid probe_waitpid
#define waitid probe_waitid
#define nanosleep probe_nanosleep
#define read probe_read
#define poll probe_poll
#define setpgid probe_setpgid
#define main foundation_main
#include "@SOURCE@"
#undef main
#undef write
#undef kill
#undef waitpid
#undef waitid
#undef nanosleep
#undef read
#undef poll
#undef setpgid
struct probe_record {
    _Atomic uint32_t ready;
    uint32_t pid;
    uint64_t ns;
    int64_t a, b;
    char kind[16], text[256];
};
struct probe_trace {
    _Atomic uint32_t count;
    uint32_t root;
    char padding[56];
    struct probe_record records[4096];
};
static struct probe_trace *trace;
static const char *probe_mode;
static bool probe_quiesced, probe_paused;
static pid_t probe_lost_owner;
static void record_probe(const char *kind, int64_t a, int64_t b,
                          const void *data, size_t length) {
    if (trace == NULL) return;
    uint32_t slot = atomic_fetch_add_explicit(&trace->count, 1, memory_order_relaxed);
    if (slot >= 4096) return;
    struct probe_record *r = &trace->records[slot];
    r->pid = (uint32_t)getpid(); r->ns = now_ns(); r->a = a; r->b = b;
    size_t k = strlen(kind); if (k > 15) k = 15;
    memcpy(r->kind, kind, k);
    if (length > 255) length = 255;
    if (data != NULL) memcpy(r->text, data, length);
    atomic_store_explicit(&r->ready, 1, memory_order_release);
}
static bool probe_is(const char *name) {
    return probe_mode != NULL && strcmp(probe_mode, name) == 0;
}
static void probe_lose_anchor(void) {
    if (trace == NULL || (uint32_t)getpid() != trace->root) return;
    uint32_t count = atomic_load(&trace->count);
    for (uint32_t i = 0; i < count && i < 4096; ++i) {
        struct probe_record *r = &trace->records[i];
        if (!atomic_load(&r->ready) || strncmp(r->text, "ANCHOR_READY 1 33 ", 18) != 0)
            continue;
        pid_t anchor = (pid_t)r->pid;
        siginfo_t info; memset(&info, 0, sizeof(info));
        if (waitid(P_PID, (id_t)anchor, &info, WEXITED|WNOHANG|WNOWAIT) != 0)
            return;
        /* Only the retained child discovered on this attempt's private pipe. */
        if (!child_termination_observed(&info, anchor)) kill(anchor, SIGKILL);
        uint64_t due = now_ns()+UINT64_C(200)*NS_PER_MILLISECOND;
        bool observed = false;
        while (now_ns() < due) {
            memset(&info, 0, sizeof(info));
            if (waitid(P_PID, (id_t)anchor, &info, WEXITED|WNOHANG|WNOWAIT) != 0) break;
            if (child_termination_observed(&info, anchor)) {observed = true; break;}
            struct timespec tick = {0, 1000000}; nanosleep(&tick, NULL);
        }
        record_probe("anchor-lost", anchor, observed, NULL, 0);
        return;
    }
}
static ssize_t probe_write(int fd, const void *data, size_t length) {
    if (length > 1 && length <= 256 && ((const char *)data)[length-1] == '\n')
        record_probe("write", fd, (int64_t)length, data, length);
    if (trace != NULL && (uint32_t)getpid() == trace->root && length == 1 &&
        *(const uint8_t *)data == 1)
        record_probe("accepted", atomic_load(&accepted_signal), 0, NULL, 0);
    if (trace != NULL && (uint32_t)getpid() == trace->root && length >= 17 &&
        ((probe_is("anchor-loss-before-w") &&
          memcmp(data, "EXIT_PERMIT 5 32 ", 17) == 0) ||
         (probe_is("anchor-loss-before-q") &&
          memcmp(data, "QUIESCE 4 1 ", 12) == 0)))
        probe_lose_anchor();
    if (trace != NULL && (uint32_t)getpid() == trace->root &&
        probe_is("late-observed") && !probe_paused &&
        length == strlen("OBSERVER_STATE 1 workload-reaped\n") &&
        memcmp(data, "OBSERVER_STATE 1 workload-reaped\n", length) == 0) {
        probe_paused = true;
        record_probe("late-observed", 0, 0, NULL, 0);
        raise(SIGSTOP);
    }
    if (length > 1 && length < 256 && trace != NULL &&
        (uint32_t)getpid() != trace->root) {
        char original[256], changed[256];
        memcpy(original, data, length); original[length] = 0;
        unsigned seq, gen; long child;
        if (sscanf(original, "WORKLOAD_STARTED %u %u %ld", &seq, &gen, &child) == 3 &&
            ((probe_is("wrong-start") && gen == 1) ||
             (probe_is("wrong-fixed-start") && gen == NFS_GROUP_MAX))) {
            int n = snprintf(changed, sizeof(changed), "WORKLOAD_STARTED %u %u %ld\n",
                             seq, gen, child + 1);
            record_probe("injected", fd, 0, changed, (size_t)n);
            return write(fd, changed, (size_t)n) == n ? (ssize_t)length : -1;
        }
        if (probe_is("q-registration-failure") &&
            strncmp(original, "GROUP_READY 2 2 ", 16) == 0) {
            record_probe("q-held", getpid(), 0, original, length);
            raise(SIGSTOP); /* Parent must retire the still-owned held generation. */
        }
        if (probe_is("late-registration") &&
            strncmp(original, "GROUP_READY 2 1 ", 16) == 0) {
            ssize_t result = write(fd, data, length);
            record_probe("reg-peer-held", getpid(), 0, NULL, 0);
            raise(SIGSTOP); /* Keep the valid held identity alive across D. */
            return result;
        }
        if (probe_is("permit-stall") &&
            strncmp(original, "GUARD_EXITING 5 1 ", 18) == 0) {
            ssize_t result = write(fd, data, length);
            record_probe("permit-stall", getpid(), 0, original, length);
            raise(SIGSTOP);
            return result;
        }
        if (probe_is("permit-delay") &&
            strncmp(original, "GUARD_EXITING 5 1 ", 18) == 0) {
            ssize_t result = write(fd, data, length);
            record_probe("permit-delayed", getpid(), 0, NULL, 0);
            /* Inject 90 ms of termination latency after actual permission.
             * The approved absolute cutoff still has more than a second. */
            struct timespec latency = {0, 90 * 1000 * 1000};
            nanosleep(&latency, NULL);
            return result;
        }
        char *observed = strstr(original, "OBSERVED 2 ");
        if ((probe_is("invented-observed") || probe_is("stale-observed")) && observed != NULL) {
            size_t prefix = (size_t)(observed - original);
            unsigned long long request;
            unsigned target;
            if (sscanf(observed, "OBSERVED 2 %llu %u", &request, &target) == 2) {
                memcpy(changed, original, prefix);
                int n = probe_is("stale-observed") ?
                    snprintf(changed + prefix, sizeof(changed) - prefix,
                             "OBSERVED 2 1 %u %s stale\n", target,
                             request == 1 ? "unconfirmed" : "confirmed") :
                    snprintf(changed + prefix, sizeof(changed) - prefix,
                             "OBSERVED 2 999 %u confirmed invented\n", target);
                n += (int)prefix;
                record_probe("injected", fd, 0, changed, (size_t)n);
                return write(fd, changed, (size_t)n) == n ? (ssize_t)length : -1;
            }
        }
    }
    ssize_t result = write(fd, data, length);
    if (result < 0) record_probe("write-error", fd, errno, NULL, 0);
    if (fd == STDOUT_FILENO && length > 1)
        record_probe("write-return", fd, result, NULL, 0);
    return result;
}
static int probe_kill(pid_t pid, int signum) {
    record_probe("kill", pid, signum, NULL, 0);
    if (trace != NULL && (uint32_t)getpid() == trace->root &&
        pid < 0 && signum == SIGTERM && probe_is("failure-signal")) {
        record_probe("failure-pause", pid, 0, NULL, 0);
        raise(SIGSTOP);
    }
    return kill(pid, signum);
}
static pid_t probe_waitpid(pid_t pid, int *status, int options) {
    pid_t result = waitpid(pid, status, options);
    if (result > 0) record_probe("reap", pid, result, NULL, 0);
    return result;
}
static int probe_waitid(idtype_t type, id_t pid, siginfo_t *info, int options) {
    if (probe_is("lost-owner") && (pid_t)pid == probe_lost_owner) {
        record_probe("identity-lost", pid, ECHILD, NULL, 0);
        errno = ECHILD; return -1;
    }
    int result = waitid(type, pid, info, options);
    record_probe("waitid", pid, result == 0 ? info->si_code : -errno, NULL, 0);
    return result;
}
static int probe_nanosleep(const struct timespec *request, struct timespec *remaining) {
    if (request->tv_sec == 3) record_probe("stall-enter", getpid(), 0, NULL, 0);
    return nanosleep(request, remaining);
}
static ssize_t probe_read(int fd, void *data, size_t length) {
    ssize_t result = read(fd, data, length);
    if (probe_is("late-registration") && trace != NULL &&
        (uint32_t)getpid() == trace->root && length == 1 && result == 1) {
        static char line[256]; static size_t used;
        char byte = *(char *)data;
        if (used < sizeof(line)-1) line[used++] = byte;
        if (byte == '\n') {
            line[used] = 0;
            if (strncmp(line, "GROUP_READY 2 1 ", 16) == 0) {
                record_probe("reg-delayed", fd, 0, line, used);
                raise(SIGSTOP);
            }
            used = 0;
        }
    }
    if (probe_is("late-permit") && trace != NULL && (uint32_t)getpid() != trace->root &&
        length == 1 && result == 1) {
        static char line[256]; static size_t used;
        char byte = *(char *)data;
        if (used < sizeof(line)-1) line[used++] = byte;
        if (byte == '\n') {
            line[used] = 0;
            if (strncmp(line, "QUIESCE ", 8) == 0) probe_quiesced = true;
            used = 0;
        }
    }
    return result;
}
static int probe_poll(struct pollfd *fds, nfds_t count, int timeout) {
    if (probe_is("late-permit") && probe_quiesced && !probe_paused) {
        probe_paused = true;
        record_probe("guard-paused", getpid(), 0, NULL, 0);
        raise(SIGSTOP);
    }
    return poll(fds, count, timeout);
}
static int probe_setpgid(pid_t pid, pid_t pgid) {
    if (probe_is("join-denied") && pgid > 0 && pgid != getpid()) {
        record_probe("join-denied", pgid, EPERM, NULL, 0);
        errno = EPERM; return -1;
    }
    return setpgid(pid, pgid);
}

static int probe_fixed_sequence(void) {
    int signals[2], control[2], lifetime[2];
    if (!install_handlers(signals) || socketpair(AF_UNIX, SOCK_STREAM, 0, control) ||
        pipe(lifetime)) return 123;
    pid_t child = fork();
    if (child == 0) {
        close(control[0]); close(lifetime[1]);
        uint64_t due = now_ns() + NS_PER_SECOND;
        char line[NFS_CONTROL_STORAGE];
        if (!write_line(control[1], "WORKLOAD_STARTED 3 7 %ld\n", (long)getpid()) ||
            !write_line(control[1], "WORKLOAD_EXIT 9 7 exit 0 reaped\n") ||
            read_line_deadline(control[1], line, sizeof(line), due) != 1 ||
            read_line_deadline(control[1], line, sizeof(line), due) != 1)
            _exit(3);
        record_probe("peer-permit", 0, 0, line, strlen(line));
        _exit(strcmp(line, "EXIT_PERMIT 5 7 reaped-fixed 9\n") == 0 ? 0 : 4);
    }
    if (child < 0) return 123;
    close(control[1]); close(lifetime[0]);
    struct fixed_guardian_handle handle = {
        .pid=child, .pgid=child, .held_pid=child, .control_fd=control[0],
        .lifetime_write=lifetime[1], .generation=7, .receive_sequence=2,
    };
    int status = 1;
    bool ok = finish_fixed_guardian(&handle, now_ns(), now_ns()+NS_PER_SECOND, &status);
    return ok && status == 0 ? 0 : 1;
}
static int probe_capacity(const char *binary) {
    fixture_test_mode = true;
    int signals[2], gate[2];
    if (!install_handlers(signals) || pipe(gate)) return 123;
    struct anchor_handle anchor;
    if (!start_anchor(&anchor, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                       now_ns()+NS_PER_SECOND, -1, NULL)) return 123;
    struct fixed_guardian_handle handles[NFS_GROUP_MAX+2];
    size_t count = 0;
    char *args[] = {(char *)binary, "--probe-fixed-hold", NULL};
    bool complete = true;
    for (uint32_t generation = 1; generation <= NFS_GROUP_MAX; ++generation) {
        if (!start_fixed_guardian(&handles[count], binary, &anchor, generation,
                                   "Q", "capacity", true, gate[0], -1, -1, -1,
                                   signals[0], args, now_ns()+NS_PER_SECOND)) {
            complete = false; break;
        }
        ++count;
    }
    bool duplicate = false, overflow = false, replacement = false;
    struct anchor_handle other;
    if (complete) {
        duplicate = start_fixed_guardian(&handles[count], binary, &anchor, 1,
            "Q", "duplicate", true, gate[0], -1, -1, -1, signals[0], args,
            now_ns()+NS_PER_SECOND);
        if (duplicate) ++count;
        overflow = start_fixed_guardian(&handles[count], binary, &anchor, NFS_GROUP_MAX+1,
            "Q", "overflow", true, gate[0], -1, -1, -1, signals[0], args,
            now_ns()+NS_PER_SECOND);
        if (overflow) ++count;
        replacement = start_anchor(&other, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                                    now_ns()+NS_PER_SECOND, -1, NULL);
    }
    record_probe("capacity", (int64_t)count,
                 duplicate + 2*overflow + 4*replacement, NULL, 0);
    close(gate[0]); close(gate[1]);
    uint64_t due = now_ns()+NFS_NORMAL_CLEANUP_NS;
    for (size_t i = 0; i < count; ++i) {
        int status = 1;
        (void)finish_fixed_guardian(&handles[i], now_ns(), due, &status);
    }
    if (replacement) retire_anchor(&other, due);
    retire_anchor(&anchor, due);
    return complete && !duplicate && !overflow && !replacement ? 0 : 1;
}
static int probe_late_permit(const char *binary) {
    int signals[2], gate[2];
    if (!install_handlers(signals) || pipe(gate)) return 123;
    struct anchor_handle anchor;
    if (!start_anchor(&anchor, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                       now_ns()+NS_PER_SECOND, -1, NULL)) return 123;
    char *args[] = {(char *)binary, "--probe-fixed-hold", NULL};
    struct fixed_guardian_handle handle;
    if (!start_fixed_guardian(&handle, binary, &anchor, 7, "Q", "late-permit",
                               true, gate[0], -1, -1, -1, signals[0], args,
                               now_ns()+NS_PER_SECOND)) return 123;
    close(gate[0]); close(gate[1]);
    bool done = false; int status = 1;
    uint64_t due = now_ns()+NS_PER_SECOND;
    while (!done && now_ns()<due) {
        char line[NFS_CONTROL_STORAGE];
        if (read_line_supervisor(handle.control_fd, signals[0], line, sizeof(line), due) != 1 ||
            !fixed_workload_report(&handle, line, &status, &done)) break;
    }
    uint64_t hard = now_ns()+UINT64_C(200)*NS_PER_MILLISECOND;
    if (!done || !write_line(handle.control_fd, "QUIESCE 4 7 %llu %llu\n",
                             (unsigned long long)now_ns(), (unsigned long long)hard)) return 123;
    record_probe("hard-cutoff", (int64_t)hard, handle.pid, NULL, 0);
    /* Deliberately queue a late permit while the retained G is descheduled.
     * This is lateness injection, not a sleep used to guess readiness. */
    bool paused = false;
    while (now_ns()<hard) {
        if (process_is_stopped(handle.pid)) {paused = true; break;}
        struct timespec tick = {0, 1000000}; nanosleep(&tick, NULL);
    }
    while (now_ns()<=hard+UINT64_C(20)*NS_PER_MILLISECOND) {
        struct timespec tick = {0, 1000000}; nanosleep(&tick, NULL);
    }
    (void)write_line(handle.control_fd, "EXIT_PERMIT 5 7 reaped-fixed %u\n",
                     handle.workload_exit_sequence);
    kill(handle.pid, SIGCONT);
    bool reaped = reap_child_until(handle.pid, now_ns()+NS_PER_SECOND, &status);
    if (!reaped) terminate_child_bounded(handle.pid, now_ns()+NS_PER_SECOND);
    close(handle.control_fd); close(handle.lifetime_write);
    retire_anchor(&anchor, now_ns()+NS_PER_SECOND);
    return paused && reaped ? 0 : 123;
}
static int probe_owner_loss(void) {
    int ready[2], gate[2];
    if (pipe(ready) || pipe(gate)) return 123;
    pid_t child = fork();
    if (child == 0) {
        close(ready[0]); close(gate[1]);
        if (setpgid(0, 0) || !write_all(ready[1], "R", 1)) _exit(123);
        char value;
        ssize_t count = read(gate[0], &value, 1);
        _exit(count == 0 ? 0 : 123);
    }
    if (child < 0) return 123;
    close(ready[1]); close(gate[0]);
    char value;
    if (!read_exact(ready[0], &value, 1)) return 123;
    close(ready[0]);
    /* Simulate a recycled numeric identity: S no longer has the retained
     * direct-child entitlement. The real child is retained by this test peer. */
    probe_lost_owner = child;
    (void)retire_unconfirmed_child(child, child, true, 7, "test-workload",
                                   now_ns()+NS_PER_SECOND, -1);
    record_probe("lost-owner-done", child, 0, NULL, 0);
    probe_lost_owner = 0;
    siginfo_t info; memset(&info, 0, sizeof(info));
    bool alive = waitid(P_PID, (id_t)child, &info, WEXITED|WNOHANG|WNOWAIT) == 0 &&
                 !child_termination_observed(&info, child);
    close(gate[1]);
    int status = 1;
    bool reaped = reap_child_until(child, now_ns()+NS_PER_SECOND, &status);
    if (!reaped) terminate_child_bounded(child, now_ns()+NS_PER_SECOND);
    return alive && reaped && WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : 1;
}
static int probe_partial_eof(void) {
    int channel[2];
    if (pipe(channel)) return 123;
    (void)write_all(channel[1], "WORKLOAD_EXIT 4 7 exit 0 reaped", 29);
    close(channel[1]);
    char line[NFS_CONTROL_STORAGE];
    int result = read_line_deadline(channel[0], line, sizeof(line), now_ns()+NS_PER_SECOND);
    close(channel[0]);
    record_probe("partial-eof", result, 0, NULL, 0);
    return result == -1 ? 0 : 1;
}
static int probe_orphan_writer(int terminal_fd, int resume_fd) {
    int control[2], bytes[2], gate[2], ready[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, control) || pipe(bytes) ||
        pipe(gate) || pipe(ready)) return 123;
    pid_t foreground = getpgrp();
    pid_t owner = fork();
    if (owner == 0) {
        close(control[0]); close(bytes[1]); close(gate[1]); close(ready[0]);
        if (setpgid(0, 0)) _exit(123);
        pid_t writer = fork();
        if (writer == 0) {
            close(gate[0]); close(ready[1]);
            reset_child_signal_state();
            default_unblocked_signal(SIGTTOU);
            int status = diagnostic_writer(bytes[0], terminal_fd, control[1],
                                            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", -1);
            _exit(status);
        }
        if (writer < 0 || setpgid(0, foreground)) _exit(123);
        close(control[1]); close(bytes[0]);
        (void)write_line(ready[1], "%ld\n", (long)writer);
        close(ready[1]);
        char value;
        ssize_t count = read(gate[0], &value, 1);
        _exit(count == 0 ? 0 : 123);
    }
    if (owner < 0) return 123;
    close(control[1]); close(bytes[0]); close(gate[0]); close(ready[1]);
    char line[NFS_CONTROL_STORAGE];
    uint64_t due = now_ns()+NS_PER_SECOND;
    if (read_line_deadline(ready[0], line, sizeof(line), due) != 1) return 123;
    long writer = strtol(line, NULL, 10); close(ready[0]);
    if (read_line_deadline(control[0], line, sizeof(line), due) != 1 ||
        !write_line(control[0], "HELLO_OK 1 33 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa %s %llu\n",
                     selected_clock_name(), (unsigned long long)now_ns())) return 123;
    close(gate[1]);
    bool orphaned = false;
    while (now_ns()<due) {
        siginfo_t info; memset(&info, 0, sizeof(info));
        if (waitid(P_PID, (id_t)owner, &info, WEXITED|WNOHANG|WNOWAIT) != 0) break;
        if (child_termination_observed(&info, owner)) {orphaned = true; break;}
        struct timespec tick = {0, 1000000}; nanosleep(&tick, NULL);
    }
    record_probe("orphan-ready", owner, writer, NULL, 0);
    bool sent = orphaned && write_all(bytes[1], "orphan-output\n", 14);
    close(bytes[1]);
    bool unavailable = sent &&
        read_line_deadline(control[0], line, sizeof(line), due) == 1 &&
        strcmp(line, "DRAINED 2 unavailable\n") == 0;
    record_probe("orphan-result", unavailable, writer, NULL, 0);
    /* Owner remains a retained zombie until the final group signal is retired. */
    (void)retire_unconfirmed_child(owner, owner, true, 7, "W-orphan", due, -1);
    close(control[0]);
    record_probe("orphan-finished", unavailable, writer, NULL, 0);
    /* Preserve the controlling session while Python checks terminal state. */
    (void)read_line_deadline(resume_fd, line, sizeof(line), now_ns()+NS_PER_SECOND);
    close(resume_fd);
    return unavailable ? 0 : 1;
}
int main(int argc, char **argv) {
    const char *path = getenv("NFS_PROBE_TRACE_PATH");
    probe_mode = getenv("NFS_PROBE_MODE");
    if (path != NULL) {
        int fd = open(path, O_RDWR | O_CLOEXEC);
        if (fd < 0) return 124;
        trace = mmap(NULL, sizeof(*trace), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        close(fd);
        if (trace == MAP_FAILED) return 124;
        if (trace->root == 0) trace->root = (uint32_t)getpid();
    }
    if (argc == 2 && strcmp(argv[1], "--probe-fixed-sequence") == 0)
        return probe_fixed_sequence();
    if (argc == 2 && strcmp(argv[1], "--probe-capacity") == 0)
        return probe_capacity(argv[0]);
    if (argc == 2 && strcmp(argv[1], "--probe-late-permit") == 0)
        return probe_late_permit(argv[0]);
    if (argc == 2 && strcmp(argv[1], "--probe-lost-owner") == 0)
        return probe_owner_loss();
    if (argc == 2 && strcmp(argv[1], "--probe-partial-eof") == 0)
        return probe_partial_eof();
    if (argc == 4 && strcmp(argv[1], "--probe-orphan-writer") == 0)
        return probe_orphan_writer(atoi(argv[2]), atoi(argv[3]));
    if (argc == 2 && strcmp(argv[1], "--probe-fixed-hold") == 0) {
        char value;
        return read(4, &value, 1) == 0 ? 0 : 1;
    }
    int status = foundation_main(argc, argv);
    for (uint32_t generation = 0; generation <= NFS_GROUP_MAX; ++generation) {
        const volatile struct retirement_evidence *e = &retirement_evidence[generation];
        if (!e->active) continue;
        char line[256];
        int n = snprintf(line, sizeof(line),
            "generation=%u cleanup=unconfirmed reaped=false generation_closed=false owner_valid=%d child_reaped=%d termination_observed=%d group_retired=%d due=%llu",
            generation, e->owner_valid, e->child_reaped, e->termination_observed,
            e->signals_retired, (unsigned long long)e->hard_due);
        record_probe("retire-state", e->owner_pid, e->pid_attempted, line, (size_t)n);
    }
    struct diagnostic_outcome diagnostic = last_diagnostic_outcome;
    record_probe("diagnostic", diagnostic.report_received,
                 diagnostic.payload_status, diagnostic.persistence,
                 strlen(diagnostic.persistence));
    record_probe("exit", status, 0, NULL, 0);
    return status;
}
'''


class RuntimeTrace:
    """Bounded raw syscall records, including the emitting process and clock."""

    def __init__(self, path: Path):
        import struct

        self.path = path
        self.record_struct = struct.Struct("=IIQqq16s256s")
        with path.open("xb") as output:
            output.truncate(64 + 4096 * self.record_struct.size)

    def environment(self, mode: str = "") -> dict[str, str]:
        return {"NFS_PROBE_TRACE_PATH": str(self.path), "NFS_PROBE_MODE": mode}

    def records(self) -> list[dict[str, object]]:
        import struct

        data = self.path.read_bytes()
        count = struct.unpack_from("=I", data)[0]
        assert count <= 4096, "runtime trace exhausted (not a passing observation)"
        records = []
        for index in range(count):
            ready, pid, ns, a, b, kind, message = self.record_struct.unpack_from(
                data, 64 + index * self.record_struct.size
            )
            if ready:
                records.append(dict(pid=pid, ns=ns, a=a, b=b,
                                    kind=kind.rstrip(b"\0").decode(),
                                    text=message.rstrip(b"\0").decode()))
        return records

    def wait(self, predicate, timeout: float = 5) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for record in self.records():
                if predicate(record):
                    return record
            time.sleep(0.002)
        raise AssertionError(f"runtime boundary unavailable: {self.records()}")

    def retain(self) -> None:
        records = self.records()
        self.path.with_suffix(".json").write_text(json.dumps(records, indent=2) + "\n")
        print(json.dumps({"trace": str(self.path), "records": records}, sort_keys=True))
