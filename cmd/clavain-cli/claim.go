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
	// beadClaimStaleSeconds is the staleness threshold for bead claims (10 minutes).
	// Shortened from 45min to 10min per flux-drive research (Airflow 10:1 ratio with 60s heartbeat).
	// Watchdog sweep uses this as the TTL; old 2700s value was too slow for automated recovery.
	beadClaimStaleSeconds = 600
	// sprintClaimStaleMinutes is the staleness threshold for sprint session claims (60 minutes).
	sprintClaimStaleMinutes = 60
)

// isClaimStale returns true if the age in seconds exceeds the 10-minute threshold.
// Matches beadClaimStaleSeconds (600s). Exactly 600 is NOT stale (> check, not >=).
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
		// An unknown (epoch/zero) created_at must not read as ~56 years old.
		ageSec := ageSecondsOrUnknown(existing.CreatedAt, time.Now().Unix())
		ageMinutes := int(ageSec / 60)

		if ageSec < 0 || ageMinutes < sprintClaimStaleMinutes {
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

	// Also set bd claim for cross-session visibility (ignore errors).
	// cmdBeadClaim acquires its own "bead-claim" lock — different namespace
	// from this function's "sprint-claim" lock, so no deadlock risk.
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

// cmdBeadClaim acquires an advisory bead claim via bd labels.
// Args: bead_id [session_id]
// Advisory locking — serializes concurrent Go callers via ic lock (or mkdir fallback)
// but does not cover direct `bd` CLI invocations from shell scripts. The claim system
// is best-effort; downstream consumers must tolerate stale or contested claims.
// Exit 1 if a live lease exists from another session. Each successful claim
// bumps the claim_gen fence token; --print-fence prints it on stdout.
func cmdBeadClaim(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: bead-claim <bead_id> [session_id]")
	}
	beadID := args[0]
	sessionID := os.Getenv("CLAUDE_SESSION_ID")
	if sessionID == "" {
		sessionID = "unknown"
	}
	if len(args) > 1 && args[1] != "" && !strings.HasPrefix(args[1], "--") {
		sessionID = args[1]
	}
	_, _, printFence, err := parseFenceFlags(args[1:])
	if err != nil {
		return fmt.Errorf("bead-claim: %w", err)
	}

	if !bdAvailable() {
		return nil
	}

	unlock, err := lockBeadClaim(beadID)
	if err != nil {
		return err
	}
	defer unlock()

	now := time.Now().Unix()
	cur, rawClaim, rawAt, rawGen, err := readBeadLease(beadID, now)
	if err != nil {
		return fmt.Errorf("bead-claim: %w", err)
	}
	next, err := leaseAcquire(cur, sessionID, now, maxLeaseTTLSeconds)
	if err != nil {
		shortSession := cur.Holder
		if len(shortSession) > 8 {
			shortSession = shortSession[:8]
		}
		ageMin := (now - (cur.ExpiresAt - maxLeaseTTLSeconds)) / 60
		return fmt.Errorf("bead %s claimed by session %s (%dm ago)", beadID, shortSession, ageMin)
	}
	if err := writeBeadLease(beadID, rawClaim, rawAt, rawGen, sessionID, now, next.Gen); err != nil {
		return fmt.Errorf("bead-claim: bd update failed for %s: %w", beadID, err)
	}
	if printFence {
		fmt.Println(next.Gen)
	}
	return nil
}

// leaseReadHook, when non-nil, runs after a lease read and before the matching
// write, inside the claim lock. Tests use it to force interleavings.
var leaseReadHook func()

