package main

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

// wordPattern matches sequences of letters, digits, and hyphens (matching the
// Bash awk gsub(/[^a-zA-Z-]/, "") behavior for keyword extraction).
var wordPattern = regexp.MustCompile(`[a-zA-Z][a-zA-Z0-9-]*`)

// trivialKeywords triggers complexity=1 when found in short descriptions (<20 words).
var trivialKeywords = map[string]bool{
	"rename": true, "format": true, "typo": true,
	"bump": true, "reformat": true, "formatting": true,
}

// researchKeywords triggers complexity=5 when >1 are found.
var researchKeywords = map[string]bool{
	"explore": true, "investigate": true, "research": true,
	"brainstorm": true, "evaluate": true, "survey": true, "analyze": true,
}

// ambiguitySignals bump complexity +1 when >2 are found.
var ambiguitySignals = map[string]bool{
	"or": true, "vs": true, "versus": true, "alternative": true,
	"tradeoff": true, "trade-off": true, "either": true,
	"approach": true, "option": true,
}

// simplicitySignals bump complexity -1 when >2 are found.
var simplicitySignals = map[string]bool{
	"like": true, "similar": true, "existing": true,
	"just": true, "simple": true, "straightforward": true,
}

// classifyComplexity scores a description on a 1-5 complexity scale.
// Scale: 1=trivial, 2=simple, 3=moderate, 4=complex, 5=research.
// This is a pure function porting the Bash heuristics from lib-sprint.sh.
func classifyComplexity(desc string) int {
	if desc == "" {
		return 3
	}

	// Word count using strings.Fields (matches wc -w behavior)
	words := strings.Fields(desc)
	wordCount := len(words)

	// Vacuous descriptions (<5 words) are too short to classify
	if wordCount < 5 {
		return 3
	}

	// Extract cleaned words for keyword matching (lowercase, letters/hyphens only)
	cleanedWords := wordPattern.FindAllString(desc, -1)

	// Count keyword matches
	trivialCount := countMatches(cleanedWords, trivialKeywords)
	researchCount := countMatches(cleanedWords, researchKeywords)
	ambiguityCount := countMatches(cleanedWords, ambiguitySignals)
	simplicityCount := countMatches(cleanedWords, simplicitySignals)

	// Trivial keywords — floor at 1
	if trivialCount > 0 && wordCount < 20 {
		return 1
	}

	// Research keywords — ceiling at 5
	if researchCount > 1 {
		return 5
	}

	// Score: start with word-count tier, adjust with signals
	var score int
	if wordCount < 30 {
		score = 2 // simple
	} else if wordCount < 100 {
		score = 3 // moderate
	} else {
		score = 4 // complex
	}

	// Adjust: >2 signals indicates a real pattern, not noise from common words
	if ambiguityCount > 2 {
		score++
	}
	if simplicityCount > 2 {
		score--
	}

	// Clamp to 1-5
	if score < 1 {
		score = 1
	}
	if score > 5 {
		score = 5
	}
	return score
}

// countMatches counts how many words (case-insensitive) appear in the keyword set.
func countMatches(words []string, keywords map[string]bool) int {
	count := 0
	for _, w := range words {
		if keywords[strings.ToLower(w)] {
			count++
		}
	}
	return count
}

// complexityLabel converts a numeric score to a human-readable label.
// Also handles legacy string values passed as integers (via the Bash caller).
func complexityLabel(score int) string {
	switch score {
	case 1:
		return "trivial"
	case 2:
		return "simple"
	case 3:
		return "moderate"
	case 4:
		return "complex"
	case 5:
		return "research"
	default:
		return "moderate"
	}
}

// complexityLabelFromString handles both numeric and legacy string inputs.
// Legacy strings: "simple"→"simple", "medium"→"moderate", "complex"→"complex".
func complexityLabelFromString(s string) string {
	// Try numeric first
	if n, err := strconv.Atoi(s); err == nil {
		return complexityLabel(n)
	}
	// Legacy string values
	switch strings.ToLower(s) {
	case "simple":
		return "simple"
	case "medium":
		return "moderate"
	case "complex":
		return "complex"
	case "trivial":
		return "trivial"
	case "research":
		return "research"
	case "moderate":
		return "moderate"
	default:
		return "moderate"
	}
}

// cmdClassifyComplexity handles: classify-complexity <bead_id> <description...>
// Checks ic run status for complexity override, then bd state, then falls back to heuristic.
func cmdClassifyComplexity(args []string) error {
	if len(args) < 2 {
		return fmt.Errorf("usage: classify-complexity <bead_id> <description...>")
	}

	beadID := args[0]
	description := strings.Join(args[1:], " ")

	// Check for manual override — try ic run first, then beads
	if beadID != "" {
		override := tryComplexityOverride(beadID)
		if override != "" {
			fmt.Println(override)
			return nil
		}
	}

	// Fall back to heuristic classification
	score := classifyComplexity(description)
	fmt.Println(score)
	return nil
}

// tryComplexityOverride checks ic run status and bd state for a manual complexity override.
// Returns the override string (numeric or legacy), or "" if none found.
func tryComplexityOverride(beadID string) string {
	// Try ic run status first — get the run for this bead
	if icAvailable() {
		var run Run
		err := runICJSON(&run, "run", "status", "--scope", beadID)
		if err == nil && run.Complexity > 0 {
			return strconv.Itoa(run.Complexity)
		}
	}

	// Try bd state
	if bdAvailable() {
		out, err := runBD("state", beadID, "complexity")
		if err == nil {
			val := strings.TrimSpace(string(out))
			if val != "" && val != "null" {
				return val
			}
		}
	}

	return ""
}

// cmdComplexityLabel handles: complexity-label <score>
// Outputs the human-readable label for the given score.
func cmdComplexityLabel(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("usage: complexity-label <score>")
	}

	// Use the string-aware version to handle both numeric and legacy inputs
	label := complexityLabelFromString(args[0])
	fmt.Println(label)
	return nil
}

// RunStatus is a partial parse of ic run status output, used only for
// extracting the complexity field without needing the full Run type.
type RunStatus struct {
	Complexity json.RawMessage `json:"complexity"`
}
