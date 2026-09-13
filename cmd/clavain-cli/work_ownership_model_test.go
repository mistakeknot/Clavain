package main

// This file contains a fixture-only ownership reference model. Everything is
// compiled exclusively into tests. Its serialized fake authority demonstrates
// state-machine expectations; it cannot qualify Beads release serialization,
// native confinement, or production implementation admission.

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"
	"sync"
)

type ownershipState string

const (
	ownershipPending  ownershipState = "pending"
	ownershipActive   ownershipState = "active"
	ownershipUnknown  ownershipState = "unknown"
	ownershipDraining ownershipState = "draining"
	ownershipReleased ownershipState = "released"
)

type ownershipCrashPoint string

const (
	crashAfterPendingAppend     ownershipCrashPoint = "after-pending-append"
	crashAfterAttributionEffect ownershipCrashPoint = "after-attribution-before-receipt"
	crashAfterClaimEffect       ownershipCrashPoint = "after-claim-before-receipt"
	crashAfterReleaseEffect     ownershipCrashPoint = "after-release-before-receipt"
)

var errOwnershipSimulatedCrash = errors.New("simulated ownership process crash")

type ownershipKey struct {
	TrackerUUID string `json:"tracker_uuid"`
	TaskID      string `json:"task_id"`
}

func canonicalOwnershipKey(key ownershipKey) (ownershipKey, error) {
	if !workUUIDPattern.MatchString(key.TrackerUUID) {
		return ownershipKey{}, errors.New("tracker UUID must be an exact UUID")
	}
	if key.TaskID == "" || strings.TrimSpace(key.TaskID) != key.TaskID {
		return ownershipKey{}, errors.New("task ID must be exact and nonempty")
	}
	key.TrackerUUID = strings.ToLower(key.TrackerUUID)
	return key, nil
}

func (k ownershipKey) mapKey() string { return k.TrackerUUID + "\x00" + k.TaskID }

type ownershipAcquireRequest struct {
	Key        ownershipKey
	Endpoint   string
	BindingID  string
	SessionID  string
	Scope      string
	Generation uint64
	CrashAt    ownershipCrashPoint
}

type ownershipReleaseRequest struct {
	Key        ownershipKey
	BindingID  string
	Generation uint64
	CrashAt    ownershipCrashPoint
}

type ownershipChildRequest struct {
	Key        ownershipKey
	ChildID    string
	BindingID  string
	SessionID  string
	Scope      string
	Generation uint64
}

type ownershipEvent struct {
	Version    int          `json:"version"`
	ID         string       `json:"id"`
	Kind       string       `json:"kind"`
	Key        ownershipKey `json:"key,omitempty"`
	Endpoint   string       `json:"endpoint,omitempty"`
	BindingID  string       `json:"binding_id,omitempty"`
	SessionID  string       `json:"session_id,omitempty"`
	Scope      string       `json:"scope,omitempty"`
	Generation uint64       `json:"generation,omitempty"`
	ChildID    string       `json:"child_id,omitempty"`
	Cause      string       `json:"cause,omitempty"`
}

type ownershipRecord struct {
	Key                 ownershipKey
	State               ownershipState
	Endpoint            string
	BindingID           string
	SessionID           string
	Scope               string
	Generation          uint64
	AttributionVerified bool
	ClaimVerified       bool
	UnsafeExternalState bool
	DrainRequested      bool
	ResumeState         ownershipState
	Children            map[string]ownershipChildRequest
}

type ownershipSnapshot struct {
	Found                    bool
	State                    ownershipState
	BindingID                string
	SessionID                string
	Scope                    string
	Generation               uint64
	AdmissionGate            string
	SimulatedMutationAllowed bool
	ImplementationAllowed    bool
	ConfinementProven        bool
	UnsafeExternalState      bool
	ChildCount               int
}

type workOwnershipModel struct {
	mu          sync.Mutex
	journalPath string
	tracker     *ownershipFakeTracker
	native      *ownershipFakeNative
	authorities map[string]string
	records     map[string]*ownershipRecord
	events      []ownershipEvent
	eventByID   map[string]ownershipEvent
	rolledBack  bool
}

