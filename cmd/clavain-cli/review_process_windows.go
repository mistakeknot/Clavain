//go:build windows

package main

import (
	"errors"
	"os"
	"os/exec"
	"syscall"

	"golang.org/x/sys/windows"
)

// Windows has no process groups to kill or flock to take; the lock uses
// LockFileEx and the group operations degrade to the leader process only.

func reviewFlock(f *os.File, nonblock bool) error {
	var overlapped windows.Overlapped
	flags := uint32(windows.LOCKFILE_EXCLUSIVE_LOCK)
	if nonblock {
		flags |= windows.LOCKFILE_FAIL_IMMEDIATELY
	}
	return windows.LockFileEx(windows.Handle(f.Fd()), flags, 0, 1, 0, &overlapped)
}

func reviewLockBusy(err error) bool {
	return errors.Is(err, windows.ERROR_LOCK_VIOLATION)
}

func reviewSupervisorAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{CreationFlags: windows.CREATE_NEW_PROCESS_GROUP | windows.DETACHED_PROCESS}
}

func reviewCheckAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{CreationFlags: windows.CREATE_NEW_PROCESS_GROUP}
}

func stopReviewWorkerGroup(_ int) (bool, error) {
	return false, nil
}

func killReviewCheckGroup(check *exec.Cmd) error {
	if check.Process == nil {
		return os.ErrProcessDone
	}
	return check.Process.Kill()
}
