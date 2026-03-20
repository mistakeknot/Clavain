package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"
)

// factoryStatus is the full dashboard output.
type factoryStatus struct {
	Timestamp     string          `json:"timestamp"`
	Fleet         fleetStatus     `json:"fleet"`
	Queue         queueStatus     `json:"queue"`
	WIP           []wipEntry      `json:"wip"`
	Dispatches    []dispatchEntry `json:"recent_dispatches"`
	Watchdog      watchdogStatus  `json:"watchdog"`
	FactoryPaused bool            `json:"factory_paused"`
}

type fleetStatus struct {
	TotalAgents  int `json:"total_agents"`
	ActiveAgents int `json:"active_agents"`
	IdleAgents   int `json:"idle_agents"`
}

type queueStatus struct {
	Total   int        `json:"total"`
	ByPri   []priCount `json:"by_priority"`
	Blocked int        `json:"blocked"`
}

type priCount struct {
	Priority int `json:"priority"`
	Count    int `json:"count"`
}

type wipEntry struct {
	Agent  string `json:"agent"`
	BeadID string `json:"bead_id"`
	Title  string `json:"title"`
	Age    string `json:"age"`
	AgeSec int64  `json:"age_seconds"`
}

type dispatchEntry struct {
	Timestamp string `json:"timestamp"`
	BeadID    string `json:"bead_id"`
	Agent     string `json:"agent"`
	Outcome   string `json:"outcome"`
	Score     int    `json:"score"`
}

type watchdogStatus struct {
	LastSweep   string `json:"last_sweep"`
	StaleFound  int    `json:"stale_found_last"`
	ActionsLast int    `json:"actions_last"`
	Quarantined int    `json:"quarantined_total"`
}

// bdListEntry is a bead from bd list --json output.
type bdListEntry struct {
	ID        string   `json:"id"`
	Title     string   `json:"title"`
	Status    string   `json:"status"`
	Priority  int      `json:"priority"`
	Assignee  string   `json:"assignee"`
	Labels    []string `json:"labels"`
	CreatedAt string   `json:"created_at"`
	UpdatedAt string   `json:"updated_at"`
}

// cmdFactoryStatus displays factory fleet health dashboard.
func cmdFactoryStatus(args []string) error {
	jsonOutput := false
	for _, arg := range args {
		if arg == "--json" {
			jsonOutput = true
		}
	}

	status := gatherFactoryStatus()

	if jsonOutput {
		data, err := json.MarshalIndent(status, "", "  ")
		if err != nil {
			return fmt.Errorf("factory-status: marshal: %w", err)
		}
		fmt.Println(string(data))
		return nil
	}

	printFactoryDashboard(status)
	return nil
}

// gatherFactoryStatus collects all dashboard data.
func gatherFactoryStatus() factoryStatus {
	now := time.Now().UTC()
	status := factoryStatus{
		Timestamp:     now.Format(time.RFC3339),
		FactoryPaused: IsFactoryPaused(),
	}

	// Fleet utilization: count tmux sessions
	status.Fleet = gatherFleetStatus()

	// Queue depth: open beads by priority
	status.Queue = gatherQueueStatus()

	// WIP balance: in-progress beads by assignee
	status.WIP = gatherWIPBalance()

	// Recent dispatches from telemetry log
	status.Dispatches = gatherRecentDispatches(10)

	// Watchdog health
	status.Watchdog = gatherWatchdogStatus()

	return status
}

// gatherFleetStatus counts active tmux sessions.
func gatherFleetStatus() fleetStatus {
	fs := fleetStatus{}

	// Count tmux sessions (each agent runs in its own session)
	sessOut, err := runCommandExec("tmux", "list-sessions", "-F", "#{session_name}")
	if err != nil {
		return fs
	}
	sessions := strings.Split(strings.TrimSpace(string(sessOut)), "\n")
	for _, s := range sessions {
		if s == "" {
			continue
		}
		fs.TotalAgents++
	}

	// Count active: sessions with recent activity (pane has a running process)
	paneOut, err := runCommandExec("tmux", "list-panes", "-a", "-F", "#{session_name} #{pane_current_command}")
	if err == nil {
		activeSet := make(map[string]bool)
		for _, line := range strings.Split(string(paneOut), "\n") {
			parts := strings.SplitN(strings.TrimSpace(line), " ", 2)
			if len(parts) == 2 && parts[1] != "bash" && parts[1] != "zsh" && parts[1] != "" {
				activeSet[parts[0]] = true
			}
		}
		fs.ActiveAgents = len(activeSet)
	}

	fs.IdleAgents = fs.TotalAgents - fs.ActiveAgents
	if fs.IdleAgents < 0 {
		fs.IdleAgents = 0
	}
	return fs
}

