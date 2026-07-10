package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"golang.org/x/sys/unix"
)

const (
	calibrationStreakSchemaVersion = 2
	calibrationStreakTarget        = 10

	CalibrationOutcomeUpdated   = "updated"
	CalibrationOutcomeValidNoop = "valid_noop"
	CalibrationOutcomeFailed    = "failed"
	CalibrationOutcomeTimeout   = "timeout"
)

var calibrationLoopNames = []string{"routing", "gate_threshold", "phase_cost"}

var calibrationLoopStatusLabels = map[string]string{
	"routing":        "routing",
	"gate_threshold": "gate",
	"phase_cost":     "phase",
}

type CalibrationStreakState struct {
	SchemaVersion    int                              `json:"schema_version"`
	Target           int                              `json:"target"`
	ProofEpoch       string                           `json:"proof_epoch"`
	ProofStartedAt   string                           `json:"proof_started_at"`
	MigrationNote    string                           `json:"migration_note,omitempty"`
	NextSequence     uint64                           `json:"next_sequence"`
	AggregateCurrent int                              `json:"aggregate_current"`
	AggregateBest    int                              `json:"aggregate_best"`
	UpdatedAt        string                           `json:"updated_at,omitempty"`
	Loops            map[string]CalibrationLoopStreak `json:"loops"`
	Receipts         []CalibrationReceipt             `json:"receipts"`
	ManualResets     []CalibrationManualReset         `json:"manual_resets,omitempty"`
}

type CalibrationLoopStreak struct {
	Current          int    `json:"current"`
	Best             int    `json:"best"`
	LastEvent        string `json:"last_event,omitempty"`
	LastEventAt      string `json:"last_event_at,omitempty"`
	LastManualAt     string `json:"last_manual_at,omitempty"`
	LastManualReason string `json:"last_manual_reason,omitempty"`
}

type CalibrationReceipt struct {
	Sequence  uint64                            `json:"sequence,omitempty"`
	SessionID string                            `json:"session_id"`
	SprintID  string                            `json:"sprint_id"`
	Host      string                            `json:"host"`
	Timestamp string                            `json:"timestamp"`
	Loops     map[string]CalibrationLoopReceipt `json:"loops"`
}

type CalibrationLoopReceipt struct {
	Outcome       string `json:"outcome"`
	BeforeHash    string `json:"before_hash"`
	AfterHash     string `json:"after_hash"`
	EvidenceCount int    `json:"evidence_count"`
	Detail        string `json:"detail"`
}

type CalibrationManualReset struct {
	Sequence  uint64 `json:"sequence"`
	Loop      string `json:"loop"`
	Timestamp string `json:"timestamp"`
	Reason    string `json:"reason"`
}

type calibrationHistoryEvent struct {
	sequence uint64
	receipt  *CalibrationReceipt
	manual   *CalibrationManualReset
}

func newCalibrationStreak(now time.Time, note string) CalibrationStreakState {
	stamp := now.UTC().Format(time.RFC3339Nano)
	state := CalibrationStreakState{
		SchemaVersion:  calibrationStreakSchemaVersion,
		Target:         calibrationStreakTarget,
		ProofEpoch:     newCalibrationProofEpoch(now),
		ProofStartedAt: stamp,
		MigrationNote:  note,
		Loops:          make(map[string]CalibrationLoopStreak, len(calibrationLoopNames)),
		Receipts:       []CalibrationReceipt{},
	}
	for _, loop := range calibrationLoopNames {
		state.Loops[loop] = CalibrationLoopStreak{}
	}
	return state
}

func newCalibrationProofEpoch(now time.Time) string {
	random := make([]byte, 12)
	if _, err := rand.Read(random); err == nil {
		return "v2-" + hex.EncodeToString(random)
	}
	return fmt.Sprintf("v2-%d-%d", now.UTC().UnixNano(), os.Getpid())
}

func calibrationStreakPathAt(root string) string {
	return filepath.Join(root, ".clavain", "calibration-streak.json")
}

