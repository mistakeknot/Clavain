/*
 * Fixture-only cancellation supervisor foundation (protocol v33).
 *
 * This file deliberately does not connect the public native fixture path.  The
 * compatibility launcher recognizes that path and returns EX_UNAVAILABLE until
 * the O/P/R/A integration batch supplies its private handshake.  The process,
 * group, clock, bounded-wire, provenance and observation primitives below are
 * the production-shaped foundation that integration will use.
 */

#include <arpa/inet.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdarg.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#if defined(__linux__)
#include <sys/syscall.h>
#endif

#if defined(NFS_TEST_LINUX_BRANCH)
#define NFS_PLATFORM_LINUX 1
#elif defined(__APPLE__)
#define NFS_PLATFORM_DARWIN 1
#elif defined(__linux__)
#define NFS_PLATFORM_LINUX 1
#endif

#if defined(NFS_PLATFORM_DARWIN)
#include <libproc.h>
#include <mach-o/dyld.h>
#include <sys/proc.h>
#include <sys/sysctl.h>
#elif defined(NFS_PLATFORM_LINUX)
#include <dirent.h>
#endif

#define NFS_PROTOCOL_VERSION 33U
#define NFS_CONTROL_MAX 256U
#define NFS_CONTROL_STORAGE (NFS_CONTROL_MAX + 1U)
#define NFS_CONTROL_QUEUE 8U
#define NFS_FRAME_MAX (1024U * 1024U)
#define NFS_ATTEMPT_MAX (32U * 1024U * 1024U)
#define NFS_GROUP_MAX 32U
#define NFS_DARWIN_FD_SNAPSHOT_MAX 4096U
#define NFS_EXIT_UNAVAILABLE 78
#define NFS_EXIT_PREREQUISITE 125
#define NS_PER_SECOND UINT64_C(1000000000)
#define NS_PER_MILLISECOND UINT64_C(1000000)

#define NFS_GUARDIAN_REGISTRATION_NS (UINT64_C(1000) * NS_PER_MILLISECOND)
#define NFS_BOOTSTRAP_NS (UINT64_C(3000) * NS_PER_MILLISECOND)
#define NFS_PREPARATION_NS (UINT64_C(8000) * NS_PER_MILLISECOND)
#define NFS_FINALIZER_READY_NS (UINT64_C(3000) * NS_PER_MILLISECOND)
#define NFS_STARTED_AUTH_NS (UINT64_C(10000) * NS_PER_MILLISECOND)
#define NFS_APPEND_RESULT_NS (UINT64_C(5000) * NS_PER_MILLISECOND)
#define NFS_INTENT_BEGIN_NS (UINT64_C(5000) * NS_PER_MILLISECOND)
#define NFS_SEND_INTENT_AUTH_NS (UINT64_C(10000) * NS_PER_MILLISECOND)
#define NFS_START_PROTOCOL_NS (UINT64_C(5000) * NS_PER_MILLISECOND)
#define NFS_PROTOCOL_VERIFIED_NS (UINT64_C(10000) * NS_PER_MILLISECOND)
#define NFS_VERIFIED_NATIVE_REQUEST_NS (UINT64_C(1000) * NS_PER_MILLISECOND)
#define NFS_NATIVE_READY_NS (UINT64_C(2000) * NS_PER_MILLISECOND)
#define NFS_DESCRIPTOR_ACK_NS (UINT64_C(1000) * NS_PER_MILLISECOND)
#define NFS_NATIVE_INPUT_NS (UINT64_C(10000) * NS_PER_MILLISECOND)
#define NFS_OPERATION_NS (UINT64_C(120000) * NS_PER_MILLISECOND)
#define NFS_OPERATION_BACKSTOP_NS (UINT64_C(122000) * NS_PER_MILLISECOND)
#define NFS_OPERATION_CHECKPOINT_NS (UINT64_C(2000) * NS_PER_MILLISECOND)
#define NFS_NORMAL_CLEANUP_NS (UINT64_C(2000) * NS_PER_MILLISECOND)
#define NFS_OBSERVATION_NS (UINT64_C(1000) * NS_PER_MILLISECOND)
#define NFS_SEAL_NS (UINT64_C(3000) * NS_PER_MILLISECOND)
#define NFS_HANDOFF_FINISH_NS (UINT64_C(3000) * NS_PER_MILLISECOND)
#define NFS_FINISH_AUTH_NS (UINT64_C(3000) * NS_PER_MILLISECOND)
#define NFS_TERMINAL_WORKER_NS (UINT64_C(5000) * NS_PER_MILLISECOND)
#define NFS_READBACK_EXPORT_NS (UINT64_C(3000) * NS_PER_MILLISECOND)
#define NFS_FINISH_EXIT_NS (UINT64_C(3000) * NS_PER_MILLISECOND)
#define NFS_ANCILLARY_SHUTDOWN_NS (UINT64_C(2000) * NS_PER_MILLISECOND)
#define NFS_WRITER_DRAIN_NS (UINT64_C(1000) * NS_PER_MILLISECOND)
#define NFS_CANCEL_KILL_NATIVE_NS (UINT64_C(350) * NS_PER_MILLISECOND)
#define NFS_CANCEL_KILL_WORKERS_NS (UINT64_C(500) * NS_PER_MILLISECOND)
#define NFS_CANCEL_EVIDENCE_STOP_NS (UINT64_C(1350) * NS_PER_MILLISECOND)
#define NFS_CANCEL_EVIDENCE_KILL_NS (UINT64_C(1500) * NS_PER_MILLISECOND)
#define NFS_CANCEL_OBSERVE_END_NS (UINT64_C(1650) * NS_PER_MILLISECOND)
#define NFS_CANCEL_WRITER_END_NS (UINT64_C(1700) * NS_PER_MILLISECOND)
#define NFS_CANCEL_TARGET_EXIT_NS (UINT64_C(1750) * NS_PER_MILLISECOND)
#define NFS_CANCEL_HARD_CUTOFF_NS (UINT64_C(1800) * NS_PER_MILLISECOND)

_Static_assert(ATOMIC_LLONG_LOCK_FREE == 2,
               "accepted cancellation timestamp must be lock-free");

static _Atomic unsigned long long accepted_ns = 0;
static _Atomic int accepted_signal = 0;
static int signal_pipe_write = -1;
static int signal_pipe_read = -1;
static unsigned diagnostic_drops = 0;
static bool fixture_test_mode = false;
static bool anchor_attempted = false;
static bool guardian_joins_disabled = false;
static bool generation_issued[NFS_GROUP_MAX + 1U];
static const char *inherited_sigchld_disposition = "uninitialized";
static bool inherited_sigchld_no_cldwait = false;
static bool sigchld_prerequisite_ready = false;

/* Fixed retained evidence: index zero is H; each generation has one terminal
 * record. This is state, not a permission to persist after the writer cutoff.
 * An actual direct-child reap never upgrades unconfirmed payload cleanup. */
struct retirement_evidence {
    bool active, owner_valid, group_attempted, signals_retired, pid_attempted;
    bool termination_observed, child_reaped;
    pid_t owner_pid, payload_pgid;
    int group_result, group_errno, pid_result, pid_errno;
    uint64_t hard_due, signals_retired_ns;
};
static volatile struct retirement_evidence retirement_evidence[NFS_GROUP_MAX + 1U];

static bool reserve_generation(uint32_t generation) {
    if (guardian_joins_disabled || generation == 0 || generation > NFS_GROUP_MAX ||
        generation_issued[generation]) return false;
    generation_issued[generation] = true;
    return true;
}

struct sha256_ctx {
    uint8_t data[64];
    uint32_t datalen;
    uint64_t bitlen;
    uint32_t state[8];
};

struct linux_stat_record {
    long pid;
    char state;
    long pgrp;
    long session;
    unsigned long long start_identity;
};

struct observation {
    bool confirmed;
    char reason[64];
};

struct deadline_entry {
    const char *name;
    uint64_t nanoseconds;
};

struct payload_spec {
    const char *name;
    uint32_t kind;
    uint64_t maximum;
    char owner;
};

static const struct deadline_entry deadline_entries[] = {
    {"bootstrap", NFS_BOOTSTRAP_NS},
    {"guardian-registration", NFS_GUARDIAN_REGISTRATION_NS},
    {"preparation", NFS_PREPARATION_NS},
    {"finalizer-ready", NFS_FINALIZER_READY_NS},
    {"started-auth", NFS_STARTED_AUTH_NS},
    {"append-result", NFS_APPEND_RESULT_NS},
    {"intent-begin", NFS_INTENT_BEGIN_NS},
    {"send-intent-auth", NFS_SEND_INTENT_AUTH_NS},
    {"start-protocol", NFS_START_PROTOCOL_NS},
    {"protocol-verified", NFS_PROTOCOL_VERIFIED_NS},
    {"verified-native-request", NFS_VERIFIED_NATIVE_REQUEST_NS},
    {"native-ready", NFS_NATIVE_READY_NS},
    {"descriptor-ack", NFS_DESCRIPTOR_ACK_NS},
    {"native-input", NFS_NATIVE_INPUT_NS},
    {"operation", NFS_OPERATION_NS},
    {"operation-backstop", NFS_OPERATION_BACKSTOP_NS},
    {"operation-checkpoint", NFS_OPERATION_CHECKPOINT_NS},
    {"normal-cleanup", NFS_NORMAL_CLEANUP_NS},
    {"observation", NFS_OBSERVATION_NS},
    {"seal", NFS_SEAL_NS},
    {"handoff-finish", NFS_HANDOFF_FINISH_NS},
    {"finish-auth", NFS_FINISH_AUTH_NS},
    {"terminal-worker", NFS_TERMINAL_WORKER_NS},
    {"readback-export", NFS_READBACK_EXPORT_NS},
    {"finish-exit", NFS_FINISH_EXIT_NS},
    {"ancillary-shutdown", NFS_ANCILLARY_SHUTDOWN_NS},
    {"writer-drain", NFS_WRITER_DRAIN_NS},
    {"cancel-kill-native", NFS_CANCEL_KILL_NATIVE_NS},
    {"cancel-kill-workers", NFS_CANCEL_KILL_WORKERS_NS},
    {"cancel-evidence-stop", NFS_CANCEL_EVIDENCE_STOP_NS},
    {"cancel-evidence-kill", NFS_CANCEL_EVIDENCE_KILL_NS},
    {"cancel-observe-end", NFS_CANCEL_OBSERVE_END_NS},
    {"cancel-writer-end", NFS_CANCEL_WRITER_END_NS},
    {"cancel-target-exit", NFS_CANCEL_TARGET_EXIT_NS},
    {"cancel-hard-cutoff", NFS_CANCEL_HARD_CUTOFF_NS},
};

static const struct payload_spec payload_specs[] = {
    {"build", 1, 64U * 1024U, 'S'},
    {"preparation", 2, 4U * 1024U * 1024U, 'O'},
    {"intent", 3, 64U * 1024U, 'O'},
    {"protocol", 4, NFS_FRAME_MAX + 44U, 'O'},
    {"native-launch", 5, NFS_FRAME_MAX, 'P'},
    {"native-input", 6, NFS_FRAME_MAX, 'P'},
    {"operation-checkpoint", 7, 16U * 1024U * 1024U, 'P'},
    {"state", 8, 64U * 1024U, 'S'},
    {"audit", 9, 4U * 1024U * 1024U, 'R'},
};

static uint32_t rotr32(uint32_t value, uint32_t bits) {
    return (value >> bits) | (value << (32U - bits));
}

static void sha256_transform(struct sha256_ctx *ctx, const uint8_t block[64]) {
    static const uint32_t constants[64] = {
        0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
        0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
        0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
        0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
        0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
        0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
        0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
        0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
        0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
        0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
        0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
        0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
        0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
        0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
        0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
        0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
    };
    uint32_t words[64];
    for (size_t i = 0; i < 16; ++i) {
        words[i] = ((uint32_t)block[i * 4] << 24) |
                   ((uint32_t)block[i * 4 + 1] << 16) |
                   ((uint32_t)block[i * 4 + 2] << 8) |
                   (uint32_t)block[i * 4 + 3];
    }
    for (size_t i = 16; i < 64; ++i) {
        uint32_t s0 = rotr32(words[i - 15], 7) ^ rotr32(words[i - 15], 18) ^
                      (words[i - 15] >> 3);
        uint32_t s1 = rotr32(words[i - 2], 17) ^ rotr32(words[i - 2], 19) ^
                      (words[i - 2] >> 10);
        words[i] = words[i - 16] + s0 + words[i - 7] + s1;
    }
    uint32_t a = ctx->state[0], b = ctx->state[1], c = ctx->state[2];
    uint32_t d = ctx->state[3], e = ctx->state[4], f = ctx->state[5];
    uint32_t g = ctx->state[6], h = ctx->state[7];
    for (size_t i = 0; i < 64; ++i) {
        uint32_t s1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
        uint32_t choice = (e & f) ^ ((~e) & g);
        uint32_t temp1 = h + s1 + choice + constants[i] + words[i];
        uint32_t s0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
        uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temp2 = s0 + majority;
        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }
    ctx->state[0] += a;
    ctx->state[1] += b;
    ctx->state[2] += c;
    ctx->state[3] += d;
    ctx->state[4] += e;
    ctx->state[5] += f;
    ctx->state[6] += g;
    ctx->state[7] += h;
}

static void sha256_init(struct sha256_ctx *ctx) {
    ctx->datalen = 0;
    ctx->bitlen = 0;
    ctx->state[0] = 0x6a09e667U;
    ctx->state[1] = 0xbb67ae85U;
    ctx->state[2] = 0x3c6ef372U;
    ctx->state[3] = 0xa54ff53aU;
    ctx->state[4] = 0x510e527fU;
    ctx->state[5] = 0x9b05688cU;
    ctx->state[6] = 0x1f83d9abU;
    ctx->state[7] = 0x5be0cd19U;
}

static void sha256_update(struct sha256_ctx *ctx, const uint8_t *data, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        ctx->data[ctx->datalen++] = data[i];
        if (ctx->datalen == 64) {
            sha256_transform(ctx, ctx->data);
            ctx->bitlen += 512;
            ctx->datalen = 0;
        }
    }
}

static void sha256_final(struct sha256_ctx *ctx, uint8_t digest[32]) {
    uint32_t i = ctx->datalen;
    ctx->data[i++] = 0x80;
    if (i > 56) {
        while (i < 64) ctx->data[i++] = 0;
        sha256_transform(ctx, ctx->data);
        i = 0;
    }
    while (i < 56) ctx->data[i++] = 0;
    ctx->bitlen += (uint64_t)ctx->datalen * 8U;
    for (size_t j = 0; j < 8; ++j)
        ctx->data[63U - j] = (uint8_t)(ctx->bitlen >> (j * 8U));
    sha256_transform(ctx, ctx->data);
    for (i = 0; i < 4; ++i) {
        for (size_t j = 0; j < 8; ++j)
            digest[i + j * 4] = (uint8_t)(ctx->state[j] >> (24U - i * 8U));
    }
}

static void digest_hex(const uint8_t digest[32], char out[65]) {
    static const char hex[] = "0123456789abcdef";
    for (size_t i = 0; i < 32; ++i) {
        out[i * 2] = hex[digest[i] >> 4];
        out[i * 2 + 1] = hex[digest[i] & 15U];
    }
    out[64] = '\0';
}

static bool sha256_path(const char *path, char out[65]) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    struct sha256_ctx ctx;
    uint8_t digest[32], buffer[32768];
    sha256_init(&ctx);
    for (;;) {
        ssize_t count = read(fd, buffer, sizeof(buffer));
        if (count == 0) break;
        if (count < 0) {
            if (errno == EINTR) continue;
            close(fd);
            return false;
        }
        sha256_update(&ctx, buffer, (size_t)count);
    }
    close(fd);
    sha256_final(&ctx, digest);
    digest_hex(digest, out);
    return true;
}

static bool is_lower_hex(const char *value, size_t exact) {
    if (value == NULL || strlen(value) != exact) return false;
    for (size_t i = 0; i < exact; ++i)
        if (!((value[i] >= '0' && value[i] <= '9') ||
              (value[i] >= 'a' && value[i] <= 'f')))
            return false;
    return true;
}

static clockid_t selected_clock(void) {
#if defined(NFS_PLATFORM_DARWIN)
    return CLOCK_UPTIME_RAW;
#else
    return CLOCK_MONOTONIC;
#endif
}

static const char *selected_clock_name(void) {
#if defined(NFS_PLATFORM_DARWIN)
    return "uptime-raw";
#else
    return "monotonic";
#endif
}

static uint64_t now_ns(void) {
    struct timespec value;
    if (clock_gettime(selected_clock(), &value) != 0) _exit(126);
    return (uint64_t)value.tv_sec * NS_PER_SECOND + (uint64_t)value.tv_nsec;
}

static int remaining_ms(uint64_t deadline) {
    uint64_t now = now_ns();
    if (now >= deadline) return 0;
    uint64_t delta = deadline - now;
    uint64_t millis = (delta + NS_PER_MILLISECOND - 1U) / NS_PER_MILLISECOND;
    return millis > (uint64_t)INT_MAX ? INT_MAX : (int)millis;
}

static uint64_t earlier_due(uint64_t left, uint64_t right) {
    return left < right ? left : right;
}

static uint64_t reserve_before(uint64_t deadline, uint64_t reserve) {
    return deadline > reserve ? deadline - reserve : 0;
}

static uint64_t signal_clipped_due(uint64_t fixed_due, uint64_t offset) {
    if (atomic_load_explicit(&accepted_signal, memory_order_relaxed) != 0) {
        uint64_t signal_due = (uint64_t)atomic_load_explicit(
            &accepted_ns, memory_order_relaxed) + offset;
        return earlier_due(fixed_due, signal_due);
    }
    return fixed_due;
}

/* This is the final exit decision. Keep handlers and their self-pipe live until
 * process exit; cleanup must never cache or disarm first-signal precedence. */
static int supervisor_exit_status(int fallback) {
    int signum = atomic_load_explicit(&accepted_signal, memory_order_relaxed);
    return signum != 0 ? 128 + signum : fallback;
}

static void cancellation_handler(int signum) {
    int saved = errno;
    int expected = 0;
    if (atomic_compare_exchange_strong_explicit(
            &accepted_signal, &expected, signum,
            memory_order_relaxed, memory_order_relaxed)) {
        atomic_store_explicit(&accepted_ns, (unsigned long long)now_ns(),
                              memory_order_relaxed);
        if (signal_pipe_write >= 0) {
            uint8_t byte = 1;
            ssize_t ignored = write(signal_pipe_write, &byte, sizeof(byte));
            (void)ignored;
        }
    }
    errno = saved;
}

static bool inherited_signals_supported(void) {
    struct sigaction current;
    if (sigaction(SIGINT, NULL, &current) != 0 || current.sa_handler == SIG_IGN)
        return false;
    if (sigaction(SIGTERM, NULL, &current) != 0 || current.sa_handler == SIG_IGN)
        return false;
    return true;
}

static bool set_fd_flags(int fd, bool nonblocking) {
    int fdflags = fcntl(fd, F_GETFD);
    if (fdflags < 0 || fcntl(fd, F_SETFD, fdflags | FD_CLOEXEC) < 0) return false;
    if (nonblocking) {
        int flags = fcntl(fd, F_GETFL);
        if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) return false;
    }
    return true;
}

static bool close_from_fd(int low) {
#if defined(NFS_PLATFORM_DARWIN)
    struct proc_fdinfo descriptors[NFS_DARWIN_FD_SNAPSHOT_MAX];
    int bytes = proc_pidinfo(getpid(), PROC_PIDLISTFDS, 0, descriptors,
                             (int)sizeof(descriptors));
    if (bytes <= 0 || (size_t)bytes >= sizeof(descriptors) ||
        (size_t)bytes % PROC_PIDLISTFD_SIZE != 0)
        return false;
    size_t count = (size_t)bytes / PROC_PIDLISTFD_SIZE;
    for (size_t index = 0; index < count; ++index) {
        int fd = descriptors[index].proc_fd;
        if (fd >= low && close(fd) != 0 && errno != EBADF)
            return false;
    }
    return true;
#elif defined(__linux__) && defined(SYS_close_range)
    if (syscall(SYS_close_range, (unsigned int)low, ~0U, 0U) == 0) return true;
    long maximum = sysconf(_SC_OPEN_MAX);
    if (maximum < low) maximum = low;
    for (int fd = low; fd < maximum; ++fd) close(fd);
    return true;
#else
    long maximum = sysconf(_SC_OPEN_MAX);
    if (maximum < low) maximum = low;
    for (int fd = low; fd < maximum; ++fd) close(fd);
    return true;
#endif
}

static bool install_devnull_standard_fds(bool keep_stdin, bool keep_stdout) {
    int null_fd = open("/dev/null", O_RDWR | O_CLOEXEC);
    if (null_fd < 0) return false;
    if ((!keep_stdin && dup2(null_fd, STDIN_FILENO) < 0) ||
        (!keep_stdout && dup2(null_fd, STDOUT_FILENO) < 0) ||
        dup2(null_fd, STDERR_FILENO) < 0) {
        close(null_fd);
        return false;
    }
    if (null_fd > STDERR_FILENO) close(null_fd);
    return true;
}

static bool prepare_guardian_descriptors(int *control_fd, int *lifetime_fd,
                                         int *workload_fd, int *ready_fd,
                                         int *pause_ready_fd,
                                         int *pause_resume_fd) {
    int *sources[] = {control_fd, lifetime_fd, workload_fd, ready_fd,
                      pause_ready_fd, pause_resume_fd};
    const int destinations[] = {3, 4, 5, 6, 7, 8};
    int copies[6] = {-1, -1, -1, -1, -1, -1};
    for (size_t i = 0; i < 6; ++i) {
        if (*sources[i] < 0) continue;
        copies[i] = fcntl(*sources[i], F_DUPFD_CLOEXEC, 10);
        if (copies[i] < 0) goto fail;
    }
    for (size_t i = 0; i < 6; ++i) {
        if (copies[i] >= 0) {
            if (dup2(copies[i], destinations[i]) < 0) goto fail;
            *sources[i] = destinations[i];
        } else {
            close(destinations[i]);
        }
    }
    for (size_t i = 0; i < 6; ++i)
        if (copies[i] >= 0) close(copies[i]);
    if (!close_from_fd(9)) goto fail;
    return true;
fail:
    for (size_t i = 0; i < 6; ++i)
        if (copies[i] >= 0) close(copies[i]);
    return false;
}

static bool descriptor_is_open(int fd) {
    return fcntl(fd, F_GETFD) >= 0 || errno != EBADF;
}

static bool guardian_descriptor_allowlist(int control_fd, int lifetime_fd,
                                          int workload_fd, int ready_fd,
                                          int pause_ready_fd,
                                          int pause_resume_fd) {
    if (control_fd != 3 || lifetime_fd != 4 ||
        (workload_fd >= 0 && workload_fd != 5) ||
        (ready_fd >= 0 && ready_fd != 6) ||
        (pause_ready_fd >= 0 && pause_ready_fd != 7) ||
        (pause_resume_fd >= 0 && pause_resume_fd != 8))
        return false;
    for (int fd = 0; fd <= 8; ++fd) {
        bool expected = fd <= STDERR_FILENO || fd == control_fd ||
                        fd == lifetime_fd || fd == workload_fd || fd == ready_fd ||
                        fd == pause_ready_fd || fd == pause_resume_fd;
        if (descriptor_is_open(fd) != expected) return false;
    }
    return true;
}

