package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/mistakeknot/intercore/pkg/contract"
	_ "modernc.org/sqlite"
)

// captureStdout temporarily redirects os.Stdout to devnull while running fn,
// preventing cmd* functions from polluting the intent JSON output.
func captureStdout(fn func() error) error {
	orig := os.Stdout
	devnull, err := os.Open(os.DevNull)
	if err != nil {
		return fn() // fallback: run without capture
	}
	os.Stdout = devnull
	fnErr := fn()
	os.Stdout = orig
	devnull.Close()
	return fnErr
}

// cmdIntentSubmit handles: clavain-cli intent submit
// Accepts JSON intent payload on stdin (preferred — avoids /proc exposure).
// Also supports flags for simple intents without params.
func cmdIntentSubmit(args []string) error {
	var intent contract.Intent

	// Check for stdin JSON (piped input) — this is the primary path.
	// Params should NEVER be passed as CLI flags (visible in /proc/cmdline).
	stat, _ := os.Stdin.Stat()
	if (stat.Mode() & os.ModeCharDevice) == 0 {
		data, err := io.ReadAll(os.Stdin)
		if err != nil {
			return writeError(contract.ErrInvalidIntent, "failed to read stdin", "")
		}
		if err := json.Unmarshal(data, &intent); err != nil {
			return writeError(contract.ErrInvalidIntent, fmt.Sprintf("invalid JSON: %v", err), "")
		}
	} else {
		// Flags path: only for simple intents without sensitive params.
		// NOTE: --params is intentionally NOT supported as a flag (security: /proc exposure).
		var intentType string
		for i := 0; i < len(args); i++ {
			switch {
			case strings.HasPrefix(args[i], "--type="):
				intentType = strings.TrimPrefix(args[i], "--type=")
			case strings.HasPrefix(args[i], "--bead="):
				intent.BeadID = strings.TrimPrefix(args[i], "--bead=")
			case strings.HasPrefix(args[i], "--session="):
				intent.SessionID = strings.TrimPrefix(args[i], "--session=")
			case strings.HasPrefix(args[i], "--key="):
				intent.IdempotencyKey = strings.TrimPrefix(args[i], "--key=")
			}
		}
		intent.Type = intentType
	}

	// Validate
	if err := intent.Validate(); err != nil {
		return writeError(contract.ErrInvalidIntent, err.Error(), "")
	}

	// Route to handler
	result := routeIntent(&intent)

	// Audit log: record every intent submission to intercore events
	logIntentEvent(&intent, result)

	// Output structured JSON
	return json.NewEncoder(os.Stdout).Encode(result)
}

// routeIntent dispatches a validated intent to the appropriate handler.
// This is the policy enforcement point — all writes go through here.
func routeIntent(intent *contract.Intent) *contract.IntentResult {
	switch intent.Type {
	case contract.IntentSprintAdvance:
		return handleSprintAdvance(intent)
	case contract.IntentSprintCreate:
		return handleSprintCreate(intent)
	case contract.IntentSprintClaim:
		return handleSprintClaim(intent)
	case contract.IntentSprintRelease:
		return handleSprintRelease(intent)
	case contract.IntentGateEnforce:
		return handleGateEnforce(intent)
	case contract.IntentBudgetCheck:
		return handleBudgetCheck(intent)
	default:
		return &contract.IntentResult{
			OK:         false,
			IntentType: intent.Type,
			BeadID:     intent.BeadID,
			Error: &contract.IntentError{
				Code:   contract.ErrInvalidIntent,
				Detail: fmt.Sprintf("intent type %q not yet implemented", intent.Type),
			},
		}
	}
}

// handleSprintAdvance wraps the existing cmdSprintAdvance logic with typed I/O.
// NOTE: TOCTOU limitation — there is a race between gate check and phase advance.
func handleSprintAdvance(intent *contract.Intent) *contract.IntentResult {
	phase, _ := intent.Params["phase"].(string)
	artifactPath, _ := intent.Params["artifact_path"].(string)

	args := []string{intent.BeadID, phase}
	if artifactPath != "" {
		args = append(args, artifactPath)
	}

	if err := captureStdout(func() error { return cmdSprintAdvance(args) }); err != nil {
		errStr := err.Error()
		code := contract.ErrInternal
		remediation := ""
		switch {
		case strings.Contains(errStr, "gate") || strings.Contains(errStr, "blocked"):
			code = contract.ErrGateBlocked
			remediation = "Run /interflux:flux-drive on the plan"
		case strings.Contains(errStr, "phase"):
			code = contract.ErrPhaseConflict
		}
		return &contract.IntentResult{
			OK:         false,
			IntentType: intent.Type,
			BeadID:     intent.BeadID,
			Error:      &contract.IntentError{Code: code, Detail: errStr, Remediation: remediation},
		}
	}

	return &contract.IntentResult{
		OK:         true,
		IntentType: intent.Type,
		BeadID:     intent.BeadID,
		Data:       map[string]any{"phase": phase},
	}
}

// handleSprintCreate wraps cmdSprintCreate with typed I/O.
func handleSprintCreate(intent *contract.Intent) *contract.IntentResult {
	title, _ := intent.Params["title"].(string)
	if title == "" {
		title = "Untitled sprint"
	}

	args := []string{title}
	if err := captureStdout(func() error { return cmdSprintCreate(args) }); err != nil {
		return &contract.IntentResult{
			OK:         false,
			IntentType: intent.Type,
			Error:      &contract.IntentError{Code: contract.ErrInternal, Detail: err.Error()},
		}
	}
	return &contract.IntentResult{
		OK:         true,
		IntentType: intent.Type,
		BeadID:     intent.BeadID,
	}
}

