package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	pkgphase "github.com/mistakeknot/intercore/pkg/phase"
	"github.com/vmihailenco/msgpack/v5"
	"gopkg.in/yaml.v3"
)

// Policy represents the v1 agent capability policy.
type Policy struct {
	SchemaVersion int                    `yaml:"schema_version" json:"schema_version"`
	Phases        map[string]PhasePolicy `yaml:"phases" json:"phases"`
}

// PhasePolicy defines allow/deny rules for a phase.
type PhasePolicy struct {
	AllowPaths []string `yaml:"allow_paths,omitempty" json:"allow_paths,omitempty"`
	DenyPaths  []string `yaml:"deny_paths,omitempty" json:"deny_paths,omitempty"`
	AllowTools []string `yaml:"allow_tools,omitempty" json:"allow_tools,omitempty"`
	DenyTools  []string `yaml:"deny_tools,omitempty" json:"deny_tools,omitempty"`
}

// PolicyCheckResult is the output of a policy check.
type PolicyCheckResult struct {
	Allowed bool   `json:"allowed"`
	Reason  string `json:"reason"`
}

// PolicyViolationRecord is the CXDB turn data for clavain.policy_violation.v1.
type PolicyViolationRecord struct {
	BeadID     string `msgpack:"1" json:"bead_id"`
	AgentName  string `msgpack:"2" json:"agent_name"`
	Phase      string `msgpack:"3" json:"phase"`
	Action     string `msgpack:"4" json:"action"`
	TargetPath string `msgpack:"5" json:"target_path"`
	PolicyRule string `msgpack:"6" json:"policy_rule"`
	Timestamp  uint64 `msgpack:"7" json:"timestamp"`
}

// cmdPolicyCheck evaluates an action against the current phase policy.
// Usage: policy-check <agent> <action> [--path=<path>] [--bead=<id>]
func cmdPolicyCheck(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: policy-check <agent> <action> [--path=<path>] [--bead=<id>]")
	}
	agentName := args[0]
	action := args[1]
	targetPath := ""
	beadID := ""

	for _, a := range args[2:] {
		if strings.HasPrefix(a, "--path=") {
			targetPath = strings.TrimPrefix(a, "--path=")
		}
		if strings.HasPrefix(a, "--bead=") {
			beadID = strings.TrimPrefix(a, "--bead=")
		}
	}

	// Determine current phase
	phase := getCurrentPhase(beadID)

	// Load policy
	policy, err := loadPolicy()
	if err != nil {
		// No policy file — default allow
		result := PolicyCheckResult{Allowed: true, Reason: "no policy configured"}
		return outputJSON(result)
	}

	// Evaluate
	result := evaluatePolicy(policy, phase, action, targetPath)

	// Record violation if denied and involves holdout
	if !result.Allowed && isHoldoutPath(targetPath) && beadID != "" {
		recordPolicyViolation(beadID, agentName, phase, action, targetPath, result.Reason)
	}

	return outputJSON(result)
}

// cmdPolicyShow displays the current policy in human-readable format.
// Usage: policy-show
func cmdPolicyShow(args []string) error {
	policy, err := loadPolicy()
	if err != nil {
		fmt.Fprintln(os.Stderr, "No policy file found. Using defaults.")
		policy = defaultPolicy()
	}

	fmt.Printf("Policy Schema Version: %d\n\n", policy.SchemaVersion)
	fmt.Printf("%-15s %-30s %-30s\n", "Phase", "Deny Paths", "Deny Tools")
	fmt.Printf("%-15s %-30s %-30s\n", "-----", "----------", "----------")

	for _, phase := range []string{pkgphase.Brainstorm, pkgphase.Strategized, pkgphase.Planned, pkgphase.Executing, pkgphase.LegacyShipping, pkgphase.Reflect} {
		pp, ok := policy.Phases[phase]
		if !ok {
			fmt.Printf("%-15s %-30s %-30s\n", phase, "(none)", "(none)")
			continue
		}
		denyPaths := "(none)"
		if len(pp.DenyPaths) > 0 {
			denyPaths = strings.Join(pp.DenyPaths, ", ")
		}
		denyTools := "(none)"
		if len(pp.DenyTools) > 0 {
			denyTools = strings.Join(pp.DenyTools, ", ")
		}
		fmt.Printf("%-15s %-30s %-30s\n", phase, denyPaths, denyTools)
	}
	return nil
}