// lockBeadClaim takes the per-bead claim lock (ic lock, falling back to a mkdir
// lock) and returns its unlock func. Every read/check/write transaction on a
// bead lease (acquire, heartbeat, release) must run under it.
func lockBeadClaim(beadID string) (func(), error) {
	_, lockErr := runIC("lock", "acquire", "bead-claim", beadID, "--timeout=500ms")
	if lockErr != nil {
		if err := fallbackLock("bead-claim", beadID); err != nil {
			return nil, fmt.Errorf("bead-claim: lock contention for %s", beadID)
		}
		return func() { fallbackUnlock("bead-claim", beadID) }, nil
	}
	return func() { _, _ = runIC("lock", "release", "bead-claim", beadID) }, nil
}

// readBeadLease loads the current lease from bd labels (additive: claim_gen is
// optional) and returns the raw label values so writers can strip them. A
// failed read is an error (fail closed): it must never read as generation 0,
// which would let acquisition reuse a fence token.
func readBeadLease(beadID string, now int64) (Lease, string, string, string, error) {
	get := func(key string) (string, error) {
		out, err := runBD("state", beadID, key)
		if err != nil {
			return "", fmt.Errorf("read %s of %s: %w", key, beadID, err)
		}
		v := strings.TrimSpace(string(out))
		if strings.HasPrefix(v, "(no ") {
			return "", nil
		}
		return v, nil
	}
	by, err := get("claimed_by")
	if err != nil {
		return Lease{}, "", "", "", err
	}
	at, err := get("claimed_at")
	if err != nil {
		return Lease{}, "", "", "", err
	}
	gen, err := get(leaseGenLabel)
	if err != nil {
		return Lease{}, "", "", "", err
	}
	if leaseReadHook != nil {
		leaseReadHook()
	}
	return leaseFromLegacy(by, at, gen, now), by, at, gen, nil
}

// writeBeadLease atomically swaps the claim labels in one bd update.
func writeBeadLease(beadID, oldBy, oldAt, oldGen, newBy string, now, gen int64) error {
	args := []string{"update", beadID}
	if oldBy != "" {
		args = append(args, "--remove-label", "claimed_by:"+oldBy)
	}
	if oldAt != "" {
		args = append(args, "--remove-label", "claimed_at:"+oldAt)
	}
	if oldGen != "" {
		args = append(args, "--remove-label", leaseGenLabel+":"+oldGen)
	}
	args = append(args,
		"--add-label", "claimed_by:"+newBy,
		"--add-label", "claimed_at:"+strconv.FormatInt(now, 10),
		"--add-label", leaseGenLabel+":"+strconv.FormatInt(gen, 10),
	)
	_, err := runBD(args...)
	return err
}

// parseFenceFlags extracts --fence=N and --print-fence from args.
// A malformed --fence is an error so callers can reject it before mutating
// anything, rather than silently falling back to unfenced behaviour.
func parseFenceFlags(args []string) (fence int64, hasFence, printFence bool, err error) {
	for _, a := range args {
		switch {
		case a == "--fence" || strings.HasPrefix(a, "--fence="):
			n, perr := strconv.ParseInt(strings.TrimPrefix(a, "--fence="), 10, 64)
			if a == "--fence" || perr != nil {
				return 0, false, false, fmt.Errorf("invalid --fence value %q (want an integer)", a)
			}
			fence, hasFence = n, true
		case a == "--print-fence":
			printFence = true
		}
	}
	return
}