static bool install_handlers(int signal_pipe[2]) {
    if (pipe(signal_pipe) != 0) return false;
    if (!set_fd_flags(signal_pipe[0], true) || !set_fd_flags(signal_pipe[1], true)) {
        close(signal_pipe[0]);
        close(signal_pipe[1]);
        return false;
    }
    signal_pipe_write = signal_pipe[1];
    signal_pipe_read = signal_pipe[0];
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = cancellation_handler;
    sigemptyset(&action.sa_mask);
    sigaddset(&action.sa_mask, SIGINT);
    sigaddset(&action.sa_mask, SIGTERM);
    action.sa_flags = SA_RESTART;
    if (sigaction(SIGINT, &action, NULL) != 0 ||
        sigaction(SIGTERM, &action, NULL) != 0) {
        close(signal_pipe[0]);
        close(signal_pipe[1]);
        signal_pipe_write = -1;
        return false;
    }
    struct sigaction ignore_pipe;
    memset(&ignore_pipe, 0, sizeof(ignore_pipe));
    ignore_pipe.sa_handler = SIG_IGN;
    sigemptyset(&ignore_pipe.sa_mask);
    if (sigaction(SIGPIPE, &ignore_pipe, NULL) != 0) return false;
    sigset_t unblock;
    sigemptyset(&unblock);
    sigaddset(&unblock, SIGINT);
    sigaddset(&unblock, SIGTERM);
    return sigprocmask(SIG_UNBLOCK, &unblock, NULL) == 0;
}

static void reset_child_signal_state(void) {
    struct sigaction reset;
    memset(&reset, 0, sizeof(reset));
    reset.sa_handler = SIG_DFL;
    sigemptyset(&reset.sa_mask);
    sigaction(SIGINT, &reset, NULL);
    sigaction(SIGTERM, &reset, NULL);
    sigaction(SIGPIPE, &reset, NULL);
    sigset_t empty;
    sigemptyset(&empty);
    sigprocmask(SIG_SETMASK, &empty, NULL);
}

static bool reap_child_until(pid_t child, uint64_t deadline, int *status) {
    for (;;) {
        if (now_ns() >= signal_clipped_due(deadline, NFS_CANCEL_TARGET_EXIT_NS))
            return false;
        pid_t waited = waitpid(child, status, WNOHANG);
        if (waited == child) return WIFEXITED(*status) || WIFSIGNALED(*status);
        if (waited < 0) return false;
        if (now_ns() >= signal_clipped_due(deadline, NFS_CANCEL_TARGET_EXIT_NS))
            return false;
        struct timespec delay = {.tv_sec = 0, .tv_nsec = 5 * 1000 * 1000};
        nanosleep(&delay, NULL);
    }
}

static bool child_termination_observed(const siginfo_t *info, pid_t child) {
    return info->si_pid == child &&
           (info->si_code == CLD_EXITED || info->si_code == CLD_KILLED ||
            info->si_code == CLD_DUMPED);
}

static void terminate_child_bounded(pid_t child, uint64_t deadline) {
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    if (child <= 0 || waitid(P_PID, (id_t)child, &info,
                             WEXITED | WNOHANG | WNOWAIT) != 0)
        return; /* Lost retained-child identity never authorizes a PID signal. */
    int status = 0;
    if (!child_termination_observed(&info, child)) kill(child, SIGKILL);
    (void)reap_child_until(child, deadline, &status);
}

