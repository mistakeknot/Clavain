package main

import (
	"fmt"
	"regexp"
	"strings"
)

// beadIDRe matches valid bead IDs like iv-abc, iv-1xtgd.1, FOO-bar2.
var beadIDRe = regexp.MustCompile(`^[A-Za-z]+-[A-Za-z0-9.]+$`)

// sectionHeaders lists all known bd show section headers.
var sectionHeaders = map[string]bool{
	"BLOCKS":      true,
	"CHILDREN":    true,
	"PARENT":      true,
	"DESCRIPTION": true,
	"LABELS":      true,
	"NOTES":       true,
	"COMMENTS":    true,
	"DEPENDS ON":  true,
}

// extractSection returns the lines belonging to a named section in bd show output.
// A section starts with a line exactly matching the header and ends at the next
// section header, a blank line, or end of output.
func extractSection(output, section string) []string {
	lines := strings.Split(output, "\n")
	var result []string
	inSection := false
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == section {
			inSection = true
			continue
		}
		if inSection {
			// End of section: blank line or another section header.
			if trimmed == "" || sectionHeaders[trimmed] {
				break
			}
			result = append(result, line)
		}
	}
	return result
}

// parseBlockedIDs extracts open bead IDs from bd show output's BLOCKS section.
// Open beads are lines containing "← ○". The ID is between "← ○ " and the first ":".
func parseBlockedIDs(output string) []string {
	lines := extractSection(output, "BLOCKS")
	var ids []string
	for _, line := range lines {
		if !strings.Contains(line, "← ○") {
			continue
		}
		// Extract text after "← ○ "
		idx := strings.Index(line, "← ○ ")
		if idx < 0 {
			continue
		}
		rest := line[idx+len("← ○ "):]
		// ID is before the first ":"
		if ci := strings.Index(rest, ":"); ci >= 0 {
			rest = rest[:ci]
		}
		candidate := strings.TrimSpace(rest)
		if beadIDRe.MatchString(candidate) {
			ids = append(ids, candidate)
		}
	}
	return ids
}

// parseParentID extracts the parent bead ID from bd show output's PARENT section.
// Looks for lines containing "↑", then extracts the ID after the status icon.
func parseParentID(output string) string {
	lines := extractSection(output, "PARENT")
	for _, line := range lines {
		if !strings.Contains(line, "↑") {
			continue
		}
		// Find "↑" then skip the status icon (○, ◐, ●, ✓, ❄) and extract ID before ":"
		idx := strings.Index(line, "↑")
		if idx < 0 {
			continue
		}
		rest := line[idx+len("↑"):]
		rest = strings.TrimSpace(rest)
		// Skip the status icon — it's a single rune followed by space
		if len(rest) > 0 {
			runes := []rune(rest)
			// Skip one rune (status icon) then any spaces
			if len(runes) > 1 {
				rest = strings.TrimSpace(string(runes[1:]))
			}
		}
		// ID is before the first ":"
		if ci := strings.Index(rest, ":"); ci >= 0 {
			rest = rest[:ci]
		}
		candidate := strings.TrimSpace(rest)
		if beadIDRe.MatchString(candidate) {
			return candidate
		}
	}
	return ""
}

// countOpenChildren counts open children (↳ ○ or ↳ ◐) from bd show output's CHILDREN section.
func countOpenChildren(output string) int {
	lines := extractSection(output, "CHILDREN")
	count := 0
	for _, line := range lines {
		if strings.Contains(line, "↳") {
			if strings.Contains(line, "↳ ○") || strings.Contains(line, "↳ ◐") {
				count++
			}
		}
	}
	return count
}

// cmdCloseChildren closes open beads blocked by the given epic.
// Args: <epic_id> [reason]
// Outputs the count of successfully closed beads.
func cmdCloseChildren(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: close-children <epic_id> [reason]")
	}
	epicID := args[0]
	reason := fmt.Sprintf("Auto-closed: parent epic %s shipped", epicID)
	if len(args) >= 2 {
		reason = args[1]
	}

	if !bdAvailable() {
		fmt.Println("0")
		return nil
	}

	// Get bd show output for the epic
	out, err := runBD("show", epicID)
	if err != nil {
		fmt.Println("0")
		return nil
	}

	blockedIDs := parseBlockedIDs(string(out))
	if len(blockedIDs) == 0 {
		fmt.Println("0")
		// Still try to close parent
		_ = cmdCloseParentIfDone([]string{epicID, fmt.Sprintf("All children completed under epic %s", epicID)})
		return nil
	}

	closed := 0
	for _, id := range blockedIDs {
		_, cerr := runBD("close", id, fmt.Sprintf("--reason=%s", reason))
		if cerr == nil {
			closed++
		}
	}

	// After closing children, try closing parent if all siblings are done
	_ = cmdCloseParentIfDone([]string{epicID, fmt.Sprintf("All children completed under epic %s", epicID)})

	fmt.Println(closed)
	return nil
}

// cmdCloseParentIfDone closes the parent bead if all its children are now closed.
// Args: <bead_id> [reason]
// Outputs the parent ID if closed, nothing otherwise.
func cmdCloseParentIfDone(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: close-parent-if-done <bead_id> [reason]")
	}
	beadID := args[0]
	reason := "Auto-closed: all children completed"
	if len(args) >= 2 {
		reason = args[1]
	}

	if !bdAvailable() {
		return nil
	}

	// Get parent from bd show
	out, err := runBD("show", beadID)
	if err != nil {
		return nil
	}

	parentID := parseParentID(string(out))
	if parentID == "" {
		return nil
	}

	// Check if parent is still open
	parentOut, err := runBD("show", parentID)
	if err != nil {
		return nil
	}
	parentLines := strings.SplitN(string(parentOut), "\n", 2)
	if len(parentLines) == 0 {
		return nil
	}
	firstLine := parentLines[0]
	if !strings.Contains(firstLine, "OPEN") && !strings.Contains(firstLine, "IN_PROGRESS") {
		return nil
	}

	// Count open children of parent
	openChildren := countOpenChildren(string(parentOut))
	if openChildren == 0 {
		_, cerr := runBD("close", parentID, fmt.Sprintf("--reason=%s", reason))
		if cerr == nil {
			fmt.Println(parentID)
		}
	}

	return nil
}
