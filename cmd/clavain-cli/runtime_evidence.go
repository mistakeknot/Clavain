package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/mistakeknot/intercore/pkg/runtimeproof"
)

const (
	runtimeEvidenceArtifactType = "runtime-evidence/v1"
	runtimeEvidenceLabel        = "close-gate:runtime-evidence"
)

type runtimeEvidenceConfigFile struct {
	SchemaVersion               int                                `json:"schema_version"`
	BuildPath                   string                             `json:"build_path"`
	InstalledPaths              map[string]string                  `json:"installed_paths"`
	StartArgv                   []string                           `json:"start_argv"`
	ProbeArgv                   []string                           `json:"probe_argv"`
	ProbeDigests                map[string]string                  `json:"probe_digests"`
	TimeoutSeconds              int                                `json:"timeout_seconds"`
	RequiredSubsystems          []string                           `json:"required_subsystems"`
	NotApplicableFailureClasses []string                           `json:"not_applicable_failure_classes"`
	RequiredAssertions          []string                           `json:"required_assertions"`
	ExpectedSurfaces            []string                           `json:"expected_surfaces"`
	RequiredResources           []runtimeproof.ResourceExpectation `json:"required_resources"`
}

type resolvedRuntimeEvidenceConfig struct {
	BuildPath     string
	InstalledPath string
	StartArgv     []string
	ProbeArgv     []string
	ProbeDigest   string
	Timeout       time.Duration
	Expectations  runtimeproof.Expectations
}

type runtimeObservedFailure struct {
	State    runtimeproof.State `json:"state"`
	Evidence string             `json:"evidence"`
}

type runtimeObservedResource struct {
	Kind       string `json:"kind"`
	Identifier string `json:"identifier"`
}

type runtimeProbeObservations struct {
	SchemaVersion    int                               `json:"schema_version"`
	ObservedNonce    string                            `json:"observed_nonce"`
	Subsystems       map[string]string                 `json:"subsystems"`
	FailureClasses   map[string]runtimeObservedFailure `json:"failure_classes"`
	ObservedEventID  string                            `json:"observed_event_id"`
	BeforeDigest     string                            `json:"before_digest"`
	AfterDigest      string                            `json:"after_digest"`
	Assertions       []runtimeproof.Assertion          `json:"assertions"`
	ObservedSurfaces []string                          `json:"observed_surfaces"`
	Resources        []runtimeObservedResource         `json:"resources"`
	Collisions       []string                          `json:"collisions"`
}

type runtimeEndpointDiscovery struct {
	SchemaVersion int                       `json:"schema_version"`
	Endpoint      string                    `json:"endpoint"`
	Resources     []runtimeObservedResource `json:"resources"`
}

type runtimeReceiptInput struct {
	BeadID          string
	RunID           string
	ProjectRoot     string
	GitHead         string
	Host            string
	CreatedAt       time.Time
	StartedAt       time.Time
	BuildDigest     string
	InstalledDigest string
	ProcessID       int
	InstanceNonce   string
	EventID         string
	Expectations    runtimeproof.Expectations
}

type runtimeCloseGateMetadata struct {
	Requirements        []string                   `json:"requirements"`
	BeadID              string                     `json:"bead_id"`
	Adoption            json.RawMessage            `json:"adoption,omitempty"`
	RuntimeExpectations *runtimeproof.Expectations `json:"runtime_expectations,omitempty"`
	ConfigDigest        string                     `json:"config_digest,omitempty"`
}

type runtimeRunMetadata struct {
	CloseGate *runtimeCloseGateMetadata `json:"close_gate,omitempty"`
}

type runtimeEvidenceOps struct {
	labels            func(string) ([]string, error)
	state             func(string, string) (string, error)
	setState          func(string, string, string) error
	resolveRun        func(string) (string, error)
	loadRun           func(string) (Run, error)
	mergeRunMetadata  func(string, string) error
	findScopeRuns     func(string) ([]Run, error)
	validateAdoption  func(string, string) (json.RawMessage, error)
	createRun         func(runtimeAdoptCreate) (string, error)
	listArtifacts     func(string) ([]Artifact, error)
	verifyFile        func(context.Context, string, runtimeproof.VerifyOptions) (*runtimeproof.Result, error)
	registerArtifact  func(string, string, string, string, string) error
	removePrivateRoot func(string) error
}

type runtimeAdoptCreate struct {
	ProjectRoot string
	Goal        string
	ScopeID     string
	Phases      []string
	Metadata    string
}

type runtimeAdoptionProvenanceFile struct {
	SchemaVersion int                     `json:"schema_version"`
	Plan          runtimeAdoptionPlan     `json:"plan"`
	Sources       []runtimeAdoptionSource `json:"sources"`
}

type runtimeAdoptionPlan struct {
	Repository string `json:"repository"`
	Path       string `json:"path"`
	Digest     string `json:"digest"`
	Head       string `json:"head"`
}

type runtimeAdoptionSource struct {
	Repository string `json:"repository"`
	Head       string `json:"head"`
}

var runtimeGitHeadPattern = regexp.MustCompile(`^[0-9a-f]{40,64}$`)
var runtimeDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
var errRuntimeRunNotBound = errors.New("runtime evidence run is not bound")

type runtimeEvidenceRequirementStatus struct {
	Required bool
	Bound    bool
	Labelled bool
	Marked   bool
	RunID    string
	Run      Run
}

func cmdRuntimeEvidence(args []string) error {
	if len(args) == 0 {
		return errors.New("usage: runtime-evidence <required|bind|adopt|collect|verify> ...")
	}
	switch args[0] {
	case "required":
		if len(args) != 2 || strings.TrimSpace(args[1]) == "" {
			return errors.New("usage: runtime-evidence required <bead_id>")
		}
		status, err := inspectRuntimeEvidenceRequirement(defaultRuntimeEvidenceOps(), args[1])
		if err != nil {
			return err
		}
		fmt.Println(status.Required)
		return nil
	case "bind":
		if len(args) != 2 || strings.TrimSpace(args[1]) == "" {
			return errors.New("usage: runtime-evidence bind <bead_id>")
		}
		return bindRuntimeEvidence(defaultRuntimeEvidenceOps(), args[1])
	case "adopt":
		if len(args) < 2 || strings.TrimSpace(args[1]) == "" {
			return errors.New("usage: runtime-evidence adopt <bead_id> --project=<root> --provenance=<json>")
		}
		projectRoot, ok := runtimeFlagValue(args[2:], "project")
		if !ok || strings.TrimSpace(projectRoot) == "" {
			return errors.New("runtime-evidence adopt: --project is required")
		}
		provenancePath, ok := runtimeFlagValue(args[2:], "provenance")
		if !ok || strings.TrimSpace(provenancePath) == "" {
			return errors.New("runtime-evidence adopt: --provenance is required")
		}
		lockOwner := fmt.Sprintf("clavain-runtime-adopt:%d", os.Getpid())
		if _, err := runIC("lock", "acquire", "runtime-evidence-adopt", args[1], "--timeout=2s", "--owner="+lockOwner); err != nil {
			return fmt.Errorf("runtime-evidence adopt: acquire serialization lock: %w", err)
		}
		defer func() {
			_, _ = runIC("lock", "release", "runtime-evidence-adopt", args[1], "--owner="+lockOwner)
		}()
		runID, err := adoptRuntimeEvidence(defaultRuntimeEvidenceOps(), args[1], projectRoot, provenancePath)
		if err != nil {
			return err
		}
		fmt.Println(runID)
		return nil
	case "verify":
		if len(args) != 2 || strings.TrimSpace(args[1]) == "" {
			return errors.New("usage: runtime-evidence verify <bead_id>")
		}
		summary, err := verifyRuntimeEvidence(defaultRuntimeEvidenceOps(), args[1])
		if err != nil {
			return err
		}
		encoded, err := json.Marshal(summary)
		if err != nil {
			return fmt.Errorf("runtime-evidence verify: encode summary: %w", err)
		}
		fmt.Println(string(encoded))
		return nil
	case "collect":
		if len(args) < 2 || strings.TrimSpace(args[1]) == "" {
			return errors.New("usage: runtime-evidence collect <bead_id> --config=<path>")
		}
		configPath, ok := runtimeFlagValue(args[2:], "config")
		if !ok || strings.TrimSpace(configPath) == "" {
			return errors.New("runtime-evidence collect: --config is required")
		}
		summary, err := collectRuntimeEvidence(defaultRuntimeEvidenceOps(), args[1], configPath)
		if err != nil {
			return err
		}
		encoded, err := json.Marshal(summary)
		if err != nil {
			return fmt.Errorf("runtime-evidence collect: encode summary: %w", err)
		}
		fmt.Println(string(encoded))
		return nil
	default:
		return fmt.Errorf("runtime-evidence: unknown subcommand %q", args[0])
	}
}