static bool write_all(int fd, const void *buffer, size_t length) {
    const uint8_t *cursor = buffer;
    while (length > 0) {
        ssize_t written = write(fd, cursor, length);
        if (written < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        cursor += (size_t)written;
        length -= (size_t)written;
    }
    return true;
}

static bool write_line(int fd, const char *format, ...) {
    char buffer[NFS_CONTROL_STORAGE];
    va_list args;
    va_start(args, format);
    int size = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    if (size < 0 || (size_t)size > NFS_CONTROL_MAX) return false;
    return write_all(fd, buffer, (size_t)size);
}

static bool write_release_with_signal_gate(int fd, uint32_t generation,
                                           const char *role,
                                           const char *launch_ref) {
    sigset_t blocked, previous, pending;
    sigemptyset(&blocked);
    sigaddset(&blocked, SIGINT);
    sigaddset(&blocked, SIGTERM);
    if (sigprocmask(SIG_BLOCK, &blocked, &previous) != 0) return false;
    bool cancelled = atomic_load_explicit(&accepted_signal, memory_order_relaxed) != 0;
    if (sigpending(&pending) != 0) cancelled = true;
    else if (sigismember(&pending, SIGINT) || sigismember(&pending, SIGTERM))
        cancelled = true;
    bool written = false;
    if (!cancelled)
        written = write_line(fd, "RELEASE 3 %u %s %s\n", generation, role,
                             launch_ref);
    if (sigprocmask(SIG_SETMASK, &previous, NULL) != 0) return false;
    return written;
}

static int read_line_deadline(int fd, char *buffer, size_t capacity,
                              uint64_t deadline) {
    size_t used = 0;
    while (used + 1 < capacity) {
        if (now_ns() >= deadline) return 0;
        struct pollfd pollfd_value = {.fd = fd, .events = POLLIN | POLLHUP};
        int polled = poll(&pollfd_value, 1, remaining_ms(deadline));
        if (now_ns() >= deadline) return 0;
        if (polled == 0) return 0;
        if (polled < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        char byte;
        ssize_t count = read(fd, &byte, 1);
        if (count == 0) return used == 0 ? -2 : -1;
        if (count < 0) {
            if (errno == EINTR || errno == EAGAIN) continue;
            return -1;
        }
        buffer[used++] = byte;
        if (byte == '\n') {
            buffer[used] = '\0';
            return now_ns() < deadline ? 1 : 0;
        }
    }
    return -1;
}

static int read_line_supervisor_until(int fd, int signal_fd, char *buffer,
                                      size_t capacity, uint64_t fixed_deadline,
                                      uint64_t signal_offset) {
    size_t used = 0;
    if (capacity < 2) return -1;
    while (used < capacity - 1U) {
        uint64_t deadline = signal_clipped_due(fixed_deadline, signal_offset);
        if (now_ns() >= deadline) return 0;
        struct pollfd items[2] = {
            {.fd = fd, .events = POLLIN | POLLHUP | POLLERR},
            {.fd = signal_fd, .events = POLLIN},
        };
        int polled = poll(items, 2, remaining_ms(deadline));
        if (polled == 0) return 0;
        if (polled < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (now_ns() >= signal_clipped_due(fixed_deadline, signal_offset)) return 0;
        if (items[1].revents & POLLIN) {
            uint8_t pending[32];
            while (read(signal_fd, pending, sizeof(pending)) > 0) {}
            continue;
        }
        if (!(items[0].revents & (POLLIN | POLLHUP | POLLERR))) continue;
        char ch;
        ssize_t count = read(fd, &ch, 1);
        if (count == 0) return used == 0 ? -2 : -1;
        if (count < 0) {
            if (errno == EINTR || errno == EAGAIN) continue;
            return -1;
        }
        buffer[used++] = ch;
        if (ch == '\0') return -1;
        if (ch == '\n') {
            buffer[used] = '\0';
            return now_ns() < signal_clipped_due(fixed_deadline, signal_offset) ? 1 : 0;
        }
    }
    return -1;
}

static int read_line_supervisor(int fd, int signal_fd, char *buffer,
                                size_t capacity, uint64_t fixed_deadline) {
    return read_line_supervisor_until(fd, signal_fd, buffer, capacity,
                                      fixed_deadline, NFS_CANCEL_OBSERVE_END_NS);
}

static bool parse_u64(const char *value, uint64_t *result) {
    if (value == NULL || *value == '\0' ||
        (value[0] == '0' && value[1] != '\0'))
        return false;
    for (const char *cursor = value; *cursor != '\0'; ++cursor)
        if (*cursor < '0' || *cursor > '9') return false;
    char *end = NULL;
    errno = 0;
    unsigned long long parsed = strtoull(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0') return false;
    *result = (uint64_t)parsed;
    return true;
}

static bool parse_long(const char *value, long *result) {
    if (value == NULL || *value == '\0' ||
        (value[0] == '0' && value[1] != '\0') || value[0] == '+')
        return false;
    const char *digits = value[0] == '-' ? value + 1 : value;
    if (*digits == '\0' || (*digits == '0' && digits[1] != '\0')) return false;
    for (const char *cursor = digits; *cursor != '\0'; ++cursor)
        if (*cursor < '0' || *cursor > '9') return false;
    char *end = NULL;
    errno = 0;
    long parsed = strtol(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0') return false;
    *result = parsed;
    return true;
}

static bool parse_positive_pid(const char *value, pid_t *result) {
    uint64_t parsed = 0;
    if (!parse_u64(value, &parsed) || parsed == 0 || parsed > (uint64_t)INT_MAX)
        return false;
    *result = (pid_t)parsed;
    return true;
}

static bool safe_atom(const char *value, size_t maximum) {
    if (value == NULL) return false;
    size_t length = strlen(value);
    if (length == 0 || length > maximum) return false;
    for (size_t i = 0; i < length; ++i) {
        unsigned char byte = (unsigned char)value[i];
        if (!((byte >= 'a' && byte <= 'z') || (byte >= 'A' && byte <= 'Z') ||
              (byte >= '0' && byte <= '9') || byte == '-' || byte == '_' ||
              byte == '.' || byte == ':' || byte == '/'))
            return false;
    }
    return true;
}

static bool native_ascii_control_line(const char *line) {
    const char *newline = memchr(line, '\n', NFS_CONTROL_MAX);
    if (newline == NULL || newline == line || newline[1] != '\0') return false;
    if (line[0] == ' ' || newline[-1] == ' ') return false;
    for (const unsigned char *cursor = (const unsigned char *)line;
         cursor < (const unsigned char *)newline; ++cursor) {
        if (*cursor < 0x20U || *cursor > 0x7eU || *cursor == '\t' ||
            (*cursor == ' ' && cursor[1] == ' '))
            return false;
    }
    return true;
}

static size_t split_fields(char *line, char *fields[], size_t capacity) {
    size_t count = 0;
    char *save = NULL;
    for (char *token = strtok_r(line, " \n", &save);
         token != NULL;
         token = strtok_r(NULL, " \n", &save)) {
        if (count == capacity) return capacity + 1;
        fields[count++] = token;
    }
    return count;
}

struct message_spec {
    const char *verb;
    unsigned argc;
    const char *roles;
};

static const struct message_spec message_specs[] = {
    {"HELLO", 8, "GOPRAQW"}, {"HELLO_OK", 6, "S"},
    {"ANCHOR_READY", 7, "H"},
    {"GROUP_READY", 9, "G"}, {"GROUP_ACK", 3, "S"},
    {"RELEASE", 5, "S"}, {"WORKLOAD_STARTED", 4, "G"},
    {"WORKLOAD_EXIT", 6, "G"}, {"QUIESCE", 5, "S"},
    {"EXIT_PERMIT", 5, "S"}, {"GUARD_EXITING", 5, "G"},
    {"BLOB_BEGIN", 7, "OPRS"}, {"BLOB_ACCEPT", 4, "SOPR"},
    {"BLOB_ACK", 5, "SOPR"}, {"OBSERVE", 8, "S"},
    {"OBSERVED", 6, "Q"}, {"CLEANUP_RESULT", 5, "S"},
    {"CANCEL", 6, "S"}, {"ABORT", 7, "S"},
    {"ERROR", 5, "GOPRAQW"}, {"DIAG", 5, "GOPRAQW"},
    {"DRAIN", 3, "S"}, {"DRAINED", 3, "W"},
};

static bool valid_foundation_fields(char *fields[], size_t count,
                                    char sender_role,
                                    const char *expected_nonce) {
    uint64_t value = 0, other = 0;
    pid_t pid = 0, second_pid = 0, third_pid = 0;
    const char *verb = fields[0];
    if (strcmp(verb, "HELLO") == 0) {
        if (!parse_u64(fields[2], &value) || value != NFS_PROTOCOL_VERSION ||
            expected_nonce == NULL || !is_lower_hex(fields[3], 32) ||
            strcmp(fields[3], expected_nonce) != 0 || strlen(fields[4]) != 1 ||
            fields[4][0] != sender_role || !parse_positive_pid(fields[5], &pid) ||
            !parse_u64(fields[7], &value))
            return false;
        if (sender_role == 'O' || sender_role == 'A')
            return strcmp(fields[6], "supervised") == 0 && value == 0;
        return strcmp(fields[6], selected_clock_name()) == 0 && value > 0;
    }
    if (strcmp(verb, "HELLO_OK") == 0)
        return parse_u64(fields[2], &value) && value == NFS_PROTOCOL_VERSION &&
               expected_nonce != NULL && is_lower_hex(fields[3], 32) &&
               strcmp(fields[3], expected_nonce) == 0 &&
               strcmp(fields[4], selected_clock_name()) == 0 &&
               parse_u64(fields[5], &value) && value > 0;
    if (strcmp(verb, "GROUP_READY") == 0)
        return parse_u64(fields[2], &value) && value > 0 && value <= NFS_GROUP_MAX &&
               parse_positive_pid(fields[3], &pid) &&
               parse_positive_pid(fields[4], &second_pid) &&
               parse_positive_pid(fields[5], &third_pid) &&
               parse_u64(fields[6], &other) && other > 0 &&
               pid == second_pid && pid != third_pid &&
               safe_atom(fields[7], 63) &&
               parse_positive_pid(fields[8], &second_pid) && second_pid != pid;
    if (strcmp(verb, "GROUP_ACK") == 0)
        return parse_u64(fields[2], &value) && value > 0 && value <= NFS_GROUP_MAX;
    if (strcmp(verb, "QUIESCE") == 0)
        return parse_u64(fields[2], &value) && value > 0 && value <= NFS_GROUP_MAX &&
               parse_u64(fields[3], &value) && parse_u64(fields[4], &other) &&
               value <= other;
    if (strcmp(verb, "EXIT_PERMIT") == 0 ||
        strcmp(verb, "GUARD_EXITING") == 0)
        return parse_u64(fields[2], &value) && value > 0 && value <= NFS_GROUP_MAX &&
               (strcmp(fields[3], "observed") == 0 ||
                strcmp(fields[3], "reaped-fixed") == 0) &&
               parse_u64(fields[4], &other) && other > 0;
    if (strcmp(verb, "RELEASE") == 0)
        return parse_u64(fields[2], &value) && value > 0 && value <= NFS_GROUP_MAX &&
               safe_atom(fields[3], 32) && safe_atom(fields[4], 96);
    if (strcmp(verb, "WORKLOAD_STARTED") == 0)
        return parse_u64(fields[2], &value) && value > 0 && value <= NFS_GROUP_MAX &&
               parse_positive_pid(fields[3], &pid);
    if (strcmp(verb, "WORKLOAD_EXIT") == 0) {
        if (!parse_u64(fields[2], &value) || value == 0 || value > NFS_GROUP_MAX ||
            !parse_u64(fields[4], &other) || strcmp(fields[5], "reaped") != 0)
            return false;
        if (strcmp(fields[3], "exit") == 0) return other <= 255;
        return strcmp(fields[3], "signal") == 0 && other > 0 && other < 128;
    }
    if (strcmp(verb, "BLOB_BEGIN") == 0)
        return safe_atom(fields[2], 32) && strlen(fields[3]) == 1 &&
               fields[3][0] == sender_role && parse_u64(fields[4], &value) && value > 0 &&
               parse_u64(fields[5], &other) && other <= NFS_ATTEMPT_MAX &&
               is_lower_hex(fields[6], 64);
    if (strcmp(verb, "BLOB_ACCEPT") == 0)
        return strlen(fields[2]) == 1 && strchr("GOPRAQW", fields[2][0]) != NULL &&
               parse_u64(fields[3], &value) && value > 0;
    if (strcmp(verb, "BLOB_ACK") == 0)
        return strlen(fields[2]) == 1 && strchr("GOPRAQW", fields[2][0]) != NULL &&
               parse_u64(fields[3], &value) && value > 0 &&
               is_lower_hex(fields[4], 64);
    if (strcmp(verb, "OBSERVE") == 0)
        return parse_u64(fields[2], &value) && value > 0 &&
               parse_u64(fields[3], &other) && other > 0 && other <= NFS_GROUP_MAX &&
               parse_positive_pid(fields[4], &pid) && parse_positive_pid(fields[5], &pid) &&
               parse_positive_pid(fields[6], &pid) && safe_atom(fields[7], 63);
    if (strcmp(verb, "OBSERVED") == 0)
        return parse_u64(fields[2], &value) && value > 0 &&
               parse_u64(fields[3], &other) && other > 0 && other <= NFS_GROUP_MAX &&
               (strcmp(fields[4], "confirmed") == 0 ||
                strcmp(fields[4], "unconfirmed") == 0) && safe_atom(fields[5], 96);
    if (strcmp(verb, "CLEANUP_RESULT") == 0)
        return parse_u64(fields[2], &value) && value > 0 && value <= NFS_GROUP_MAX &&
               (strcmp(fields[3], "confirmed") == 0 ||
                strcmp(fields[3], "unconfirmed") == 0) && safe_atom(fields[4], 96);
    if (strcmp(verb, "CANCEL") == 0)
        return parse_u64(fields[2], &value) && (value == SIGINT || value == SIGTERM) &&
               parse_u64(fields[3], &value) && parse_u64(fields[4], &value) &&
               parse_u64(fields[5], &value);
    if (strcmp(verb, "ABORT") == 0)
        return safe_atom(fields[2], 96) && safe_atom(fields[3], 32) &&
               parse_u64(fields[4], &value) && parse_u64(fields[5], &value) &&
               parse_u64(fields[6], &value);
    if (strcmp(verb, "ERROR") == 0)
        return safe_atom(fields[2], 32) && safe_atom(fields[3], 96) &&
               safe_atom(fields[4], 32);
    if (strcmp(verb, "DIAG") == 0)
        return safe_atom(fields[2], 32) && safe_atom(fields[3], 32) &&
               safe_atom(fields[4], 237);
    if (strcmp(verb, "DRAIN") == 0)
        return parse_u64(fields[2], &value);
    if (strcmp(verb, "DRAINED") == 0)
        return strcmp(fields[2], "persisted") == 0 ||
               strcmp(fields[2], "partial") == 0 ||
               strcmp(fields[2], "unavailable") == 0;
    (void)count;
    return false;
}

static bool validate_control_line(char *line, char sender_role,
                                  uint32_t *last_sequence,
                                  const char *expected_nonce,
                                  bool require_hello) {
    if (!native_ascii_control_line(line)) return false;
    char *fields[12] = {0};
    size_t count = split_fields(line, fields, 12);
    if (count < 2 || count > 12) return false;
    uint64_t sequence64;
    if (!parse_u64(fields[1], &sequence64) || sequence64 == 0 ||
        sequence64 > UINT32_MAX || sequence64 <= *last_sequence ||
        (*last_sequence == 0 && sequence64 != 1))
        return false;
    if (require_hello && *last_sequence == 0 && strcmp(fields[0], "HELLO") != 0)
        return false;
    if (*last_sequence != 0 && strcmp(fields[0], "HELLO") == 0) return false;
    const struct message_spec *spec = NULL;
    for (size_t i = 0; i < sizeof(message_specs) / sizeof(message_specs[0]); ++i) {
        if (strcmp(fields[0], message_specs[i].verb) == 0) {
            spec = &message_specs[i];
            break;
        }
    }
    if (spec == NULL || spec->argc != count ||
        strchr(spec->roles, sender_role) == NULL)
        return false;
    if (!valid_foundation_fields(fields, count, sender_role, expected_nonce)) return false;
    *last_sequence = (uint32_t)sequence64;
    return true;
}

static bool read_exact(int fd, void *buffer, size_t length) {
    uint8_t *cursor = buffer;
    while (length > 0) {
        ssize_t count = read(fd, cursor, length);
        if (count == 0) return false;
        if (count < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        cursor += (size_t)count;
        length -= (size_t)count;
    }
    return true;
}

static bool read_exact_deadline(int fd, void *buffer, size_t length,
                                uint64_t deadline) {
    uint8_t *cursor = buffer;
    while (length > 0) {
        struct pollfd pollfd_value = {.fd = fd, .events = POLLIN | POLLHUP};
        int polled = poll(&pollfd_value, 1, remaining_ms(deadline));
        if (polled == 0) return false;
        if (polled < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        ssize_t count = read(fd, cursor, length);
        if (count == 0) return false;
        if (count < 0) {
            if (errno == EINTR || errno == EAGAIN) continue;
            return false;
        }
        cursor += (size_t)count;
        length -= (size_t)count;
    }
    return true;
}

static int validate_wire(const char *role_arg, const char *nonce) {
    if (role_arg == NULL || strlen(role_arg) != 1 || !is_lower_hex(nonce, 32)) return 2;
    char role = role_arg[0];
    if (strchr("GOPRAQW", role) == NULL) return 2;
    uint32_t last_sequence = 0;
    uint32_t receiver_sequence = 0;
    bool received_message = false;
    bool group_ready = false, workload_started = false, workload_exited = false;
    bool observed = false, drained = false;
    uint64_t group_generation = 0;
    uint64_t retained = 0;
    uint64_t last_transfer = 0;
    uint64_t deadline = now_ns() + NFS_OBSERVATION_NS;
    for (;;) {
        char line[NFS_CONTROL_STORAGE];
        int line_status = read_line_deadline(STDIN_FILENO, line, sizeof(line), deadline);
        if (line_status == -2) return received_message ? 0 : 2;
        if (line_status != 1) return 2;
        size_t used = strlen(line);
        char original[NFS_CONTROL_STORAGE];
        memcpy(original, line, used + 1);
        if (!validate_control_line(line, role, &last_sequence, nonce, true)) return 2;
        received_message = true;
        char state_copy[NFS_CONTROL_STORAGE];
        memcpy(state_copy, original, used + 1);
        char *state_fields[12];
        size_t state_count = split_fields(state_copy, state_fields, 12);
        (void)state_count;
        const char *verb = state_fields[0];
        if (strcmp(verb, "HELLO") != 0 && strcmp(verb, "DIAG") != 0 &&
            strcmp(verb, "ERROR") != 0) {
            bool ordered = false;
            if ((role == 'O' || role == 'P' || role == 'R') &&
                strcmp(verb, "BLOB_BEGIN") == 0)
                ordered = true;
            else if (role == 'G' && strcmp(verb, "GROUP_READY") == 0 &&
                     !group_ready && !workload_started && !workload_exited) {
                if (!parse_u64(state_fields[2], &group_generation)) return 2;
                group_ready = true;
                ordered = true;
            } else if (role == 'G' && strcmp(verb, "WORKLOAD_STARTED") == 0 &&
                       group_ready && !workload_started && !workload_exited) {
                uint64_t reference = 0;
                if (!parse_u64(state_fields[2], &reference) ||
                    reference != group_generation)
                    return 2;
                workload_started = true;
                ordered = true;
            } else if (role == 'G' && strcmp(verb, "WORKLOAD_EXIT") == 0 &&
                       workload_started && !workload_exited) {
                uint64_t reference = 0;
                if (!parse_u64(state_fields[2], &reference) ||
                    reference != group_generation)
                    return 2;
                workload_exited = true;
                ordered = true;
            } else if (role == 'Q' && strcmp(verb, "OBSERVED") == 0 && !observed) {
                observed = true;
                ordered = true;
            } else if (role == 'W' && strcmp(verb, "DRAINED") == 0 && !drained) {
                drained = true;
                ordered = true;
            }
            if (!ordered) return 2;
        }
        if (strncmp(original, "BLOB_BEGIN ", 11) != 0) continue;

        char *fields[10];
        size_t field_count = split_fields(original, fields, 10);
        uint64_t transfer, total;
        if (field_count != 7 || !parse_u64(fields[4], &transfer) || transfer == 0 ||
            transfer <= last_transfer || transfer > UINT32_MAX ||
            !parse_u64(fields[5], &total) || total > NFS_ATTEMPT_MAX ||
            !is_lower_hex(fields[6], 64))
            return 2;
        if (strlen(fields[3]) != 1 || fields[3][0] != role) return 2;
        const struct payload_spec *payload_spec = NULL;
        for (size_t i = 0; i < sizeof(payload_specs) / sizeof(payload_specs[0]); ++i)
            if (strcmp(fields[2], payload_specs[i].name) == 0) {
                payload_spec = &payload_specs[i];
                break;
            }
        if (payload_spec == NULL || payload_spec->owner != role ||
            total > payload_spec->maximum)
            return 2;
        char accept[NFS_CONTROL_STORAGE], accept_copy[NFS_CONTROL_STORAGE];
        if (read_line_deadline(STDIN_FILENO, accept, sizeof(accept), deadline) != 1)
            return 2;
        strcpy(accept_copy, accept);
        if (!validate_control_line(accept, 'S', &receiver_sequence, nonce, false))
            return 2;
        char *accept_fields[6];
        size_t accept_count = split_fields(accept_copy, accept_fields, 6);
        uint64_t accepted_transfer = 0;
        if (accept_count != 4 || strcmp(accept_fields[0], "BLOB_ACCEPT") != 0 ||
            strlen(accept_fields[2]) != 1 || accept_fields[2][0] != role ||
            !parse_u64(accept_fields[3], &accepted_transfer) ||
            accepted_transfer != transfer)
            return 2;
        /* BLOB_BEGIN fields are: verb seq kind owner transfer total sha256. */
        const char *expected_digest = fields[6];
        if (!is_lower_hex(expected_digest, 64)) return 2;
        struct sha256_ctx digest;
        sha256_init(&digest);
        if (retained + total > NFS_ATTEMPT_MAX) return 2;
        uint64_t received = 0;
        for (;;) {
            uint32_t header[4];
            if (!read_exact_deadline(STDIN_FILENO, header, sizeof(header), deadline)) return 2;
            if (memcmp(header, "NFS1", 4) != 0) return 2;
            uint32_t kind = ntohl(header[1]);
            uint32_t sequence = ntohl(header[2]);
            uint32_t length = ntohl(header[3]);
            if (kind != payload_spec->kind || sequence != (uint32_t)transfer ||
                length > NFS_FRAME_MAX)
                return 2;
            if (length == 0) break;
            if (received + length > total || received + length > NFS_ATTEMPT_MAX) return 2;
            uint8_t *payload = malloc(length);
            if (payload == NULL) return 2;
            bool ok = read_exact_deadline(STDIN_FILENO, payload, length, deadline);
            if (ok) sha256_update(&digest, payload, length);
            free(payload);
            if (!ok) return 2;
            received += length;
        }
        if (received != total) return 2;
        uint8_t result[32];
        char result_hex[65];
        sha256_final(&digest, result);
        digest_hex(result, result_hex);
        if (strcmp(result_hex, expected_digest) != 0) return 2;
        retained += received;
        last_transfer = transfer;
    }
}

static bool parse_linux_stat_line(const char *line, struct linux_stat_record *record) {
    if (line == NULL || record == NULL) return false;
    char *end = NULL;
    errno = 0;
    long pid = strtol(line, &end, 10);
    if (errno != 0 || end == line || pid <= 0 || *end != ' ') return false;
    const char *open_paren = strchr(end, '(');
    const char *close_paren = strrchr(end, ')');
    if (open_paren == NULL || close_paren == NULL || close_paren <= open_paren ||
        close_paren[1] != ' ' || close_paren[2] == '\0' || close_paren[3] != ' ')
        return false;
    record->pid = pid;
    record->state = close_paren[2];
    const char *cursor = close_paren + 4;
    long pgrp = 0, session = 0;
    unsigned long long start_identity = 0;
    for (int field = 4; field <= 22; ++field) {
        while (*cursor == ' ') ++cursor;
        if (*cursor == '\0' || *cursor == '\n') return false;
        errno = 0;
        char *token_end = NULL;
        if (field == 22) {
            start_identity = strtoull(cursor, &token_end, 10);
        } else {
            long value = strtol(cursor, &token_end, 10);
            if (field == 5) pgrp = value;
            if (field == 6) session = value;
        }
        if (errno != 0 || token_end == cursor ||
            (*token_end != ' ' && *token_end != '\0' && *token_end != '\n'))
            return false;
        cursor = token_end;
    }
    if (pgrp <= 0 || session <= 0 || start_identity == 0) return false;
    record->pgrp = pgrp;
    record->session = session;
    record->start_identity = start_identity;
    return true;
}

static bool process_start_identity(pid_t pid, char *buffer, size_t capacity) {
#if defined(NFS_PLATFORM_DARWIN)
    int mib[4] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, pid};
    struct kinfo_proc info;
    size_t size = sizeof(info);
    memset(&info, 0, sizeof(info));
    if (sysctl(mib, 4, &info, &size, NULL, 0) != 0 || size != sizeof(info) ||
        info.kp_proc.p_pid != pid)
        return false;
    int result = snprintf(buffer, capacity, "%lld.%06d",
                          (long long)info.kp_proc.p_starttime.tv_sec,
                          info.kp_proc.p_starttime.tv_usec);
    return result > 0 && (size_t)result < capacity;
#elif defined(NFS_PLATFORM_LINUX)
    char path[64], line[4096];
    int size = snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid);
    if (size <= 0 || (size_t)size >= sizeof(path)) return false;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    ssize_t count = read(fd, line, sizeof(line) - 1);
    close(fd);
    if (count <= 0 || (size_t)count >= sizeof(line) - 1) return false;
    line[count] = '\0';
    struct linux_stat_record record;
    if (!parse_linux_stat_line(line, &record) || record.pid != pid) return false;
    size = snprintf(buffer, capacity, "%llu", record.start_identity);
    return size > 0 && (size_t)size < capacity;
#else
    (void)pid;
    (void)buffer;
    (void)capacity;
    return false;
#endif
}

static bool process_is_stopped(pid_t pid) {
#if defined(NFS_PLATFORM_DARWIN)
    int mib[4] = {CTL_KERN, KERN_PROC, KERN_PROC_PID, pid};
    struct kinfo_proc info;
    size_t size = sizeof(info);
    memset(&info, 0, sizeof(info));
    return sysctl(mib, 4, &info, &size, NULL, 0) == 0 &&
           size == sizeof(info) && info.kp_proc.p_pid == pid &&
           info.kp_proc.p_stat == SSTOP;
#elif defined(NFS_PLATFORM_LINUX)
    char path[64], line[4096];
    int size = snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid);
    if (size <= 0 || (size_t)size >= sizeof(path)) return false;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    ssize_t count = read(fd, line, sizeof(line) - 1U);
    close(fd);
    if (count <= 0 || (size_t)count >= sizeof(line) - 1U) return false;
    line[count] = '\0';
    struct linux_stat_record record;
    return parse_linux_stat_line(line, &record) && record.pid == pid &&
           (record.state == 'T' || record.state == 't');
#else
    (void)pid;
    return false;
#endif
}

struct census_identity {
    pid_t pid;
    unsigned long long start;
};

struct census_snapshot {
    bool complete;
    bool live;
    size_t count;
    struct census_identity members[1024];
};

static int compare_census_identity(const void *left, const void *right) {
    const struct census_identity *a = left, *b = right;
    if (a->pid < b->pid) return -1;
    if (a->pid > b->pid) return 1;
    if (a->start < b->start) return -1;
    return a->start > b->start ? 1 : 0;
}

#if defined(NFS_PLATFORM_LINUX)
static bool linux_process_has_live_task(pid_t pid, pid_t pgid, pid_t sid,
                                        uint64_t deadline, bool *live) {
    char task_path[64];
    int length = snprintf(task_path, sizeof(task_path), "/proc/%ld/task", (long)pid);
    if (length <= 0 || (size_t)length >= sizeof(task_path)) return false;
    DIR *tasks = opendir(task_path);
    if (tasks == NULL) return false;
    bool saw_task = false, complete = true;
    struct dirent *entry;
    size_t task_count = 0;
    while ((entry = readdir(tasks)) != NULL) {
        if (now_ns() >= deadline || ++task_count > 4096U) {
            complete = false;
            break;
        }
        char *end = NULL;
        long tid = strtol(entry->d_name, &end, 10);
        if (tid <= 0 || end == entry->d_name || *end != '\0') continue;
        saw_task = true;
        char path[96], line[4096];
        length = snprintf(path, sizeof(path), "/proc/%ld/task/%ld/stat",
                          (long)pid, tid);
        if (length <= 0 || (size_t)length >= sizeof(path)) {
            complete = false;
            break;
        }
        int fd = open(path, O_RDONLY | O_CLOEXEC);
        if (fd < 0) {
            complete = false;
            break;
        }
        ssize_t count = read(fd, line, sizeof(line) - 1U);
        int saved = errno;
        close(fd);
        errno = saved;
        if (count <= 0 || (size_t)count >= sizeof(line) - 1U) {
            complete = false;
            break;
        }
        line[count] = '\0';
        struct linux_stat_record record;
        if (!parse_linux_stat_line(line, &record) || record.pgrp != pgid ||
            record.session != sid) {
            complete = false;
            break;
        }
        if (record.state != 'Z' && record.state != 'X') *live = true;
    }
    closedir(tasks);
    return complete && saw_task;
}
#endif

static struct census_snapshot census_group(pid_t pgid, pid_t sid,
                                            uint64_t deadline) {
    struct census_snapshot snapshot;
    memset(&snapshot, 0, sizeof(snapshot));
    snapshot.complete = true;
#if defined(NFS_PLATFORM_DARWIN)
    int mib[4] = {CTL_KERN, KERN_PROC, KERN_PROC_PGRP, pgid};
    size_t size = 0;
    if (sysctl(mib, 4, NULL, &size, NULL, 0) != 0 || size > NFS_FRAME_MAX ||
        now_ns() >= deadline) {
        snapshot.complete = false;
        return snapshot;
    }
    if (size == 0) return snapshot;
    struct kinfo_proc *records = calloc(1, size);
    if (records == NULL) {
        snapshot.complete = false;
        return snapshot;
    }
    size_t actual = size;
    if (sysctl(mib, 4, records, &actual, NULL, 0) != 0 || actual > size ||
        actual % sizeof(*records) != 0 ||
        actual / sizeof(*records) > 1024U) {
        free(records);
        snapshot.complete = false;
        return snapshot;
    }
    snapshot.count = actual / sizeof(*records);
    for (size_t i = 0; i < snapshot.count; ++i) {
        pid_t pid = records[i].kp_proc.p_pid;
        if (pid <= 0 || getsid(pid) != sid) snapshot.complete = false;
        snapshot.members[i].pid = pid;
        snapshot.members[i].start =
            (unsigned long long)records[i].kp_proc.p_starttime.tv_sec * UINT64_C(1000000) +
            (unsigned long long)records[i].kp_proc.p_starttime.tv_usec;
        if (records[i].kp_proc.p_stat != SZOMB) snapshot.live = true;
    }
    free(records);
#elif defined(NFS_PLATFORM_LINUX)
    DIR *directory = opendir("/proc");
    if (directory == NULL) {
        snapshot.complete = false;
        return snapshot;
    }
    struct dirent *entry;
    size_t rows = 0;
    while ((entry = readdir(directory)) != NULL) {
        if (now_ns() >= deadline || ++rows > 131072U) {
            snapshot.complete = false;
            break;
        }
        char *name_end = NULL;
        long candidate = strtol(entry->d_name, &name_end, 10);
        if (candidate <= 0 || name_end == entry->d_name || *name_end != '\0') continue;
        char path[64], line[4096];
        int path_len = snprintf(path, sizeof(path), "/proc/%ld/stat", candidate);
        if (path_len <= 0 || (size_t)path_len >= sizeof(path)) {
            snapshot.complete = false;
            break;
        }
        int fd = open(path, O_RDONLY | O_CLOEXEC);
        if (fd < 0) {
            if (errno != ENOENT) snapshot.complete = false;
            continue;
        }
        ssize_t count = read(fd, line, sizeof(line) - 1U);
        int saved = errno;
        close(fd);
        errno = saved;
        if (count <= 0 || (size_t)count >= sizeof(line) - 1U) {
            snapshot.complete = false;
            continue;
        }
        line[count] = '\0';
        struct linux_stat_record record;
        if (!parse_linux_stat_line(line, &record)) {
            snapshot.complete = false;
            continue;
        }
        if (record.pgrp != pgid) continue;
        if (snapshot.count == 1024U || record.session != sid) {
            snapshot.complete = false;
            break;
        }
        snapshot.members[snapshot.count].pid = (pid_t)record.pid;
        snapshot.members[snapshot.count].start = record.start_identity;
        ++snapshot.count;
        if (!linux_process_has_live_task((pid_t)record.pid, pgid, sid,
                                         deadline, &snapshot.live)) {
            snapshot.complete = false;
            break;
        }
    }
    closedir(directory);
#else
    (void)pgid;
    (void)sid;
    (void)deadline;
    snapshot.complete = false;
#endif
    qsort(snapshot.members, snapshot.count, sizeof(snapshot.members[0]),
          compare_census_identity);
    return snapshot;
}

static struct observation observe_group_once(pid_t pgid, pid_t sid,
                                             pid_t owner_pid,
                                             const char *start_identity) {
    struct observation result = {.confirmed = false, .reason = "unavailable"};
    char current_identity[64];
    if (!process_start_identity(owner_pid, current_identity,
                                sizeof(current_identity)) ||
        strcmp(current_identity, start_identity) != 0) {
        strcpy(result.reason, "owner-identity");
        return result;
    }
    uint64_t deadline = now_ns() + NFS_OBSERVATION_NS;
    struct census_snapshot first = census_group(pgid, sid, deadline);
    if (!first.complete) {
        strcpy(result.reason, "inventory-incomplete");
        return result;
    }
    struct timespec delay = {.tv_sec = 0, .tv_nsec = 10 * 1000 * 1000};
    nanosleep(&delay, NULL);
    struct census_snapshot second = census_group(pgid, sid, deadline);
    if (!second.complete) strcpy(result.reason, "inventory-incomplete");
    else if (first.count != second.count ||
             memcmp(first.members, second.members,
                    first.count * sizeof(first.members[0])) != 0)
        strcpy(result.reason, "inventory-changing");
    else if (first.live || second.live) strcpy(result.reason, "live-member");
    else {
        result.confirmed = true;
        strcpy(result.reason, first.count == 0 ? "two-consistent-empty" :
                                               "two-consistent-terminal");
    }
    return result;
}

struct anchor_handle {
    pid_t pid;
    pid_t pgid;
    pid_t sid;
    int lifetime_write;
};

struct phase_pause {
    const char *name;
    int ready_fd;
    int resume_fd;
};

static bool pause_at_phase(struct phase_pause *pause, const char *name) {
    if (pause == NULL || pause->name == NULL || strcmp(pause->name, name) != 0)
        return true;
    uint8_t ready = 'R', resume = 0;
    bool ok = write_all(pause->ready_fd, &ready, 1) &&
              read_exact(pause->resume_fd, &resume, 1) && resume == 'C';
    close(pause->ready_fd);
    close(pause->resume_fd);
    pause->ready_fd = -1;
    pause->resume_fd = -1;
    pause->name = NULL;
    return ok;
}

static void emit_event(int fd, const char *format, ...);
static bool retire_unconfirmed_child(pid_t child, pid_t payload_pgid,
                                      bool registered, uint32_t generation,
                                      const char *role, uint64_t hard_due,
                                      int diagnostics_fd);

static const char *signal_disposition_name(const struct sigaction *action) {
    if (action->sa_handler == SIG_DFL) return "default";
    if (action->sa_handler == SIG_IGN) return "ignored";
    return "handler";
}

/* S must retain every direct child until it deliberately reaps it. Normalize
 * this prerequisite at the common H boundary, before the first helper fork, so
 * both the compatibility and direct supervisor entry paths are covered. */
static bool initialize_sigchld_before_helpers(int diagnostics_fd) {
    struct sigaction inherited, reset, current;
    if (sigaction(SIGCHLD, NULL, &inherited) != 0) return false;
    memset(&reset, 0, sizeof(reset));
    reset.sa_handler = SIG_DFL;
    sigemptyset(&reset.sa_mask);
    reset.sa_flags = 0;
    if (sigaction(SIGCHLD, &reset, NULL) != 0 ||
        sigaction(SIGCHLD, NULL, &current) != 0 ||
        current.sa_handler != SIG_DFL)
        return false;
#if defined(SA_NOCLDWAIT)
    bool inherited_no_cldwait = (inherited.sa_flags & SA_NOCLDWAIT) != 0;
    if ((current.sa_flags & SA_NOCLDWAIT) != 0) return false;
#else
    bool inherited_no_cldwait = false;
#endif
    inherited_sigchld_disposition = signal_disposition_name(&inherited);
    inherited_sigchld_no_cldwait = inherited_no_cldwait;
    sigchld_prerequisite_ready = true;
    emit_event(diagnostics_fd,
               "SIGCHLD_PREREQUISITE inherited=%s inherited_no_cldwait=%s current=default current_no_cldwait=false before_helpers=true\n",
               inherited_sigchld_disposition,
               inherited_no_cldwait ? "true" : "false");
    return true;
}

static void emit_sigchld_prerequisite(int diagnostics_fd) {
    if (!sigchld_prerequisite_ready) return;
    emit_event(diagnostics_fd,
               "SIGCHLD_PREREQUISITE inherited=%s inherited_no_cldwait=%s current=default current_no_cldwait=false before_helpers=true\n",
               inherited_sigchld_disposition,
               inherited_sigchld_no_cldwait ? "true" : "false");
}

static void ignore_signal(int signum) {
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = SIG_IGN;
    sigemptyset(&action.sa_mask);
    (void)sigaction(signum, &action, NULL);
}

static void default_unblocked_signal(int signum) {
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = SIG_DFL;
    sigemptyset(&action.sa_mask);
    (void)sigaction(signum, &action, NULL);
    sigset_t one;
    sigemptyset(&one);
    sigaddset(&one, signum);
    (void)sigprocmask(SIG_UNBLOCK, &one, NULL);
}

static int anchor_child_main(int ready_fd, int lifetime_fd, const char *nonce,
                             pid_t expected_sid, struct phase_pause *pause) {
    /* These dispositions are the anchor's first actions after fork. */
    ignore_signal(SIGINT);
    ignore_signal(SIGTERM);
    default_unblocked_signal(SIGHUP);
    default_unblocked_signal(SIGCONT);
    if (!pause_at_phase(pause, "before-anchor-ready")) _exit(1);
    if (setpgid(0, 0) != 0) _exit(1);
    pid_t pid = getpid(), pgid = getpgrp(), sid = getsid(0);
    if (pid != pgid || sid != expected_sid ||
        !write_line(ready_fd, "ANCHOR_READY 1 %u %s %ld %ld %ld\n",
                    NFS_PROTOCOL_VERSION, nonce, (long)pid, (long)pgid,
                    (long)sid))
        _exit(1);
    close(ready_fd);
    if (lifetime_fd != 3) {
        if (dup2(lifetime_fd, 3) < 0) _exit(1);
        close(lifetime_fd);
        lifetime_fd = 3;
    }
    if (!close_from_fd(4)) _exit(1);
    close(STDIN_FILENO);
    close(STDOUT_FILENO);
    close(STDERR_FILENO);
    for (;;) {
        struct pollfd item = {.fd = lifetime_fd, .events = POLLIN | POLLHUP};
        int polled = poll(&item, 1, -1);
        if (polled < 0 && errno == EINTR) continue;
        if (polled <= 0 || (item.revents & (POLLIN | POLLHUP | POLLERR)))
            _exit(0);
    }
}

static bool start_anchor(struct anchor_handle *anchor, const char *nonce,
                         uint64_t deadline, int diagnostics_fd,
                         struct phase_pause *pause) {
    int ready[2] = {-1, -1}, lifetime[2] = {-1, -1};
    if (anchor_attempted || guardian_joins_disabled) return false;
    if (!initialize_sigchld_before_helpers(diagnostics_fd)) return false;
    anchor_attempted = true;
    if (now_ns() >= signal_clipped_due(deadline, NFS_CANCEL_OBSERVE_END_NS))
        return false;
    memset(anchor, 0, sizeof(*anchor));
    anchor->pid = -1;
    anchor->lifetime_write = -1;
    if (pipe(ready) != 0 || pipe(lifetime) != 0) goto fail;
    if (!set_fd_flags(ready[0], true) || !set_fd_flags(ready[1], false) ||
        !set_fd_flags(lifetime[0], false) || !set_fd_flags(lifetime[1], false))
        goto fail;
    pid_t inherited_sid = getsid(0);
    sigset_t blocked, previous;
    sigemptyset(&blocked);
    sigaddset(&blocked, SIGINT);
    sigaddset(&blocked, SIGTERM);
    if (sigprocmask(SIG_BLOCK, &blocked, &previous) != 0) goto fail;
    pid_t child = fork();
    if (child == 0) {
        close(ready[0]);
        close(lifetime[1]);
        if (signal_pipe_write >= 0) close(signal_pipe_write);
        anchor_child_main(ready[1], lifetime[0], nonce, inherited_sid, pause);
        _exit(1);
    }
    (void)sigprocmask(SIG_SETMASK, &previous, NULL);
    if (child < 0) goto fail;
    close(ready[1]); ready[1] = -1;
    close(lifetime[0]); lifetime[0] = -1;
    char line[NFS_CONTROL_STORAGE], original[NFS_CONTROL_STORAGE];
    if (read_line_supervisor(ready[0], signal_pipe_read, line, sizeof(line), deadline) != 1 ||
        !native_ascii_control_line(line)) {
        (void)retire_unconfirmed_child(child, 0, true, 0, "H-bootstrap", deadline, -1);
        goto fail;
    }
    strcpy(original, line);
    char *fields[8];
    size_t count = split_fields(original, fields, 8);
    uint64_t seq, version;
    long pid, pgid, sid;
    if (count != 7 || strcmp(fields[0], "ANCHOR_READY") != 0 ||
        !parse_u64(fields[1], &seq) || seq != 1 ||
        !parse_u64(fields[2], &version) || version != NFS_PROTOCOL_VERSION ||
        strcmp(fields[3], nonce) != 0 || !parse_long(fields[4], &pid) ||
        !parse_long(fields[5], &pgid) || !parse_long(fields[6], &sid) ||
        pid != child || pgid != child || sid != inherited_sid) {
        (void)retire_unconfirmed_child(child, 0, true, 0, "H-bootstrap", deadline, -1);
        goto fail;
    }
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    if (waitid(P_PID, (id_t)child, &info, WEXITED | WNOHANG | WNOWAIT) != 0 ||
        info.si_pid != 0) {
        (void)retire_unconfirmed_child(child, 0, true, 0, "H-bootstrap", deadline, -1);
        goto fail;
    }
    close(ready[0]);
    anchor->pid = child;
    anchor->pgid = child;
    anchor->sid = inherited_sid;
    anchor->lifetime_write = lifetime[1];
    emit_event(diagnostics_fd, "ANCHOR_READY %ld %ld %ld %ld\n", (long)child,
               (long)child, (long)inherited_sid, (long)getpgrp());
    return true;
fail:
    if (ready[0] >= 0) close(ready[0]);
    if (ready[1] >= 0) close(ready[1]);
    if (lifetime[0] >= 0) close(lifetime[0]);
    if (lifetime[1] >= 0) close(lifetime[1]);
    return false;
}

static void retire_anchor(struct anchor_handle *anchor, uint64_t deadline) {
    guardian_joins_disabled = true;
    if (anchor->lifetime_write >= 0) close(anchor->lifetime_write);
    anchor->lifetime_write = -1;
    if (anchor->pid <= 0) return;
    int status = 0;
    uint64_t graceful_due = earlier_due(deadline, now_ns() +
                                        UINT64_C(10) * NS_PER_MILLISECOND);
    if (!reap_child_until(anchor->pid, graceful_due, &status))
        (void)retire_unconfirmed_child(anchor->pid, 0, true, 0, "H", deadline, -1);
    anchor->pid = -1;
}

static bool retained_child_running(pid_t child) {
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    return child > 0 &&
           waitid(P_PID, (id_t)child, &info,
                  WEXITED | WNOHANG | WNOWAIT) == 0 && info.si_pid == 0;
}

/* One terminal retirement, never a new shutdown budget. The caller still owns
 * the unreaped direct child. Pre-registration requires a final derived-group
 * attempt after stopping G's ability to form that group. Registered generations
 * retire S's group authority before targeting G by PID. */
static bool retire_unconfirmed_child(pid_t child, pid_t payload_pgid,
                                      bool registered, uint32_t generation,
                                      const char *role, uint64_t hard_due,
                                      int diagnostics_fd) {
    hard_due = signal_clipped_due(hard_due, NFS_CANCEL_HARD_CUTOFF_NS);
    if (generation > NFS_GROUP_MAX) return false;
    volatile struct retirement_evidence *evidence = &retirement_evidence[generation];
    if (evidence->active) return evidence->child_reaped;
    *evidence = (struct retirement_evidence){.active = true, .owner_pid = child,
        .payload_pgid = payload_pgid, .hard_due = hard_due};
    int output = now_ns() < reserve_before(hard_due,
                     UINT64_C(100) * NS_PER_MILLISECOND) ? diagnostics_fd : -1;
    emit_event(output, "RETIRE_REVOKE %u %s %ld %llu\n", generation, role,
               (long)child, (unsigned long long)now_ns());
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    if (child <= 0 || waitid(P_PID, (id_t)child, &info,
                             WEXITED | WNOHANG | WNOWAIT) != 0) {
        emit_event(output, "RETIRE_CHILD %u %s owner-identity-lost cleanup=unconfirmed reaped=false generation_closed=false\n",
                   generation, role);
        return false;
    }
    evidence->owner_valid = true;
    evidence->termination_observed = child_termination_observed(&info, child);
    if (payload_pgid > 0) {
        int result = kill(-payload_pgid, SIGKILL), saved = result < 0 ? errno : 0;
        evidence->group_attempted = true;
        evidence->group_result = result;
        evidence->group_errno = saved;
        emit_event(output, "RETIRE_GROUP_KILL %u %s %ld %llu %d %d\n",
                   generation, role, (long)payload_pgid,
                   (unsigned long long)now_ns(), result, saved);
    }
    if (registered) {
        evidence->signals_retired = true;
        evidence->signals_retired_ns = now_ns();
        emit_event(output, "RETIRE_SIGNALS %u %s %llu\n", generation, role,
                   (unsigned long long)now_ns());
    }
    if (!child_termination_observed(&info, child)) {
        int result = kill(child, SIGKILL), saved = result < 0 ? errno : 0;
        evidence->pid_attempted = true;
        evidence->pid_result = result;
        evidence->pid_errno = saved;
        emit_event(output, "RETIRE_PID_KILL %u %s %ld %llu %d %d\n",
                   generation, role, (long)child,
                   (unsigned long long)now_ns(), result, saved);
    }
    if (!registered) {
        if (payload_pgid > 0) {
            int result = kill(-payload_pgid, SIGKILL), saved = result < 0 ? errno : 0;
            evidence->group_attempted = true;
            evidence->group_result = result;
            evidence->group_errno = saved;
            emit_event(output, "RETIRE_GROUP_KILL %u %s %ld %llu %d %d\n",
                       generation, role, (long)payload_pgid,
                       (unsigned long long)now_ns(), result, saved);
        }
        evidence->signals_retired = true;
        evidence->signals_retired_ns = now_ns();
        emit_event(output, "RETIRE_SIGNALS %u %s %llu\n", generation, role,
                   (unsigned long long)now_ns());
    }
    /* Exactly one terminal nonblocking reap, and none beginning after D. */
    int status = 0;
    evidence->hard_due = signal_clipped_due(hard_due, NFS_CANCEL_HARD_CUTOFF_NS);
    bool child_reaped = now_ns() < evidence->hard_due && waitpid(child, &status, WNOHANG) == child &&
        (WIFEXITED(status) || WIFSIGNALED(status));
    evidence->child_reaped = child_reaped;
    evidence->termination_observed |= child_reaped;
    emit_event(output,
               "RETIRE_CHILD %u %s %ld %llu child_reaped=%s termination=%s cleanup=unconfirmed reaped=false generation_closed=false\n",
               generation, role, (long)child, (unsigned long long)now_ns(),
               child_reaped ? "true" : "false",
               (child_reaped || child_termination_observed(&info, child)) ? "observed" : "unobserved");
    return child_reaped;
}

struct guardian_observer_slot {
    _Atomic int stop;
    _Atomic int request;
    _Atomic int ready;
    pid_t pgid;
    pid_t sid;
    pid_t owner_pid;
    char owner_identity[64];
    struct observation result;
    int test_ready_fd;
};

static void *guardian_observer_thread(void *opaque) {
    struct guardian_observer_slot *slot = opaque;
    bool test_stall = fixture_test_mode && getenv("NFS_TEST_G_OBSERVER_STALL") != NULL;
    while (atomic_load_explicit(&slot->stop, memory_order_acquire) == 0) {
        if (atomic_exchange_explicit(&slot->request, 0, memory_order_acq_rel)) {
            if (test_stall) {
                if (slot->test_ready_fd >= 0) {
                    (void)write_all(slot->test_ready_fd, "R", 1);
                    close(slot->test_ready_fd);
                    slot->test_ready_fd = -1;
                }
                struct timespec stall = {.tv_sec = 3, .tv_nsec = 0};
                nanosleep(&stall, NULL);
            }
            slot->result = observe_group_once(slot->pgid, slot->sid,
                                              slot->owner_pid,
                                              slot->owner_identity);
            atomic_store_explicit(&slot->ready, 1, memory_order_release);
        }
        struct timespec delay = {.tv_sec = 0, .tv_nsec = 5 * 1000 * 1000};
        nanosleep(&delay, NULL);
    }
    return NULL;
}

static int guardian_main(int control_fd, int lifetime_fd, int diagnostics_fd,
                         int workload_only_fd, uint32_t generation,
                         const char *nonce, pid_t guard_pgid, pid_t session_id,
                         const char *role, bool source_fixed_nonforking,
                         char *const workload_argv[], struct phase_pause *pause,
                         uint64_t bootstrap_due);
static void emit_event(int fd, const char *format, ...);
static void terminate_registered_group(pid_t pgid, pid_t guardian_pid,
                                       int lifetime_fd, uint64_t started,
                                       uint64_t hard_due, uint32_t generation,
                                       int diagnostics_fd);

struct observer_receive {
    char buffer[NFS_CONTROL_MAX * 2U];
    size_t used;
    uint32_t last_sequence;
    pid_t reported_pid;
    bool hello;
    bool observed;
    struct observation result;
};

static bool observer_message_matches(bool identity_active,
                                     uint64_t active_request,
                                     uint32_t active_generation,
                                     uint64_t incoming_request,
                                     uint64_t incoming_generation) {
    return identity_active && active_request == incoming_request &&
           incoming_generation == active_generation;
}

static bool source_fixed_role(const char *role) {
    return strcmp(role, "W") == 0 || strcmp(role, "verifier") == 0 ||
           strcmp(role, "Q") == 0;
}

static bool valid_exit_permit(uint32_t generation, const char *role,
                              bool release_revoked, bool workload_done,
                              uint32_t workload_exit_sequence,
                              uint64_t incoming_generation,
                              const char *proof_kind, uint64_t proof_ref) {
    if (!release_revoked || incoming_generation != generation || proof_ref == 0)
        return false;
    if (strcmp(proof_kind, "observed") == 0) return true;
    return strcmp(proof_kind, "reaped-fixed") == 0 &&
           source_fixed_role(role) && workload_done &&
           proof_ref == workload_exit_sequence;
}

static int observer_receive_bytes(struct observer_receive *receive, int fd,
                                  const char *nonce, uint64_t request_id,
                                  uint32_t target_generation) {
    if (receive->used == sizeof(receive->buffer)) return -1;
    ssize_t count = read(fd, receive->buffer + receive->used,
                         sizeof(receive->buffer) - receive->used);
    if (count < 0) return (errno == EAGAIN || errno == EINTR) ? 1 : -1;
    if (count == 0) return receive->used == 0 ? 0 : -1;
    receive->used += (size_t)count;
    for (;;) {
        char *newline = memchr(receive->buffer, '\n', receive->used);
        if (newline == NULL) return receive->used < sizeof(receive->buffer) ? 1 : -1;
        size_t length = (size_t)(newline - receive->buffer) + 1U;
        if (length > NFS_CONTROL_MAX) return -1;
        char line[NFS_CONTROL_STORAGE], original[NFS_CONTROL_STORAGE];
        memcpy(line, receive->buffer, length);
        line[length] = '\0';
        memcpy(original, line, length + 1U);
        memmove(receive->buffer, receive->buffer + length, receive->used - length);
        receive->used -= length;
        if (!validate_control_line(line, 'Q', &receive->last_sequence, nonce, true))
            return -1;
        char *fields[8];
        size_t field_count = split_fields(original, fields, 8);
        if (strcmp(fields[0], "HELLO") == 0) {
            if (receive->hello || field_count != 8 ||
                !parse_positive_pid(fields[5], &receive->reported_pid))
                return -1;
            receive->hello = true;
        } else if (strcmp(fields[0], "OBSERVED") == 0) {
            uint64_t incoming_request, incoming_generation;
            if (!receive->hello || receive->observed || field_count != 6 ||
                !parse_u64(fields[2], &incoming_request) ||
                !parse_u64(fields[3], &incoming_generation) ||
                !observer_message_matches(true, request_id, target_generation,
                                          incoming_request, incoming_generation))
                return -1;
            receive->result.confirmed = strcmp(fields[4], "confirmed") == 0;
            if (strlen(fields[5]) >= sizeof(receive->result.reason)) return -1;
            strcpy(receive->result.reason, fields[5]);
            receive->observed = true;
        } else {
            return -1;
        }
    }
}

static int observer_worker(int result_fd, uint64_t request_id,
                           uint32_t target_generation, pid_t pgid, pid_t sid,
                           pid_t leader_pid, const char *start_identity,
                           const char *mode, const char *nonce) {
    if (strcmp(mode, "stalled") == 0) {
        struct timespec delay = {.tv_sec = 3, .tv_nsec = 0};
        nanosleep(&delay, NULL);
    }
    struct observation observation;
    if (strcmp(mode, "denied") == 0) {
        observation.confirmed = false;
        strcpy(observation.reason, "observer-denied");
    } else {
        observation = observe_group_once(pgid, sid, leader_pid, start_identity);
    }
    char payload[NFS_CONTROL_MAX * 2U];
    int size = snprintf(payload, sizeof(payload),
                        "HELLO 1 %u %s Q %ld %s %llu\n"
                        "OBSERVED 2 %llu %u %s %s\n",
                        NFS_PROTOCOL_VERSION, nonce, (long)getpid(),
                        selected_clock_name(), (unsigned long long)now_ns(),
                        (unsigned long long)request_id, target_generation,
                        observation.confirmed ? "confirmed" : "unconfirmed",
                        observation.reason);
    if (size <= 0 || (size_t)size >= sizeof(payload)) return 1;
    if (strcmp(mode, "incomplete") == 0) {
        char *newline = strchr(payload, '\n');
        return newline != NULL &&
               write_all(result_fd, payload, (size_t)(newline - payload) + 1U) ? 0 : 1;
    }
    if (strcmp(mode, "fragmented") == 0) {
        for (int i = 0; i < size; ++i) {
            if (!write_all(result_fd, payload + i, 1)) return 1;
            struct timespec delay = {.tv_sec = 0, .tv_nsec = 500 * 1000};
            nanosleep(&delay, NULL);
        }
        return 0;
    }
    return write_all(result_fd, payload, (size_t)size) ? 0 : 1;
}

static struct observation observe_group_worker(
    const char *binary_path, pid_t pgid, pid_t sid, pid_t leader_pid,
    const char *start_identity, uint32_t target_generation,
    uint64_t request_id, uint64_t deadline, int signal_fd, int diagnostics_fd,
    const char *mode, pid_t guard_pgid, pid_t supervisor_sid,
    const int close_fds[], size_t close_fd_count) {
    struct observation unavailable = {.confirmed = false, .reason = "observer-failed"};
    if (!retained_child_running(guard_pgid) ||
        now_ns() >= signal_clipped_due(deadline, NFS_CANCEL_OBSERVE_END_NS))
        return unavailable;
    uint64_t observe_due = reserve_before(deadline,
                                          UINT64_C(150) * NS_PER_MILLISECOND);
    int control[2] = {-1, -1}, lifetime[2] = {-1, -1};
    int result_pipe[2] = {-1, -1};
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, control) != 0 ||
        pipe(lifetime) != 0 || pipe(result_pipe) != 0) {
        if (control[0] >= 0) close(control[0]);
        if (control[1] >= 0) close(control[1]);
        if (lifetime[0] >= 0) close(lifetime[0]);
        if (lifetime[1] >= 0) close(lifetime[1]);
        if (result_pipe[0] >= 0) close(result_pipe[0]);
        if (result_pipe[1] >= 0) close(result_pipe[1]);
        return unavailable;
    }
    if (!set_fd_flags(control[0], false) || !set_fd_flags(control[1], false) ||
        !set_fd_flags(lifetime[0], false) || !set_fd_flags(lifetime[1], false) ||
        !set_fd_flags(result_pipe[0], true) || !set_fd_flags(result_pipe[1], false)) {
        close(control[0]); close(control[1]); close(lifetime[0]); close(lifetime[1]);
        close(result_pipe[0]); close(result_pipe[1]);
        return unavailable;
    }
    char q_nonce[33];
    snprintf(q_nonce, sizeof(q_nonce), "%016llx%016llx",
             (unsigned long long)((uint64_t)getpid() ^ request_id),
             (unsigned long long)now_ns());
    char result_fd_text[32], request_text[32], generation_text[32];
    char pgid_text[32], sid_text[32], leader_text[32];
    snprintf(result_fd_text, sizeof(result_fd_text), "4");
    snprintf(request_text, sizeof(request_text), "%llu",
             (unsigned long long)request_id);
    snprintf(generation_text, sizeof(generation_text), "%u", target_generation);
    snprintf(pgid_text, sizeof(pgid_text), "%ld", (long)pgid);
    snprintf(sid_text, sizeof(sid_text), "%ld", (long)sid);
    snprintf(leader_text, sizeof(leader_text), "%ld", (long)leader_pid);
    char *observer_argv[] = {
        (char *)binary_path, "--observer-worker", result_fd_text, request_text,
        generation_text, pgid_text, sid_text, leader_text, (char *)start_identity,
        (char *)mode, q_nonce, NULL,
    };

    sigset_t blocked, previous;
    sigemptyset(&blocked);
    sigaddset(&blocked, SIGINT);
    sigaddset(&blocked, SIGTERM);
    if (sigprocmask(SIG_BLOCK, &blocked, &previous) != 0) {
        close(control[0]); close(control[1]); close(lifetime[0]); close(lifetime[1]);
        close(result_pipe[0]); close(result_pipe[1]);
        return unavailable;
    }
    if (request_id > (uint64_t)(NFS_GROUP_MAX - target_generation)) {
        sigprocmask(SIG_SETMASK, &previous, NULL);
        close(control[0]); close(control[1]); close(lifetime[0]); close(lifetime[1]);
        close(result_pipe[0]); close(result_pipe[1]);
        return unavailable;
    }
    uint32_t guardian_generation = target_generation + (uint32_t)request_id;
    if (!reserve_generation(guardian_generation)) {
        sigprocmask(SIG_SETMASK, &previous, NULL);
        close(control[0]); close(control[1]); close(lifetime[0]); close(lifetime[1]);
        close(result_pipe[0]); close(result_pipe[1]);
        return unavailable;
    }
    pid_t guardian_pid = fork();
    if (guardian_pid == 0) {
        close(control[0]);
        close(lifetime[1]);
        close(result_pipe[0]);
        for (size_t i = 0; i < close_fd_count; ++i)
            if (close_fds[i] >= 0 && close_fds[i] != result_pipe[1] &&
                close_fds[i] != control[1] && close_fds[i] != lifetime[0])
                close(close_fds[i]);
        if (!install_devnull_standard_fds(false, false)) _exit(1);
        int child_control = control[1];
        int child_lifetime = lifetime[0];
        int child_workload = result_pipe[1];
        int no_ready = -1, no_pause_ready = -1, no_pause_resume = -1;
        if (!prepare_guardian_descriptors(&child_control, &child_lifetime,
                                          &child_workload, &no_ready,
                                          &no_pause_ready, &no_pause_resume))
            _exit(1);
        int status = guardian_main(child_control, child_lifetime, -1,
                                   child_workload,
                                   guardian_generation, q_nonce, guard_pgid,
                                   supervisor_sid, "Q", true, observer_argv,
                                   NULL, observe_due);
        _exit(status);
    }
    sigprocmask(SIG_SETMASK, &previous, NULL);
    if (guardian_pid < 0) {
        close(control[0]); close(control[1]); close(lifetime[0]); close(lifetime[1]);
        close(result_pipe[0]); close(result_pipe[1]);
        return unavailable;
    }
    close(control[1]);
    close(lifetime[0]);
    close(result_pipe[1]);

    char hello[NFS_CONTROL_STORAGE], ready[NFS_CONTROL_STORAGE];
    char ready_copy[NFS_CONTROL_STORAGE];
    uint32_t guardian_sequence = 0;
    pid_t observer_pgid = 0;
    pid_t held_pid = 0;
    bool guardian_reaped = false;
    if (read_line_supervisor(control[0], signal_fd, hello, sizeof(hello), observe_due) != 1 ||
        !validate_control_line(hello, 'G', &guardian_sequence, q_nonce, true) ||
        read_line_supervisor(control[0], signal_fd, ready, sizeof(ready), observe_due) != 1) {
        emit_event(diagnostics_fd, "OBSERVER_STATE %llu registration-read\n",
                   (unsigned long long)request_id);
        strcpy(unavailable.reason, "observer-registration");
        goto observer_retire;
    }
    strcpy(ready_copy, ready);
    if (!validate_control_line(ready, 'G', &guardian_sequence, q_nonce, true)) {
        emit_event(diagnostics_fd, "OBSERVER_STATE %llu registration-wire\n",
                   (unsigned long long)request_id);
        strcpy(unavailable.reason, "observer-registration");
        goto observer_retire;
    }
    char *ready_fields[10];
    size_t ready_count = split_fields(ready_copy, ready_fields, 10);
    long parsed_generation, parsed_leader, parsed_pgid, parsed_guard, parsed_sid;
    if (ready_count != 9 || strcmp(ready_fields[0], "GROUP_READY") != 0 ||
        !parse_long(ready_fields[2], &parsed_generation) ||
        parsed_generation != (long)guardian_generation ||
        !parse_long(ready_fields[3], &parsed_leader) || parsed_leader != guardian_pid ||
        !parse_long(ready_fields[4], &parsed_pgid) || parsed_pgid != guardian_pid ||
        !parse_long(ready_fields[5], &parsed_guard) || parsed_guard != guard_pgid ||
        !parse_long(ready_fields[6], &parsed_sid) || parsed_sid != supervisor_sid ||
        !parse_positive_pid(ready_fields[8], &held_pid) ||
        !retained_child_running(guard_pgid) ||
        !retained_child_running(guardian_pid) ||
        getpgid(guardian_pid) != guard_pgid ||
        getpgid(held_pid) != guardian_pid || getsid(held_pid) != supervisor_sid)
    {
        emit_event(diagnostics_fd, "OBSERVER_STATE %llu registration-identity\n",
                   (unsigned long long)request_id);
        goto observer_retire;
    }
    observer_pgid = (pid_t)parsed_pgid;
    if (now_ns() >= signal_clipped_due(observe_due, NFS_CANCEL_OBSERVE_END_NS))
        goto observer_retire;
    if (!write_line(control[0], "HELLO_OK 1 %u %s %s %llu\n",
                    NFS_PROTOCOL_VERSION, q_nonce, selected_clock_name(),
                    (unsigned long long)now_ns()) ||
        !write_line(control[0], "GROUP_ACK 2 %u\n", guardian_generation) ||
        !write_line(control[0], "RELEASE 3 %u Q observe\n", guardian_generation))
        goto observer_retire;
    emit_event(diagnostics_fd, "OBSERVER_STATE %llu released\n",
               (unsigned long long)request_id);

    struct observer_receive receive;
    memset(&receive, 0, sizeof(receive));
    bool workload_reaped = false, quiesce_sent = false;
    uint32_t workload_exit_sequence = 0;
    bool result_open = true;
    pid_t observer_pid = 0;
    uint64_t effective_deadline = observe_due;
    while (now_ns() < effective_deadline) {
        int accepted = atomic_load_explicit(&accepted_signal, memory_order_relaxed);
        if (accepted != 0) {
            uint64_t cancellation_end = (uint64_t)atomic_load_explicit(
                &accepted_ns, memory_order_relaxed) + NFS_CANCEL_OBSERVE_END_NS;
            if (cancellation_end < effective_deadline)
                effective_deadline = cancellation_end;
        }
        struct pollfd pollfds[3] = {
            {.fd = signal_fd, .events = POLLIN},
            {.fd = control[0], .events = POLLIN | POLLHUP},
            {.fd = result_open ? result_pipe[0] : -1, .events = POLLIN | POLLHUP},
        };
        int timeout = remaining_ms(effective_deadline);
        if (timeout > 20) timeout = 20;
        int polled = poll(pollfds, 3, timeout);
        if (polled < 0 && errno != EINTR) break;
        effective_deadline = signal_clipped_due(effective_deadline,
                                                NFS_CANCEL_OBSERVE_END_NS);
        if (now_ns() >= effective_deadline) break;
        if (pollfds[0].revents & POLLIN) {
            uint8_t bytes[32];
            while (read(signal_fd, bytes, sizeof(bytes)) > 0) {}
        }
        if (pollfds[2].revents & POLLIN) {
            int receive_status = observer_receive_bytes(
                &receive, result_pipe[0], q_nonce, request_id, target_generation);
            if (receive_status < 0) break;
            if (receive_status == 0) {
                close(result_pipe[0]);
                result_pipe[0] = -1;
                result_open = false;
            }
        } else if (pollfds[2].revents & POLLHUP) {
            close(result_pipe[0]);
            result_pipe[0] = -1;
            result_open = false;
        }
        if (pollfds[1].revents & POLLIN) {
            char line[NFS_CONTROL_STORAGE], original[NFS_CONTROL_STORAGE];
            if (read_line_supervisor(control[0], signal_fd, line, sizeof(line),
                                     effective_deadline) != 1)
                break;
            strcpy(original, line);
            if (!validate_control_line(line, 'G', &guardian_sequence, q_nonce, true))
                break;
            char *fields[8];
            size_t count = split_fields(original, fields, 8);
            if (count == 4 && strcmp(fields[0], "WORKLOAD_STARTED") == 0) {
                uint64_t incoming_generation;
                if (!parse_positive_pid(fields[3], &observer_pid) ||
                    observer_pid != held_pid ||
                    !parse_u64(fields[2], &incoming_generation) ||
                    incoming_generation != guardian_generation) break;
                emit_event(diagnostics_fd, "OBSERVER_STATE %llu started\n",
                           (unsigned long long)request_id);
            } else if (count == 6 && strcmp(fields[0], "WORKLOAD_EXIT") == 0) {
                uint64_t incoming_generation;
                if (observer_pid != held_pid ||
                    !parse_u64(fields[2], &incoming_generation) ||
                    incoming_generation != guardian_generation) break;
                workload_reaped = true;
                workload_exit_sequence = guardian_sequence;
                emit_event(diagnostics_fd, "OBSERVER_STATE %llu workload-reaped\n",
                           (unsigned long long)request_id);
                if (!quiesce_sent) {
                    uint64_t hard_due = deadline;
                    uint64_t kill_due = now_ns();
                    if (!write_line(control[0], "QUIESCE 4 %u %llu %llu\n",
                                    guardian_generation,
                                    (unsigned long long)kill_due,
                                    (unsigned long long)hard_due))
                        break;
                    quiesce_sent = true;
                    emit_event(diagnostics_fd, "OBSERVER_STATE %llu quiesce\n",
                               (unsigned long long)request_id);
                }
            } else {
                break;
            }
        }
        if (workload_reaped && receive.observed && receive.hello &&
            observer_pid == receive.reported_pid) {
            break;
        }
    }
    if (workload_reaped && receive.observed && receive.hello &&
        observer_pid == receive.reported_pid &&
        now_ns() < signal_clipped_due(effective_deadline, NFS_CANCEL_OBSERVE_END_NS)) {
        unavailable = receive.result;
        emit_event(diagnostics_fd, "OBSERVER_REAPED %llu %u\n",
                   (unsigned long long)request_id, target_generation);
        if (write_line(control[0], "EXIT_PERMIT 5 %u reaped-fixed %u\n",
                       guardian_generation, workload_exit_sequence)) {
            int status = 0;
            uint64_t reap_due = signal_clipped_due(
                reserve_before(deadline, UINT64_C(50) * NS_PER_MILLISECOND),
                NFS_CANCEL_OBSERVE_END_NS);
            guardian_reaped = reap_child_until(guardian_pid, reap_due, &status);
        }
    } else {
        emit_event(diagnostics_fd,
                   "OBSERVER_STATE %llu incomplete-%d-%d-%ld-%ld\n",
                   (unsigned long long)request_id, receive.hello,
                   receive.observed, (long)observer_pid,
                   (long)receive.reported_pid);
        strcpy(unavailable.reason, "observer-timeout");
    }

observer_retire:
    if (result_pipe[0] >= 0) close(result_pipe[0]);
    close(control[0]);
    close(lifetime[1]);
    if (!guardian_reaped) {
        (void)retire_unconfirmed_child(guardian_pid, guardian_pid,
            observer_pgid > 0, guardian_generation, "Q", deadline, diagnostics_fd);
        if (unavailable.confirmed) {
            unavailable.confirmed = false;
            strcpy(unavailable.reason, "observer-retirement-unconfirmed");
        }
    }
    return unavailable;
}

static bool guardian_read_command(int fd, const char *expected,
                                  const char *nonce, uint32_t *last_sequence,
                                  uint64_t deadline);

static int diagnostic_writer(int read_fd, int event_fd, int control_fd,
                             const char *nonce, int test_ready_fd) {
    if (!write_line(control_fd, "HELLO 1 %u %s W %ld %s %llu\n",
                    NFS_PROTOCOL_VERSION, nonce, (long)getpid(),
                    selected_clock_name(), (unsigned long long)now_ns()))
        return 1;
    uint32_t supervisor_sequence = 0;
    if (!guardian_read_command(control_fd, "HELLO_OK", nonce,
                               &supervisor_sequence,
                               now_ns() + NFS_GUARDIAN_REGISTRATION_NS))
        return 1;
    char buffer[4096];
    bool drain_requested = false;
    for (;;) {
        struct pollfd items[2] = {
            {.fd = read_fd, .events = POLLIN | POLLHUP},
            {.fd = control_fd, .events = POLLIN | POLLHUP},
        };
        int polled = poll(items, 2, -1);
        if (polled < 0) {
            if (errno == EINTR) continue;
            return 1;
        }
        if (items[1].revents & POLLIN) {
            char line[NFS_CONTROL_STORAGE], copy[NFS_CONTROL_STORAGE];
            if (read_line_deadline(control_fd, line, sizeof(line),
                                   now_ns() + NFS_WRITER_DRAIN_NS) != 1)
                return 1;
            strcpy(copy, line);
            if (!validate_control_line(line, 'S', &supervisor_sequence, nonce, false))
                return 1;
            char *fields[5];
            size_t count = split_fields(copy, fields, 5);
            if (count != 3 || strcmp(fields[0], "DRAIN") != 0) return 1;
            drain_requested = true;
        }
        if (!(items[0].revents & (POLLIN | POLLHUP))) continue;
        ssize_t count = read(read_fd, buffer, sizeof(buffer));
        if (count == 0) {
            const char *state = drain_requested ? "persisted" : "partial";
            (void)write_line(control_fd, "DRAINED 2 %s\n", state);
            break;
        }
        if (count < 0) {
            if (errno == EINTR) continue;
            return 1;
        }
        if (test_ready_fd >= 0) {
            /* The diagnostic bytes have actually been received. For a full
             * pipe, the next syscall is the blocked atomic output write. */
            (void)write_line(test_ready_fd, "%ld %ld %ld\n", (long)getpid(),
                             (long)getppid(), (long)getpgrp());
            close(test_ready_fd);
            test_ready_fd = -1;
        }
        if (!write_all(event_fd, buffer, (size_t)count)) {
            (void)write_line(control_fd, "DRAINED 2 unavailable\n");
            return 1;
        }
    }
    return 0;
}

static void emit_event(int fd, const char *format, ...) {
    if (fd < 0) return;
    char buffer[NFS_CONTROL_STORAGE];
    va_list args;
    va_start(args, format);
    int size = vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    if (size <= 0 || (size_t)size > NFS_CONTROL_MAX) return;
    if (diagnostic_drops != 0) {
        char loss[NFS_CONTROL_STORAGE];
        int loss_size = snprintf(loss, sizeof(loss), "DIAG_LOSS %u\n",
                                 diagnostic_drops);
        if (loss_size > 0 && (size_t)loss_size <= NFS_CONTROL_MAX &&
            write(fd, loss, (size_t)loss_size) == loss_size)
            diagnostic_drops = 0;
    }
    if (write(fd, buffer, (size_t)size) != size && diagnostic_drops != UINT_MAX)
        ++diagnostic_drops;
}

static bool guardian_read_command(int fd, const char *expected,
                                  const char *nonce, uint32_t *last_sequence,
                                  uint64_t deadline) {
    char line[NFS_CONTROL_STORAGE], original[NFS_CONTROL_STORAGE];
    int status = read_line_deadline(fd, line, sizeof(line), deadline);
    if (status != 1) return false;
    strcpy(original, line);
    if (!validate_control_line(line, 'S', last_sequence, nonce, false)) return false;
    char *fields[8];
    size_t count = split_fields(original, fields, 8);
    return count >= 2 && strcmp(fields[0], expected) == 0;
}

static bool guardian_read_registration_command(
    int fd, const char *expected, const char *nonce, uint32_t *last_sequence,
    uint64_t deadline, uint32_t generation, const char *role) {
    char line[NFS_CONTROL_STORAGE], original[NFS_CONTROL_STORAGE];
    if (read_line_deadline(fd, line, sizeof(line), deadline) != 1) return false;
    strcpy(original, line);
    if (!validate_control_line(line, 'S', last_sequence, nonce, false)) return false;
    char *fields[8];
    size_t count = split_fields(original, fields, 8);
    if (count < 2 || strcmp(fields[0], expected) != 0) return false;
    if (strcmp(expected, "HELLO_OK") == 0) return count == 6;
    uint64_t incoming_generation;
    if (!parse_u64(fields[2], &incoming_generation) ||
        incoming_generation != generation)
        return false;
    if (strcmp(expected, "GROUP_ACK") == 0) return count == 3;
    return strcmp(expected, "RELEASE") == 0 && count == 5 &&
           strcmp(fields[3], role) == 0;
}

static _Noreturn void guardian_bounded_exit(
    pid_t payload_pgid, pid_t workload_pid, int gate_fd,
    uint64_t supplied_kill_due, uint64_t supplied_hard_due,
    bool fixed_reaped, struct guardian_observer_slot *observer) {
    if (gate_fd >= 0) close(gate_fd);
    uint64_t loss = now_ns();
    uint64_t hard_due = loss + NFS_CANCEL_HARD_CUTOFF_NS;
    if (supplied_hard_due != 0 && supplied_hard_due < hard_due)
        hard_due = supplied_hard_due;
    if (fixed_reaped) _exit(0);
    uint64_t kill_due = loss + NFS_CANCEL_KILL_NATIVE_NS;
    if (supplied_kill_due != 0 && supplied_kill_due < kill_due)
        kill_due = supplied_kill_due;
    uint64_t final_due = hard_due > UINT64_C(50) * NS_PER_MILLISECOND ?
        hard_due - UINT64_C(50) * NS_PER_MILLISECOND : hard_due;
    if (kill_due > final_due) kill_due = final_due;
    uint64_t observation_due = reserve_before(hard_due,
                                              UINT64_C(150) * NS_PER_MILLISECOND);
    if (loss < kill_due) (void)kill(-payload_pgid, SIGTERM);
    if (observer != NULL && loss < observation_due)
        atomic_store_explicit(&observer->request, 1, memory_order_release);
    uint64_t next_repeat = kill_due;
    while (now_ns() < final_due) {
        uint64_t now = now_ns();
        if (observer != NULL && now < observation_due &&
            atomic_exchange_explicit(&observer->ready, 0,
                                     memory_order_acq_rel)) {
            if (observer->result.confirmed) _exit(0);
            atomic_store_explicit(&observer->request, 1, memory_order_release);
        }
        if (observer != NULL && now >= observation_due)
            atomic_store_explicit(&observer->stop, 1, memory_order_release);
        if (now >= next_repeat) {
            (void)kill(-payload_pgid, SIGKILL);
            next_repeat += UINT64_C(50) * NS_PER_MILLISECOND;
            if (next_repeat < now) next_repeat = now + UINT64_C(50) * NS_PER_MILLISECOND;
        }
        if (workload_pid > 0) {
            int status = 0;
            (void)waitpid(workload_pid, &status, WNOHANG);
        }
        struct timespec delay = {.tv_sec = 0, .tv_nsec = 5 * 1000 * 1000};
        nanosleep(&delay, NULL);
    }
    (void)kill(-payload_pgid, SIGKILL);
    _exit(1);
}

static void terminate_registered_group(pid_t pgid, pid_t guardian_pid,
                                       int lifetime_fd, uint64_t started,
                                       uint64_t hard_due, uint32_t generation,
                                       int diagnostics_fd) {
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    bool pinned = guardian_pid > 0 &&
        waitid(P_PID, (id_t)guardian_pid, &info, WEXITED | WNOHANG | WNOWAIT) == 0;
    if (pgid > 0 && pinned) {
        kill(-pgid, SIGTERM);
        uint64_t kill_due = earlier_due(started + NFS_CANCEL_KILL_NATIVE_NS,
            reserve_before(hard_due, UINT64_C(150) * NS_PER_MILLISECOND));
        while (now_ns() < signal_clipped_due(kill_due, NFS_CANCEL_KILL_NATIVE_NS)) {
            struct timespec delay = {.tv_sec = 0, .tv_nsec = 5 * 1000 * 1000};
            nanosleep(&delay, NULL);
        }
    }
    close(lifetime_fd);
    (void)retire_unconfirmed_child(guardian_pid, pgid > 0 ? pgid : guardian_pid,
                                   pgid > 0, generation, "failure", hard_due,
                                   diagnostics_fd);
}

static int guardian_main(int control_fd, int lifetime_fd, int diagnostics_fd,
                         int workload_only_fd,
                         uint32_t generation, const char *nonce,
                         pid_t guard_pgid, pid_t session_id,
                         const char *role, bool source_fixed_nonforking,
                         char *const workload_argv[], struct phase_pause *pause,
                         uint64_t bootstrap_due) {
    if (diagnostics_fd >= 0) close(diagnostics_fd);
    int ready_fd = -1;
    const char *ready_name = strcmp(role, "verifier") == 0 ?
        "NFS_VERIFIER_READY_FD" : (strcmp(role, "W") == 0 ? "NFS_WRITER_READY_FD" : NULL);
    if (fixture_test_mode && ready_name != NULL) {
        const char *ready_text = getenv(ready_name);
        long parsed_ready;
        if (ready_text != NULL) {
            if (!parse_long(ready_text, &parsed_ready) || parsed_ready < 0 ||
                parsed_ready > INT_MAX)
                return 1;
            ready_fd = (int)parsed_ready;
        }
    }
    if (!guardian_descriptor_allowlist(control_fd, lifetime_fd,
                                       workload_only_fd, ready_fd,
                                       pause != NULL ? pause->ready_fd : -1,
                                       pause != NULL ? pause->resume_fd : -1))
        return 1;
    struct sigaction ignore;
    memset(&ignore, 0, sizeof(ignore));
    ignore.sa_handler = SIG_IGN;
    sigemptyset(&ignore.sa_mask);
    sigaction(SIGINT, &ignore, NULL);
    sigaction(SIGTERM, &ignore, NULL);
    if (!pause_at_phase(pause, "before-group") || setpgid(0, 0) != 0 ||
        getpgrp() != getpid() || getsid(0) != session_id)
        return 1;
    pid_t leader = getpid();
    char identity[64];
    if (!process_start_identity(leader, identity, sizeof(identity))) return 1;
    if (!pause_at_phase(pause, "group-formed")) return 1;

    int gate[2] = {-1, -1};
    if (pipe(gate) != 0 || !set_fd_flags(gate[0], false) ||
        !set_fd_flags(gate[1], false))
        return 1;
    default_unblocked_signal(SIGHUP);
    default_unblocked_signal(SIGCONT);
    pid_t workload_pid = fork();
    if (workload_pid < 0) {
        close(gate[0]);
        close(gate[1]);
        return 1;
    }
    if (workload_pid == 0) {
        close(gate[1]);
        int held_gate_fd = fcntl(gate[0], F_DUPFD_CLOEXEC, 6);
        int held_workload_fd = workload_only_fd >= 0 ?
            fcntl(workload_only_fd, F_DUPFD_CLOEXEC, 6) : -1;
        if (workload_only_fd >= 0) {
            if (held_workload_fd < 0) _exit(127);
        } else {
            close(4);
        }
        const char *ready_text = fixture_test_mode && ready_name != NULL ?
            getenv(ready_name) : NULL;
        int held_ready_fd = -1;
        if (ready_text != NULL) {
            long ready_fd;
            if (!parse_long(ready_text, &ready_fd) || ready_fd < 0 ||
                ready_fd > INT_MAX)
                _exit(127);
            held_ready_fd = fcntl((int)ready_fd, F_DUPFD_CLOEXEC, 6);
            if (held_ready_fd < 0) _exit(127);
        }
        if (held_gate_fd < 0 || dup2(held_gate_fd, 3) < 0 ||
            (held_workload_fd >= 0 && dup2(held_workload_fd, 4) < 0) ||
            (held_ready_fd >= 0 && dup2(held_ready_fd, 5) < 0))
            _exit(127);
        if (ready_text != NULL) {
            if (setenv(ready_name, "5", 1) != 0) _exit(127);
        } else {
            close(5);
        }
        if (!close_from_fd(6)) _exit(127);
        char release = 0;
        bool released = read_exact(3, &release, 1) && release == 'R';
        close(3);
        if (!released) _exit(126);
        reset_child_signal_state();
        default_unblocked_signal(SIGHUP);
        default_unblocked_signal(SIGCONT);
        default_unblocked_signal(SIGTTOU);
        if (workload_only_fd >= 0) {
            int flags = fcntl(4, F_GETFD);
            if (flags < 0 ||
                fcntl(4, F_SETFD, flags & ~FD_CLOEXEC) < 0)
                _exit(127);
        }
        execvp(workload_argv[0], workload_argv);
        _exit(127);
    }
    close(gate[0]);
    if (!pause_at_phase(pause, "child-held")) {
        close(gate[1]);
        (void)kill(-leader, SIGKILL);
        _exit(1);
    }
    if (workload_only_fd >= 0) {
        close(workload_only_fd);
        workload_only_fd = -1;
    }
    if (ready_fd >= 0) close(ready_fd);
    if (getpgid(workload_pid) != leader || setpgid(0, guard_pgid) != 0 ||
        getpgrp() != guard_pgid || getsid(0) != session_id ||
        getsid(workload_pid) != session_id) {
        close(gate[1]);
        (void)kill(-leader, SIGKILL);
        _exit(1);
    }
    if (!pause_at_phase(pause, "group-migrated")) {
        close(gate[1]);
        (void)kill(-leader, SIGKILL);
        _exit(1);
    }
    if (pause != NULL && pause->name != NULL &&
        strcmp(pause->name, "after-quiesce") != 0 &&
        strcmp(pause->name, "observer-stalled") != 0) {
        close(pause->ready_fd);
        close(pause->resume_fd);
        guardian_bounded_exit(leader, workload_pid, gate[1], 0,
                              bootstrap_due, false, NULL);
    }
    /* The held child already inherited default HUP/CONT. G now protects its loop. */
    ignore_signal(SIGHUP);
    for (int fd = STDIN_FILENO; fd <= STDERR_FILENO; ++fd)
        if (fd != control_fd && fd != lifetime_fd && fd != gate[1] &&
            fd != workload_only_fd)
            close(fd);

    struct guardian_observer_slot observer_slot;
    memset(&observer_slot, 0, sizeof(observer_slot));
    observer_slot.test_ready_fd = -1;
    if (fixture_test_mode && pause != NULL && pause->name != NULL &&
        strcmp(pause->name, "observer-stalled") == 0) {
        observer_slot.test_ready_fd = pause->ready_fd;
        close(pause->resume_fd);
        pause->ready_fd = pause->resume_fd = -1;
        pause->name = NULL;
    }
    observer_slot.pgid = leader;
    observer_slot.sid = session_id;
    observer_slot.owner_pid = leader;
    strcpy(observer_slot.owner_identity, identity);
    pthread_t observer_thread;
    if (pthread_create(&observer_thread, NULL, guardian_observer_thread,
                       &observer_slot) != 0) {
        close(gate[1]);
        guardian_bounded_exit(leader, workload_pid, -1, 0,
                              bootstrap_due, false,
                              NULL);
    }
    (void)observer_thread;

    if (!write_line(control_fd, "HELLO 1 %u %s G %ld %s %llu\n",
                    NFS_PROTOCOL_VERSION, nonce, (long)leader,
                    selected_clock_name(), (unsigned long long)now_ns()) ||
        !write_line(control_fd,
                    "GROUP_READY 2 %u %ld %ld %ld %ld %s %ld\n", generation,
                    (long)leader, (long)leader, (long)guard_pgid,
                    (long)session_id, identity, (long)workload_pid))
        guardian_bounded_exit(leader, workload_pid, gate[1], 0,
                              bootstrap_due, false,
                              &observer_slot);
    uint64_t deadline = bootstrap_due;
    uint32_t supervisor_sequence = 0;
    if (!guardian_read_registration_command(
            control_fd, "HELLO_OK", nonce, &supervisor_sequence, deadline,
            generation, role) ||
        !guardian_read_registration_command(
            control_fd, "GROUP_ACK", nonce, &supervisor_sequence, deadline,
            generation, role) ||
        !guardian_read_registration_command(
            control_fd, "RELEASE", nonce, &supervisor_sequence, deadline,
            generation, role))
        guardian_bounded_exit(leader, workload_pid, gate[1], 0, deadline, false,
                              &observer_slot);
    if (!write_all(gate[1], "R", 1))
        guardian_bounded_exit(leader, workload_pid, gate[1], 0, deadline, false,
                              &observer_slot);
    close(gate[1]);
    gate[1] = -1;
    if (!write_line(control_fd, "WORKLOAD_STARTED 3 %u %ld\n", generation,
                    (long)workload_pid)) {
        guardian_bounded_exit(leader, workload_pid, -1, 0, 0, false,
                              &observer_slot);
    }

    int workload_status = 0;
    bool workload_done = false;
    uint32_t workload_exit_sequence = 0;
    bool release_revoked = false;
    uint64_t kill_due = 0, hard_due = 0;
    for (;;) {
        if (hard_due != 0 && now_ns() >= hard_due)
            guardian_bounded_exit(leader, workload_pid, -1, kill_due, hard_due,
                                  source_fixed_nonforking && workload_done,
                                  &observer_slot);
        struct pollfd pollfds[2] = {
            {.fd = lifetime_fd, .events = POLLIN | POLLHUP | POLLERR},
            {.fd = control_fd, .events = POLLIN | POLLHUP | POLLERR},
        };
        int polled = poll(pollfds, 2, 5);
        if (hard_due != 0 && now_ns() >= hard_due)
            guardian_bounded_exit(leader, workload_pid, -1, kill_due, hard_due,
                                  source_fixed_nonforking && workload_done,
                                  &observer_slot);
        if (polled < 0 && errno != EINTR)
            guardian_bounded_exit(leader, workload_pid, -1, kill_due, hard_due,
                                  source_fixed_nonforking && workload_done,
                                  &observer_slot);
        if (pollfds[0].revents & (POLLIN | POLLHUP | POLLERR))
            guardian_bounded_exit(leader, workload_pid, -1, kill_due, hard_due,
                                  source_fixed_nonforking && workload_done,
                                  &observer_slot);
        if (!workload_done) {
            pid_t waited = waitpid(workload_pid, &workload_status, WNOHANG);
            if (waited == workload_pid) {
                workload_done = true;
                const char *kind = WIFEXITED(workload_status) ? "exit" : "signal";
                int value = WIFEXITED(workload_status) ? WEXITSTATUS(workload_status) :
                            (WIFSIGNALED(workload_status) ? WTERMSIG(workload_status) : 0);
                if (!write_line(control_fd, "WORKLOAD_EXIT 4 %u %s %d reaped\n",
                                generation, kind, value))
                    guardian_bounded_exit(leader, workload_pid, -1, kill_due,
                                          hard_due, source_fixed_nonforking,
                                          &observer_slot);
                workload_exit_sequence = 4;
            } else if (waited < 0 && errno != EINTR) {
                guardian_bounded_exit(leader, workload_pid, -1, kill_due,
                                      hard_due, false, &observer_slot);
            }
        }
        if (pollfds[1].revents & (POLLIN | POLLHUP)) {
            char line[NFS_CONTROL_STORAGE], original[NFS_CONTROL_STORAGE];
            int read_status = read_line_deadline(control_fd, line, sizeof(line),
                hard_due != 0 ? hard_due : now_ns() + NFS_GUARDIAN_REGISTRATION_NS);
            if (read_status != 1)
                guardian_bounded_exit(leader, workload_pid, -1, kill_due,
                                      hard_due, source_fixed_nonforking && workload_done,
                                      &observer_slot);
            strcpy(original, line);
            if (!validate_control_line(line, 'S', &supervisor_sequence, nonce, false))
                guardian_bounded_exit(leader, workload_pid, -1, kill_due,
                                      hard_due, source_fixed_nonforking && workload_done,
                                      &observer_slot);
            char *fields[10];
            size_t count = split_fields(original, fields, 8);
            if (count == 5 && strcmp(fields[0], "QUIESCE") == 0) {
                uint64_t parsed_generation, parsed_kill, parsed_hard;
                if (!parse_u64(fields[2], &parsed_generation) ||
                    parsed_generation != generation ||
                    !parse_u64(fields[3], &parsed_kill) ||
                    !parse_u64(fields[4], &parsed_hard) || parsed_kill > parsed_hard)
                    guardian_bounded_exit(leader, workload_pid, -1, kill_due,
                                          hard_due, false, &observer_slot);
                release_revoked = true;
                kill_due = kill_due == 0 ? parsed_kill : earlier_due(kill_due, parsed_kill);
                hard_due = hard_due == 0 ? parsed_hard : earlier_due(hard_due, parsed_hard);
                atomic_store_explicit(&observer_slot.request, 1, memory_order_release);
                if (fixture_test_mode && pause != NULL && pause->name != NULL &&
                    strcmp(pause->name, "after-quiesce") == 0) {
                    (void)write_all(pause->ready_fd, "R", 1);
                    close(pause->ready_fd);
                    close(pause->resume_fd);
                    pause->ready_fd = pause->resume_fd = -1;
                    pause->name = NULL;
                }
                continue;
            }
            if (count == 5 && strcmp(fields[0], "EXIT_PERMIT") == 0) {
                uint64_t parsed_generation, proof_ref;
                if (!parse_u64(fields[2], &parsed_generation) ||
                    !parse_u64(fields[4], &proof_ref) || proof_ref == 0 ||
                    !valid_exit_permit(generation, role, release_revoked,
                                       workload_done,
                                       workload_exit_sequence,
                                       parsed_generation, fields[3], proof_ref) ||
                    (strcmp(fields[3], "reaped-fixed") == 0 &&
                     !source_fixed_nonforking))
                    guardian_bounded_exit(leader, workload_pid, -1, kill_due,
                                          hard_due, false, &observer_slot);
                (void)write_line(control_fd, "GUARD_EXITING 5 %u %s %llu\n",
                                 generation, fields[3],
                                 (unsigned long long)proof_ref);
                atomic_store_explicit(&observer_slot.stop, 1, memory_order_release);
                _exit(0);
            }
            if (count >= 2 && (strcmp(fields[0], "CANCEL") == 0 ||
                               strcmp(fields[0], "ABORT") == 0)) {
                release_revoked = true;
                continue;
            }
            guardian_bounded_exit(leader, workload_pid, -1, kill_due, hard_due,
                                  false, &observer_slot);
        }
        if (release_revoked && hard_due != 0 && now_ns() >= hard_due)
            guardian_bounded_exit(leader, workload_pid, -1, kill_due, hard_due,
                                  source_fixed_nonforking && workload_done,
                                  &observer_slot);
    }
}

static bool running_executable_path(char *buffer, size_t capacity) {
#if defined(NFS_PLATFORM_DARWIN)
    uint32_t required = (uint32_t)capacity;
    char unresolved[PATH_MAX];
    if (_NSGetExecutablePath(unresolved, &required) != 0 || required > sizeof(unresolved))
        return false;
    char *resolved = realpath(unresolved, NULL);
    if (resolved == NULL) return false;
    size_t length = strlen(resolved);
    bool ok = length + 1U <= capacity;
    if (ok) memcpy(buffer, resolved, length + 1U);
    free(resolved);
    return ok;
#elif defined(NFS_PLATFORM_LINUX)
    if (capacity < 2U) return false;
    ssize_t length = readlink("/proc/self/exe", buffer, capacity - 1U);
    if (length <= 0 || (size_t)length >= capacity - 1U) return false;
    buffer[length] = '\0';
    return buffer[0] == '/';
#else
    (void)buffer;
    (void)capacity;
    return false;
#endif
}

static bool verify_provenance(const char *binary_path) {
    const char *source = getenv("NFS_SOURCE_PATH");
    const char *expected_binary = getenv("NFS_EXPECTED_BINARY_SHA256");
    const char *expected_source = getenv("NFS_EXPECTED_SOURCE_SHA256");
    const char *bash = getenv("NFS_REAL_BASH");
    const char *expected_bash = getenv("NFS_EXPECTED_BASH_SHA256");
    const char *version = getenv("NFS_PROTOCOL_VERSION");
    if (source == NULL || source[0] != '/' || bash == NULL || bash[0] != '/' ||
        expected_binary == NULL || expected_source == NULL || expected_bash == NULL ||
        !is_lower_hex(expected_binary, 64) || !is_lower_hex(expected_source, 64) ||
        !is_lower_hex(expected_bash, 64) || version == NULL ||
        strcmp(version, "33") != 0)
        return false;
    char executable[PATH_MAX], actual[65];
    (void)binary_path;
    return running_executable_path(executable, sizeof(executable)) &&
           sha256_path(executable, actual) && strcmp(actual, expected_binary) == 0 &&
           sha256_path(source, actual) && strcmp(actual, expected_source) == 0 &&
           sha256_path(bash, actual) && strcmp(actual, expected_bash) == 0;
}

struct fixed_guardian_handle {
    pid_t pid;
    pid_t pgid;
    pid_t held_pid;
    int control_fd;
    int lifetime_write;
    uint32_t generation;
    uint32_t receive_sequence;
    bool workload_started;
    uint32_t workload_exit_sequence;
    char nonce[33];
};

static bool start_fixed_guardian(
    struct fixed_guardian_handle *handle, const char *binary_path,
    const struct anchor_handle *anchor, uint32_t generation, const char *role,
    const char *launch_ref, bool release_after_cancel, int workload_only_fd,
    int child_stdin_fd, int child_stdout_fd, int diagnostics_fd,
    int signal_read_fd,
    char *const workload_argv[], uint64_t deadline) {
    int control[2] = {-1, -1}, lifetime[2] = {-1, -1};
    memset(handle, 0, sizeof(*handle));
    handle->pid = -1;
    handle->control_fd = -1;
    handle->lifetime_write = -1;
    if (now_ns() >= signal_clipped_due(deadline, NFS_CANCEL_OBSERVE_END_NS) ||
        !retained_child_running(anchor->pid) || !reserve_generation(generation))
        return false;
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, control) != 0 ||
        pipe(lifetime) != 0 || !set_fd_flags(control[0], false) ||
        !set_fd_flags(control[1], false) || !set_fd_flags(lifetime[0], false) ||
        !set_fd_flags(lifetime[1], false))
        goto fail;
    char nonce[33];
    snprintf(nonce, sizeof(nonce), "%016llx%016llx",
             (unsigned long long)((uint64_t)getpid() ^ generation),
             (unsigned long long)now_ns());
    sigset_t blocked, previous;
    sigemptyset(&blocked);
    sigaddset(&blocked, SIGINT);
    sigaddset(&blocked, SIGTERM);
    if (sigprocmask(SIG_BLOCK, &blocked, &previous) != 0) goto fail;
    pid_t guardian = fork();
    if (guardian == 0) {
        close(control[0]);
        close(lifetime[1]);
        close(anchor->lifetime_write);
        if (signal_read_fd >= 0) close(signal_read_fd);
        if (signal_pipe_write >= 0) close(signal_pipe_write);
        if (setenv("NFS_FIXED_NONCE", nonce, 1) != 0) _exit(1);
        int stdin_copy = child_stdin_fd >= 0 ?
            fcntl(child_stdin_fd, F_DUPFD_CLOEXEC, 10) : -1;
        int stdout_copy = child_stdout_fd >= 0 ?
            fcntl(child_stdout_fd, F_DUPFD_CLOEXEC, 10) : -1;
        if ((child_stdin_fd >= 0 && stdin_copy < 0) ||
            (child_stdout_fd >= 0 && stdout_copy < 0) ||
            (stdin_copy >= 0 && dup2(stdin_copy, STDIN_FILENO) < 0) ||
            (stdout_copy >= 0 && dup2(stdout_copy, STDOUT_FILENO) < 0))
            _exit(1);
        if (stdin_copy >= 0) close(stdin_copy);
        if (stdout_copy >= 0) close(stdout_copy);
        if (!install_devnull_standard_fds(child_stdin_fd >= 0,
                                           child_stdout_fd >= 0))
            _exit(1);
        if (diagnostics_fd >= 0) close(diagnostics_fd);
        int ready_fd = -1;
        const char *ready_name = strcmp(role, "verifier") == 0 ?
            "NFS_VERIFIER_READY_FD" : (strcmp(role, "W") == 0 ? "NFS_WRITER_READY_FD" : NULL);
        const char *ready_text = fixture_test_mode && ready_name != NULL ?
            getenv(ready_name) : NULL;
        if (ready_text != NULL) {
            long parsed_ready;
            if (!parse_long(ready_text, &parsed_ready) || parsed_ready < 0 ||
                parsed_ready > INT_MAX)
                _exit(1);
            ready_fd = (int)parsed_ready;
        }
        int child_control = control[1];
        int child_lifetime = lifetime[0];
        int child_workload = workload_only_fd;
        int no_pause_ready = -1, no_pause_resume = -1;
        if (!prepare_guardian_descriptors(&child_control, &child_lifetime,
                                          &child_workload, &ready_fd,
                                          &no_pause_ready, &no_pause_resume))
            _exit(1);
        if (ready_fd >= 0 && setenv(ready_name, "6", 1) != 0)
            _exit(1);
        int status = guardian_main(child_control, child_lifetime, -1,
                                   child_workload, generation, nonce,
                                   anchor->pgid, anchor->sid, role, true,
                                   workload_argv, NULL, deadline);
        _exit(status);
    }
    (void)sigprocmask(SIG_SETMASK, &previous, NULL);
    if (guardian < 0) goto fail;
    close(control[1]); control[1] = -1;
    close(lifetime[0]); lifetime[0] = -1;
    char hello[NFS_CONTROL_STORAGE], ready[NFS_CONTROL_STORAGE];
    uint32_t sequence = 0;
    if (read_line_supervisor(control[0], signal_read_fd, hello, sizeof(hello), deadline) != 1 ||
        !validate_control_line(hello, 'G', &sequence, nonce, true) ||
        read_line_supervisor(control[0], signal_read_fd, ready, sizeof(ready), deadline) != 1)
        goto retire;
    char copy[NFS_CONTROL_STORAGE];
    strcpy(copy, ready);
    if (!validate_control_line(ready, 'G', &sequence, nonce, true)) goto retire;
    char *fields[10];
    size_t count = split_fields(copy, fields, 10);
    long parsed_generation, parsed_pid, parsed_pgid, parsed_guard, parsed_sid;
    long held_pid;
    if (count != 9 || strcmp(fields[0], "GROUP_READY") != 0 ||
        !parse_long(fields[2], &parsed_generation) ||
        parsed_generation != (long)generation ||
        !parse_long(fields[3], &parsed_pid) || parsed_pid != guardian ||
        !parse_long(fields[4], &parsed_pgid) || parsed_pgid != guardian ||
        !parse_long(fields[5], &parsed_guard) || parsed_guard != anchor->pgid ||
        !parse_long(fields[6], &parsed_sid) || parsed_sid != anchor->sid ||
        !parse_long(fields[8], &held_pid) || held_pid <= 0 ||
        !retained_child_running(anchor->pid) ||
        !retained_child_running(guardian) ||
        getpgid(guardian) != anchor->pgid || getsid(guardian) != anchor->sid ||
        getpgid((pid_t)held_pid) != guardian || getsid((pid_t)held_pid) != anchor->sid)
        goto retire;
    char owner_identity[64];
    if (!process_start_identity(guardian, owner_identity, sizeof(owner_identity)) ||
        strcmp(owner_identity, fields[7]) != 0) goto retire;
    if (!write_line(control[0], "HELLO_OK 1 %u %s %s %llu\n",
                    NFS_PROTOCOL_VERSION, nonce, selected_clock_name(),
                    (unsigned long long)now_ns()) ||
        !write_line(control[0], "GROUP_ACK 2 %u\n", generation))
        goto retire;
    bool released = release_after_cancel ?
        write_line(control[0], "RELEASE 3 %u %s %s\n", generation, role,
                   launch_ref) :
        write_release_with_signal_gate(control[0], generation, role, launch_ref);
    if (!released) goto retire;
    handle->pid = guardian;
    handle->pgid = guardian;
    handle->held_pid = (pid_t)held_pid;
    handle->control_fd = control[0];
    handle->lifetime_write = lifetime[1];
    handle->generation = generation;
    handle->receive_sequence = sequence;
    strcpy(handle->nonce, nonce);
    (void)binary_path;
    return true;
retire:
    close(lifetime[1]); lifetime[1] = -1;
    (void)retire_unconfirmed_child(guardian, guardian, false, generation, role,
                                   deadline, diagnostics_fd);
fail:
    if (control[0] >= 0) close(control[0]);
    if (control[1] >= 0) close(control[1]);
    if (lifetime[0] >= 0) close(lifetime[0]);
    if (lifetime[1] >= 0) close(lifetime[1]);
    return false;
}

