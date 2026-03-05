package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/vmihailenco/msgpack/v5"
	"gopkg.in/yaml.v3"
)

// EvidenceManifest is the v1 manifest for an evidence pack.
type EvidenceManifest struct {
	SchemaVersion     int      `yaml:"schema_version" json:"schema_version"`
	SourcePlugin      string   `yaml:"source_plugin" json:"source_plugin"`
	EvidenceType      string   `yaml:"evidence_type" json:"evidence_type"`
	SessionID         string   `yaml:"session_id" json:"session_id"`
	Phase             string   `yaml:"phase" json:"phase"`
	Timestamp         uint64   `yaml:"timestamp" json:"timestamp"`
	BeadID            string   `yaml:"bead_id,omitempty" json:"bead_id,omitempty"`
	FindingID         string   `yaml:"finding_id,omitempty" json:"finding_id,omitempty"`
	Severity          string   `yaml:"severity,omitempty" json:"severity,omitempty"`
	ReplayInstructions string  `yaml:"replay_instructions,omitempty" json:"replay_instructions,omitempty"`
	Attachments       []string `yaml:"attachments,omitempty" json:"attachments,omitempty"`
	BlobHash          string   `yaml:"blob_hash,omitempty" json:"blob_hash,omitempty"`
}

// EvidenceRecord is the CXDB turn data for clavain.evidence.v1.
type EvidenceRecord struct {
	BeadID       string `msgpack:"1" json:"bead_id"`
	SourcePlugin string `msgpack:"2" json:"source_plugin"`
	EvidenceType string `msgpack:"3" json:"evidence_type"`
	FindingID    string `msgpack:"4" json:"finding_id,omitempty"`
	SessionID    string `msgpack:"5" json:"session_id,omitempty"`
	Severity     string `msgpack:"6" json:"severity,omitempty"`
	BlobHash     []byte `msgpack:"7" json:"blob_hash,omitempty"`
	Timestamp    uint64 `msgpack:"8" json:"timestamp"`
}

// evidenceDir returns the evidence base directory, creating it if needed.
func evidenceDir() string {
	base := os.Getenv("SPRINT_LIB_PROJECT_DIR")
	if base == "" {
		base = "."
	}
	dir := filepath.Join(base, ".clavain", "evidence")
	os.MkdirAll(dir, 0755)
	return dir
}

// cmdEvidenceToScenario converts a finding to a dev scenario.
// Usage: evidence-to-scenario <finding-id> [--bead=<id>]
func cmdEvidenceToScenario(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: evidence-to-scenario <finding-id> [--bead=<id>]")
	}
	findingID := args[0]
	beadID := ""
	for _, a := range args[1:] {
		if strings.HasPrefix(a, "--bead=") {
			beadID = strings.TrimPrefix(a, "--bead=")
		}
	}

	// Load evidence manifest for this finding
	caseDir := filepath.Join(evidenceDir(), findingID)
	manifestPath := filepath.Join(caseDir, "manifest.yml")
	manifest, err := loadEvidenceManifest(manifestPath)
	if err != nil {
		// No evidence pack — try to create minimal scenario from finding ID
		manifest = &EvidenceManifest{
			SchemaVersion: 1,
			SourcePlugin:  "unknown",
			EvidenceType:  "finding",
			FindingID:     findingID,
			Timestamp:     uint64(time.Now().Unix()),
		}
	}
	if beadID != "" {
		manifest.BeadID = beadID
	}

	// Generate dev scenario (NEVER holdout)
	hash := sha256.Sum256([]byte(findingID))
	scenarioID := "finding-" + hex.EncodeToString(hash[:8])

	scenario := Scenario{
		SchemaVersion: 1,
		ID:            scenarioID,
		Intent:        fmt.Sprintf("Regression check for finding %s (%s)", findingID, manifest.EvidenceType),
		Mode:          "behavioral",
		Setup:         []string{fmt.Sprintf("Evidence from %s: %s", manifest.SourcePlugin, manifest.EvidenceType)},
		Steps: []ScenarioStep{
			{
				Action: fmt.Sprintf("Reproduce condition from finding %s", findingID),
				Expect: "Issue is resolved or mitigated",
				Type:   "llm-judge",
			},
		},
		Rubric: []RubricItem{
			{Criterion: "Finding no longer reproduces", Weight: 0.7},
			{Criterion: "No regression introduced", Weight: 0.3},
		},
		RiskTags: []string{manifest.EvidenceType},
		Holdout:  false, // ALWAYS dev, never holdout
	}

	// Write to dev directory (hardcoded — never holdout)
	devDir := scenarioSubDir("dev")
	outPath := filepath.Join(devDir, scenarioID+".yaml")
	data, err := yaml.Marshal(scenario)
	if err != nil {
		return fmt.Errorf("evidence-to-scenario: marshal: %w", err)
	}
	if err := os.WriteFile(outPath, data, 0644); err != nil {
		return fmt.Errorf("evidence-to-scenario: write: %w", err)
	}

	fmt.Println(outPath)
	return nil
}