func openWorkOwnershipModel(journalPath string, tracker *ownershipFakeTracker, native *ownershipFakeNative, authorities map[string]string) (*workOwnershipModel, error) {
	if tracker == nil || native == nil {
		return nil, errors.New("serialized tracker and native-session fakes are required")
	}
	m := &workOwnershipModel{
		journalPath: journalPath,
		tracker:     tracker,
		native:      native,
		authorities: make(map[string]string, len(authorities)),
		records:     make(map[string]*ownershipRecord),
		eventByID:   make(map[string]ownershipEvent),
	}
	for trackerUUID, endpoint := range authorities {
		key, err := canonicalOwnershipKey(ownershipKey{TrackerUUID: trackerUUID, TaskID: "authority-validation"})
		if err != nil || endpoint == "" || strings.TrimSpace(endpoint) != endpoint {
			return nil, errors.New("authority mapping must pin an exact tracker UUID and endpoint")
		}
		m.authorities[key.TrackerUUID] = endpoint
	}
	data, err := os.ReadFile(journalPath)
	if os.IsNotExist(err) {
		file, createErr := os.OpenFile(journalPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
		if createErr != nil {
			return nil, createErr
		}
		if closeErr := file.Close(); closeErr != nil {
			return nil, closeErr
		}
		return m, nil
	}
	if err != nil {
		return nil, err
	}
	if len(data) > 0 && data[len(data)-1] != '\n' {
		return nil, errors.New("ownership journal is truncated; refusing reconstruction")
	}
	for lineNumber, line := range bytes.Split(data, []byte{'\n'}) {
		if len(line) == 0 {
			continue
		}
		event, decodeErr := decodeOwnershipEvent(line)
		if decodeErr != nil {
			return nil, fmt.Errorf("ownership journal line %d corrupt: %w", lineNumber+1, decodeErr)
		}
		if previous, exists := m.eventByID[event.ID]; exists {
			if previous != event {
				return nil, fmt.Errorf("ownership journal event %q has conflicting payload", event.ID)
			}
			continue
		}
		if applyErr := m.applyEvent(event); applyErr != nil {
			return nil, fmt.Errorf("ownership journal line %d invalid: %w", lineNumber+1, applyErr)
		}
		m.events = append(m.events, event)
		m.eventByID[event.ID] = event
	}
	return m, nil
}

func decodeOwnershipEvent(data []byte) (ownershipEvent, error) {
	if err := rejectDuplicateJSONKeys(data); err != nil {
		return ownershipEvent{}, err
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var event ownershipEvent
	if err := decoder.Decode(&event); err != nil {
		return ownershipEvent{}, err
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return ownershipEvent{}, errors.New("extra journal data")
	}
	return event, nil
}

func (m *workOwnershipModel) cloneForValidation() *workOwnershipModel {
	clone := &workOwnershipModel{
		journalPath: m.journalPath,
		tracker:     m.tracker,
		native:      m.native,
		authorities: m.authorities,
		records:     make(map[string]*ownershipRecord, len(m.records)),
		rolledBack:  m.rolledBack,
	}
	for key, record := range m.records {
		copyRecord := *record
		copyRecord.Children = make(map[string]ownershipChildRequest, len(record.Children))
		for childID, child := range record.Children {
			copyRecord.Children[childID] = child
		}
		clone.records[key] = &copyRecord
	}
	return clone
}

func (m *workOwnershipModel) appendEvent(event ownershipEvent) error {
	if previous, exists := m.eventByID[event.ID]; exists {
		if previous == event {
			return nil
		}
		return fmt.Errorf("duplicate ownership event %q has conflicting payload", event.ID)
	}
	trial := m.cloneForValidation()
	if err := trial.applyEvent(event); err != nil {
		return err
	}
	encoded, err := json.Marshal(event)
	if err != nil {
		return err
	}
	file, err := os.OpenFile(m.journalPath, os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if _, err = file.Write(append(encoded, '\n')); err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	if err := m.applyEvent(event); err != nil {
		return err
	}
	m.events = append(m.events, event)
	m.eventByID[event.ID] = event
	return nil
}

func (m *workOwnershipModel) applyEvent(event ownershipEvent) error {
	if event.Version != 1 || event.ID == "" || event.Kind == "" {
		return errors.New("journal event requires version 1, id, and kind")
	}
	if event.Kind == "rollback" {
		if event.Key != (ownershipKey{}) || event.Generation != 0 {
			return errors.New("rollback must be global")
		}
		m.rolledBack = true
		return nil
	}
	key, err := canonicalOwnershipKey(event.Key)
	if err != nil || key != event.Key {
		return errors.New("journal event key is not canonical")
	}
	record := m.records[key.mapKey()]
	sameBinding := func() bool {
		return record != nil && record.BindingID == event.BindingID && record.SessionID == event.SessionID && record.Scope == event.Scope && record.Generation == event.Generation
	}
	sameOwner := func() bool {
		return record != nil && record.BindingID == event.BindingID && record.Generation == event.Generation
	}
	switch event.Kind {
	case "pending":
		if event.Endpoint == "" || event.BindingID == "" || event.SessionID == "" || event.Scope == "" {
			return errors.New("pending event lacks exact ownership identity")
		}
		wantGeneration := uint64(1)
		if record != nil {
			if record.State != ownershipReleased {
				return errors.New("pending acquisition conflicts with current owner")
			}
			wantGeneration = record.Generation + 1
		}
		if event.Generation != wantGeneration {
			return fmt.Errorf("generation must strictly increase to %d", wantGeneration)
		}
		m.records[key.mapKey()] = &ownershipRecord{
			Key: key, State: ownershipPending, Endpoint: event.Endpoint,
			BindingID: event.BindingID, SessionID: event.SessionID, Scope: event.Scope,
			Generation: event.Generation, Children: make(map[string]ownershipChildRequest),
		}
	case "attribution-verified":
		if record == nil || record.State != ownershipPending || !sameBinding() {
			return errors.New("attribution receipt does not match pending acquisition")
		}
		record.AttributionVerified = true
	case "claim-verified":
		if record == nil || record.State != ownershipPending || !sameBinding() {
			return errors.New("claim receipt does not match pending acquisition")
		}
		record.ClaimVerified = true
	case "active":
		if record == nil || record.State != ownershipPending || !sameBinding() || !record.AttributionVerified || !record.ClaimVerified {
			return errors.New("activation requires matching attribution and claim receipts")
		}
		record.State = ownershipActive
	case "unknown":
		if record == nil || !sameOwner() || (record.State != ownershipPending && record.State != ownershipActive && record.State != ownershipUnknown && record.State != ownershipDraining) {
			return errors.New("unknown event does not match a live ownership generation")
		}
		if record.State != ownershipUnknown {
			record.ResumeState = record.State
		}
		record.State = ownershipUnknown
		if event.Cause == "unsafe-external-clear" {
			record.UnsafeExternalState = true
		}
	case "pending-resumed":
		if record == nil || record.State != ownershipUnknown || record.ResumeState != ownershipPending || !sameBinding() || record.UnsafeExternalState {
			return errors.New("pending reconciliation requires exact suspended acquisition")
		}
		record.State = ownershipPending
	case "reverified":
		if record == nil || record.State != ownershipUnknown || record.ResumeState == ownershipPending || !sameBinding() || record.UnsafeExternalState || !record.AttributionVerified || !record.ClaimVerified {
			return errors.New("reverification does not match recoverable unknown ownership")
		}
		record.State = ownershipActive
		if record.DrainRequested {
			record.State = ownershipDraining
		}
	case "draining":
		if record == nil || record.State != ownershipActive || !sameOwner() {
			return errors.New("draining requires the exact active owner and generation")
		}
		record.State = ownershipDraining
		record.DrainRequested = true
	case "child-admitted":
		child := ownershipChildRequest{Key: key, ChildID: event.ChildID, BindingID: event.BindingID, SessionID: event.SessionID, Scope: event.Scope, Generation: event.Generation}
		if record == nil || record.State != ownershipActive || !sameBinding() || event.ChildID == "" {
			return errors.New("child admission requires exact active binding, session, scope, and generation")
		}
		if previous, exists := record.Children[event.ChildID]; exists && previous != child {
			return errors.New("child identity conflicts with prior admission")
		}
		record.Children[event.ChildID] = child
	case "released":
		if record == nil || (record.State != ownershipDraining && !(record.State == ownershipUnknown && record.DrainRequested)) || !sameOwner() {
			return errors.New("release receipt requires exact draining owner and generation")
		}
		record.State = ownershipReleased
	default:
		return fmt.Errorf("unknown ownership event kind %q", event.Kind)
	}
	return nil
}

func ownershipStableEventID(kind string, key ownershipKey, generation uint64) string {
	return fmt.Sprintf("%s:%s:%s:%d", kind, key.TrackerUUID, key.TaskID, generation)
}

func (m *workOwnershipModel) nextObservationID(kind string, key ownershipKey, generation uint64) string {
	return fmt.Sprintf("%s:%s:%s:%d:%d", kind, key.TrackerUUID, key.TaskID, generation, len(m.events)+1)
}

// ProductionImplementationAllowed is deliberately invariant. This reference
// model never confers production authority.
func (m *workOwnershipModel) ProductionImplementationAllowed() bool { return false }

func (m *workOwnershipModel) SimulatedAcquire(request ownershipAcquireRequest) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.simulatedAcquireLocked(request)
}

func (m *workOwnershipModel) simulatedAcquireLocked(request ownershipAcquireRequest) error {
	key, err := canonicalOwnershipKey(request.Key)
	if err != nil {
		return err
	}
	request.Key = key
	endpoint, registered := m.authorities[key.TrackerUUID]
	if !registered {
		return errors.New("tracker mapping missing; simulated admission blocked")
	}
	if request.Endpoint != endpoint {
		return errors.New("authority endpoint mismatch; replica cannot admit")
	}
	if m.rolledBack {
		return errors.New("rollback admission gate is closed")
	}
	if request.BindingID == "" || request.SessionID == "" || request.Scope == "" {
		return errors.New("binding, native session, and scope must be exact and nonempty")
	}
	record := m.records[key.mapKey()]
	if record == nil || record.State == ownershipReleased {
		wantGeneration := uint64(1)
		if record != nil {
			wantGeneration = record.Generation + 1
		}
		if request.Generation != wantGeneration {
			return fmt.Errorf("generation must strictly increase to %d", wantGeneration)
		}
		task, readErr := m.tracker.Read(key)
		if readErr != nil {
			return fmt.Errorf("tracker authority unavailable: %w", readErr)
		}
		if task.Assignee != "" || task.Status == "in_progress" {
			return errors.New("existing claimed task remains owned; takeover forbidden")
		}
		pending := ownershipEvent{Version: 1, ID: ownershipStableEventID("pending", key, request.Generation), Kind: "pending", Key: key, Endpoint: request.Endpoint, BindingID: request.BindingID, SessionID: request.SessionID, Scope: request.Scope, Generation: request.Generation}
		if err := m.appendEvent(pending); err != nil {
			return err
		}
		record = m.records[key.mapKey()]
	} else {
		if record.BindingID != request.BindingID || record.SessionID != request.SessionID || record.Scope != request.Scope || record.Generation != request.Generation || record.Endpoint != request.Endpoint {
			return errors.New("current or unknown ownership forbids takeover")
		}
		if record.State == ownershipActive {
			return m.verifyMutationLocked(record)
		}
		if record.State == ownershipUnknown && record.ResumeState == ownershipPending && !record.UnsafeExternalState {
			if err := m.appendEvent(ownershipEvent{Version: 1, ID: m.nextObservationID("pending-resumed", key, request.Generation), Kind: "pending-resumed", Key: key, BindingID: request.BindingID, SessionID: request.SessionID, Scope: request.Scope, Generation: request.Generation}); err != nil {
				return err
			}
		}
		if record.State != ownershipPending {
			return errors.New("ownership must be reverified or released before acquisition")
		}
	}
	if request.CrashAt == crashAfterPendingAppend {
		return errOwnershipSimulatedCrash
	}
	if !record.AttributionVerified {
		if err := m.native.AttributeExact(request); err != nil {
			return fmt.Errorf("native attribution failed: %w", err)
		}
		if request.CrashAt == crashAfterAttributionEffect {
			return errOwnershipSimulatedCrash
		}
		event := ownershipEvent{Version: 1, ID: ownershipStableEventID("attribution", key, request.Generation), Kind: "attribution-verified", Key: key, BindingID: request.BindingID, SessionID: request.SessionID, Scope: request.Scope, Generation: request.Generation}
		if err := m.appendEvent(event); err != nil {
			return err
		}
	}
	if !record.ClaimVerified {
		if err := m.tracker.ClaimExact(request); err != nil {
			return fmt.Errorf("tracker claim failed: %w", err)
		}
		if request.CrashAt == crashAfterClaimEffect {
			return errOwnershipSimulatedCrash
		}
		event := ownershipEvent{Version: 1, ID: ownershipStableEventID("claim", key, request.Generation), Kind: "claim-verified", Key: key, BindingID: request.BindingID, SessionID: request.SessionID, Scope: request.Scope, Generation: request.Generation}
		if err := m.appendEvent(event); err != nil {
			return err
		}
	}
	if err := m.verifyExactAuthority(request); err != nil {
		return err
	}
	return m.appendEvent(ownershipEvent{Version: 1, ID: ownershipStableEventID("active", key, request.Generation), Kind: "active", Key: key, BindingID: request.BindingID, SessionID: request.SessionID, Scope: request.Scope, Generation: request.Generation})
}

func (m *workOwnershipModel) verifyExactAuthority(request ownershipAcquireRequest) error {
	task, err := m.tracker.Read(request.Key)
	if err != nil {
		return fmt.Errorf("tracker authority unavailable: %w", err)
	}
	if task.Status != "in_progress" || task.Assignee != request.BindingID || !task.Leaf {
		return errors.New("activation requires current exact in_progress leaf claim by binding actor")
	}
	return m.verifyNativeAuthority(request)
}

func (m *workOwnershipModel) verifyNativeAuthority(request ownershipAcquireRequest) error {
	attribution, err := m.native.Read(request.Key, request.Generation)
	if err != nil {
		return fmt.Errorf("native session authority unavailable: %w", err)
	}
	if attribution.BindingID != request.BindingID || attribution.SessionID != request.SessionID || attribution.Scope != request.Scope || attribution.Generation != request.Generation {
		return errors.New("activation requires exact native binding, session, scope, and generation attribution")
	}
	return nil
}

func (m *workOwnershipModel) markUnknownLocked(record *ownershipRecord, cause string) error {
	if record.State == ownershipUnknown && (cause != "unsafe-external-clear" || record.UnsafeExternalState) {
		return nil
	}
	return m.appendEvent(ownershipEvent{Version: 1, ID: m.nextObservationID("unknown", record.Key, record.Generation), Kind: "unknown", Key: record.Key, BindingID: record.BindingID, Generation: record.Generation, Cause: cause})
}

// Every simulated mutation rechecks both independently persisted authorities;
// an active journal entry is historical evidence, not current admission.
func (m *workOwnershipModel) verifyMutationLocked(record *ownershipRecord) error {
	request := ownershipAcquireRequest{Key: record.Key, Endpoint: record.Endpoint, BindingID: record.BindingID, SessionID: record.SessionID, Scope: record.Scope, Generation: record.Generation}
	if err := m.verifyExactAuthority(request); err != nil {
		if journalErr := m.markUnknownLocked(record, "authority-verification-failed"); journalErr != nil {
			return fmt.Errorf("authority verification failed (%v); journal: %w", err, journalErr)
		}
		return err
	}
	return nil
}

func (m *workOwnershipModel) SimulatedLoseHeartbeat(key ownershipKey, bindingID string, generation uint64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	key, err := canonicalOwnershipKey(key)
	if err != nil {
		return err
	}
	record := m.records[key.mapKey()]
	if record == nil || (record.State != ownershipActive && record.State != ownershipDraining) || record.BindingID != bindingID || record.Generation != generation {
		return errors.New("stale heartbeat must identify exact active ownership")
	}
	return m.markUnknownLocked(record, "stale-heartbeat")
}

func (m *workOwnershipModel) SimulatedReverify(request ownershipAcquireRequest) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	key, err := canonicalOwnershipKey(request.Key)
	if err != nil {
		return err
	}
	request.Key = key
	record := m.records[key.mapKey()]
	if record == nil || (record.State != ownershipUnknown && record.State != ownershipActive) || record.BindingID != request.BindingID || record.SessionID != request.SessionID || record.Scope != request.Scope || record.Generation != request.Generation {
		return errors.New("only the exact current owner may reverify")
	}
	if record.UnsafeExternalState {
		return errors.New("unsafe external clear revoked simulated mutation")
	}
	if record.State == ownershipUnknown && record.ResumeState == ownershipPending {
		return errors.New("pending acquisition must reconcile claim and activation receipts through acquisition retry")
	}
	if err := m.verifyExactAuthority(request); err != nil {
		if unknownErr := m.markUnknownLocked(record, "authority-verification-failed"); unknownErr != nil {
			return unknownErr
		}
		return err
	}
	if record.State == ownershipActive {
		return nil
	}
	return m.appendEvent(ownershipEvent{Version: 1, ID: m.nextObservationID("reverified", key, request.Generation), Kind: "reverified", Key: key, BindingID: request.BindingID, SessionID: request.SessionID, Scope: request.Scope, Generation: request.Generation})
}

func (m *workOwnershipModel) SimulatedObserveAuthority(key ownershipKey) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	key, err := canonicalOwnershipKey(key)
	if err != nil {
		return err
	}
	record := m.records[key.mapKey()]
	if record == nil || record.State == ownershipReleased {
		return errors.New("no live ownership to observe")
	}
	task, err := m.tracker.Read(key)
	if err != nil {
		return m.markUnknownLocked(record, "authority-unavailable")
	}
	if record.DrainRequested && ownershipHasReleaseReceipt(task, record.BindingID, record.Generation) {
		return nil
	}
	if task.UnsafeExternalClear {
		return m.markUnknownLocked(record, "unsafe-external-clear")
	}
	// These unclaimed states are expected transaction windows, not a takeover.
	if (record.State == ownershipPending || record.State == ownershipUnknown && record.ResumeState == ownershipPending) && task.Assignee == "" && task.Status == "open" {
		return nil
	}
	if task.Assignee != record.BindingID || task.Status != "in_progress" {
		return m.markUnknownLocked(record, "unsafe-external-clear")
	}
	return nil
}

