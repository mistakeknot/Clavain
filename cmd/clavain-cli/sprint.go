package main

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// runIDCache caches bead_id → run_id mappings for the process lifetime.
var runIDCache = map[string]string{}

// resolveRunID resolves a bead ID to an Intercore run ID.
// Uses bd state <beadID> ic_run_id, caches the result.
func resolveRunID(beadID string) (string, error) {
	if beadID == "" {
		return "", fmt.Errorf("empty bead ID")
	}

	// Cache hit
	if rid, ok := runIDCache[beadID]; ok {
		return rid, nil
	}

	// Resolve from bead
	out, err := runBD("state", beadID, "ic_run_id")
	if err != nil {
		return "", fmt.Errorf("resolve run ID for %s: %w", beadID, err)
	}
	runID := strings.TrimSpace(string(out))
	if runID == "" || runID == "null" || strings.HasPrefix(runID, "(no ") {
		return "", fmt.Errorf("no run ID for bead %s", beadID)
	}

	runIDCache[beadID] = runID
	return runID, nil
}

// defaultBudget returns the token budget for a given complexity tier.
// Matches _sprint_default_budget in lib-sprint.sh.
func defaultBudget(complexity int) int64 {
	switch complexity {
	case 1:
		return 50000
	case 2:
		return 100000
	case 3:
		return 250000
	case 4:
		return 500000
	default:
		return 1000000
	}
}

// beadIDPattern matches bead IDs like "iv-abc123" from bd create output.
var beadIDPattern = regexp.MustCompile(`[A-Za-z]+-[a-z0-9]+`)

// defaultPhases is the standard sprint phase sequence.
var defaultPhases = []string{
	"brainstorm", "brainstorm-reviewed", "strategized", "planned",
	"plan-reviewed", "executing", "shipping", "reflect", "done",
}

// defaultActions is the default phase→action mapping for kernel-driven routing.
var defaultActions = map[string]any{
	"brainstorm":   map[string]string{"command": "/clavain:strategy", "mode": "interactive"},
	"strategized":  map[string]string{"command": "/clavain:write-plan", "mode": "interactive"},
	"planned":      map[string]string{"command": "/interflux:flux-drive", "args": `["${artifact:plan}"]`, "mode": "interactive"},
	"plan-reviewed": map[string]string{"command": "/clavain:work", "args": `["${artifact:plan}"]`, "mode": "both"},
	"executing":    map[string]string{"command": "/clavain:quality-gates", "mode": "interactive"},
	"shipping":     map[string]string{"command": "/clavain:reflect", "mode": "interactive"},
}

