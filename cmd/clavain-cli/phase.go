package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	pkgphase "github.com/mistakeknot/intercore/pkg/phase"
)

var phaseAttributionSessionFile = "/tmp/interstat-session-id"

// nextStep returns the static fallback next step for a given phase.
// This matches the Bash sprint_next_step() fallback case statement.
func nextStep(phase string) string {
	switch phase {
	case pkgphase.Brainstorm:
		return "strategy"
	case pkgphase.BrainstormReviewed:
		return "strategy"
	case pkgphase.Strategized:
		return "write-plan"
	case pkgphase.Planned:
		return "flux-drive"
	case pkgphase.LegacyPlanReviewed:
		return "work"
	case pkgphase.Executing:
		return "quality-gates"
	case pkgphase.LegacyShipping:
		return "reflect"
	case pkgphase.Reflect:
		return "ship"
	case pkgphase.Done:
		return "done"
	default:
		fmt.Fprintf(os.Stderr, "WARNING: unknown phase %q — defaulting to brainstorm\n", phase)
		return "brainstorm"
	}
}

// commandToStep maps a kernel action command name to a sprint step name.
func commandToStep(cmd string) string {
	switch cmd {
	case "/clavain:brainstorm":
		return "brainstorm"
	case "/clavain:strategy":
		return "strategy"
	case "/clavain:write-plan":
		return "write-plan"
	case "/interflux:flux-drive":
		return "flux-drive"
	case "/clavain:work":
		return "work"
	case "/clavain:quality-gates":
		return "quality-gates"
	case "/clavain:resolve":
		return "resolve"
	case "/reflect", "/clavain:reflect":
		return "reflect"
	default:
		return cmd
	}
}

// resolveRunID is defined in sprint.go (with caching).

// cmdSprintNextStep determines the next sprint step for a given phase.
// First tries kernel action list via ic, then falls back to static mapping.
// Usage: sprint-next-step <phase>
func cmdSprintNextStep(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: sprint-next-step <phase>")
	}
	phase := args[0]

	// Try kernel action list if bead ID is available
	beadID := os.Getenv("CLAVAIN_BEAD_ID")
	if phase == pkgphase.Reflect && beadID != "" {
		fmt.Println(reflectionResumeStep(beadID, artifactPathForBead))
		return nil
	}
	if beadID != "" {
		runID, err := resolveRunID(beadID)
		if err == nil && runID != "" {
			var actions []RunAction
			err := runICJSON(&actions, "run", "action", "list", runID, "--phase="+phase)
			if err == nil && len(actions) > 0 {
				cmd := actions[0].Command
				if cmd != "" {
					step := commandToStep(cmd)
					fmt.Println(step)
					return nil
				}
			}
		}
	}

	// Fallback: static phase->step mapping
	fmt.Println(nextStep(phase))
	return nil
}

func reflectionResumeStep(beadID string, lookup func(string, string) (string, error)) string {
	path, err := lookup(beadID, "reflection")
	if err != nil || path == "" {
		return "reflect"
	}
	info, err := os.Stat(path)
	if err != nil || !info.Mode().IsRegular() {
		return "reflect"
	}
	return "ship"
}