func defaultRuntimeEvidenceOps() runtimeEvidenceOps {
	return runtimeEvidenceOps{
		labels: func(beadID string) ([]string, error) {
			out, err := runBD("show", beadID, "--json")
			if err != nil {
				return nil, err
			}
			return runtimeEvidenceLabelsFromBDJSON(out)
		},
		state: func(beadID, key string) (string, error) {
			out, err := runBDQuiet("state", beadID, key)
			if err != nil {
				return "", err
			}
			value := strings.TrimSpace(string(out))
			if value == "null" || strings.HasPrefix(value, "(no ") {
				return "", nil
			}
			return value, nil
		},
		setState: func(beadID, key, value string) error {
			_, err := runBD("set-state", beadID, key+"="+value)
			return err
		},
		resolveRun: func(beadID string) (string, error) {
			if runID, ok := runIDCache[beadID]; ok && strings.TrimSpace(runID) != "" {
				return runID, nil
			}
			out, err := runBDQuiet("state", beadID, "ic_run_id")
			if err != nil {
				return "", err
			}
			runID := strings.TrimSpace(string(out))
			if runID == "" || runID == "null" || strings.HasPrefix(runID, "(no ") {
				return "", errRuntimeRunNotBound
			}
			runIDCache[beadID] = runID
			return runID, nil
		},
		loadRun: func(runID string) (Run, error) {
			var run Run
			if err := runICJSONQuiet(&run, "run", "status", runID); err != nil {
				return Run{}, err
			}
			return run, nil
		},
		mergeRunMetadata: func(runID, patch string) error {
			_, err := runIC("run", "set", runID, "--metadata-merge="+patch)
			return err
		},
		findScopeRuns: func(scopeID string) ([]Run, error) {
			var runs []Run
			if err := runICJSONQuiet(&runs, "run", "list", "--scope="+scopeID); err != nil {
				return nil, err
			}
			return runs, nil
		},
		validateAdoption: validateRuntimeAdoptionProvenance,
		createRun: func(spec runtimeAdoptCreate) (string, error) {
			phases, err := json.Marshal(spec.Phases)
			if err != nil {
				return "", err
			}
			out, err := runIC(
				"run", "create",
				"--project="+spec.ProjectRoot,
				"--goal="+spec.Goal,
				"--scope-id="+spec.ScopeID,
				"--phases="+string(phases),
				"--metadata="+spec.Metadata,
			)
			if err != nil {
				return "", err
			}
			return strings.TrimSpace(string(out)), nil
		},
		listArtifacts: func(runID string) ([]Artifact, error) {
			var artifacts []Artifact
			if err := runICJSONQuiet(&artifacts, "run", "artifact", "list", runID); err != nil {
				return nil, err
			}
			return artifacts, nil
		},
		verifyFile: runtimeproof.VerifyFile,
		registerArtifact: func(beadID, runID, phase, path, artifactType string) error {
			if _, err := runBD("set-state", beadID, "artifact_"+artifactType+"="+path); err != nil {
				return fmt.Errorf("register runtime evidence in Beads: %w", err)
			}
			if _, err := runIC("run", "artifact", "add", runID, "--phase="+phase, "--path="+path, "--type="+artifactType); err != nil {
				return fmt.Errorf("register runtime evidence in Intercore: %w", err)
			}
			return nil
		},
		removePrivateRoot: removeRuntimePrivateRoot,
	}
}

func runtimeFlagValue(args []string, name string) (string, bool) {
	prefix := "--" + name + "="
	for _, arg := range args {
		if strings.HasPrefix(arg, prefix) {
			return strings.TrimPrefix(arg, prefix), true
		}
	}
	return "", false
}

func runtimeEvidenceLabelsFromBDJSON(data []byte) ([]string, error) {
	decodeOne := func(raw json.RawMessage) ([]string, error) {
		var item map[string]json.RawMessage
		if err := json.Unmarshal(raw, &item); err != nil {
			return nil, err
		}
		rawLabels, ok := item["labels"]
		if !ok || bytes.Equal(bytes.TrimSpace(rawLabels), []byte("null")) {
			return nil, nil
		}
		var labels []string
		if err := json.Unmarshal(rawLabels, &labels); err != nil {
			return nil, fmt.Errorf("decode labels: %w", err)
		}
		return labels, nil
	}

	trimmed := bytes.TrimSpace(data)
	if len(trimmed) == 0 {
		return nil, errors.New("empty bd show JSON")
	}
	if trimmed[0] == '[' {
		var items []json.RawMessage
		if err := json.Unmarshal(trimmed, &items); err != nil {
			return nil, err
		}
		if len(items) != 1 {
			return nil, fmt.Errorf("bd show returned %d records, want 1", len(items))
		}
		return decodeOne(items[0])
	}
	return decodeOne(trimmed)
}

func inspectRuntimeEvidenceRequirement(ops runtimeEvidenceOps, beadID string) (runtimeEvidenceRequirementStatus, error) {
	labels, err := ops.labels(beadID)
	if err != nil {
		return runtimeEvidenceRequirementStatus{}, fmt.Errorf("runtime-evidence required: read labels: %w", err)
	}
	markerValue, err := ops.state(beadID, "runtime_evidence_required")
	if err != nil {
		return runtimeEvidenceRequirementStatus{}, fmt.Errorf("runtime-evidence required: read durable marker: %w", err)
	}
	status := runtimeEvidenceRequirementStatus{
		Labelled: containsString(labels, runtimeEvidenceLabel),
		Marked:   runtimeMarkerSet(markerValue),
	}
	runID, resolveErr := ops.resolveRun(beadID)
	if resolveErr != nil && !errors.Is(resolveErr, errRuntimeRunNotBound) {
		return runtimeEvidenceRequirementStatus{}, fmt.Errorf("runtime-evidence required: resolve run binding: %w", resolveErr)
	}
	if resolveErr == nil && strings.TrimSpace(runID) != "" {
		status.RunID = runID
		status.Run, err = ops.loadRun(runID)
		if err != nil {
			return runtimeEvidenceRequirementStatus{}, fmt.Errorf("runtime-evidence required: load run %s: %w", runID, err)
		}
		_, status.Bound, err = runtimeEvidenceMetadataState(beadID, status.Run.Metadata)
		if err != nil {
			return runtimeEvidenceRequirementStatus{}, err
		}
	}
	status.Required = status.Labelled || status.Marked || status.Bound
	return status, nil
}

func validateRuntimeEvidenceBinding(ops runtimeEvidenceOps, beadID string) error {
	status, err := inspectRuntimeEvidenceRequirement(ops, beadID)
	if err != nil {
		return err
	}
	if !status.Required {
		return nil
	}
	if status.RunID == "" {
		return fmt.Errorf("runtime evidence is required for %s but no run is bound; use `clavain-cli runtime-evidence adopt %s --project=<root> --provenance=<json>`", beadID, beadID)
	}
	if !status.Bound {
		return fmt.Errorf("runtime evidence is required for %s but run %s is not sealed; use `clavain-cli runtime-evidence bind %s`", beadID, status.RunID, beadID)
	}
	return nil
}

func runtimeEvidenceMetadataForBead(beadID string) (string, error) {
	if strings.TrimSpace(beadID) == "" {
		return "", errors.New("runtime evidence metadata requires a bead or scope ID")
	}
	data, err := json.Marshal(runtimeRunMetadata{CloseGate: &runtimeCloseGateMetadata{
		Requirements: []string{runtimeEvidenceArtifactType},
		BeadID:       beadID,
	}})
	if err != nil {
		return "", err
	}
	return string(data), nil
}

func verifyRuntimeEvidence(ops runtimeEvidenceOps, beadID string) (runtimeproof.Summary, error) {
	status, err := inspectRuntimeEvidenceRequirement(ops, beadID)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence verify: %w", err)
	}
	if !status.Required {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence verify: bead %s does not require runtime evidence", beadID)
	}
	if !status.Bound || status.RunID == "" {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence verify: bead %s is required but not bound to a sealed run", beadID)
	}
	metadata, _, err := runtimeEvidenceMetadataState(beadID, status.Run.Metadata)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence verify: %w", err)
	}
	if metadata.CloseGate == nil || metadata.CloseGate.RuntimeExpectations == nil || metadata.CloseGate.ConfigDigest == "" {
		return runtimeproof.Summary{}, errors.New("runtime-evidence verify: sealed runtime expectations and config digest are missing")
	}
	if !runtimeDigestPattern.MatchString(metadata.CloseGate.ConfigDigest) {
		return runtimeproof.Summary{}, errors.New("runtime-evidence verify: sealed config digest is invalid")
	}
	if err := runtimeproof.ValidateExpectations(*metadata.CloseGate.RuntimeExpectations); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence verify: sealed expectations: %w", err)
	}
	if !filepath.IsAbs(status.Run.ProjectDir) {
		return runtimeproof.Summary{}, errors.New("runtime-evidence verify: run project directory must be absolute")
	}
	artifacts, err := ops.listArtifacts(status.RunID)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence verify: list artifacts: %w", err)
	}
	var newest *Artifact
	for idx := len(artifacts) - 1; idx >= 0; idx-- {
		artifact := artifacts[idx]
		if artifact.Type == runtimeEvidenceArtifactType && artifact.Status == "active" {
			newest = &artifact
			break
		}
	}
	if newest == nil {
		return runtimeproof.Summary{}, errors.New("runtime-evidence verify: no active runtime-evidence/v1 artifact is registered")
	}
	if !runtimeDigestPattern.MatchString(newest.ContentHash) {
		return runtimeproof.Summary{}, errors.New("runtime-evidence verify: newest runtime evidence artifact has no valid content hash")
	}
	result, err := ops.verifyFile(context.Background(), newest.Path, runtimeproof.VerifyOptions{
		ExpectedBeadID:       beadID,
		ExpectedRunID:        status.RunID,
		ExpectedProjectRoot:  filepath.Clean(status.Run.ProjectDir),
		ExpectedArtifactHash: newest.ContentHash,
		RunCreatedAt:         time.Unix(status.Run.CreatedAt, 0),
		Expectations:         *metadata.CloseGate.RuntimeExpectations,
	})
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence verify: %w", err)
	}
	return result.Summary, nil
}

