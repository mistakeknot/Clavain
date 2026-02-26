package main

import "testing"

func TestParseBlockedIDs(t *testing.T) {
	tests := []struct {
		name string
		out  string
		want []string
	}{
		{
			name: "typical BLOCKS section with mix of open and closed",
			out: `✓ iv-1xtgd [EPIC] · Bash-Heavy L2 Logic Migration   [● P0 · CLOSED]
Owner: mk · Type: epic
Created: 2026-02-24 · Updated: 2026-02-26

DESCRIPTION
Some description text

CHILDREN
  ↳ ✓ iv-1xtgd.1: Some closed child ● P0

BLOCKS
  ← ○ iv-5b6wu: F3: Phase transitions ● P2
  ← ✓ iv-sevis: F1: Go binary scaffold ● P2
  ← ○ iv-udul3: F2: Budget math ● P2

PARENT
  ↑ ○ iv-xyz: Some parent epic ● P1`,
			want: []string{"iv-5b6wu", "iv-udul3"},
		},
		{
			name: "all closed — no open beads",
			out: `BLOCKS
  ← ✓ iv-abc: Done ● P1
  ← ✓ iv-def: Done ● P2`,
			want: nil,
		},
		{
			name: "empty output",
			out:  "",
			want: nil,
		},
		{
			name: "no BLOCKS section",
			out: `✓ iv-xyz [TASK] · Some task   [● P0 · OPEN]

DESCRIPTION
Text

PARENT
  ↑ ○ iv-parent: Epic ● P0`,
			want: nil,
		},
		{
			name: "dotted bead IDs",
			out: `BLOCKS
  ← ○ iv-1xtgd.1: Sub-task one ● P2
  ← ○ iv-1xtgd.2: Sub-task two ● P2`,
			want: []string{"iv-1xtgd.1", "iv-1xtgd.2"},
		},
		{
			name: "single open bead",
			out: `BLOCKS
  ← ○ iv-abc: Only one ● P1`,
			want: []string{"iv-abc"},
		},
		{
			name: "BLOCKS section followed by another section",
			out: `BLOCKS
  ← ○ iv-abc: Open bead ● P1

LABELS
  some-label`,
			want: []string{"iv-abc"},
		},
		{
			name: "mixed status icons in BLOCKS",
			out: `BLOCKS
  ← ○ iv-open1: Open ● P2
  ← ◐ iv-inprog: In progress ● P2
  ← ● iv-closed1: Closed ● P2
  ← ✓ iv-done: Done ● P2
  ← ❄ iv-frozen: Deferred ● P2
  ← ○ iv-open2: Also open ● P1`,
			want: []string{"iv-open1", "iv-open2"},
		},
		{
			name: "BLOCKS section with only blank line after",
			out: `BLOCKS
  ← ○ iv-abc: Task ● P2
`,
			want: []string{"iv-abc"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := parseBlockedIDs(tt.out)
			if !stringSliceEqual(got, tt.want) {
				t.Errorf("parseBlockedIDs() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestParseParentID(t *testing.T) {
	tests := []struct {
		name string
		out  string
		want string
	}{
		{
			name: "typical parent with open status",
			out: `✓ iv-1xtgd [EPIC] · Title   [● P0 · CLOSED]

PARENT
  ↑ ○ iv-xyz: Some parent epic ● P1`,
			want: "iv-xyz",
		},
		{
			name: "parent with in-progress status",
			out: `PARENT
  ↑ ◐ iv-big: Big parent ● P0`,
			want: "iv-big",
		},
		{
			name: "parent with closed status",
			out: `PARENT
  ↑ ✓ iv-done: Closed parent ● P0`,
			want: "iv-done",
		},
		{
			name: "parent with frozen status",
			out: `PARENT
  ↑ ❄ iv-frozen: Deferred parent ● P0`,
			want: "iv-frozen",
		},
		{
			name: "parent with filled status",
			out: `PARENT
  ↑ ● iv-full: Full parent ● P0`,
			want: "iv-full",
		},
		{
			name: "no parent section",
			out: `✓ iv-abc [TASK]   [● P0 · OPEN]

DESCRIPTION
Text

BLOCKS
  ← ○ iv-child: Child ● P2`,
			want: "",
		},
		{
			name: "empty output",
			out:  "",
			want: "",
		},
		{
			name: "parent section with no arrow line",
			out: `PARENT
  (none)`,
			want: "",
		},
		{
			name: "dotted parent ID",
			out: `PARENT
  ↑ ○ iv-1xtgd.1: Sub-epic parent ● P0`,
			want: "iv-1xtgd.1",
		},
		{
			name: "parent section followed by another section",
			out: `PARENT
  ↑ ○ iv-par: Parent ● P0

NOTES
  some note`,
			want: "iv-par",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := parseParentID(tt.out)
			if got != tt.want {
				t.Errorf("parseParentID() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestCountOpenChildren(t *testing.T) {
	tests := []struct {
		name string
		out  string
		want int
	}{
		{
			name: "mix of open, in-progress, and closed",
			out: `✓ iv-1xtgd [EPIC]   [● P0 · CLOSED]

CHILDREN
  ↳ ✓ iv-1xtgd.1: Closed child ● P0
  ↳ ○ iv-abc: Open child ● P2
  ↳ ◐ iv-def: In-progress child ● P2
  ↳ ● iv-ghi: Another closed ● P1
  ↳ ❄ iv-jkl: Deferred child ● P3`,
			want: 2,
		},
		{
			name: "all closed",
			out: `CHILDREN
  ↳ ✓ iv-a: Done ● P0
  ↳ ✓ iv-b: Done ● P0
  ↳ ● iv-c: Done ● P0`,
			want: 0,
		},
		{
			name: "all open",
			out: `CHILDREN
  ↳ ○ iv-a: Open ● P0
  ↳ ○ iv-b: Open ● P0
  ↳ ○ iv-c: Open ● P0`,
			want: 3,
		},
		{
			name: "all in-progress",
			out: `CHILDREN
  ↳ ◐ iv-a: WIP ● P0
  ↳ ◐ iv-b: WIP ● P0`,
			want: 2,
		},
		{
			name: "empty output",
			out:  "",
			want: 0,
		},
		{
			name: "no CHILDREN section",
			out: `BLOCKS
  ← ○ iv-abc: Open ● P2

PARENT
  ↑ ○ iv-par: Parent ● P0`,
			want: 0,
		},
		{
			name: "single open child",
			out: `CHILDREN
  ↳ ○ iv-only: Only child ● P1`,
			want: 1,
		},
		{
			name: "single closed child",
			out: `CHILDREN
  ↳ ✓ iv-only: Only child ● P1`,
			want: 0,
		},
		{
			name: "children section with deferred only",
			out: `CHILDREN
  ↳ ❄ iv-x: Deferred ● P0
  ↳ ❄ iv-y: Also deferred ● P0`,
			want: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := countOpenChildren(tt.out)
			if got != tt.want {
				t.Errorf("countOpenChildren() = %d, want %d", got, tt.want)
			}
		})
	}
}

func TestExtractSection(t *testing.T) {
	output := `✓ iv-1xtgd [EPIC]   [● P0 · CLOSED]
Owner: mk

DESCRIPTION
Some description text

CHILDREN
  ↳ ✓ iv-a: Child ● P0
  ↳ ○ iv-b: Child ● P2

BLOCKS
  ← ○ iv-c: Block ● P2

PARENT
  ↑ ○ iv-d: Parent ● P1`

	tests := []struct {
		name    string
		section string
		want    int // expected line count
	}{
		{"DESCRIPTION", "DESCRIPTION", 1},
		{"CHILDREN", "CHILDREN", 2},
		{"BLOCKS", "BLOCKS", 1},
		{"PARENT", "PARENT", 1},
		{"nonexistent", "LABELS", 0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := extractSection(output, tt.section)
			if len(got) != tt.want {
				t.Errorf("extractSection(%q) returned %d lines, want %d: %v", tt.section, len(got), tt.want, got)
			}
		})
	}
}

func TestBeadIDRegex(t *testing.T) {
	tests := []struct {
		input string
		match bool
	}{
		{"iv-abc", true},
		{"iv-1xtgd", true},
		{"iv-1xtgd.1", true},
		{"iv-1xtgd.12", true},
		{"FOO-bar2", true},
		{"A-b", true},
		{"abc", false},          // no dash
		{"-abc", false},         // starts with dash
		{"123-abc", false},      // starts with digit
		{"iv-", false},          // nothing after dash
		{"", false},             // empty
		{"iv-abc def", false},   // space
		{"iv-abc:xyz", false},   // colon
		{"iv-abc.1.2", true},    // double dots
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := beadIDRe.MatchString(tt.input)
			if got != tt.match {
				t.Errorf("beadIDRe.MatchString(%q) = %v, want %v", tt.input, got, tt.match)
			}
		})
	}
}

// stringSliceEqual compares two string slices. Both nil and empty are treated as equal.
func stringSliceEqual(a, b []string) bool {
	if len(a) == 0 && len(b) == 0 {
		return true
	}
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
