package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	// beadClaimStaleSeconds is the staleness threshold for bead claims (45 minutes).
	// Matches heartbeat interval (60s) + TTL in lib-discovery.sh (2700s).
	beadClaimStaleSeconds = 2700
	// sprintClaimStaleMinutes is the staleness threshold for sprint session claims (60 minutes).
	sprintClaimStaleMinutes = 60
)

// isClaimStale returns true if the age in seconds exceeds the 45-minute threshold.
// Matches bash: `if [[ $age_sec -lt 2700 ]]` — so exactly 2700 is NOT stale.
func isClaimStale(ageSeconds int64) bool {
	return ageSeconds > beadClaimStaleSeconds
}

// beadShowJSON is a minimal struct for parsing bd show --json output.
type beadShowJSON struct {
	Status string `json:"status"`
}

// isBeadClosed returns true if the bead's status is "closed".
// Returns false if bd is unavailable or the bead doesn't exist.
func isBeadClosed(beadID string) bool {
	out, err := runBD("show", beadID, "--json")
	if err != nil {
		return false
	}
	var beads []beadShowJSON
	if err := json.Unmarshal(out, &beads); err != nil {
		return false
	}
	return len(beads) > 0 && beads[0].Status == "closed"
}

// cmdSprintClaim acquires a sprint claim for the given session.
// Args: bead_id session_id
// Acquires ic lock, checks active agents, registers session, releases lock, also claims bead.
// Exit 1 on conflict (< 60 min).
func cmdSprintClaim(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: sprint-claim <bead_id> <session_id>")
	}
	beadID := args[0]
	sessionID := args[1]
	if beadID == "" || sessionID == "" {
		return nil
	}

	if !icAvailable() {
		return fmt.Errorf("sprint_claim: ic not available")
	}

	// Resolve run ID
	runID, err := resolveRunID(beadID)
	if err != nil {
		return fmt.Errorf("sprint_claim: no ic run found for %s", beadID)
	}

	// Acquire lock
	_, lockErr := runIC("lock", "acquire", "sprint-claim", beadID, "--timeout=500ms")
	if lockErr != nil {
		// Fall back to mkdir-based lock
		lockErr = fallbackLock("sprint-claim", beadID)
		if lockErr != nil {
			return fmt.Errorf("sprint_claim: lock contention for %s", beadID)
		}
		defer fallbackUnlock("sprint-claim", beadID)
	} else {
		defer func() {
			_, _ = runIC("lock", "release", "sprint-claim", beadID)
		}()
	}

	// List agents for this run
	var agents []RunAgent
	agentsOut, err := runIC("--json", "run", "agent", "list", runID)
	if err != nil {
		agents = []RunAgent{}
	} else {
		if err := json.Unmarshal(agentsOut, &agents); err != nil {
			agents = []RunAgent{}
		}
	}

	// Filter active session agents
	var activeAgents []RunAgent
	for _, a := range agents {
		if a.Status == "active" && a.AgentType == "session" {
			activeAgents = append(activeAgents, a)
		}
	}

	if len(activeAgents) > 0 {
		existing := activeAgents[0]
		existingName := existing.Name
		if existingName == "" {
			existingName = "unknown"
		}

		// Already claimed by us?
		if existingName == sessionID {
			return nil // exit 0
		}

		// Check age
		createdAt := existing.CreatedAt
		if createdAt == "" {
			createdAt = "1970-01-01T00:00:00Z"
		}
		created, err := time.Parse(time.RFC3339, createdAt)
		if err != nil {
			created = time.Unix(0, 0)
		}
		ageMinutes := int(time.Since(created).Minutes())

		if ageMinutes < sprintClaimStaleMinutes {
			shortName := existingName
			if len(shortName) > 8 {
				shortName = shortName[:8]
			}
			return fmt.Errorf("sprint_claim: sprint %s is claimed by session %s (%dm ago)",
				beadID, shortName, ageMinutes)
		}

		// Stale session — mark the old agent as failed
		if existing.ID != "" {
			_, _ = runIC("run", "agent", "update", existing.ID, "--status=failed")
		}
	}

	// Register new session agent
	_, err = runIC("run", "agent", "add", runID, "--type=session", "--name="+sessionID)
	if err != nil {
		return fmt.Errorf("sprint_claim: failed to register session agent for %s", beadID)
	}

	// Also set bd claim for cross-session visibility (ignore errors)
	_ = cmdBeadClaim([]string{beadID, sessionID})
	return nil
}