func calibrationProofRoot(override string) (string, error) {
	if override == "" {
		override = strings.TrimSpace(os.Getenv("CLAVAIN_CALIBRATION_ROOT"))
	}
	if override == "" {
		// Existing Clavain callers use this as their explicit project override.
		override = strings.TrimSpace(os.Getenv("SPRINT_LIB_PROJECT_DIR"))
	}
	if override != "" {
		return canonicalCalibrationDir(override)
	}

	current, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("calibration-streak: current directory: %w", err)
	}
	current, err = canonicalCalibrationDir(current)
	if err != nil {
		return "", err
	}
	for {
		metadata := filepath.Join(current, ".beads", "metadata.json")
		if info, statErr := os.Stat(metadata); statErr == nil && !info.IsDir() {
			return current, nil
		}
		parent := filepath.Dir(current)
		if parent == current {
			break
		}
		current = parent
	}
	return "", errors.New("calibration-streak: no .beads/metadata.json found; use --root or CLAVAIN_CALIBRATION_ROOT")
}

func canonicalCalibrationDir(path string) (string, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return "", fmt.Errorf("calibration-streak: resolve root %q: %w", path, err)
	}
	if resolved, evalErr := filepath.EvalSymlinks(abs); evalErr == nil {
		abs = resolved
	}
	return filepath.Clean(abs), nil
}

func cmdCalibrationStreak(args []string) error {
	if len(args) == 0 {
		return errors.New("calibration-streak: expected subcommand: record-receipt, record-manual, status, verify")
	}

	subcommand := args[0]
	rootOverride, rest, err := extractCalibrationStringFlag(args[1:], "root")
	if err != nil {
		return err
	}
	root, err := calibrationProofRoot(rootOverride)
	if err != nil {
		return err
	}

	switch subcommand {
	case "record-receipt":
		file, remaining, flagErr := extractCalibrationStringFlag(rest, "file")
		if flagErr != nil {
			return flagErr
		}
		if len(remaining) != 0 {
			return fmt.Errorf("calibration-streak record-receipt: unexpected arguments: %s", strings.Join(remaining, " "))
		}
		if file == "" {
			file = "-"
		}
		receipt, readErr := readCalibrationReceipt(file)
		if readErr != nil {
			return readErr
		}
		return recordCalibrationReceiptAt(root, receipt)
	case "record-session-end":
		return errors.New("calibration-streak record-session-end: blind counters are disabled; submit an evidence receipt with record-receipt")
	case "record-manual":
		if len(rest) < 1 {
			return errors.New("calibration-streak record-manual: expected loop name")
		}
		reason := "manual-intervention"
		if len(rest) > 1 {
			reason = strings.Join(rest[1:], " ")
		}
		return recordCalibrationManualAt(root, rest[0], reason, time.Now().UTC())
	case "status":
		jsonOutput, remaining, flagErr := extractCalibrationBoolFlag(rest, "json")
		if flagErr != nil {
			return flagErr
		}
		if len(remaining) != 0 {
			return fmt.Errorf("calibration-streak status: unexpected arguments: %s", strings.Join(remaining, " "))
		}
		state, loadErr := loadVerifiedCalibrationStreakAt(root)
		if loadErr != nil {
			return loadErr
		}
		if jsonOutput {
			data, marshalErr := json.MarshalIndent(state, "", "  ")
			if marshalErr != nil {
				return fmt.Errorf("calibration-streak status: marshal: %w", marshalErr)
			}
			fmt.Println(string(data))
			return nil
		}
		fmt.Println(calibrationStreakStatusLine(state))
		return nil
	case "verify":
		targetText, remaining, flagErr := extractCalibrationStringFlag(rest, "target")
		if flagErr != nil {
			return flagErr
		}
		if len(remaining) != 0 {
			return fmt.Errorf("calibration-streak verify: unexpected arguments: %s", strings.Join(remaining, " "))
		}
		target := calibrationStreakTarget
		if targetText != "" {
			target, flagErr = strconv.Atoi(targetText)
			if flagErr != nil || target < 1 {
				return fmt.Errorf("calibration-streak verify: invalid target %q", targetText)
			}
		}
		if verifyErr := verifyCalibrationStreakAt(root, target); verifyErr != nil {
			return verifyErr
		}
		fmt.Printf("A:L3 calibration proof verified: %d/%d\n", target, target)
		return nil
	case "help", "--help", "-h":
		printCalibrationStreakHelp()
		return nil
	default:
		return fmt.Errorf("calibration-streak: unknown subcommand %q", subcommand)
	}
}

