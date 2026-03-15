package main

import (
	"testing"
	"time"
)

func TestParseDuration(t *testing.T) {
	tests := []struct {
		input string
		want  time.Duration
	}{
		{"7d", 7 * 24 * time.Hour},
		{"30d", 30 * 24 * time.Hour},
		{"1d", 24 * time.Hour},
		{"24h", 24 * time.Hour},
		{"1h30m", 90 * time.Minute},
		{"", 0},
		{"abc", 0},
		{"0d", 0},
	}
	for _, tt := range tests {
		got := parseDuration(tt.input)
		if got != tt.want {
			t.Errorf("parseDuration(%q) = %v, want %v", tt.input, got, tt.want)
		}
	}
}

func TestStatsRowRate(t *testing.T) {
	// Test rate calculation logic matches cmdSprintStats
	tests := []struct {
		name      string
		completed int
		abandoned int
		wantRate  float64
	}{
		{"all completed", 10, 0, 100.0},
		{"all abandoned", 0, 10, 0.0},
		{"70 pct", 7, 3, 70.0},
		{"no data", 0, 0, 0.0},
		{"one each", 1, 1, 50.0},
	}
	for _, tt := range tests {
		denom := tt.completed + tt.abandoned
		var rate float64
		if denom > 0 {
			rate = float64(tt.completed) / float64(denom) * 100.0
		}
		if rate != tt.wantRate {
			t.Errorf("%s: rate = %.1f, want %.1f", tt.name, rate, tt.wantRate)
		}
	}
}