// cmdSprintAdvance advances a sprint to the next phase.
// Budget check (unless CLAVAIN_SKIP_BUDGET set) -> ic run advance -> handle result.
// On success: invalidate caches, record phase tokens, print transition to stderr.
// On failure: structured pause reason on stdout.
// Usage: sprint-advance <bead_id> <current_phase> [artifact_path]
func cmdSprintAdvance(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: sprint-advance <bead_id> <current_phase> [artifact_path]")
	}
	beadID := args[0]
	currentPhase := args[1]
	if err := validateRuntimeEvidenceBinding(defaultRuntimeEvidenceOps(), beadID); err != nil {
		return fmt.Errorf("sprint-advance: %w", err)
	}

	runID, err := resolveRunID(beadID)
	if err != nil {
		return err
	}

	// Budget check (skip with CLAVAIN_SKIP_BUDGET)
	if os.Getenv("CLAVAIN_SKIP_BUDGET") == "" {
		// Run budget check via ic
		budgetOut, budgetErr := runIC("run", "budget", runID)
		if budgetErr != nil {
			// Exit code 1 from ic run budget means budget exceeded
			if strings.Contains(budgetErr.Error(), "exit status 1") || strings.Contains(budgetErr.Error(), "exit status") {
				// Get token details for the pause reason
				spent := "?"
				budgetVal := "?"
				var tokenAgg TokenAgg
				if err := runICJSON(&tokenAgg, "run", "tokens", runID); err == nil {
					spent = fmt.Sprintf("%d", tokenAgg.InputTokens+tokenAgg.OutputTokens)
				}
				var runStatus Run
				if err := runICJSON(&runStatus, "run", "status", runID); err == nil && runStatus.TokenBudget > 0 {
					budgetVal = fmt.Sprintf("%d", runStatus.TokenBudget)
				}
				fmt.Printf("budget_exceeded|%s|%s/%s billing tokens\n", currentPhase, spent, budgetVal)
				return fmt.Errorf("budget exceeded")
			}
			// Other budget errors are non-fatal, continue
			_ = budgetOut
		}
	}

	// Advance via ic — pass calibration file if available
	advanceArgs := []string{"run", "advance", runID, "--priority=0"}
	calPath := gateCalibrationFilePath()
	if _, statErr := os.Stat(calPath); statErr == nil {
		advanceArgs = append(advanceArgs, "--calibration-file="+calPath)
	}

	var result AdvanceResult
	err = runICJSON(&result, advanceArgs...)
	if err != nil {
		// ic returned error — check if phase already advanced
		actualPhaseOut, phaseErr := runIC("run", "phase", runID)
		if phaseErr == nil {
			actualPhase := string(actualPhaseOut)
			if actualPhase != "" && actualPhase != currentPhase {
				fmt.Printf("stale_phase|%s|Phase already advanced to %s\n", currentPhase, actualPhase)
			}
		}
		return fmt.Errorf("sprint-advance: ic run advance failed: %w", err)
	}

	if !result.Advanced {
		switch result.EventType {
		case "block":
			fmt.Printf("gate_blocked|%s|Gate prerequisites not met\n", result.ToPhase)
		case "pause":
			fmt.Printf("manual_pause|%s|auto_advance=false\n", result.ToPhase)
		default:
			if result.EventType == "" {
				fmt.Fprintf(os.Stderr, "sprint_advance: ic run advance returned unexpected result\n")
			}
			// Check if phase was already advanced
			actualPhaseOut, phaseErr := runIC("run", "phase", runID)
			if phaseErr == nil {
				actualPhase := string(actualPhaseOut)
				if actualPhase != "" && actualPhase != currentPhase {
					fmt.Printf("stale_phase|%s|Phase already advanced to %s\n", currentPhase, actualPhase)
				}
			}
		}
		return fmt.Errorf("sprint-advance: not advanced")
	}

	// Success path
	fromPhase := result.FromPhase
	if fromPhase == "" {
		fromPhase = currentPhase
	}
	toPhase := result.ToPhase
	refreshPhaseAdvanceAttribution(beadID, runID, toPhase)

	// Invalidate caches
	invalidateCaches()

	// Record phase tokens (best-effort)
	recordPhaseTokens(beadID, currentPhase)

	fmt.Fprintf(os.Stderr, "Phase: %s \u2192 %s (auto-advancing)\n", fromPhase, toPhase)

	// Sideband parity (KD 11): keep the statusline current without interphase.
	if sid := os.Getenv("CLAUDE_SESSION_ID"); sid != "" {
		_ = writeBeadSideband(sid, beadID, toPhase, "sprint-advance")
	}
	return nil
}

