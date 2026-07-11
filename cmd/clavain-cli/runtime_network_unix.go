//go:build !windows

package main

import (
	"errors"
	"syscall"
)

func isRuntimeConnectionRefused(err error) bool {
	return errors.Is(err, syscall.ECONNREFUSED)
}
