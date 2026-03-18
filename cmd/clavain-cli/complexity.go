package main

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

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

// trivialKeywordsList etc. are pre-computed slices for countMatchesInText.
var trivialKeywordsList = mapKeys(trivialKeywords)
var researchKeywordsList = mapKeys(researchKeywords)
var ambiguitySignalsList = mapKeys(ambiguitySignals)
var simplicitySignalsList = mapKeys(simplicitySignals)

func mapKeys(m map[string]bool) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
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

	// Pre-lowercase the entire input once, then search for keywords directly.
	lowered := strings.ToLower(desc)

	// Count keyword matches by scanning text for each keyword
	trivialCount := countMatchesInText(lowered, trivialKeywordsList)
	researchCount := countMatchesInText(lowered, researchKeywordsList)
	ambiguityCount := countMatchesInText(lowered, ambiguitySignalsList)
	simplicityCount := countMatchesInText(lowered, simplicitySignalsList)

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
// Retained for backward compatibility with direct callers.
func countMatches(words []string, keywords map[string]bool) int {
	count := 0
	for _, w := range words {
		if keywords[strings.ToLower(w)] {
			count++
		}
	}
	return count
}

// isWordBoundary reports whether the byte at position i in text is a word boundary
// (i.e., not a letter, digit, or hyphen).
func isWordBoundary(text string, i int) bool {
	if i < 0 || i >= len(text) {
		return true // start/end of string is a boundary
	}
	c := text[i]
	return !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-')
}

// countMatchesInText searches pre-lowered text for each keyword, counting all
// word-boundary-delimited occurrences. This avoids regex extraction and per-word lowering.
func countMatchesInText(lowered string, keywords []string) int {
	count := 0
	for _, kw := range keywords {
		off := 0
		for off < len(lowered) {
			idx := strings.Index(lowered[off:], kw)
			if idx < 0 {
				break
			}
			abs := off + idx
			// Check word boundaries: char before and after the match
			if isWordBoundary(lowered, abs-1) && isWordBoundary(lowered, abs+len(kw)) {
				count++
			}
			off = abs + len(kw)
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
// Checks ic run status for complexity override, then bd state, then falls back to heuristic
// with structural signals from the bead (type, children).
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

	// Heuristic classification from description text
	score := classifyComplexity(description)

	// Structural adjustments from bead metadata (if available)
	if beadID != "" && bdAvailable() {
		// Epic with no children → needs decomposition → bump complexity
		beadType, _ := runBD("show", beadID, "--field=type")
		if strings.TrimSpace(string(beadType)) == "epic" {
			childCount, _ := runBD("children", beadID)
			if strings.TrimSpace(string(childCount)) == "[]" || strings.TrimSpace(string(childCount)) == "" {
				if score < 4 {
					score = 4 // epics without children need full exploration
				}
			}
		}
		// Bug type → cap complexity at 3 (bugs have clear scope)
		if strings.TrimSpace(string(beadType)) == "bug" && score > 3 {
			score = 3
		}
	}

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
