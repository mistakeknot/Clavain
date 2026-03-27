package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// daemonConfig holds daemon runtime configuration.
type daemonConfig struct {
	PollInterval  time.Duration
	MaxConcurrent int
	MaxComplexity int
	MinPriority   int // Lower number = higher priority (P0 is highest)
	LabelFilter   string
	ProjectDir    string
	DryRun        bool
	Once          bool // Run one cycle then exit
}

// agentInfo tracks a running agent subprocess.
type agentInfo struct {
	BeadID    string
	Title     string
	Cmd       *exec.Cmd
	StartTime time.Time
	LogFile   string
}

// daemonState holds the daemon's runtime state.
type daemonState struct {
	mu       sync.Mutex
	active   map[string]*agentInfo // bead ID → agent
	shutdown bool
}

func (s *daemonState) isShutdown() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.shutdown
}

func (s *daemonState) setShutdown() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.shutdown = true
}

func (s *daemonState) activeCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.active)
}

func (s *daemonState) addAgent(bead string, info *agentInfo) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.active[bead] = info
}

func (s *daemonState) removeAgent(bead string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.active, bead)
}

func (s *daemonState) isActive(bead string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, ok := s.active[bead]
	return ok
}

func (s *daemonState) allAgents() []*agentInfo {
	s.mu.Lock()
	defer s.mu.Unlock()
	agents := make([]*agentInfo, 0, len(s.active))
	for _, a := range s.active {
		agents = append(agents, a)
	}
	return agents
}

// bdReadyEntry represents a bead from `bd ready --json` output.
type bdReadyEntry struct {
	ID       string   `json:"id"`
	Title    string   `json:"title"`
	Priority int      `json:"priority"`
	Labels   []string `json:"labels"`
}

// cmdDaemon is the entry point for the daemon subcommand.
func cmdDaemon(args []string) error {
	cfg, err := parseDaemonFlags(args)
	if err != nil {
		return err
	}

	if !bdAvailable() {
		return fmt.Errorf("daemon: bd binary not found — beads tracker required")
	}

	// Verify project directory
	absDir, err := filepath.Abs(cfg.ProjectDir)
	if err != nil {
		return fmt.Errorf("daemon: cannot resolve project dir: %w", err)
	}
	cfg.ProjectDir = absDir

	if _, err := os.Stat(filepath.Join(cfg.ProjectDir, ".beads")); err != nil {
		if _, err2 := os.Stat(filepath.Join(cfg.ProjectDir, "CLAUDE.md")); err2 != nil {
			return fmt.Errorf("daemon: %s has no .beads/ or CLAUDE.md — not a Sylveste project", cfg.ProjectDir)
		}
	}

	// Change to project dir so bd/ic/git commands find their databases
	if err := os.Chdir(cfg.ProjectDir); err != nil {
		return fmt.Errorf("daemon: cannot chdir to %s: %w", cfg.ProjectDir, err)
	}

	// Create log directory
	logDir := filepath.Join(cfg.ProjectDir, ".clavain", "daemon")
	if err := os.MkdirAll(logDir, 0o755); err != nil {
		return fmt.Errorf("daemon: cannot create log dir: %w", err)
	}

	state := &daemonState{
		active: make(map[string]*agentInfo),
	}

	// Signal handling
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)

	mode := "continuous"
	if cfg.Once {
		mode = "one-shot"
	}
	if cfg.DryRun {
		mode += " (dry-run)"
	}
	log.Printf("daemon: started (%s, poll=%s, max=%d, complexity≤%d, priority≤P%d)",
		mode, cfg.PollInterval, cfg.MaxConcurrent, cfg.MaxComplexity, cfg.MinPriority)

	// Main loop
	for {
		if state.isShutdown() {
			break
		}

		// Check for signal (non-blocking)
		select {
		case sig := <-sigCh:
			log.Printf("daemon: received %s, shutting down", sig)
			state.setShutdown()
			break
		default:
		}

		if state.isShutdown() {
			break
		}

		// Reap completed agents
		reapCompleted(state, cfg)

		// Check available slots
		slots := cfg.MaxConcurrent - state.activeCount()
		if slots > 0 {
			beads, err := pollEligible(state, cfg)
			if err != nil {
				log.Printf("daemon: poll error: %v", err)
			} else if len(beads) > 0 {
				// Dispatch up to available slots
				if len(beads) > slots {
					beads = beads[:slots]
				}
				for _, b := range beads {
					if state.isShutdown() {
						break
					}
					if cfg.DryRun {
						log.Printf("daemon: [dry-run] would dispatch %s — %s (P%d)", b.ID, b.Title, b.Priority)
					} else {
						if err := spawnAgent(state, cfg, b, logDir); err != nil {
							log.Printf("daemon: spawn %s failed: %v", b.ID, err)
						}
					}
				}
			}
		}

		if cfg.Once {
			// One-shot: wait for all agents to complete, then exit
			if !cfg.DryRun {
				waitForAgents(state, 0) // 0 = wait indefinitely
			}
			break
		}

		// Sleep until next poll (interruptible by signal)
		select {
		case sig := <-sigCh:
			log.Printf("daemon: received %s, shutting down", sig)
			state.setShutdown()
		case <-time.After(cfg.PollInterval):
		}
	}

	// Graceful shutdown
	shutdownAgents(state)

	completed := 0
	for _, a := range state.allAgents() {
		if a.Cmd.ProcessState != nil {
			completed++
		}
	}
	log.Printf("daemon: stopped (agents completed: %d)", completed)
	return nil
}

