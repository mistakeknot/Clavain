// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package types

import (
	"os"
	"runtime"
	"testing"
)

func TestCaptureProcessProvenance(t *testing.T) {
	p := CaptureProcessProvenance("test-service", "1.0.0")

	if p.ServiceName != "test-service" {
		t.Errorf("ServiceName = %q, want %q", p.ServiceName, "test-service")
	}
	if p.ServiceVersion != "1.0.0" {
		t.Errorf("ServiceVersion = %q, want %q", p.ServiceVersion, "1.0.0")
	}
	if p.ServiceInstanceID == "" {
		t.Error("ServiceInstanceID should not be empty")
	}
	if p.ProcessPID != os.Getpid() {
		t.Errorf("ProcessPID = %d, want %d", p.ProcessPID, os.Getpid())
	}
	if p.HostArch != runtime.GOARCH {
		t.Errorf("HostArch = %q, want %q", p.HostArch, runtime.GOARCH)
	}
	if p.CapturedAt == 0 {
		t.Error("CapturedAt should not be zero")
	}
}

func TestNewProvenance(t *testing.T) {
	base := CaptureProcessProvenance("test-service", "1.0.0")
	baseInstanceID := base.ServiceInstanceID

	// Create derived provenance
	derived := NewProvenance(base,
		WithOnBehalfOf("user123", "slack", "user@example.com"),
		WithCorrelationID("req-abc"),
	)

	// Should inherit base fields
	if derived.ServiceName != "test-service" {
		t.Errorf("ServiceName = %q, want %q", derived.ServiceName, "test-service")
	}
	if derived.ServiceInstanceID != baseInstanceID {
		t.Errorf("ServiceInstanceID changed unexpectedly")
	}

	// Should have new fields
	if derived.OnBehalfOf != "user123" {
		t.Errorf("OnBehalfOf = %q, want %q", derived.OnBehalfOf, "user123")
	}
	if derived.OnBehalfOfSource != "slack" {
		t.Errorf("OnBehalfOfSource = %q, want %q", derived.OnBehalfOfSource, "slack")
	}
	if derived.OnBehalfOfEmail != "user@example.com" {
		t.Errorf("OnBehalfOfEmail = %q, want %q", derived.OnBehalfOfEmail, "user@example.com")
	}
	if derived.CorrelationID != "req-abc" {
		t.Errorf("CorrelationID = %q, want %q", derived.CorrelationID, "req-abc")
	}

	// Should have updated timestamp (or same if within same millisecond)
	if derived.CapturedAt < base.CapturedAt {
		t.Error("CapturedAt should not be earlier in derived provenance")
	}
}

func TestWithParentContext(t *testing.T) {
	p := NewProvenance(nil, WithParentContext(100, 50))

	if p.ParentContextID == nil || *p.ParentContextID != 100 {
		t.Errorf("ParentContextID = %v, want 100", p.ParentContextID)
	}
	if p.RootContextID == nil || *p.RootContextID != 50 {
		t.Errorf("RootContextID = %v, want 50", p.RootContextID)
	}

	// Test with rootID = 0 (should default to parentID)
	p2 := NewProvenance(nil, WithParentContext(200, 0))
	if p2.RootContextID == nil || *p2.RootContextID != 200 {
		t.Errorf("RootContextID = %v, want 200 (defaulted from parentID)", p2.RootContextID)
	}
}

func TestWithTraceContext(t *testing.T) {
	traceID := "4bf92f3577b34da6a3ce929d0e0e4736"
	spanID := "00f067aa0ba902b7"

	p := NewProvenance(nil, WithTraceContext(traceID, spanID))

	if p.TraceID != traceID {
		t.Errorf("TraceID = %q, want %q", p.TraceID, traceID)
	}
	if p.SpanID != spanID {
		t.Errorf("SpanID = %q, want %q", p.SpanID, spanID)
	}
}

func TestWithWriterIdentity(t *testing.T) {
	p := NewProvenance(nil, WithWriterIdentity(
		"k8s_oidc",
		"system:serviceaccount:default:my-service",
		"https://oidc.eks.us-west-2.amazonaws.com/id/ABC123",
	))

	if p.WriterMethod != "k8s_oidc" {
		t.Errorf("WriterMethod = %q, want %q", p.WriterMethod, "k8s_oidc")
	}
	if p.WriterSubject != "system:serviceaccount:default:my-service" {
		t.Errorf("WriterSubject = %q, want expected value", p.WriterSubject)
	}
	if p.WriterIssuer != "https://oidc.eks.us-west-2.amazonaws.com/id/ABC123" {
		t.Errorf("WriterIssuer = %q, want expected value", p.WriterIssuer)
	}
}