// cmdSprintCreate creates a sprint: bd epic + ic run, links them.
// Args: <title> [complexity] [lane]
// Output: bead ID (plain text) on stdout.
func cmdSprintCreate(args []string) error {
	title := "Sprint"
	if len(args) > 0 && args[0] != "" {
		title = args[0]
	}
	complexity := 3
	if len(args) > 1 {
		if c, err := strconv.Atoi(args[1]); err == nil && c >= 1 && c <= 5 {
			complexity = c
		}
	}
	lane := ""
	if len(args) > 2 {
		lane = args[2]
	}

	if !icAvailable() {
		fmt.Fprintln(os.Stderr, "Sprint requires intercore (ic). Install ic or use beads directly for task tracking.")
		fmt.Print("")
		return fmt.Errorf("ic unavailable")
	}

	// Create bead for tracking (fatal when bd is available)
	var sprintID string
	if bdAvailable() {
		out, err := runBD("create", "--title="+title, "--type=epic", "--priority=2")
		if err != nil {
			fmt.Fprintln(os.Stderr, "sprint_create: bead creation failed")
			fmt.Print("")
			return fmt.Errorf("bead creation failed: %w", err)
		}
		match := beadIDPattern.FindString(string(out))
		if match == "" {
			fmt.Fprintln(os.Stderr, "sprint_create: bead creation failed")
			fmt.Print("")
			return fmt.Errorf("could not parse bead ID from bd output")
		}
		sprintID = match

		// Set sprint state and status (non-fatal)
		runBD("set-state", sprintID, "sprint=true")
		runBD("update", sprintID, "--status=in_progress")

		// Tag with lane label if specified
		if lane != "" {
			runBD("label", "add", sprintID, "lane:"+lane)
		}
	}

	// Use bead ID as scope_id, or generate a placeholder
	scopeID := sprintID
	if scopeID == "" {
		scopeID = fmt.Sprintf("sprint-%d", time.Now().Unix())
	}

	// Build ic run create args
	tokenBudget := defaultBudget(complexity)

	phasesJSON, _ := json.Marshal(defaultPhases)
	actionsJSON, _ := json.Marshal(defaultActions)

	icArgs := []string{
		"run", "create",
		"--project=" + mustGetwd(),
		"--goal=" + title,
		"--complexity=" + strconv.Itoa(complexity),
		"--phases=" + string(phasesJSON),
		"--scope-id=" + scopeID,
		"--token-budget=" + strconv.FormatInt(tokenBudget, 10),
		"--actions=" + string(actionsJSON),
	}

	runIDOut, err := runIC(icArgs...)
	if err != nil {
		fmt.Fprintln(os.Stderr, "sprint_create: ic run create failed")
		if sprintID != "" {
			runBD("update", sprintID, "--status=cancelled")
		}
		fmt.Print("")
		return fmt.Errorf("ic run create: %w", err)
	}
	runID := string(runIDOut)

	if runID == "" {
		fmt.Fprintln(os.Stderr, "sprint_create: ic run create failed")
		if sprintID != "" {
			runBD("update", sprintID, "--status=cancelled")
		}
		fmt.Print("")
		return fmt.Errorf("ic run create returned empty ID")
	}

	// Verify ic run is at brainstorm phase
	phaseOut, err := runIC("run", "phase", runID)
	if err != nil || string(phaseOut) != "brainstorm" {
		fmt.Fprintf(os.Stderr, "sprint_create: ic run verification failed (phase=%s)\n", string(phaseOut))
		runIC("run", "cancel", runID)
		if sprintID != "" {
			runBD("update", sprintID, "--status=cancelled")
		}
		fmt.Print("")
		return fmt.Errorf("ic run phase verification failed")
	}

	// Store run_id on bead AFTER verification
	if sprintID != "" {
		_, err := runBD("set-state", sprintID, "ic_run_id="+runID)
		if err != nil {
			fmt.Fprintln(os.Stderr, "sprint_create: failed to write ic_run_id to bead")
			runIC("run", "cancel", runID)
			runBD("update", sprintID, "--status=cancelled")
			fmt.Print("")
			return fmt.Errorf("failed to write ic_run_id to bead: %w", err)
		}
		runBD("set-state", sprintID, "token_budget="+strconv.FormatInt(tokenBudget, 10))
	}

	// Load default agency specs if available
	agencyDir := os.Getenv("CLAVAIN_CONFIG_DIR")
	if agencyDir != "" {
		specDir := agencyDir + "/agency"
		if fi, err := os.Stat(specDir); err == nil && fi.IsDir() {
			_, err := runIC("agency", "load", "all", "--run="+runID, "--spec-dir="+specDir)
			if err != nil {
				fmt.Fprintf(os.Stderr, "warning: agency spec load failed for run %s (non-blocking)\n", runID)
			}
		}
	}

	// Cache the run ID for this session
	runIDCache[scopeID] = runID

	fmt.Print(sprintID)
	return nil
}

// cmdSprintFindActive finds active sprint runs.
// Output: JSON array [{id, title, phase, run_id}] or "[]"
func cmdSprintFindActive(args []string) error {
	if !icAvailable() {
		fmt.Print("[]")
		return nil
	}

	var runs []Run
	err := runICJSON(&runs, "run", "list", "--active")
	if err != nil {
		fmt.Print("[]")
		return nil
	}

	results := make([]ActiveSprint, 0, len(runs))
	for i, run := range runs {
		if i >= 100 {
			break
		}
		if run.ScopeID == "" {
			continue
		}

		title := run.Goal
		if title == "" {
			// Try to get title from bd
			out, err := runBD("show", run.ScopeID)
			if err == nil {
				line := strings.SplitN(string(out), "\n", 2)[0]
				// Parse: strip prefix up to "· " and suffix from " ["
				if idx := strings.Index(line, "· "); idx >= 0 {
					line = line[idx+len("· "):]
				}
				if idx := strings.Index(line, " ["); idx >= 0 {
					line = line[:idx]
				}
				line = strings.TrimSpace(line)
				if line != "" {
					title = line
				}
			}
			if title == "" {
				title = "Untitled"
			}
		}

		results = append(results, ActiveSprint{
			ID:    run.ScopeID,
			Title: title,
			Phase: run.Phase,
			RunID: run.ID,
		})
	}

	out, err := json.Marshal(results)
	if err != nil {
		fmt.Print("[]")
		return nil
	}
	fmt.Print(string(out))
	return nil
}

// RunEvent represents an event from ic run events.
type RunEvent struct {
	EventType string `json:"event_type"`
	ToPhase   string `json:"to_phase"`
	CreatedAt string `json:"created_at"`
}