// parseDaemonFlags parses daemon CLI flags.
func parseDaemonFlags(args []string) (daemonConfig, error) {
	fs := flag.NewFlagSet("daemon", flag.ContinueOnError)
	poll := fs.Duration("poll", 30*time.Second, "poll interval")
	maxConc := fs.Int("max-concurrent", 3, "max concurrent agents")
	maxComp := fs.Int("max-complexity", 3, "max bead complexity to dispatch")
	minPri := fs.Int("min-priority", 3, "minimum priority to dispatch (0=P0 only, 3=P0-P3)")
	label := fs.String("label", "", "only dispatch beads with this label")
	projDir := fs.String("project-dir", ".", "project root directory")
	dryRun := fs.Bool("dry-run", false, "log what would be dispatched without spawning")
	once := fs.Bool("once", false, "run one poll cycle then exit")

	if err := fs.Parse(args); err != nil {
		return daemonConfig{}, err
	}

	return daemonConfig{
		PollInterval:  *poll,
		MaxConcurrent: *maxConc,
		MaxComplexity: *maxComp,
		MinPriority:   *minPri,
		LabelFilter:   *label,
		ProjectDir:    *projDir,
		DryRun:        *dryRun,
		Once:          *once,
	}, nil
}

// pollEligible fetches eligible beads from `bd ready`.
func pollEligible(state *daemonState, cfg daemonConfig) ([]bdReadyEntry, error) {
	out, err := runBD("ready", "--json")
	if err != nil {
		return nil, err
	}

	var beads []bdReadyEntry
	if err := json.Unmarshal(out, &beads); err != nil {
		// bd ready might return non-JSON (e.g., "No ready issues")
		return nil, nil
	}

	var eligible []bdReadyEntry
	for _, b := range beads {
		// Skip already-active
		if state.isActive(b.ID) {
			continue
		}

		// Priority filter (lower number = higher priority)
		if b.Priority > cfg.MinPriority {
			continue
		}

		// Label filter
		if cfg.LabelFilter != "" && !hasLabel(b.Labels, cfg.LabelFilter) {
			continue
		}

		// Complexity filter: check bead state
		if cfg.MaxComplexity < 5 {
			comp := getBeadComplexity(b.ID)
			if comp > cfg.MaxComplexity {
				continue
			}
		}

		// Claim freshness: skip if another agent claimed recently
		if isRecentlyClaimed(b.ID) {
			continue
		}

		eligible = append(eligible, b)
	}

	return eligible, nil
}

// hasLabel checks if a label exists in the list (case-insensitive substring match).
func hasLabel(labels []string, filter string) bool {
	f := strings.ToLower(filter)
	for _, l := range labels {
		if strings.Contains(strings.ToLower(l), f) {
			return true
		}
	}
	return false
}

// getBeadComplexity reads the cached complexity from bead state. Returns 3 (moderate) if unknown.
func getBeadComplexity(beadID string) int {
	out, err := runBD("state", beadID, "complexity")
	if err != nil {
		return 3
	}
	s := strings.TrimSpace(string(out))
	// bd state returns "(no complexity state set)" when unset
	if strings.HasPrefix(s, "(") {
		return 3
	}
	c, err := strconv.Atoi(s)
	if err != nil {
		return 3
	}
	return c
}

// isRecentlyClaimed returns true if another session claimed this bead within the stale threshold.
func isRecentlyClaimed(beadID string) bool {
	out, err := runBD("state", beadID, "claimed_at")
	if err != nil {
		return false
	}
	s := strings.TrimSpace(string(out))
	if strings.HasPrefix(s, "(") || s == "0" || s == "" {
		return false // unclaimed
	}
	ts, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return false
	}
	age := time.Now().Unix() - ts
	return age < beadClaimStaleSeconds
}

// sanitizeTitle removes characters that could cause shell injection when passed as prompt.
func sanitizeTitle(s string) string {
	r := strings.NewReplacer("`", "", "$", "", "\\", "", "\n", " ", "\r", "")
	cleaned := r.Replace(s)
	if len(cleaned) > 200 {
		cleaned = cleaned[:200]
	}
	return strings.TrimSpace(cleaned)
}