// refreshPhaseAdvanceAttribution updates both durable Intercore attribution and
// Interstat's compatibility context after Intercore has committed an advance.
// Failures are warnings: returning an error here would falsely report the
// already-committed phase transition as failed.
func refreshPhaseAdvanceAttribution(beadID, runID, phase string) {
	sessionID := phaseAttributionSessionID()
	if sessionID == "" {
		fmt.Fprintln(os.Stderr, "sprint_advance: WARNING: phase attribution skipped: no session ID")
		return
	}
	if phase == "" {
		fmt.Fprintln(os.Stderr, "sprint_advance: WARNING: phase attribution skipped: advance returned no target phase")
		return
	}

	if _, err := runIC(
		"session", "attribute",
		"--session="+sessionID,
		"--bead="+beadID,
		"--run="+runID,
		"--phase="+phase,
	); err != nil {
		fmt.Fprintf(os.Stderr, "sprint_advance: WARNING: Intercore attribution failed: %v\n", err)
	}

	script := findPhaseInterstatContextScript()
	if script == "" {
		fmt.Fprintln(os.Stderr, "sprint_advance: WARNING: Interstat attribution failed: set-bead-context.sh not found")
		return
	}
	if _, err := runCommandExec("bash", script, sessionID, beadID, phase); err != nil {
		fmt.Fprintf(os.Stderr, "sprint_advance: WARNING: Interstat attribution failed: %v\n", err)
	}
}

func phaseAttributionSessionID() string {
	if sessionID := strings.TrimSpace(os.Getenv("CLAUDE_SESSION_ID")); sessionID != "" {
		return sessionID
	}
	data, err := os.ReadFile(phaseAttributionSessionFile)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

// findPhaseInterstatContextScript is intentionally local to phase handling;
// budget.go has a separate cost-query discovery contract.
func findPhaseInterstatContextScript() string {
	var candidates []string
	if root := strings.TrimSpace(os.Getenv("INTERSTAT_ROOT")); root != "" {
		candidates = append(candidates, filepath.Join(root, "scripts", "set-bead-context.sh"))
	}
	if pluginRoot := strings.TrimSpace(os.Getenv("CLAUDE_PLUGIN_ROOT")); pluginRoot != "" {
		candidates = append(candidates, filepath.Join(filepath.Dir(pluginRoot), "interstat", "scripts", "set-bead-context.sh"))
	}
	if sourceDir := strings.TrimSpace(os.Getenv("CLAVAIN_SOURCE_DIR")); sourceDir != "" {
		candidates = append(candidates, filepath.Join(sourceDir, "..", "..", "interverse", "interstat", "scripts", "set-bead-context.sh"))
	}
	if home, err := os.UserHomeDir(); err == nil && home != "" {
		candidates = append(candidates, filepath.Join(home, "projects", "Sylveste", "interverse", "interstat", "scripts", "set-bead-context.sh"))
	}

	for _, candidate := range candidates {
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return filepath.Clean(candidate)
		}
	}
	return ""
}

// cmdSprintShouldPause checks if a sprint should pause before advancing.
// Returns exit 0 with structured trigger on stdout if pause, exit 1 if continue.
// Usage: sprint-should-pause <bead_id> <target_phase>
func cmdSprintShouldPause(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: sprint-should-pause <bead_id> <target_phase>")
	}
	beadID := args[0]
	targetPhase := args[1]

	runID, err := resolveRunID(beadID)
	if err != nil {
		// No run ID = no pause check possible, continue
		return fmt.Errorf("continue")
	}

	// Check gate via ic
	_, gateErr := runIC("gate", "check", runID)
	if gateErr != nil {
		// Gate blocked — output structured trigger and return success (exit 0)
		fmt.Printf("gate_blocked|%s|Gate prerequisites not met\n", targetPhase)
		return nil
	}

	// No pause trigger — return error (exit 1) to signal "continue"
	return fmt.Errorf("continue")
}

