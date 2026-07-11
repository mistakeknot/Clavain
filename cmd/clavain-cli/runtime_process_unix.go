//go:build !windows

package main

import (
	"errors"
	"os/exec"
	"syscall"
	"time"
)

func configureRuntimeProcessIsolation(cmd *exec.Cmd) error {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	return nil
}

func stopRuntimeProcessIsolation(process *runtimeManagedProcess, timeout time.Duration) error {
	// Signal the group even when the leader has already exited. Descendants
	// inherit the collector-created PGID and otherwise survive an early leader.
	if err := signalRuntimeProcessGroup(process.pid, syscall.SIGTERM); err != nil {
		return err
	}
	if waitRuntimeProcessGroupExit(process, timeout) {
		return nil
	}
	if err := signalRuntimeProcessGroup(process.pid, syscall.SIGKILL); err != nil {
		return err
	}
	if !waitRuntimeProcessGroupExit(process, timeout) {
		return errors.New("process group remains after SIGKILL")
	}
	return nil
}

func signalRuntimeProcessGroup(pid int, signal syscall.Signal) error {
	err := syscall.Kill(-pid, signal)
	if err != nil && !errors.Is(err, syscall.ESRCH) {
		return err
	}
	return nil
}

func waitRuntimeProcessGroupExit(process *runtimeManagedProcess, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for {
		leaderExited, _ := process.exited()
		groupErr := syscall.Kill(-process.pid, 0)
		groupGone := errors.Is(groupErr, syscall.ESRCH)
		if leaderExited && groupGone {
			return true
		}
		if groupErr != nil && !groupGone {
			return false
		}
		if time.Now().After(deadline) {
			return false
		}
		time.Sleep(20 * time.Millisecond)
	}
}
