package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"
)

// addCompletedStep appends step to ckpt.CompletedSteps if not already present.
// Returns the updated Checkpoint (value semantics).
func addCompletedStep(ckpt Checkpoint, step string) Checkpoint {
	for _, s := range ckpt.CompletedSteps {
		if s == step {
			return ckpt
		}
	}
	ckpt.CompletedSteps = append(ckpt.CompletedSteps, step)
	sort.Strings(ckpt.CompletedSteps)
	return ckpt
}

// addKeyDecision appends a key decision, deduplicates, and keeps the last 5.
func addKeyDecision(ckpt Checkpoint, decision string) Checkpoint {
	for _, d := range ckpt.KeyDecisions {
		if d == decision {
			return ckpt
		}
	}
	ckpt.KeyDecisions = append(ckpt.KeyDecisions, decision)
	sort.Strings(ckpt.KeyDecisions)
	if len(ckpt.KeyDecisions) > 5 {
		ckpt.KeyDecisions = ckpt.KeyDecisions[len(ckpt.KeyDecisions)-5:]
	}
	return ckpt
}

// resolveRunID is defined in sprint.go (with caching).

// currentRunID gets the active run for the current working directory.
func currentRunID() (string, error) {
	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}
	out, err := runIC("run", "current", "--project="+dir)
	if err != nil {
		return "", err
	}
	runID := strings.TrimSpace(string(out))
	if runID == "" {
		return "", fmt.Errorf("no active run for %s", dir)
	}
	return runID, nil
}

// readCheckpoint reads the checkpoint from ic state for the given run ID.
// Returns an empty Checkpoint if not found.
func readCheckpoint(runID string) Checkpoint {
	out, err := runIC("state", "get", "checkpoint", runID)
	if err != nil || len(out) == 0 {
		return Checkpoint{}
	}
	var ckpt Checkpoint
	if err := json.Unmarshal(out, &ckpt); err != nil {
		return Checkpoint{}
	}
	return ckpt
}

// cmdCheckpointWrite writes or updates a checkpoint after a sprint step completes.
// Args: bead_id phase step plan_path [key_decision]
func cmdCheckpointWrite(args []string) error {
	if len(args) < 3 {
		return fmt.Errorf("usage: checkpoint-write <bead_id> <phase> <step> [plan_path] [key_decision]")
	}
	beadID := args[0]
	phase := args[1]
	step := args[2]
	planPath := ""
	if len(args) > 3 {
		planPath = args[3]
	}
	keyDecision := ""
	if len(args) > 4 {
		keyDecision = args[4]
	}

	// Get git SHA
	gitSHA := "unknown"
	if out, err := runGit("rev-parse", "HEAD"); err == nil {
		gitSHA = string(out)
	}

	timestamp := time.Now().UTC().Format("2006-01-02T15:04:05Z")

	// Resolve run ID — if unavailable, silently succeed (matches bash return 0)
	runID, err := resolveRunID(beadID)
	if err != nil {
		return nil
	}

	// Read existing checkpoint
	ckpt := readCheckpoint(runID)

	// Merge fields
	ckpt.Bead = beadID
	ckpt.Phase = phase
	if planPath != "" {
		ckpt.PlanPath = planPath
	}
	ckpt.GitSHA = gitSHA
	ckpt.UpdatedAt = timestamp

	// Add completed step (deduplicated)
	ckpt = addCompletedStep(ckpt, step)

	// Add key decision if provided (deduplicated, keep last 5)
	if keyDecision != "" {
		ckpt = addKeyDecision(ckpt, keyDecision)
	}

	// Serialize and write
	data, err := json.Marshal(ckpt)
	if err != nil {
		return fmt.Errorf("marshal checkpoint: %w", err)
	}

	// Write via ic state set checkpoint <run_id> — pipe JSON on stdin
	writeICState("checkpoint", runID, string(data))
	return nil
}