func (m *workOwnershipModel) SimulatedAdmitChild(request ownershipChildRequest) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	key, err := canonicalOwnershipKey(request.Key)
	if err != nil {
		return err
	}
	request.Key = key
	if m.rolledBack {
		return errors.New("rollback admission gate is closed")
	}
	record := m.records[key.mapKey()]
	if record == nil || record.State != ownershipActive || record.UnsafeExternalState || request.ChildID == "" || record.BindingID != request.BindingID || record.SessionID != request.SessionID || record.Scope != request.Scope || record.Generation != request.Generation {
		return errors.New("simulated child admission requires exact active scope and generation")
	}
	if err := m.verifyMutationLocked(record); err != nil {
		return err
	}
	if err := m.tracker.AddChild(key, request.ChildID); err != nil {
		return err
	}
	event := ownershipEvent{Version: 1, ID: ownershipStableEventID("child-"+request.ChildID, key, request.Generation), Kind: "child-admitted", Key: key, BindingID: request.BindingID, SessionID: request.SessionID, Scope: request.Scope, Generation: request.Generation, ChildID: request.ChildID}
	return m.appendEvent(event)
}

func (m *workOwnershipModel) SimulatedRelease(request ownershipReleaseRequest) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.simulatedReleaseLocked(request)
}