func collectRuntimeEvidence(ops runtimeEvidenceOps, beadID, configPath string) (summary runtimeproof.Summary, returnErr error) {
	if err := bindRuntimeEvidence(ops, beadID); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: %w", err)
	}
	status, err := inspectRuntimeEvidenceRequirement(ops, beadID)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: %w", err)
	}
	if !status.Bound || status.RunID == "" || !filepath.IsAbs(status.Run.ProjectDir) {
		return runtimeproof.Summary{}, errors.New("runtime-evidence collect: required run is not durably bound to an absolute project root")
	}
	if status.Run.CreatedAt <= 0 {
		return runtimeproof.Summary{}, errors.New("runtime-evidence collect: run creation time is missing")
	}
	projectRoot := filepath.Clean(status.Run.ProjectDir)
	resolved, configDigest, err := loadRuntimeEvidenceConfig(projectRoot, configPath)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: %w", err)
	}
	metadataPatch, err := json.Marshal(map[string]any{"close_gate": map[string]any{
		"runtime_expectations": resolved.Expectations,
		"config_digest":        configDigest,
	}})
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: encode expectations: %w", err)
	}
	if err := ops.mergeRunMetadata(status.RunID, string(metadataPatch)); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: seal expectations: %w", err)
	}
	status, err = inspectRuntimeEvidenceRequirement(ops, beadID)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: reload sealed run: %w", err)
	}
	metadata, bound, err := runtimeEvidenceMetadataState(beadID, status.Run.Metadata)
	if err != nil || !bound || metadata.CloseGate == nil || metadata.CloseGate.RuntimeExpectations == nil || metadata.CloseGate.ConfigDigest != configDigest {
		return runtimeproof.Summary{}, errors.New("runtime-evidence collect: sealed expectations failed read-after-write verification")
	}

	buildDigest, _, err := hashRuntimeRegularFile(resolved.BuildPath, runtimeproof.DefaultMaxArtifactBytes)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: build artifact: %w", err)
	}
	installedDigest, installedMode, err := hashRuntimeRegularFile(resolved.InstalledPath, runtimeproof.DefaultMaxArtifactBytes)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: installed artifact: %w", err)
	}
	if installedMode&0o111 == 0 {
		return runtimeproof.Summary{}, errors.New("runtime-evidence collect: installed artifact is not executable")
	}
	if buildDigest != installedDigest {
		return runtimeproof.Summary{}, errors.New("runtime-evidence collect: build and installed artifact digests differ")
	}
	gitHead, err := runtimeGitOutput(projectRoot, "rev-parse", "HEAD")
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: resolve git HEAD: %w", err)
	}
	gitHead = strings.TrimSpace(gitHead)
	if !runtimeGitHeadPattern.MatchString(gitHead) {
		return runtimeproof.Summary{}, errors.New("runtime-evidence collect: git HEAD is invalid")
	}
	host, err := os.Hostname()
	if err != nil || strings.TrimSpace(host) == "" {
		return runtimeproof.Summary{}, errors.New("runtime-evidence collect: hostname is unavailable")
	}
	instanceNonce, err := newRuntimeEvidenceID()
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: nonce: %w", err)
	}
	eventID, err := newRuntimeEvidenceID()
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: event ID: %w", err)
	}

	stateDir, err := runtimeEvidenceStateDir(projectRoot)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: state directory: %w", err)
	}
	privateRoot, err := os.MkdirTemp(stateDir, ".probe-")
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: private probe directory: %w", err)
	}
	removePrivateRoot := ops.removePrivateRoot
	if removePrivateRoot == nil {
		removePrivateRoot = removeRuntimePrivateRoot
	}
	privateRootRemoved := false
	defer func() {
		if !privateRootRemoved {
			if cleanupErr := removePrivateRoot(privateRoot); cleanupErr != nil {
				returnErr = errors.Join(returnErr, fmt.Errorf("runtime-evidence collect: deferred private probe directory cleanup: %w", cleanupErr))
			}
		}
	}()
	if err := os.Chmod(privateRoot, 0o700); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: private probe permissions: %w", err)
	}
	endpointPath := filepath.Join(privateRoot, "endpoint.json")
	if _, err := os.Lstat(endpointPath); !errors.Is(err, os.ErrNotExist) {
		return runtimeproof.Summary{}, errors.New("runtime-evidence collect: endpoint discovery path was not fresh")
	}
	generatedEnv := map[string]string{
		"CLAVAIN_RUNTIME_BEAD_ID":        beadID,
		"CLAVAIN_RUNTIME_RUN_ID":         status.RunID,
		"CLAVAIN_RUNTIME_GIT_HEAD":       gitHead,
		"CLAVAIN_RUNTIME_INSTANCE_NONCE": instanceNonce,
		"CLAVAIN_RUNTIME_EVENT_ID":       eventID,
		"CLAVAIN_RUNTIME_ENDPOINT_FILE":  endpointPath,
	}
	childEnv := runtimeEvidenceEnvironment(generatedEnv)
	startedAt := time.Now().UTC()
	process, err := startRuntimeManagedProcess(resolved.StartArgv, childEnv, projectRoot, 256<<10)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: start installed runtime: %w", err)
	}
	generatedEnv["CLAVAIN_RUNTIME_PROCESS_ID"] = strconv.Itoa(process.pid)
	childEnv = runtimeEvidenceEnvironment(generatedEnv)
	processStopped := false
	discoveryLoaded := false
	var cleanupResources []runtimeObservedResource
	defer func() {
		if !processStopped {
			if cleanupErr := process.stop(2 * time.Second); cleanupErr != nil {
				returnErr = errors.Join(returnErr, fmt.Errorf("runtime-evidence collect: deferred process-group cleanup: %w", cleanupErr))
			}
			if discoveryLoaded {
				if cleanupErr := verifyRuntimeResourceCleanup(cleanupResources); cleanupErr != nil {
					returnErr = errors.Join(returnErr, fmt.Errorf("runtime-evidence collect: deferred resource cleanup: %w", cleanupErr))
				}
			}
		}
	}()

	discovery, err := waitRuntimeEndpointDiscovery(endpointPath, privateRoot, startedAt, resolved.Timeout, process)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: %w", err)
	}
	discoveryLoaded = true
	cleanupResources = append([]runtimeObservedResource(nil), discovery.Resources...)
	probeOutput, err := runRuntimeBoundedCommand(resolved.ProbeArgv, childEnv, projectRoot, resolved.Timeout, 256<<10)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: probe: %w", err)
	}
	if exited, exitErr := process.exited(); exited {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: installed runtime exited before cleanup: %v", exitErr)
	}
	var observations runtimeProbeObservations
	if err := decodeStrictJSON(probeOutput, &observations); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: decode probe output: %w", err)
	}
	if err := validateRuntimeProbeScope(observations, discovery, resolved.Expectations, instanceNonce, eventID); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: %w", err)
	}
	if err := process.stop(2 * time.Second); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: stop installed runtime: %w", err)
	}
	processStopped = true
	if process.stdout.overflowed() || process.stderr.overflowed() {
		return runtimeproof.Summary{}, errors.New("runtime-evidence collect: installed runtime output exceeded limit")
	}
	if err := verifyRuntimeResourceCleanup(discovery.Resources); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: cleanup: %w", err)
	}
	if err := removePrivateRoot(privateRoot); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: private probe directory cleanup: %w", err)
	}
	privateRootRemoved = true

	receipt, err := buildRuntimeEvidenceReceipt(runtimeReceiptInput{
		BeadID: beadID, RunID: status.RunID, ProjectRoot: projectRoot, GitHead: gitHead, Host: host,
		CreatedAt: time.Now().UTC(), StartedAt: startedAt,
		BuildDigest: buildDigest, InstalledDigest: installedDigest,
		ProcessID: process.pid, InstanceNonce: instanceNonce, EventID: eventID,
		Expectations: resolved.Expectations,
	}, observations)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: assemble receipt: %w", err)
	}
	receiptPath, _, err := writeAndVerifyRuntimeReceipt(stateDir, beadID, status.Run, receipt, resolved.Expectations)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: receipt: %w", err)
	}
	if err := ops.registerArtifact(beadID, status.RunID, status.Run.Phase, receiptPath, runtimeEvidenceArtifactType); err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: register receipt: %w", err)
	}
	summary, err = verifyRuntimeEvidence(ops, beadID)
	if err != nil {
		return runtimeproof.Summary{}, fmt.Errorf("runtime-evidence collect: post-registration verification: %w", err)
	}
	return summary, nil
}

func bindRuntimeEvidence(ops runtimeEvidenceOps, beadID string) error {
	if strings.TrimSpace(beadID) == "" {
		return errors.New("runtime-evidence bind: bead ID is required")
	}
	labels, err := ops.labels(beadID)
	if err != nil {
		return fmt.Errorf("runtime-evidence bind: read labels: %w", err)
	}
	labelled := containsString(labels, runtimeEvidenceLabel)
	markerValue, err := ops.state(beadID, "runtime_evidence_required")
	if err != nil {
		return fmt.Errorf("runtime-evidence bind: read durable marker: %w", err)
	}
	marker := runtimeMarkerSet(markerValue)

	runID, err := ops.resolveRun(beadID)
	if err != nil {
		if !errors.Is(err, errRuntimeRunNotBound) {
			return fmt.Errorf("runtime-evidence bind: resolve existing run: %w", err)
		}
		return fmt.Errorf("runtime-evidence bind: bead %s has no Intercore run; use `clavain-cli runtime-evidence adopt %s --project=<root> --provenance=<json>`", beadID, beadID)
	}
	if strings.TrimSpace(runID) == "" {
		return fmt.Errorf("runtime-evidence bind: bead %s has no Intercore run; use `clavain-cli runtime-evidence adopt %s --project=<root> --provenance=<json>`", beadID, beadID)
	}
	run, err := ops.loadRun(runID)
	if err != nil {
		return fmt.Errorf("runtime-evidence bind: load run %s: %w", runID, err)
	}
	_, bound, err := runtimeEvidenceMetadataState(beadID, run.Metadata)
	if err != nil {
		return fmt.Errorf("runtime-evidence bind: %w", err)
	}
	if bound {
		if err := ops.setState(beadID, "runtime_evidence_required", "1"); err != nil {
			return fmt.Errorf("runtime-evidence bind: persist durable marker: %w", err)
		}
		return nil
	}
	if !labelled && !marker {
		return fmt.Errorf("runtime-evidence bind: first activation requires label %q", runtimeEvidenceLabel)
	}
	patch, err := json.Marshal(runtimeRunMetadata{CloseGate: &runtimeCloseGateMetadata{
		Requirements: []string{runtimeEvidenceArtifactType},
		BeadID:       beadID,
	}})
	if err != nil {
		return fmt.Errorf("runtime-evidence bind: encode metadata: %w", err)
	}
	if err := ops.mergeRunMetadata(runID, string(patch)); err != nil {
		return fmt.Errorf("runtime-evidence bind: seal run metadata: %w", err)
	}
	if err := ops.setState(beadID, "runtime_evidence_required", "1"); err != nil {
		return fmt.Errorf("runtime-evidence bind: persist durable marker: %w", err)
	}
	return nil
}

