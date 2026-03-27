package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// cxdbDir returns the .clavain/cxdb directory path, creating it if needed.
func cxdbDir() string {
	projectDir := os.Getenv("SPRINT_LIB_PROJECT_DIR")
	if projectDir == "" {
		projectDir = "."
	}
	dir := filepath.Join(projectDir, ".clavain", "cxdb")
	os.MkdirAll(dir, 0755)
	return dir
}

// cxdbBinaryPath returns the path to the cxdb-server binary.
func cxdbBinaryPath() string {
	return filepath.Join(cxdbDir(), "cxdb-server")
}

// cxdbPIDPath returns the path to the PID file.
func cxdbPIDPath() string {
	return filepath.Join(cxdbDir(), "cxdb.pid")
}

// cxdbDataDir returns the data directory path, creating it if needed.
func cxdbDataDir() string {
	dir := filepath.Join(cxdbDir(), "data")
	os.MkdirAll(dir, 0755)
	return dir
}

// cxdbWritePID writes the server PID to the PID file.
func cxdbWritePID(pid int) error {
	return os.WriteFile(cxdbPIDPath(), []byte(strconv.Itoa(pid)), 0644)
}

// cxdbReadPID reads the server PID from the PID file.
// Returns 0 if the file doesn't exist or can't be read.
func cxdbReadPID() int {
	data, err := os.ReadFile(cxdbPIDPath())
	if err != nil {
		return 0
	}
	pid, err := strconv.Atoi(strings.TrimSpace(string(data)))
	if err != nil {
		return 0
	}
	return pid
}

// cxdbProcessAlive checks if a process with the given PID is alive.
func cxdbProcessAlive(pid int) bool {
	if pid <= 0 {
		return false
	}
	process, err := os.FindProcess(pid)
	if err != nil {
		return false
	}
	// Signal 0 checks if process exists without sending a signal
	err = process.Signal(syscall.Signal(0))
	return err == nil
}

// cxdbPIDStale returns true if the PID file exists but the process is dead.
func cxdbPIDStale() bool {
	pid := cxdbReadPID()
	if pid == 0 {
		return false
	}
	return !cxdbProcessAlive(pid)
}

// CXDBStatus is the JSON output of cxdb-status.
type CXDBStatus struct {
	Running  bool   `json:"running"`
	PID      int    `json:"pid,omitempty"`
	Port     int    `json:"port"`
	DataDir  string `json:"data_dir"`
	Version  string `json:"version,omitempty"`
	Uptime   string `json:"uptime,omitempty"`
}

// cxdbDefaultPort is the default CXDB binary protocol port.
const cxdbDefaultPort = 9009

// cxdbHTTPPort is the default CXDB HTTP API port.
const cxdbHTTPPort = 9010

// cmdCXDBStart starts the CXDB server.
// Usage: cxdb-start [--port=<port>]
func cmdCXDBStart(args []string) error {
	binPath := cxdbBinaryPath()
	if _, err := os.Stat(binPath); os.IsNotExist(err) {
		return fmt.Errorf("cxdb-server not installed at %s — run 'clavain-cli cxdb-setup' first", binPath)
	}

	// Check if already running
	pid := cxdbReadPID()
	if pid > 0 && cxdbProcessAlive(pid) {
		fmt.Fprintf(os.Stderr, "cxdb-start: already running (PID %d)\n", pid)
		return nil
	}

	// Clean up stale PID file
	if pid > 0 {
		os.Remove(cxdbPIDPath())
	}

	dataDir := cxdbDataDir()

	// Start the server
	cmd := exec.Command(binPath,
		"--data-dir", dataDir,
		"--port", strconv.Itoa(cxdbDefaultPort),
		"--http-port", strconv.Itoa(cxdbHTTPPort),
	)
	cmd.Stdout = nil
	cmd.Stderr = nil

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("cxdb-start: failed to start: %w", err)
	}

	// Write PID
	if err := cxdbWritePID(cmd.Process.Pid); err != nil {
		return fmt.Errorf("cxdb-start: failed to write PID: %w", err)
	}

	// Wait briefly for server to be ready
	time.Sleep(500 * time.Millisecond)

	// Release the process so it runs independently
	cmd.Process.Release()

	// Register type bundles
	if err := cxdbRegisterTypes(); err != nil {
		fmt.Fprintf(os.Stderr, "cxdb-start: type registration warning: %v\n", err)
	}

	fmt.Fprintf(os.Stderr, "cxdb-start: server started (PID %d, port %d)\n", cmd.Process.Pid, cxdbDefaultPort)
	return nil
}

// cxdbRegisterTypes registers the Clavain type bundle with the running CXDB server.
func cxdbRegisterTypes() error {
	// Find the types bundle
	typesPath := cxdbFindTypesBundle()
	if typesPath == "" {
		return fmt.Errorf("cxdb-types.json not found")
	}

	// Use the CXDB HTTP API to register types
	binPath := cxdbBinaryPath()
	out, err := runCommandExec(binPath, "type-register", "--bundle", typesPath,
		"--port", strconv.Itoa(cxdbHTTPPort))
	if err != nil {
		// Fallback: try direct HTTP POST if CLI subcommand not available
		fmt.Fprintf(os.Stderr, "cxdb: type-register via CLI failed (%v), types may need manual registration\n", err)
		return err
	}
	_ = out
	return nil
}