// loadPolicy loads the project policy or falls back to default.
func loadPolicy() (*Policy, error) {
	base := os.Getenv("SPRINT_LIB_PROJECT_DIR")
	if base == "" {
		base = "."
	}

	// Try project policy first
	projectPath := filepath.Join(base, ".clavain", "policy.yml")
	if data, err := os.ReadFile(projectPath); err == nil {
		var p Policy
		if yaml.Unmarshal(data, &p) == nil {
			return &p, nil
		}
	}

	// Fall back to default policy
	return defaultPolicy(), nil
}

// defaultPolicy returns the built-in default policy.
func defaultPolicy() *Policy {
	return &Policy{
		SchemaVersion: 1,
		Phases: map[string]PhasePolicy{
			pkgphase.Brainstorm:     {DenyPaths: []string{".clavain/scenarios/holdout/**"}},
			pkgphase.Strategized:    {DenyPaths: []string{".clavain/scenarios/holdout/**"}},
			pkgphase.Planned:        {DenyPaths: []string{".clavain/scenarios/holdout/**"}},
			pkgphase.Executing:      {DenyPaths: []string{".clavain/scenarios/holdout/**"}},
			pkgphase.LegacyShipping: {AllowPaths: []string{"**"}, AllowTools: []string{"**"}},
			pkgphase.Reflect:        {DenyPaths: []string{".clavain/scenarios/holdout/**"}},
		},
	}
}

// evaluatePolicy checks whether an action on a path is allowed in the given phase.
func evaluatePolicy(policy *Policy, phase, action, targetPath string) PolicyCheckResult {
	pp, ok := policy.Phases[phase]
	if !ok {
		return PolicyCheckResult{Allowed: true, Reason: fmt.Sprintf("no policy for phase %q", phase)}
	}

	// Check deny paths (deny takes precedence)
	for _, pattern := range pp.DenyPaths {
		if matchGlob(pattern, targetPath) {
			return PolicyCheckResult{
				Allowed: false,
				Reason:  fmt.Sprintf("path %q denied by pattern %q in phase %q", targetPath, pattern, phase),
			}
		}
	}

	// Check deny tools
	for _, pattern := range pp.DenyTools {
		if matchGlob(pattern, action) {
			return PolicyCheckResult{
				Allowed: false,
				Reason:  fmt.Sprintf("action %q denied by pattern %q in phase %q", action, pattern, phase),
			}
		}
	}

	return PolicyCheckResult{Allowed: true, Reason: "allowed by policy"}
}

// matchGlob matches a path against a glob pattern.
// Supports ** for recursive matching and * for single-level.
func matchGlob(pattern, path string) bool {
	if pattern == "**" {
		return true
	}

	// Convert glob pattern to filepath.Match format
	// ** matches any path segment
	if strings.Contains(pattern, "**") {
		prefix := strings.TrimSuffix(pattern, "/**")
		prefix = strings.TrimSuffix(prefix, "**")
		return strings.HasPrefix(path, prefix)
	}

	matched, _ := filepath.Match(pattern, path)
	return matched
}

// isHoldoutPath checks if a path is in the holdout directory.
func isHoldoutPath(path string) bool {
	return strings.Contains(path, "/holdout/") || strings.Contains(path, "holdout/")
}

// getCurrentPhase determines the current sprint phase.
func getCurrentPhase(beadID string) string {
	if beadID != "" && bdAvailable() {
		out, err := runBD("state", beadID, "phase")
		if err == nil {
			phase := strings.TrimSpace(string(out))
			if phase != "" {
				return phase
			}
		}
	}

	// Try environment variable
	if phase := os.Getenv("CLAVAIN_PHASE"); phase != "" {
		return phase
	}

	return pkgphase.Executing // Default to most restrictive build phase
}

// recordPolicyViolation records a policy violation in CXDB.
func recordPolicyViolation(beadID, agentName, phase, action, targetPath, rule string) {
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
	rec := PolicyViolationRecord{
		BeadID:     beadID,
		AgentName:  agentName,
		Phase:      phase,
		Action:     action,
		TargetPath: targetPath,
		PolicyRule: rule,
		Timestamp:  uint64(time.Now().Unix()),
	}
	payload, err := msgpack.Marshal(rec)
	if err != nil {
		return
	}
	_ = cxdbAppendTyped(client, ctxID, "clavain.policy_violation.v1", payload)
}

func outputJSON(v any) error {
	data, err := json.Marshal(v)
	if err != nil {
		return err
	}
	fmt.Println(string(data))
	return nil
}
