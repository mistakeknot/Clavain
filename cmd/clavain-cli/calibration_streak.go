package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const calibrationStreakTarget = 10

var calibrationLoopNames = []string{"routing", "gate_threshold", "phase_cost"}

var calibrationLoopStatusLabels = map[string]string{
	"routing":        "routing",
	"gate_threshold": "gate",
	"phase_cost":     "phase",
}

type CalibrationStreakState struct {
	SchemaVersion    int                              `json:"schema_version"`
	Target           int                              `json:"target"`
	AggregateCurrent int                              `json:"aggregate_current"`
	AggregateBest    int                              `json:"aggregate_best"`
	UpdatedAt        string                           `json:"updated_at,omitempty"`
	Loops            map[string]CalibrationLoopStreak `json:"loops"`
}

type CalibrationLoopStreak struct {
	Current          int    `json:"current"`
	Best             int    `json:"best"`
	LastEvent        string `json:"last_event,omitempty"`
	LastEventAt      string `json:"last_event_at,omitempty"`
	LastManualAt     string `json:"last_manual_at,omitempty"`
	LastManualReason string `json:"last_manual_reason,omitempty"`
}

func defaultCalibrationStreak() CalibrationStreakState {
	state := CalibrationStreakState{
		SchemaVersion: 1,
		Target:        calibrationStreakTarget,
		Loops:         make(map[string]CalibrationLoopStreak, len(calibrationLoopNames)),
	}
	for _, loop := range calibrationLoopNames {
		state.Loops[loop] = CalibrationLoopStreak{}
	}
	state.recomputeAggregate()
	return state
}

func calibrationStreakPath() string {
	return filepath.Join(projectRoot(), ".clavain", "calibration-streak.json")
}

func cmdCalibrationStreak(args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("calibration-streak: expected subcommand: record-session-end, record-manual, status")
	}

	switch args[0] {
	case "record-session-end":
		return recordCalibrationSessionEnd(time.Now().UTC())
	case "record-manual":
		if len(args) < 2 {
			return fmt.Errorf("calibration-streak record-manual: expected loop name")
		}
		reason := "manual-intervention"
		if len(args) > 2 {
			reason = strings.Join(args[2:], " ")
		}
		return recordCalibrationManual(args[1], reason, time.Now().UTC())
	case "status":
		state, err := loadCalibrationStreak()
		if err != nil {
			return err
		}
		if len(args) > 1 && args[1] == "--json" {
			data, err := json.MarshalIndent(state, "", "  ")
			if err != nil {
				return fmt.Errorf("calibration-streak status: marshal: %w", err)
			}
			fmt.Println(string(data))
			return nil
		}
		fmt.Println(calibrationStreakStatusLine(state))
		return nil
	case "help", "--help", "-h":
		fmt.Println("usage: clavain-cli calibration-streak <record-session-end|record-manual LOOP [REASON]|status [--json]>")
		fmt.Println("loops: routing, gate_threshold, phase_cost")
		return nil
	default:
		return fmt.Errorf("calibration-streak: unknown subcommand %q", args[0])
	}
}

func recordCalibrationSessionEnd(now time.Time) error {
	state, err := loadCalibrationStreak()
	if err != nil {
		return err
	}
	state.applySessionEnd(now, "session-end")
	return saveCalibrationStreak(state)
}

func recordCalibrationManual(loopName string, reason string, now time.Time) error {
	loop, err := normalizeCalibrationLoop(loopName)
	if err != nil {
		return err
	}
	state, err := loadCalibrationStreak()
	if err != nil {
		return err
	}
	state.applyManualIntervention(loop, now, reason)
	return saveCalibrationStreak(state)
}

func loadCalibrationStreak() (CalibrationStreakState, error) {
	path := calibrationStreakPath()
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return defaultCalibrationStreak(), nil
		}
		return CalibrationStreakState{}, fmt.Errorf("calibration-streak: read %s: %w", path, err)
	}
	var state CalibrationStreakState
	if err := json.Unmarshal(data, &state); err != nil {
		return CalibrationStreakState{}, fmt.Errorf("calibration-streak: parse %s: %w", path, err)
	}
	state.ensureDefaults()
	return state, nil
}

func saveCalibrationStreak(state CalibrationStreakState) error {
	state.ensureDefaults()
	path := calibrationStreakPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("calibration-streak: create dir: %w", err)
	}
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return fmt.Errorf("calibration-streak: marshal: %w", err)
	}
	data = append(data, '\n')
	tmp, err := os.CreateTemp(filepath.Dir(path), ".calibration-streak-*.tmp")
	if err != nil {
		return fmt.Errorf("calibration-streak: temp file: %w", err)
	}
	tmpName := tmp.Name()
	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()
		_ = os.Remove(tmpName)
		return fmt.Errorf("calibration-streak: write temp file: %w", err)
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpName)
		return fmt.Errorf("calibration-streak: close temp file: %w", err)
	}
	if err := os.Rename(tmpName, path); err != nil {
		_ = os.Remove(tmpName)
		return fmt.Errorf("calibration-streak: replace state file: %w", err)
	}
	return nil
}

