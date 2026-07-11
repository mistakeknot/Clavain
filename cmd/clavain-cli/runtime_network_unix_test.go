//go:build !windows

package main

import (
	"context"
	"os"
	"syscall"
	"testing"
)

func TestRuntimePortCleanupAcceptsOnlyConnectionRefused(t *testing.T) {
	if !runtimePortCleanupConfirmed(os.NewSyscallError("connect", syscall.ECONNREFUSED)) {
		t.Fatal("ECONNREFUSED should confirm a closed listener")
	}
	for _, err := range []error{
		os.NewSyscallError("connect", syscall.EPERM),
		os.NewSyscallError("connect", syscall.ETIMEDOUT),
		context.DeadlineExceeded,
	} {
		if runtimePortCleanupConfirmed(err) {
			t.Fatalf("ambiguous dial error was treated as cleanup proof: %v", err)
		}
	}
}
