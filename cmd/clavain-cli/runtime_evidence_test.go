package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

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

	ops.resolveRun = func(string) (string, error) { return "", errRuntimeRunNotBound }
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

func TestValidateRuntimeEvidenceBindingNeverAdoptsImplicitly(t *testing.T) {
	tests := []struct {
		name    string
		labels  []string
		marker  string
		runID   string
		run     Run
		wantErr string
	}{
		{name: "ordinary bead"},
		{name: "labelled without run", labels: []string{runtimeEvidenceLabel}, wantErr: "runtime-evidence adopt"},
		{name: "durable marker without run", marker: "1", wantErr: "runtime-evidence adopt"},
		{name: "labelled unbound run", labels: []string{runtimeEvidenceLabel}, runID: "run-1", run: Run{ID: "run-1"}, wantErr: "runtime-evidence bind"},
		{name: "bound after label removal", marker: "1", runID: "run-1", run: Run{ID: "run-1", Metadata: `{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"iv-1"}}`}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ops := runtimeEvidenceOps{
				labels: func(string) ([]string, error) { return tt.labels, nil },
				state:  func(string, string) (string, error) { return tt.marker, nil },
				resolveRun: func(string) (string, error) {
					if tt.runID == "" {
						return "", errRuntimeRunNotBound
					}
					return tt.runID, nil
				},
				loadRun: func(string) (Run, error) { return tt.run, nil },
			}
			err := validateRuntimeEvidenceBinding(ops, "iv-1")
			if tt.wantErr == "" {
				if err != nil {
					t.Fatal(err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("error = %v, want substring %q", err, tt.wantErr)
			}
		})
	}
}

func TestParseSprintCreateRuntimeEvidenceOption(t *testing.T) {
	parsed := parseSprintCreateArgs([]string{"Runtime proof", "4", "core", "--runtime-evidence"})
	if parsed.Title != "Runtime proof" || parsed.Complexity != 4 || parsed.Lane != "core" || !parsed.RuntimeEvidence {
		t.Fatalf("parsed = %+v", parsed)
	}
	metadata, err := runtimeEvidenceMetadataForBead("iv-1")
	if err != nil {
		t.Fatal(err)
	}
	_, bound, err := runtimeEvidenceMetadataState("iv-1", metadata)
	if err != nil || !bound {
		t.Fatalf("metadata = %s, bound=%v, err=%v", metadata, bound, err)
	}
}

func TestSprintCreateRuntimeEvidenceIsRequiredInInitialRunRow(t *testing.T) {
	root := t.TempDir()
	binDir := filepath.Join(root, "bin")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		t.Fatal(err)
	}
	logPath := filepath.Join(root, "calls.log")
	bdScript := `#!/bin/sh
set -eu
printf 'bd:%s\n' "$*" >>"$RUNTIME_CREATE_LOG"
if [ "${1:-}" = create ]; then
  printf 'Created issue iv-new\n'
fi
`
	icScript := `#!/bin/sh
set -eu
printf 'ic:%s\n' "$*" >>"$RUNTIME_CREATE_LOG"
if [ "${1:-}" = health ]; then exit 0; fi
if [ "${1:-}" = run ] && [ "${2:-}" = create ]; then
  case " $* " in
    *' --metadata='*'runtime-evidence/v1'*'iv-new'*) printf 'run-new\n'; exit 0 ;;
    *) printf 'missing atomic runtime metadata\n' >&2; exit 9 ;;
  esac
fi
if [ "${1:-}" = run ] && [ "${2:-}" = phase ]; then printf 'brainstorm\n'; exit 0; fi
exit 0
`
	for name, content := range map[string]string{"bd": bdScript, "ic": icScript} {
		if err := os.WriteFile(filepath.Join(binDir, name), []byte(content), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	t.Setenv("PATH", binDir+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("RUNTIME_CREATE_LOG", logPath)
	oldICBin := icBin
	oldCache := runIDCache
	icBin = ""
	runIDCache = map[string]string{}
	t.Cleanup(func() { icBin = oldICBin; runIDCache = oldCache })
	oldDir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(root); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chdir(oldDir) })

	if err := cmdSprintCreate([]string{"Runtime gate", "3", "core", "--runtime-evidence"}); err != nil {
		t.Fatal(err)
	}
	calls := string(mustReadRuntimeTestFile(t, logPath))
	for _, required := range []string{
		"bd:label add iv-new close-gate:runtime-evidence",
		"ic:run create ",
		"--metadata=",
		"runtime-evidence/v1",
		"bd:set-state iv-new ic_run_id=run-new",
		"bd:set-state iv-new runtime_evidence_required=1",
	} {
		if !strings.Contains(calls, required) {
			t.Fatalf("calls missing %q:\n%s", required, calls)
		}
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

func TestVerifyRuntimeEvidenceUsesNewestTypedArtifactWithoutFallback(t *testing.T) {
	expectations := runtimeproof.Expectations{
		ExpectedBuildPath:           "/tmp/build",
		ExpectedInstalledPath:       "/tmp/install",
		RequiredSubsystems:          []string{"store"},
		NotApplicableFailureClasses: map[string]bool{"dependency_injection": true},
		RequiredAssertions:          []string{"state-delta"},
		ExpectedSurfaces:            []string{"diag/health"},
		RequiredResources:           []runtimeproof.ResourceExpectation{{Kind: "port", Ownership: "ephemeral"}},
	}
	metadataBytes, err := json.Marshal(map[string]any{"close_gate": map[string]any{
		"requirements":         []string{runtimeEvidenceArtifactType},
		"bead_id":              "iv-1",
		"runtime_expectations": expectations,
		"config_digest":        digestForRuntimeEvidence([]byte("config")),
	}})
	if err != nil {
		t.Fatal(err)
	}
	artifacts := []Artifact{
		{ID: "old", Type: runtimeEvidenceArtifactType, Path: "/tmp/old", ContentHash: digestForRuntimeEvidence([]byte("old")), Status: "active", CreatedAt: 1},
		{ID: "new", Type: runtimeEvidenceArtifactType, Path: "/tmp/new", ContentHash: digestForRuntimeEvidence([]byte("new")), Status: "active", CreatedAt: 2},
	}
	var verifiedPath string
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return nil, nil },
		state:      func(string, string) (string, error) { return "1", nil },
		resolveRun: func(string) (string, error) { return "run-1", nil },
		loadRun: func(string) (Run, error) {
			return Run{ID: "run-1", ProjectDir: "/tmp/project", Metadata: string(metadataBytes), CreatedAt: 1}, nil
		},
		listArtifacts: func(string) ([]Artifact, error) { return artifacts, nil },
		verifyFile: func(_ context.Context, path string, _ runtimeproof.VerifyOptions) (*runtimeproof.Result, error) {
			verifiedPath = path
			return nil, errors.New("newest receipt invalid")
		},
	}
	if _, err := verifyRuntimeEvidence(ops, "iv-1"); err == nil || !strings.Contains(err.Error(), "newest receipt invalid") {
		t.Fatalf("error = %v", err)
	}
	if verifiedPath != "/tmp/new" {
		t.Fatalf("verified path = %q, want newest", verifiedPath)
	}

	ops.verifyFile = func(_ context.Context, path string, options runtimeproof.VerifyOptions) (*runtimeproof.Result, error) {
		if path != "/tmp/new" || options.ExpectedArtifactHash != artifacts[1].ContentHash || options.ExpectedBeadID != "iv-1" {
			t.Fatalf("verification request = %q %+v", path, options)
		}
		return &runtimeproof.Result{Summary: runtimeproof.Summary{SchemaVersion: 1, ProofHash: artifacts[1].ContentHash, RunID: "run-1"}}, nil
	}
	summary, err := verifyRuntimeEvidence(ops, "iv-1")
	if err != nil {
		t.Fatal(err)
	}
	if summary.ProofHash != artifacts[1].ContentHash {
		t.Fatalf("summary = %+v", summary)
	}
}

func TestVerifyRuntimeEvidenceRequiresSealedExpectations(t *testing.T) {
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return []string{runtimeEvidenceLabel}, nil },
		state:      func(string, string) (string, error) { return "1", nil },
		resolveRun: func(string) (string, error) { return "run-1", nil },
		loadRun: func(string) (Run, error) {
			return Run{ID: "run-1", Metadata: `{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"iv-1"}}`}, nil
		},
	}
	if _, err := verifyRuntimeEvidence(ops, "iv-1"); err == nil || !strings.Contains(err.Error(), "expectations") {
		t.Fatalf("error = %v", err)
	}
}