func (s *CalibrationStreakState) ensureDefaults() {
	if s.SchemaVersion == 0 {
		s.SchemaVersion = 1
	}
	if s.Target == 0 {
		s.Target = calibrationStreakTarget
	}
	if s.Loops == nil {
		s.Loops = make(map[string]CalibrationLoopStreak, len(calibrationLoopNames))
	}
	for _, loop := range calibrationLoopNames {
		if _, ok := s.Loops[loop]; !ok {
			s.Loops[loop] = CalibrationLoopStreak{}
		}
	}
	s.recomputeAggregate()
}

func (s *CalibrationStreakState) applySessionEnd(now time.Time, event string) {
	s.ensureDefaults()
	stamp := now.UTC().Format(time.RFC3339)
	if event == "" {
		event = "session-end"
	}
	for _, loop := range calibrationLoopNames {
		loopState := s.Loops[loop]
		loopState.Current++
		if loopState.Current > loopState.Best {
			loopState.Best = loopState.Current
		}
		loopState.LastEvent = event
		loopState.LastEventAt = stamp
		s.Loops[loop] = loopState
	}
	s.UpdatedAt = stamp
	s.recomputeAggregate()
}

func (s *CalibrationStreakState) applyManualIntervention(loop string, now time.Time, reason string) {
	s.ensureDefaults()
	loop, err := normalizeCalibrationLoop(loop)
	if err != nil {
		return
	}
	stamp := now.UTC().Format(time.RFC3339)
	if reason == "" {
		reason = "manual-intervention"
	}
	loopState := s.Loops[loop]
	loopState.Current = 0
	loopState.LastEvent = "manual-intervention"
	loopState.LastEventAt = stamp
	loopState.LastManualAt = stamp
	loopState.LastManualReason = reason
	s.Loops[loop] = loopState
	s.UpdatedAt = stamp
	s.recomputeAggregate()
}

func (s *CalibrationStreakState) recomputeAggregate() {
	if s.Target == 0 {
		s.Target = calibrationStreakTarget
	}
	if len(s.Loops) == 0 {
		s.AggregateCurrent = 0
		return
	}
	minCurrent := -1
	for _, loop := range calibrationLoopNames {
		loopState := s.Loops[loop]
		if minCurrent < 0 || loopState.Current < minCurrent {
			minCurrent = loopState.Current
		}
	}
	if minCurrent < 0 {
		minCurrent = 0
	}
	s.AggregateCurrent = minCurrent
	if s.AggregateCurrent > s.AggregateBest {
		s.AggregateBest = s.AggregateCurrent
	}
}

func calibrationStreakStatusLine(state CalibrationStreakState) string {
	state.ensureDefaults()
	parts := make([]string, 0, len(calibrationLoopNames))
	for _, loop := range calibrationLoopNames {
		label := calibrationLoopStatusLabels[loop]
		if label == "" {
			label = loop
		}
		parts = append(parts, fmt.Sprintf("%s=%d", label, state.Loops[loop].Current))
	}
	line := fmt.Sprintf("A:L3 no-touch %d/%d (%s; best=%d", state.AggregateCurrent, state.Target, strings.Join(parts, " "), state.AggregateBest)
	if loop, reason := latestManualReset(state); loop != "" {
		line += fmt.Sprintf("; reset:%s %s", loop, reason)
	}
	line += ")"
	return line
}

func latestManualReset(state CalibrationStreakState) (string, string) {
	var latestLoop, latestReason, latestAt string
	for _, loop := range calibrationLoopNames {
		loopState := state.Loops[loop]
		if loopState.LastManualAt == "" {
			continue
		}
		if latestAt == "" || loopState.LastManualAt > latestAt {
			latestAt = loopState.LastManualAt
			latestLoop = loop
			latestReason = loopState.LastManualReason
		}
	}
	return latestLoop, latestReason
}

func normalizeCalibrationLoop(loop string) (string, error) {
	switch strings.TrimSpace(strings.ToLower(loop)) {
	case "routing", "route":
		return "routing", nil
	case "gate", "gate_threshold", "gate-threshold", "gate_tier", "gate-tier", "gate_tiers", "gate-tiers":
		return "gate_threshold", nil
	case "phase", "phase_cost", "phase-cost", "phase_costs", "phase-costs", "cost":
		return "phase_cost", nil
	default:
		return "", fmt.Errorf("calibration-streak: unknown loop %q (want routing, gate_threshold, or phase_cost)", loop)
	}
}
