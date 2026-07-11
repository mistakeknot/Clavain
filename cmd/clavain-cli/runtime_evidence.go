package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
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

type runtimeEvidenceOps struct {
	labels           func(string) ([]string, error)
	state            func(string, string) (string, error)
	setState         func(string, string, string) error
	resolveRun       func(string) (string, error)
	loadRun          func(string) (Run, error)
	mergeRunMetadata func(string, string) error
	findScopeRuns    func(string) ([]Run, error)
	validateAdoption func(string, string) (json.RawMessage, error)
	createRun        func(runtimeAdoptCreate) (string, error)
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
		if _, err := runIC("lock", "acquire", "runtime-evidence-adopt", args[1], "--timeout=2s"); err != nil {
			return fmt.Errorf("runtime-evidence adopt: acquire serialization lock: %w", err)
		}
		defer func() {
			_, _ = runIC("lock", "release", "runtime-evidence-adopt", args[1])
		}()
		runID, err := adoptRuntimeEvidence(defaultRuntimeEvidenceOps(), args[1], projectRoot, provenancePath)
		if err != nil {
			return err
		}
		fmt.Println(runID)
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
		resolveRun: resolveRunIDQuiet,
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
	if err != nil || strings.TrimSpace(runID) == "" {
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

	if runID, resolveErr := ops.resolveRun(beadID); resolveErr == nil && strings.TrimSpace(runID) != "" {
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
		_, bound, metadataErr := runtimeEvidenceMetadataState(beadID, run.Metadata)
		if metadataErr != nil {
			return "", fmt.Errorf("runtime-evidence adopt: scope run %s: %w", run.ID, metadataErr)
		}
		if bound && run.Status != "cancelled" {
			recovered = append(recovered, run)
		}
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
	runID, err := ops.createRun(spec)
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
