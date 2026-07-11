package main

import (
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/mistakeknot/intercore/pkg/runtimeproof"
)

func TestRuntimeEvidenceBindSealsRequirementBeforeMarker(t *testing.T) {
	var calls []string
	ops := runtimeEvidenceOps{
		labels: func(string) ([]string, error) { return []string{runtimeEvidenceLabel}, nil },
		state:  func(string, string) (string, error) { return "", nil },
		setState: func(_, key, value string) error {
			calls = append(calls, "state:"+key+"="+value)
			return nil
		},
		resolveRun: func(string) (string, error) { return "run-1", nil },
		loadRun: func(string) (Run, error) {
			return Run{ID: "run-1", ProjectDir: "/tmp/project"}, nil
		},
		mergeRunMetadata: func(runID, patch string) error {
			calls = append(calls, "merge:"+runID+":"+patch)
			var metadata runtimeRunMetadata
			if err := decodeStrictJSON([]byte(patch), &metadata); err != nil {
				t.Fatalf("invalid metadata patch: %v", err)
			}
			if metadata.CloseGate == nil || metadata.CloseGate.BeadID != "iv-1" || !containsString(metadata.CloseGate.Requirements, runtimeEvidenceArtifactType) {
				t.Fatalf("wrong close gate patch: %s", patch)
			}
			return nil
		},
	}

	if err := bindRuntimeEvidence(ops, "iv-1"); err != nil {
		t.Fatal(err)
	}
	if len(calls) != 2 || !strings.HasPrefix(calls[0], "merge:") || calls[1] != "state:runtime_evidence_required=1" {
		t.Fatalf("calls = %#v, want metadata then durable marker", calls)
	}
}

func TestRuntimeEvidenceBindSurvivesLabelRemovalAndRejectsMissingRun(t *testing.T) {
	sealed := `{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"iv-1"}}`
	markerWrites := 0
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return nil, nil },
		state:      func(string, string) (string, error) { return "1", nil },
		setState:   func(string, string, string) error { markerWrites++; return nil },
		resolveRun: func(string) (string, error) { return "run-1", nil },
		loadRun:    func(string) (Run, error) { return Run{ID: "run-1", Metadata: sealed}, nil },
		mergeRunMetadata: func(string, string) error {
			t.Fatal("already sealed run must not be rebound")
			return nil
		},
	}
	if err := bindRuntimeEvidence(ops, "iv-1"); err != nil {
		t.Fatal(err)
	}
	if markerWrites != 1 {
		t.Fatalf("marker writes = %d, want 1", markerWrites)
	}

	ops.resolveRun = func(string) (string, error) { return "", errors.New("no run") }
	if err := bindRuntimeEvidence(ops, "iv-2"); err == nil || !strings.Contains(err.Error(), "runtime-evidence adopt") {
		t.Fatalf("missing-run error = %v", err)
	}
}

func TestRuntimeEvidenceBindRequiresExplicitLabelOnFirstActivation(t *testing.T) {
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return nil, nil },
		state:      func(string, string) (string, error) { return "", nil },
		setState:   func(string, string, string) error { return nil },
		resolveRun: func(string) (string, error) { return "run-1", nil },
		loadRun:    func(string) (Run, error) { return Run{ID: "run-1"}, nil },
		mergeRunMetadata: func(string, string) error {
			t.Fatal("unlabelled run must not be mutated")
			return nil
		},
	}
	if err := bindRuntimeEvidence(ops, "iv-1"); err == nil || !strings.Contains(err.Error(), runtimeEvidenceLabel) {
		t.Fatalf("error = %v", err)
	}
}

func TestRuntimeEvidenceLabelsFromBDJSON(t *testing.T) {
	for _, raw := range []string{
		`[{"id":"iv-1","labels":["close-gate:runtime-evidence","P1"]}]`,
		`{"id":"iv-1","labels":["close-gate:runtime-evidence","P1"]}`,
	} {
		labels, err := runtimeEvidenceLabelsFromBDJSON([]byte(raw))
		if err != nil {
			t.Fatal(err)
		}
		if !containsString(labels, runtimeEvidenceLabel) {
			t.Fatalf("labels = %#v", labels)
		}
	}
	if _, err := runtimeEvidenceLabelsFromBDJSON([]byte(`{"labels":"wrong"}`)); err == nil {
		t.Fatal("malformed labels must fail closed")
	}
}

