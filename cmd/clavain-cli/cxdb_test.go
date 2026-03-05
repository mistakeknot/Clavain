package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestCXDBPlatformTriple(t *testing.T) {
	triple := cxdbPlatformTriple()
	if triple == "" {
		t.Skipf("unsupported test platform %s/%s", runtime.GOOS, runtime.GOARCH)
	}

	// Should contain OS and arch
	switch runtime.GOOS {
	case "linux":
		if triple != "linux-x86_64" && triple != "linux-aarch64" {
			t.Errorf("unexpected triple for linux: %s", triple)
		}
	case "darwin":
		if triple != "darwin-x86_64" && triple != "darwin-aarch64" {
			t.Errorf("unexpected triple for darwin: %s", triple)
		}
	}
}

func TestCXDBPIDManagement(t *testing.T) {
	// Use temp dir to avoid interfering with real state
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// Create .clavain/cxdb directory
	cxdbPath := filepath.Join(tmpDir, ".clavain", "cxdb")
	os.MkdirAll(cxdbPath, 0755)

	// No PID file → read returns 0
	pid := cxdbReadPID()
	if pid != 0 {
		t.Errorf("expected 0 for missing PID file, got %d", pid)
	}

	// Write PID
	if err := cxdbWritePID(12345); err != nil {
		t.Fatalf("cxdbWritePID failed: %v", err)
	}

	// Read PID back
	pid = cxdbReadPID()
	if pid != 12345 {
		t.Errorf("expected PID 12345, got %d", pid)
	}

	// Stale check — PID 12345 is almost certainly not alive
	if cxdbProcessAlive(12345) {
		t.Skip("PID 12345 is somehow alive, skipping stale check")
	}
	if !cxdbPIDStale() {
		t.Error("expected PID to be stale")
	}

	// Process alive — PID 0 should be false
	if cxdbProcessAlive(0) {
		t.Error("PID 0 should not be alive")
	}
	if cxdbProcessAlive(-1) {
		t.Error("PID -1 should not be alive")
	}

	// Current process should be alive
	if !cxdbProcessAlive(os.Getpid()) {
		t.Error("current process should be alive")
	}
}

func TestCXDBStatusJSON(t *testing.T) {
	status := CXDBStatus{
		Running: true,
		PID:     42,
		Port:    9009,
		DataDir: "/tmp/test/data",
		Version: "0.1.0",
	}

	data, err := json.Marshal(status)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}

	var decoded CXDBStatus
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if decoded.Running != true {
		t.Error("expected Running=true")
	}
	if decoded.PID != 42 {
		t.Errorf("expected PID=42, got %d", decoded.PID)
	}
	if decoded.Port != 9009 {
		t.Errorf("expected Port=9009, got %d", decoded.Port)
	}
}

func TestCXDBTypeBundleParsing(t *testing.T) {
	// Read the actual type bundle file
	bundlePath := filepath.Join("..", "..", "config", "cxdb-types.json")
	data, err := os.ReadFile(bundlePath)
	if err != nil {
		t.Skipf("cxdb-types.json not found at %s: %v", bundlePath, err)
	}

	var bundle struct {
		BundleVersion int `json:"bundle_version"`
		Types         map[string]struct {
			Description string `json:"description"`
			Fields      map[string]struct {
				Type     string `json:"type"`
				Tag      int    `json:"tag"`
				Required bool   `json:"required,omitempty"`
			} `json:"fields"`
		} `json:"types"`
	}

	if err := json.Unmarshal(data, &bundle); err != nil {
		t.Fatalf("parse failed: %v", err)
	}

	if bundle.BundleVersion != 1 {
		t.Errorf("expected bundle_version=1, got %d", bundle.BundleVersion)
	}

	expectedTypes := []string{
		"clavain.phase.v1",
		"clavain.dispatch.v1",
		"clavain.artifact.v1",
		"clavain.scenario.v1",
		"clavain.satisfaction.v1",
		"clavain.evidence.v1",
		"clavain.policy_violation.v1",
	}

	if len(bundle.Types) != len(expectedTypes) {
		t.Errorf("expected %d types, got %d", len(expectedTypes), len(bundle.Types))
	}

	for _, name := range expectedTypes {
		typ, ok := bundle.Types[name]
		if !ok {
			t.Errorf("missing type: %s", name)
			continue
		}
		if len(typ.Fields) == 0 {
			t.Errorf("type %s has no fields", name)
		}
		if typ.Description == "" {
			t.Errorf("type %s has no description", name)
		}
		// Check all fields have tags
		for fieldName, field := range typ.Fields {
			if field.Tag == 0 {
				t.Errorf("type %s field %s has tag=0", name, fieldName)
			}
			if field.Type == "" {
				t.Errorf("type %s field %s has no type", name, fieldName)
			}
		}
	}
}

func TestCXDBAvailable_NoServer(t *testing.T) {
	// With no server running, should return false
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	if cxdbAvailable() {
		t.Error("expected cxdbAvailable=false with no server")
	}
}

func TestCXDBDir(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	dir := cxdbDir()
	expected := filepath.Join(tmpDir, ".clavain", "cxdb")
	if dir != expected {
		t.Errorf("expected %s, got %s", expected, dir)
	}

	// Directory should be created
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		t.Error("cxdbDir should create the directory")
	}
}