func TestRuntimeEvidenceAdoptCreatesMinimalRunAndPersistsIdentity(t *testing.T) {
	var created runtimeAdoptCreate
	var stateWrites []string
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return []string{runtimeEvidenceLabel}, nil },
		state:      func(string, string) (string, error) { return "", nil },
		resolveRun: func(string) (string, error) { return "", errRuntimeRunNotBound },
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
		resolveRun: func(string) (string, error) { return "", errRuntimeRunNotBound },
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

func TestRuntimeEvidenceAdoptFailsOnStateReadAndScopeConflicts(t *testing.T) {
	base := runtimeEvidenceOps{
		labels:   func(string) ([]string, error) { return []string{runtimeEvidenceLabel}, nil },
		state:    func(string, string) (string, error) { return "", nil },
		setState: func(string, string, string) error { return nil },
		validateAdoption: func(string, string) (json.RawMessage, error) {
			return json.RawMessage(`{"schema_version":1}`), nil
		},
		createRun: func(runtimeAdoptCreate) (string, error) {
			t.Fatal("conflict must not create a run")
			return "", nil
		},
	}

	t.Run("operational state read", func(t *testing.T) {
		ops := base
		ops.resolveRun = func(string) (string, error) { return "", errors.New("tracker unavailable") }
		if _, err := adoptRuntimeEvidence(ops, "iv-1", "/tmp/project", "/tmp/provenance"); err == nil || !strings.Contains(err.Error(), "tracker unavailable") {
			t.Fatalf("error = %v", err)
		}
	})

	t.Run("unbound scope run", func(t *testing.T) {
		ops := base
		ops.resolveRun = func(string) (string, error) { return "", errRuntimeRunNotBound }
		ops.findScopeRuns = func(string) ([]Run, error) {
			return []Run{{ID: "run-conflict", Status: "active", ProjectDir: "/tmp/project"}}, nil
		}
		if _, err := adoptRuntimeEvidence(ops, "iv-1", "/tmp/project", "/tmp/provenance"); err == nil || !strings.Contains(err.Error(), "conflicting") {
			t.Fatalf("error = %v", err)
		}
	})

	t.Run("bound wrong project", func(t *testing.T) {
		ops := base
		ops.resolveRun = func(string) (string, error) { return "", errRuntimeRunNotBound }
		ops.findScopeRuns = func(string) ([]Run, error) {
			return []Run{{ID: "run-wrong-root", Status: "active", ProjectDir: "/tmp/other", Metadata: `{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"iv-1"}}`}}, nil
		}
		if _, err := adoptRuntimeEvidence(ops, "iv-1", "/tmp/project", "/tmp/provenance"); err == nil || !strings.Contains(err.Error(), "project root") {
			t.Fatalf("error = %v", err)
		}
	})
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
		ProbeDigests:   map[string]string{platform: digestForRuntimeEvidence([]byte("probe"))},
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

func TestRuntimeBoundedCommandFailsClosed(t *testing.T) {
	tests := []struct {
		name    string
		mode    string
		timeout time.Duration
		limit   int
		wantErr string
	}{
		{name: "timeout", mode: "sleep", timeout: 50 * time.Millisecond, limit: 1024, wantErr: "timed out"},
		{name: "nonzero", mode: "exit", timeout: 5 * time.Second, limit: 1024, wantErr: "command failed"},
		{name: "oversized", mode: "flood", timeout: 5 * time.Second, limit: 128, wantErr: "output exceeded"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			env := runtimeEvidenceEnvironment(map[string]string{"CLAVAIN_RUNTIME_TEST_HELPER": tt.mode})
			_, err := runRuntimeBoundedCommand([]string{os.Args[0], "-test.run=TestRuntimeManagedProcessHelper"}, env, ".", tt.timeout, tt.limit)
			if err == nil || !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("error = %v, want substring %q", err, tt.wantErr)
			}
		})
	}
}

