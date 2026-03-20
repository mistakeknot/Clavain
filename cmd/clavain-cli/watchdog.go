package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"time"
)

// watchdogConfig holds watchdog runtime configuration.
type watchdogConfig struct {
	StaleTTL      time.Duration // bead claim staleness threshold
	SweepInterval time.Duration // how often to run the sweep
	MaxUnclaims   int           // disruption budget: max unclaims per sweep
	MaxRetries    int           // max auto-retries before quarantine
	CircuitWindow time.Duration // time window for circuit breaker detection
	CircuitThresh int           // quarantines in window to trip circuit
	FactoryWindow time.Duration // time window for factory pause detection
	FactoryThresh int           // circuit breakers in window to pause factory
	Once          bool          // run one sweep then exit
	DryRun        bool          // log actions without executing
}

func defaultWatchdogConfig() watchdogConfig {
	return watchdogConfig{
		StaleTTL:      600 * time.Second,
		SweepInterval: 60 * time.Second,
		MaxUnclaims:   2,
		MaxRetries:    3,
		CircuitWindow: 30 * time.Minute,
		CircuitThresh: 3,
		FactoryWindow: 15 * time.Minute,
		FactoryThresh: 2,
		Once:          false,
		DryRun:        false,
	}
}

// escalationTier indicates the severity of a recovery action.
type escalationTier int

const (
	tierAutoRetry    escalationTier = 1 // unclaim + re-queue
	tierQuarantine   escalationTier = 2 // set status=blocked
	tierCircuitBreak escalationTier = 3 // pause agent dispatch
	tierFactoryPause escalationTier = 4 // pause all dispatch
)

func (t escalationTier) String() string {
	switch t {
	case tierAutoRetry:
		return "auto-retry"
	case tierQuarantine:
		return "quarantine"
	case tierCircuitBreak:
		return "circuit-breaker"
	case tierFactoryPause:
		return "factory-pause"
	default:
		return "unknown"
	}
}

// sweepResult tracks the outcome of a single sweep cycle.
type sweepResult struct {
	Timestamp    time.Time     `json:"timestamp"`
	BeadsChecked int           `json:"beads_checked"`
	StaleFound   int           `json:"stale_found"`
	Actions      []sweepAction `json:"actions"`
	Skipped      int           `json:"skipped"` // skipped due to disruption budget
	Errors       []string      `json:"errors,omitempty"`
}

type sweepAction struct {
	BeadID       string         `json:"bead_id"`
	FailureClass string         `json:"failure_class"`
	Tier         escalationTier `json:"tier"`
	Action       string         `json:"action"`
	Reason       string         `json:"reason"`
}

// beadInProgress represents an in-progress bead from bd list --json.
type beadInProgress struct {
	ID       string   `json:"id"`
	Title    string   `json:"title"`
	Status   string   `json:"status"`
	Priority int      `json:"priority"`
	Labels   []string `json:"labels"`
}

// cmdWatchdog is the entry point for the watchdog subcommand.
func cmdWatchdog(args []string) error {
	cfg := defaultWatchdogConfig()

	// Parse flags
	for _, arg := range args {
		switch {
		case arg == "--once":
			cfg.Once = true
		case arg == "--dry-run":
			cfg.DryRun = true
		case strings.HasPrefix(arg, "--stale-ttl="):
			if d, err := time.ParseDuration(strings.TrimPrefix(arg, "--stale-ttl=")); err == nil {
				cfg.StaleTTL = d
			}
		case strings.HasPrefix(arg, "--interval="):
			if d, err := time.ParseDuration(strings.TrimPrefix(arg, "--interval=")); err == nil {
				cfg.SweepInterval = d
			}
		case strings.HasPrefix(arg, "--max-unclaims="):
			if n, err := strconv.Atoi(strings.TrimPrefix(arg, "--max-unclaims=")); err == nil {
				cfg.MaxUnclaims = n
			}
		}
	}

	if !bdAvailable() {
		return fmt.Errorf("watchdog: bd binary not found — beads tracker required")
	}

	mode := "continuous"
	if cfg.Once {
		mode = "one-shot"
	}
	if cfg.DryRun {
		mode += " (dry-run)"
	}
	log.Printf("watchdog: started (%s, stale-ttl=%s, interval=%s, max-unclaims=%d)",
		mode, cfg.StaleTTL, cfg.SweepInterval, cfg.MaxUnclaims)

	for {
		result := runSweep(cfg)
		logSweepResult(result)

		if cfg.Once {
			// Output result as JSON for callers
			out, _ := json.Marshal(result)
			fmt.Println(string(out))
			return nil
		}

		time.Sleep(cfg.SweepInterval)
	}
}