func (m *workOwnershipModel) simulatedReleaseLocked(request ownershipReleaseRequest) error {
	key, err := canonicalOwnershipKey(request.Key)
	if err != nil {
		return err
	}
	request.Key = key
	if m.rolledBack {
		return errors.New("rollback admission gate is closed")
	}
	record := m.records[key.mapKey()]
	if record == nil || (record.State != ownershipActive && record.State != ownershipDraining && !(record.State == ownershipUnknown && record.DrainRequested)) || record.BindingID != request.BindingID || record.Generation != request.Generation {
		return errors.New("release requires exact current active owner and generation")
	}
	if record.State == ownershipActive {
		if err := m.appendEvent(ownershipEvent{Version: 1, ID: ownershipStableEventID("draining", key, request.Generation), Kind: "draining", Key: key, BindingID: request.BindingID, Generation: request.Generation}); err != nil {
			return err
		}
	}
	task, err := m.tracker.Read(key)
	if err != nil {
		if journalErr := m.markUnknownLocked(record, "tracker-authority-unavailable"); journalErr != nil {
			return journalErr
		}
		return fmt.Errorf("cannot verify terminal child tree: %w", err)
	}
	if ownershipHasReleaseReceipt(task, record.BindingID, record.Generation) {
		// Reconcile the completed historical operation. Never clear a later
		// claimant, even when it reused this actor string or already released.
		return m.appendEvent(ownershipEvent{Version: 1, ID: ownershipStableEventID("released", key, request.Generation), Kind: "released", Key: key, BindingID: request.BindingID, Generation: request.Generation})
	}
	if record.UnsafeExternalState {
		return errors.New("unsafe external clear revoked simulated release")
	}
	if err := m.verifyNativeAuthority(ownershipAcquireRequest{Key: key, BindingID: record.BindingID, SessionID: record.SessionID, Scope: record.Scope, Generation: record.Generation}); err != nil {
		if journalErr := m.markUnknownLocked(record, "native-authority-unavailable"); journalErr != nil {
			return journalErr
		}
		return err
	}
	if !task.TreeKnown {
		return errors.New("explicit unknown child tree blocks release")
	}
	for childID := range record.Children {
		status, present := task.Children[childID]
		if !present || !ownershipTerminalStatus(status) {
			return fmt.Errorf("known child %s lacks terminal evidence", childID)
		}
	}
	for childID, status := range task.Children {
		if !ownershipTerminalStatus(status) {
			return fmt.Errorf("child %s is nonterminal", childID)
		}
	}
	if task.Assignee != request.BindingID || task.Status != "in_progress" {
		return errors.New("unqualified external release or current owner mismatch")
	}
	if record.State == ownershipUnknown {
		if err := m.appendEvent(ownershipEvent{Version: 1, ID: m.nextObservationID("reverified", key, request.Generation), Kind: "reverified", Key: key, BindingID: record.BindingID, SessionID: record.SessionID, Scope: record.Scope, Generation: record.Generation}); err != nil {
			return err
		}
	}
	if task.Assignee != "" {
		if err := m.tracker.ReleaseExact(request); err != nil {
			return err
		}
	}
	if request.CrashAt == crashAfterReleaseEffect {
		return errOwnershipSimulatedCrash
	}
	return m.appendEvent(ownershipEvent{Version: 1, ID: ownershipStableEventID("released", key, request.Generation), Kind: "released", Key: key, BindingID: request.BindingID, Generation: request.Generation})
}

