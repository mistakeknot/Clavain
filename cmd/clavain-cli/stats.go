package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	pkgphase "github.com/mistakeknot/intercore/pkg/phase"
)

// StatsRow is per-complexity stats in sprint-stats output.
type StatsRow struct {
	Complexity int     `json:"complexity"`
	Completed  int     `json:"completed"`
	Abandoned  int     `json:"abandoned"`
	Active     int     `json:"active"`
	Total      int     `json:"total"`
	Rate       float64 `json:"rate"`
}

// StatsResult is the full sprint-stats output.
type StatsResult struct {
	Rows         []StatsRow `json:"rows"`
	TotalRow     StatsRow   `json:"total"`
	TargetRate   float64    `json:"target_rate"`
	TargetMaxC   int        `json:"target_max_complexity"`
	TargetActual float64    `json:"target_actual"`
	TargetMet    bool       `json:"target_met"`
}

// cmdSprintStats computes sprint completion rate from ic run data.
// Flags: --complexity=N --since=DURATION --json --project=DIR
func cmdSprintStats(args []string) error {
	maxComplexity := 0 // 0 = no filter
	sinceDuration := time.Duration(0)
	jsonOutput := false
	projectDir := ""

	for _, arg := range args {
		switch {
		case strings.HasPrefix(arg, "--complexity="):
			if c, err := strconv.Atoi(arg[len("--complexity="):]); err == nil && c >= 1 && c <= 5 {
				maxComplexity = c
			}
		case strings.HasPrefix(arg, "--since="):
			sinceDuration = parseDuration(arg[len("--since="):])
		case arg == "--json":
			jsonOutput = true
		case strings.HasPrefix(arg, "--project="):
			projectDir = arg[len("--project="):]
		}
	}

	// Fetch all runs from intercore
	var runs []Run
	err := runICJSON(&runs, "run", "list")
	if err != nil {
		fmt.Fprintln(os.Stderr, "sprint-stats: cannot query runs")
		return err
	}

	// Apply filters
	sinceEpoch := int64(0)
	if sinceDuration > 0 {
		sinceEpoch = time.Now().Add(-sinceDuration).Unix()
	}
	if projectDir == "" {
		projectDir = mustGetwd()
	}

	// Aggregate by complexity
	byComplexity := map[int]*StatsRow{}
	for _, r := range runs {
		// Filter: project
		if r.ProjectDir != projectDir {
			continue
		}
		// Filter: complexity ceiling
		if maxComplexity > 0 && r.Complexity > maxComplexity {
			continue
		}
		// Filter: time window
		if sinceEpoch > 0 && r.CreatedAt < sinceEpoch {
			continue
		}

		row, ok := byComplexity[r.Complexity]
		if !ok {
			row = &StatsRow{Complexity: r.Complexity}
			byComplexity[r.Complexity] = row
		}

		row.Total++
		switch {
		case r.Status == "completed" || r.Phase == pkgphase.Done:
			row.Completed++
		case r.Status == "cancelled" || r.Status == "failed":
			row.Abandoned++
		default:
			row.Active++
		}
	}

	// Compute rates
	for _, row := range byComplexity {
		denominator := row.Completed + row.Abandoned
		if denominator > 0 {
			row.Rate = float64(row.Completed) / float64(denominator) * 100.0
		}
	}

	// Build ordered rows (complexity 1-5)
	var rows []StatsRow
	total := StatsRow{}
	for c := 1; c <= 5; c++ {
		if row, ok := byComplexity[c]; ok {
			rows = append(rows, *row)
			total.Completed += row.Completed
			total.Abandoned += row.Abandoned
			total.Active += row.Active
			total.Total += row.Total
		}
	}
	denom := total.Completed + total.Abandoned
	if denom > 0 {
		total.Rate = float64(total.Completed) / float64(denom) * 100.0
	}

	// Target: >70% for complexity ≤3
	targetRate := 70.0
	targetMaxC := 3
	var targetCompleted, targetAbandoned int
	for c := 1; c <= targetMaxC; c++ {
		if row, ok := byComplexity[c]; ok {
			targetCompleted += row.Completed
			targetAbandoned += row.Abandoned
		}
	}
	targetActual := 0.0
	targetDenom := targetCompleted + targetAbandoned
	if targetDenom > 0 {
		targetActual = float64(targetCompleted) / float64(targetDenom) * 100.0
	}

	result := StatsResult{
		Rows:         rows,
		TotalRow:     total,
		TargetRate:   targetRate,
		TargetMaxC:   targetMaxC,
		TargetActual: targetActual,
		TargetMet:    targetActual >= targetRate,
	}

	if jsonOutput {
		out, _ := json.Marshal(result)
		fmt.Print(string(out))
		return nil
	}

	// Human-readable table
	fmt.Println("Sprint Completion Rate")
	fmt.Println(strings.Repeat("─", 58))
	fmt.Printf("  %-16s %9s %9s %8s %8s\n", "", "Completed", "Abandoned", "Active", "Rate")

	for _, row := range rows {
		rateStr := "  n/a"
		if row.Completed+row.Abandoned > 0 {
			rateStr = fmt.Sprintf("%5.1f%%", row.Rate)
		}
		marker := ""
		if row.Complexity <= targetMaxC && row.Completed+row.Abandoned > 0 && row.Rate < targetRate {
			marker = "  ← below target"
		}
		fmt.Printf("  Complexity %-4d %9d %9d %8d %8s%s\n",
			row.Complexity, row.Completed, row.Abandoned, row.Active, rateStr, marker)
	}

	fmt.Println("  " + strings.Repeat("─", 56))
	totalRateStr := "  n/a"
	if denom > 0 {
		totalRateStr = fmt.Sprintf("%5.1f%%", total.Rate)
	}
	fmt.Printf("  %-16s %9d %9d %8d %8s\n", "Total", total.Completed, total.Abandoned, total.Active, totalRateStr)

	fmt.Println()
	if targetDenom > 0 {
		check := "✗"
		if result.TargetMet {
			check = "✓"
		}
		fmt.Printf("Target: >%.0f%% for complexity ≤%d → Current: %.1f%% (%d/%d) %s\n",
			targetRate, targetMaxC, targetActual, targetCompleted, targetDenom, check)
	} else {
		fmt.Printf("Target: >%.0f%% for complexity ≤%d → No data (0 completed+abandoned runs)\n",
			targetRate, targetMaxC)
	}

	return nil
}