func TestRuntimeManagedProcessHelper(t *testing.T) {
	switch os.Getenv("CLAVAIN_RUNTIME_TEST_HELPER") {
	case "parent":
		cmd := exec.Command(os.Args[0], "-test.run=TestRuntimeManagedProcessHelper")
		cmd.Env = runtimeEvidenceEnvironment(map[string]string{"CLAVAIN_RUNTIME_TEST_HELPER": "child"})
		if err := cmd.Start(); err != nil {
			os.Exit(91)
		}
		if err := os.WriteFile(os.Getenv("CLAVAIN_RUNTIME_TEST_PID_FILE"), []byte(strconv.Itoa(cmd.Process.Pid)), 0o600); err != nil {
			os.Exit(92)
		}
		return
	case "child":
		time.Sleep(30 * time.Second)
		return
	case "sleep":
		time.Sleep(30 * time.Second)
		return
	case "exit":
		_, _ = fmt.Fprintln(os.Stderr, "intentional failure")
		os.Exit(7)
	case "flood":
		_, _ = fmt.Fprint(os.Stdout, strings.Repeat("x", 4096))
		return
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
		ProbeDigests:                map[string]string{platform: digestForRuntimeEvidence([]byte("probe"))},
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
			cfg.ProbeDigests = cloneStringMap(base.ProbeDigests)
			cfg.RequiredResources = append([]runtimeproof.ResourceExpectation(nil), base.RequiredResources...)
			tt.mutate(&cfg)
			_, err := resolveRuntimeEvidenceConfig(root, cfg)
			if err == nil || !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("error = %v, want substring %q", err, tt.wantErr)
			}
		})
	}
}