// cmdSprintRelease releases a sprint claim.
// Args: bead_id
func cmdSprintRelease(args []string) error {
	if len(args) < 1 || args[0] == "" {
		return nil
	}
	beadID := args[0]

	// Release bd claim first
	_ = cmdBeadRelease([]string{beadID})

	// Resolve run ID
	runID, err := resolveRunID(beadID)
	if err != nil {
		return nil // no run — nothing to release
	}

	// List agents and mark active session agents as completed
	var agents []RunAgent
	agentsOut, err := runIC("--json", "run", "agent", "list", runID)
	if err != nil {
		return nil
	}
	if err := json.Unmarshal(agentsOut, &agents); err != nil {
		return nil
	}

	for _, a := range agents {
		if a.Status == "active" && a.AgentType == "session" && a.ID != "" {
			_, _ = runIC("run", "agent", "update", a.ID, "--status=completed")
		}
	}

	// If the bead is closed, cancel the ic run entirely to prevent stale sprint markers
	if isBeadClosed(beadID) {
		_, _ = runIC("run", "cancel", runID)
	}
	return nil
}

// cmdBeadClaim acquires an advisory bead claim via atomic bd update.
// Args: bead_id [session_id]
// Combines claim identity labels with status update in a single bd call
// to eliminate the crash window between claim and identity write.
// Exit 1 if a fresh claim exists from another session.
func cmdBeadClaim(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: bead-claim <bead_id> [session_id]")
	}
	beadID := args[0]
	sessionID := os.Getenv("CLAUDE_SESSION_ID")
	if sessionID == "" {
		sessionID = "unknown"
	}
	if len(args) > 1 && args[1] != "" {
		sessionID = args[1]
	}

	if !bdAvailable() {
		return nil
	}

	// Check existing claim
	existingClaim := ""
	if out, err := runBD("state", beadID, "claimed_by"); err == nil {
		existingClaim = strings.TrimSpace(string(out))
	}

	if existingClaim != "" && !strings.HasPrefix(existingClaim, "(no ") && existingClaim != "released" {
		// Same session? Already claimed by us.
		if existingClaim == sessionID {
			return nil
		}

		// Check staleness
		existingAt := ""
		if out, err := runBD("state", beadID, "claimed_at"); err == nil {
			existingAt = strings.TrimSpace(string(out))
		}

		if existingAt != "" && !strings.HasPrefix(existingAt, "(no ") {
			epoch, err := strconv.ParseInt(existingAt, 10, 64)
			if err == nil {
				ageSeconds := time.Now().Unix() - epoch
				if ageSeconds < beadClaimStaleSeconds {
					shortSession := existingClaim
					if len(shortSession) > 8 {
						shortSession = shortSession[:8]
					}
					ageMin := ageSeconds / 60
					return fmt.Errorf("bead %s claimed by session %s (%dm ago)",
						beadID, shortSession, ageMin)
				}
			}
		}
	}

	// Build atomic update args: remove old labels, add new ones
	epoch := strconv.FormatInt(time.Now().Unix(), 10)
	updateArgs := []string{"update", beadID}
	if existingClaim != "" && !strings.HasPrefix(existingClaim, "(no ") {
		updateArgs = append(updateArgs, "--remove-label", "claimed_by:"+existingClaim)
	}
	existingAt := ""
	if out, err := runBD("state", beadID, "claimed_at"); err == nil {
		existingAt = strings.TrimSpace(string(out))
	}
	if existingAt != "" && !strings.HasPrefix(existingAt, "(no ") {
		updateArgs = append(updateArgs, "--remove-label", "claimed_at:"+existingAt)
	}
	updateArgs = append(updateArgs,
		"--add-label", "claimed_by:"+sessionID,
		"--add-label", "claimed_at:"+epoch,
	)

	_, _ = runBD(updateArgs...)
	return nil
}

