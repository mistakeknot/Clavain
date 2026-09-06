package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestReviewCancellationStopsWorkerChildrenEvenIfKernelReportsSuccess(t *testing.T) {
	dir := t.TempDir()
	bin := filepath.Join(dir, "bin")
	os.Mkdir(bin, 0700)
	os.WriteFile(filepath.Join(bin, "ic"), []byte("#!/bin/sh\nexit 0\n"), 0700)
	t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
	script := filepath.Join(dir, "launch.sh")
	childFile := filepath.Join(dir, "child")
	os.WriteFile(script, []byte("#!/bin/sh\nsleep 300 &\necho $! > "+shellReviewQuote(childFile)+"\nwait\n"), 0700)
	cmd := exec.Command("sh", script)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL); cmd.Wait() }()
	var child int
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		data, _ := os.ReadFile(childFile)
		child, _ = strconv.Atoi(strings.TrimSpace(string(data)))
		if child > 1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if child <= 1 {
		t.Fatal("child never started")
	}
	if err := stopReviewWorker(reviewReceipt{Project: dir, DispatchID: "fixture", WorkerPID: cmd.Process.Pid}, dir); err != nil {
		t.Fatal(err)
	}
	deadline = time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		data, err := exec.Command("ps", "-p", strconv.Itoa(child), "-o", "stat=").Output()
		if err != nil || strings.HasPrefix(strings.TrimSpace(string(data)), "Z") {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("model child survived successful kernel cancellation")
}
