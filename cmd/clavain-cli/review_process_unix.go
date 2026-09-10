//go:build !windows

package main

import (
	"errors"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// The review supervisor and worker lean on POSIX process groups and flock.
// Keeping those calls here, behind a build tag, lets the CLI still compile
// for windows (the release build targets it) with the degraded behaviour in
// review_process_windows.go, the same split runtime_process_*.go uses.

func reviewFlock(f *os.File, nonblock bool) error {
	flags := syscall.LOCK_EX
	if nonblock {
		flags |= syscall.LOCK_NB
	}
	return syscall.Flock(int(f.Fd()), flags)
}

func reviewLockBusy(err error) bool {
	return errors.Is(err, syscall.EWOULDBLOCK)
}

func reviewSupervisorAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{Setsid: true}
}

func reviewCheckAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{Setpgid: true}
}

// Verify the worker group once, then retain its ID through graceful drain.
// The wrapper may exit first; looking its PID up again would orphan children.
func stopReviewWorkerGroup(pid int) (bool, error) {
	group, err := syscall.Getpgid(pid)
	if err != nil || group != pid {
		return false, nil
	}
	if err = syscall.Kill(-group, syscall.SIGTERM); err != nil && err != syscall.ESRCH {
		return false, err
	}
	deadline := time.Now().Add(8 * time.Second)
	for time.Now().Before(deadline) {
		probe := syscall.Kill(-group, 0)
		if probe == syscall.ESRCH || (probe == syscall.EPERM && reviewGroupExited(group)) {
			return true, nil
		}
		time.Sleep(50 * time.Millisecond)
	}
	if err = syscall.Kill(-group, syscall.SIGKILL); err != nil && err != syscall.ESRCH {
		return false, err
	}
	return true, nil
}

// On macOS, signalling a group containing only its unreaped zombie leader
// returns EPERM, not ESRCH. Confirm the absence of live group members; an
// unavailable process inventory must not turn a permission error into success.
func reviewGroupExited(group int) bool {
	data, err := exec.Command("ps", "-axo", "pgid=,stat=").Output()
	if err != nil {
		return false
	}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) == 2 && fields[0] == strconv.Itoa(group) && !strings.HasPrefix(fields[1], "Z") {
			return false
		}
	}
	return true
}

func killReviewCheckGroup(check *exec.Cmd) error {
	if check.Process == nil {
		return os.ErrProcessDone
	}
	return syscall.Kill(-check.Process.Pid, syscall.SIGKILL)
}
