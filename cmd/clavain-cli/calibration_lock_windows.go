//go:build windows

package main

import (
	"fmt"
	"os"

	"golang.org/x/sys/windows"
)

func withCalibrationFileLock(lock *os.File, fn func() error) error {
	var overlapped windows.Overlapped
	handle := windows.Handle(lock.Fd())
	if err := windows.LockFileEx(handle, windows.LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, &overlapped); err != nil {
		return fmt.Errorf("calibration-streak: acquire lock: %w", err)
	}
	defer windows.UnlockFileEx(handle, 0, 1, 0, &overlapped) //nolint:errcheck
	return fn()
}