func adoptRuntimeEvidence(ops runtimeEvidenceOps, beadID, projectRoot, provenancePath string) (string, error) {
	if strings.TrimSpace(beadID) == "" {
		return "", errors.New("runtime-evidence adopt: bead ID is required")
	}
	root, err := filepath.Abs(projectRoot)
	if err != nil || !filepath.IsAbs(root) {
		return "", errors.New("runtime-evidence adopt: project root must be absolute")
	}
	root = filepath.Clean(root)
	if resolvedRoot, resolveErr := filepath.EvalSymlinks(root); resolveErr == nil {
		root = filepath.Clean(resolvedRoot)
	}

	labels, err := ops.labels(beadID)
	if err != nil {
		return "", fmt.Errorf("runtime-evidence adopt: read labels: %w", err)
	}
	markerValue, err := ops.state(beadID, "runtime_evidence_required")
	if err != nil {
		return "", fmt.Errorf("runtime-evidence adopt: read durable marker: %w", err)
	}
	labelled := containsString(labels, runtimeEvidenceLabel)
	marked := runtimeMarkerSet(markerValue)

	runID, resolveErr := ops.resolveRun(beadID)
	if resolveErr != nil && !errors.Is(resolveErr, errRuntimeRunNotBound) {
		return "", fmt.Errorf("runtime-evidence adopt: resolve existing run binding: %w", resolveErr)
	}
	if resolveErr == nil && strings.TrimSpace(runID) != "" {
		run, loadErr := ops.loadRun(runID)
		if loadErr != nil {
			return "", fmt.Errorf("runtime-evidence adopt: load existing run %s: %w", runID, loadErr)
		}
		_, bound, metadataErr := runtimeEvidenceMetadataState(beadID, run.Metadata)
		if metadataErr != nil {
			return "", fmt.Errorf("runtime-evidence adopt: %w", metadataErr)
		}
		if !bound {
			return "", fmt.Errorf("runtime-evidence adopt: bead already has run %s; use `clavain-cli runtime-evidence bind %s`", runID, beadID)
		}
		if filepath.Clean(run.ProjectDir) != root {
			return "", fmt.Errorf("runtime-evidence adopt: existing run %s project root %q does not match %q", runID, run.ProjectDir, root)
		}
		if err := persistAdoptedRuntimeRun(ops, beadID, run); err != nil {
			return "", err
		}
		return runID, nil
	}

	runs, err := ops.findScopeRuns(beadID)
	if err != nil {
		return "", fmt.Errorf("runtime-evidence adopt: inspect existing scope runs: %w", err)
	}
	var recovered []Run
	for _, run := range runs {
		if run.Status == "cancelled" {
			continue
		}
		if filepath.Clean(run.ProjectDir) != root {
			return "", fmt.Errorf("runtime-evidence adopt: scope run %s project root %q does not match %q", run.ID, run.ProjectDir, root)
		}
		_, bound, metadataErr := runtimeEvidenceMetadataState(beadID, run.Metadata)
		if metadataErr != nil {
			return "", fmt.Errorf("runtime-evidence adopt: scope run %s: %w", run.ID, metadataErr)
		}
		if !bound {
			return "", fmt.Errorf("runtime-evidence adopt: conflicting unbound scope run %s already exists", run.ID)
		}
		recovered = append(recovered, run)
	}
	if len(recovered) > 1 {
		return "", fmt.Errorf("runtime-evidence adopt: %d matching runs exist for %s; refusing ambiguous adoption", len(recovered), beadID)
	}
	if len(recovered) == 1 {
		if err := persistAdoptedRuntimeRun(ops, beadID, recovered[0]); err != nil {
			return "", err
		}
		return recovered[0].ID, nil
	}
	if !labelled && !marked {
		return "", fmt.Errorf("runtime-evidence adopt: first activation requires label %q", runtimeEvidenceLabel)
	}

	adoption, err := ops.validateAdoption(root, provenancePath)
	if err != nil {
		return "", fmt.Errorf("runtime-evidence adopt: provenance: %w", err)
	}
	var adoptionObject map[string]any
	if err := decodeStrictJSON(adoption, &adoptionObject); err != nil || len(adoptionObject) == 0 {
		return "", errors.New("runtime-evidence adopt: validated provenance is not a non-empty JSON object")
	}
	metadataBytes, err := json.Marshal(map[string]any{
		"close_gate": map[string]any{
			"requirements": []string{runtimeEvidenceArtifactType},
			"bead_id":      beadID,
			"adoption":     adoptionObject,
		},
	})
	if err != nil {
		return "", fmt.Errorf("runtime-evidence adopt: encode metadata: %w", err)
	}
	spec := runtimeAdoptCreate{
		ProjectRoot: root,
		Goal:        "Adopt " + beadID + " for installed runtime verification",
		ScopeID:     beadID,
		Phases:      []string{"reflect", "done"},
		Metadata:    string(metadataBytes),
	}
	runID, err = ops.createRun(spec)
	if err != nil {
		return "", fmt.Errorf("runtime-evidence adopt: create run: %w", err)
	}
	created, err := ops.loadRun(runID)
	if err != nil {
		return "", fmt.Errorf("runtime-evidence adopt: verify created run: %w", err)
	}
	_, bound, err := runtimeEvidenceMetadataState(beadID, created.Metadata)
	if err != nil || !bound || created.Phase != "reflect" || filepath.Clean(created.ProjectDir) != root {
		return "", fmt.Errorf("runtime-evidence adopt: created run failed identity verification")
	}
	if err := persistAdoptedRuntimeRun(ops, beadID, created); err != nil {
		return "", err
	}
	return runID, nil
}

func persistAdoptedRuntimeRun(ops runtimeEvidenceOps, beadID string, run Run) error {
	phase := run.Phase
	if phase == "" {
		phase = "reflect"
	}
	for _, item := range []struct{ key, value string }{
		{"ic_run_id", run.ID},
		{"phase", phase},
		{"runtime_evidence_required", "1"},
	} {
		if err := ops.setState(beadID, item.key, item.value); err != nil {
			return fmt.Errorf("runtime-evidence adopt: persist %s: %w", item.key, err)
		}
	}
	runIDCache[beadID] = run.ID
	return nil
}

func validateRuntimeAdoptionProvenance(projectRoot, provenancePath string) (json.RawMessage, error) {
	data, err := readRuntimeRegularFile(provenancePath, 256<<10)
	if err != nil {
		return nil, fmt.Errorf("read provenance: %w", err)
	}
	var provenance runtimeAdoptionProvenanceFile
	if err := decodeStrictJSON(data, &provenance); err != nil {
		return nil, fmt.Errorf("decode provenance: %w", err)
	}
	if provenance.SchemaVersion != 1 {
		return nil, fmt.Errorf("schema_version = %d, want 1", provenance.SchemaVersion)
	}
	if len(provenance.Sources) == 0 {
		return nil, errors.New("at least one source repository HEAD is required")
	}

	planRepo, err := canonicalRuntimeGitRepository(provenance.Plan.Repository)
	if err != nil {
		return nil, fmt.Errorf("plan repository: %w", err)
	}
	planHead, err := runtimeGitOutput(planRepo, "rev-parse", "HEAD")
	if err != nil {
		return nil, fmt.Errorf("plan repository HEAD: %w", err)
	}
	planHead = strings.TrimSpace(planHead)
	if !runtimeGitHeadPattern.MatchString(provenance.Plan.Head) || provenance.Plan.Head != planHead {
		return nil, fmt.Errorf("plan repository HEAD mismatch: got %q, current %q", provenance.Plan.Head, planHead)
	}
	if filepath.IsAbs(provenance.Plan.Path) || strings.TrimSpace(provenance.Plan.Path) == "" {
		return nil, errors.New("plan path must be repository-relative")
	}
	planPath, err := joinWithinProject(planRepo, filepath.FromSlash(provenance.Plan.Path))
	if err != nil {
		return nil, fmt.Errorf("plan path: %w", err)
	}
	planRel, err := filepath.Rel(planRepo, planPath)
	if err != nil {
		return nil, fmt.Errorf("plan path: %w", err)
	}
	if _, err := runtimeGitOutput(planRepo, "ls-files", "--error-unmatch", "--", filepath.ToSlash(planRel)); err != nil {
		return nil, errors.New("plan path is not tracked at the declared repository HEAD")
	}
	planBytes, err := readRuntimeRegularFile(planPath, 256<<10)
	if err != nil {
		return nil, fmt.Errorf("read plan: %w", err)
	}
	planDigest := digestForRuntimeEvidence(planBytes)
	if provenance.Plan.Digest != planDigest {
		return nil, fmt.Errorf("plan digest mismatch: got %q, current %q", provenance.Plan.Digest, planDigest)
	}
	committedPlan, err := runtimeGitOutputBytes(planRepo, "show", "HEAD:"+filepath.ToSlash(planRel))
	if err != nil {
		return nil, fmt.Errorf("read committed plan: %w", err)
	}
	if !bytes.Equal(committedPlan, planBytes) {
		return nil, errors.New("plan worktree bytes differ from the committed plan")
	}

	projectRepo, err := canonicalRuntimeGitRepository(projectRoot)
	if err != nil {
		return nil, fmt.Errorf("project repository: %w", err)
	}
	normalizedSources := make([]runtimeAdoptionSource, 0, len(provenance.Sources))
	seen := make(map[string]struct{}, len(provenance.Sources))
	projectFound := false
	for _, source := range provenance.Sources {
		repo, repoErr := canonicalRuntimeGitRepository(source.Repository)
		if repoErr != nil {
			return nil, fmt.Errorf("source repository %q: %w", source.Repository, repoErr)
		}
		if _, exists := seen[repo]; exists {
			return nil, fmt.Errorf("duplicate source repository %q", repo)
		}
		seen[repo] = struct{}{}
		currentHead, headErr := runtimeGitOutput(repo, "rev-parse", "HEAD")
		if headErr != nil {
			return nil, fmt.Errorf("source repository %q HEAD: %w", repo, headErr)
		}
		currentHead = strings.TrimSpace(currentHead)
		if !runtimeGitHeadPattern.MatchString(source.Head) || source.Head != currentHead {
			return nil, fmt.Errorf("source repository %q HEAD mismatch: got %q, current %q", repo, source.Head, currentHead)
		}
		if repo == projectRepo {
			projectFound = true
		}
		normalizedSources = append(normalizedSources, runtimeAdoptionSource{Repository: repo, Head: currentHead})
	}
	if !projectFound {
		return nil, errors.New("project repository is missing from source repository HEADs")
	}
	sort.Slice(normalizedSources, func(i, j int) bool { return normalizedSources[i].Repository < normalizedSources[j].Repository })
	normalized := runtimeAdoptionProvenanceFile{
		SchemaVersion: 1,
		Plan: runtimeAdoptionPlan{
			Repository: planRepo, Path: filepath.ToSlash(planRel), Digest: planDigest, Head: planHead,
		},
		Sources: normalizedSources,
	}
	encoded, err := json.Marshal(normalized)
	if err != nil {
		return nil, fmt.Errorf("encode normalized provenance: %w", err)
	}
	return encoded, nil
}

