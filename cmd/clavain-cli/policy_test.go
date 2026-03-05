package main

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/vmihailenco/msgpack/v5"
)

func TestDefaultPolicyHoldoutDenied(t *testing.T) {
	policy := defaultPolicy()

	// Build phases should deny holdout
	for _, phase := range []string{"brainstorm", "strategized", "planned", "executing", "reflect"} {
		result := evaluatePolicy(policy, phase, "read", ".clavain/scenarios/holdout/test.yaml")
		if result.Allowed {
			t.Errorf("phase %s should deny holdout path", phase)
		}
	}
}

func TestDefaultPolicyShippingAllowed(t *testing.T) {
	policy := defaultPolicy()

	// Shipping phase should allow holdout
	result := evaluatePolicy(policy, "shipping", "read", ".clavain/scenarios/holdout/test.yaml")
	if !result.Allowed {
		t.Errorf("shipping phase should allow holdout path: %s", result.Reason)
	}
}

func TestDefaultPolicyDevAllowed(t *testing.T) {
	policy := defaultPolicy()

	// Dev scenarios should always be allowed
	for _, phase := range []string{"brainstorm", "executing", "shipping"} {
		result := evaluatePolicy(policy, phase, "read", ".clavain/scenarios/dev/test.yaml")
		if !result.Allowed {
			t.Errorf("phase %s should allow dev path: %s", phase, result.Reason)
		}
	}
}

func TestPolicyUnknownPhase(t *testing.T) {
	policy := defaultPolicy()

	result := evaluatePolicy(policy, "unknown-phase", "read", ".clavain/scenarios/holdout/test.yaml")
	if !result.Allowed {
		t.Error("unknown phase should default to allowed")
	}
}

func TestMatchGlob(t *testing.T) {
	tests := []struct {
		pattern string
		path    string
		want    bool
	}{
		{"**", "anything", true},
		{".clavain/scenarios/holdout/**", ".clavain/scenarios/holdout/test.yaml", true},
		{".clavain/scenarios/holdout/**", ".clavain/scenarios/dev/test.yaml", false},
		{"*.yaml", "test.yaml", true},
		{"*.yaml", "test.json", false},
	}

	for _, tt := range tests {
		got := matchGlob(tt.pattern, tt.path)
		if got != tt.want {
			t.Errorf("matchGlob(%q, %q) = %v, want %v", tt.pattern, tt.path, got, tt.want)
		}
	}
}

func TestIsHoldoutPath(t *testing.T) {
	if !isHoldoutPath(".clavain/scenarios/holdout/test.yaml") {
		t.Error("should detect holdout path")
	}
	if !isHoldoutPath("holdout/test.yaml") {
		t.Error("should detect holdout prefix")
	}
	if isHoldoutPath(".clavain/scenarios/dev/test.yaml") {
		t.Error("should not detect dev path as holdout")
	}
}

func TestPolicyViolationRecordMsgpack(t *testing.T) {
	rec := PolicyViolationRecord{
		BeadID:     "iv-test",
		AgentName:  "build-agent",
		Phase:      "executing",
		Action:     "read",
		TargetPath: ".clavain/scenarios/holdout/test.yaml",
		PolicyRule: "deny_paths",
		Timestamp:  1709654400,
	}

	data, err := msgpack.Marshal(rec)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded PolicyViolationRecord
	if err := msgpack.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.AgentName != "build-agent" {
		t.Errorf("AgentName: got %q", decoded.AgentName)
	}
	if decoded.TargetPath != rec.TargetPath {
		t.Errorf("TargetPath mismatch")
	}
}

func TestLoadPolicyFromFile(t *testing.T) {
	tmpDir := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmpDir)

	// Create custom policy
	policyDir := filepath.Join(tmpDir, ".clavain")
	os.MkdirAll(policyDir, 0755)

	content := `schema_version: 1
phases:
  executing:
    deny_paths:
      - ".clavain/scenarios/holdout/**"
      - "secrets/**"
    deny_tools:
      - "rm"
`
	os.WriteFile(filepath.Join(policyDir, "policy.yml"), []byte(content), 0644)

	policy, err := loadPolicy()
	if err != nil {
		t.Fatalf("loadPolicy: %v", err)
	}

	if policy.SchemaVersion != 1 {
		t.Errorf("schema_version: got %d", policy.SchemaVersion)
	}

	pp := policy.Phases["executing"]
	if len(pp.DenyPaths) != 2 {
		t.Errorf("deny_paths: got %d, want 2", len(pp.DenyPaths))
	}
	if len(pp.DenyTools) != 1 {
		t.Errorf("deny_tools: got %d, want 1", len(pp.DenyTools))
	}

	// Test custom deny
	result := evaluatePolicy(policy, "executing", "read", "secrets/api-key.txt")
	if result.Allowed {
		t.Error("should deny secrets path")
	}

	result = evaluatePolicy(policy, "executing", "rm", "/tmp/test")
	if result.Allowed {
		t.Error("should deny rm tool")
	}
}

func TestGetCurrentPhase_Env(t *testing.T) {
	t.Setenv("CLAVAIN_PHASE", "shipping")
	phase := getCurrentPhase("")
	if phase != "shipping" {
		t.Errorf("got %q, want 'shipping'", phase)
	}
}

func TestGetCurrentPhase_Default(t *testing.T) {
	t.Setenv("CLAVAIN_PHASE", "")
	phase := getCurrentPhase("")
	if phase != "executing" {
		t.Errorf("got %q, want 'executing' (default)", phase)
	}
}