// cmdEnforceGate enforces gate prerequisites for a phase transition.
// Respects CLAVAIN_SKIP_GATE env var. Fail-open: if ic unavailable, gates pass.
// Usage: enforce-gate <bead_id> <target_phase> [artifact_path]
func cmdEnforceGate(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: enforce-gate <bead_id> <target_phase> [artifact_path]")
	}
	beadID := args[0]
	targetPhase := args[1]

	// Check CLAVAIN_SKIP_GATE env var
	if os.Getenv("CLAVAIN_SKIP_GATE") != "" {
		fmt.Fprintf(os.Stderr, "enforce-gate: skipping gate for %s (CLAVAIN_SKIP_GATE set)\n", targetPhase)
		// Audit event: gate was skipped — important for calibration signal quality
		runID, resolveErr := resolveRunID(beadID)
		if resolveErr == nil && runID != "" {
			emitInterspectEvent("calibration_skip_gate",
				fmt.Sprintf("run=%s phase=%s reason=CLAVAIN_SKIP_GATE", runID, targetPhase))
		}
		return nil
	}

	// Handoff contract pre-check (before ic gate check)
	if os.Getenv("CLAVAIN_SKIP_HANDOFF") == "" {
		// Load spec once for gate mode checks (hoisted outside loop)
		spec, specErr := loadAgencySpec()
		var gateMode string
		if specErr == nil {
			gateMode = getGateModeForPhase(spec, targetPhase)
		} else {
			gateMode = "shadow"
		}

		handoffResults := checkHandoffContracts(beadID, targetPhase)
		for _, r := range handoffResults {
			if r.Result == "fail" {
				if gateMode == "enforce" {
					return fmt.Errorf("handoff contract failed for %s: %s", r.ArtifactType, summarizeFailures(r))
				}
				// Shadow mode: warn on stderr, continue
				fmt.Fprintf(os.Stderr, "enforce-gate: handoff WARN: %s validation failed (%s) [shadow mode]\n",
					r.ArtifactType, summarizeFailures(r))
			}
		}
	}

	// Satisfaction gate check for shipping phase
	if targetPhase == pkgphase.LegacyShipping {
		spec, specErr := loadAgencySpec()
		var gateMode string
		if specErr == nil {
			gateMode = getGateModeForPhase(spec, targetPhase)
		} else {
			gateMode = "shadow"
		}

		if err := satisfactionGateCheck(beadID); err != nil {
			if gateMode == "enforce" {
				return fmt.Errorf("enforce-gate: %w", err)
			}
			fmt.Fprintf(os.Stderr, "enforce-gate: satisfaction WARN: %v [shadow mode]\n", err)
		}
	}

	// Resolve run ID — fail-open if no run
	runID, err := resolveRunID(beadID)
	if err != nil {
		fmt.Fprintf(os.Stderr, "enforce-gate: skipped — no ic run for bead %q\n", beadID)
		return nil
	}

	// Run ic gate check — fail-open if ic unavailable
	if !icAvailable() {
		return nil
	}

	// Pass calibration file if available
	gateArgs := []string{"gate", "check", runID}
	calPathGate := gateCalibrationFilePath()
	if _, statErr := os.Stat(calPathGate); statErr == nil {
		gateArgs = append(gateArgs, "--calibration-file="+calPathGate)
	}

	_, gateErr := runIC(gateArgs...)
	if gateErr != nil {
		return fmt.Errorf("gate blocked for %s", targetPhase)
	}

	return nil
}

// knownArtifactTypes is the canonical set of artifact types for the sprint lifecycle.
var knownArtifactTypes = map[string]bool{
	"brainstorm":                true,
	"prd":                       true,
	"plan":                      true,
	"plan-review":               true,
	"implementation":            true,
	"quality-verdict":           true,
	"resolution":                true,
	"reflection":                true,
	"landed":                    true,
	"closed":                    true,
	"degradation":               true,
	"test-pass-sha":             true,
	"prior-art":                 true,
	"acceptance-criteria":       true,
	"criteria-results":          true,
	runtimeEvidenceArtifactType: true,
}