// cmdBeadRelease clears a bead claim.
// Args: bead_id
// Only releases if we own the claim (or claim is empty/stale).
// Uses atomic bd update to set sentinel labels in a single call.
func cmdBeadRelease(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: bead-release <bead_id>")
	}
	beadID := args[0]

	if !bdAvailable() {
		return nil
	}

	// Ownership check: only release if we own the claim
	ourSession := os.Getenv("CLAUDE_SESSION_ID")
	if ourSession == "" {
		ourSession = "unknown"
	}
	currentClaimer := ""
	if out, err := runBD("state", beadID, "claimed_by"); err == nil {
		currentClaimer = strings.TrimSpace(string(out))
	}
	if currentClaimer != "" && !strings.HasPrefix(currentClaimer, "(no ") && currentClaimer != "released" && currentClaimer != ourSession {
		return nil // Another session holds this — don't release
	}

	// Build atomic update: remove old labels, add sentinel labels
	updateArgs := []string{"update", beadID}
	if currentClaimer != "" && !strings.HasPrefix(currentClaimer, "(no ") {
		updateArgs = append(updateArgs, "--remove-label", "claimed_by:"+currentClaimer)
	}
	existingAt := ""
	if out, err := runBD("state", beadID, "claimed_at"); err == nil {
		existingAt = strings.TrimSpace(string(out))
	}
	if existingAt != "" && !strings.HasPrefix(existingAt, "(no ") {
		updateArgs = append(updateArgs, "--remove-label", "claimed_at:"+existingAt)
	}
	updateArgs = append(updateArgs,
		"--add-label", "claimed_by:released",
		"--add-label", "claimed_at:0",
	)

	_, _ = runBD(updateArgs...)
	return nil
}

// cmdBeadHeartbeat refreshes the claimed_at timestamp for an active bead claim.
// Only refreshes if we own the claim (or claim is unowned). Silently succeeds otherwise.
// Args: bead_id
func cmdBeadHeartbeat(args []string) error {
	if len(args) < 1 || args[0] == "" {
		return nil
	}
	beadID := args[0]

	if !bdAvailable() {
		return nil
	}

	// Only heartbeat if we own the claim
	ourSession := os.Getenv("CLAUDE_SESSION_ID")
	if ourSession == "" {
		ourSession = "unknown"
	}
	currentClaimer := ""
	if out, err := runBD("state", beadID, "claimed_by"); err == nil {
		currentClaimer = strings.TrimSpace(string(out))
	}

	// Refresh if: we own it, it's unclaimed, or it's the "unknown" sentinel
	if currentClaimer != "" &&
		!strings.HasPrefix(currentClaimer, "(no ") &&
		currentClaimer != "released" &&
		currentClaimer != "unknown" &&
		currentClaimer != ourSession {
		return nil // Another session holds this — don't touch
	}

	// Atomic refresh: remove old labels, add new ones in single call
	epoch := strconv.FormatInt(time.Now().Unix(), 10)
	updateArgs := []string{"update", beadID}
	if currentClaimer != "" && !strings.HasPrefix(currentClaimer, "(no ") {
		updateArgs = append(updateArgs, "--remove-label", "claimed_by:"+currentClaimer)
	}
	existingAt := ""
	if out, err := runBD("state", beadID, "claimed_at"); err == nil {
		existingAt = strings.TrimSpace(string(out))
	}
	if existingAt != "" && !strings.HasPrefix(existingAt, "(no ") {
		updateArgs = append(updateArgs, "--remove-label", "claimed_at:"+existingAt)
	}
	updateArgs = append(updateArgs,
		"--add-label", "claimed_by:"+ourSession,
		"--add-label", "claimed_at:"+epoch,
	)

	_, _ = runBD(updateArgs...)
	return nil
}

// fallbackLock acquires a directory-based lock as fallback when ic lock is unavailable.
func fallbackLock(name, scope string) error {
	lockDir := fmt.Sprintf("/tmp/intercore/locks/%s/%s", name, scope)
	parentDir := fmt.Sprintf("/tmp/intercore/locks/%s", name)
	_ = os.MkdirAll(parentDir, 0755)

	maxRetries := 10
	for i := 0; i < maxRetries; i++ {
		if err := os.Mkdir(lockDir, 0755); err == nil {
			// Write owner.json
			hostname, _ := os.Hostname()
			if hostname == "" {
				hostname = "unknown"
			}
			owner := fmt.Sprintf("%d:%s", os.Getpid(), hostname)
			data := fmt.Sprintf(`{"pid":%d,"host":"%s","owner":"%s","created":%d}`,
				os.Getpid(), hostname, owner, time.Now().Unix())
			_ = os.WriteFile(lockDir+"/owner.json", []byte(data+"\n"), 0644)
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("lock contention: %s/%s", name, scope)
}

// fallbackUnlock releases a directory-based lock.
func fallbackUnlock(name, scope string) {
	lockDir := fmt.Sprintf("/tmp/intercore/locks/%s/%s", name, scope)
	_ = os.Remove(lockDir + "/owner.json")
	_ = os.Remove(lockDir)
}