/* Receive-side state binds both reports to the registered child and captures
 * the actual wire sequence that can authorize a source-fixed reap proof. */
static bool fixed_workload_report(struct fixed_guardian_handle *handle,
                                   char *line, int *status, bool *reaped) {
    char copy[NFS_CONTROL_STORAGE];
    strcpy(copy, line);
    if (!validate_control_line(line, 'G', &handle->receive_sequence, NULL, true))
        return false;
    char *fields[8];
    size_t count = split_fields(copy, fields, 8);
    uint64_t incoming_generation;
    if (count < 3 || !parse_u64(fields[2], &incoming_generation) ||
        incoming_generation != handle->generation) return false;
    if (count == 4 && strcmp(fields[0], "WORKLOAD_STARTED") == 0) {
        pid_t pid;
        if (handle->workload_started ||
            !parse_positive_pid(fields[3], &pid) || pid != handle->held_pid)
            return false;
        handle->workload_started = true;
        return true;
    }
    if (count == 6 && strcmp(fields[0], "WORKLOAD_EXIT") == 0 &&
        handle->workload_started && handle->workload_exit_sequence == 0) {
        uint64_t value;
        if (!parse_u64(fields[4], &value)) return false;
        *status = strcmp(fields[3], "exit") == 0 ? (int)value : 128 + (int)value;
        handle->workload_exit_sequence = handle->receive_sequence;
        *reaped = true;
        return true;
    }
    return false;
}