func printCalibrationStreakHelp() {
	fmt.Println("usage: clavain-cli calibration-streak <record-receipt [--file=PATH]|record-manual LOOP [REASON]|status [--json]|verify [--target=10]> [--root=DIR]")
	fmt.Println("record-receipt reads one schema-v2 receipt from --file or stdin")
	fmt.Println("outcomes: updated, valid_noop, failed, timeout")
	fmt.Println("loops: routing, gate_threshold, phase_cost")
}

func extractCalibrationStringFlag(args []string, name string) (string, []string, error) {
	prefix := "--" + name + "="
	plain := "--" + name
	var value string
	rest := make([]string, 0, len(args))
	for i := 0; i < len(args); i++ {
		arg := args[i]
		switch {
		case strings.HasPrefix(arg, prefix):
			if value != "" {
				return "", nil, fmt.Errorf("calibration-streak: duplicate --%s", name)
			}
			value = strings.TrimPrefix(arg, prefix)
			if value == "" {
				return "", nil, fmt.Errorf("calibration-streak: --%s requires a value", name)
			}
		case arg == plain:
			if value != "" || i+1 >= len(args) {
				return "", nil, fmt.Errorf("calibration-streak: --%s requires one value", name)
			}
			i++
			value = args[i]
			if value == "" {
				return "", nil, fmt.Errorf("calibration-streak: --%s requires a value", name)
			}
		default:
			rest = append(rest, arg)
		}
	}
	return value, rest, nil
}

func extractCalibrationBoolFlag(args []string, name string) (bool, []string, error) {
	plain := "--" + name
	found := false
	rest := make([]string, 0, len(args))
	for _, arg := range args {
		if arg != plain {
			rest = append(rest, arg)
			continue
		}
		if found {
			return false, nil, fmt.Errorf("calibration-streak: duplicate --%s", name)
		}
		found = true
	}
	return found, rest, nil
}

func readCalibrationReceipt(path string) (CalibrationReceipt, error) {
	var reader io.Reader = os.Stdin
	var file *os.File
	if path != "-" {
		opened, err := os.Open(path)
		if err != nil {
			return CalibrationReceipt{}, fmt.Errorf("calibration-streak record-receipt: open %s: %w", path, err)
		}
		file = opened
		defer file.Close()
		reader = file
	}
	decoder := json.NewDecoder(reader)
	decoder.DisallowUnknownFields()
	var receipt CalibrationReceipt
	if err := decoder.Decode(&receipt); err != nil {
		return CalibrationReceipt{}, fmt.Errorf("calibration-streak record-receipt: parse receipt: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		if err == nil {
			return CalibrationReceipt{}, errors.New("calibration-streak record-receipt: receipt must contain one JSON value")
		}
		return CalibrationReceipt{}, fmt.Errorf("calibration-streak record-receipt: trailing data: %w", err)
	}
	return receipt, nil
}

func recordCalibrationReceiptAt(root string, receipt CalibrationReceipt) error {
	return withCalibrationStreakLock(root, func() error {
		state, _, err := loadCalibrationStreakUnlocked(root, time.Now().UTC())
		if err != nil {
			return err
		}
		if err := validateCalibrationCache(state); err != nil {
			return err
		}
		if err := validateCalibrationReceipt(receipt); err != nil {
			return err
		}
		for _, existing := range state.Receipts {
			if existing.SessionID == receipt.SessionID {
				return fmt.Errorf("calibration-streak: duplicate session_id %q", receipt.SessionID)
			}
			if existing.SprintID == receipt.SprintID {
				return fmt.Errorf("calibration-streak: duplicate sprint_id %q", receipt.SprintID)
			}
		}
		state.NextSequence++
		receipt.Sequence = state.NextSequence
		state.Receipts = append(state.Receipts, receipt)
		if err := refreshCalibrationCache(&state); err != nil {
			return err
		}
		return saveCalibrationStreakUnlocked(root, state)
	})
}

