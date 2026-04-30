package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestCalibrationStreakSessionEndIncrementsAllLoopsAndAggregate(t *testing.T) {
	state := defaultCalibrationStreak()
	now := time.Date(2026, 4, 30, 16, 0, 0, 0, time.UTC)

	state.applySessionEnd(now, "session-end")
	if state.AggregateCurrent != 1 {
		t.Fatalf("AggregateCurrent after first clean SessionEnd = %d, want 1", state.AggregateCurrent)
	}
	for _, loop := range calibrationLoopNames {
		got := state.Loops[loop]
		if got.Current != 1 {
			t.Fatalf("%s current after first clean SessionEnd = %d, want 1", loop, got.Current)
		}
		if got.Best != 1 {
			t.Fatalf("%s best after first clean SessionEnd = %d, want 1", loop, got.Best)
		}
		if got.LastEvent != "session-end" {
			t.Fatalf("%s last event = %q, want session-end", loop, got.LastEvent)
		}
	}

	state.applySessionEnd(now.Add(time.Hour), "session-end")
	if state.AggregateCurrent != 2 {
		t.Fatalf("AggregateCurrent after second clean SessionEnd = %d, want 2", state.AggregateCurrent)
	}
	if state.Target != 10 {
		t.Fatalf("Target = %d, want 10", state.Target)
	}
}

func TestCalibrationStreakManualInterventionResetsOnlyTargetLoop(t *testing.T) {
	state := defaultCalibrationStreak()
	now := time.Date(2026, 4, 30, 16, 0, 0, 0, time.UTC)
	state.applySessionEnd(now, "session-end")
	state.applySessionEnd(now.Add(time.Hour), "session-end")

	state.applyManualIntervention("phase_cost", now.Add(2*time.Hour), "reflect-command")
	if state.Loops["phase_cost"].Current != 0 {
		t.Fatalf("phase_cost current after manual reset = %d, want 0", state.Loops["phase_cost"].Current)
	}
	if state.Loops["gate_threshold"].Current != 2 || state.Loops["routing"].Current != 2 {
		t.Fatalf("manual phase_cost reset should not reset other loops: %+v", state.Loops)
	}
	if state.AggregateCurrent != 0 {
		t.Fatalf("AggregateCurrent after one loop reset = %d, want 0", state.AggregateCurrent)
	}
	if state.Loops["phase_cost"].LastManualReason != "reflect-command" {
		t.Fatalf("LastManualReason = %q", state.Loops["phase_cost"].LastManualReason)
	}

	state.applySessionEnd(now.Add(3*time.Hour), "session-end")
	if state.Loops["phase_cost"].Current != 1 {
		t.Fatalf("phase_cost current after next clean SessionEnd = %d, want 1", state.Loops["phase_cost"].Current)
	}
	if state.AggregateCurrent != 1 {
		t.Fatalf("AggregateCurrent after reset recovery = %d, want 1", state.AggregateCurrent)
	}
}

func TestCalibrationStreakRecordSessionEndPersistsState(t *testing.T) {
	tmp := t.TempDir()
	t.Setenv("SPRINT_LIB_PROJECT_DIR", tmp)
	now := time.Date(2026, 4, 30, 16, 0, 0, 0, time.UTC)

	if err := recordCalibrationSessionEnd(now); err != nil {
		t.Fatalf("recordCalibrationSessionEnd: %v", err)
	}

	path := calibrationStreakPath()
	if path != filepath.Join(tmp, ".clavain", "calibration-streak.json") {
		t.Fatalf("calibrationStreakPath = %q", path)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read persisted streak file: %v", err)
	}
	var state CalibrationStreakState
	if err := json.Unmarshal(data, &state); err != nil {
		t.Fatalf("parse persisted streak file: %v", err)
	}
	if state.AggregateCurrent != 1 || state.Loops["routing"].Current != 1 || state.Loops["phase_cost"].Current != 1 {
		t.Fatalf("persisted state did not record clean SessionEnd for all loops: %+v", state)
	}
}

func TestCalibrationStreakStatusLineShowsAggregateAndLoopBreakdown(t *testing.T) {
	state := defaultCalibrationStreak()
	now := time.Date(2026, 4, 30, 16, 0, 0, 0, time.UTC)
	state.applySessionEnd(now, "session-end")
	state.applyManualIntervention("routing", now.Add(time.Hour), "manual-calibrate")

	line := calibrationStreakStatusLine(state)
	for _, want := range []string{
		"A:L3 no-touch 0/10",
		"routing=0",
		"gate=1",
		"phase=1",
		"reset:routing manual-calibrate",
	} {
		if !strings.Contains(line, want) {
			t.Fatalf("status line %q missing %q", line, want)
		}
	}
}