// runSweep executes one watchdog sweep cycle.
func runSweep(cfg watchdogConfig) sweepResult {
	result := sweepResult{
		Timestamp: time.Now().UTC(),
	}

	// Get all in-progress beads
	beads, err := listInProgressBeads()
	if err != nil {
		result.Errors = append(result.Errors, fmt.Sprintf("list beads: %v", err))
		return result
	}
	result.BeadsChecked = len(beads)

	if len(beads) == 0 {
		return result
	}

	// Count active agents (for disruption budget: keep min 1 working)
	activeCount := len(beads)
	unclaimCount := 0

	for _, bead := range beads {
		// Check staleness
		stale, ageSeconds := isBeadStale(bead.ID, cfg.StaleTTL)
		if !stale {
			continue
		}
		result.StaleFound++

		// Cross-reference: check if pane is actually alive (false positive prevention)
		if isPaneAlive(bead.ID) {
			// Pane alive with output — refresh heartbeat, not stale
			if !cfg.DryRun {
				_ = cmdBeadHeartbeat([]string{bead.ID})
			}
			log.Printf("watchdog: %s stale (%ds) but pane alive — refreshed heartbeat", bead.ID, ageSeconds)
			continue
		}

		// Disruption budget check
		if unclaimCount >= cfg.MaxUnclaims {
			result.Skipped++
			log.Printf("watchdog: %s stale but disruption budget exhausted (%d/%d)", bead.ID, unclaimCount, cfg.MaxUnclaims)
			continue
		}
		// Keep at least 1 agent working
		if activeCount-unclaimCount <= 1 && activeCount > 1 {
			result.Skipped++
			log.Printf("watchdog: %s stale but would leave 0 active agents — skipping", bead.ID)
			continue
		}

		// Classify failure
		failureClass := classifyFailure(bead.ID)
		attemptCount := getAttemptCount(bead.ID)

		// Determine escalation tier
		tier := determineTier(failureClass, attemptCount, bead.ID, cfg)

		// Execute recovery action
		action := executeRecovery(bead.ID, failureClass, tier, cfg)
		result.Actions = append(result.Actions, sweepAction{
			BeadID:       bead.ID,
			FailureClass: failureClass,
			Tier:         tier,
			Action:       action,
			Reason:       fmt.Sprintf("stale %ds, attempts=%d, class=%s", ageSeconds, attemptCount, failureClass),
		})
		unclaimCount++
	}

	// Check for factory-level escalation
	checkFactoryEscalation(cfg)

	return result
}

// listInProgressBeads returns all beads with status=in_progress.
func listInProgressBeads() ([]beadInProgress, error) {
	out, err := runBDQuiet("list", "--status=in_progress", "--json")
	if err != nil {
		return nil, err
	}
	var beads []beadInProgress
	if err := json.Unmarshal(out, &beads); err != nil {
		return nil, fmt.Errorf("parse bd list: %w", err)
	}
	return beads, nil
}

// isBeadStale checks if a bead's claim has exceeded the TTL.
// Returns (stale, ageSeconds).
func isBeadStale(beadID string, ttl time.Duration) (bool, int64) {
	out, err := runBDQuiet("state", beadID, "claimed_at")
	if err != nil {
		return false, 0
	}
	raw := strings.TrimSpace(string(out))
	if raw == "" || strings.HasPrefix(raw, "(no ") || raw == "0" {
		// No claim timestamp — not stale (probably unclaimed)
		return false, 0
	}

	epoch, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		return false, 0
	}

	age := time.Now().Unix() - epoch
	return age > int64(ttl.Seconds()), age
}

// isPaneAlive checks if the agent working on this bead still has a live tmux pane.
func isPaneAlive(beadID string) bool {
	// Check claimer session
	out, err := runBDQuiet("state", beadID, "claimed_by")
	if err != nil {
		return false
	}
	claimer := strings.TrimSpace(string(out))
	if claimer == "" || strings.HasPrefix(claimer, "(no ") || claimer == "released" {
		return false
	}

	// Check tmux for pane matching bead ID or claimer session
	paneOut, err := runCommandExec("tmux", "list-panes", "-a", "-F", "#{pane_title}")
	if err != nil {
		return false
	}
	panes := string(paneOut)
	return strings.Contains(panes, beadID) || strings.Contains(panes, claimer)
}