// cmdSprintReadState assembles sprint state from multiple ic queries.
// Args: <bead_id>
// Output: SprintState JSON or "{}" on failure.
func cmdSprintReadState(args []string) error {
	if len(args) < 1 || args[0] == "" {
		fmt.Print("{}")
		return nil
	}
	sprintID := args[0]

	runID, err := resolveRunID(sprintID)
	if err != nil {
		fmt.Print("{}")
		return nil
	}

	// Get run status
	var run Run
	err = runICJSON(&run, "run", "status", runID)
	if err != nil {
		fmt.Print("{}")
		return nil
	}

	// Artifacts from ic run artifact list
	artifacts := map[string]string{}
	var artifactList []Artifact
	err = runICJSON(&artifactList, "run", "artifact", "list", runID)
	if err == nil {
		for _, a := range artifactList {
			if a.Type != "" && a.Path != "" {
				artifacts[a.Type] = a.Path
			}
		}
	}

	// Phase history from ic run events
	history := map[string]string{}
	var events []RunEvent
	eventsOut, err := runIC("--json", "run", "events", runID)
	if err == nil && len(eventsOut) > 0 {
		if json.Unmarshal(eventsOut, &events) == nil {
			for _, ev := range events {
				if ev.EventType == "advance" && ev.ToPhase != "" {
					history[ev.ToPhase+"_at"] = ev.CreatedAt
				}
			}
		}
	}

	// Active session from agent tracking
	activeSession := ""
	var agents []RunAgent
	err = runICJSON(&agents, "run", "agent", "list", runID)
	if err == nil {
		for _, a := range agents {
			if a.Status == "active" {
				activeSession = a.Name
				break
			}
		}
	}

	// Token budget and spend
	tokenBudget := run.TokenBudget
	var tokensSpent int64
	var tokenAgg TokenAgg
	err = runICJSON(&tokenAgg, "run", "tokens", runID)
	if err == nil {
		tokensSpent = tokenAgg.InputTokens + tokenAgg.OutputTokens
	}

	state := SprintState{
		ID:            sprintID,
		Phase:         run.Phase,
		Artifacts:     artifacts,
		History:       history,
		Complexity:    strconv.Itoa(run.Complexity),
		AutoAdvance:   strconv.FormatBool(run.AutoAdvance),
		ActiveSession: activeSession,
		TokenBudget:   tokenBudget,
		TokensSpent:   tokensSpent,
	}

	out, err := json.Marshal(state)
	if err != nil {
		fmt.Print("{}")
		return nil
	}
	fmt.Print(string(out))
	return nil
}

// cmdSprintTrackAgent tracks an agent dispatch against a sprint run.
// Args: <bead_id> <agent_name> [agent_type] [dispatch_id]
func cmdSprintTrackAgent(args []string) error {
	if len(args) < 2 || args[0] == "" || args[1] == "" {
		return nil
	}
	sprintID := args[0]
	agentName := args[1]
	agentType := "claude"
	if len(args) > 2 && args[2] != "" {
		agentType = args[2]
	}
	dispatchID := ""
	if len(args) > 3 {
		dispatchID = args[3]
	}

	runID, err := resolveRunID(sprintID)
	if err != nil {
		return nil // fail-safe
	}

	icArgs := []string{"run", "agent", "add", runID, "--type=" + agentType}
	if agentName != "" {
		icArgs = append(icArgs, "--name="+agentName)
	}
	if dispatchID != "" {
		icArgs = append(icArgs, "--dispatch-id="+dispatchID)
	}

	runIC(icArgs...)
	return nil
}

// cmdSprintCompleteAgent marks an agent as completed.
// Args: <agent_id> [status]
func cmdSprintCompleteAgent(args []string) error {
	if len(args) < 1 || args[0] == "" {
		return nil
	}
	agentID := args[0]
	status := "completed"
	if len(args) > 1 && args[1] != "" {
		status = args[1]
	}

	if !icAvailable() {
		return nil
	}

	runIC("run", "agent", "update", agentID, "--status="+status)
	return nil
}

// cmdSprintInvalidateCaches deletes discovery_brief state entries.
func cmdSprintInvalidateCaches(args []string) error {
	if !icAvailable() {
		return nil
	}

	// List all scopes for discovery_brief, then delete each
	out, err := runIC("state", "list", "discovery_brief")
	if err != nil {
		return nil
	}

	scopes := strings.Split(string(out), "\n")
	for _, scope := range scopes {
		scope = strings.TrimSpace(scope)
		if scope == "" {
			continue
		}
		runIC("state", "delete", "discovery_brief", scope)
	}
	return nil
}

// mustGetwd returns the current working directory, falling back to ".".
func mustGetwd() string {
	wd, err := os.Getwd()
	if err != nil {
		return "."
	}
	return wd
}
