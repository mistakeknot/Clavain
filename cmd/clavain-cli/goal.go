package main

import (
	"fmt"
	"os"
	"strings"
)

// formatGoalPaste renders the mint result: durable entity id + the exact
// /goal invocation the user pastes to bind a session to it.
func formatGoalPaste(goalID, condition string) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Goal minted: %s\n", goalID)
	fmt.Fprintf(&b, "Ready to paste:\n\n  /goal %s\n", condition)
	return b.String()
}

// cmdGoalMint lints, mints the intercore Goal entity, optionally binds a
// bead, and prints the /goal paste text (brainstorm KD 2/7).
// Usage: goal-mint <title> --project=<dir> --condition-file=<path>
//
//	[--charter=<path>] [--complexity=N] [--bead=<id>]
func cmdGoalMint(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: goal-mint <title> --project=<dir> --condition-file=<path> [--charter=] [--complexity=] [--bead=]")
	}
	title := args[0]
	flags := parseAuthzArgs(args[1:])
	project := flags["project"]
	conditionFile := flags["condition-file"]
	if project == "" || conditionFile == "" {
		return fmt.Errorf("goal-mint: --project and --condition-file are required")
	}
	condBytes, err := os.ReadFile(conditionFile)
	if err != nil {
		return fmt.Errorf("goal-mint: read condition: %w", err)
	}
	condition := strings.TrimSpace(string(condBytes))

	createArgs := []string{
		"goal", "create",
		"--title=" + title,
		"--project=" + project,
		"--condition-file=" + conditionFile,
	}
	if v := flags["charter"]; v != "" {
		createArgs = append(createArgs, "--charter="+v)
	}
	if v := flags["complexity"]; v != "" {
		createArgs = append(createArgs, "--complexity="+v)
	}
	if v := flags["bead"]; v != "" {
		createArgs = append(createArgs, "--bead="+v)
	}

	var res struct {
		ID string `json:"id"`
	}
	if err := runICJSON(&res, createArgs...); err != nil {
		return fmt.Errorf("goal-mint: ic goal create: %w", err)
	}
	if beadID := flags["bead"]; beadID != "" && bdAvailable() {
		if _, err := runBD("state", beadID, "ic_goal_id", res.ID); err != nil {
			fmt.Fprintf(os.Stderr, "goal-mint: bead bind failed (non-fatal): %v\n", err)
		}
	}

	fmt.Print(formatGoalPaste(res.ID, condition))
	return nil
}