func recordCalibrationManualAt(root, loopName, reason string, now time.Time) error {
	loop, err := normalizeCalibrationLoop(loopName)
	if err != nil {
		return err
	}
	reason = strings.TrimSpace(reason)
	if reason == "" {
		reason = "manual-intervention"
	}
	return withCalibrationStreakLock(root, func() error {
		state, _, loadErr := loadCalibrationStreakUnlocked(root, now)
		if loadErr != nil {
			return loadErr
		}
		if cacheErr := validateCalibrationCache(state); cacheErr != nil {
			return cacheErr
		}
		state.NextSequence++
		state.ManualResets = append(state.ManualResets, CalibrationManualReset{
			Sequence:  state.NextSequence,
			Loop:      loop,
			Timestamp: now.UTC().Format(time.RFC3339Nano),
			Reason:    reason,
		})
		if cacheErr := refreshCalibrationCache(&state); cacheErr != nil {
			return cacheErr
		}
		return saveCalibrationStreakUnlocked(root, state)
	})
}

func verifyCalibrationStreakAt(root string, target int) error {
	if target < 1 {
		return fmt.Errorf("calibration-streak verify: target must be positive, got %d", target)
	}
	return withCalibrationStreakLock(root, func() error {
		state, migrated, err := loadCalibrationStreakUnlocked(root, time.Now().UTC())
		if err != nil {
			return err
		}
		if migrated {
			if err := saveCalibrationStreakUnlocked(root, state); err != nil {
				return err
			}
		}
		if err := validateCalibrationCache(state); err != nil {
			return err
		}
		if state.AggregateCurrent < target {
			return fmt.Errorf("calibration-streak verify: proof is %d/%d; %d more evidence-qualified sprints required", state.AggregateCurrent, target, target-state.AggregateCurrent)
		}
		for _, loop := range calibrationLoopNames {
			if state.Loops[loop].Current < target {
				return fmt.Errorf("calibration-streak verify: %s proof is %d/%d", loop, state.Loops[loop].Current, target)
			}
		}
		return nil
	})
}

func loadCalibrationStreakAt(root string) (CalibrationStreakState, error) {
	var state CalibrationStreakState
	err := withCalibrationStreakLock(root, func() error {
		loaded, migrated, loadErr := loadCalibrationStreakUnlocked(root, time.Now().UTC())
		if loadErr != nil {
			return loadErr
		}
		state = loaded
		if migrated {
			return saveCalibrationStreakUnlocked(root, state)
		}
		return nil
	})
	return state, err
}

func loadVerifiedCalibrationStreakAt(root string) (CalibrationStreakState, error) {
	var state CalibrationStreakState
	err := withCalibrationStreakLock(root, func() error {
		loaded, migrated, loadErr := loadCalibrationStreakUnlocked(root, time.Now().UTC())
		if loadErr != nil {
			return loadErr
		}
		if migrated {
			if saveErr := saveCalibrationStreakUnlocked(root, loaded); saveErr != nil {
				return saveErr
			}
		}
		if cacheErr := validateCalibrationCache(loaded); cacheErr != nil {
			return cacheErr
		}
		state = loaded
		return nil
	})
	return state, err
}

func loadCalibrationStreakUnlocked(root string, now time.Time) (CalibrationStreakState, bool, error) {
	path := calibrationStreakPathAt(root)
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return newCalibrationStreak(now, ""), true, nil
		}
		return CalibrationStreakState{}, false, fmt.Errorf("calibration-streak: read %s: %w", path, err)
	}
	var envelope struct {
		SchemaVersion int `json:"schema_version"`
	}
	if err := json.Unmarshal(data, &envelope); err != nil {
		return CalibrationStreakState{}, false, fmt.Errorf("calibration-streak: parse %s: %w", path, err)
	}
	if envelope.SchemaVersion == 0 || envelope.SchemaVersion == 1 {
		return newCalibrationStreak(now, "schema-v1 counters reset; receipt proof required"), true, nil
	}
	if envelope.SchemaVersion != calibrationStreakSchemaVersion {
		return CalibrationStreakState{}, false, fmt.Errorf("calibration-streak: unsupported schema_version %d", envelope.SchemaVersion)
	}
	var state CalibrationStreakState
	if err := json.Unmarshal(data, &state); err != nil {
		return CalibrationStreakState{}, false, fmt.Errorf("calibration-streak: parse %s: %w", path, err)
	}
	return state, false, nil
}

