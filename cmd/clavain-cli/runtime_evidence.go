package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
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

func runtimeEvidenceRequiredState(beadID string, labelled, marker bool, metadata string) (bool, error) {
	bound := false
	if strings.TrimSpace(metadata) != "" {
		var decoded runtimeRunMetadata
		if err := decodeStrictJSON([]byte(metadata), &decoded); err != nil {
			return false, fmt.Errorf("runtime evidence run metadata: %w", err)
		}
		if decoded.CloseGate != nil {
			seen := make(map[string]struct{}, len(decoded.CloseGate.Requirements))
			for _, requirement := range decoded.CloseGate.Requirements {
				if strings.TrimSpace(requirement) == "" {
					return false, errors.New("runtime evidence requirements contain a blank value")
				}
				if _, exists := seen[requirement]; exists {
					return false, fmt.Errorf("runtime evidence requirements contain duplicate %q", requirement)
				}
				seen[requirement] = struct{}{}
				if requirement == runtimeEvidenceArtifactType {
					bound = true
				}
			}
			if bound && decoded.CloseGate.BeadID != beadID {
				return false, fmt.Errorf("runtime evidence bead mismatch: run metadata names %q, expected %q", decoded.CloseGate.BeadID, beadID)
			}
		}
	}
	return labelled || marker || bound, nil
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
		Timeout:      time.Duration(cfg.TimeoutSeconds) * time.Second,
		Expectations: expectations,
	}, nil
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