// cmdCheckpointRead reads the current checkpoint.
// Args: [bead_id]
// Output: JSON or "{}"
func cmdCheckpointRead(args []string) error {
	if !icAvailable() {
		fmt.Println("{}")
		return nil
	}

	var runID string

	// Try bead_id first
	if len(args) > 0 && args[0] != "" {
		if rid, err := resolveRunID(args[0]); err == nil {
			runID = rid
		}
	}

	// Fall back to current run
	if runID == "" {
		if rid, err := currentRunID(); err == nil {
			runID = rid
		}
	}

	if runID == "" {
		fmt.Println("{}")
		return nil
	}

	ckpt := readCheckpoint(runID)
	if ckpt.Bead == "" && ckpt.Phase == "" {
		fmt.Println("{}")
		return nil
	}

	data, err := json.Marshal(ckpt)
	if err != nil {
		fmt.Println("{}")
		return nil
	}
	fmt.Println(string(data))
	return nil
}

// cmdCheckpointValidate compares the checkpoint git SHA against current HEAD.
// Warns on stderr if mismatch. Always exits 0 (the error return is for fatal issues only).
func cmdCheckpointValidate(args []string) error {
	// Read checkpoint (pass bead_id if provided)
	if !icAvailable() {
		return nil
	}

	var runID string
	if len(args) > 0 && args[0] != "" {
		if rid, err := resolveRunID(args[0]); err == nil {
			runID = rid
		}
	}
	if runID == "" {
		if rid, err := currentRunID(); err == nil {
			runID = rid
		}
	}
	if runID == "" {
		return nil
	}

	ckpt := readCheckpoint(runID)
	if ckpt.Bead == "" && ckpt.Phase == "" {
		return nil // no checkpoint
	}

	savedSHA := ckpt.GitSHA
	if savedSHA == "" || savedSHA == "unknown" {
		return nil
	}

	currentSHA := "unknown"
	if out, err := runGit("rev-parse", "HEAD"); err == nil {
		currentSHA = string(out)
	}

	if savedSHA != currentSHA {
		short := func(sha string) string {
			if len(sha) > 8 {
				return sha[:8]
			}
			return sha
		}
		fmt.Fprintf(os.Stderr, "WARNING: Code changed since checkpoint (was %s, now %s)\n",
			short(savedSHA), short(currentSHA))
	}
	return nil
}

// cmdCheckpointClear removes the legacy file-based checkpoint.
func cmdCheckpointClear(args []string) error {
	path := ".clavain/checkpoint.json"
	if envPath := os.Getenv("CLAVAIN_CHECKPOINT_FILE"); envPath != "" {
		path = envPath
	}
	_ = os.Remove(path) // ignore errors (file may not exist)
	return nil
}

// cmdCheckpointCompletedSteps outputs the JSON array of completed step names.
// Output: JSON array or "[]"
func cmdCheckpointCompletedSteps(args []string) error {
	if !icAvailable() {
		fmt.Println("[]")
		return nil
	}

	var runID string
	if len(args) > 0 && args[0] != "" {
		if rid, err := resolveRunID(args[0]); err == nil {
			runID = rid
		}
	}
	if runID == "" {
		if rid, err := currentRunID(); err == nil {
			runID = rid
		}
	}
	if runID == "" {
		fmt.Println("[]")
		return nil
	}

	ckpt := readCheckpoint(runID)
	if ckpt.Bead == "" && ckpt.Phase == "" {
		fmt.Println("[]")
		return nil
	}

	steps := ckpt.CompletedSteps
	if steps == nil {
		steps = []string{}
	}
	data, err := json.Marshal(steps)
	if err != nil {
		fmt.Println("[]")
		return nil
	}
	fmt.Println(string(data))
	return nil
}

// cmdCheckpointStepDone checks if a specific step is in the completed steps.
// Exit 0 if found, exit 1 if not.
func cmdCheckpointStepDone(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: checkpoint-step-done <step_name>")
	}
	stepName := args[0]

	if !icAvailable() {
		os.Exit(1)
	}

	var runID string
	if len(args) > 1 && args[1] != "" {
		if rid, err := resolveRunID(args[1]); err == nil {
			runID = rid
		}
	}
	if runID == "" {
		if rid, err := currentRunID(); err == nil {
			runID = rid
		}
	}
	if runID == "" {
		os.Exit(1)
	}

	ckpt := readCheckpoint(runID)
	if ckpt.Bead == "" && ckpt.Phase == "" {
		os.Exit(1)
	}

	for _, s := range ckpt.CompletedSteps {
		if s == stepName {
			return nil // exit 0
		}
	}
	os.Exit(1)
	return nil // unreachable
}