func saveCalibrationStreakUnlocked(root string, state CalibrationStreakState) error {
	path := calibrationStreakPathAt(root)
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
	defer os.Remove(tmpName)
	if err := tmp.Chmod(0o600); err != nil {
		_ = tmp.Close()
		return fmt.Errorf("calibration-streak: chmod temp file: %w", err)
	}
	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()
		return fmt.Errorf("calibration-streak: write temp file: %w", err)
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return fmt.Errorf("calibration-streak: sync temp file: %w", err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("calibration-streak: close temp file: %w", err)
	}
	if err := os.Rename(tmpName, path); err != nil {
		return fmt.Errorf("calibration-streak: replace state file: %w", err)
	}
	return nil
}

func withCalibrationStreakLock(root string, fn func() error) error {
	dir := filepath.Join(root, ".clavain")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("calibration-streak: create lock dir: %w", err)
	}
	lock, err := os.OpenFile(filepath.Join(dir, "calibration-streak.lock"), os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return fmt.Errorf("calibration-streak: open lock: %w", err)
	}
	defer lock.Close()
	if err := unix.Flock(int(lock.Fd()), unix.LOCK_EX); err != nil {
		return fmt.Errorf("calibration-streak: acquire lock: %w", err)
	}
	defer unix.Flock(int(lock.Fd()), unix.LOCK_UN) //nolint:errcheck
	return fn()
}

func validateCalibrationReceipt(receipt CalibrationReceipt) error {
	if receipt.Sequence != 0 {
		return errors.New("calibration-streak: receipt sequence is assigned by the recorder")
	}
	if strings.TrimSpace(receipt.SessionID) == "" || strings.TrimSpace(receipt.SprintID) == "" {
		return errors.New("calibration-streak: receipt requires session_id and sprint_id")
	}
	if strings.TrimSpace(receipt.Host) == "" {
		return errors.New("calibration-streak: receipt requires host")
	}
	if _, err := time.Parse(time.RFC3339Nano, receipt.Timestamp); err != nil {
		return fmt.Errorf("calibration-streak: receipt timestamp must be RFC3339: %w", err)
	}
	if len(receipt.Loops) != len(calibrationLoopNames) {
		return fmt.Errorf("calibration-streak: receipt requires exactly %d loop outcomes", len(calibrationLoopNames))
	}
	for _, loop := range calibrationLoopNames {
		result, ok := receipt.Loops[loop]
		if !ok {
			return fmt.Errorf("calibration-streak: receipt missing %s outcome", loop)
		}
		if err := validateCalibrationLoopReceipt(loop, result); err != nil {
			return err
		}
	}
	return nil
}

func validateStoredCalibrationReceipt(receipt CalibrationReceipt) error {
	sequence := receipt.Sequence
	receipt.Sequence = 0
	if sequence == 0 {
		return errors.New("calibration-streak: stored receipt has zero sequence")
	}
	return validateCalibrationReceipt(receipt)
}

