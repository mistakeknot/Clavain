//go:build !windows

package main

import (
	"errors"
	"os"
	"os/exec"
	"syscall"
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

// stopReviewWorkerGroup kills the worker's process group when pid leads one.
// It reports whether the group was signalled.
func stopReviewWorkerGroup(pid int) (bool, error) {
	group, err := syscall.Getpgid(pid)
	if err != nil || group != pid {
		return false, nil
	}
	if err = syscall.Kill(-group, syscall.SIGKILL); err != nil && err != syscall.ESRCH {
		return false, err
	}
	return true, nil
}

func killReviewCheckGroup(check *exec.Cmd) error {
	if check.Process == nil {
		return os.ErrProcessDone
	}
	return syscall.Kill(-check.Process.Pid, syscall.SIGKILL)
}
