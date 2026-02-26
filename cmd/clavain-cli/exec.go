package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// icBin caches the resolved path to the ic binary.
var icBin string

// findIC locates the ic binary on PATH. Returns error if not found.
func findIC() (string, error) {
	if icBin != "" {
		return icBin, nil
	}
	path, err := exec.LookPath("ic")
	if err != nil {
		path, err = exec.LookPath("intercore")
		if err != nil {
			return "", fmt.Errorf("ic binary not found on PATH")
		}
	}
	icBin = path
	return icBin, nil
}

// runIC executes ic with the given args and returns stdout.
// Pass --json as first arg for JSON mode.
func runIC(args ...string) ([]byte, error) {
	bin, err := findIC()
	if err != nil {
		return nil, err
	}
	cmd := exec.Command(bin, args...)
	cmd.Stderr = os.Stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("ic %s: %w", strings.Join(args, " "), err)
	}
	return bytes.TrimSpace(out), nil
}

// runICJSON executes ic --json <args> and unmarshals the result into dst.
func runICJSON(dst any, args ...string) error {
	fullArgs := append([]string{"--json"}, args...)
	out, err := runIC(fullArgs...)
	if err != nil {
		return err
	}
	return json.Unmarshal(out, dst)
}

// runBD executes bd with the given args and returns stdout.
func runBD(args ...string) ([]byte, error) {
	path, err := exec.LookPath("bd")
	if err != nil {
		return nil, fmt.Errorf("bd binary not found on PATH")
	}
	cmd := exec.Command(path, args...)
	cmd.Stderr = os.Stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("bd %s: %w", strings.Join(args, " "), err)
	}
	return bytes.TrimSpace(out), nil
}

// runGit executes git with the given args and returns stdout.
func runGit(args ...string) ([]byte, error) {
	cmd := exec.Command("git", args...)
	cmd.Stderr = os.Stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("git %s: %w", strings.Join(args, " "), err)
	}
	return bytes.TrimSpace(out), nil
}

// bdAvailable returns true if bd is on PATH.
func bdAvailable() bool {
	_, err := exec.LookPath("bd")
	return err == nil
}

// icAvailable returns true if ic is on PATH and healthy.
func icAvailable() bool {
	bin, err := findIC()
	if err != nil {
		return false
	}
	cmd := exec.Command(bin, "health")
	return cmd.Run() == nil
}

// execCommand creates an exec.Cmd (extracted for testability).
var execCommand = exec.Command

// runCommandExec runs an arbitrary command and returns trimmed stdout.
func runCommandExec(name string, args ...string) ([]byte, error) {
	cmd := execCommand(name, args...)
	cmd.Stderr = os.Stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("%s %s: %w", name, strings.Join(args, " "), err)
	}
	return bytes.TrimSpace(out), nil
}