static bool finish_fixed_guardian(struct fixed_guardian_handle *handle,
                                  uint64_t kill_due, uint64_t hard_due,
                                  int *workload_status) {
    bool reaped_workload = false;
    uint64_t proof_due = reserve_before(hard_due, UINT64_C(150) * NS_PER_MILLISECOND);
    while (now_ns() < signal_clipped_due(proof_due, NFS_CANCEL_OBSERVE_END_NS) &&
           !reaped_workload) {
        char line[NFS_CONTROL_STORAGE];
        int status = read_line_supervisor(handle->control_fd, signal_pipe_read,
                                          line, sizeof(line), proof_due);
        if (status != 1) break;
        if (!fixed_workload_report(handle, line, workload_status, &reaped_workload))
            break;
    }
    bool signals_retired = reaped_workload;
    if (reaped_workload &&
        write_line(handle->control_fd, "QUIESCE 4 %u %llu %llu\n",
                   handle->generation, (unsigned long long)kill_due,
                   (unsigned long long)hard_due) &&
        write_line(handle->control_fd, "EXIT_PERMIT 5 %u reaped-fixed %u\n",
                   handle->generation, handle->workload_exit_sequence)) {
        int guardian_status = 0;
        uint64_t reap_due = reserve_before(hard_due, UINT64_C(50) * NS_PER_MILLISECOND);
        if (reap_child_until(handle->pid, reap_due, &guardian_status)) {
            close(handle->lifetime_write);
            close(handle->control_fd);
            handle->pid = -1;
            return WIFEXITED(guardian_status) && WEXITSTATUS(guardian_status) == 0;
        }
    }
    close(handle->lifetime_write);
    (void)retire_unconfirmed_child(handle->pid, signals_retired ? 0 : handle->pgid,
                                   true, handle->generation, "fixed", hard_due, -1);
    close(handle->control_fd);
    handle->pid = -1;
    return false;
}