func TestInspectRuntimeEvidenceRequirementDetectsUnboundDurableState(t *testing.T) {
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return nil, nil },
		state:      func(string, string) (string, error) { return "1", nil },
		resolveRun: func(string) (string, error) { return "run-1", nil },
		loadRun:    func(string) (Run, error) { return Run{ID: "run-1"}, nil },
	}
	status, err := inspectRuntimeEvidenceRequirement(ops, "iv-1")
	if err != nil {
		t.Fatal(err)
	}
	if !status.Required || status.Bound || status.RunID != "run-1" {
		t.Fatalf("status = %+v", status)
	}
}

func TestRuntimeEvidenceCommandRejectsUnknownSubcommand(t *testing.T) {
	if err := cmdRuntimeEvidence([]string{"unknown"}); err == nil || !strings.Contains(err.Error(), "unknown subcommand") {
		t.Fatalf("error = %v", err)
	}
}

func TestRuntimeEvidenceAdoptCreatesMinimalRunAndPersistsIdentity(t *testing.T) {
	var created runtimeAdoptCreate
	var stateWrites []string
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return []string{runtimeEvidenceLabel}, nil },
		state:      func(string, string) (string, error) { return "", nil },
		resolveRun: func(string) (string, error) { return "", errors.New("no run") },
		findScopeRuns: func(string) ([]Run, error) {
			return nil, nil
		},
		validateAdoption: func(projectRoot, path string) (json.RawMessage, error) {
			if projectRoot != "/tmp/project" || path != "/tmp/provenance.json" {
				t.Fatalf("validation args = %q %q", projectRoot, path)
			}
			return json.RawMessage(`{"schema_version":1,"verified":true}`), nil
		},
		createRun: func(spec runtimeAdoptCreate) (string, error) {
			created = spec
			return "run-adopted", nil
		},
		loadRun: func(runID string) (Run, error) {
			return Run{ID: runID, ProjectDir: "/tmp/project", Phase: "reflect", Metadata: created.Metadata}, nil
		},
		setState: func(_ string, key, value string) error {
			stateWrites = append(stateWrites, key+"="+value)
			return nil
		},
	}

	runID, err := adoptRuntimeEvidence(ops, "iv-1", "/tmp/project", "/tmp/provenance.json")
	if err != nil {
		t.Fatal(err)
	}
	if runID != "run-adopted" {
		t.Fatalf("run ID = %q", runID)
	}
	if strings.Join(created.Phases, ",") != "reflect,done" || created.ScopeID != "iv-1" {
		t.Fatalf("create spec = %+v", created)
	}
	metadata, bound, err := runtimeEvidenceMetadataState("iv-1", created.Metadata)
	if err != nil || !bound || len(metadata.CloseGate.Adoption) == 0 {
		t.Fatalf("metadata = %+v, bound=%v, err=%v", metadata, bound, err)
	}
	wantWrites := []string{"ic_run_id=run-adopted", "phase=reflect", "runtime_evidence_required=1"}
	if strings.Join(stateWrites, ",") != strings.Join(wantWrites, ",") {
		t.Fatalf("state writes = %#v, want %#v", stateWrites, wantWrites)
	}
}

func TestRuntimeEvidenceAdoptRetryRepairsStateWithoutDuplicateRun(t *testing.T) {
	metadata := `{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"iv-1","adoption":{"schema_version":1}}}`
	createCalls := 0
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return nil, nil },
		state:      func(string, string) (string, error) { return "1", nil },
		resolveRun: func(string) (string, error) { return "", errors.New("state write was lost") },
		findScopeRuns: func(string) ([]Run, error) {
			return []Run{{ID: "run-existing", Status: "active", Phase: "reflect", ProjectDir: "/tmp/project", Metadata: metadata}}, nil
		},
		validateAdoption: func(string, string) (json.RawMessage, error) {
			return json.RawMessage(`{"schema_version":1}`), nil
		},
		createRun: func(runtimeAdoptCreate) (string, error) {
			createCalls++
			return "", nil
		},
		setState: func(string, string, string) error { return nil },
	}
	runID, err := adoptRuntimeEvidence(ops, "iv-1", "/tmp/project", "/tmp/provenance.json")
	if err != nil {
		t.Fatal(err)
	}
	if runID != "run-existing" || createCalls != 0 {
		t.Fatalf("run=%q createCalls=%d", runID, createCalls)
	}
}

func TestRuntimeEvidenceAdoptRejectsExistingUnboundRun(t *testing.T) {
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return []string{runtimeEvidenceLabel}, nil },
		state:      func(string, string) (string, error) { return "", nil },
		resolveRun: func(string) (string, error) { return "run-ordinary", nil },
		loadRun:    func(string) (Run, error) { return Run{ID: "run-ordinary"}, nil },
	}
	if _, err := adoptRuntimeEvidence(ops, "iv-1", "/tmp/project", "/tmp/provenance.json"); err == nil || !strings.Contains(err.Error(), "runtime-evidence bind") {
		t.Fatalf("error = %v", err)
	}
}