// cmdSetArtifact records an artifact for the current phase.
// Usage: set-artifact <bead_id> <type> <path>
func cmdSetArtifact(args []string) error {
	if len(args) < 3 {
		return fmt.Errorf("usage: set-artifact <bead_id> <type> <path>")
	}
	beadID := args[0]
	artifactType := args[1]
	artifactPath := args[2]

	if !knownArtifactTypes[artifactType] {
		fmt.Fprintf(os.Stderr, "set-artifact: warning: unknown type %q\n", artifactType)
	}

	// Write-once seal for acceptance criteria (fc5.3, f-034): the standard a
	// validator judges against must not be rewritable after execution starts —
	// especially by an escalation-triggered re-plan that has seen why the
	// first attempt failed. Seal = content-hash sidecar; independent of bd/ic.
	if artifactType == "acceptance-criteria" {
		if err := sealArtifact(artifactPath); err != nil {
			return err
		}
	}

	// Always store in bd state as fallback (works without ic run)
	if bdAvailable() {
		_, stateErr := runBD("set-state", beadID, "artifact_"+artifactType+"="+artifactPath)
		if stateErr != nil && artifactType == runtimeEvidenceArtifactType {
			return fmt.Errorf("set-artifact: register runtime evidence in Beads: %w", stateErr)
		}
	}

	runID, err := resolveRunID(beadID)
	if err != nil {
		if artifactType == runtimeEvidenceArtifactType {
			return fmt.Errorf("set-artifact: runtime evidence requires a bound Intercore run: %w", err)
		}
		return nil // no ic run — bd fallback already written
	}

	// Get current phase
	phaseOut, err := runIC("run", "phase", runID)
	if err != nil {
		if artifactType == runtimeEvidenceArtifactType {
			return fmt.Errorf("set-artifact: resolve runtime evidence phase: %w", err)
		}
		phaseOut = []byte("unknown")
	}
	phase := string(phaseOut)

	// Add artifact via ic
	_, err = runIC("run", "artifact", "add", runID,
		"--phase="+phase,
		"--path="+artifactPath,
		"--type="+artifactType)
	if err != nil {
		if artifactType == runtimeEvidenceArtifactType {
			return fmt.Errorf("set-artifact: register runtime evidence in Intercore: %w", err)
		}
		// Fail-safe: log but don't fail
		fmt.Fprintf(os.Stderr, "set-artifact: warning: %v\n", err)
	}

	// Best-effort: record artifact with content hash in CXDB
	cxdbRecordArtifact(beadID, artifactType, artifactPath)

	return nil
}

// cmdGetArtifact retrieves an artifact path by type.
// Tries ic run artifacts first, falls back to bd state.
// Usage: get-artifact <bead_id> <type>
func cmdGetArtifact(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: get-artifact <bead_id> <type>")
	}
	beadID := args[0]
	artifactType := args[1]
	path, err := artifactPathForBead(beadID, artifactType)
	if err != nil {
		return err
	}
	fmt.Println(path)
	return nil
}

func artifactPathForBead(beadID, artifactType string) (string, error) {
	// Try ic first (if run exists)
	runID, err := resolveRunID(beadID)
	if err == nil {
		var artifacts []Artifact
		err = runICJSON(&artifacts, "run", "artifact", "list", runID)
		if err == nil {
			for idx := len(artifacts) - 1; idx >= 0; idx-- {
				a := artifacts[idx]
				if a.Type == artifactType {
					if a.Status != "" && a.Status != "active" {
						continue
					}
					return a.Path, nil
				}
			}
		}
	}

	// Fallback: read from bd state
	if bdAvailable() {
		out, err := runBD("state", beadID, "artifact_"+artifactType)
		if err == nil {
			path := strings.TrimSpace(string(out))
			if path != "" && !strings.HasPrefix(path, "(no") {
				return path, nil
			}
		}
	}

	return "", fmt.Errorf("no artifact of type %q found for %s", artifactType, beadID)
}

// cmdRecordPhase records phase completion — just invalidates caches.
// With ic, events are auto-recorded by the kernel.
// Usage: record-phase <bead_id> <phase>
func cmdRecordPhase(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: record-phase <bead_id> <phase>")
	}
	// Sprint phase completion just invalidates discovery caches
	invalidateCaches()
	return nil
}

// cmdAdvancePhase is the legacy gate/phase command that delegates to
// enforce_gate + record_phase logic.
// Usage: advance-phase <bead_id> <phase> <reason> <artifact_path>
func cmdAdvancePhase(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: advance-phase <bead_id> <phase> [reason] [artifact_path]")
	}
	beadID := args[0]
	targetPhase := args[1]
	artifactPath := ""
	if len(args) >= 4 {
		artifactPath = args[3]
	}

	// Enforce gate first
	gateArgs := []string{beadID, targetPhase}
	if artifactPath != "" {
		gateArgs = append(gateArgs, artifactPath)
	}
	if err := cmdEnforceGate(gateArgs); err != nil {
		return err
	}

	// Record phase completion
	if err := cmdRecordPhase(args[:2]); err != nil {
		return err
	}

	// Best-effort: record phase transition in CXDB turn DAG
	cxdbRecordPhaseTransition(beadID, targetPhase, artifactPath)

	return nil
}