struct diagnostic_outcome {
    bool drain_sent, report_received, payload_reaped, guardian_reaped;
    int payload_status;
    char persistence[16];
};
static volatile struct diagnostic_outcome last_diagnostic_outcome = {
    .payload_status = 1, .persistence = "unavailable",
};

static bool finish_diagnostic_guardian(
    struct fixed_guardian_handle *handle, int writer_control_fd,
    uint32_t *writer_sequence, int diagnostics_fd, int signal_fd,
    uint64_t drain_due, uint64_t hard_due) {
    struct diagnostic_outcome result = {.payload_status = 1, .persistence = "unavailable"};
    drain_due = signal_clipped_due(drain_due, NFS_CANCEL_WRITER_END_NS);
    hard_due = signal_clipped_due(hard_due, NFS_CANCEL_TARGET_EXIT_NS);
    uint64_t now = now_ns();
    if (now < drain_due)
        result.drain_sent = write_line(writer_control_fd, "DRAIN 2 %llu\n",
            (unsigned long long)(drain_due - now));
    close(diagnostics_fd);
    bool writer_open = true;
    while (now_ns() < signal_clipped_due(drain_due, NFS_CANCEL_WRITER_END_NS) &&
           !(result.payload_reaped && (result.report_received || !writer_open))) {
        drain_due = signal_clipped_due(drain_due, NFS_CANCEL_WRITER_END_NS);
        hard_due = signal_clipped_due(hard_due, NFS_CANCEL_TARGET_EXIT_NS);
        struct pollfd items[3] = {
            {.fd = signal_fd, .events = POLLIN},
            {.fd = result.payload_reaped ? -1 : handle->control_fd, .events = POLLIN | POLLHUP},
            {.fd = writer_open && !result.report_received ? writer_control_fd : -1,
             .events = POLLIN | POLLHUP},
        };
        uint64_t next_due = earlier_due(drain_due, hard_due);
        int timeout = remaining_ms(next_due);
        if (timeout > 10) timeout = 10;
        int polled = poll(items, 3, timeout);
        if (polled < 0 && errno != EINTR) break;
        if (now_ns() >= signal_clipped_due(drain_due, NFS_CANCEL_WRITER_END_NS)) break;
        if (items[0].revents & POLLIN) {
            uint8_t bytes[32];
            while (read(signal_fd, bytes, sizeof(bytes)) > 0) {}
        }
        if (items[2].revents & (POLLIN | POLLHUP)) {
            char line[NFS_CONTROL_STORAGE], copy[NFS_CONTROL_STORAGE];
            int received = read_line_supervisor_until(writer_control_fd, signal_fd,
                line, sizeof(line), drain_due, NFS_CANCEL_WRITER_END_NS);
            if (received == -2) {
                writer_open = false;
            } else if (received == 1) {
                strcpy(copy, line);
                if (!validate_control_line(line, 'W', writer_sequence, handle->nonce, true))
                    break;
                char *fields[5];
                size_t count = split_fields(copy, fields, 5);
                if (count != 3 || strcmp(fields[0], "DRAINED") != 0) break;
                result.report_received = true;
                strcpy(result.persistence, fields[2]);
            } else {
                writer_open = false; /* Partial/late receipt is unavailable. */
            }
        }
        if (items[1].revents & (POLLIN | POLLHUP)) {
            char line[NFS_CONTROL_STORAGE];
            if (read_line_supervisor_until(handle->control_fd, signal_fd, line,
                    sizeof(line), drain_due, NFS_CANCEL_WRITER_END_NS) != 1 ||
                !fixed_workload_report(handle, line, &result.payload_status,
                                        &result.payload_reaped))
                break;
        }
    }
    bool signals_retired = result.payload_reaped;
    if (result.payload_reaped && now_ns() < hard_due &&
        write_line(handle->control_fd, "QUIESCE 4 %u %llu %llu\n",
                   handle->generation, (unsigned long long)earlier_due(drain_due, hard_due),
                   (unsigned long long)hard_due) &&
        write_line(handle->control_fd, "EXIT_PERMIT 5 %u reaped-fixed %u\n",
                   handle->generation, handle->workload_exit_sequence)) {
        int guardian_status = 0;
        result.guardian_reaped = reap_child_until(handle->pid, hard_due, &guardian_status);
    }
    if (!result.guardian_reaped)
        result.guardian_reaped = retire_unconfirmed_child(
            handle->pid, signals_retired ? 0 : handle->pgid,
            true, handle->generation, "W", hard_due, -1);
    if (!result.drain_sent || !result.report_received || result.payload_status != 0)
        strcpy(result.persistence, "unavailable");
    last_diagnostic_outcome = result; /* Bounded state, never a late persistence attempt. */
    close(handle->lifetime_write);
    close(handle->control_fd);
    close(writer_control_fd);
    handle->pid = -1;
    return strcmp(result.persistence, "persisted") == 0 && result.guardian_reaped;
}

/* D belongs to the enclosing cleanup, including failure cleanup. Each terminal
 * phase consumes a reserve inside D; changing phases cannot restart shutdown. */
static void finish_supervisor_output(
    struct fixed_guardian_handle *writer, int writer_control,
    uint32_t *writer_sequence, int diagnostics_fd, int signal_fd,
    struct anchor_handle *anchor, uint64_t hard_due) {
    guardian_joins_disabled = true;
    hard_due = signal_clipped_due(hard_due, NFS_CANCEL_HARD_CUTOFF_NS);
    uint64_t drain_due = earlier_due(now_ns() + NFS_WRITER_DRAIN_NS,
        reserve_before(hard_due, UINT64_C(100) * NS_PER_MILLISECOND));
    uint64_t writer_due = reserve_before(hard_due,
                                         UINT64_C(50) * NS_PER_MILLISECOND);
    (void)finish_diagnostic_guardian(writer, writer_control, writer_sequence,
                                     diagnostics_fd, signal_fd, drain_due,
                                     writer_due);
    /* All joins and guardian terminal actions have ended before H retirement. */
    retire_anchor(anchor, writer_due);
}

