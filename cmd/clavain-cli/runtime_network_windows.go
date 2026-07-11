//go:build windows

package main

import (
	"errors"

	"golang.org/x/sys/windows"
)

func isRuntimeConnectionRefused(err error) bool {
	return errors.Is(err, windows.WSAECONNREFUSED)
}