// cmdBeadRelease clears a bead claim.
// Args: bead_id [--failure-class=retriable|spec_blocked|env_blocked]
// Only releases if we own the claim (or claim is empty/stale).
// Uses atomic bd update to set sentinel labels in a single call.
// If --failure-class is provided, writes failure classification to bead state.
func cmdBeadRelease(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: bead-release <bead_id> [--failure-class=<class>]")
	}
	beadID := args[0]

	// Validate flags before any mutation.
	fence, hasFence, _, err := parseFenceFlags(args[1:])
	if err != nil {
		return fmt.Errorf("bead-release: %w", err)
	}

	// Parse optional --failure-class flag
	failureClass := ""
	for _, arg := range args[1:] {
		if strings.HasPrefix(arg, "--failure-class=") {
			failureClass = strings.TrimPrefix(arg, "--failure-class=")
		}
	}
	if failureClass != "" {
		_, _ = runBDQuiet("set-state", beadID, "failure_class="+failureClass)
	}

	if !bdAvailable() {
		return nil
	}

	// Ownership check: only release if we own the claim. With --fence=N the
	// fence must also be current; a mismatch is a hard error (stale holder).
	ourSession := os.Getenv("CLAUDE_SESSION_ID")
	if ourSession == "" {
		ourSession = "unknown"
	}
	unlock, err := lockBeadClaim(beadID)
	if err != nil {
		return err
	}
	defer unlock()
	now := time.Now().Unix()
	cur, rawBy, rawAt, _, err := readBeadLease(beadID, now)
	if err != nil {
		return fmt.Errorf("bead-release: %w", err)
	}
	if cur.Holder != "" && cur.Holder != ourSession {
		if hasFence {
			return fmt.Errorf("bead-release: %s: %w", beadID, ErrLeaseNotHolder)
		}
		return nil // Another session holds this — don't release
	}
	if hasFence && cur.Holder != "" {
		if _, err := leaseRelease(cur, ourSession, fence); err != nil {
			return fmt.Errorf("bead-release: %s: %w", beadID, err)
		}
	}

	// Build atomic update: remove old labels, add sentinel labels. The
	// generation is preserved so the next acquire gets gen+1.
	updateArgs := []string{"update", beadID}
	if rawBy != "" {
		updateArgs = append(updateArgs, "--remove-label", "claimed_by:"+rawBy)
	}
	if rawAt != "" {
		updateArgs = append(updateArgs, "--remove-label", "claimed_at:"+rawAt)
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

	fence, hasFence, _, err := parseFenceFlags(args[1:])
	if err != nil {
		return fmt.Errorf("bead-heartbeat: %w", err)
	}

	if !bdAvailable() {
		return nil
	}

	// Only heartbeat if we own the claim
	ourSession := os.Getenv("CLAUDE_SESSION_ID")
	if ourSession == "" {
		ourSession = "unknown"
	}
	unlock, err := lockBeadClaim(beadID)
	if err != nil {
		if hasFence {
			return err
		}
		return nil // legacy heartbeat is best-effort
	}
	defer unlock()
	now := time.Now().Unix()
	cur, rawBy, rawAt, rawGen, err := readBeadLease(beadID, now)
	if err != nil {
		if hasFence {
			return fmt.Errorf("bead-heartbeat: %w", err)
		}
		return nil
	}

	if hasFence {
		// Strict mode: renew requires the current holder, fence and an
		// unexpired lease; anything else fails loudly.
		next, err := leaseRenew(cur, ourSession, fence, now, maxLeaseTTLSeconds)
		if err != nil {
			return fmt.Errorf("bead-heartbeat: %s: %w", beadID, err)
		}
		return writeBeadLease(beadID, rawBy, rawAt, rawGen, ourSession, now, next.Gen)
	}

	// Legacy (unfenced) mode: refresh if we own it, it's unclaimed, or it's the
	// "unknown" sentinel. An expired claim we still hold is re-acquired (new
	// generation) rather than renewed.
	if cur.Holder != "" && cur.Holder != "unknown" && cur.Holder != ourSession {
		return nil // Another session holds this — don't touch
	}
	if cur.Holder == "unknown" && ourSession != "unknown" {
		cur.ExpiresAt = 0 // sentinel holder never blocks
	}
	gen := cur.Gen
	if cur.Holder == ourSession && cur.Live(now) {
		// plain renew, same generation
	} else {
		next, err := leaseAcquire(cur, ourSession, now, maxLeaseTTLSeconds)
		if err != nil {
			return nil
		}
		gen = next.Gen
	}
	_ = writeBeadLease(beadID, rawBy, rawAt, rawGen, ourSession, now, gen)
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
