package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestDefaultWatchdogConfig(t *testing.T) {
	cfg := defaultWatchdogConfig()
	if cfg.StaleTTL != 600*time.Second {
		t.Errorf("StaleTTL: got %s, want 600s", cfg.StaleTTL)
	}
	if cfg.MaxUnclaims != 2 {
		t.Errorf("MaxUnclaims: got %d, want 2", cfg.MaxUnclaims)
	}
	if cfg.MaxRetries != 3 {
		t.Errorf("MaxRetries: got %d, want 3", cfg.MaxRetries)
	}
	if cfg.CircuitThresh != 3 {
		t.Errorf("CircuitThresh: got %d, want 3", cfg.CircuitThresh)
	}
	if cfg.FactoryThresh != 2 {
		t.Errorf("FactoryThresh: got %d, want 2", cfg.FactoryThresh)
	}
}

func TestEscalationTierString(t *testing.T) {
	tests := []struct {
		tier escalationTier
		want string
	}{
		{tierAutoRetry, "auto-retry"},
		{tierQuarantine, "quarantine"},
		{tierCircuitBreak, "circuit-breaker"},
		{tierFactoryPause, "factory-pause"},
		{escalationTier(99), "unknown"},
	}
	for _, tt := range tests {
		if got := tt.tier.String(); got != tt.want {
			t.Errorf("tier %d: got %q, want %q", tt.tier, got, tt.want)
		}
	}
}

func TestDetermineTier(t *testing.T) {
	cfg := defaultWatchdogConfig()

	tests := []struct {
		name         string
		failureClass string
		attempts     int
		want         escalationTier
	}{
		{"retriable first attempt", "retriable", 0, tierAutoRetry},
		{"retriable second attempt", "retriable", 1, tierAutoRetry},
		{"retriable at max retries", "retriable", 3, tierQuarantine},
		{"retriable over max retries", "retriable", 5, tierQuarantine},
		{"spec_blocked always quarantine", "spec_blocked", 0, tierQuarantine},
		{"env_blocked always quarantine", "env_blocked", 0, tierQuarantine},
		{"spec_blocked with retries", "spec_blocked", 2, tierQuarantine},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := determineTier(tt.failureClass, tt.attempts, "test-bead", cfg)
			if got != tt.want {
				t.Errorf("determineTier(%q, %d): got %s, want %s",
					tt.failureClass, tt.attempts, got, tt.want)
			}
		})
	}
}

func TestSanitizeFilename(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"simple", "simple"},
		{"has/slash", "has_slash"},
		{"has:colon", "has_colon"},
		{"has spaces", "has_spaces"},
		{"a/b:c d", "a_b_c_d"},
	}
	for _, tt := range tests {
		if got := sanitizeFilename(tt.input); got != tt.want {
			t.Errorf("sanitizeFilename(%q): got %q, want %q", tt.input, got, tt.want)
		}
	}
}

func TestIsFactoryPaused(t *testing.T) {
	// Use temp dir as HOME
	tmpDir := t.TempDir()
	origHome := os.Getenv("HOME")
	os.Setenv("HOME", tmpDir)
	defer os.Setenv("HOME", origHome)

	// Not paused initially
	if IsFactoryPaused() {
		t.Error("factory should not be paused initially")
	}

	// Pause factory
	pauseFactory()

	// Now should be paused
	if !IsFactoryPaused() {
		t.Error("factory should be paused after pauseFactory()")
	}
}

func TestIsAgentPaused(t *testing.T) {
	tmpDir := t.TempDir()
	origHome := os.Getenv("HOME")
	os.Setenv("HOME", tmpDir)
	defer os.Setenv("HOME", origHome)

	agent := "test-agent-123"

	if IsAgentPaused(agent) {
		t.Error("agent should not be paused initially")
	}

	pauseAgentDispatch(agent)

	if !IsAgentPaused(agent) {
		t.Error("agent should be paused after pauseAgentDispatch()")
	}

	// Different agent should not be paused
	if IsAgentPaused("other-agent") {
		t.Error("other agent should not be paused")
	}
}

func TestCheckCircuitBreaker(t *testing.T) {
	tmpDir := t.TempDir()
	origHome := os.Getenv("HOME")
	os.Setenv("HOME", tmpDir)
	defer os.Setenv("HOME", origHome)

	cfg := defaultWatchdogConfig()
	agent := "agent-cb-test"

	// No quarantines — should not trip
	if checkCircuitBreaker(agent, cfg) {
		t.Error("circuit breaker should not trip with no quarantines")
	}

	// Empty agent — should not trip
	if checkCircuitBreaker("", cfg) {
		t.Error("circuit breaker should not trip for empty agent")
	}

	// Write 3 quarantine records (threshold)
	logPath := filepath.Join(tmpDir, ".clavain", "quarantine-log.jsonl")
	_ = os.MkdirAll(filepath.Dir(logPath), 0o755)
	f, _ := os.Create(logPath)
	now := time.Now().Unix()
	for i := 0; i < 3; i++ {
		rec := quarantineRecord{
			BeadID:    "bead-" + string(rune('a'+i)),
			Agent:     agent,
			Timestamp: now - int64(i*60), // spread over 3 minutes
		}
		data, _ := json.Marshal(rec)
		f.Write(append(data, '\n'))
	}
	f.Close()

	if !checkCircuitBreaker(agent, cfg) {
		t.Error("circuit breaker should trip with 3 quarantines")
	}

	// Different agent should not trip
	if checkCircuitBreaker("other-agent", cfg) {
		t.Error("circuit breaker should not trip for different agent")
	}
}

func TestSweepResultJSON(t *testing.T) {
	result := sweepResult{
		Timestamp:    time.Now().UTC(),
		BeadsChecked: 5,
		StaleFound:   2,
		Skipped:      1,
		Actions: []sweepAction{
			{
				BeadID:       "Demarch-test.1",
				FailureClass: "retriable",
				Tier:         tierAutoRetry,
				Action:       "released for auto-retry",
				Reason:       "stale 700s",
			},
		},
	}

	data, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded sweepResult
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.BeadsChecked != 5 {
		t.Errorf("BeadsChecked: got %d, want 5", decoded.BeadsChecked)
	}
	if len(decoded.Actions) != 1 {
		t.Fatalf("Actions: got %d, want 1", len(decoded.Actions))
	}
	if decoded.Actions[0].Tier != tierAutoRetry {
		t.Errorf("Tier: got %d, want %d", decoded.Actions[0].Tier, tierAutoRetry)
	}
}