func validateCalibrationLoopReceipt(loop string, result CalibrationLoopReceipt) error {
	switch result.Outcome {
	case CalibrationOutcomeUpdated:
		if result.BeforeHash == result.AfterHash {
			return fmt.Errorf("calibration-streak: %s updated outcome requires different before/after hashes", loop)
		}
	case CalibrationOutcomeValidNoop:
		if result.BeforeHash != result.AfterHash {
			return fmt.Errorf("calibration-streak: %s valid_noop requires identical before/after hashes", loop)
		}
	case CalibrationOutcomeFailed, CalibrationOutcomeTimeout:
	default:
		return fmt.Errorf("calibration-streak: %s has invalid outcome %q", loop, result.Outcome)
	}
	if strings.TrimSpace(result.BeforeHash) == "" || strings.TrimSpace(result.AfterHash) == "" {
		return fmt.Errorf("calibration-streak: %s requires before_hash and after_hash", loop)
	}
	if result.EvidenceCount < 0 {
		return fmt.Errorf("calibration-streak: %s evidence_count cannot be negative", loop)
	}
	if strings.TrimSpace(result.Detail) == "" {
		return fmt.Errorf("calibration-streak: %s requires detail", loop)
	}
	return nil
}

func validateCalibrationCache(state CalibrationStreakState) error {
	derived := state
	if err := refreshCalibrationCache(&derived); err != nil {
		return err
	}
	if state.NextSequence != derived.NextSequence ||
		state.AggregateCurrent != derived.AggregateCurrent ||
		state.AggregateBest != derived.AggregateBest ||
		state.UpdatedAt != derived.UpdatedAt {
		return errors.New("calibration-streak: tampered cached counters; receipt history does not match state")
	}
	for _, loop := range calibrationLoopNames {
		if state.Loops[loop] != derived.Loops[loop] {
			return fmt.Errorf("calibration-streak: tampered cached counters for %s", loop)
		}
	}
	return nil
}

func refreshCalibrationCache(state *CalibrationStreakState) error {
	if state.SchemaVersion != calibrationStreakSchemaVersion {
		return fmt.Errorf("calibration-streak: cannot derive schema_version %d", state.SchemaVersion)
	}
	if state.Target == 0 {
		state.Target = calibrationStreakTarget
	}
	if state.ProofEpoch == "" || state.ProofStartedAt == "" {
		return errors.New("calibration-streak: schema-v2 state missing proof epoch")
	}

	events := make([]calibrationHistoryEvent, 0, len(state.Receipts)+len(state.ManualResets))
	sequences := make(map[uint64]struct{}, cap(events))
	sessions := make(map[string]struct{}, len(state.Receipts))
	sprints := make(map[string]struct{}, len(state.Receipts))
	var maxSequence uint64
	for i := range state.Receipts {
		receipt := &state.Receipts[i]
		if err := validateStoredCalibrationReceipt(*receipt); err != nil {
			return err
		}
		if _, duplicate := sequences[receipt.Sequence]; duplicate {
			return fmt.Errorf("calibration-streak: duplicate history sequence %d", receipt.Sequence)
		}
		if _, duplicate := sessions[receipt.SessionID]; duplicate {
			return fmt.Errorf("calibration-streak: duplicate session_id %q in history", receipt.SessionID)
		}
		if _, duplicate := sprints[receipt.SprintID]; duplicate {
			return fmt.Errorf("calibration-streak: duplicate sprint_id %q in history", receipt.SprintID)
		}
		sequences[receipt.Sequence] = struct{}{}
		sessions[receipt.SessionID] = struct{}{}
		sprints[receipt.SprintID] = struct{}{}
		if receipt.Sequence > maxSequence {
			maxSequence = receipt.Sequence
		}
		events = append(events, calibrationHistoryEvent{sequence: receipt.Sequence, receipt: receipt})
	}
	for i := range state.ManualResets {
		manual := &state.ManualResets[i]
		if manual.Sequence == 0 {
			return errors.New("calibration-streak: manual reset has zero sequence")
		}
		loop, err := normalizeCalibrationLoop(manual.Loop)
		if err != nil || loop != manual.Loop {
			return fmt.Errorf("calibration-streak: invalid manual reset loop %q", manual.Loop)
		}
		if _, err := time.Parse(time.RFC3339Nano, manual.Timestamp); err != nil {
			return fmt.Errorf("calibration-streak: manual reset timestamp must be RFC3339: %w", err)
		}
		if strings.TrimSpace(manual.Reason) == "" {
			return errors.New("calibration-streak: manual reset requires reason")
		}
		if _, duplicate := sequences[manual.Sequence]; duplicate {
			return fmt.Errorf("calibration-streak: duplicate history sequence %d", manual.Sequence)
		}
		sequences[manual.Sequence] = struct{}{}
		if manual.Sequence > maxSequence {
			maxSequence = manual.Sequence
		}
		events = append(events, calibrationHistoryEvent{sequence: manual.Sequence, manual: manual})
	}
	sort.Slice(events, func(i, j int) bool { return events[i].sequence < events[j].sequence })

	loops := make(map[string]CalibrationLoopStreak, len(calibrationLoopNames))
	lastHashes := make(map[string]string, len(calibrationLoopNames))
	for _, loop := range calibrationLoopNames {
		loops[loop] = CalibrationLoopStreak{}
	}
	aggregateBest := 0
	updatedAt := ""
	for _, event := range events {
		if event.manual != nil {
			manual := event.manual
			loopState := loops[manual.Loop]
			loopState.Current = 0
			loopState.LastEvent = "manual-intervention"
			loopState.LastEventAt = manual.Timestamp
			loopState.LastManualAt = manual.Timestamp
			loopState.LastManualReason = manual.Reason
			loops[manual.Loop] = loopState
			lastHashes[manual.Loop] = ""
			updatedAt = manual.Timestamp
		} else {
			receipt := event.receipt
			for _, loop := range calibrationLoopNames {
				result := receipt.Loops[loop]
				loopState := loops[loop]
				acceptable := result.Outcome == CalibrationOutcomeUpdated || result.Outcome == CalibrationOutcomeValidNoop
				if loop == "gate_threshold" && result.EvidenceCount < calibrationStreakTarget {
					acceptable = false
				}
				drift := lastHashes[loop] != "" && result.BeforeHash != lastHashes[loop]
				switch {
				case !acceptable:
					loopState.Current = 0
					loopState.LastEvent = result.Outcome
					lastHashes[loop] = ""
				case drift:
					loopState.Current = 0
					loopState.LastEvent = "hash-drift"
					lastHashes[loop] = result.AfterHash
				default:
					loopState.Current++
					if loopState.Current > loopState.Best {
						loopState.Best = loopState.Current
					}
					loopState.LastEvent = result.Outcome
					lastHashes[loop] = result.AfterHash
				}
				loopState.LastEventAt = receipt.Timestamp
				loops[loop] = loopState
			}
			updatedAt = receipt.Timestamp
		}
		current := aggregateCalibrationCurrent(loops)
		if current > aggregateBest {
			aggregateBest = current
		}
	}

	state.NextSequence = maxSequence
	state.Loops = loops
	state.AggregateCurrent = aggregateCalibrationCurrent(loops)
	state.AggregateBest = aggregateBest
	state.UpdatedAt = updatedAt
	return nil
}