// gatherQueueStatus counts open beads by priority.
func gatherQueueStatus() queueStatus {
	qs := queueStatus{}

	out, err := runBDQuiet("list", "--status=open", "--json")
	if err != nil {
		return qs
	}
	var beads []bdListEntry
	if err := json.Unmarshal(out, &beads); err != nil {
		return qs
	}

	priMap := make(map[int]int)
	for _, b := range beads {
		priMap[b.Priority]++
		qs.Total++
	}

	for p, c := range priMap {
		qs.ByPri = append(qs.ByPri, priCount{Priority: p, Count: c})
	}
	sort.Slice(qs.ByPri, func(i, j int) bool {
		return qs.ByPri[i].Priority < qs.ByPri[j].Priority
	})

	// Count blocked
	blockedOut, err := runBDQuiet("list", "--status=blocked", "--json")
	if err == nil {
		var blocked []bdListEntry
		if err := json.Unmarshal(blockedOut, &blocked); err == nil {
			qs.Blocked = len(blocked)
		}
	}

	return qs
}

// gatherWIPBalance shows in-progress beads grouped by assignee.
func gatherWIPBalance() []wipEntry {
	out, err := runBDQuiet("list", "--status=in_progress", "--json")
	if err != nil {
		return nil
	}
	var beads []bdListEntry
	if err := json.Unmarshal(out, &beads); err != nil {
		return nil
	}

	now := time.Now()
	var entries []wipEntry
	for _, b := range beads {
		agent := b.Assignee
		if agent == "" {
			agent = "unassigned"
		}
		// Truncate agent ID for display
		if len(agent) > 8 {
			agent = agent[:8]
		}

		// Calculate age from claimed_at label
		ageSec := int64(0)
		for _, label := range b.Labels {
			if strings.HasPrefix(label, "claimed_at:") {
				val := strings.TrimPrefix(label, "claimed_at:")
				if epoch, err := parseInt64(val); err == nil && epoch > 0 {
					ageSec = now.Unix() - epoch
				}
			}
		}

		entries = append(entries, wipEntry{
			Agent:  agent,
			BeadID: b.ID,
			Title:  truncateStr(b.Title, 40),
			Age:    formatDuration(ageSec),
			AgeSec: ageSec,
		})
	}

	// Sort by age descending (oldest first)
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].AgeSec > entries[j].AgeSec
	})

	return entries
}

// gatherRecentDispatches reads the last N entries from the dispatch log.
func gatherRecentDispatches(limit int) []dispatchEntry {
	logPath := os.Getenv("HOME") + "/.clavain/dispatch-log.jsonl"
	data, err := os.ReadFile(logPath)
	if err != nil {
		return nil
	}

	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	var entries []dispatchEntry

	// Read from end (most recent)
	start := len(lines) - limit
	if start < 0 {
		start = 0
	}

	for i := len(lines) - 1; i >= start; i-- {
		line := strings.TrimSpace(lines[i])
		if line == "" {
			continue
		}
		var raw struct {
			Ts      string `json:"ts"`
			Session string `json:"session"`
			Bead    string `json:"bead"`
			Score   int    `json:"score"`
			Outcome string `json:"outcome"`
		}
		if err := json.Unmarshal([]byte(line), &raw); err != nil {
			continue
		}
		agent := raw.Session
		if len(agent) > 8 {
			agent = agent[:8]
		}
		entries = append(entries, dispatchEntry{
			Timestamp: raw.Ts,
			BeadID:    raw.Bead,
			Agent:     agent,
			Outcome:   raw.Outcome,
			Score:     raw.Score,
		})
	}

	return entries
}

// gatherWatchdogStatus reads the latest watchdog sweep result.
func gatherWatchdogStatus() watchdogStatus {
	ws := watchdogStatus{}

	logPath := os.Getenv("HOME") + "/.clavain/watchdog-log.jsonl"
	data, err := os.ReadFile(logPath)
	if err != nil {
		return ws
	}

	lines := strings.Split(strings.TrimSpace(string(data)), "\n")
	if len(lines) == 0 {
		return ws
	}

	// Parse last entry
	lastLine := lines[len(lines)-1]
	var lastSweep sweepResult
	if err := json.Unmarshal([]byte(lastLine), &lastSweep); err == nil {
		ws.LastSweep = lastSweep.Timestamp.Format(time.RFC3339)
		ws.StaleFound = lastSweep.StaleFound
		ws.ActionsLast = len(lastSweep.Actions)
	}

	// Count total quarantines from quarantine log
	qLogPath := os.Getenv("HOME") + "/.clavain/quarantine-log.jsonl"
	qData, err := os.ReadFile(qLogPath)
	if err == nil {
		ws.Quarantined = len(strings.Split(strings.TrimSpace(string(qData)), "\n"))
	}

	return ws
}