// classifyFailure determines the failure class for a stale bead.
// Mirrors lib-recovery.sh logic in Go for the watchdog sweep.
func classifyFailure(beadID string) string {
	// Check last error from bead state
	errorOut, _ := runBDQuiet("state", beadID, "last_error")
	errorStr := strings.TrimSpace(string(errorOut))

	// Environment patterns
	envPatterns := []string{
		"ENOSPC", "disk full", "no space",
		"auth", "permission denied",
		"Dolt", "ECONNREFUSED", "connection refused",
		"OOM", "out of memory", "cannot allocate",
	}
	errorLower := strings.ToLower(errorStr)
	for _, pat := range envPatterns {
		if strings.Contains(errorLower, strings.ToLower(pat)) {
			return "env_blocked"
		}
	}

	// Spec patterns
	specPatterns := []string{
		"ambiguous", "unclear", "conflicting",
		"missing context", "underspecified", "cannot determine",
	}
	for _, pat := range specPatterns {
		if strings.Contains(errorLower, strings.ToLower(pat)) {
			return "spec_blocked"
		}
	}

	// Check attempt count + no commits → spec_blocked
	attempts := getAttemptCount(beadID)
	if attempts >= 2 {
		commitOut, err := runGit("log", "--since=30 minutes ago", "--oneline", "--grep="+beadID)
		if err != nil || len(strings.TrimSpace(string(commitOut))) == 0 {
			return "spec_blocked"
		}
	}

	return "retriable"
}

// getAttemptCount reads the attempt_count state for a bead.
func getAttemptCount(beadID string) int {
	out, err := runBDQuiet("state", beadID, "attempt_count")
	if err != nil {
		return 0
	}
	raw := strings.TrimSpace(string(out))
	if raw == "" || strings.HasPrefix(raw, "(no ") {
		return 0
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return 0
	}
	return n
}

// incrementAttemptCount bumps the attempt counter for a bead.
func incrementAttemptCount(beadID string) {
	current := getAttemptCount(beadID)
	next := strconv.Itoa(current + 1)
	_, _ = runBDQuiet("set-state", beadID, "attempt_count="+next)
}

// determineTier selects the escalation tier based on failure class and history.
func determineTier(failureClass string, attemptCount int, beadID string, cfg watchdogConfig) escalationTier {
	switch {
	// Tier 2: quarantine — too many retries or spec-blocked
	case attemptCount >= cfg.MaxRetries:
		return tierQuarantine
	case failureClass == "spec_blocked":
		return tierQuarantine
	case failureClass == "env_blocked":
		return tierQuarantine

	// Tier 1: auto-retry — retriable with room to retry
	case failureClass == "retriable" && attemptCount < cfg.MaxRetries:
		return tierAutoRetry

	default:
		return tierAutoRetry
	}
}

// executeRecovery performs the recovery action for a bead.
// Returns a description of the action taken.
func executeRecovery(beadID string, failureClass string, tier escalationTier, cfg watchdogConfig) string {
	if cfg.DryRun {
		return fmt.Sprintf("dry-run: would %s %s", tier.String(), beadID)
	}

	// Write failure metadata
	_, _ = runBDQuiet("set-state", beadID, "failure_class="+failureClass)
	_, _ = runBDQuiet("set-state", beadID, fmt.Sprintf("last_recovery=%d", time.Now().Unix()))
	incrementAttemptCount(beadID)

	switch tier {
	case tierAutoRetry:
		// Release claim — bead returns to dispatch queue
		_ = cmdBeadRelease([]string{beadID})
		// Reset status back to open for re-dispatch
		_, _ = runBDQuiet("update", beadID, "--status=open")
		logRecoveryEvent(beadID, failureClass, "auto-retry")
		return "released for auto-retry"

	case tierQuarantine:
		// Release claim and block the bead
		_ = cmdBeadRelease([]string{beadID})
		_, _ = runBDQuiet("update", beadID, "--status=blocked")
		label := "quarantine:needs-human"
		if failureClass == "env_blocked" {
			label = "quarantine:needs-infra"
		}
		_, _ = runBDQuiet("update", beadID, "--add-label", label)
		// Record quarantine for circuit breaker tracking
		recordQuarantine(beadID)
		logRecoveryEvent(beadID, failureClass, "quarantined")
		return "quarantined (blocked)"

	case tierCircuitBreak:
		// Release and block the bead
		_ = cmdBeadRelease([]string{beadID})
		_, _ = runBDQuiet("update", beadID, "--status=blocked")
		// Pause dispatch for the owning agent
		agent := getBeadAgent(beadID)
		if agent != "" {
			pauseAgentDispatch(agent)
		}
		logRecoveryEvent(beadID, failureClass, "circuit-breaker")
		return fmt.Sprintf("circuit-breaker (agent %s paused)", agent)

	case tierFactoryPause:
		// Release and block
		_ = cmdBeadRelease([]string{beadID})
		_, _ = runBDQuiet("update", beadID, "--status=blocked")
		// Pause all factory dispatch
		pauseFactory()
		logRecoveryEvent(beadID, failureClass, "factory-pause")
		return "factory paused"
	}

	return "no-op"
}