func aggregateCalibrationCurrent(loops map[string]CalibrationLoopStreak) int {
	minimum := -1
	for _, loop := range calibrationLoopNames {
		current := loops[loop].Current
		if minimum < 0 || current < minimum {
			minimum = current
		}
	}
	if minimum < 0 {
		return 0
	}
	return minimum
}

func calibrationStreakStatusLine(state CalibrationStreakState) string {
	parts := make([]string, 0, len(calibrationLoopNames))
	for _, loop := range calibrationLoopNames {
		label := calibrationLoopStatusLabels[loop]
		if label == "" {
			label = loop
		}
		parts = append(parts, fmt.Sprintf("%s=%d", label, state.Loops[loop].Current))
	}
	line := fmt.Sprintf("A:L3 receipt proof %d/%d (%s; best=%d", state.AggregateCurrent, state.Target, strings.Join(parts, " "), state.AggregateBest)
	if loop, reason := latestManualReset(state); loop != "" {
		line += fmt.Sprintf("; reset:%s %s", loop, reason)
	}
	line += ")"
	return line
}

func latestManualReset(state CalibrationStreakState) (string, string) {
	var latestLoop, latestReason string
	var latestSequence uint64
	for _, reset := range state.ManualResets {
		if reset.Sequence > latestSequence {
			latestSequence = reset.Sequence
			latestLoop = reset.Loop
			latestReason = reset.Reason
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