// spawnAgent claims a bead and starts a Claude Code subprocess.
func spawnAgent(state *daemonState, cfg daemonConfig, bead bdReadyEntry, logDir string) error {
	// Claim the bead
	_, err := runBD("update", bead.ID, "--claim")
	if err != nil {
		return fmt.Errorf("claim failed (likely already claimed): %w", err)
	}

	// Write claim identity
	daemonID := fmt.Sprintf("daemon-%d", os.Getpid())
	_, _ = runBD("set-state", bead.ID, fmt.Sprintf("claimed_by=%s", daemonID))
	_, _ = runBD("set-state", bead.ID, fmt.Sprintf("claimed_at=%d", time.Now().Unix()))

	// Build Claude command
	claudePath, err := exec.LookPath("claude")
	if err != nil {
		releaseClaim(bead.ID)
		return fmt.Errorf("claude binary not found: %w", err)
	}

	prompt := fmt.Sprintf("/clavain:route %s", bead.ID)
	cmd := exec.Command(claudePath, "--dangerously-skip-permissions", "--verbose", "-p", prompt)
	cmd.Dir = cfg.ProjectDir

	// Clear env vars that prevent nested Claude Code sessions.
	// The daemon spawns independent sessions, not nested ones.
	env := os.Environ()
	cleanEnv := make([]string, 0, len(env))
	for _, e := range env {
		if !strings.HasPrefix(e, "CLAUDECODE=") &&
			!strings.HasPrefix(e, "CLAUDE_CODE_ENTRYPOINT=") {
			cleanEnv = append(cleanEnv, e)
		}
	}
	cmd.Env = cleanEnv

	// Set up log file
	logFile := filepath.Join(logDir, fmt.Sprintf("%s.log", bead.ID))
	f, err := os.OpenFile(logFile, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		releaseClaim(bead.ID)
		return fmt.Errorf("cannot create log file: %w", err)
	}

	fmt.Fprintf(f, "\n=== Daemon dispatch: %s at %s ===\n", bead.ID, time.Now().Format(time.RFC3339))
	cmd.Stdout = f
	cmd.Stderr = f

	if err := cmd.Start(); err != nil {
		f.Close()
		releaseClaim(bead.ID)
		return fmt.Errorf("start failed: %w", err)
	}

	info := &agentInfo{
		BeadID:    bead.ID,
		Title:     bead.Title,
		Cmd:       cmd,
		StartTime: time.Now(),
		LogFile:   logFile,
	}
	state.addAgent(bead.ID, info)

	log.Printf("daemon: dispatched %s — %s (PID %d, log: %s)",
		bead.ID, sanitizeTitle(bead.Title), cmd.Process.Pid, logFile)

	// Start goroutine to wait for completion and close log file
	go func() {
		_ = cmd.Wait()
		f.Close()
	}()

	return nil
}

// releaseClaim releases a bead claim by setting sentinel values.
func releaseClaim(beadID string) {
	_, _ = runBD("set-state", beadID, "claimed_by=released")
	_, _ = runBD("set-state", beadID, "claimed_at=0")
}

// reapCompleted checks for finished agents and removes them from active state.
func reapCompleted(state *daemonState, cfg daemonConfig) {
	for _, agent := range state.allAgents() {
		if agent.Cmd.ProcessState != nil {
			// Process has exited
			exitCode := agent.Cmd.ProcessState.ExitCode()
			duration := time.Since(agent.StartTime).Round(time.Second)
			if exitCode == 0 {
				log.Printf("daemon: completed %s — %s (exit=0, duration=%s)",
					agent.BeadID, sanitizeTitle(agent.Title), duration)
			} else {
				log.Printf("daemon: failed %s — %s (exit=%d, duration=%s)",
					agent.BeadID, sanitizeTitle(agent.Title), exitCode, duration)
			}
			releaseClaim(agent.BeadID)
			state.removeAgent(agent.BeadID)
		}
	}
}

// waitForAgents blocks until all agents complete or timeout expires.
// timeout=0 means wait indefinitely.
func waitForAgents(state *daemonState, timeout time.Duration) {
	deadline := time.Time{}
	if timeout > 0 {
		deadline = time.Now().Add(timeout)
	}

	for state.activeCount() > 0 {
		if !deadline.IsZero() && time.Now().After(deadline) {
			return
		}
		time.Sleep(time.Second)
		reapCompleted(state, daemonConfig{})
	}
}

// shutdownAgents gracefully stops all running agents.
func shutdownAgents(state *daemonState) {
	agents := state.allAgents()
	if len(agents) == 0 {
		return
	}

	log.Printf("daemon: shutting down %d agent(s)...", len(agents))

	// Send SIGTERM
	for _, a := range agents {
		if a.Cmd.Process != nil && a.Cmd.ProcessState == nil {
			_ = a.Cmd.Process.Signal(syscall.SIGTERM)
		}
	}

	// Wait up to 60s for graceful exit
	waitForAgents(state, 60*time.Second)

	// Kill remaining
	for _, a := range state.allAgents() {
		if a.Cmd.Process != nil && a.Cmd.ProcessState == nil {
			log.Printf("daemon: killing %s (PID %d) — did not exit gracefully",
				a.BeadID, a.Cmd.Process.Pid)
			_ = a.Cmd.Process.Kill()
		}
		releaseClaim(a.BeadID)
	}
}
