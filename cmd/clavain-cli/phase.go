package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// nextStep returns the static fallback next step for a given phase.
// This matches the Bash sprint_next_step() fallback case statement.
func nextStep(phase string) string {
	switch phase {
	case "brainstorm":
		return "strategy"
	case "brainstorm-reviewed":
		return "strategy"
	case "strategized":
		return "write-plan"
	case "planned":
		return "flux-drive"
	case "plan-reviewed":
		return "work"
	case "executing":
		return "quality-gates"
	case "shipping":
		return "reflect"
	case "reflect":
		return "done"
	case "done":
		return "done"
	default:
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
		return "ship"
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

	// Advance via ic
	var result AdvanceResult
	err = runICJSON(&result, "run", "advance", runID, "--priority=0")
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

	// Invalidate caches
	invalidateCaches()

	// Record phase tokens (best-effort)
	recordPhaseTokens(beadID, currentPhase)

	fmt.Fprintf(os.Stderr, "Phase: %s \u2192 %s (auto-advancing)\n", fromPhase, toPhase)
	return nil
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
		return nil
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

	_, gateErr := runIC("gate", "check", runID)
	if gateErr != nil {
		return fmt.Errorf("gate blocked for %s", targetPhase)
	}

	return nil
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

	runID, err := resolveRunID(beadID)
	if err != nil {
		return nil // fail-safe: no run, no artifact recording
	}

	// Get current phase
	phaseOut, err := runIC("run", "phase", runID)
	if err != nil {
		phaseOut = []byte("unknown")
	}
	phase := string(phaseOut)

	// Add artifact via ic
	_, err = runIC("run", "artifact", "add", runID,
		"--phase="+phase,
		"--path="+artifactPath,
		"--type="+artifactType)
	if err != nil {
		// Fail-safe: log but don't fail
		fmt.Fprintf(os.Stderr, "set-artifact: warning: %v\n", err)
	}
	return nil
}

// cmdGetArtifact retrieves an artifact path by type from the current run.
// Usage: get-artifact <bead_id> <type>
func cmdGetArtifact(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: get-artifact <bead_id> <type>")
	}
	beadID := args[0]
	artifactType := args[1]

	runID, err := resolveRunID(beadID)
	if err != nil {
		return fmt.Errorf("no run for bead %q", beadID)
	}

	var artifacts []Artifact
	err = runICJSON(&artifacts, "run", "artifact", "list", runID)
	if err != nil {
		return fmt.Errorf("get-artifact: %w", err)
	}

	// Filter by type, return first match
	for _, a := range artifacts {
		if a.Type == artifactType {
			fmt.Println(a.Path)
			return nil
		}
	}

	// No match found
	return fmt.Errorf("no artifact of type %q found", artifactType)
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
	return cmdRecordPhase(args[:2])
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
	case "brainstorm":
		return "strategize"
	case "brainstorm-reviewed":
		return "strategize"
	case "strategized":
		return "plan"
	case "planned":
		return "execute"
	case "plan-reviewed":
		return "execute"
	case "executing":
		return "continue"
	case "shipping":
		return "ship"
	case "done":
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
