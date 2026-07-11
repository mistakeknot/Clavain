//go:build !windows

package main

import (
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestRuntimeManagedProcessStopKillsDescendantsAfterLeaderExit(t *testing.T) {
	pidFile := filepath.Join(t.TempDir(), "child.pid")
	env := runtimeEvidenceEnvironment(map[string]string{
		"CLAVAIN_RUNTIME_TEST_HELPER":   "parent",
		"CLAVAIN_RUNTIME_TEST_PID_FILE": pidFile,
	})
	process, err := startRuntimeManagedProcess([]string{os.Args[0], "-test.run=TestRuntimeManagedProcessHelper"}, env, ".", 64<<10)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = syscall.Kill(-process.pid, syscall.SIGKILL) }()
	select {
	case <-process.done:
	case <-time.After(5 * time.Second):
		t.Fatal("helper leader did not exit")
	}
	var childPID int
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		data, readErr := os.ReadFile(pidFile)
		if readErr == nil {
			childPID, _ = strconv.Atoi(strings.TrimSpace(string(data)))
			if childPID > 0 {
				break
			}
		}
		time.Sleep(20 * time.Millisecond)
	}
	if childPID <= 0 {
		t.Fatal("helper did not report child PID")
	}
	if err := process.stop(500 * time.Millisecond); err != nil {
		t.Fatalf("stop: %v", err)
	}
	if err := syscall.Kill(childPID, 0); !errors.Is(err, syscall.ESRCH) {
		t.Fatalf("descendant %d remains after stop: %v", childPID, err)
	}
}
