package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestNextStep(t *testing.T) {
	tests := []struct {
		phase string
		want  string
	}{
		{"brainstorm", "strategy"},
		{"brainstorm-reviewed", "strategy"},
		{"strategized", "write-plan"},
		{"planned", "flux-drive"},
		{"plan-reviewed", "work"},
		{"executing", "quality-gates"},
		{"shipping", "reflect"},
		{"reflect", "done"},
		{"done", "done"},
		{"unknown", "brainstorm"},
		{"", "brainstorm"},
	}
	for _, tt := range tests {
		got := nextStep(tt.phase)
		if got != tt.want {
			t.Errorf("nextStep(%q) = %q, want %q", tt.phase, got, tt.want)
		}
	}
}

// TestPhaseSequence verifies the canonical 9-phase chain.
func TestPhaseSequence(t *testing.T) {
	phases := []string{
		"brainstorm", "brainstorm-reviewed", "strategized",
		"planned", "plan-reviewed", "executing",
		"shipping", "reflect", "done",
	}
	if len(phases) != 9 {
		t.Fatalf("expected 9 phases, got %d", len(phases))
	}
	// Each phase except "done" must map to a non-empty next step
	for _, p := range phases[:8] {
		step := nextStep(p)
		if step == "" {
			t.Errorf("nextStep(%q) returned empty", p)
		}
	}
	// "done" maps to itself
	if nextStep("done") != "done" {
		t.Errorf("nextStep(\"done\") should return \"done\"")
	}
}

func TestCommandToStep(t *testing.T) {
	tests := []struct {
		cmd  string
		want string
	}{
		{"/clavain:brainstorm", "brainstorm"},
		{"/clavain:strategy", "strategy"},
		{"/clavain:write-plan", "write-plan"},
		{"/interflux:flux-drive", "flux-drive"},
		{"/clavain:work", "work"},
		{"/clavain:quality-gates", "quality-gates"},
		{"/clavain:resolve", "ship"},
		{"/reflect", "reflect"},
		{"/clavain:reflect", "reflect"},
		{"/custom:command", "/custom:command"},
	}
	for _, tt := range tests {
		got := commandToStep(tt.cmd)
		if got != tt.want {
			t.Errorf("commandToStep(%q) = %q, want %q", tt.cmd, got, tt.want)
		}
	}
}

func TestPhaseToStage(t *testing.T) {
	tests := []struct {
		phase string
		want  string
	}{
		{"brainstorm", "discover"},
		{"brainstorm-reviewed", "design"},
		{"strategized", "design"},
		{"planned", "design"},
		{"plan-reviewed", "design"},
		{"executing", "build"},
		{"shipping", "ship"},
		{"reflect", "reflect"},
		{"done", "done"},
		{"unknown", "unknown"},
		{"", "unknown"},
	}
	for _, tt := range tests {
		got := phaseToStage(tt.phase)
		if got != tt.want {
			t.Errorf("phaseToStage(%q) = %q, want %q", tt.phase, got, tt.want)
		}
	}
}

func TestPhaseToAction(t *testing.T) {
	tests := []struct {
		phase string
		want  string
	}{
		{"brainstorm", "strategize"},
		{"brainstorm-reviewed", "strategize"},
		{"strategized", "plan"},
		{"planned", "execute"},
		{"plan-reviewed", "execute"},
		{"executing", "continue"},
		{"shipping", "ship"},
		{"done", "closed"},
		{"unknown-phase", ""},
		{"", ""},
	}
	for _, tt := range tests {
		got := phaseToAction(tt.phase)
		if got != tt.want {
			t.Errorf("phaseToAction(%q) = %q, want %q", tt.phase, got, tt.want)
		}
	}
}

func TestBeadPattern(t *testing.T) {
	tests := []struct {
		line string
		want string
	}{
		{"**Bead:** iv-abc123", "iv-abc123"},
		{"Bead: iv-abc123", "iv-abc123"},
		{"**Bead**: iv-abc123", "iv-abc123"},
		{"**Bead:** Test-xyz", "Test-xyz"},
		{"no bead here", ""},
		{"Bead: iv-abc123 and more text", "iv-abc123"},
	}
	for _, tt := range tests {
		m := beadPattern.FindStringSubmatch(tt.line)
		got := ""
		if m != nil {
			got = m[1]
		}
		if got != tt.want {
			t.Errorf("beadPattern on %q = %q, want %q", tt.line, got, tt.want)
		}
	}
}