func ownershipTerminalStatus(status string) bool {
	switch status {
	case "closed", "done", "completed", "cancelled":
		return true
	default:
		return false
	}
}

func (m *workOwnershipModel) SimulatedHandoff(current ownershipReleaseRequest, successor ownershipAcquireRequest) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if current.Key != successor.Key {
		return errors.New("handoff successor must use the same exact task key")
	}
	if successor.Generation != current.Generation+1 {
		return errors.New("handoff successor generation must strictly increase")
	}
	if err := m.simulatedReleaseLocked(current); err != nil {
		return err
	}
	return m.simulatedAcquireLocked(successor)
}

func (m *workOwnershipModel) SimulatedRollback() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.rolledBack {
		return nil
	}
	return m.appendEvent(ownershipEvent{Version: 1, ID: "rollback", Kind: "rollback"})
}

func (m *workOwnershipModel) Snapshot(key ownershipKey) ownershipSnapshot {
	m.mu.Lock()
	defer m.mu.Unlock()
	key, err := canonicalOwnershipKey(key)
	if err != nil {
		return ownershipSnapshot{ImplementationAllowed: false, ConfinementProven: false, AdmissionGate: "closed"}
	}
	record := m.records[key.mapKey()]
	if record == nil {
		return ownershipSnapshot{ImplementationAllowed: false, ConfinementProven: false, AdmissionGate: "closed"}
	}
	gate := "closed"
	simulatedAllowed := false
	if record.State == ownershipActive && !m.rolledBack && !record.UnsafeExternalState && m.verifyMutationLocked(record) == nil {
		gate = "simulated-only"
		simulatedAllowed = true
	}
	return ownershipSnapshot{
		Found: true, State: record.State, BindingID: record.BindingID,
		SessionID: record.SessionID, Scope: record.Scope, Generation: record.Generation,
		AdmissionGate: gate, SimulatedMutationAllowed: simulatedAllowed,
		ImplementationAllowed: false, ConfinementProven: false,
		UnsafeExternalState: record.UnsafeExternalState, ChildCount: len(record.Children),
	}
}