// cxdbFindTypesBundle locates the cxdb-types.json file.
func cxdbFindTypesBundle() string {
	// Check plugin root first
	pluginRoot := os.Getenv("CLAUDE_PLUGIN_ROOT")
	if pluginRoot != "" {
		p := filepath.Join(pluginRoot, "config", "cxdb-types.json")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}

	// Check source dir (dev mode)
	sourceDir := os.Getenv("CLAVAIN_SOURCE_DIR")
	if sourceDir != "" {
		p := filepath.Join(sourceDir, "config", "cxdb-types.json")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}

	// Check relative to binary
	exePath, err := os.Executable()
	if err == nil {
		p := filepath.Join(filepath.Dir(exePath), "..", "config", "cxdb-types.json")
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}

	return ""
}

// cmdCXDBStop stops the CXDB server.
// Usage: cxdb-stop
func cmdCXDBStop(args []string) error {
	pid := cxdbReadPID()
	if pid == 0 {
		fmt.Fprintf(os.Stderr, "cxdb-stop: no PID file — server not running\n")
		return nil
	}

	if !cxdbProcessAlive(pid) {
		os.Remove(cxdbPIDPath())
		fmt.Fprintf(os.Stderr, "cxdb-stop: process %d not running, cleaned up PID file\n", pid)
		return nil
	}

	// Send SIGTERM
	process, err := os.FindProcess(pid)
	if err != nil {
		os.Remove(cxdbPIDPath())
		return fmt.Errorf("cxdb-stop: cannot find process %d: %w", pid, err)
	}

	if err := process.Signal(syscall.SIGTERM); err != nil {
		os.Remove(cxdbPIDPath())
		return fmt.Errorf("cxdb-stop: failed to signal process %d: %w", pid, err)
	}

	// Wait up to 5 seconds for clean shutdown
	for i := 0; i < 10; i++ {
		time.Sleep(500 * time.Millisecond)
		if !cxdbProcessAlive(pid) {
			break
		}
	}

	// Force kill if still alive
	if cxdbProcessAlive(pid) {
		process.Signal(syscall.SIGKILL)
		time.Sleep(200 * time.Millisecond)
	}

	os.Remove(cxdbPIDPath())
	fmt.Fprintf(os.Stderr, "cxdb-stop: server stopped (was PID %d)\n", pid)
	return nil
}

// cmdCXDBStatus returns the status of the CXDB server.
// Usage: cxdb-status
func cmdCXDBStatus(args []string) error {
	pid := cxdbReadPID()
	running := pid > 0 && cxdbProcessAlive(pid)

	status := CXDBStatus{
		Running: running,
		PID:     pid,
		Port:    cxdbDefaultPort,
		DataDir: cxdbDataDir(),
	}

	if running {
		// Try to get version from the server
		binPath := cxdbBinaryPath()
		if out, err := runCommandExec(binPath, "--version"); err == nil {
			status.Version = strings.TrimSpace(string(out))
		}
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(status)
}

// cmdCXDBSetup downloads and installs the CXDB server binary.
// Usage: cxdb-setup [--version=<version>]
func cmdCXDBSetup(args []string) error {
	version := "v0.1.0"
	for _, arg := range args {
		if strings.HasPrefix(arg, "--version=") {
			version = strings.TrimPrefix(arg, "--version=")
		}
	}

	platform := cxdbPlatformTriple()
	if platform == "" {
		return fmt.Errorf("cxdb-setup: unsupported platform %s/%s", runtime.GOOS, runtime.GOARCH)
	}

	artifactName := fmt.Sprintf("cxdb-server-%s", platform)
	releaseTag := fmt.Sprintf("cxdb-%s", version)

	// Download from GitHub release using gh CLI
	destPath := cxdbBinaryPath()
	fmt.Fprintf(os.Stderr, "cxdb-setup: downloading %s from release %s...\n", artifactName, releaseTag)

	_, err := runCommandExec("gh", "release", "download", releaseTag,
		"--repo", "mistakeknot/Sylveste",
		"--pattern", artifactName,
		"--dir", cxdbDir(),
		"--clobber")
	if err != nil {
		return fmt.Errorf("cxdb-setup: download failed: %w", err)
	}

	// Rename to standard name
	downloadedPath := filepath.Join(cxdbDir(), artifactName)
	if downloadedPath != destPath {
		if err := os.Rename(downloadedPath, destPath); err != nil {
			return fmt.Errorf("cxdb-setup: rename failed: %w", err)
		}
	}

	// Make executable
	if err := os.Chmod(destPath, 0755); err != nil {
		return fmt.Errorf("cxdb-setup: chmod failed: %w", err)
	}

	// Verify binary runs
	out, err := runCommandExec(destPath, "--version")
	if err != nil {
		fmt.Fprintf(os.Stderr, "cxdb-setup: warning: binary version check failed: %v\n", err)
	} else {
		fmt.Fprintf(os.Stderr, "cxdb-setup: installed %s\n", strings.TrimSpace(string(out)))
	}

	return nil
}

// cxdbPlatformTriple returns the platform identifier for binary downloads.
func cxdbPlatformTriple() string {
	switch runtime.GOOS {
	case "linux":
		switch runtime.GOARCH {
		case "amd64":
			return "linux-x86_64"
		case "arm64":
			return "linux-aarch64"
		}
	case "darwin":
		switch runtime.GOARCH {
		case "amd64":
			return "darwin-x86_64"
		case "arm64":
			return "darwin-aarch64"
		}
	}
	return ""
}

// cxdbAvailable returns true if the CXDB server is running and healthy.
func cxdbAvailable() bool {
	pid := cxdbReadPID()
	return pid > 0 && cxdbProcessAlive(pid)
}