func TestCmdInferBead_EnvVar(t *testing.T) {
	t.Setenv("CLAVAIN_BEAD_ID", "iv-test123")

	// Capture stdout
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	err := cmdInferBead(nil)

	w.Close()
	os.Stdout = old

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	buf := make([]byte, 256)
	n, _ := r.Read(buf)
	got := string(buf[:n])
	if got != "iv-test123\n" {
		t.Errorf("cmdInferBead with CLAVAIN_BEAD_ID set: got %q, want %q", got, "iv-test123\n")
	}
}

func TestCmdInferBead_FromFile(t *testing.T) {
	t.Setenv("CLAVAIN_BEAD_ID", "")

	// Create a temp file with bead reference
	dir := t.TempDir()
	path := filepath.Join(dir, "test-plan.md")
	content := "# Test Plan\n\n**Bead:** iv-mytest\n\nSome content here.\n"
	os.WriteFile(path, []byte(content), 0644)

	// Capture stdout
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	err := cmdInferBead([]string{path})

	w.Close()
	os.Stdout = old

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	buf := make([]byte, 256)
	n, _ := r.Read(buf)
	got := string(buf[:n])
	if got != "iv-mytest\n" {
		t.Errorf("cmdInferBead from file: got %q, want %q", got, "iv-mytest\n")
	}
}

func TestCmdInferBead_NoMatch(t *testing.T) {
	t.Setenv("CLAVAIN_BEAD_ID", "")

	// Create a temp file without bead reference
	dir := t.TempDir()
	path := filepath.Join(dir, "no-bead.md")
	os.WriteFile(path, []byte("# No bead here\n"), 0644)

	// Capture stdout
	old := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	err := cmdInferBead([]string{path})

	w.Close()
	os.Stdout = old

	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	buf := make([]byte, 256)
	n, _ := r.Read(buf)
	got := string(buf[:n])
	if got != "\n" {
		t.Errorf("cmdInferBead no match: got %q, want %q", got, "\n")
	}
}

func TestFindBeadArtifact_NotExist(t *testing.T) {
	result := findBeadArtifact("iv-xxx", "/nonexistent/dir")
	if result != "" {
		t.Errorf("expected empty for nonexistent dir, got %q", result)
	}
}

func TestFindBeadArtifact_Match(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "plan.md")
	os.WriteFile(path, []byte("**Bead:** iv-test1\n\nPlan content"), 0644)

	result := findBeadArtifact("iv-test1", dir)
	if result != path {
		t.Errorf("findBeadArtifact = %q, want %q", result, path)
	}
}

func TestFindBeadArtifact_NoMatch(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "plan.md")
	os.WriteFile(path, []byte("**Bead:** iv-other\n"), 0644)

	result := findBeadArtifact("iv-test1", dir)
	if result != "" {
		t.Errorf("findBeadArtifact should not match, got %q", result)
	}
}

func TestFindBeadArtifact_WordBoundary(t *testing.T) {
	dir := t.TempDir()
	// iv-abc should NOT match iv-abcdef
	path := filepath.Join(dir, "plan.md")
	os.WriteFile(path, []byte("**Bead:** iv-abcdef\n"), 0644)

	result := findBeadArtifact("iv-abc", dir)
	if result != "" {
		t.Errorf("findBeadArtifact should not match substring, got %q", result)
	}
}

func TestNextStep_AllPhasesUnique(t *testing.T) {
	// All 9 canonical phases should have a defined step (not default "brainstorm")
	canonicalPhases := []string{
		"brainstorm", "brainstorm-reviewed", "strategized",
		"planned", "plan-reviewed", "executing",
		"shipping", "reflect", "done",
	}
	for _, p := range canonicalPhases {
		step := nextStep(p)
		if p != "done" && step == "brainstorm" && p != "" {
			// Only unknown/empty phases should map to brainstorm
			// brainstorm phase mapping to strategy is correct
			if p == "brainstorm" {
				continue // brainstorm -> strategy is correct
			}
			t.Errorf("canonical phase %q unexpectedly maps to default 'brainstorm'", p)
		}
	}
}