func (m *workOwnershipModel) History() []ownershipEvent {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]ownershipEvent(nil), m.events...)
}

type ownershipTrackerTask struct {
	// Leaf is the Beads task hierarchy; Children is the fixture execution tree.
	// Delegates share an owner and do not create new Beads implementation tasks.
	Status                 string            `json:"status"`
	Assignee               string            `json:"assignee"`
	Leaf                   bool              `json:"leaf"`
	TreeKnown              bool              `json:"tree_known"`
	Children               map[string]string `json:"children"`
	UnsafeExternalClear    bool              `json:"unsafe_external_clear"`
	ClaimWrites            int               `json:"claim_writes"`
	ReleaseWrites          int               `json:"release_writes"`
	LastReleasedBinding    string            `json:"last_released_binding,omitempty"`
	LastReleasedGeneration uint64            `json:"last_released_generation,omitempty"`
	ReleaseReceipts        map[string]bool   `json:"release_receipts,omitempty"`
}

func ownershipReleaseReceiptKey(binding string, generation uint64) string {
	return fmt.Sprintf("%s\x00%d", binding, generation)
}

func ownershipHasReleaseReceipt(task ownershipTrackerTask, binding string, generation uint64) bool {
	return task.ReleaseReceipts[ownershipReleaseReceiptKey(binding, generation)]
}