// cmdRecentReflectLearnings surfaces recent reflect learnings from sibling beads.
// Reads closed siblings under the same parent, extracts reflection artifact content.
// Usage: recent-reflect-learnings <bead_id> [max_count]
func cmdRecentReflectLearnings(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: recent-reflect-learnings <bead_id> [max_count]")
	}
	beadID := args[0]
	maxCount := 3
	if len(args) >= 2 {
		if n, err := strconv.Atoi(args[1]); err == nil && n > 0 {
			maxCount = n
		}
	}

	if !bdAvailable() {
		return nil
	}

	// Find parent bead from dependency list
	depsOut, err := runBD("dep", "list", beadID, "--json")
	if err != nil {
		return nil // no deps — no siblings to query
	}

	type DepEntry struct {
		ID   string `json:"id"`
		Type string `json:"dependency_type"`
	}
	var deps []DepEntry
	if err := json.Unmarshal(depsOut, &deps); err != nil {
		return nil
	}

	// Find parent: bd dep list returns edges from bead's perspective.
	// parent-child deps where ID != beadID point to the parent.
	// If bd returns bidirectional edges, the first non-self match may be a sibling;
	// current bd behavior returns only direct edges (verified v0.60).
	parentID := ""
	for _, d := range deps {
		if d.Type == "parent-child" && d.ID != beadID {
			parentID = d.ID
			break
		}
	}
	if parentID == "" {
		return nil // no parent — standalone bead
	}

	// List closed siblings under the same parent
	siblingsOut, err := runBD("list", "--parent="+parentID, "--status=closed", "--json")
	if err != nil {
		return nil
	}

	type BeadEntry struct {
		ID string `json:"id"`
	}
	var siblings []BeadEntry
	if err := json.Unmarshal(siblingsOut, &siblings); err != nil {
		return nil
	}

	found := 0
	for _, sib := range siblings {
		if sib.ID == beadID || found >= maxCount {
			continue
		}
		// Check for reflection artifact
		artOut, err := runBD("state", sib.ID, "artifact_reflection")
		if err != nil {
			continue
		}
		artPath := strings.TrimSpace(string(artOut))
		if artPath == "" || strings.HasPrefix(artPath, "(no ") {
			continue
		}

		// Read file and extract substantive lines (skip frontmatter)
		content, err := os.ReadFile(artPath)
		if err != nil {
			continue
		}

		lines := strings.Split(string(content), "\n")
		inFrontmatter := false
		pastFrontmatter := false
		var substantive []string
		for _, line := range lines {
			trimmed := strings.TrimSpace(line)
			if trimmed == "---" {
				if !inFrontmatter && !pastFrontmatter {
					inFrontmatter = true
					continue
				}
				if inFrontmatter {
					inFrontmatter = false
					pastFrontmatter = true
					continue
				}
			}
			if inFrontmatter {
				continue
			}
			if trimmed != "" {
				substantive = append(substantive, trimmed)
			}
		}

		if len(substantive) == 0 {
			continue
		}

		// Take first 3 substantive lines
		limit := 3
		if len(substantive) < limit {
			limit = len(substantive)
		}
		fmt.Fprintf(os.Stdout, "  [%s] %s\n", sib.ID, strings.Join(substantive[:limit], " | "))
		found++
	}

	return nil
}

// parseDuration parses "7d", "30d", "24h" etc. into time.Duration.
func parseDuration(s string) time.Duration {
	s = strings.TrimSpace(s)
	if strings.HasSuffix(s, "d") {
		if days, err := strconv.Atoi(s[:len(s)-1]); err == nil {
			return time.Duration(days) * 24 * time.Hour
		}
	}
	if d, err := time.ParseDuration(s); err == nil {
		return d
	}
	return 0
}