func TestWithEnvVars(t *testing.T) {
	// Set some test env vars
	_ = os.Setenv("TEST_PROV_VAR", "test-value")
	defer func() { _ = os.Unsetenv("TEST_PROV_VAR") }()

	p := NewProvenance(nil, WithEnvVars([]string{"TEST_PROV_VAR", "NONEXISTENT_VAR"}))

	if p.EnvVars == nil {
		t.Fatal("EnvVars should not be nil")
	}
	if p.EnvVars["TEST_PROV_VAR"] != "test-value" {
		t.Errorf("EnvVars[TEST_PROV_VAR] = %q, want %q", p.EnvVars["TEST_PROV_VAR"], "test-value")
	}
	if _, exists := p.EnvVars["NONEXISTENT_VAR"]; exists {
		t.Error("NONEXISTENT_VAR should not be in EnvVars")
	}
}

func TestWithEnvVarsDefaultAllowlist(t *testing.T) {
	// Set a var from the default allowlist
	_ = os.Setenv("HOSTNAME", "test-host")
	defer func() { _ = os.Unsetenv("HOSTNAME") }()

	p := NewProvenance(nil, WithEnvVars(nil)) // nil = use default

	// Should capture HOSTNAME if set
	if p.EnvVars != nil {
		if val, exists := p.EnvVars["HOSTNAME"]; exists && val != "test-host" {
			t.Errorf("EnvVars[HOSTNAME] = %q, want %q", val, "test-host")
		}
	}
}

func TestWithSDK(t *testing.T) {
	p := NewProvenance(nil, WithSDK("ai-agents-sdk", "0.5.0"))

	if p.SDKName != "ai-agents-sdk" {
		t.Errorf("SDKName = %q, want %q", p.SDKName, "ai-agents-sdk")
	}
	if p.SDKVersion != "0.5.0" {
		t.Errorf("SDKVersion = %q, want %q", p.SDKVersion, "0.5.0")
	}
}

func TestWithSpawnReason(t *testing.T) {
	p := NewProvenance(nil, WithSpawnReason("quest"))

	if p.SpawnReason != "quest" {
		t.Errorf("SpawnReason = %q, want %q", p.SpawnReason, "quest")
	}
}

func TestProvenanceDeepCopy(t *testing.T) {
	base := NewProvenance(nil, WithEnvVars([]string{"PATH"}))
	if base.EnvVars == nil {
		// PATH might not be set in all test environments
		base.EnvVars = map[string]string{"TEST": "value"}
	}

	derived := NewProvenance(base)
	derived.EnvVars["NEW_KEY"] = "new_value"

	// Modifying derived should not affect base
	if _, exists := base.EnvVars["NEW_KEY"]; exists {
		t.Error("Modifying derived EnvVars should not affect base")
	}
}

func TestCombinedOptions(t *testing.T) {
	base := CaptureProcessProvenance("my-service", "1.0.0",
		WithSDK("cxdb-go", "0.1.0"),
		WithEnvVars(nil), // use default
	)

	p := NewProvenance(base,
		WithParentContext(100, 50),
		WithSpawnReason("quest"),
		WithOnBehalfOf("user@example.com", "slack", "user@example.com"),
		WithTraceContext("abc123", "def456"),
		WithCorrelationID("req-789"),
		WithWriterIdentity("k8s_oidc", "sa:default:worker", "https://oidc.example.com"),
	)

	// Check everything is set
	if p.ServiceName != "my-service" {
		t.Error("ServiceName not inherited")
	}
	if p.SDKName != "cxdb-go" {
		t.Error("SDKName not inherited")
	}
	if p.ParentContextID == nil || *p.ParentContextID != 100 {
		t.Error("ParentContextID not set")
	}
	if p.SpawnReason != "quest" {
		t.Error("SpawnReason not set")
	}
	if p.OnBehalfOf != "user@example.com" {
		t.Error("OnBehalfOf not set")
	}
	if p.TraceID != "abc123" {
		t.Error("TraceID not set")
	}
	if p.CorrelationID != "req-789" {
		t.Error("CorrelationID not set")
	}
	if p.WriterMethod != "k8s_oidc" {
		t.Error("WriterMethod not set")
	}
}