type ownershipTrackerDisk struct {
	Available bool                            `json:"available"`
	Tasks     map[string]ownershipTrackerTask `json:"tasks"`
}

type ownershipFakeTracker struct {
	mu   sync.Mutex
	path string
}

func createOwnershipFakeTracker(path string) (*ownershipFakeTracker, error) {
	fake := &ownershipFakeTracker{path: path}
	return fake, fake.write(ownershipTrackerDisk{Available: true, Tasks: make(map[string]ownershipTrackerTask)})
}

func openOwnershipFakeTracker(path string) *ownershipFakeTracker {
	return &ownershipFakeTracker{path: path}
}

func (f *ownershipFakeTracker) readDisk() (ownershipTrackerDisk, error) {
	data, err := os.ReadFile(f.path)
	if err != nil {
		return ownershipTrackerDisk{}, err
	}
	var disk ownershipTrackerDisk
	if err := json.Unmarshal(data, &disk); err != nil {
		return ownershipTrackerDisk{}, err
	}
	if disk.Tasks == nil {
		disk.Tasks = make(map[string]ownershipTrackerTask)
	}
	return disk, nil
}

func (f *ownershipFakeTracker) write(disk ownershipTrackerDisk) error {
	data, err := json.Marshal(disk)
	if err != nil {
		return err
	}
	temporary := f.path + ".tmp"
	if err := os.WriteFile(temporary, data, 0o600); err != nil {
		return err
	}
	return os.Rename(temporary, f.path)
}

func (f *ownershipFakeTracker) SetTask(key ownershipKey, task ownershipTrackerTask) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	key, err := canonicalOwnershipKey(key)
	if err != nil {
		return err
	}
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	if task.Children == nil {
		task.Children = make(map[string]string)
	}
	disk.Tasks[key.mapKey()] = task
	return f.write(disk)
}

func (f *ownershipFakeTracker) SetAvailable(available bool) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	disk.Available = available
	return f.write(disk)
}

func (f *ownershipFakeTracker) Read(key ownershipKey) (ownershipTrackerTask, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return ownershipTrackerTask{}, err
	}
	if !disk.Available {
		return ownershipTrackerTask{}, errors.New("fake tracker disconnected")
	}
	task, exists := disk.Tasks[key.mapKey()]
	if !exists {
		return ownershipTrackerTask{}, errors.New("task not found at fake authority")
	}
	return task, nil
}

func (f *ownershipFakeTracker) ClaimExact(request ownershipAcquireRequest) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	if !disk.Available {
		return errors.New("fake tracker disconnected")
	}
	task, exists := disk.Tasks[request.Key.mapKey()]
	if !exists {
		return errors.New("task not found")
	}
	if task.Status == "in_progress" && task.Assignee == request.BindingID && task.Leaf {
		return nil
	}
	if task.Status != "open" || task.Assignee != "" || !task.Leaf {
		return errors.New("task is not an unclaimed leaf")
	}
	task.Status = "in_progress"
	task.Assignee = request.BindingID
	task.ClaimWrites++
	disk.Tasks[request.Key.mapKey()] = task
	return f.write(disk)
}

func (f *ownershipFakeTracker) AddChild(key ownershipKey, childID string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	if !disk.Available {
		return errors.New("fake tracker disconnected")
	}
	task := disk.Tasks[key.mapKey()]
	if task.Children == nil {
		task.Children = make(map[string]string)
	}
	if _, exists := task.Children[childID]; !exists {
		task.Children[childID] = "in_progress"
		// Execution delegates do not change the Beads dependency-leaf flag.
	}
	disk.Tasks[key.mapKey()] = task
	return f.write(disk)
}

func (f *ownershipFakeTracker) SetChildStatus(key ownershipKey, childID, status string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	task := disk.Tasks[key.mapKey()]
	if task.Children == nil {
		return errors.New("child tree absent")
	}
	if _, exists := task.Children[childID]; !exists {
		return errors.New("child absent")
	}
	task.Children[childID] = status
	disk.Tasks[key.mapKey()] = task
	return f.write(disk)
}

