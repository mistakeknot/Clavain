//go:build windows

package quarantine

import (
	"os"

	"golang.org/x/sys/windows"
)

func withFileLock(lock *os.File, fn func() error) error {
	var overlapped windows.Overlapped
	handle := windows.Handle(lock.Fd())
	if err := windows.LockFileEx(handle, windows.LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, &overlapped); err != nil {
		return err
	}
	defer windows.UnlockFileEx(handle, 0, 1, 0, &overlapped) //nolint:errcheck
	return fn()
}