func TestValidateRuntimeAdoptionProvenance(t *testing.T) {
	planRepo, planHead := initRuntimeEvidenceGitRepo(t, "docs/plan.md", "approved plan\n")
	projectRepo, projectHead := initRuntimeEvidenceGitRepo(t, "README.md", "project\n")
	planBytes, err := os.ReadFile(filepath.Join(planRepo, "docs", "plan.md"))
	if err != nil {
		t.Fatal(err)
	}
	provenance := runtimeAdoptionProvenanceFile{
		SchemaVersion: 1,
		Plan: runtimeAdoptionPlan{
			Repository: planRepo,
			Path:       "docs/plan.md",
			Digest:     digestForRuntimeEvidence(planBytes),
			Head:       planHead,
		},
		Sources: []runtimeAdoptionSource{{Repository: projectRepo, Head: projectHead}},
	}
	path := writeRuntimeAdoptionFile(t, provenance)
	validated, err := validateRuntimeAdoptionProvenance(projectRepo, path)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(validated), projectHead) || !strings.Contains(string(validated), planHead) {
		t.Fatalf("validated provenance lost heads: %s", validated)
	}

	t.Run("plan digest mismatch", func(t *testing.T) {
		bad := provenance
		bad.Plan.Digest = digestForRuntimeEvidence([]byte("wrong"))
		_, err := validateRuntimeAdoptionProvenance(projectRepo, writeRuntimeAdoptionFile(t, bad))
		if err == nil || !strings.Contains(err.Error(), "digest") {
			t.Fatalf("error = %v", err)
		}
	})
	t.Run("source head mismatch", func(t *testing.T) {
		bad := provenance
		bad.Sources = append([]runtimeAdoptionSource(nil), provenance.Sources...)
		bad.Sources[0].Head = strings.Repeat("f", 40)
		_, err := validateRuntimeAdoptionProvenance(projectRepo, writeRuntimeAdoptionFile(t, bad))
		if err == nil || !strings.Contains(err.Error(), "HEAD") {
			t.Fatalf("error = %v", err)
		}
	})
	t.Run("project source missing", func(t *testing.T) {
		bad := provenance
		bad.Sources = []runtimeAdoptionSource{{Repository: planRepo, Head: planHead}}
		_, err := validateRuntimeAdoptionProvenance(projectRepo, writeRuntimeAdoptionFile(t, bad))
		if err == nil || !strings.Contains(err.Error(), "project repository") {
			t.Fatalf("error = %v", err)
		}
	})
	t.Run("untracked plan", func(t *testing.T) {
		untracked := filepath.Join(planRepo, "docs", "untracked.md")
		if err := os.WriteFile(untracked, []byte("not committed\n"), 0o600); err != nil {
			t.Fatal(err)
		}
		bad := provenance
		bad.Plan.Path = "docs/untracked.md"
		bad.Plan.Digest = digestForRuntimeEvidence([]byte("not committed\n"))
		_, err := validateRuntimeAdoptionProvenance(projectRepo, writeRuntimeAdoptionFile(t, bad))
		if err == nil || !strings.Contains(err.Error(), "tracked") {
			t.Fatalf("error = %v", err)
		}
	})
}

func initRuntimeEvidenceGitRepo(t *testing.T, path, content string) (string, string) {
	t.Helper()
	repo := t.TempDir()
	runRuntimeEvidenceGit(t, repo, "init", "-q")
	runRuntimeEvidenceGit(t, repo, "config", "user.email", "runtime-evidence@example.invalid")
	runRuntimeEvidenceGit(t, repo, "config", "user.name", "Runtime Evidence Test")
	abs := filepath.Join(repo, filepath.FromSlash(path))
	if err := os.MkdirAll(filepath.Dir(abs), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(abs, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	runRuntimeEvidenceGit(t, repo, "add", "--", path)
	runRuntimeEvidenceGit(t, repo, "commit", "-q", "-m", "fixture")
	head := strings.TrimSpace(runRuntimeEvidenceGit(t, repo, "rev-parse", "HEAD"))
	return repo, head
}

func runRuntimeEvidenceGit(t *testing.T, repo string, args ...string) string {
	t.Helper()
	cmdArgs := append([]string{"-C", repo}, args...)
	out, err := exec.Command("git", cmdArgs...).CombinedOutput()
	if err != nil {
		t.Fatalf("git %s: %v\n%s", strings.Join(cmdArgs, " "), err, out)
	}
	return string(out)
}

func writeRuntimeAdoptionFile(t *testing.T, value runtimeAdoptionProvenanceFile) string {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "provenance.json")
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

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