// handleSprintClaim wraps bead claiming with typed I/O.
// IMPORTANT: Uses cmdSprintClaim (not cmdBeadClaim) — cmdBeadClaim calls os.Exit(1)
// on active claim conflicts instead of returning an error.
func handleSprintClaim(intent *contract.Intent) *contract.IntentResult {
	args := []string{intent.BeadID, intent.SessionID}
	if err := cmdSprintClaim(args); err != nil {
		code := contract.ErrInternal
		if strings.Contains(err.Error(), "claimed") || strings.Contains(err.Error(), "conflict") || strings.Contains(err.Error(), "lock") {
			code = contract.ErrClaimConflict
		}
		return &contract.IntentResult{
			OK:         false,
			IntentType: intent.Type,
			BeadID:     intent.BeadID,
			Error:      &contract.IntentError{Code: code, Detail: err.Error()},
		}
	}
	return &contract.IntentResult{
		OK:         true,
		IntentType: intent.Type,
		BeadID:     intent.BeadID,
	}
}

// handleSprintRelease wraps bead release with typed I/O.
func handleSprintRelease(intent *contract.Intent) *contract.IntentResult {
	args := []string{intent.BeadID}
	if err := cmdBeadRelease(args); err != nil {
		return &contract.IntentResult{
			OK:         false,
			IntentType: intent.Type,
			BeadID:     intent.BeadID,
			Error:      &contract.IntentError{Code: contract.ErrInternal, Detail: err.Error()},
		}
	}
	return &contract.IntentResult{
		OK:         true,
		IntentType: intent.Type,
		BeadID:     intent.BeadID,
	}
}

// handleGateEnforce wraps gate enforcement with typed I/O.
func handleGateEnforce(intent *contract.Intent) *contract.IntentResult {
	targetPhase, _ := intent.Params["target_phase"].(string)
	artifactPath, _ := intent.Params["artifact_path"].(string)

	args := []string{intent.BeadID, targetPhase, artifactPath}
	if err := cmdEnforceGate(args); err != nil {
		return &contract.IntentResult{
			OK:         false,
			IntentType: intent.Type,
			BeadID:     intent.BeadID,
			Error: &contract.IntentError{
				Code:        contract.ErrGateBlocked,
				Detail:      err.Error(),
				Remediation: "Run /interflux:flux-drive on the plan to satisfy the gate precondition",
			},
		}
	}
	return &contract.IntentResult{
		OK:         true,
		IntentType: intent.Type,
		BeadID:     intent.BeadID,
	}
}

// handleBudgetCheck wraps budget checking with typed I/O.
func handleBudgetCheck(intent *contract.Intent) *contract.IntentResult {
	args := []string{intent.BeadID}
	if err := cmdBudgetRemaining(args); err != nil {
		return &contract.IntentResult{
			OK:         false,
			IntentType: intent.Type,
			BeadID:     intent.BeadID,
			Error:      &contract.IntentError{Code: contract.ErrBudgetExceeded, Detail: err.Error()},
		}
	}
	return &contract.IntentResult{
		OK:         true,
		IntentType: intent.Type,
		BeadID:     intent.BeadID,
	}
}

// logIntentEvent records the intent submission in Intercore's event store.
// Uses direct SQL — internal/event is not importable from outside the module,
// and ic events emit rejects --source=intent.
// Fails silently — audit logging must not block intent execution.
func logIntentEvent(intent *contract.Intent, result *contract.IntentResult) {
	dbPath := findICDB()
	if dbPath == "" {
		return // No DB found — skip audit silently
	}

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return
	}
	defer db.Close()
	db.SetMaxOpenConns(1)
	_, _ = db.Exec("PRAGMA busy_timeout = 5000")

	errorDetail := ""
	if result.Error != nil {
		errorDetail = string(result.Error.Code) + ": " + result.Error.Detail
	}

	successInt := 0
	if result.OK {
		successInt = 1
	}

	_, _ = db.ExecContext(
		context.Background(),
		`INSERT INTO intent_events (
			intent_type, bead_id, idempotency_key, session_id, run_id, success, error_detail
		) VALUES (?, ?, ?, ?, NULLIF(?, ''), ?, NULLIF(?, ''))`,
		intent.Type, intent.BeadID, intent.IdempotencyKey, intent.SessionID,
		"", // run ID — may not exist yet
		successInt, errorDetail,
	)
}

// findICDB locates the intercore database file.
// Validates path safety: must end in .db, no path traversal.
func findICDB() string {
	candidates := []string{
		os.Getenv("IC_DB"),
		".ic.db",
	}
	for _, c := range candidates {
		if c == "" {
			continue
		}
		// Reject path traversal and non-.db paths
		if strings.Contains(c, "..") || !strings.HasSuffix(c, ".db") {
			continue
		}
		if _, err := os.Stat(c); err == nil {
			return c
		}
	}
	return ""
}

// writeError writes a structured error to stdout and returns nil (error already reported).
func writeError(code contract.ErrorCode, detail, remediation string) error {
	result := contract.IntentResult{
		OK: false,
		Error: &contract.IntentError{
			Code:        code,
			Detail:      detail,
			Remediation: remediation,
		},
	}
	return json.NewEncoder(os.Stdout).Encode(result)
}