// cmdInferAction determines the next action from sprint state.
// Mirrors the interphase infer_bead_action function.
// Outputs: "<action>|<artifact_path>"
// Usage: infer-action <bead_id> [status]
func cmdInferAction(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: infer-action <bead_id> [status]")
	}
	beadID := args[0]
	status := ""
	if len(args) >= 2 {
		status = args[1]
	}

	// Try phase-aware inference first
	runID, err := resolveRunID(beadID)
	if err == nil && runID != "" {
		phaseOut, phaseErr := runIC("run", "phase", runID)
		if phaseErr == nil {
			phase := string(phaseOut)
			if phase != "" {
				action := phaseToAction(phase)
				if action != "" {
					// Try to find associated artifact
					artifactPath := findArtifactForPhase(beadID, phase)
					fmt.Printf("%s|%s\n", action, artifactPath)
					return nil
				}
			}
		}
	}

	// Fallback: filesystem-based inference
	projectDir := "."
	planPath := findBeadArtifact(beadID, filepath.Join(projectDir, "docs/plans"))
	prdPath := findBeadArtifact(beadID, filepath.Join(projectDir, "docs/prds"))
	brainstormPath := findBeadArtifact(beadID, filepath.Join(projectDir, "docs/brainstorms"))

	if status == "in_progress" {
		fmt.Printf("continue|%s\n", planPath)
	} else if planPath != "" {
		fmt.Printf("execute|%s\n", planPath)
	} else if prdPath != "" {
		fmt.Printf("plan|%s\n", prdPath)
	} else if brainstormPath != "" {
		fmt.Printf("strategize|%s\n", brainstormPath)
	} else {
		fmt.Println("brainstorm|")
	}
	return nil
}

// phaseToAction maps a phase name to an action name for infer-action.
func phaseToAction(phase string) string {
	switch phase {
	case pkgphase.Brainstorm:
		return "strategize"
	case pkgphase.BrainstormReviewed:
		return "strategize"
	case pkgphase.Strategized:
		return "plan"
	case pkgphase.Planned:
		return "execute"
	case pkgphase.LegacyPlanReviewed:
		return "execute"
	case pkgphase.Executing:
		return "continue"
	case pkgphase.LegacyShipping:
		return "ship"
	case pkgphase.Reflect:
		return "reflect" // identity mapping: reflect is both phase and action (unlike ship/closed)
	case pkgphase.Done:
		return "closed"
	default:
		return ""
	}
}

// findArtifactForPhase tries to find an artifact path from ic for the given phase.
func findArtifactForPhase(beadID, phase string) string {
	runID, err := resolveRunID(beadID)
	if err != nil {
		return ""
	}
	var artifacts []Artifact
	if err := runICJSON(&artifacts, "run", "artifact", "list", runID); err != nil {
		return ""
	}
	for _, a := range artifacts {
		if a.Phase == phase {
			return a.Path
		}
	}
	return ""
}

// findBeadArtifact searches a directory for files referencing the given bead ID.
// Returns the first matching file path, or empty string.
func findBeadArtifact(beadID, dir string) string {
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		return ""
	}

	// Walk directory looking for files that reference this bead
	pattern := regexp.MustCompile(`(?i)Bead.*` + regexp.QuoteMeta(beadID) + `\b`)

	var result string
	filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || result != "" {
			return nil
		}
		// Only check markdown files
		if !strings.HasSuffix(path, ".md") {
			return nil
		}
		f, err := os.Open(path)
		if err != nil {
			return nil
		}
		defer f.Close()

		scanner := bufio.NewScanner(f)
		for scanner.Scan() {
			if pattern.MatchString(scanner.Text()) {
				result = path
				return filepath.SkipAll
			}
		}
		return nil
	})
	return result
}

// beadPattern matches bead references in artifact files.
// Handles: **Bead:** iv-xxx, Bead: iv-xxx, **Bead**: iv-xxx
var beadPattern = regexp.MustCompile(`\*{0,2}Bead\*{0,2}:\*{0,2}\s*([A-Za-z]+-[A-Za-z0-9]+)`)