// ─── Terminal Display ────────────────────────────────────────────

func printFactoryDashboard(s factoryStatus) {
	fmt.Println("╔══════════════════════════════════════════════════════════════╗")
	fmt.Println("║                    FACTORY STATUS                           ║")
	fmt.Printf("║  %s", s.Timestamp)
	pad := 62 - 2 - len(s.Timestamp)
	if pad > 0 {
		fmt.Print(strings.Repeat(" ", pad))
	}
	fmt.Println("║")
	if s.FactoryPaused {
		fmt.Println("║  ⚠  FACTORY PAUSED — all dispatch halted                    ║")
	}
	fmt.Println("╠══════════════════════════════════════════════════════════════╣")

	// Fleet
	fmt.Println("║ Fleet                                                        ║")
	printPadLine(fmt.Sprintf("   Agents: %d total, %d active, %d idle", s.Fleet.TotalAgents, s.Fleet.ActiveAgents, s.Fleet.IdleAgents))

	// Queue
	fmt.Println("║ Queue                                                        ║")
	queueLine := fmt.Sprintf("   Open: %d", s.Queue.Total)
	for _, p := range s.Queue.ByPri {
		queueLine += fmt.Sprintf("  P%d:%d", p.Priority, p.Count)
	}
	if s.Queue.Blocked > 0 {
		queueLine += fmt.Sprintf("  Blocked:%d", s.Queue.Blocked)
	}
	printPadLine(queueLine)

	// WIP
	fmt.Println("║ WIP                                                          ║")
	if len(s.WIP) == 0 {
		printPadLine("   (no beads in progress)")
	}
	for _, w := range s.WIP {
		line := fmt.Sprintf("   %s  %-18s  %s  %s", w.Agent, w.BeadID, w.Age, w.Title)
		if len(line) > 60 {
			line = line[:60]
		}
		printPadLine(line)
	}

	// Recent Dispatches
	if len(s.Dispatches) > 0 {
		fmt.Println("║ Recent Dispatches                                            ║")
		for _, d := range s.Dispatches {
			ts := d.Timestamp
			if len(ts) > 19 {
				ts = ts[:19] // trim to YYYY-MM-DDTHH:MM:SS
			}
			line := fmt.Sprintf("   %s  %s  %s  s=%d", ts, d.Agent, d.BeadID, d.Score)
			if len(line) > 60 {
				line = line[:60]
			}
			printPadLine(line)
		}
	}

	// Watchdog
	if s.Watchdog.LastSweep != "" {
		fmt.Println("║ Watchdog                                                     ║")
		line := fmt.Sprintf("   Last: %s  stale=%d  actions=%d  quarantined=%d",
			shortTimestamp(s.Watchdog.LastSweep), s.Watchdog.StaleFound, s.Watchdog.ActionsLast, s.Watchdog.Quarantined)
		if len(line) > 60 {
			line = line[:60]
		}
		printPadLine(line)
	}

	fmt.Println("╚══════════════════════════════════════════════════════════════╝")
}

func printPadLine(content string) {
	maxWidth := 60
	if len(content) > maxWidth {
		content = content[:maxWidth]
	}
	pad := maxWidth - len(content)
	if pad < 0 {
		pad = 0
	}
	fmt.Printf("║ %s%s ║\n", content, strings.Repeat(" ", pad))
}

// ─── Helpers ─────────────────────────────────────────────────────

func truncateStr(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-1] + "…"
}

func formatDuration(seconds int64) string {
	if seconds <= 0 {
		return "just now"
	}
	if seconds < 60 {
		return fmt.Sprintf("%ds", seconds)
	}
	if seconds < 3600 {
		return fmt.Sprintf("%dm", seconds/60)
	}
	hours := seconds / 3600
	mins := (seconds % 3600) / 60
	if hours < 24 {
		return fmt.Sprintf("%dh%dm", hours, mins)
	}
	days := hours / 24
	return fmt.Sprintf("%dd%dh", days, hours%24)
}

func shortTimestamp(ts string) string {
	if len(ts) > 19 {
		return ts[11:19] // HH:MM:SS
	}
	return ts
}

func parseInt64(s string) (int64, error) {
	var n int64
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0, fmt.Errorf("not a number: %s", s)
		}
		n = n*10 + int64(c-'0')
	}
	return n, nil
}