/*
 * Filesystem provenance is deliberately isolated from S.  The worker is fixed,
 * has no descendants, and is killed/reaped within the already-running bootstrap
 * deadline when hashing or open(2) stalls.
 */
static int verify_provenance_bounded(const char *binary_path, int signal_fd,
    int close_fd, uint64_t deadline, const struct anchor_handle *anchor) {
    (void)binary_path;
    int result_pipe[2];
    if (pipe(result_pipe) != 0)
        return 0;
    if (!set_fd_flags(result_pipe[0], true) ||
        !set_fd_flags(result_pipe[1], false)) {
        close(result_pipe[0]);
        close(result_pipe[1]);
        return 0;
    }
    char executable_path[PATH_MAX];
    if (!running_executable_path(executable_path, sizeof(executable_path))) {
        close(result_pipe[0]);
        close(result_pipe[1]);
        return 0;
    }
    char *verifier_argv[] = {executable_path,
                             fixture_test_mode ? "--test-verify-worker" : "--verify-worker",
                             "4", executable_path, NULL};
    struct fixed_guardian_handle verifier;
    if (!start_fixed_guardian(&verifier, executable_path, anchor, NFS_GROUP_MAX,
                              "verifier", "build-provenance", false,
                              result_pipe[1], -1, -1, close_fd, signal_fd,
                              verifier_argv, deadline)) {
        close(result_pipe[0]);
        close(result_pipe[1]);
        return atomic_load_explicit(&accepted_signal, memory_order_relaxed) != 0 ? -1 : 0;
    }
    close(result_pipe[1]);
    uint8_t result = 0;
    bool received = false;
    while (now_ns() < deadline) {
        if (atomic_load_explicit(&accepted_signal, memory_order_relaxed) != 0) break;
        struct pollfd pollfds[2] = {
            {.fd = signal_fd, .events = POLLIN},
            {.fd = result_pipe[0], .events = POLLIN | POLLHUP},
        };
        int timeout = remaining_ms(deadline);
        if (timeout > 20) timeout = 20;
        int polled = poll(pollfds, 2, timeout);
        if (polled < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (pollfds[0].revents & POLLIN) {
            uint8_t buffer[32];
            while (read(signal_fd, buffer, sizeof(buffer)) > 0) {}
        }
        if (pollfds[1].revents & POLLIN) {
            ssize_t count = read(result_pipe[0], &result, sizeof(result));
            if (count == (ssize_t)sizeof(result)) received = true;
        }
        if (received) break;
        if (pollfds[1].revents & POLLHUP) break;
    }
    close(result_pipe[0]);
    uint64_t reap_due = deadline;
    int signum = atomic_load_explicit(&accepted_signal, memory_order_relaxed);
    if (signum != 0) {
        uint64_t cancellation_due = (uint64_t)atomic_load_explicit(
            &accepted_ns, memory_order_relaxed) + NFS_CANCEL_KILL_WORKERS_NS;
        if (cancellation_due < reap_due) reap_due = cancellation_due;
    }
    if (signum != 0) {
        (void)kill(-verifier.pgid, SIGTERM);
        uint64_t kill_due = (uint64_t)atomic_load_explicit(
            &accepted_ns, memory_order_relaxed) + NFS_CANCEL_KILL_WORKERS_NS;
        while (now_ns() < kill_due) {
            struct timespec delay = {.tv_sec = 0, .tv_nsec = 5 * 1000 * 1000};
            nanosleep(&delay, NULL);
        }
        (void)kill(-verifier.pgid, SIGKILL);
    }
    int verifier_status = 1;
    bool guardian_reaped = finish_fixed_guardian(
        &verifier, reap_due, reap_due, &verifier_status);
    if (signum != 0) return -1;
    return received && result == 1U && guardian_reaped && verifier_status == 0 ? 1 : 0;
}

static bool launcher_recognizes(int argc, char *argv[]) {
    if (argc < 5 || strcmp(argv[1], "-c") != 0) return false;
    const char *script = argv[2];
    if (strstr(script, "<<") != NULL) return false;
    const char *last = script;
    const char *end = script + strlen(script);
    while (end > script && (end[-1] == ' ' || end[-1] == '\t' ||
                            end[-1] == '\r' || end[-1] == '\n'))
        --end;
    bool single = false, quoted = false, escaped = false, comment = false;
    for (const char *cursor = script; cursor < end; ++cursor) {
        char ch = *cursor;
        if (comment) {
            if (ch == '\n') {
                comment = false;
                last = cursor + 1;
            }
            continue;
        }
        if (escaped) {
            escaped = false;
            continue;
        }
        if (ch == '\\' && !single) {
            escaped = true;
            continue;
        }
        if (ch == '\'' && !quoted) {
            single = !single;
            continue;
        }
        if (ch == '"' && !single) {
            quoted = !quoted;
            continue;
        }
        if (!single && !quoted && ch == '#') {
            bool begins_comment = cursor == script || cursor[-1] == '\n' ||
                                  cursor[-1] == ';' || cursor[-1] == ' ' ||
                                  cursor[-1] == '\t';
            if (begins_comment) comment = true;
            continue;
        }
        if (!single && !quoted && (ch == ';' || ch == '\n')) last = cursor + 1;
    }
    if (single || quoted || escaped || comment) return false;
    while (*last == ' ' || *last == '\t' || *last == '\r' || *last == '\n') ++last;
    static const char target[] = "native_fixture_run \"$2\"";
    return (size_t)(end - last) == sizeof(target) - 1 &&
           memcmp(last, target, sizeof(target) - 1) == 0;
}

static int compatibility_launcher(int argc, char *argv[]) {
    const char *real_bash = getenv("NFS_REAL_BASH");
    if (real_bash == NULL || real_bash[0] != '/') return NFS_EXIT_PREREQUISITE;
    if (!launcher_recognizes(argc, argv)) {
        if (!verify_provenance(argv[0])) return NFS_EXIT_PREREQUISITE;
        execv(real_bash, argv);
        return NFS_EXIT_PREREQUISITE;
    }
    if (!inherited_signals_supported()) return NFS_EXIT_PREREQUISITE;
    int signal_pipe[2];
    if (!install_handlers(signal_pipe)) return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    uint64_t bootstrap_due = now_ns() + NFS_BOOTSTRAP_NS;
    char nonce[33];
    snprintf(nonce, sizeof(nonce), "%016llx%016llx",
             (unsigned long long)(uint64_t)getpid(),
             (unsigned long long)now_ns());
    struct anchor_handle anchor;
    if (!start_anchor(&anchor, nonce, now_ns() + NFS_GUARDIAN_REGISTRATION_NS,
                      -1, NULL)) {
        return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    }
    int verified = verify_provenance_bounded(
        argv[0], signal_pipe[0], -1, bootstrap_due, &anchor);
    retire_anchor(&anchor, bootstrap_due);
    return supervisor_exit_status(verified == 1 ? NFS_EXIT_UNAVAILABLE :
                                                  NFS_EXIT_PREREQUISITE);
}

static int supervise_test_workload(const char *binary_path, int event_fd,
                                   int pause_ready_fd, int pause_resume_fd,
                                   int release_ready_fd, int release_resume_fd,
                                   int writer_ready_fd,
                                   int writer_drain_ready_fd,
                                   bool flood_diagnostics,
                                   bool fail_after_workload_start,
                                   const char *observer_mode,
                                   const char *phase_pause_name,
                                   int phase_ready_fd, int phase_resume_fd,
                                   char *const workload_argv[]) {
    if (!inherited_signals_supported()) return NFS_EXIT_PREREQUISITE;
    if (pause_ready_fd >= 0) {
        uint8_t ready = 'R', resume;
        if (!write_all(pause_ready_fd, &ready, 1)) return NFS_EXIT_PREREQUISITE;
        if (!read_exact(pause_resume_fd, &resume, 1)) return NFS_EXIT_PREREQUISITE;
        close(pause_ready_fd);
        close(pause_resume_fd);
    }
    int signal_pipe[2];
    if (!install_handlers(signal_pipe)) return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    uint64_t bootstrap_due = now_ns() + NFS_BOOTSTRAP_NS;
    uint64_t generation_hard_due = 0;
    uint32_t generation = 1;
    char nonce[33];
    snprintf(nonce, sizeof(nonce), "%016llx%016llx",
             (unsigned long long)(uint64_t)getpid(),
             (unsigned long long)now_ns());
    struct anchor_handle anchor;
    struct phase_pause phase_pause = {
        .name = phase_pause_name,
        .ready_fd = phase_ready_fd,
        .resume_fd = phase_resume_fd,
    };
    bool anchor_phase = phase_pause_name != NULL &&
                        strcmp(phase_pause_name, "before-anchor-ready") == 0;
    if (!start_anchor(&anchor, nonce, now_ns() + NFS_GUARDIAN_REGISTRATION_NS,
                      -1, anchor_phase ? &phase_pause : NULL)) {
        return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    }
    if (anchor_phase) {
        close(phase_ready_fd);
        close(phase_resume_fd);
        phase_pause.name = NULL;
        phase_pause.ready_fd = -1;
        phase_pause.resume_fd = -1;
    }
    int verified = verify_provenance_bounded(
        binary_path, signal_pipe[0], event_fd, bootstrap_due,
        &anchor);
    if (verified != 1) {
        retire_anchor(&anchor, bootstrap_due);
        return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    }
    int signum = atomic_load_explicit(&accepted_signal, memory_order_relaxed);
    if (signum != 0) {
        retire_anchor(&anchor, bootstrap_due);
        return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    }

    int diagnostics[2];
    if (pipe(diagnostics) != 0) {
        retire_anchor(&anchor, bootstrap_due);
        return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    }
    if (!set_fd_flags(diagnostics[1], true)) {
        close(diagnostics[0]);
        close(diagnostics[1]);
        close(event_fd);
        retire_anchor(&anchor, bootstrap_due);
        return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    }
    int writer_control[2] = {-1, -1};
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, writer_control) != 0 ||
        !set_fd_flags(writer_control[0], false) ||
        !set_fd_flags(writer_control[1], false)) {
        close(diagnostics[0]);
        close(diagnostics[1]);
        close(event_fd);
        retire_anchor(&anchor, bootstrap_due);
        return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    }
    char diagnostics_fd_text[32];
    snprintf(diagnostics_fd_text, sizeof(diagnostics_fd_text), "4");
    char *writer_argv[] = {(char *)binary_path, "--test-diagnostic-writer",
                           diagnostics_fd_text, NULL};
    if (writer_ready_fd >= 0) {
        char ready_text[32];
        snprintf(ready_text, sizeof(ready_text), "%d", writer_ready_fd);
        if (setenv("NFS_WRITER_READY_FD", ready_text, 1) != 0) {
            close(writer_control[0]); close(writer_control[1]);
            close(diagnostics[0]); close(diagnostics[1]); close(event_fd);
            retire_anchor(&anchor, bootstrap_due);
            return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
        }
    } else {
        unsetenv("NFS_WRITER_READY_FD");
    }
    struct fixed_guardian_handle writer_guardian;
    uint64_t writer_registration_due = earlier_due(bootstrap_due,
        now_ns() + NFS_GUARDIAN_REGISTRATION_NS);
    if (!start_fixed_guardian(
            &writer_guardian, binary_path, &anchor, NFS_GROUP_MAX - 1U, "W",
            "diagnostics", true, diagnostics[0], writer_control[1], event_fd,
            diagnostics[1], signal_pipe[0], writer_argv,
            writer_registration_due)) {
        close(writer_control[0]);
        close(writer_control[1]);
        close(diagnostics[0]);
        close(diagnostics[1]);
        close(event_fd);
        retire_anchor(&anchor, bootstrap_due);
        return supervisor_exit_status(NFS_EXIT_PREREQUISITE);
    }
    close(writer_control[1]);
    close(diagnostics[0]);
    close(event_fd);
    char writer_hello[NFS_CONTROL_STORAGE];
    uint32_t writer_sequence = 0;
    if (read_line_supervisor(writer_control[0], signal_pipe[0], writer_hello, sizeof(writer_hello),
                           writer_registration_due) != 1 ||
        !validate_control_line(writer_hello, 'W', &writer_sequence,
                               writer_guardian.nonce, true) ||
        !write_line(writer_control[0], "HELLO_OK 1 %u %s %s %llu\n",
                    NFS_PROTOCOL_VERSION, writer_guardian.nonce,
                    selected_clock_name(), (unsigned long long)now_ns()))
        goto writer_setup_failure;
    if (writer_ready_fd >= 0) {
        close(writer_ready_fd);
        writer_ready_fd = -1;
    }
    if (flood_diagnostics) {
        for (unsigned int i = 0; i < 8192U; ++i)
            emit_event(diagnostics[1], "DIAGNOSTIC_FILL %u\n", i);
    }
    emit_sigchld_prerequisite(diagnostics[1]);
    emit_event(diagnostics[1], "ANCHOR_READY %ld %ld %ld %ld\n",
               (long)anchor.pid, (long)anchor.pgid, (long)anchor.sid,
               (long)getpgrp());

    int control[2] = {-1, -1}, lifetime[2] = {-1, -1};
    if (!retained_child_running(anchor.pid) || !reserve_generation(generation))
        goto pre_guardian_failure;
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, control) != 0 ||
        pipe(lifetime) != 0 || !set_fd_flags(control[0], false) ||
        !set_fd_flags(control[1], false) || !set_fd_flags(lifetime[0], false) ||
        !set_fd_flags(lifetime[1], false))
        goto pre_guardian_failure;

    sigset_t blocked, previous;
    sigemptyset(&blocked);
    sigaddset(&blocked, SIGINT);
    sigaddset(&blocked, SIGTERM);
    if (sigprocmask(SIG_BLOCK, &blocked, &previous) != 0)
        goto pre_guardian_failure;
    uint64_t registration_deadline = earlier_due(bootstrap_due,
        now_ns() + NFS_GUARDIAN_REGISTRATION_NS);
    bool registration_complete = false;
    pid_t guardian_pid = fork();
    if (guardian_pid < 0) {
        sigprocmask(SIG_SETMASK, &previous, NULL);
        goto pre_guardian_failure;
    }
    if (guardian_pid == 0) {
        close(control[0]);
        close(lifetime[1]);
        close(signal_pipe[0]);
        close(signal_pipe[1]);
        if (release_ready_fd >= 0) close(release_ready_fd);
        if (release_resume_fd >= 0) close(release_resume_fd);
        close(anchor.lifetime_write);
        close(writer_guardian.lifetime_write);
        close(writer_guardian.control_fd);
        close(writer_control[0]);
        if (!install_devnull_standard_fds(false, false)) _exit(1);
        close(diagnostics[1]);
        int child_control = control[1];
        int child_lifetime = lifetime[0];
        int no_workload = -1, no_ready = -1;
        int child_pause_ready = phase_pause.name != NULL ?
            phase_pause.ready_fd : -1;
        int child_pause_resume = phase_pause.name != NULL ?
            phase_pause.resume_fd : -1;
        if (!prepare_guardian_descriptors(&child_control, &child_lifetime,
                                          &no_workload, &no_ready,
                                          &child_pause_ready,
                                          &child_pause_resume))
            _exit(1);
        struct phase_pause child_pause = {
            .name = phase_pause.name,
            .ready_fd = child_pause_ready,
            .resume_fd = child_pause_resume,
        };
        int status = guardian_main(child_control, child_lifetime, -1, -1,
                                   generation, nonce, anchor.pgid, getsid(0),
                                   "test-workload", false, workload_argv,
                                   child_pause.name != NULL ? &child_pause : NULL,
                                   registration_deadline);
        _exit(status);
    }
    close(control[1]);
    close(lifetime[0]);
    sigprocmask(SIG_SETMASK, &previous, NULL);
    pid_t registered_pgid = 0;

    char hello[NFS_CONTROL_STORAGE], ready[NFS_CONTROL_STORAGE];
    uint32_t last_sequence = 0;
    if (read_line_supervisor(control[0], signal_pipe[0], hello, sizeof(hello), registration_deadline) != 1 ||
        !validate_control_line(hello, 'G', &last_sequence, nonce, true) ||
        read_line_supervisor(control[0], signal_pipe[0], ready, sizeof(ready), registration_deadline) != 1)
        goto supervisor_failure;
    char ready_copy[NFS_CONTROL_STORAGE];
    strcpy(ready_copy, ready);
    if (!validate_control_line(ready, 'G', &last_sequence, nonce, true))
        goto supervisor_failure;
    char *fields[10];
    size_t count = split_fields(ready_copy, fields, 10);
    long parsed_generation, leader, pgid, guard_pgid, sid, held_pid;
    if (count != 9 || strcmp(fields[0], "GROUP_READY") != 0 ||
        !parse_long(fields[2], &parsed_generation) || parsed_generation != (long)generation ||
        !parse_long(fields[3], &leader) || leader != guardian_pid ||
        !parse_long(fields[4], &pgid) || pgid != guardian_pid ||
        !parse_long(fields[5], &guard_pgid) || guard_pgid != anchor.pgid ||
        !parse_long(fields[6], &sid) || sid != getsid(0) || fields[7][0] == '\0' ||
        !parse_long(fields[8], &held_pid) || held_pid <= 0 ||
        !retained_child_running(anchor.pid) ||
        getpgid(guardian_pid) != anchor.pgid ||
        getpgid((pid_t)held_pid) != guardian_pid)
        goto supervisor_failure;
    registered_pgid = (pid_t)pgid;
    char leader_identity[64];
    if (strlen(fields[7]) >= sizeof(leader_identity)) goto supervisor_failure;
    strcpy(leader_identity, fields[7]);
    emit_event(diagnostics[1], "GROUP_READY %u %ld %ld %ld %ld %s %ld\n",
               generation, leader, pgid, guard_pgid, sid, leader_identity,
               held_pid);
    if (phase_pause.name != NULL) {
        close(phase_pause.ready_fd);
        close(phase_pause.resume_fd);
        phase_pause.name = NULL;
        phase_pause.ready_fd = -1;
        phase_pause.resume_fd = -1;
    }
    if (!write_line(control[0], "HELLO_OK 1 %u %s %s %llu\n",
                    NFS_PROTOCOL_VERSION, nonce, selected_clock_name(),
                    (unsigned long long)now_ns()) ||
        !write_line(control[0], "GROUP_ACK 2 %u\n", generation))
        goto supervisor_failure;
    if (release_ready_fd >= 0) {
        uint8_t ready_byte = 'R', resume_byte = 0;
        if (!write_all(release_ready_fd, &ready_byte, 1) ||
            !read_exact(release_resume_fd, &resume_byte, 1))
            goto supervisor_failure;
        close(release_ready_fd);
        close(release_resume_fd);
        release_ready_fd = -1;
        release_resume_fd = -1;
    }
    if (!retained_child_running(anchor.pid)) goto supervisor_failure;
    if (!write_release_with_signal_gate(control[0], generation, "test-workload",
                                        "test-launch"))
        goto supervisor_failure;
    registration_complete = true;

    bool workload_started = false, workload_exited = false, guardian_dead = false;
    bool sent_term = false, sent_kill = false, quiesce_sent = false;
    int workload_exit = 1;
    uint64_t first_term_attempt = 0;
    uint64_t normal_deadline = now_ns() + UINT64_C(10) * NS_PER_SECOND;
    for (;;) {
        if (!retained_child_running(anchor.pid)) goto supervisor_failure;
        signum = atomic_load_explicit(&accepted_signal, memory_order_relaxed);
        uint64_t first_ns = (uint64_t)atomic_load_explicit(&accepted_ns, memory_order_relaxed);
        if (signum != 0 && !sent_term) {
            emit_event(diagnostics[1], "SIGNAL_ACCEPTED %d %llu\n", signum,
                       (unsigned long long)first_ns);
            first_term_attempt = now_ns();
            generation_hard_due = first_ns + NFS_CANCEL_HARD_CUTOFF_NS;
            kill(-pgid, SIGTERM);
            emit_event(diagnostics[1], "SIGNAL_GROUP %u %ld %d %llu\n", generation,
                       pgid, SIGTERM, (unsigned long long)now_ns());
            sent_term = true;
        }
        if (signum != 0 && !sent_kill &&
            now_ns() >= first_ns + NFS_CANCEL_KILL_NATIVE_NS) {
            kill(-pgid, SIGKILL);
            emit_event(diagnostics[1], "SIGNAL_GROUP %u %ld %d %llu\n", generation,
                       pgid, SIGKILL, (unsigned long long)now_ns());
            sent_kill = true;
        }
        if (signum != 0 && now_ns() >= first_ns + NFS_CANCEL_HARD_CUTOFF_NS)
            break;
        if (signum == 0 && now_ns() >= normal_deadline) goto supervisor_failure;

        struct pollfd pollfds[2] = {
            {.fd = signal_pipe[0], .events = POLLIN},
            {.fd = control[0], .events = POLLIN | POLLHUP},
        };
        int timeout = 10;
        if (signum != 0 && !sent_kill) {
            uint64_t kill_due = first_ns + NFS_CANCEL_KILL_NATIVE_NS;
            int until_kill = remaining_ms(kill_due);
            if (until_kill < timeout) timeout = until_kill;
        }
        int polled = poll(pollfds, 2, timeout);
        if (polled < 0 && errno != EINTR) goto supervisor_failure;
        if (pollfds[0].revents & POLLIN) {
            uint8_t buffer[32];
            while (read(signal_pipe[0], buffer, sizeof(buffer)) > 0) {}
        }
        if (pollfds[1].revents & POLLIN) {
            char line[NFS_CONTROL_STORAGE], original[NFS_CONTROL_STORAGE];
            uint64_t line_deadline = normal_deadline;
            if (generation_hard_due != 0 && generation_hard_due < line_deadline)
                line_deadline = generation_hard_due;
            int line_status = read_line_supervisor(
                control[0], signal_pipe[0], line, sizeof(line), line_deadline);
            if (line_status == -2 && (quiesce_sent || sent_kill)) {
                guardian_dead = true;
                goto guardian_state_check;
            }
            if (line_status != 1) goto supervisor_failure;
            strcpy(original, line);
            if (!validate_control_line(line, 'G', &last_sequence, nonce, true))
                goto supervisor_failure;
            char *message[8];
            size_t message_count = split_fields(original, message, 8);
            if (message_count == 4 && strcmp(message[0], "WORKLOAD_STARTED") == 0) {
                long workload_pid;
                uint64_t incoming_generation;
                if (workload_started || !parse_long(message[3], &workload_pid) ||
                    workload_pid != held_pid ||
                    !parse_u64(message[2], &incoming_generation) ||
                    incoming_generation != generation)
                    goto supervisor_failure;
                workload_started = true;
                emit_event(diagnostics[1], "WORKLOAD_STARTED %u %ld\n", generation,
                           workload_pid);
                if (fail_after_workload_start) {
                    uint64_t fail_due = now_ns() + UINT64_C(250) * NS_PER_MILLISECOND;
                    while (now_ns() < fail_due) {
                        struct timespec delay = {
                            .tv_sec = 0,
                            .tv_nsec = 5 * 1000 * 1000,
                        };
                        nanosleep(&delay, NULL);
                    }
                    goto supervisor_failure;
                }
            } else if (message_count == 6 && strcmp(message[0], "WORKLOAD_EXIT") == 0) {
                long value;
                uint64_t incoming_generation;
                if (!workload_started || workload_exited ||
                    !parse_u64(message[2], &incoming_generation) ||
                    incoming_generation != generation ||
                    !parse_long(message[4], &value) || value < 0 || value > 255)
                    goto supervisor_failure;
                workload_exit = strcmp(message[3], "exit") == 0 ? (int)value : 128 + (int)value;
                workload_exited = true;
                emit_event(diagnostics[1], "WORKLOAD_EXIT %u %s %ld reaped\n",
                           generation, message[3], value);
                if (!quiesce_sent) {
                    uint64_t term_attempt = first_term_attempt;
                    if (!sent_term) {
                        term_attempt = now_ns();
                        (void)kill(-pgid, SIGTERM);
                        sent_term = true;
                        first_term_attempt = term_attempt;
                        emit_event(diagnostics[1],
                                   "NORMAL_SIGNAL_GROUP %u %ld %d %llu\n",
                                   generation, pgid, SIGTERM,
                                   (unsigned long long)term_attempt);
                    }
                    uint64_t kill_due = term_attempt + NFS_CANCEL_KILL_NATIVE_NS;
                    uint64_t hard_due = term_attempt + NFS_NORMAL_CLEANUP_NS;
                    if (signum != 0) {
                        uint64_t accepted = (uint64_t)atomic_load_explicit(
                            &accepted_ns, memory_order_relaxed);
                        uint64_t cancel_kill = accepted + NFS_CANCEL_KILL_NATIVE_NS;
                        uint64_t cancel_hard = accepted + NFS_CANCEL_HARD_CUTOFF_NS;
                        if (cancel_kill < kill_due) kill_due = cancel_kill;
                        if (cancel_hard < hard_due) hard_due = cancel_hard;
                    }
                    generation_hard_due = hard_due;
                    if (!write_line(control[0], "QUIESCE 4 %u %llu %llu\n",
                                    generation, (unsigned long long)kill_due,
                                    (unsigned long long)hard_due))
                        goto supervisor_failure;
                    quiesce_sent = true;
                }
            }
        }
        if (pollfds[1].revents & POLLHUP) guardian_dead = true;
guardian_state_check:
        if (workload_exited && quiesce_sent) break;
        if (guardian_dead) {
            siginfo_t info;
            memset(&info, 0, sizeof(info));
            if (waitid(P_PID, (id_t)guardian_pid, &info,
                       WEXITED | WNOHANG | WNOWAIT) == 0 && info.si_pid == guardian_pid) {
                break;
            }
        }
    }

    bool cleanup_confirmed;
    char cleanup_reason[64] = "unavailable";
    uint64_t accepted_proof = 0;
    {
        const int q_close_fds[] = {
            control[0], lifetime[1], signal_pipe[0], signal_pipe[1], diagnostics[1],
            writer_guardian.lifetime_write, writer_guardian.control_fd,
            writer_control[0]
        };
        signum = atomic_load_explicit(&accepted_signal, memory_order_relaxed);
        uint64_t cleanup_started = signum != 0 ?
            (uint64_t)atomic_load_explicit(&accepted_ns, memory_order_relaxed) : now_ns();
        uint64_t hard_due = generation_hard_due != 0 ? generation_hard_due :
            cleanup_started + (signum != 0 ? NFS_CANCEL_HARD_CUTOFF_NS :
                                             NFS_NORMAL_CLEANUP_NS);
        generation_hard_due = hard_due;
        uint64_t cleanup_due = hard_due > UINT64_C(350) * NS_PER_MILLISECOND ?
            hard_due - UINT64_C(350) * NS_PER_MILLISECOND : hard_due;
        uint64_t observe_due = now_ns() + NFS_OBSERVATION_NS;
        if (observe_due > cleanup_due) observe_due = cleanup_due;
        struct observation observation = {.confirmed = false, .reason = "cutoff"};
        if (now_ns() < observe_due)
            observation = observe_group_worker(
                binary_path, (pid_t)pgid, (pid_t)sid, guardian_pid, leader_identity,
                generation, 1, observe_due, signal_pipe[0], diagnostics[1], observer_mode,
                anchor.pgid, getsid(0), q_close_fds,
                sizeof(q_close_fds) / sizeof(q_close_fds[0]));
        if (observation.confirmed) accepted_proof = 1;
        signum = atomic_load_explicit(&accepted_signal, memory_order_relaxed);
        if (signum != 0) {
            uint64_t accepted = (uint64_t)atomic_load_explicit(
                &accepted_ns, memory_order_relaxed);
            uint64_t signal_hard = accepted + NFS_CANCEL_HARD_CUTOFF_NS;
            uint64_t signal_observe = accepted + NFS_CANCEL_OBSERVE_END_NS;
            if (generation_hard_due == 0 || signal_hard < generation_hard_due)
                generation_hard_due = signal_hard;
            if (signal_observe < cleanup_due) cleanup_due = signal_observe;
        }
        if (signum != 0 && !sent_term) {
            emit_event(diagnostics[1], "SIGNAL_ACCEPTED %d %llu\n", signum,
                       atomic_load_explicit(&accepted_ns, memory_order_relaxed));
        }
        if (!observation.confirmed && !(signum != 0 && sent_kill)) {
            bool cancellation_cleanup = signum != 0;
            if (!sent_term) {
                first_term_attempt = now_ns();
                kill(-pgid, SIGTERM);
                sent_term = true;
                emit_event(diagnostics[1], "%s %u %ld %d %llu\n",
                           cancellation_cleanup ? "SIGNAL_GROUP" : "NORMAL_SIGNAL_GROUP",
                           generation, pgid, SIGTERM,
                           (unsigned long long)first_term_attempt);
            }
            uint64_t kill_due = first_term_attempt + NFS_CANCEL_KILL_NATIVE_NS;
            if (signum != 0) {
                uint64_t fixed_due = cleanup_started + NFS_CANCEL_KILL_NATIVE_NS;
                if (fixed_due < kill_due) kill_due = fixed_due;
            }
            while (now_ns() < kill_due) {
                struct pollfd signal_poll = {.fd = signal_pipe[0], .events = POLLIN};
                int polled = poll(&signal_poll, 1, remaining_ms(kill_due));
                if (polled < 0 && errno != EINTR) break;
                if (polled > 0) {
                    uint8_t buffer[32];
                    while (read(signal_pipe[0], buffer, sizeof(buffer)) > 0) {}
                }
            }
            signum = atomic_load_explicit(&accepted_signal, memory_order_relaxed);
            if (signum != 0 && !cancellation_cleanup)
                emit_event(diagnostics[1], "SIGNAL_ACCEPTED %d %llu\n", signum,
                           atomic_load_explicit(&accepted_ns, memory_order_relaxed));
            kill(-pgid, SIGKILL);
            sent_kill = true;
            emit_event(diagnostics[1], "%s %u %ld %d %llu\n",
                       cancellation_cleanup ? "SIGNAL_GROUP" : "NORMAL_SIGNAL_GROUP",
                       generation, pgid, SIGKILL,
                       (unsigned long long)now_ns());
        }
        if (!observation.confirmed && now_ns() < cleanup_due) {
            uint64_t second_due = now_ns() + NFS_OBSERVATION_NS;
            if (second_due > cleanup_due) second_due = cleanup_due;
            observation = observe_group_worker(
                binary_path, (pid_t)pgid, (pid_t)sid, guardian_pid, leader_identity,
                generation, 2, second_due, signal_pipe[0], diagnostics[1],
                observer_mode, anchor.pgid, getsid(0), q_close_fds,
                sizeof(q_close_fds) / sizeof(q_close_fds[0]));
            if (observation.confirmed) accepted_proof = 2;
        }
        cleanup_confirmed = observation.confirmed;
        strcpy(cleanup_reason, observation.reason);
        emit_event(diagnostics[1], "OBSERVED %u %s %s\n", generation,
                   observation.confirmed ? "confirmed" : "unconfirmed",
                   observation.reason);
    }
    if (!cleanup_confirmed) (void)kill(-pgid, SIGKILL);
    emit_event(diagnostics[1], "RETIRED %u\n", generation);
    if (cleanup_confirmed) {
        if (!write_line(control[0], "EXIT_PERMIT 5 %u observed %llu\n",
                        generation, (unsigned long long)accepted_proof))
            cleanup_confirmed = false;
    }
    if (cleanup_confirmed) {
        int guardian_status = 0;
        uint64_t reap_due = signal_clipped_due(
            reserve_before(generation_hard_due, UINT64_C(150) * NS_PER_MILLISECOND),
            NFS_CANCEL_OBSERVE_END_NS);
        if (!reap_child_until(guardian_pid, reap_due, &guardian_status)) {
            cleanup_confirmed = false;
            strcpy(cleanup_reason, "guardian-retirement-unconfirmed");
        }
    }
    if (!cleanup_confirmed) {
        /* S already retired group signalling above, including when a valid
         * EXIT_PERMIT was sent but G failed to terminate within its reserve. */
        (void)retire_unconfirmed_child(guardian_pid, 0, true, generation,
                                       "workload", generation_hard_due,
                                       diagnostics[1]);
        emit_event(diagnostics[1],
                   "CLEANUP_RESULT %u unconfirmed %s reaped=false generation_closed=false\n",
                   generation, cleanup_reason);
    }
    close(lifetime[1]);
    close(control[0]);
    if (writer_drain_ready_fd >= 0) {
        (void)write_all(writer_drain_ready_fd, "R", 1);
        close(writer_drain_ready_fd);
    }
    finish_supervisor_output(&writer_guardian, writer_control[0], &writer_sequence,
                             diagnostics[1], signal_pipe[0], &anchor,
                             generation_hard_due);
    return supervisor_exit_status(cleanup_confirmed ? workload_exit : 1);