// cmdInferBead extracts a bead ID from an artifact file's frontmatter.
// Strategy 1: CLAVAIN_BEAD_ID env var (authoritative)
// Strategy 2: grep target file for **Bead:** pattern
// Strategy 3: empty string (no bead tracking)
// Usage: infer-bead <artifact_path>
func cmdInferBead(args []string) error {
	// Strategy 1: explicit env var
	beadID := os.Getenv("CLAVAIN_BEAD_ID")
	if beadID != "" {
		fmt.Println(beadID)
		return nil
	}

	// Strategy 2: grep target file
	if len(args) >= 1 && args[0] != "" {
		targetFile := args[0]
		f, err := os.Open(targetFile)
		if err == nil {
			defer f.Close()

			var matches []string
			scanner := bufio.NewScanner(f)
			for scanner.Scan() {
				line := scanner.Text()
				m := beadPattern.FindStringSubmatch(line)
				if m != nil {
					matches = append(matches, m[1])
				}
			}

			if len(matches) > 0 {
				if len(matches) > 1 {
					fmt.Fprintf(os.Stderr, "WARNING: multiple bead IDs in %s — using first (%s). Set CLAVAIN_BEAD_ID for explicit control.\n",
						targetFile, matches[0])
				}
				fmt.Println(matches[0])
				return nil
			}
		}
	}

	// Strategy 3: no bead found
	fmt.Println("")
	return nil
}

// invalidateCaches clears discovery caches by calling ic state delete.
// Mirrors sprint_invalidate_caches() from lib-sprint.sh.
func invalidateCaches() {
	if !icAvailable() {
		return
	}
	// List all scopes for discovery_brief key and delete them
	out, err := runIC("state", "list", "discovery_brief")
	if err != nil {
		return
	}
	scopes := strings.TrimSpace(string(out))
	if scopes == "" {
		return
	}
	for _, scope := range strings.Split(scopes, "\n") {
		scope = strings.TrimSpace(scope)
		if scope == "" {
			continue
		}
		runIC("state", "delete", "discovery_brief", scope)
	}
}

// recordPhaseTokens records token usage for a completed phase to ic state.
// Best-effort: errors are silently ignored.
func recordPhaseTokens(beadID, phase string) {
	if beadID == "" || phase == "" {
		return
	}
	// Delegate to the sprint-record-phase-tokens command
	cmdRecordPhaseTokens([]string{beadID, phase})
}

// phaseToStage is defined in budget.go.

// sealArtifact enforces write-once semantics via a content-hash sidecar.
// First call writes <path>.seal; later calls verify the hash and refuse a
// changed file unless CLAVAIN_RESEAL=1.
func sealArtifact(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("seal: cannot read %s: %w", path, err)
	}
	sum := sha256.Sum256(data)
	hexSum := hex.EncodeToString(sum[:])
	sealPath := path + ".seal"

	existing, rerr := os.ReadFile(sealPath)
	if rerr == nil {
		if strings.TrimSpace(string(existing)) == hexSum {
			return nil // unchanged content — idempotent re-register is fine
		}
		if os.Getenv("CLAVAIN_RESEAL") != "1" {
			return fmt.Errorf("acceptance-criteria is sealed (write-once); content changed since seal.\nSet CLAVAIN_RESEAL=1 to re-seal deliberately (this is an audit event)")
		}
		fmt.Fprintf(os.Stderr, "set-artifact: RESEAL of acceptance-criteria %s (old %.12s → new %.12s)\n", path, strings.TrimSpace(string(existing)), hexSum)
	}
	return os.WriteFile(sealPath, []byte(hexSum+"\n"), 0o644)
}

// verifySeal reports whether path's content still matches its seal sidecar.
func verifySeal(path string) error {
	sealPath := path + ".seal"
	want, err := os.ReadFile(sealPath)
	if err != nil {
		return fmt.Errorf("no seal found at %s", sealPath)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("cannot read sealed file: %w", err)
	}
	sum := sha256.Sum256(data)
	if hex.EncodeToString(sum[:]) != strings.TrimSpace(string(want)) {
		return fmt.Errorf("SEAL MISMATCH: %s was modified after sealing", path)
	}
	return nil
}

// cmdVerifySeal is the CLI entry point for the verify-seal verb.
// Usage: verify-seal <path>
func cmdVerifySeal(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: verify-seal <path>")
	}
	if err := verifySeal(args[0]); err != nil {
		return err
	}
	fmt.Println("seal ok")
	return nil
}
