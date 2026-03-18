package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
)

// Tokyo Night color constants (truecolor hex → ANSI escape).
// Inlined to avoid importing masaq/lipgloss dependency.
const (
	colorPrimary = "\033[38;2;122;162;247m" // #7aa2f7 — borders, labels
	colorFg      = "\033[38;2;192;202;245m" // #c0caf5 — default text
	colorInfo    = "\033[38;2;125;207;255m" // #7dcfff — info values
	colorSuccess = "\033[38;2;158;206;106m" // #9ece6a — healthy budget
	colorWarning = "\033[38;2;224;175;104m" // #e0af68 — budget >70%
	colorError   = "\033[38;2;247;118;142m" // #f7768e — budget >90%
	colorMuted   = "\033[38;2;86;95;137m"   // #565f89 — separators
	colorReset   = "\033[0m"
)

// sprintInitData holds all the info gathered for the banner.
type sprintInitData struct {
	beadID     string
	title      string
	complexity int
	compLabel  string
	phase      string
	nextPhase  string
	budget     int64
	spent      int64
	hasRun     bool
}

// cmdSprintInit consolidates sprint bootstrap into a single CLI call.
// Validates bead, reads complexity/phase/budget, writes interstat attribution,
// and outputs a formatted status banner.
// Args: <bead_id>
func cmdSprintInit(args []string) error {
	if len(args) < 1 || args[0] == "" {
		return fmt.Errorf("usage: sprint-init <bead_id>")
	}
	beadID := args[0]

	// Validate bead exists and get title (use loud version — this is a real error)
	titleOut, err := runBDQuiet("show", beadID)
	if err != nil {
		return fmt.Errorf("bead %s not found", beadID)
	}
	title := parseBDTitle(string(titleOut))

	// Parallel queries for complexity, phase, budget
	var (
		complexity int
		compLabel  string
		phase      string
		budget     int64
		spent      int64
		hasRun     bool
		wg         sync.WaitGroup
	)

	wg.Add(3)

	// Complexity (quiet — ic run may not exist)
	go func() {
		defer wg.Done()
		override := tryComplexityOverrideQuiet(beadID)
		if override != "" {
			if n, err := strconv.Atoi(override); err == nil {
				complexity = n
			} else {
				complexity = 3
			}
		} else {
			complexity = 3
		}
		compLabel = complexityLabel(complexity)
	}()

	// Phase (quiet — state may not be set)
	go func() {
		defer wg.Done()
		out, err := runBDQuiet("state", beadID, "phase")
		if err == nil {
			val := strings.TrimSpace(string(out))
			if val != "" && !strings.HasPrefix(val, "(no ") {
				phase = val
			}
		}
	}()

	// Budget (quiet — ic run may not exist)
	go func() {
		defer wg.Done()
		runID, err := resolveRunIDQuiet(beadID)
		if err != nil {
			return
		}
		hasRun = true
		br, err := readBudgetResultQuiet(runID)
		if err != nil {
			return
		}
		budget = br.TokenBudget
		spent = br.TokensUsed
	}()

	wg.Wait()

	// Interstat attribution (fire-and-forget)
	sessionID := os.Getenv("CLAUDE_SESSION_ID")
	if sessionID == "" {
		// Try the interstat session file
		if data, err := os.ReadFile("/tmp/interstat-session-id"); err == nil {
			sessionID = strings.TrimSpace(string(data))
		}
	}
	if sessionID != "" {
		_ = os.WriteFile("/tmp/interstat-bead-"+sessionID, []byte(beadID), 0644)
		if icAvailable() {
			runIC("session", "attribute", "--session="+sessionID, "--bead="+beadID)
		}
	}

	// Compute next phase
	nextPhase := ""
	if phase != "" {
		next := cmdSprintNextStepPure(phase)
		if next != "" && next != phase {
			nextPhase = next
		}
	}

	data := sprintInitData{
		beadID:     beadID,
		title:      title,
		complexity: complexity,
		compLabel:  compLabel,
		phase:      phase,
		nextPhase:  nextPhase,
		budget:     budget,
		spent:      spent,
		hasRun:     hasRun,
	}

	// Print to stdout, also output complexity as a parseable line for the caller
	useColor := shouldUseColor()
	fmt.Print(formatBanner(data, useColor))
	return nil
}

// cmdSprintNextStepPure returns the next step name for a given phase (pure, no subprocess).
func cmdSprintNextStepPure(phase string) string {
	for i, p := range defaultPhases {
		if p == phase && i+1 < len(defaultPhases) {
			return defaultPhases[i+1]
		}
	}
	return ""
}

// shouldUseColor returns true if stdout is a TTY and NO_COLOR is not set.
func shouldUseColor() bool {
	if os.Getenv("NO_COLOR") != "" {
		return false
	}
	fi, err := os.Stdout.Stat()
	if err != nil {
		return false
	}
	// Check if stdout is a character device (terminal)
	return fi.Mode()&os.ModeCharDevice != 0
}