supervisor_failure:
    {
        uint64_t failure_started = now_ns();
        if (!registration_complete && failure_started > registration_deadline)
            failure_started = registration_deadline;
        if (generation_hard_due == 0)
            generation_hard_due = failure_started + NFS_CANCEL_HARD_CUTOFF_NS;
        generation_hard_due = signal_clipped_due(generation_hard_due,
                                                  NFS_CANCEL_HARD_CUTOFF_NS);
        terminate_registered_group(registered_pgid, guardian_pid, lifetime[1],
                                   failure_started, generation_hard_due,
                                   generation, diagnostics[1]);
    }
    close(control[0]);
    finish_supervisor_output(&writer_guardian, writer_control[0], &writer_sequence,
                             diagnostics[1], signal_pipe[0], &anchor,
                             generation_hard_due);
    return supervisor_exit_status(1);

pre_guardian_failure:
    if (control[0] >= 0) close(control[0]);
    if (control[1] >= 0) close(control[1]);
    if (lifetime[0] >= 0) close(lifetime[0]);
    if (lifetime[1] >= 0) close(lifetime[1]);
    finish_supervisor_output(&writer_guardian, writer_control[0], &writer_sequence,
                             diagnostics[1], signal_pipe[0], &anchor,
                             bootstrap_due);
    return supervisor_exit_status(NFS_EXIT_PREREQUISITE);

writer_setup_failure:
    (void)kill(-writer_guardian.pgid, SIGKILL);
    (void)kill(writer_guardian.pid, SIGKILL);
    close(writer_guardian.lifetime_write);
    terminate_child_bounded(writer_guardian.pid,
                            bootstrap_due);
    close(writer_guardian.control_fd);
    close(writer_control[0]);
    close(diagnostics[1]);
    retire_anchor(&anchor, bootstrap_due);
    return supervisor_exit_status(NFS_EXIT_PREREQUISITE);

}

static const char *base_name(const char *path) {
    const char *slash = strrchr(path, '/');
    return slash == NULL ? path : slash + 1;
}

int main(int argc, char *argv[]) {
    if (strcmp(base_name(argv[0]), "bash") == 0) return compatibility_launcher(argc, argv);

    if (argc == 3 && strcmp(argv[1], "--test-process-stopped") == 0) {
        long pid;
        if (!parse_long(argv[2], &pid) || pid <= 0) return 2;
        return process_is_stopped((pid_t)pid) ? 0 : 2;
    }

    if (argc == 4 && (strcmp(argv[1], "--verify-worker") == 0 ||
                      strcmp(argv[1], "--test-verify-worker") == 0)) {
        fixture_test_mode = strcmp(argv[1], "--test-verify-worker") == 0;
        long result_fd;
        if (!parse_long(argv[2], &result_fd) || result_fd < 0 || result_fd > INT_MAX)
            return 2;
        const char *ready_text = fixture_test_mode ? getenv("NFS_VERIFIER_READY_FD") : NULL;
        if (ready_text != NULL) {
            long ready_fd;
            char ready[96];
            if (!parse_long(ready_text, &ready_fd) || ready_fd < 0 ||
                ready_fd > INT_MAX)
                return 2;
            int size = snprintf(ready, sizeof(ready), "%ld %ld %ld\n",
                                (long)getpid(), (long)getppid(), (long)getpgrp());
            if (size <= 0 || (size_t)size >= sizeof(ready) ||
                !write_all((int)ready_fd, ready, (size_t)size))
                return 2;
            close((int)ready_fd);
        }
        uint8_t result = verify_provenance(argv[3]) ? 1U : 0U;
        bool written = write_all((int)result_fd, &result, sizeof(result));
        close((int)result_fd);
        return written ? 0 : 1;
    }

    if (argc == 3 && (strcmp(argv[1], "--diagnostic-writer") == 0 ||
                      strcmp(argv[1], "--test-diagnostic-writer") == 0)) {
        fixture_test_mode = strcmp(argv[1], "--test-diagnostic-writer") == 0;
        long read_fd;
        const char *nonce = getenv("NFS_FIXED_NONCE");
        if (!parse_long(argv[2], &read_fd) || read_fd < 0 || read_fd > INT_MAX ||
            nonce == NULL || !is_lower_hex(nonce, 32))
            return 2;
        int ready_fd = -1;
        const char *ready_text = fixture_test_mode ? getenv("NFS_WRITER_READY_FD") : NULL;
        long parsed_ready;
        if (ready_text != NULL) {
            if (!parse_long(ready_text, &parsed_ready) || parsed_ready < 0 || parsed_ready > INT_MAX)
                return 2;
            ready_fd = (int)parsed_ready;
        }
        int status = diagnostic_writer((int)read_fd, STDOUT_FILENO,
                                       STDIN_FILENO, nonce, ready_fd);
        close((int)read_fd);
        return status;
    }

    if (argc == 4 && strcmp(argv[1], "--test-deadline") == 0) {
        uint64_t expected;
        if (!parse_u64(argv[3], &expected)) return 2;
        for (size_t i = 0; i < sizeof(deadline_entries) / sizeof(deadline_entries[0]); ++i)
            if (strcmp(argv[2], deadline_entries[i].name) == 0)
                return deadline_entries[i].nanoseconds == expected ? 0 : 2;
        return 2;
    }
    if (argc == 4 && strcmp(argv[1], "--test-validate-wire") == 0)
        return validate_wire(argv[2], argv[3]);
    if (argc == 11 && strcmp(argv[1], "--observer-worker") == 0) {
        long result_fd_value;
        uint64_t request_id, generation;
        pid_t pgid, sid, leader;
        if (!parse_long(argv[2], &result_fd_value) || result_fd_value < 0 ||
            result_fd_value > INT_MAX || !parse_u64(argv[3], &request_id) ||
            request_id == 0 || !parse_u64(argv[4], &generation) || generation == 0 ||
            generation > NFS_GROUP_MAX || !parse_positive_pid(argv[5], &pgid) ||
            !parse_positive_pid(argv[6], &sid) || !parse_positive_pid(argv[7], &leader) ||
            !safe_atom(argv[8], 63) ||
            !(strcmp(argv[9], "normal") == 0 ||
              strcmp(argv[9], "fragmented") == 0 ||
              strcmp(argv[9], "stalled") == 0 ||
              strcmp(argv[9], "denied") == 0 ||
              strcmp(argv[9], "incomplete") == 0) ||
            !is_lower_hex(argv[10], 32))
            return 2;
        return observer_worker((int)result_fd_value, request_id, (uint32_t)generation,
                               pgid, sid, leader, argv[8], argv[9], argv[10]);
    }
    if (argc == 7 && strcmp(argv[1], "--test-parse-linux-stat") == 0) {
        char buffer[4096];
        ssize_t count = read(STDIN_FILENO, buffer, sizeof(buffer) - 1);
        if (count <= 0 || (size_t)count >= sizeof(buffer) - 1) return 2;
        buffer[count] = '\0';
        struct linux_stat_record record;
        long pid, pgrp, sid;
        uint64_t identity;
        if (!parse_linux_stat_line(buffer, &record) || !parse_long(argv[2], &pid) ||
            strlen(argv[3]) != 1 || !parse_long(argv[4], &pgrp) ||
            !parse_long(argv[5], &sid) || !parse_u64(argv[6], &identity))
            return 2;
        return record.pid == pid && record.state == argv[3][0] &&
               record.pgrp == pgrp && record.session == sid &&
               record.start_identity == identity ? 0 : 2;
    }
    if (argc == 7 && strcmp(argv[1], "--test-observe") == 0) {
        long generation, pgid, sid, leader;
        if (!parse_long(argv[2], &generation) || generation <= 0 ||
            !parse_long(argv[3], &pgid) || !parse_long(argv[4], &sid) ||
            !parse_long(argv[5], &leader))
            return 1;
        struct observation observation = observe_group_once((pid_t)pgid, (pid_t)sid,
                                                            (pid_t)leader, argv[6]);
        return observation.confirmed ? 0 : 2;
    }
    if (argc == 7 && strcmp(argv[1], "--test-observer-message") == 0) {
        uint64_t active_request, active_generation, message_request, message_generation;
        if (!parse_u64(argv[3], &active_request) || active_request == 0 ||
            !parse_u64(argv[4], &active_generation) || active_generation == 0 ||
            active_generation > NFS_GROUP_MAX ||
            !parse_u64(argv[5], &message_request) || message_request == 0 ||
            !parse_u64(argv[6], &message_generation) || message_generation == 0 ||
            message_generation > NFS_GROUP_MAX)
            return 2;
        bool active = strcmp(argv[2], "active") == 0;
        if (!active && strcmp(argv[2], "retired") != 0) return 2;
        return observer_message_matches(active, active_request,
                                        (uint32_t)active_generation,
                                        message_request, message_generation) ? 0 : 2;
    }
    if (argc == 10 && strcmp(argv[1], "--test-exit-proof") == 0) {
        uint64_t revoked, done, own_sequence, generation, incoming, proof_ref;
        if (!safe_atom(argv[2], 32) || !parse_u64(argv[3], &revoked) ||
            revoked > 1 || !parse_u64(argv[4], &done) || done > 1 ||
            !parse_u64(argv[5], &own_sequence) || own_sequence > UINT32_MAX ||
            !parse_u64(argv[6], &generation) || generation == 0 ||
            generation > NFS_GROUP_MAX || !parse_u64(argv[7], &incoming) ||
            !parse_u64(argv[9], &proof_ref))
            return 2;
        return valid_exit_permit((uint32_t)generation, argv[2], revoked != 0,
                                 done != 0, (uint32_t)own_sequence, incoming,
                                 argv[8], proof_ref) ? 0 : 2;
    }
    if (argc >= 6 && strcmp(argv[1], "--test-supervise") == 0) {
        fixture_test_mode = true;
        int event_fd = -1, pause_ready = -1, pause_resume = -1;
        int release_ready = -1, release_resume = -1, index = 2;
        int writer_ready = -1;
        int writer_drain_ready = -1;
        bool flood_diagnostics = false;
        bool fail_after_workload_start = false;
        const char *observer_mode = "normal";
        const char *phase_pause_name = NULL;
        int phase_ready = -1, phase_resume = -1;
        while (index < argc && strcmp(argv[index], "--") != 0) {
            long first, second;
            if (index + 1 < argc && strcmp(argv[index], "--event-fd") == 0 &&
                parse_long(argv[index + 1], &first) && first >= 0 && first <= INT_MAX) {
                event_fd = (int)first;
                index += 2;
            } else if (index + 2 < argc &&
                       strcmp(argv[index], "--pause-before-handlers") == 0 &&
                       parse_long(argv[index + 1], &first) && first >= 0 &&
                       first <= INT_MAX && parse_long(argv[index + 2], &second) &&
                       second >= 0 && second <= INT_MAX) {
                pause_ready = (int)first;
                pause_resume = (int)second;
                index += 3;
            } else if (index + 2 < argc &&
                       strcmp(argv[index], "--pause-before-release") == 0 &&
                       parse_long(argv[index + 1], &first) && first >= 0 &&
                       first <= INT_MAX && parse_long(argv[index + 2], &second) &&
                       second >= 0 && second <= INT_MAX) {
                release_ready = (int)first;
                release_resume = (int)second;
                index += 3;
            } else if (strcmp(argv[index], "--fail-after-workload-start") == 0) {
                fail_after_workload_start = true;
                ++index;
            } else if (strcmp(argv[index], "--flood-diagnostics") == 0) {
                flood_diagnostics = true;
                ++index;
            } else if (index + 3 < argc &&
                       strcmp(argv[index], "--phase-pause") == 0 &&
                       (strcmp(argv[index + 1], "before-anchor-ready") == 0 ||
                        strcmp(argv[index + 1], "before-group") == 0 ||
                        strcmp(argv[index + 1], "group-formed") == 0 ||
                        strcmp(argv[index + 1], "child-held") == 0 ||
                        strcmp(argv[index + 1], "after-quiesce") == 0 ||
                        strcmp(argv[index + 1], "observer-stalled") == 0 ||
                        strcmp(argv[index + 1], "group-migrated") == 0) &&
                       parse_long(argv[index + 2], &first) && first >= 0 &&
                       first <= INT_MAX && parse_long(argv[index + 3], &second) &&
                       second >= 0 && second <= INT_MAX) {
                phase_pause_name = argv[index + 1];
                phase_ready = (int)first;
                phase_resume = (int)second;
                index += 4;
            } else if (index + 1 < argc && strcmp(argv[index], "--observer-mode") == 0 &&
                       (strcmp(argv[index + 1], "normal") == 0 ||
                        strcmp(argv[index + 1], "fragmented") == 0 ||
                        strcmp(argv[index + 1], "stalled") == 0 ||
                        strcmp(argv[index + 1], "denied") == 0 ||
                        strcmp(argv[index + 1], "incomplete") == 0)) {
                observer_mode = argv[index + 1];
                index += 2;
            } else if (index + 1 < argc &&
                       strcmp(argv[index], "--writer-ready-fd") == 0 &&
                       parse_long(argv[index + 1], &first) && first >= 0 &&
                       first <= INT_MAX) {
                writer_ready = (int)first;
                index += 2;
            } else if (index + 1 < argc &&
                       strcmp(argv[index], "--writer-drain-ready-fd") == 0 &&
                       parse_long(argv[index + 1], &first) && first >= 0 &&
                       first <= INT_MAX) {
                writer_drain_ready = (int)first;
                index += 2;
            } else {
                return 2;
            }
        }
        if (event_fd < 0 || index >= argc || strcmp(argv[index], "--") != 0 ||
            index + 1 >= argc)
            return 2;
        return supervise_test_workload(argv[0], event_fd, pause_ready, pause_resume,
                                       release_ready, release_resume,
                                       writer_ready,
                                       writer_drain_ready,
                                       flood_diagnostics,
                                       fail_after_workload_start, observer_mode,
                                       phase_pause_name, phase_ready, phase_resume,
                                       &argv[index + 1]);
    }
    return NFS_EXIT_UNAVAILABLE;
}