func canonicalRuntimeGitRepository(path string) (string, error) {
	if !filepath.IsAbs(path) {
		return "", errors.New("repository path must be absolute")
	}
	top, err := runtimeGitOutput(path, "rev-parse", "--show-toplevel")
	if err != nil {
		return "", err
	}
	top = filepath.Clean(strings.TrimSpace(top))
	resolved, err := filepath.EvalSymlinks(top)
	if err != nil {
		return "", err
	}
	return filepath.Clean(resolved), nil
}

func runtimeGitOutput(repo string, args ...string) (string, error) {
	out, err := runtimeGitOutputBytes(repo, args...)
	return string(out), err
}

func runtimeGitOutputBytes(repo string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	cmdArgs := append([]string{"-C", repo}, args...)
	cmd := exec.CommandContext(ctx, "git", cmdArgs...)
	out, err := cmd.Output()
	if ctx.Err() != nil {
		return nil, fmt.Errorf("git timed out: %w", ctx.Err())
	}
	if err != nil {
		return nil, err
	}
	return out, nil
}

func readRuntimeRegularFile(path string, limit int64) ([]byte, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, errors.New("path is not a regular file")
	}
	if info.Size() > limit {
		return nil, fmt.Errorf("file exceeds %d-byte limit", limit)
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil {
		return nil, err
	}
	if !os.SameFile(info, opened) || !opened.Mode().IsRegular() {
		return nil, errors.New("file identity changed while opening")
	}
	data, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > limit {
		return nil, fmt.Errorf("file exceeds %d-byte limit", limit)
	}
	return data, nil
}

func hashRuntimeRegularFile(path string, limit int64) (string, os.FileMode, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return "", 0, err
	}
	if !info.Mode().IsRegular() {
		return "", 0, errors.New("path is not a regular file")
	}
	if info.Size() > limit {
		return "", 0, fmt.Errorf("file exceeds %d-byte limit", limit)
	}
	file, err := os.Open(path)
	if err != nil {
		return "", 0, err
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil {
		return "", 0, err
	}
	if !opened.Mode().IsRegular() || !os.SameFile(info, opened) {
		return "", 0, errors.New("file identity changed while opening")
	}
	hash := sha256.New()
	written, err := io.Copy(hash, io.LimitReader(file, limit+1))
	if err != nil {
		return "", 0, err
	}
	if written > limit {
		return "", 0, fmt.Errorf("file exceeds %d-byte limit", limit)
	}
	return fmt.Sprintf("sha256:%x", hash.Sum(nil)), opened.Mode(), nil
}

func newRuntimeEvidenceID() (string, error) {
	data := make([]byte, 16)
	if _, err := io.ReadFull(rand.Reader, data); err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", data), nil
}

func runtimeEvidenceStateDir(projectRoot string) (string, error) {
	base := strings.TrimSpace(os.Getenv("XDG_STATE_HOME"))
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		base = filepath.Join(home, ".local", "state")
	}
	if !filepath.IsAbs(base) {
		return "", errors.New("XDG_STATE_HOME must be absolute")
	}
	projectHash := strings.TrimPrefix(digestForRuntimeEvidence([]byte(filepath.Clean(projectRoot))), "sha256:")[:16]
	dir := filepath.Join(base, "clavain", "runtime-evidence", projectHash)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	info, err := os.Lstat(dir)
	if err != nil {
		return "", err
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return "", errors.New("runtime evidence state path is not a private directory")
	}
	if err := os.Chmod(dir, 0o700); err != nil {
		return "", err
	}
	return dir, nil
}

func removeRuntimePrivateRoot(path string) error {
	if err := os.RemoveAll(path); err != nil {
		return err
	}
	if _, err := os.Lstat(path); !errors.Is(err, os.ErrNotExist) {
		if err == nil {
			return errors.New("private probe directory still exists")
		}
		return err
	}
	return nil
}

func runtimeEvidenceEnvironment(generated map[string]string) []string {
	allowed := map[string]bool{
		"HOME": true, "PATH": true, "TMPDIR": true,
		"LANG": true, "LC_ALL": true, "SSL_CERT_FILE": true, "SSL_CERT_DIR": true,
		"XDG_RUNTIME_DIR": true,
	}
	env := make([]string, 0, len(allowed)+len(generated))
	for _, entry := range os.Environ() {
		key, _, ok := strings.Cut(entry, "=")
		if ok && allowed[key] {
			env = append(env, entry)
		}
	}
	keys := make([]string, 0, len(generated))
	for key := range generated {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		env = append(env, key+"="+generated[key])
	}
	return env
}

type runtimeLimitedCapture struct {
	mu       sync.Mutex
	limit    int
	data     []byte
	overflow bool
}

func (capture *runtimeLimitedCapture) Write(data []byte) (int, error) {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	remaining := capture.limit - len(capture.data)
	if remaining > 0 {
		keep := len(data)
		if keep > remaining {
			keep = remaining
		}
		capture.data = append(capture.data, data[:keep]...)
	}
	if len(data) > remaining {
		capture.overflow = true
	}
	return len(data), nil
}

func (capture *runtimeLimitedCapture) bytes() []byte {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	return append([]byte(nil), capture.data...)
}

func (capture *runtimeLimitedCapture) overflowed() bool {
	capture.mu.Lock()
	defer capture.mu.Unlock()
	return capture.overflow
}

type runtimeManagedProcess struct {
	cmd     *exec.Cmd
	pid     int
	done    chan struct{}
	mu      sync.Mutex
	waitErr error
	stdout  *runtimeLimitedCapture
	stderr  *runtimeLimitedCapture
}

func startRuntimeManagedProcess(argv, env []string, dir string, outputLimit int) (*runtimeManagedProcess, error) {
	if len(argv) == 0 {
		return nil, errors.New("empty command")
	}
	stdout := &runtimeLimitedCapture{limit: outputLimit}
	stderr := &runtimeLimitedCapture{limit: outputLimit}
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Dir = dir
	cmd.Env = env
	cmd.Stdout = stdout
	cmd.Stderr = stderr
	if err := configureRuntimeProcessIsolation(cmd); err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	process := &runtimeManagedProcess{
		cmd: cmd, pid: cmd.Process.Pid, done: make(chan struct{}), stdout: stdout, stderr: stderr,
	}
	go func() {
		err := cmd.Wait()
		process.mu.Lock()
		process.waitErr = err
		process.mu.Unlock()
		close(process.done)
	}()
	return process, nil
}

func (process *runtimeManagedProcess) exited() (bool, error) {
	select {
	case <-process.done:
		process.mu.Lock()
		defer process.mu.Unlock()
		return true, process.waitErr
	default:
		return false, nil
	}
}

func (process *runtimeManagedProcess) stop(timeout time.Duration) error {
	return stopRuntimeProcessIsolation(process, timeout)
}

func waitRuntimeEndpointDiscovery(path, privateRoot string, startedAt time.Time, timeout time.Duration, process *runtimeManagedProcess) (runtimeEndpointDiscovery, error) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if exited, exitErr := process.exited(); exited {
			return runtimeEndpointDiscovery{}, fmt.Errorf("installed runtime exited before endpoint discovery: %v; stderr=%s", exitErr, strings.TrimSpace(string(process.stderr.bytes())))
		}
		info, err := os.Lstat(path)
		if err == nil {
			if !info.Mode().IsRegular() || info.ModTime().Before(startedAt.Add(-time.Second)) {
				return runtimeEndpointDiscovery{}, errors.New("endpoint discovery file is stale or non-regular")
			}
			data, readErr := readRuntimeRegularFile(path, 64<<10)
			if readErr != nil {
				return runtimeEndpointDiscovery{}, readErr
			}
			var discovery runtimeEndpointDiscovery
			if decodeErr := decodeStrictJSON(data, &discovery); decodeErr != nil {
				return runtimeEndpointDiscovery{}, fmt.Errorf("decode endpoint discovery: %w", decodeErr)
			}
			if validateErr := validateRuntimeEndpointDiscovery(discovery, privateRoot, startedAt); validateErr != nil {
				return runtimeEndpointDiscovery{}, validateErr
			}
			return discovery, nil
		}
		if !errors.Is(err, os.ErrNotExist) {
			return runtimeEndpointDiscovery{}, err
		}
		time.Sleep(20 * time.Millisecond)
	}
	return runtimeEndpointDiscovery{}, errors.New("timed out waiting for fresh endpoint discovery")
}

func runRuntimeBoundedCommand(argv, env []string, dir string, timeout time.Duration, outputLimit int) ([]byte, error) {
	process, err := startRuntimeManagedProcess(argv, env, dir, outputLimit)
	if err != nil {
		return nil, err
	}
	select {
	case <-process.done:
	case <-time.After(timeout):
		if cleanupErr := process.stop(time.Second); cleanupErr != nil {
			return nil, fmt.Errorf("command timed out and process-group cleanup failed: %w", cleanupErr)
		}
		return nil, errors.New("command timed out")
	}
	process.mu.Lock()
	waitErr := process.waitErr
	process.mu.Unlock()
	if err := process.stop(time.Second); err != nil {
		return nil, fmt.Errorf("command process-group cleanup: %w", err)
	}
	if process.stdout.overflowed() || process.stderr.overflowed() {
		return nil, errors.New("command output exceeded limit")
	}
	if waitErr != nil {
		return nil, fmt.Errorf("command failed: %w; stderr=%s", waitErr, strings.TrimSpace(string(process.stderr.bytes())))
	}
	return process.stdout.bytes(), nil
}