func (f *ownershipFakeTracker) SetTreeKnown(key ownershipKey, known bool) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	task := disk.Tasks[key.mapKey()]
	task.TreeKnown = known
	disk.Tasks[key.mapKey()] = task
	return f.write(disk)
}

func (f *ownershipFakeTracker) ReleaseExact(request ownershipReleaseRequest) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	if !disk.Available {
		return errors.New("fake tracker disconnected")
	}
	task := disk.Tasks[request.Key.mapKey()]
	if task.Status != "in_progress" || task.Assignee != request.BindingID {
		return errors.New("fake release lacks exact owner; unconditional clear forbidden")
	}
	task.Status = "open"
	task.Assignee = ""
	task.ReleaseWrites++
	task.LastReleasedBinding = request.BindingID
	task.LastReleasedGeneration = request.Generation
	if task.ReleaseReceipts == nil {
		task.ReleaseReceipts = make(map[string]bool)
	}
	task.ReleaseReceipts[ownershipReleaseReceiptKey(request.BindingID, request.Generation)] = true
	disk.Tasks[request.Key.mapKey()] = task
	return f.write(disk)
}

func (f *ownershipFakeTracker) UnsafeExternalClear(key ownershipKey) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	task := disk.Tasks[key.mapKey()]
	task.Status = "open"
	task.Assignee = ""
	task.UnsafeExternalClear = true
	disk.Tasks[key.mapKey()] = task
	return f.write(disk)
}

type ownershipNativeAttribution struct {
	BindingID         string `json:"binding_id"`
	SessionID         string `json:"session_id"`
	Scope             string `json:"scope"`
	Generation        uint64 `json:"generation"`
	AttributionWrites int    `json:"attribution_writes"`
}

type ownershipNativeDisk struct {
	Available    bool                                  `json:"available"`
	Attributions map[string]ownershipNativeAttribution `json:"attributions"`
}

type ownershipFakeNative struct {
	mu   sync.Mutex
	path string
}

func createOwnershipFakeNative(path string) (*ownershipFakeNative, error) {
	fake := &ownershipFakeNative{path: path}
	return fake, fake.write(ownershipNativeDisk{Available: true, Attributions: make(map[string]ownershipNativeAttribution)})
}

func openOwnershipFakeNative(path string) *ownershipFakeNative {
	return &ownershipFakeNative{path: path}
}

func (f *ownershipFakeNative) readDisk() (ownershipNativeDisk, error) {
	data, err := os.ReadFile(f.path)
	if err != nil {
		return ownershipNativeDisk{}, err
	}
	var disk ownershipNativeDisk
	if err := json.Unmarshal(data, &disk); err != nil {
		return ownershipNativeDisk{}, err
	}
	if disk.Attributions == nil {
		disk.Attributions = make(map[string]ownershipNativeAttribution)
	}
	return disk, nil
}

func (f *ownershipFakeNative) write(disk ownershipNativeDisk) error {
	data, err := json.Marshal(disk)
	if err != nil {
		return err
	}
	temporary := f.path + ".tmp"
	if err := os.WriteFile(temporary, data, 0o600); err != nil {
		return err
	}
	return os.Rename(temporary, f.path)
}

func (f *ownershipFakeNative) SetAvailable(available bool) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	disk.Available = available
	return f.write(disk)
}

func (f *ownershipFakeNative) SetAttribution(key ownershipKey, attribution ownershipNativeAttribution) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	disk.Attributions[ownershipNativeMapKey(key, attribution.Generation)] = attribution
	return f.write(disk)
}

func (f *ownershipFakeNative) AttributeExact(request ownershipAcquireRequest) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return err
	}
	if !disk.Available {
		return errors.New("fake native-session authority disconnected")
	}
	want := ownershipNativeAttribution{BindingID: request.BindingID, SessionID: request.SessionID, Scope: request.Scope, Generation: request.Generation}
	mapKey := ownershipNativeMapKey(request.Key, request.Generation)
	if existing, exists := disk.Attributions[mapKey]; exists {
		if existing.BindingID != want.BindingID || existing.SessionID != want.SessionID || existing.Scope != want.Scope || existing.Generation != want.Generation {
			return errors.New("conflicting native attribution")
		}
		return nil
	}
	want.AttributionWrites = 1
	disk.Attributions[mapKey] = want
	return f.write(disk)
}

func ownershipNativeMapKey(key ownershipKey, generation uint64) string {
	return fmt.Sprintf("%s\x00%d", key.mapKey(), generation)
}

func (f *ownershipFakeNative) Read(key ownershipKey, generation uint64) (ownershipNativeAttribution, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	disk, err := f.readDisk()
	if err != nil {
		return ownershipNativeAttribution{}, err
	}
	if !disk.Available {
		return ownershipNativeAttribution{}, errors.New("fake native-session authority disconnected")
	}
	attribution, exists := disk.Attributions[ownershipNativeMapKey(key, generation)]
	if !exists {
		return ownershipNativeAttribution{}, errors.New("native attribution absent")
	}
	return attribution, nil
}
