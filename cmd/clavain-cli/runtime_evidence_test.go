package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/mistakeknot/intercore/pkg/runtimeproof"
)

func TestRuntimeEvidenceRequiredStateIsMonotonic(t *testing.T) {
	tests := []struct {
		name     string
		labelled bool
		marker   bool
		metadata string
		want     bool
		wantErr  string
	}{
		{name: "ordinary bead", want: false},
		{name: "current label", labelled: true, want: true},
		{name: "durable marker survives label removal", marker: true, want: true},
		{
			name:     "sealed run survives label removal",
			metadata: `{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"iv-1"}}`,
			want:     true,
		},
		{
			name:     "malformed close gate fails closed",
			metadata: `{"close_gate":{"requirements":"runtime-evidence/v1"}}`,
			wantErr:  "requirements",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := runtimeEvidenceRequiredState("iv-1", tt.labelled, tt.marker, tt.metadata)
			if tt.wantErr != "" {
				if err == nil || !strings.Contains(err.Error(), tt.wantErr) {
					t.Fatalf("error = %v, want substring %q", err, tt.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if got != tt.want {
				t.Fatalf("required = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestResolveRuntimeEvidenceConfigUsesTrustedPlatformPaths(t *testing.T) {
	root := t.TempDir()
	buildRel := filepath.Join("build", "fixture")
	if err := os.MkdirAll(filepath.Dir(filepath.Join(root, buildRel)), 0o755); err != nil {
		t.Fatal(err)
	}
	install := filepath.Join(t.TempDir(), "installed-fixture")
	platform := runtime.GOOS + "-" + runtime.GOARCH
	cfg := runtimeEvidenceConfigFile{
		SchemaVersion:  1,
		BuildPath:      buildRel,
		InstalledPaths: map[string]string{platform: install},
		StartArgv:      []string{"{installed_path}", "--serve"},
		ProbeArgv:      []string{"{project_root}/tools/probe"},
		TimeoutSeconds: 7,
		RequiredSubsystems: []string{
			"store",
		},
		NotApplicableFailureClasses: []string{"dependency_injection", "projection_catchup"},
		RequiredAssertions:          []string{"state-delta"},
		ExpectedSurfaces:            []string{"http-api"},
		RequiredResources: []runtimeproof.ResourceExpectation{
			{Kind: "port", Ownership: "ephemeral"},
		},
	}

	resolved, err := resolveRuntimeEvidenceConfig(root, cfg)
	if err != nil {
		t.Fatal(err)
	}
	if resolved.BuildPath != filepath.Join(root, buildRel) {
		t.Fatalf("build path = %q", resolved.BuildPath)
	}
	if resolved.InstalledPath != install {
		t.Fatalf("installed path = %q", resolved.InstalledPath)
	}
	if resolved.StartArgv[0] != install {
		t.Fatalf("start executable = %q", resolved.StartArgv[0])
	}
	if resolved.ProbeArgv[0] != filepath.Join(root, "tools", "probe") {
		t.Fatalf("probe executable = %q", resolved.ProbeArgv[0])
	}
	if resolved.Expectations.ExpectedBuildPath != resolved.BuildPath || resolved.Expectations.ExpectedInstalledPath != install {
		t.Fatalf("trusted paths not carried into expectations: %+v", resolved.Expectations)
	}
}

func TestResolveRuntimeEvidenceConfigRejectsUntrustedInputs(t *testing.T) {
	root := t.TempDir()
	platform := runtime.GOOS + "-" + runtime.GOARCH
	base := runtimeEvidenceConfigFile{
		SchemaVersion:               1,
		BuildPath:                   "build/fixture",
		InstalledPaths:              map[string]string{platform: filepath.Join(t.TempDir(), "fixture")},
		StartArgv:                   []string{"{installed_path}"},
		ProbeArgv:                   []string{"{project_root}/probe"},
		TimeoutSeconds:              5,
		RequiredSubsystems:          []string{"store"},
		RequiredAssertions:          []string{"state-delta"},
		ExpectedSurfaces:            []string{"http-api"},
		RequiredResources:           []runtimeproof.ResourceExpectation{{Kind: "port", Ownership: "ephemeral"}},
		NotApplicableFailureClasses: []string{"dependency_injection"},
	}

	tests := []struct {
		name    string
		mutate  func(*runtimeEvidenceConfigFile)
		wantErr string
	}{
		{"absolute build path", func(c *runtimeEvidenceConfigFile) { c.BuildPath = filepath.Join(root, "fixture") }, "project-relative"},
		{"parent build path", func(c *runtimeEvidenceConfigFile) { c.BuildPath = "../fixture" }, "project root"},
		{"environment expansion", func(c *runtimeEvidenceConfigFile) { c.ProbeArgv = []string{"$HOME/probe"} }, "unsupported token"},
		{"wrong start executable", func(c *runtimeEvidenceConfigFile) { c.StartArgv[0] = "/tmp/not-installed" }, "installed path"},
		{"database resource", func(c *runtimeEvidenceConfigFile) { c.RequiredResources[0].Kind = "database" }, "unverifiable"},
		{"shared resource", func(c *runtimeEvidenceConfigFile) { c.RequiredResources[0].Ownership = "shared" }, "not isolated"},
		{"missing platform", func(c *runtimeEvidenceConfigFile) { c.InstalledPaths = map[string]string{"other-platform": "/tmp/x"} }, platform},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cfg := base
			cfg.InstalledPaths = cloneStringMap(base.InstalledPaths)
			cfg.StartArgv = append([]string(nil), base.StartArgv...)
			cfg.ProbeArgv = append([]string(nil), base.ProbeArgv...)
			cfg.RequiredResources = append([]runtimeproof.ResourceExpectation(nil), base.RequiredResources...)
			tt.mutate(&cfg)
			_, err := resolveRuntimeEvidenceConfig(root, cfg)
			if err == nil || !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("error = %v, want substring %q", err, tt.wantErr)
			}
		})
	}
}

func TestBuildRuntimeEvidenceReceiptKeepsExpectationsOutOfProbeControl(t *testing.T) {
	expectations := runtimeproof.Expectations{
		ExpectedBuildPath:           "/tmp/build",
		ExpectedInstalledPath:       "/tmp/install",
		RequiredSubsystems:          []string{"store"},
		NotApplicableFailureClasses: map[string]bool{"dependency_injection": true, "projection_catchup": true},
		RequiredAssertions:          []string{"state-delta"},
		ExpectedSurfaces:            []string{"http-api"},
		RequiredResources:           []runtimeproof.ResourceExpectation{{Kind: "port", Ownership: "ephemeral"}},
	}
	obs := runtimeProbeObservations{
		SchemaVersion: 1,
		ObservedNonce: "nonce",
		Subsystems:    map[string]string{"store": "healthy"},
		FailureClasses: map[string]runtimeObservedFailure{
			"startup":              {State: runtimeproof.StateVerified, Evidence: "process stayed alive"},
			"dependency_injection": {State: runtimeproof.StateNotApplicable, Evidence: "standalone fixture"},
			"connection":           {State: runtimeproof.StateVerified, Evidence: "loopback request succeeded"},
			"projection_catchup":   {State: runtimeproof.StateNotApplicable, Evidence: "no projection"},
		},
		ObservedEventID:  "event",
		BeforeDigest:     digestForRuntimeEvidence([]byte("before")),
		AfterDigest:      digestForRuntimeEvidence([]byte("after")),
		Assertions:       []runtimeproof.Assertion{{Name: "state-delta", State: runtimeproof.StateVerified, Evidence: "changed"}},
		ObservedSurfaces: []string{"http-api"},
		Resources:        []runtimeObservedResource{{Kind: "port", Identifier: "127.0.0.1:43123"}},
		Collisions:       []string{},
	}
	input := runtimeReceiptInput{
		BeadID: "iv-1", RunID: "run-1", ProjectRoot: "/tmp/project", GitHead: strings.Repeat("a", 40), Host: "host",
		BuildDigest: digestForRuntimeEvidence([]byte("binary")), InstalledDigest: digestForRuntimeEvidence([]byte("binary")),
		ProcessID: 42, InstanceNonce: "nonce", EventID: "event", Expectations: expectations,
	}

	receipt, err := buildRuntimeEvidenceReceipt(input, obs)
	if err != nil {
		t.Fatal(err)
	}
	if receipt.Health.RequiredSubsystems[0] != "store" || receipt.SurfaceScan.Expected[0] != "http-api" {
		t.Fatalf("receipt did not use trusted expectations: %+v", receipt)
	}
	if receipt.Isolation.Resources[0].Ownership != "ephemeral" {
		t.Fatalf("probe controlled ownership: %+v", receipt.Isolation.Resources[0])
	}
	if strings.Contains(receipt.Isolation.Resources[0].Fingerprint, "43123") {
		t.Fatal("receipt leaked raw resource identifier")
	}
	b, err := json.Marshal(receipt)
	if err != nil || strings.Contains(string(b), "127.0.0.1:43123") {
		t.Fatalf("receipt leaked resource identifier: %s (err=%v)", b, err)
	}
}

func cloneStringMap(in map[string]string) map[string]string {
	out := make(map[string]string, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}