func verifyRuntimeResourceCleanup(resources []runtimeObservedResource) error {
	for _, resource := range resources {
		switch resource.Kind {
		case "port":
			connection, err := net.DialTimeout("tcp", resource.Identifier, 150*time.Millisecond)
			if err == nil {
				connection.Close()
				return fmt.Errorf("loopback port %s still accepts connections", digestForRuntimeEvidence([]byte(resource.Identifier)))
			}
			if !runtimePortCleanupConfirmed(err) {
				return fmt.Errorf("loopback port cleanup is UNVERIFIABLE: %w", err)
			}
		case "path":
			if _, err := os.Lstat(resource.Identifier); !errors.Is(err, os.ErrNotExist) {
				return fmt.Errorf("private path %s remains", digestForRuntimeEvidence([]byte(resource.Identifier)))
			}
		default:
			return fmt.Errorf("resource kind %q is UNVERIFIABLE", resource.Kind)
		}
	}
	return nil
}

func runtimePortCleanupConfirmed(err error) bool {
	return isRuntimeConnectionRefused(err)
}

func writeAndVerifyRuntimeReceipt(stateDir, beadID string, run Run, receipt runtimeproof.Receipt, expectations runtimeproof.Expectations) (string, *runtimeproof.Result, error) {
	data, err := json.Marshal(receipt)
	if err != nil {
		return "", nil, err
	}
	data = append(data, '\n')
	temp, err := os.CreateTemp(stateDir, ".receipt-*.tmp")
	if err != nil {
		return "", nil, err
	}
	tempPath := temp.Name()
	committed := false
	defer func() {
		_ = temp.Close()
		if !committed {
			_ = os.Remove(tempPath)
		}
	}()
	if err := temp.Chmod(0o600); err != nil {
		return "", nil, err
	}
	if _, err := temp.Write(data); err != nil {
		return "", nil, err
	}
	if err := temp.Sync(); err != nil {
		return "", nil, err
	}
	if err := temp.Close(); err != nil {
		return "", nil, err
	}
	proofHash := digestForRuntimeEvidence(data)
	result, err := runtimeproof.VerifyFile(context.Background(), tempPath, runtimeproof.VerifyOptions{
		ExpectedBeadID:       beadID,
		ExpectedRunID:        run.ID,
		ExpectedProjectRoot:  filepath.Clean(run.ProjectDir),
		ExpectedArtifactHash: proofHash,
		RunCreatedAt:         time.Unix(run.CreatedAt, 0),
		Expectations:         expectations,
	})
	if err != nil {
		return "", nil, err
	}
	safeBead := regexp.MustCompile(`[^A-Za-z0-9._-]+`).ReplaceAllString(beadID, "_")
	suffix, err := newRuntimeEvidenceID()
	if err != nil {
		return "", nil, err
	}
	finalPath := filepath.Join(stateDir, safeBead+"-"+suffix+".json")
	if err := os.Rename(tempPath, finalPath); err != nil {
		return "", nil, err
	}
	committed = true
	if err := os.Chmod(finalPath, 0o600); err != nil {
		return "", nil, err
	}
	return finalPath, result, nil
}

func runtimeEvidenceRequiredState(beadID string, labelled, marker bool, metadata string) (bool, error) {
	_, bound, err := runtimeEvidenceMetadataState(beadID, metadata)
	if err != nil {
		return false, err
	}
	return labelled || marker || bound, nil
}

func runtimeEvidenceMetadataState(beadID, metadata string) (runtimeRunMetadata, bool, error) {
	var decoded runtimeRunMetadata
	if strings.TrimSpace(metadata) == "" {
		return decoded, false, nil
	}
	var top map[string]json.RawMessage
	if err := json.Unmarshal([]byte(metadata), &top); err != nil {
		return decoded, false, fmt.Errorf("runtime evidence run metadata: %w", err)
	}
	if raw, exists := top["close_gate"]; exists {
		if err := decodeStrictJSON(raw, &decoded.CloseGate); err != nil {
			return decoded, false, fmt.Errorf("runtime evidence close_gate metadata: %w", err)
		}
	}
	if decoded.CloseGate == nil {
		return decoded, false, nil
	}
	seen := make(map[string]struct{}, len(decoded.CloseGate.Requirements))
	bound := false
	for _, requirement := range decoded.CloseGate.Requirements {
		if strings.TrimSpace(requirement) == "" {
			return decoded, false, errors.New("runtime evidence requirements contain a blank value")
		}
		if _, exists := seen[requirement]; exists {
			return decoded, false, fmt.Errorf("runtime evidence requirements contain duplicate %q", requirement)
		}
		seen[requirement] = struct{}{}
		if requirement == runtimeEvidenceArtifactType {
			bound = true
		}
	}
	if bound && decoded.CloseGate.BeadID != beadID {
		return decoded, false, fmt.Errorf("runtime evidence bead mismatch: run metadata names %q, expected %q", decoded.CloseGate.BeadID, beadID)
	}
	return decoded, bound, nil
}

func runtimeMarkerSet(value string) bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "yes", "required":
		return true
	default:
		return false
	}
}

func containsString(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func resolveRuntimeEvidenceConfig(projectRoot string, cfg runtimeEvidenceConfigFile) (resolvedRuntimeEvidenceConfig, error) {
	if cfg.SchemaVersion != 1 {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence config schema_version = %d, want 1", cfg.SchemaVersion)
	}
	root, err := filepath.Abs(projectRoot)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("resolve project root: %w", err)
	}
	root = filepath.Clean(root)
	if cfg.BuildPath == "" || filepath.IsAbs(cfg.BuildPath) {
		return resolvedRuntimeEvidenceConfig{}, errors.New("runtime evidence build_path must be project-relative")
	}
	buildPath, err := joinWithinProject(root, cfg.BuildPath)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence build_path: %w", err)
	}

	platform := runtime.GOOS + "-" + runtime.GOARCH
	installedPath, ok := cfg.InstalledPaths[platform]
	if !ok || strings.TrimSpace(installedPath) == "" {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence config has no installed_paths entry for %s", platform)
	}
	if !filepath.IsAbs(installedPath) {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence installed path for %s must be absolute", platform)
	}
	if err := rejectUnsupportedExpansion(installedPath); err != nil {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence installed path: %w", err)
	}
	installedPath = filepath.Clean(installedPath)
	if buildPath == installedPath {
		return resolvedRuntimeEvidenceConfig{}, errors.New("runtime evidence build and installed paths must be distinct")
	}

	if cfg.TimeoutSeconds <= 0 || cfg.TimeoutSeconds > 300 {
		return resolvedRuntimeEvidenceConfig{}, errors.New("runtime evidence timeout_seconds must be between 1 and 300")
	}
	startArgv, err := resolveRuntimeArgv(root, installedPath, cfg.StartArgv)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence start_argv: %w", err)
	}
	if filepath.Clean(startArgv[0]) != installedPath {
		return resolvedRuntimeEvidenceConfig{}, errors.New("runtime evidence start executable must be the installed path")
	}
	probeArgv, err := resolveRuntimeArgv(root, installedPath, cfg.ProbeArgv)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence probe_argv: %w", err)
	}
	if !filepath.IsAbs(probeArgv[0]) {
		return resolvedRuntimeEvidenceConfig{}, errors.New("runtime evidence probe executable must resolve inside the project root")
	}
	probeDigest, ok := cfg.ProbeDigests[platform]
	if !ok || !runtimeDigestPattern.MatchString(probeDigest) {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence config has no valid probe_digests entry for %s", platform)
	}
	probeRel, err := filepath.Rel(root, filepath.Clean(probeArgv[0]))
	if err != nil || probeRel == ".." || strings.HasPrefix(probeRel, ".."+string(filepath.Separator)) {
		return resolvedRuntimeEvidenceConfig{}, errors.New("runtime evidence probe executable must resolve inside the project root")
	}

	notApplicable := make(map[string]bool, len(cfg.NotApplicableFailureClasses))
	for _, class := range cfg.NotApplicableFailureClasses {
		if notApplicable[class] {
			return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence duplicate NOT_APPLICABLE failure class %q", class)
		}
		notApplicable[class] = true
	}
	expectations := runtimeproof.Expectations{
		ExpectedBuildPath:           buildPath,
		ExpectedInstalledPath:       installedPath,
		RequiredSubsystems:          append([]string(nil), cfg.RequiredSubsystems...),
		NotApplicableFailureClasses: notApplicable,
		RequiredAssertions:          append([]string(nil), cfg.RequiredAssertions...),
		ExpectedSurfaces:            append([]string(nil), cfg.ExpectedSurfaces...),
		RequiredResources:           append([]runtimeproof.ResourceExpectation(nil), cfg.RequiredResources...),
	}
	if err := runtimeproof.ValidateExpectations(expectations); err != nil {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence config expectations: %w", err)
	}
	return resolvedRuntimeEvidenceConfig{
		BuildPath: buildPath, InstalledPath: installedPath,
		StartArgv: startArgv, ProbeArgv: probeArgv,
		ProbeDigest:  probeDigest,
		Timeout:      time.Duration(cfg.TimeoutSeconds) * time.Second,
		Expectations: expectations,
	}, nil
}