// formatBanner renders the sprint status banner.
func formatBanner(d sprintInitData, color bool) string {
	var b strings.Builder

	// Color helpers
	c := func(code, text string) string {
		if !color {
			return text
		}
		return code + text + colorReset
	}

	// Width for the box
	const width = 50

	// Top border
	border := strings.Repeat("─", width)
	if color {
		b.WriteString(c(colorPrimary, "── Sprint: "+d.beadID+" ") + c(colorMuted, border[:max(0, width-len("── Sprint: "+d.beadID+" "))]) + "\n")
	} else {
		header := "-- Sprint: " + d.beadID + " "
		b.WriteString(header + strings.Repeat("-", max(0, width-len(header))) + "\n")
	}

	// Title (truncate if long)
	titleDisplay := d.title
	if len(titleDisplay) > 45 {
		titleDisplay = titleDisplay[:42] + "..."
	}
	b.WriteString(c(colorPrimary, " Title:      ") + c(colorFg, titleDisplay) + "\n")

	// Complexity
	compStr := fmt.Sprintf("%d/5 (%s)", d.complexity, d.compLabel)
	b.WriteString(c(colorPrimary, " Complexity: ") + c(colorInfo, compStr) + "\n")

	// Phase
	if d.phase != "" {
		phaseStr := d.phase
		if d.nextPhase != "" {
			phaseStr = d.phase + " → " + d.nextPhase
		}
		b.WriteString(c(colorPrimary, " Phase:      ") + c(colorInfo, phaseStr) + "\n")
	}

	// Budget
	if d.hasRun && d.budget > 0 {
		pct := int(float64(d.spent) / float64(d.budget) * 100)
		budgetStr := fmt.Sprintf("%dk / %dk (%d%%)", d.spent/1000, d.budget/1000, pct)
		budgetColor := colorSuccess
		if pct > 90 {
			budgetColor = colorError
		} else if pct > 70 {
			budgetColor = colorWarning
		}
		b.WriteString(c(colorPrimary, " Budget:     ") + c(budgetColor, budgetStr) + "\n")
	} else if d.hasRun {
		b.WriteString(c(colorPrimary, " Budget:     ") + c(colorMuted, "(no budget set)") + "\n")
	}

	// Bottom border
	if color {
		b.WriteString(c(colorMuted, strings.Repeat("─", width)) + "\n")
	} else {
		b.WriteString(strings.Repeat("-", width) + "\n")
	}

	return b.String()
}

// parseBDTitle extracts the bead title from `bd show` output.
// Format varies but typically: "✓ Demarch-czxk · Title here [status]"
// or "Demarch-czxk — Title here"
func parseBDTitle(output string) string {
	lines := strings.SplitN(output, "\n", 2)
	if len(lines) == 0 {
		return ""
	}
	line := lines[0]

	// Try "· " separator first (bd show format)
	if idx := strings.Index(line, "· "); idx >= 0 {
		line = line[idx+len("· "):]
	} else if idx := strings.Index(line, "— "); idx >= 0 {
		line = line[idx+len("— "):]
	}

	// Strip trailing status bracket
	if idx := strings.LastIndex(line, " ["); idx >= 0 {
		line = line[:idx]
	}

	return strings.TrimSpace(line)
}

// tryComplexityOverrideQuiet is like tryComplexityOverride but discards stderr.
func tryComplexityOverrideQuiet(beadID string) string {
	if icAvailable() {
		var run Run
		err := runICJSONQuiet(&run, "run", "status", "--scope", beadID)
		if err == nil && run.Complexity > 0 {
			return strconv.Itoa(run.Complexity)
		}
	}
	if bdAvailable() {
		out, err := runBDQuiet("state", beadID, "complexity")
		if err == nil {
			val := strings.TrimSpace(string(out))
			if val != "" && val != "null" && !strings.HasPrefix(val, "(no ") {
				return val
			}
		}
	}
	return ""
}

// resolveRunIDQuiet is like resolveRunID but discards stderr.
func resolveRunIDQuiet(beadID string) (string, error) {
	if beadID == "" {
		return "", fmt.Errorf("empty bead ID")
	}
	if rid, ok := runIDCache[beadID]; ok {
		return rid, nil
	}
	out, err := runBDQuiet("state", beadID, "ic_run_id")
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

// readBudgetResultQuiet is like readBudgetResult but discards stderr.
func readBudgetResultQuiet(runID string) (BudgetResult, error) {
	var br BudgetResult
	if err := runICJSONQuiet(&br, "run", "budget", runID); err != nil {
		return BudgetResult{}, err
	}
	return br, nil
}

// max returns the larger of a or b.
func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
