package main

import "testing"

func TestClassifyComplexity(t *testing.T) {
	tests := []struct {
		name string
		desc string
		want int
	}{
		// Empty / vacuous descriptions → default 3
		{"empty string", "", 3},
		{"too short single word", "fix", 3},
		{"too short four words", "fix the bug now", 3},

		// Trivial keywords with <20 words → 1
		{"trivial rename", "rename the variable to something better", 1},
		{"trivial typo", "fix typo in the readme file", 1},
		{"trivial bump", "bump the version number please", 1},
		{"trivial format", "reformat the code in main module", 1},
		{"trivial formatting", "formatting changes to the config file", 1},

		// Trivial keyword but >=20 words → NOT trivial (word count takes over)
		{"trivial keyword but long", "rename the variable to something better and also update all references across the entire codebase including tests and documentation files", 2},

		// Research keywords (>1) → 5
		{"research two keywords", "explore the architecture and investigate tradeoffs for the new system", 5},
		{"research explore and brainstorm", "explore different options and brainstorm approaches for auth", 5},
		{"research three keywords", "research and evaluate and analyze the new framework options", 5},

		// Research single keyword → NOT forced to 5
		{"research single keyword", "explore the new framework options for better performance", 2},

		// Short simple descriptions → 2
		{"short simple", "add a button to the form", 2},
		{"short moderate", "implement the user login page", 2},

		// Long complex descriptions (>=100 words) → 4
		{"long complex", "implement the authentication system with OAuth2 integration rate limiting and session management for multiple providers including Google Facebook Apple and GitHub with proper error handling retry logic token refresh mechanism secure storage of credentials audit logging of all authentication events proper CORS configuration for the frontend integration rate limiting per user and per IP address with configurable thresholds and a comprehensive test suite covering unit integration and end to end scenarios including failure modes and edge cases and proper documentation for the API endpoints and configuration options plus database migration scripts for the new tables and indexes needed to support the feature", 4},

		// Ambiguity signals (>2) → +1
		{"ambiguity bump", "decide between option A or option B versus option C with tradeoff analysis either approach works", 3},

		// Simplicity signals (>2) → -1
		{"simplicity bump", "add simple feature like existing similar functionality just copy the straightforward pattern", 1},

		// Word count tiers
		{"exactly 5 words short", "add the new user button", 2},
		{"moderate length 30+ words", "implement the new dashboard view with filtering and sorting capabilities for the admin panel including proper pagination handling error states loading indicators and responsive design for mobile devices on all pages", 3},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := classifyComplexity(tt.desc)
			if got != tt.want {
				t.Errorf("classifyComplexity(%q) = %d, want %d", tt.desc, got, tt.want)
			}
		})
	}
}

func TestComplexityLabel(t *testing.T) {
	tests := []struct {
		name  string
		score int
		want  string
	}{
		{"trivial", 1, "trivial"},
		{"simple", 2, "simple"},
		{"moderate", 3, "moderate"},
		{"complex", 4, "complex"},
		{"research", 5, "research"},
		{"zero", 0, "moderate"},
		{"negative", -1, "moderate"},
		{"high out of range", 99, "moderate"},
		{"six", 6, "moderate"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := complexityLabel(tt.score)
			if got != tt.want {
				t.Errorf("complexityLabel(%d) = %q, want %q", tt.score, got, tt.want)
			}
		})
	}
}

func TestComplexityLabelFromString(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		// Numeric inputs
		{"numeric 1", "1", "trivial"},
		{"numeric 2", "2", "simple"},
		{"numeric 3", "3", "moderate"},
		{"numeric 4", "4", "complex"},
		{"numeric 5", "5", "research"},
		{"numeric 0", "0", "moderate"},

		// Legacy string inputs
		{"legacy simple", "simple", "simple"},
		{"legacy medium", "medium", "moderate"},
		{"legacy complex", "complex", "complex"},
		{"legacy trivial", "trivial", "trivial"},
		{"legacy research", "research", "research"},
		{"legacy moderate", "moderate", "moderate"},

		// Case insensitive
		{"legacy Simple upper", "Simple", "simple"},
		{"legacy MEDIUM upper", "MEDIUM", "moderate"},

		// Unknown defaults to moderate
		{"unknown string", "foobar", "moderate"},
		{"empty string", "", "moderate"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := complexityLabelFromString(tt.input)
			if got != tt.want {
				t.Errorf("complexityLabelFromString(%q) = %q, want %q", tt.input, got, tt.want)
			}
		})
	}
}

func TestCountMatches(t *testing.T) {
	keywords := map[string]bool{"foo": true, "bar": true, "baz": true}

	tests := []struct {
		name  string
		words []string
		want  int
	}{
		{"no matches", []string{"hello", "world"}, 0},
		{"one match", []string{"hello", "foo", "world"}, 1},
		{"two matches", []string{"foo", "bar"}, 2},
		{"case insensitive", []string{"FOO", "Bar", "BAZ"}, 3},
		{"empty input", []string{}, 0},
		{"duplicates counted", []string{"foo", "foo", "foo"}, 3},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := countMatches(tt.words, keywords)
			if got != tt.want {
				t.Errorf("countMatches(%v) = %d, want %d", tt.words, got, tt.want)
			}
		})
	}
}

// TestClassifyComplexityEdgeCases covers boundary conditions.
func TestClassifyComplexityEdgeCases(t *testing.T) {
	tests := []struct {
		name string
		desc string
		want int
	}{
		// Exactly 5 words (boundary — should NOT be "too short")
		{"exactly 5 words", "please add new user button", 2},

		// Exactly 4 words (boundary — SHOULD be "too short")
		{"exactly 4 words", "please add new button", 3},

		// Trivial keyword at exactly 19 words (should be 1)
		{"trivial at 19 words", "rename the old variable name to something new and better across all of the main source code files", 1},

		// Trivial keyword at exactly 20 words (should NOT be trivial — word count >=20)
		{"trivial at 20 words", "rename the old variable name to something new and better across all of the main source code files right now", 2},

		// Clamping: simplicity signals on already-low score
		{"clamp low to 1", "just add simple existing similar like straightforward feature copy", 1},

		// Mixed signals: both ambiguity and simplicity
		{"mixed ambiguity and simplicity", "choose option or approach or alternative or tradeoff vs just simple like existing similar straightforward", 2},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := classifyComplexity(tt.desc)
			if got != tt.want {
				t.Errorf("classifyComplexity(%q) = %d, want %d", tt.desc, got, tt.want)
			}
		})
	}
}