func loadRuntimeEvidenceConfig(projectRoot, configPath string) (resolvedRuntimeEvidenceConfig, string, error) {
	root, err := filepath.Abs(projectRoot)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, "", fmt.Errorf("runtime evidence project root: %w", err)
	}
	root = filepath.Clean(root)
	if resolvedRoot, resolveErr := filepath.EvalSymlinks(root); resolveErr == nil {
		root = filepath.Clean(resolvedRoot)
	}
	path := configPath
	if !filepath.IsAbs(path) {
		path, err = joinWithinProject(root, path)
		if err != nil {
			return resolvedRuntimeEvidenceConfig{}, "", fmt.Errorf("runtime evidence config path: %w", err)
		}
	}
	path = filepath.Clean(path)
	originalInfo, originalErr := os.Lstat(path)
	if originalErr != nil {
		return resolvedRuntimeEvidenceConfig{}, "", fmt.Errorf("runtime evidence config: %w", originalErr)
	}
	if originalInfo.Mode()&os.ModeSymlink != 0 {
		return resolvedRuntimeEvidenceConfig{}, "", errors.New("runtime evidence config must not be a symlink")
	}
	if resolvedPath, resolveErr := filepath.EvalSymlinks(path); resolveErr == nil {
		path = filepath.Clean(resolvedPath)
	}
	data, err := readRuntimeRegularFile(path, 256<<10)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, "", fmt.Errorf("runtime evidence config: %w", err)
	}
	rel, relErr := filepath.Rel(root, path)
	if relErr != nil || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return resolvedRuntimeEvidenceConfig{}, "", errors.New("runtime evidence config must be inside the project root")
	}
	repo, repoErr := canonicalRuntimeGitRepository(root)
	if repoErr != nil {
		return resolvedRuntimeEvidenceConfig{}, "", fmt.Errorf("runtime evidence config repository: %w", repoErr)
	}
	repoRel, relErr := filepath.Rel(repo, path)
	if relErr != nil || repoRel == ".." || strings.HasPrefix(repoRel, ".."+string(filepath.Separator)) {
		return resolvedRuntimeEvidenceConfig{}, "", errors.New("runtime evidence config is not inside the project repository")
	}
	repoRel = filepath.ToSlash(repoRel)
	if _, gitErr := runtimeGitOutput(repo, "ls-files", "--error-unmatch", "--", repoRel); gitErr != nil {
		return resolvedRuntimeEvidenceConfig{}, "", errors.New("runtime evidence config inside the project must be tracked")
	}
	committed, gitErr := runtimeGitOutputBytes(repo, "show", "HEAD:"+repoRel)
	if gitErr != nil {
		return resolvedRuntimeEvidenceConfig{}, "", fmt.Errorf("read committed runtime evidence config: %w", gitErr)
	}
	if !bytes.Equal(committed, data) {
		return resolvedRuntimeEvidenceConfig{}, "", errors.New("runtime evidence config bytes differ from the committed version")
	}
	var cfg runtimeEvidenceConfigFile
	if err := decodeStrictJSON(data, &cfg); err != nil {
		return resolvedRuntimeEvidenceConfig{}, "", fmt.Errorf("runtime evidence config decode: %w", err)
	}
	resolved, err := resolveRuntimeEvidenceConfig(root, cfg)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, "", err
	}
	resolved, err = canonicalizeRuntimeCollectorPaths(root, resolved)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, "", err
	}
	return resolved, digestForRuntimeEvidence(data), nil
}

func canonicalizeRuntimeCollectorPaths(projectRoot string, resolved resolvedRuntimeEvidenceConfig) (resolvedRuntimeEvidenceConfig, error) {
	root, err := filepath.EvalSymlinks(projectRoot)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence project root: %w", err)
	}
	root = filepath.Clean(root)
	canonicalFile := func(label, path string, mustBeInProject bool) (string, os.FileMode, error) {
		info, statErr := os.Lstat(path)
		if statErr != nil {
			return "", 0, fmt.Errorf("runtime evidence %s: %w", label, statErr)
		}
		if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return "", 0, fmt.Errorf("runtime evidence %s must be a non-symlink regular file", label)
		}
		canonical, resolveErr := filepath.EvalSymlinks(path)
		if resolveErr != nil {
			return "", 0, fmt.Errorf("runtime evidence %s: %w", label, resolveErr)
		}
		canonical = filepath.Clean(canonical)
		if mustBeInProject {
			rel, relErr := filepath.Rel(root, canonical)
			if relErr != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
				return "", 0, fmt.Errorf("runtime evidence %s resolves outside the project root", label)
			}
		}
		return canonical, info.Mode(), nil
	}

	buildPath, _, err := canonicalFile("build artifact", resolved.BuildPath, true)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, err
	}
	installedPath, installedMode, err := canonicalFile("installed artifact", resolved.InstalledPath, false)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, err
	}
	if installedMode&0o111 == 0 {
		return resolvedRuntimeEvidenceConfig{}, errors.New("runtime evidence installed artifact is not executable")
	}
	probePath, probeMode, err := canonicalFile("probe executable", resolved.ProbeArgv[0], true)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, err
	}
	if probeMode&0o111 == 0 {
		return resolvedRuntimeEvidenceConfig{}, errors.New("runtime evidence probe executable is not executable")
	}
	probeDigest, _, err := hashRuntimeRegularFile(probePath, runtimeproof.DefaultMaxArtifactBytes)
	if err != nil {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence probe digest: %w", err)
	}
	if probeDigest != resolved.ProbeDigest {
		return resolvedRuntimeEvidenceConfig{}, fmt.Errorf("runtime evidence probe digest mismatch: got %s, want %s", probeDigest, resolved.ProbeDigest)
	}
	resolved.BuildPath = buildPath
	resolved.InstalledPath = installedPath
	resolved.StartArgv[0] = installedPath
	resolved.ProbeArgv[0] = probePath
	resolved.Expectations.ExpectedBuildPath = buildPath
	resolved.Expectations.ExpectedInstalledPath = installedPath
	return resolved, nil
}

func joinWithinProject(root, relative string) (string, error) {
	clean := filepath.Clean(relative)
	if clean == "." || clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return "", errors.New("path escapes project root")
	}
	joined := filepath.Join(root, clean)
	rel, err := filepath.Rel(root, joined)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", errors.New("path escapes project root")
	}
	return filepath.Clean(joined), nil
}

func resolveRuntimeArgv(projectRoot, installedPath string, argv []string) ([]string, error) {
	if len(argv) == 0 || strings.TrimSpace(argv[0]) == "" {
		return nil, errors.New("argv must contain an executable")
	}
	resolved := make([]string, len(argv))
	for idx, arg := range argv {
		if err := rejectUnsupportedExpansion(arg); err != nil {
			return nil, err
		}
		arg = strings.ReplaceAll(arg, "{project_root}", projectRoot)
		arg = strings.ReplaceAll(arg, "{installed_path}", installedPath)
		if strings.Contains(arg, "{") || strings.Contains(arg, "}") {
			return nil, fmt.Errorf("unsupported token in argument %q", argv[idx])
		}
		if idx == 0 {
			if filepath.IsAbs(arg) {
				arg = filepath.Clean(arg)
			} else {
				var err error
				arg, err = joinWithinProject(projectRoot, arg)
				if err != nil {
					return nil, err
				}
			}
		}
		resolved[idx] = arg
	}
	return resolved, nil
}

func rejectUnsupportedExpansion(value string) error {
	if strings.Contains(value, "$") {
		return fmt.Errorf("unsupported token or environment expansion in %q", value)
	}
	return nil
}

func buildRuntimeEvidenceReceipt(input runtimeReceiptInput, obs runtimeProbeObservations) (runtimeproof.Receipt, error) {
	if obs.SchemaVersion != 1 {
		return runtimeproof.Receipt{}, fmt.Errorf("runtime probe schema_version = %d, want 1", obs.SchemaVersion)
	}
	if obs.ObservedNonce != input.InstanceNonce {
		return runtimeproof.Receipt{}, errors.New("runtime probe nonce mismatch")
	}
	if obs.ObservedEventID != input.EventID {
		return runtimeproof.Receipt{}, errors.New("runtime probe event correlation mismatch")
	}
	if len(obs.FailureClasses) != 4 {
		return runtimeproof.Receipt{}, errors.New("runtime probe must report all four failure classes")
	}
	failureClasses := make(map[string]runtimeproof.State, len(obs.FailureClasses))
	for name, result := range obs.FailureClasses {
		if strings.TrimSpace(result.Evidence) == "" {
			return runtimeproof.Receipt{}, fmt.Errorf("runtime probe failure class %q has no evidence", name)
		}
		failureClasses[name] = result.State
	}
	if len(obs.Resources) != len(input.Expectations.RequiredResources) {
		return runtimeproof.Receipt{}, errors.New("runtime probe resource count does not match trusted expectations")
	}
	resources := make([]runtimeproof.Resource, len(obs.Resources))
	for idx, observed := range obs.Resources {
		expected := input.Expectations.RequiredResources[idx]
		if observed.Kind != expected.Kind {
			return runtimeproof.Receipt{}, fmt.Errorf("runtime probe resource %d kind %q does not match trusted kind %q", idx, observed.Kind, expected.Kind)
		}
		if strings.TrimSpace(observed.Identifier) == "" {
			return runtimeproof.Receipt{}, fmt.Errorf("runtime probe resource %d has an empty identifier", idx)
		}
		resources[idx] = runtimeproof.Resource{
			Kind: observed.Kind, Fingerprint: digestForRuntimeEvidence([]byte(observed.Identifier)), Ownership: expected.Ownership,
		}
	}
	collisions := make([]string, len(obs.Collisions))
	for idx, collision := range obs.Collisions {
		collisions[idx] = digestForRuntimeEvidence([]byte(collision))
	}
	createdAt := input.CreatedAt.UTC()
	if createdAt.IsZero() {
		createdAt = time.Now().UTC()
	}
	startedAt := input.StartedAt.UTC()
	if startedAt.IsZero() {
		startedAt = createdAt
	}
	return runtimeproof.Receipt{
		SchemaVersion: runtimeproof.SchemaVersion,
		Subject: runtimeproof.Subject{
			BeadID: input.BeadID, RunID: input.RunID, ProjectRoot: input.ProjectRoot,
			GitHead: input.GitHead, Host: input.Host, CreatedAt: createdAt.Format(time.RFC3339Nano),
		},
		Artifact: runtimeproof.Artifact{
			Kind: "file", BuildPath: input.Expectations.ExpectedBuildPath, InstalledPath: input.Expectations.ExpectedInstalledPath,
			BuildDigest: input.BuildDigest, InstalledDigest: input.InstalledDigest, RuntimeDigest: input.InstalledDigest,
		},
		Boot: runtimeproof.Boot{
			StartedForProbe: true, ProcessID: input.ProcessID, StartedAt: startedAt.Format(time.RFC3339Nano),
			InstanceNonce: input.InstanceNonce, ObservedNonce: obs.ObservedNonce, State: runtimeproof.StateVerified,
		},
		Health: runtimeproof.Health{
			RequiredSubsystems: append([]string(nil), input.Expectations.RequiredSubsystems...),
			Observed:           copyRuntimeStringMap(obs.Subsystems), FailureClasses: failureClasses,
		},
		Event: runtimeproof.Event{
			EventID: input.EventID, ObservedEventID: obs.ObservedEventID,
			BeforeDigest: obs.BeforeDigest, AfterDigest: obs.AfterDigest,
			Assertions: append([]runtimeproof.Assertion(nil), obs.Assertions...),
		},
		SurfaceScan: runtimeproof.SurfaceScan{
			Expected: append([]string(nil), input.Expectations.ExpectedSurfaces...),
			Observed: append([]string(nil), obs.ObservedSurfaces...), Missing: []string{}, Unexpected: []string{},
		},
		Isolation: runtimeproof.Isolation{Resources: resources, Collisions: collisions},
		Cleanup:   runtimeproof.Cleanup{OwnedResourcesRemaining: []string{}},
	}, nil
}

