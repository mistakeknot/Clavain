//go:build !windows

package quarantine

import (
	"os"

	"golang.org/x/sys/unix"
)

func withFileLock(lock *os.File, fn func() error) error {
	if err := unix.Flock(int(lock.Fd()), unix.LOCK_EX); err != nil {
		return err
	}
	defer unix.Flock(int(lock.Fd()), unix.LOCK_UN) //nolint:errcheck
	return fn()
}
