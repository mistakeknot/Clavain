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
	// beadClaimStaleSeconds is the staleness threshold for bead claims (2 hours).
	beadClaimStaleSeconds = 7200
	// sprintClaimStaleMinutes is the staleness threshold for sprint session claims (60 minutes).
	sprintClaimStaleMinutes = 60
)

// isClaimStale returns true if the age in seconds exceeds the 2-hour threshold.
// Matches bash: `if [[ $age_seconds -lt 7200 ]]` — so exactly 7200 is NOT stale.
func isClaimStale(ageSeconds int64) bool {
	return ageSeconds > beadClaimStaleSeconds
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
		fmt.Fprintf(os.Stderr, "sprint_claim: no ic run found for %s\n", beadID)
		os.Exit(1)
	}

	// Acquire lock
	_, lockErr := runIC("lock", "acquire", "sprint-claim", beadID, "--timeout=500ms")
	if lockErr != nil {
		// Fall back to mkdir-based lock
		lockErr = fallbackLock("sprint-claim", beadID)
		if lockErr != nil {
			os.Exit(1)
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
			fmt.Fprintf(os.Stderr, "Sprint %s is active in session %s (%dm ago)\n",
				beadID, shortName, ageMinutes)
			os.Exit(1)
		}

		// Stale session — mark the old agent as failed
		if existing.ID != "" {
			_, _ = runIC("run", "agent", "update", existing.ID, "--status=failed")
		}
	}

	// Register new session agent
	_, err = runIC("run", "agent", "add", runID, "--type=session", "--name="+sessionID)
	if err != nil {
		fmt.Fprintf(os.Stderr, "sprint_claim: failed to register session agent for %s\n", beadID)
		os.Exit(1)
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
	return nil
}

// cmdBeadClaim acquires an advisory bead claim via bd set-state.
// Args: bead_id [session_id]
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

	if existingClaim != "" && !strings.HasPrefix(existingClaim, "(no ") {
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
					fmt.Fprintf(os.Stderr, "Bead %s claimed by session %s (%dm ago)\n",
						beadID, shortSession, ageMin)
					os.Exit(1)
				}
			}
		}
	}

	// Set claim
	_, _ = runBD("set-state", beadID, "claimed_by="+sessionID)
	_, _ = runBD("set-state", beadID, "claimed_at="+strconv.FormatInt(time.Now().Unix(), 10))
	return nil
}

// cmdBeadRelease clears a bead claim.
// Args: bead_id
func cmdBeadRelease(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: bead-release <bead_id>")
	}
	beadID := args[0]

	if !bdAvailable() {
		return nil
	}

	_, _ = runBD("set-state", beadID, "claimed_by=")
	_, _ = runBD("set-state", beadID, "claimed_at=")
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
