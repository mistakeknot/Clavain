//go:build windows

package main

import (
	"errors"
	"os/exec"
	"time"
)

func configureRuntimeProcessIsolation(_ *exec.Cmd) error {
	return errors.New("runtime evidence process isolation is unsupported on windows")
}

func stopRuntimeProcessIsolation(_ *runtimeManagedProcess, _ time.Duration) error {
	return errors.New("runtime evidence process isolation is unsupported on windows")
}