// cmdEvidencePack creates an evidence pack from sprint failure data.
// Usage: evidence-pack <bead-id> [--type=<type>]
func cmdEvidencePack(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: evidence-pack <bead-id> [--type=<type>]")
	}
	beadID := args[0]
	evidenceType := "sprint_failure"
	for _, a := range args[1:] {
		if strings.HasPrefix(a, "--type=") {
			evidenceType = strings.TrimPrefix(a, "--type=")
		}
	}

	// Create evidence directory
	caseDir := filepath.Join(evidenceDir(), beadID)
	os.MkdirAll(caseDir, 0755)

	sessionID := os.Getenv("CLAUDE_SESSION_ID")
	phase := ""
	if bdAvailable() {
		out, err := runBD("state", beadID, "phase")
		if err == nil {
			phase = strings.TrimSpace(string(out))
		}
	}

	manifest := EvidenceManifest{
		SchemaVersion:      1,
		SourcePlugin:       "clavain",
		EvidenceType:       evidenceType,
		SessionID:          sessionID,
		Phase:              phase,
		Timestamp:          uint64(time.Now().Unix()),
		BeadID:             beadID,
		ReplayInstructions: "Review bead state and CXDB trajectory for this sprint",
	}

	// Collect attachments
	var attachments []string

	// Bead state
	if bdAvailable() {
		out, _ := runBD("show", beadID)
		if len(out) > 0 {
			statePath := filepath.Join(caseDir, "bead-state.json")
			os.WriteFile(statePath, out, 0644)
			attachments = append(attachments, "bead-state.json")
		}
	}

	// Recent git log
	out, err := runGit("log", "--oneline", "-10")
	if err == nil {
		logPath := filepath.Join(caseDir, "git-log.txt")
		os.WriteFile(logPath, out, 0644)
		attachments = append(attachments, "git-log.txt")
	}

	manifest.Attachments = attachments

	// Write manifest
	manifestData, err := yaml.Marshal(manifest)
	if err != nil {
		return fmt.Errorf("evidence-pack: marshal manifest: %w", err)
	}
	manifestPath := filepath.Join(caseDir, "manifest.yml")
	if err := os.WriteFile(manifestPath, manifestData, 0644); err != nil {
		return fmt.Errorf("evidence-pack: write manifest: %w", err)
	}

	// Record in CXDB
	cxdbRecordEvidence(beadID, manifest)

	fmt.Println(caseDir)
	return nil
}

// cmdEvidenceList lists evidence packs.
// Usage: evidence-list [bead-id]
func cmdEvidenceList(args []string) error {
	base := evidenceDir()
	entries, err := os.ReadDir(base)
	if err != nil {
		fmt.Fprintln(os.Stderr, "No evidence packs found.")
		return nil
	}

	filterBead := ""
	if len(args) > 0 {
		filterBead = args[0]
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		manifestPath := filepath.Join(base, entry.Name(), "manifest.yml")
		m, err := loadEvidenceManifest(manifestPath)
		if err != nil {
			continue
		}
		if filterBead != "" && m.BeadID != filterBead {
			continue
		}
		fmt.Printf("%-20s %-15s %-15s %s\n",
			entry.Name(), m.EvidenceType, m.SourcePlugin, m.Phase)
	}
	return nil
}

func loadEvidenceManifest(path string) (*EvidenceManifest, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var m EvidenceManifest
	if err := yaml.Unmarshal(data, &m); err != nil {
		return nil, err
	}
	return &m, nil
}

// cxdbRecordEvidence records an evidence event as a CXDB turn.
func cxdbRecordEvidence(beadID string, m EvidenceManifest) {
	if !cxdbAvailable() {
		return
	}
	client, err := cxdbConnect()
	if err != nil {
		return
	}
	ctxID, err := cxdbSprintContext(client, beadID)
	if err != nil {
		return
	}
	rec := EvidenceRecord{
		BeadID:       beadID,
		SourcePlugin: m.SourcePlugin,
		EvidenceType: m.EvidenceType,
		FindingID:    m.FindingID,
		SessionID:    m.SessionID,
		Severity:     m.Severity,
		Timestamp:    m.Timestamp,
	}
	payload, err := msgpack.Marshal(rec)
	if err != nil {
		return
	}
	_ = cxdbAppendTyped(client, ctxID, "clavain.evidence.v1", payload)
}

// createFluxDriveDevScenario creates a dev scenario from a flux-drive regression finding.
func createFluxDriveDevScenario(findingHash, description, severity string) error {
	if severity != "error" && severity != "critical" {
		return nil // Only create scenarios for error+ severity
	}

	hashPrefix := findingHash
	if len(hashPrefix) > 16 {
		hashPrefix = hashPrefix[:16]
	}
	scenarioID := "fd-" + hashPrefix

	// Hardcoded dev path — NEVER holdout
	devDir := scenarioSubDir("dev")
	outPath := filepath.Join(devDir, scenarioID+".yaml")

	// Don't overwrite existing scenario
	if _, err := os.Stat(outPath); err == nil {
		return nil
	}

	scenario := Scenario{
		SchemaVersion: 1,
		ID:            scenarioID,
		Intent:        fmt.Sprintf("Regression check: %s", truncate(description, 100)),
		Mode:          "behavioral",
		Steps: []ScenarioStep{
			{
				Action: truncate(description, 200),
				Expect: "Issue is resolved",
				Type:   "llm-judge",
			},
		},
		Rubric: []RubricItem{
			{Criterion: "Regression fixed", Weight: 1.0},
		},
		RiskTags: []string{"regression"},
		Holdout:  false,
	}

	data, err := yaml.Marshal(scenario)
	if err != nil {
		return err
	}
	return os.WriteFile(outPath, data, 0644)
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}

// writeEvidenceJSON writes evidence data as JSON.
func writeEvidenceJSON(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0644)
}