// ─── Circuit Breaker & Factory Pause ─────────────────────────────

// quarantineRecord tracks when a bead was quarantined and by which agent.
type quarantineRecord struct {
	BeadID    string `json:"bead_id"`
	Agent     string `json:"agent"`
	Timestamp int64  `json:"timestamp"`
}

// recordQuarantine writes a quarantine event for circuit breaker tracking.
func recordQuarantine(beadID string) {
	agent := getBeadAgent(beadID)
	rec := quarantineRecord{
		BeadID:    beadID,
		Agent:     agent,
		Timestamp: time.Now().Unix(),
	}
	data, _ := json.Marshal(rec)

	logPath := os.Getenv("HOME") + "/.clavain/quarantine-log.jsonl"
	_ = os.MkdirAll(os.Getenv("HOME")+"/.clavain", 0o755)
	f, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.Write(append(data, '\n'))
}

// checkCircuitBreaker returns true if the agent should be paused.
// Checks: 3+ quarantines from same agent within 30 minutes.
func checkCircuitBreaker(agent string, cfg watchdogConfig) bool {
	if agent == "" {
		return false
	}

	logPath := os.Getenv("HOME") + "/.clavain/quarantine-log.jsonl"
	data, err := os.ReadFile(logPath)
	if err != nil {
		return false
	}

	cutoff := time.Now().Unix() - int64(cfg.CircuitWindow.Seconds())
	count := 0
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var rec quarantineRecord
		if err := json.Unmarshal([]byte(line), &rec); err != nil {
			continue
		}
		if rec.Agent == agent && rec.Timestamp > cutoff {
			count++
		}
	}
	return count >= cfg.CircuitThresh
}

// checkFactoryEscalation checks if factory-level pause is needed.
// Trigger: circuit breakers on 2+ agents within 15 minutes.
func checkFactoryEscalation(cfg watchdogConfig) {
	if cfg.DryRun {
		return
	}

	logPath := os.Getenv("HOME") + "/.clavain/quarantine-log.jsonl"
	data, err := os.ReadFile(logPath)
	if err != nil {
		return
	}

	cutoff := time.Now().Unix() - int64(cfg.FactoryWindow.Seconds())
	agentQuarantines := make(map[string]int)
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var rec quarantineRecord
		if err := json.Unmarshal([]byte(line), &rec); err != nil {
			continue
		}
		if rec.Timestamp > cutoff && rec.Agent != "" {
			agentQuarantines[rec.Agent]++
		}
	}

	// Count agents with enough quarantines to trigger circuit breaker
	circuitBreakerAgents := 0
	for _, count := range agentQuarantines {
		if count >= cfg.CircuitThresh {
			circuitBreakerAgents++
		}
	}

	if circuitBreakerAgents >= cfg.FactoryThresh {
		log.Printf("watchdog: FACTORY PAUSE — %d agents hit circuit breaker within %s", circuitBreakerAgents, cfg.FactoryWindow)
		pauseFactory()
	}
}

// getBeadAgent returns the agent/session that last worked on this bead.
func getBeadAgent(beadID string) string {
	out, err := runBDQuiet("state", beadID, "claimed_by")
	if err != nil {
		return ""
	}
	agent := strings.TrimSpace(string(out))
	if agent == "" || strings.HasPrefix(agent, "(no ") || agent == "released" {
		return ""
	}
	return agent
}

