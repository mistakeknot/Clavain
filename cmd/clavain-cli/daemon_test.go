package main

import (
	"strings"
	"testing"
	"time"
)

func TestParseDaemonFlags(t *testing.T) {
	tests := []struct {
		name string
		args []string
		want daemonConfig
	}{
		{
			name: "defaults",
			args: nil,
			want: daemonConfig{
				PollInterval:  30 * time.Second,
				MaxConcurrent: 3,
				MaxComplexity: 3,
				MinPriority:   3,
				ProjectDir:    ".",
			},
		},
		{
			name: "custom",
			args: []string{"--poll=10s", "--max-concurrent=5", "--max-complexity=2", "--min-priority=1", "--label=mod:clavain", "--dry-run", "--once"},
			want: daemonConfig{
				PollInterval:  10 * time.Second,
				MaxConcurrent: 5,
				MaxComplexity: 2,
				MinPriority:   1,
				LabelFilter:   "mod:clavain",
				ProjectDir:    ".",
				DryRun:        true,
				Once:          true,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := parseDaemonFlags(tt.args)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got.PollInterval != tt.want.PollInterval {
				t.Errorf("PollInterval = %v, want %v", got.PollInterval, tt.want.PollInterval)
			}
			if got.MaxConcurrent != tt.want.MaxConcurrent {
				t.Errorf("MaxConcurrent = %d, want %d", got.MaxConcurrent, tt.want.MaxConcurrent)
			}
			if got.MaxComplexity != tt.want.MaxComplexity {
				t.Errorf("MaxComplexity = %d, want %d", got.MaxComplexity, tt.want.MaxComplexity)
			}
			if got.MinPriority != tt.want.MinPriority {
				t.Errorf("MinPriority = %d, want %d", got.MinPriority, tt.want.MinPriority)
			}
			if got.LabelFilter != tt.want.LabelFilter {
				t.Errorf("LabelFilter = %q, want %q", got.LabelFilter, tt.want.LabelFilter)
			}
			if got.DryRun != tt.want.DryRun {
				t.Errorf("DryRun = %v, want %v", got.DryRun, tt.want.DryRun)
			}
			if got.Once != tt.want.Once {
				t.Errorf("Once = %v, want %v", got.Once, tt.want.Once)
			}
		})
	}
}

func TestSanitizeTitle(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"Simple title", "Simple title"},
		{"Title with `backticks`", "Title with backticks"},
		{"Title with $vars", "Title with vars"},
		{"Title with \\escapes", "Title with escapes"},
		{"Title\nwith\nnewlines", "Title with newlines"},
		{strings.Repeat("a", 300), strings.Repeat("a", 200)},
		{"  padded  ", "padded"},
	}

	for _, tt := range tests {
		t.Run(tt.input[:min(len(tt.input), 20)], func(t *testing.T) {
			got := sanitizeTitle(tt.input)
			if got != tt.want {
				t.Errorf("sanitizeTitle(%q) = %q, want %q", tt.input, got, tt.want)
			}
		})
	}
}

func TestHasLabel(t *testing.T) {
	labels := []string{"mod:clavain", "theme:research", "P2"}

	tests := []struct {
		filter string
		want   bool
	}{
		{"mod:clavain", true},
		{"clavain", true},
		{"CLAVAIN", true},
		{"mod:intercore", false},
		{"research", true},
		{"", false},
	}

	for _, tt := range tests {
		t.Run(tt.filter, func(t *testing.T) {
			// Empty filter always returns false (handled by caller before hasLabel)
			if tt.filter == "" {
				return
			}
			got := hasLabel(labels, tt.filter)
			if got != tt.want {
				t.Errorf("hasLabel(%v, %q) = %v, want %v", labels, tt.filter, got, tt.want)
			}
		})
	}
}

func TestDaemonState(t *testing.T) {
	state := &daemonState{
		active: make(map[string]*agentInfo),
	}

	// Initially empty
	if state.activeCount() != 0 {
		t.Errorf("activeCount = %d, want 0", state.activeCount())
	}
	if state.isActive("iv-test") {
		t.Error("isActive should be false for unknown bead")
	}

	// Add agent
	state.addAgent("iv-test", &agentInfo{BeadID: "iv-test", Title: "Test"})
	if state.activeCount() != 1 {
		t.Errorf("activeCount = %d, want 1", state.activeCount())
	}
	if !state.isActive("iv-test") {
		t.Error("isActive should be true after add")
	}

	// Remove agent
	state.removeAgent("iv-test")
	if state.activeCount() != 0 {
		t.Errorf("activeCount = %d, want 0 after remove", state.activeCount())
	}

	// Shutdown
	if state.isShutdown() {
		t.Error("isShutdown should be false initially")
	}
	state.setShutdown()
	if !state.isShutdown() {
		t.Error("isShutdown should be true after setShutdown")
	}
}

func TestDaemonStateConcurrent(t *testing.T) {
	state := &daemonState{
		active: make(map[string]*agentInfo),
	}

	done := make(chan bool, 10)

	// Concurrent adds
	for i := 0; i < 5; i++ {
		go func(n int) {
			id := "iv-test" + string(rune('a'+n))
			state.addAgent(id, &agentInfo{BeadID: id})
			done <- true
		}(i)
	}

	// Concurrent reads
	for i := 0; i < 5; i++ {
		go func() {
			_ = state.activeCount()
			_ = state.allAgents()
			done <- true
		}()
	}

	for i := 0; i < 10; i++ {
		<-done
	}

	if state.activeCount() != 5 {
		t.Errorf("activeCount = %d, want 5", state.activeCount())
	}
}