func TestLoadRuntimeEvidenceConfigRequiresCommittedBytesInsideProject(t *testing.T) {
	project, _ := initRuntimeEvidenceGitRepo(t, "README.md", "project\n")
	platform := runtime.GOOS + "-" + runtime.GOARCH
	buildPath := filepath.Join(project, "build", "fixture")
	probePath := filepath.Join(project, "tools", "probe")
	installedPath := filepath.Join(t.TempDir(), "installed")
	for path, content := range map[string][]byte{
		buildPath:     []byte("fixture"),
		probePath:     []byte("probe"),
		installedPath: []byte("fixture"),
	} {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, content, 0o700); err != nil {
			t.Fatal(err)
		}
	}
	cfg := runtimeEvidenceConfigFile{
		SchemaVersion:               1,
		BuildPath:                   "build/fixture",
		InstalledPaths:              map[string]string{platform: installedPath},
		StartArgv:                   []string{"{installed_path}"},
		ProbeArgv:                   []string{"{project_root}/tools/probe"},
		ProbeDigests:                map[string]string{platform: digestForRuntimeEvidence([]byte("probe"))},
		TimeoutSeconds:              5,
		RequiredSubsystems:          []string{"store"},
		NotApplicableFailureClasses: []string{"dependency_injection", "projection_catchup"},
		RequiredAssertions:          []string{"state-delta"},
		ExpectedSurfaces:            []string{"diag/health", "diag/smoke-test"},
		RequiredResources:           []runtimeproof.ResourceExpectation{{Kind: "port", Ownership: "ephemeral"}},
	}
	data, err := json.Marshal(cfg)
	if err != nil {
		t.Fatal(err)
	}
	configPath := filepath.Join(project, "runtime-evidence.json")
	if err := os.WriteFile(configPath, data, 0o600); err != nil {
		t.Fatal(err)
	}
	runRuntimeEvidenceGit(t, project, "add", "--", "runtime-evidence.json", "tools/probe")
	runRuntimeEvidenceGit(t, project, "commit", "-q", "-m", "runtime config")
	loaded, digest, err := loadRuntimeEvidenceConfig(project, configPath)
	if err != nil {
		t.Fatal(err)
	}
	wantInstalled, err := filepath.EvalSymlinks(cfg.InstalledPaths[platform])
	if err != nil {
		t.Fatal(err)
	}
	if loaded.InstalledPath != wantInstalled || digest != digestForRuntimeEvidence(data) {
		t.Fatalf("loaded=%+v digest=%s", loaded, digest)
	}
	if err := os.WriteFile(probePath, []byte("tampered probe"), 0o700); err != nil {
		t.Fatal(err)
	}
	if _, _, err := loadRuntimeEvidenceConfig(project, configPath); err == nil || !strings.Contains(err.Error(), "probe digest") {
		t.Fatalf("tampered probe error = %v", err)
	}
	if err := os.WriteFile(probePath, []byte("probe"), 0o700); err != nil {
		t.Fatal(err)
	}

	if err := os.WriteFile(configPath, append(data, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := loadRuntimeEvidenceConfig(project, configPath); err == nil || !strings.Contains(err.Error(), "committed") {
		t.Fatalf("dirty config error = %v", err)
	}

	untracked := filepath.Join(project, "untracked-runtime.json")
	if err := os.WriteFile(untracked, data, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := loadRuntimeEvidenceConfig(project, untracked); err == nil || !strings.Contains(err.Error(), "tracked") {
		t.Fatalf("untracked config error = %v", err)
	}

	privateConfig := filepath.Join(t.TempDir(), "runtime-evidence.json")
	if err := os.WriteFile(privateConfig, data, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := loadRuntimeEvidenceConfig(project, privateConfig); err == nil || !strings.Contains(err.Error(), "inside the project root") {
		t.Fatalf("out-of-project config error = %v", err)
	}
	symlinkConfig := filepath.Join(t.TempDir(), "runtime-evidence.json")
	if err := os.Symlink(privateConfig, symlinkConfig); err != nil {
		t.Fatal(err)
	}
	if _, _, err := loadRuntimeEvidenceConfig(project, symlinkConfig); err == nil || !strings.Contains(err.Error(), "symlink") {
		t.Fatalf("symlink config error = %v", err)
	}
}

func TestLoadRuntimeEvidenceConfigRejectsBuildParentSymlinkEscape(t *testing.T) {
	project, _ := initRuntimeEvidenceGitRepo(t, "README.md", "project\n")
	outside := t.TempDir()
	if err := os.WriteFile(filepath.Join(outside, "fixture"), []byte("fixture"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(project, "build")); err != nil {
		t.Fatal(err)
	}
	probe := filepath.Join(project, "probe")
	installed := filepath.Join(t.TempDir(), "installed")
	for path, content := range map[string][]byte{probe: []byte("probe"), installed: []byte("fixture")} {
		if err := os.WriteFile(path, content, 0o700); err != nil {
			t.Fatal(err)
		}
	}
	platform := runtime.GOOS + "-" + runtime.GOARCH
	cfg := runtimeEvidenceConfigFile{
		SchemaVersion: 1, BuildPath: "build/fixture",
		InstalledPaths: map[string]string{platform: installed}, StartArgv: []string{"{installed_path}"},
		ProbeArgv: []string{"{project_root}/probe"}, ProbeDigests: map[string]string{platform: digestForRuntimeEvidence([]byte("probe"))},
		TimeoutSeconds: 5, RequiredSubsystems: []string{"store"}, RequiredAssertions: []string{"state-delta"},
		ExpectedSurfaces: []string{"diag/health"}, RequiredResources: []runtimeproof.ResourceExpectation{{Kind: "port", Ownership: "ephemeral"}},
	}
	data, err := json.Marshal(cfg)
	if err != nil {
		t.Fatal(err)
	}
	configPath := filepath.Join(project, "runtime-evidence.json")
	if err := os.WriteFile(configPath, data, 0o600); err != nil {
		t.Fatal(err)
	}
	runRuntimeEvidenceGit(t, project, "add", "--", "runtime-evidence.json")
	runRuntimeEvidenceGit(t, project, "commit", "-q", "-m", "runtime config")
	if _, _, err := loadRuntimeEvidenceConfig(project, configPath); err == nil || !strings.Contains(err.Error(), "outside the project root") {
		t.Fatalf("parent symlink escape error = %v", err)
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

func TestValidateRuntimeEndpointDiscoveryAcceptsOnlyFreshPrivateLoopback(t *testing.T) {
	privateRoot := t.TempDir()
	valid := runtimeEndpointDiscovery{
		SchemaVersion: 1,
		Endpoint:      "http://127.0.0.1:43123",
		Resources:     []runtimeObservedResource{{Kind: "port", Identifier: "127.0.0.1:43123"}},
	}
	escapedPath := filepath.Join(filepath.Dir(privateRoot), "shared-runtime-path")
	if err := os.WriteFile(escapedPath, []byte("shared"), 0o600); err != nil {
		t.Fatal(err)
	}
	startedAt := time.Now().Add(-time.Second)
	if err := validateRuntimeEndpointDiscovery(valid, privateRoot, startedAt); err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		name    string
		mutate  func(*runtimeEndpointDiscovery)
		wantErr string
	}{
		{"remote endpoint", func(d *runtimeEndpointDiscovery) { d.Endpoint = "http://192.0.2.10:43123" }, "loopback"},
		{"hostname endpoint", func(d *runtimeEndpointDiscovery) { d.Endpoint = "http://localhost:43123" }, "IP literal"},
		{"https endpoint", func(d *runtimeEndpointDiscovery) { d.Endpoint = "https://127.0.0.1:43123" }, "http"},
		{"port disagreement", func(d *runtimeEndpointDiscovery) { d.Resources[0].Identifier = "127.0.0.1:43124" }, "endpoint port"},
		{"database", func(d *runtimeEndpointDiscovery) { d.Resources[0].Kind = "database" }, "UNVERIFIABLE"},
		{"private path escape", func(d *runtimeEndpointDiscovery) {
			d.Resources = []runtimeObservedResource{{Kind: "path", Identifier: escapedPath}}
		}, "private"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			discovery := valid
			discovery.Resources = append([]runtimeObservedResource(nil), valid.Resources...)
			tt.mutate(&discovery)
			err := validateRuntimeEndpointDiscovery(discovery, privateRoot, startedAt)
			if err == nil || !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("error = %v, want substring %q", err, tt.wantErr)
			}
		})
	}
}

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

func TestValidateRuntimePathResourceRequiresFreshOwnedExistence(t *testing.T) {
	privateRoot := t.TempDir()
	startedAt := time.Now().Add(-time.Second)
	validPath := filepath.Join(privateRoot, "owned-state")
	if err := os.WriteFile(validPath, []byte("state"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := validateRuntimePathResource(validPath, privateRoot, startedAt); err != nil {
		t.Fatalf("valid private path: %v", err)
	}

	if _, err := validateRuntimePathResource(filepath.Join(privateRoot, "never-created"), privateRoot, startedAt); err == nil || !strings.Contains(err.Error(), "exist") {
		t.Fatalf("nonexistent path error = %v", err)
	}
	symlinkPath := filepath.Join(privateRoot, "symlink")
	if err := os.Symlink(validPath, symlinkPath); err != nil {
		t.Fatal(err)
	}
	if _, err := validateRuntimePathResource(symlinkPath, privateRoot, startedAt); err == nil || !strings.Contains(err.Error(), "symlink") {
		t.Fatalf("symlink path error = %v", err)
	}
	stalePath := filepath.Join(privateRoot, "stale")
	if err := os.WriteFile(stalePath, []byte("old"), 0o600); err != nil {
		t.Fatal(err)
	}
	old := startedAt.Add(-time.Minute)
	if err := os.Chtimes(stalePath, old, old); err != nil {
		t.Fatal(err)
	}
	if _, err := validateRuntimePathResource(stalePath, privateRoot, startedAt); err == nil || !strings.Contains(err.Error(), "fresh") {
		t.Fatalf("stale path error = %v", err)
	}
}

func TestValidateRuntimeProbeScopeRejectsSpoofedOrUnverifiableObservations(t *testing.T) {
	expectations := runtimeproof.Expectations{
		ExpectedBuildPath:           "/tmp/build",
		ExpectedInstalledPath:       "/tmp/install",
		RequiredSubsystems:          []string{"store"},
		NotApplicableFailureClasses: map[string]bool{"dependency_injection": true, "projection_catchup": true},
		RequiredAssertions:          []string{"state-delta"},
		ExpectedSurfaces:            []string{"diag/health", "diag/smoke-test"},
		RequiredResources:           []runtimeproof.ResourceExpectation{{Kind: "port", Ownership: "ephemeral"}},
	}
	discovery := runtimeEndpointDiscovery{
		SchemaVersion: 1,
		Endpoint:      "http://127.0.0.1:43123",
		Resources:     []runtimeObservedResource{{Kind: "port", Identifier: "127.0.0.1:43123"}},
	}
	valid := runtimeProbeObservations{
		SchemaVersion:    1,
		ObservedNonce:    "nonce",
		Subsystems:       map[string]string{"store": "healthy"},
		FailureClasses:   validRuntimeFailureObservations(),
		ObservedEventID:  "event",
		BeforeDigest:     digestForRuntimeEvidence([]byte("before")),
		AfterDigest:      digestForRuntimeEvidence([]byte("after")),
		Assertions:       []runtimeproof.Assertion{{Name: "state-delta", State: runtimeproof.StateVerified, Evidence: "changed"}},
		ObservedSurfaces: []string{"diag/health", "diag/smoke-test"},
		Resources:        append([]runtimeObservedResource(nil), discovery.Resources...),
		Collisions:       []string{},
	}
	if err := validateRuntimeProbeScope(valid, discovery, expectations, "nonce", "event"); err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		name    string
		mutate  func(*runtimeProbeObservations)
		wantErr string
	}{
		{"nonce", func(o *runtimeProbeObservations) { o.ObservedNonce = "shared-instance" }, "nonce"},
		{"event", func(o *runtimeProbeObservations) { o.ObservedEventID = "old-event" }, "event"},
		{"missing failure evidence", func(o *runtimeProbeObservations) {
			v := o.FailureClasses["connection"]
			v.Evidence = ""
			o.FailureClasses["connection"] = v
		}, "evidence"},
		{"unauthorized not applicable", func(o *runtimeProbeObservations) {
			v := o.FailureClasses["connection"]
			v.State = runtimeproof.StateNotApplicable
			o.FailureClasses["connection"] = v
		}, "NOT_APPLICABLE"},
		{"unverifiable failure", func(o *runtimeProbeObservations) {
			v := o.FailureClasses["connection"]
			v.State = runtimeproof.StateUnverifiable
			o.FailureClasses["connection"] = v
		}, "UNVERIFIABLE"},
		{"surface spoof", func(o *runtimeProbeObservations) { o.ObservedSurfaces = []string{"diag/health"} }, "surface"},
		{"resource spoof", func(o *runtimeProbeObservations) { o.Resources[0].Identifier = "127.0.0.1:49999" }, "discovery"},
		{"database observation", func(o *runtimeProbeObservations) { o.Resources[0].Kind = "database" }, "UNVERIFIABLE"},
		{"collision", func(o *runtimeProbeObservations) { o.Collisions = []string{"127.0.0.1:43123"} }, "collision"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			obs := valid
			obs.Subsystems = cloneStringMap(valid.Subsystems)
			obs.FailureClasses = cloneRuntimeFailureObservations(valid.FailureClasses)
			obs.Assertions = append([]runtimeproof.Assertion(nil), valid.Assertions...)
			obs.ObservedSurfaces = append([]string(nil), valid.ObservedSurfaces...)
			obs.Resources = append([]runtimeObservedResource(nil), valid.Resources...)
			obs.Collisions = append([]string(nil), valid.Collisions...)
			tt.mutate(&obs)
			err := validateRuntimeProbeScope(obs, discovery, expectations, "nonce", "event")
			if err == nil || !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("error = %v, want substring %q", err, tt.wantErr)
			}
		})
	}
}

func TestCollectRuntimeEvidenceLaunchesInstalledFixtureAndRegistersPrivateReceipt(t *testing.T) {
	project, _ := initRuntimeEvidenceGitRepo(t, "README.md", "runtime project\n")
	buildDir := filepath.Join(project, "build")
	toolsDir := filepath.Join(project, "tools")
	if err := os.MkdirAll(buildDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(toolsDir, 0o755); err != nil {
		t.Fatal(err)
	}
	fixtureBuild := filepath.Join(buildDir, "runtimefixture")
	probeBuild := filepath.Join(toolsDir, "runtimeprobe")
	buildRuntimeTestBinary(t, "./testdata/runtimefixture", fixtureBuild)
	buildRuntimeTestBinary(t, "./testdata/runtimeprobe", probeBuild)
	installed := filepath.Join(t.TempDir(), "runtimefixture-installed")
	fixtureBytes, err := os.ReadFile(fixtureBuild)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(installed, fixtureBytes, 0o700); err != nil {
		t.Fatal(err)
	}

	platform := runtime.GOOS + "-" + runtime.GOARCH
	cfg := runtimeEvidenceConfigFile{
		SchemaVersion:               1,
		BuildPath:                   "build/runtimefixture",
		InstalledPaths:              map[string]string{platform: installed},
		StartArgv:                   []string{"{installed_path}"},
		ProbeArgv:                   []string{"{project_root}/tools/runtimeprobe"},
		ProbeDigests:                map[string]string{platform: digestForRuntimeEvidence(mustReadRuntimeTestFile(t, probeBuild))},
		TimeoutSeconds:              10,
		RequiredSubsystems:          []string{"store"},
		NotApplicableFailureClasses: []string{"dependency_injection", "projection_catchup"},
		RequiredAssertions:          []string{"state-delta"},
		ExpectedSurfaces:            []string{"diag/health", "diag/smoke-test"},
		RequiredResources:           []runtimeproof.ResourceExpectation{{Kind: "port", Ownership: "ephemeral"}},
	}
	configBytes, err := json.Marshal(cfg)
	if err != nil {
		t.Fatal(err)
	}
	configPath := filepath.Join(project, "runtime-evidence-canary.json")
	if err := os.WriteFile(configPath, configBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	runRuntimeEvidenceGit(t, project, "add", "--", "runtime-evidence-canary.json")
	runRuntimeEvidenceGit(t, project, "commit", "-q", "-m", "runtime evidence canary config")

	metadata := `{"close_gate":{"requirements":["runtime-evidence/v1"],"bead_id":"iv-collect"}}`
	run := Run{ID: "run-collect", ProjectDir: project, Phase: "reflect", Status: "active", Metadata: metadata, CreatedAt: time.Now().Add(-time.Minute).Unix()}
	var artifacts []Artifact
	ops := runtimeEvidenceOps{
		labels:     func(string) ([]string, error) { return []string{runtimeEvidenceLabel}, nil },
		state:      func(string, string) (string, error) { return "1", nil },
		setState:   func(string, string, string) error { return nil },
		resolveRun: func(string) (string, error) { return run.ID, nil },
		loadRun:    func(string) (Run, error) { return run, nil },
		mergeRunMetadata: func(_ string, patch string) error {
			var current map[string]any
			var update map[string]any
			if err := json.Unmarshal([]byte(run.Metadata), &current); err != nil {
				return err
			}
			if err := json.Unmarshal([]byte(patch), &update); err != nil {
				return err
			}
			currentGate := current["close_gate"].(map[string]any)
			for key, value := range update["close_gate"].(map[string]any) {
				currentGate[key] = value
			}
			encoded, err := json.Marshal(current)
			if err == nil {
				run.Metadata = string(encoded)
			}
			return err
		},
		registerArtifact: func(_, runID, phase, path, artifactType string) error {
			data, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			artifacts = append(artifacts, Artifact{
				ID: "artifact-1", RunID: runID, Phase: phase, Path: path, Type: artifactType,
				ContentHash: digestForRuntimeEvidence(data), Status: "active", CreatedAt: time.Now().Unix(),
			})
			return nil
		},
		listArtifacts: func(string) ([]Artifact, error) { return append([]Artifact(nil), artifacts...), nil },
		verifyFile:    runtimeproof.VerifyFile,
	}
	t.Setenv("XDG_STATE_HOME", t.TempDir())
	summary, err := collectRuntimeEvidence(ops, "iv-collect", configPath)
	if err != nil {
		t.Fatal(err)
	}
	if summary.RunID != run.ID || !runtimeDigestPattern.MatchString(summary.ProofHash) || len(artifacts) != 1 {
		t.Fatalf("summary=%+v artifacts=%+v", summary, artifacts)
	}
	receiptPath := artifacts[0].Path
	if rel, err := filepath.Rel(project, receiptPath); err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		t.Fatalf("receipt was written in worktree: %s", receiptPath)
	}
	info, err := os.Stat(receiptPath)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("receipt mode = %o", info.Mode().Perm())
	}
	receiptBytes, err := os.ReadFile(receiptPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(receiptPath, append(append([]byte(nil), receiptBytes...), '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := verifyRuntimeEvidence(ops, "iv-collect"); err == nil || !strings.Contains(err.Error(), "content hash mismatch") {
		t.Fatalf("tampered receipt error = %v", err)
	}
	if err := os.WriteFile(receiptPath, receiptBytes, 0o600); err != nil {
		t.Fatal(err)
	}

	registeredBefore := len(artifacts)
	failingCleanupOps := ops
	failingCleanupOps.removePrivateRoot = func(path string) error {
		_ = os.RemoveAll(path)
		return errors.New("forced private cleanup failure")
	}
	if _, err := collectRuntimeEvidence(failingCleanupOps, "iv-collect", configPath); err == nil || !strings.Contains(err.Error(), "private probe directory") {
		t.Fatalf("private cleanup error = %v", err)
	}
	if len(artifacts) != registeredBefore {
		t.Fatalf("cleanup failure registered a receipt: before=%d after=%d", registeredBefore, len(artifacts))
	}

	failingRegistrationOps := ops
	failingRegistrationOps.registerArtifact = func(string, string, string, string, string) error {
		return errors.New("forced registration failure")
	}
	if _, err := collectRuntimeEvidence(failingRegistrationOps, "iv-collect", configPath); err == nil || !strings.Contains(err.Error(), "forced registration failure") {
		t.Fatalf("registration error = %v", err)
	}
	if len(artifacts) != registeredBefore {
		t.Fatalf("registration failure changed artifact list: before=%d after=%d", registeredBefore, len(artifacts))
	}

	if err := os.WriteFile(installed, []byte("tampered installed artifact"), 0o700); err != nil {
		t.Fatal(err)
	}
	if _, err := collectRuntimeEvidence(ops, "iv-collect", configPath); err == nil || !strings.Contains(err.Error(), "digests differ") {
		t.Fatalf("build/install mismatch error = %v", err)
	}
}

func buildRuntimeTestBinary(t *testing.T, pkg, output string) {
	t.Helper()
	cmd := exec.Command("go", "build", "-o", output, pkg)
	cmd.Dir = "."
	cmd.Env = append(os.Environ(), "GOCACHE=/tmp/clavain-runtime-fixture-gocache")
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("go build %s: %v\n%s", pkg, err, out)
	}
}

func mustReadRuntimeTestFile(t *testing.T, path string) []byte {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func validRuntimeFailureObservations() map[string]runtimeObservedFailure {
	return map[string]runtimeObservedFailure{
		"startup":              {State: runtimeproof.StateVerified, Evidence: "started"},
		"dependency_injection": {State: runtimeproof.StateNotApplicable, Evidence: "standalone"},
		"connection":           {State: runtimeproof.StateVerified, Evidence: "connected"},
		"projection_catchup":   {State: runtimeproof.StateNotApplicable, Evidence: "no projection"},
	}
}

func cloneRuntimeFailureObservations(in map[string]runtimeObservedFailure) map[string]runtimeObservedFailure {
	out := make(map[string]runtimeObservedFailure, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}

func cloneStringMap(in map[string]string) map[string]string {
	out := make(map[string]string, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}