func validateRuntimeEndpointDiscovery(discovery runtimeEndpointDiscovery, privateRoot string, startedAt time.Time) error {
	if discovery.SchemaVersion != 1 {
		return fmt.Errorf("runtime endpoint discovery schema_version = %d, want 1", discovery.SchemaVersion)
	}
	parsed, err := url.Parse(discovery.Endpoint)
	if err != nil || parsed.Scheme != "http" {
		return errors.New("runtime endpoint must use http on a loopback IP literal")
	}
	if parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || (parsed.Path != "" && parsed.Path != "/") {
		return errors.New("runtime endpoint must be an unadorned loopback origin")
	}
	host := parsed.Hostname()
	ip := net.ParseIP(host)
	if ip == nil {
		return errors.New("runtime endpoint host must be a loopback IP literal")
	}
	if !ip.IsLoopback() {
		return errors.New("runtime endpoint must be loopback")
	}
	port := parsed.Port()
	portNumber, err := strconv.Atoi(port)
	if err != nil || portNumber < 1 || portNumber > 65535 {
		return errors.New("runtime endpoint must name a valid loopback port")
	}
	if len(discovery.Resources) == 0 {
		return errors.New("runtime endpoint discovery has no isolated resources")
	}
	privateRoot, err = filepath.Abs(privateRoot)
	if err != nil {
		return fmt.Errorf("resolve private root: %w", err)
	}
	privateRoot = filepath.Clean(privateRoot)
	seen := make(map[string]struct{}, len(discovery.Resources))
	portMatched := false
	for _, resource := range discovery.Resources {
		key := resource.Kind + "\x00" + resource.Identifier
		if _, exists := seen[key]; exists {
			return errors.New("runtime endpoint discovery contains duplicate resources")
		}
		seen[key] = struct{}{}
		switch resource.Kind {
		case "port":
			resourceHost, resourcePort, splitErr := net.SplitHostPort(resource.Identifier)
			resourceIP := net.ParseIP(resourceHost)
			if splitErr != nil || resourceIP == nil || !resourceIP.IsLoopback() {
				return errors.New("runtime port resource must be a loopback IP literal and port")
			}
			if resourcePort == port && resourceIP.Equal(ip) {
				portMatched = true
			}
		case "path":
			if _, pathErr := validateRuntimePathResource(resource.Identifier, privateRoot, startedAt); pathErr != nil {
				return pathErr
			}
		default:
			return fmt.Errorf("runtime resource kind %q is UNVERIFIABLE", resource.Kind)
		}
	}
	if !portMatched {
		return errors.New("runtime endpoint port is not declared as an owned resource")
	}
	return nil
}

func validateRuntimePathResource(path, privateRoot string, startedAt time.Time) (string, error) {
	if !filepath.IsAbs(path) {
		return "", errors.New("runtime path resource must be absolute and private")
	}
	root, err := filepath.EvalSymlinks(privateRoot)
	if err != nil {
		return "", fmt.Errorf("runtime path private root: %w", err)
	}
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return "", errors.New("runtime path resource must exist when discovered")
	}
	if err != nil {
		return "", fmt.Errorf("runtime path resource: %w", err)
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return "", errors.New("runtime path resource must not be a symlink")
	}
	if !info.Mode().IsRegular() && !info.IsDir() {
		return "", errors.New("runtime path resource must be a regular file or directory")
	}
	if !startedAt.IsZero() && info.ModTime().Before(startedAt.Add(-time.Second)) {
		return "", errors.New("runtime path resource is not fresh for this collector launch")
	}
	canonical, err := filepath.EvalSymlinks(path)
	if err != nil {
		return "", fmt.Errorf("runtime path resource: %w", err)
	}
	canonical = filepath.Clean(canonical)
	rel, err := filepath.Rel(filepath.Clean(root), canonical)
	if err != nil || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", errors.New("runtime path resource is outside the collector private root")
	}
	return canonical, nil
}

func validateRuntimeProbeScope(obs runtimeProbeObservations, discovery runtimeEndpointDiscovery, expectations runtimeproof.Expectations, instanceNonce, eventID string) error {
	if obs.SchemaVersion != 1 {
		return fmt.Errorf("runtime probe schema_version = %d, want 1", obs.SchemaVersion)
	}
	if obs.ObservedNonce != instanceNonce {
		return errors.New("runtime probe nonce does not identify the collector-started instance")
	}
	if obs.ObservedEventID != eventID {
		return errors.New("runtime probe event correlation mismatch")
	}
	if len(obs.Subsystems) != len(expectations.RequiredSubsystems) {
		return errors.New("runtime probe subsystem scope differs from trusted expectations")
	}
	for _, subsystem := range expectations.RequiredSubsystems {
		if obs.Subsystems[subsystem] != "healthy" {
			return fmt.Errorf("runtime probe subsystem %q is not healthy", subsystem)
		}
	}
	requiredClasses := []string{"startup", "dependency_injection", "connection", "projection_catchup"}
	if len(obs.FailureClasses) != len(requiredClasses) {
		return errors.New("runtime probe must report exactly four failure classes")
	}
	for _, class := range requiredClasses {
		result, ok := obs.FailureClasses[class]
		if !ok {
			return fmt.Errorf("runtime probe failure class %q is missing", class)
		}
		if strings.TrimSpace(result.Evidence) == "" {
			return fmt.Errorf("runtime probe failure class %q has no evidence", class)
		}
		if class == "startup" && result.State != runtimeproof.StateVerified {
			return fmt.Errorf("runtime probe startup = %s", result.State)
		}
		if result.State == runtimeproof.StateNotApplicable && !expectations.NotApplicableFailureClasses[class] {
			return fmt.Errorf("runtime probe failure class %q is NOT_APPLICABLE without authorization", class)
		}
		if result.State != runtimeproof.StateVerified && result.State != runtimeproof.StateNotApplicable {
			return fmt.Errorf("runtime probe failure class %q = %s", class, result.State)
		}
	}
	if !runtimeDigestPattern.MatchString(obs.BeforeDigest) || !runtimeDigestPattern.MatchString(obs.AfterDigest) || obs.BeforeDigest == obs.AfterDigest {
		return errors.New("runtime probe event did not produce a valid state delta")
	}
	assertionNames := make([]string, 0, len(obs.Assertions))
	for _, assertion := range obs.Assertions {
		if assertion.State != runtimeproof.StateVerified || strings.TrimSpace(assertion.Evidence) == "" {
			return fmt.Errorf("runtime probe assertion %q is not VERIFIED with evidence", assertion.Name)
		}
		assertionNames = append(assertionNames, assertion.Name)
	}
	if !sameRuntimeStringSet(assertionNames, expectations.RequiredAssertions) {
		return errors.New("runtime probe assertion scope differs from trusted expectations")
	}
	if !sameRuntimeStringSet(obs.ObservedSurfaces, expectations.ExpectedSurfaces) {
		return errors.New("runtime probe surface scope differs from trusted expectations")
	}
	if len(obs.Collisions) != 0 {
		return errors.New("runtime probe reported an isolation collision")
	}
	if len(obs.Resources) != len(discovery.Resources) || len(obs.Resources) != len(expectations.RequiredResources) {
		return errors.New("runtime probe resource scope differs from discovery and trusted expectations")
	}
	discovered := make(map[string]struct{}, len(discovery.Resources))
	for _, resource := range discovery.Resources {
		discovered[resource.Kind+"\x00"+resource.Identifier] = struct{}{}
	}
	observedKinds := make([]string, 0, len(obs.Resources))
	expectedKinds := make([]string, 0, len(expectations.RequiredResources))
	for _, expected := range expectations.RequiredResources {
		expectedKinds = append(expectedKinds, expected.Kind)
	}
	for _, resource := range obs.Resources {
		if resource.Kind != "port" && resource.Kind != "path" {
			return fmt.Errorf("runtime probe resource kind %q is UNVERIFIABLE", resource.Kind)
		}
		if _, ok := discovered[resource.Kind+"\x00"+resource.Identifier]; !ok {
			return errors.New("runtime probe resource does not match fresh child discovery")
		}
		observedKinds = append(observedKinds, resource.Kind)
	}
	if !sameRuntimeStringSet(observedKinds, expectedKinds) {
		return errors.New("runtime probe resource kinds differ from trusted expectations")
	}
	return nil
}

func sameRuntimeStringSet(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	aa := sortedStrings(a)
	bb := sortedStrings(b)
	for idx := range aa {
		if aa[idx] != bb[idx] || strings.TrimSpace(aa[idx]) == "" || (idx > 0 && aa[idx] == aa[idx-1]) {
			return false
		}
	}
	return true
}

func digestForRuntimeEvidence(data []byte) string {
	return fmt.Sprintf("sha256:%x", sha256.Sum256(data))
}

func copyRuntimeStringMap(in map[string]string) map[string]string {
	out := make(map[string]string, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}

func decodeStrictJSON(data []byte, dst any) error {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	if err := dec.Decode(dst); err != nil {
		return err
	}
	if err := dec.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("multiple JSON values")
		}
		return err
	}
	return nil
}

func sortedStrings(values []string) []string {
	result := append([]string(nil), values...)
	sort.Strings(result)
	return result
}