// pauseAgentDispatch pauses self-dispatch for a specific agent.
// Writes a marker file that lib-dispatch.sh checks before dispatching.
func pauseAgentDispatch(agent string) {
	pauseDir := os.Getenv("HOME") + "/.clavain/paused-agents"
	_ = os.MkdirAll(pauseDir, 0o755)
	data := fmt.Sprintf(`{"agent":"%s","paused_at":%d,"reason":"circuit-breaker"}`, agent, time.Now().Unix())
	_ = os.WriteFile(pauseDir+"/"+sanitizeFilename(agent)+".json", []byte(data+"\n"), 0o644)
	log.Printf("watchdog: paused dispatch for agent %s", agent)
}

// pauseFactory pauses all factory dispatch by writing a global marker.
func pauseFactory() {
	pauseFile := os.Getenv("HOME") + "/.clavain/factory-paused.json"
	_ = os.MkdirAll(os.Getenv("HOME")+"/.clavain", 0o755)
	data := fmt.Sprintf(`{"paused_at":%d,"reason":"factory-pause","tier":4}`, time.Now().Unix())
	_ = os.WriteFile(pauseFile, []byte(data+"\n"), 0o644)
	log.Printf("watchdog: FACTORY PAUSED — all dispatch halted")
}

// IsFactoryPaused checks if factory dispatch is globally paused.
// Exported for use by lib-dispatch.sh integration.
func IsFactoryPaused() bool {
	pauseFile := os.Getenv("HOME") + "/.clavain/factory-paused.json"
	_, err := os.Stat(pauseFile)
	return err == nil
}

// IsAgentPaused checks if a specific agent's dispatch is paused.
func IsAgentPaused(agent string) bool {
	pauseFile := os.Getenv("HOME") + "/.clavain/paused-agents/" + sanitizeFilename(agent) + ".json"
	_, err := os.Stat(pauseFile)
	return err == nil
}

// sanitizeFilename makes an agent ID safe for use as a filename.
func sanitizeFilename(s string) string {
	r := strings.NewReplacer("/", "_", "\\", "_", " ", "_", ":", "_")
	return r.Replace(s)
}

// ─── Logging ─────────────────────────────────────────────────────

func logSweepResult(result sweepResult) {
	logPath := os.Getenv("HOME") + "/.clavain/watchdog-log.jsonl"
	_ = os.MkdirAll(os.Getenv("HOME")+"/.clavain", 0o755)
	data, err := json.Marshal(result)
	if err != nil {
		return
	}
	f, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.Write(append(data, '\n'))

	// Also log summary to stderr
	if len(result.Actions) > 0 {
		log.Printf("watchdog: sweep checked=%d stale=%d actions=%d skipped=%d",
			result.BeadsChecked, result.StaleFound, len(result.Actions), result.Skipped)
		for _, a := range result.Actions {
			log.Printf("watchdog:   %s → %s (%s, tier %d)", a.BeadID, a.Action, a.FailureClass, a.Tier)
		}
	}
}

// ─── CLI Check Commands ──────────────────────────────────────────

// cmdFactoryPaused exits 0 if factory is paused, 1 if not.
func cmdFactoryPaused(_ []string) error {
	if IsFactoryPaused() {
		fmt.Println("paused")
		return nil
	}
	fmt.Println("running")
	return nil
}

// cmdAgentPaused exits 0 if the given agent is paused, 1 if not.
// Args: agent_id
func cmdAgentPaused(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: agent-paused <agent_id>")
	}
	if IsAgentPaused(args[0]) {
		fmt.Println("paused")
		return nil
	}
	fmt.Println("running")
	return nil
}

func logRecoveryEvent(beadID, failureClass, action string) {
	logPath := os.Getenv("HOME") + "/.clavain/recovery-log.jsonl"
	_ = os.MkdirAll(os.Getenv("HOME")+"/.clavain", 0o755)
	data := fmt.Sprintf(`{"ts":"%s","ts_epoch":%d,"bead":"%s","failure_class":"%s","action":"%s"}`,
		time.Now().UTC().Format(time.RFC3339), time.Now().Unix(), beadID, failureClass, action)
	f, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.Write([]byte(data + "\n"))
}
