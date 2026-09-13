package main

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

type ownershipHarness struct {
	dir         string
	journalPath string
	trackerPath string
	nativePath  string
	tracker     *ownershipFakeTracker
	native      *ownershipFakeNative
	model       *workOwnershipModel
	key         ownershipKey
	request     ownershipAcquireRequest
}

func newOwnershipHarness(t *testing.T) ownershipHarness {
	t.Helper()
	dir := t.TempDir()
	trackerPath := filepath.Join(dir, "tracker.json")
	nativePath := filepath.Join(dir, "native.json")
	journalPath := filepath.Join(dir, "journal.jsonl")
	tracker, err := createOwnershipFakeTracker(trackerPath)
	if err != nil {
		t.Fatal(err)
	}
	native, err := createOwnershipFakeNative(nativePath)
	if err != nil {
		t.Fatal(err)
	}
	key := ownershipKey{TrackerUUID: workUUIDA, TaskID: "Sylveste-grez.3"}
	if err := tracker.SetTask(key, ownershipTrackerTask{Status: "open", Leaf: true, TreeKnown: true}); err != nil {
		t.Fatal(err)
	}
	model, err := openWorkOwnershipModel(journalPath, tracker, native, map[string]string{workUUIDA: "authority"})
	if err != nil {
		t.Fatal(err)
	}
	request := ownershipAcquireRequest{Key: key, Endpoint: "authority", BindingID: "owner-A", SessionID: "session-A", Scope: "fixture-only", Generation: 1}
	return ownershipHarness{dir: dir, journalPath: journalPath, trackerPath: trackerPath, nativePath: nativePath, tracker: tracker, native: native, model: model, key: key, request: request}
}

func (h ownershipHarness) reopen(t *testing.T) *workOwnershipModel {
	t.Helper()
	model, err := openWorkOwnershipModel(h.journalPath, openOwnershipFakeTracker(h.trackerPath), openOwnershipFakeNative(h.nativePath), map[string]string{workUUIDA: "authority", workUUIDB: "authority"})
	if err != nil {
		t.Fatal(err)
	}
	return model
}

func TestWorkOwnershipActivationRequiresImplementedReferenceModel(t *testing.T) {
	h := newOwnershipHarness(t)
	if err := h.model.SimulatedAcquire(h.request); err != nil {
		t.Fatalf("simulated acquisition did not activate: %v", err)
	}
	snapshot := h.model.Snapshot(h.key)
	if snapshot.State != ownershipActive || snapshot.BindingID != "owner-A" || snapshot.Generation != 1 {
		t.Fatalf("unexpected active snapshot: %+v", snapshot)
	}
	if snapshot.ImplementationAllowed || snapshot.ConfinementProven || h.model.ProductionImplementationAllowed() {
		t.Fatal("fixture model claimed production implementation or confinement")
	}
	if snapshot.AdmissionGate != "simulated-only" || !snapshot.SimulatedMutationAllowed {
		t.Fatalf("fixture admission was not explicitly simulated: %+v", snapshot)
	}
}

func TestWorkOwnershipSimultaneousAcquisitionIsSerialized(t *testing.T) {
	h := newOwnershipHarness(t)
	requests := []ownershipAcquireRequest{h.request, h.request}
	requests[1].BindingID = "owner-B"
	requests[1].SessionID = "session-B"
	var wg sync.WaitGroup
	errorsSeen := make([]error, len(requests))
	for i := range requests {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			errorsSeen[index] = h.model.SimulatedAcquire(requests[index])
		}(i)
	}
	wg.Wait()
	successes := 0
	for _, err := range errorsSeen {
		if err == nil {
			successes++
		}
	}
	if successes != 1 {
		t.Fatalf("simultaneous acquisition successes=%d errors=%v", successes, errorsSeen)
	}
	snapshot := h.model.Snapshot(h.key)
	if snapshot.State != ownershipActive || (snapshot.BindingID != "owner-A" && snapshot.BindingID != "owner-B") {
		t.Fatalf("serialized winner absent: %+v", snapshot)
	}
	if len(h.model.History()) != 4 {
		t.Fatalf("duplicate acquisition journaled: %+v", h.model.History())
	}
}

func TestWorkOwnershipDuplicateEventIDsAreIdempotentOrRejected(t *testing.T) {
	h := newOwnershipHarness(t)
	event := ownershipEvent{Version: 1, ID: "pending-id", Kind: "pending", Key: h.key, Endpoint: "authority", BindingID: "owner-A", SessionID: "session-A", Scope: "fixture-only", Generation: 1}
	if err := h.model.appendEvent(event); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(h.journalPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := h.model.appendEvent(event); err != nil {
		t.Fatalf("exact duplicate was not idempotent: %v", err)
	}
	after, _ := os.ReadFile(h.journalPath)
	if string(after) != string(before) || len(h.model.History()) != 1 {
		t.Fatal("exact duplicate appended a second event")
	}
	conflict := event
	conflict.BindingID = "owner-B"
	if err := h.model.appendEvent(conflict); err == nil || !strings.Contains(err.Error(), "conflicting payload") {
		t.Fatalf("conflicting duplicate accepted: %v", err)
	}
}

func TestWorkOwnershipActivationRejectsSuccessWithoutVerifiedReceipts(t *testing.T) {
	h := newOwnershipHarness(t)
	pending := ownershipEvent{Version: 1, ID: "pending", Kind: "pending", Key: h.key, Endpoint: "authority", BindingID: "owner-A", SessionID: "session-A", Scope: "fixture-only", Generation: 1}
	if err := h.model.appendEvent(pending); err != nil {
		t.Fatal(err)
	}
	active := ownershipEvent{Version: 1, ID: "active", Kind: "active", Key: h.key, BindingID: "owner-A", SessionID: "session-A", Scope: "fixture-only", Generation: 1}
	if err := h.model.appendEvent(active); err == nil || !strings.Contains(err.Error(), "requires matching attribution and claim receipts") {
		t.Fatalf("success-shaped activation bypassed receipts: %v", err)
	}
	if snapshot := h.model.Snapshot(h.key); snapshot.State != ownershipPending {
		t.Fatalf("invalid activation changed state: %+v", snapshot)
	}
}

func TestWorkOwnershipCrashWindowsReconcileDurableSideEffects(t *testing.T) {
	for _, crashPoint := range []ownershipCrashPoint{crashAfterPendingAppend, crashAfterAttributionEffect, crashAfterClaimEffect} {
		t.Run(string(crashPoint), func(t *testing.T) {
			h := newOwnershipHarness(t)
			request := h.request
			request.CrashAt = crashPoint
			if err := h.model.SimulatedAcquire(request); !errors.Is(err, errOwnershipSimulatedCrash) {
				t.Fatalf("missing injected crash: %v", err)
			}
			restarted := h.reopen(t)
			request.CrashAt = ""
			if err := restarted.SimulatedAcquire(request); err != nil {
				t.Fatalf("restart did not reconcile: %v", err)
			}
			if snapshot := restarted.Snapshot(h.key); snapshot.State != ownershipActive || snapshot.Generation != 1 {
				t.Fatalf("restart snapshot: %+v", snapshot)
			}
			task, err := openOwnershipFakeTracker(h.trackerPath).Read(h.key)
			if err != nil || task.ClaimWrites != 1 {
				t.Fatalf("claim side effect duplicated: task=%+v err=%v", task, err)
			}
			attribution, err := openOwnershipFakeNative(h.nativePath).Read(h.key, 1)
			if err != nil || attribution.AttributionWrites != 1 {
				t.Fatalf("attribution side effect duplicated: attribution=%+v err=%v", attribution, err)
			}
		})
	}
}

func TestWorkOwnershipReleaseCrashReconcilesOnlyExactReceipt(t *testing.T) {
	h := newOwnershipHarness(t)
	if err := h.model.SimulatedAcquire(h.request); err != nil {
		t.Fatal(err)
	}
	release := ownershipReleaseRequest{Key: h.key, BindingID: h.request.BindingID, Generation: 1, CrashAt: crashAfterReleaseEffect}
	if err := h.model.SimulatedRelease(release); !errors.Is(err, errOwnershipSimulatedCrash) {
		t.Fatalf("release crash not injected: %v", err)
	}
	restarted := h.reopen(t)
	release.CrashAt = ""
	if err := restarted.SimulatedRelease(release); err != nil {
		t.Fatalf("exact release effect not reconciled: %v", err)
	}
	if snapshot := restarted.Snapshot(h.key); snapshot.State != ownershipReleased {
		t.Fatalf("release receipt not reconstructed: %+v", snapshot)
	}
	task, _ := openOwnershipFakeTracker(h.trackerPath).Read(h.key)
	if task.ReleaseWrites != 1 {
		t.Fatalf("release side effect duplicated: %+v", task)
	}
}

func TestWorkOwnershipJournalReconstructionFailsClosed(t *testing.T) {
	for _, tc := range []struct {
		name string
		data string
		want string
	}{
		{name: "truncated", data: `{"version":1`, want: "truncated"},
		{name: "corrupt", data: "not-json\n", want: "corrupt"},
		{name: "unknown-event", data: `{"version":1,"id":"x","kind":"surprise","key":{"tracker_uuid":"` + workUUIDA + `","task_id":"a"}}` + "\n", want: "unknown ownership event"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			h := newOwnershipHarness(t)
			if err := os.WriteFile(h.journalPath, []byte(tc.data), 0o600); err != nil {
				t.Fatal(err)
			}
			_, err := openWorkOwnershipModel(h.journalPath, h.tracker, h.native, map[string]string{workUUIDA: "authority"})
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("journal did not fail closed: %v", err)
			}
		})
	}
}

func TestWorkOwnershipActivationRejectsUnverifiedAuthority(t *testing.T) {
	tests := []struct {
		name  string
		alter func(t *testing.T, h *ownershipHarness)
		want  string
	}{
		{name: "authority-replica", alter: func(t *testing.T, h *ownershipHarness) { h.request.Endpoint = "replica" }, want: "replica cannot admit"},
		{name: "missing-mapping", alter: func(t *testing.T, h *ownershipHarness) { h.request.Key.TrackerUUID = workUUIDB }, want: "tracker mapping missing"},
		{name: "wrong-status", alter: func(t *testing.T, h *ownershipHarness) {
			if err := h.tracker.SetTask(h.key, ownershipTrackerTask{Status: "blocked", Leaf: true, TreeKnown: true}); err != nil {
				t.Fatal(err)
			}
		}, want: "not an unclaimed leaf"},
		{name: "not-leaf", alter: func(t *testing.T, h *ownershipHarness) {
			if err := h.tracker.SetTask(h.key, ownershipTrackerTask{Status: "open", Leaf: false, TreeKnown: true}); err != nil {
				t.Fatal(err)
			}
		}, want: "not an unclaimed leaf"},
		{name: "wrong-native-attribution", alter: func(t *testing.T, h *ownershipHarness) {
			if err := h.native.SetAttribution(h.key, ownershipNativeAttribution{BindingID: "other", SessionID: "session-A", Scope: "fixture-only", Generation: 1}); err != nil {
				t.Fatal(err)
			}
		}, want: "conflicting native attribution"},
		{name: "tracker-disconnected", alter: func(t *testing.T, h *ownershipHarness) {
			if err := h.tracker.SetAvailable(false); err != nil {
				t.Fatal(err)
			}
		}, want: "tracker authority unavailable"},
		{name: "session-disconnected", alter: func(t *testing.T, h *ownershipHarness) {
			if err := h.native.SetAvailable(false); err != nil {
				t.Fatal(err)
			}
		}, want: "native attribution failed"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			h := newOwnershipHarness(t)
			tc.alter(t, &h)
			err := h.model.SimulatedAcquire(h.request)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("unverified authority activated: %v", err)
			}
			if h.model.Snapshot(h.request.Key).State == ownershipActive {
				t.Fatal("failed verification produced active state")
			}
		})
	}
}

func TestWorkOwnershipExistingClaimRemainsOwned(t *testing.T) {
	for _, assignee := range []string{"existing-owner", "owner-A"} {
		t.Run(assignee, func(t *testing.T) {
			h := newOwnershipHarness(t)
			if err := h.tracker.SetTask(h.key, ownershipTrackerTask{Status: "in_progress", Assignee: assignee, Leaf: true, TreeKnown: true}); err != nil {
				t.Fatal(err)
			}
			if err := h.model.SimulatedAcquire(h.request); err == nil || !strings.Contains(err.Error(), "remains owned") {
				t.Fatalf("existing claim taken over: %v", err)
			}
			task, _ := h.tracker.Read(h.key)
			if task.Assignee != assignee || task.ClaimWrites != 0 || len(h.model.History()) != 0 {
				t.Fatalf("existing claim mutated: %+v history=%v", task, h.model.History())
			}
		})
	}
}

func TestWorkOwnershipUnknownNeverPermitsTakeoverAndOwnerMayReverify(t *testing.T) {
	h := newOwnershipHarness(t)
	if err := h.model.SimulatedAcquire(h.request); err != nil {
		t.Fatal(err)
	}
	if err := h.model.SimulatedLoseHeartbeat(h.key, "owner-A", 1); err != nil {
		t.Fatal(err)
	}
	takeover := h.request
	takeover.BindingID = "owner-B"
	takeover.SessionID = "session-B"
	if err := h.model.SimulatedAcquire(takeover); err == nil || !strings.Contains(err.Error(), "takeover") {
		t.Fatalf("unknown ownership permitted takeover: %v", err)
	}
	if err := h.model.SimulatedReverify(h.request); err != nil {
		t.Fatalf("same owner could not reverify: %v", err)
	}
	if snapshot := h.model.Snapshot(h.key); snapshot.State != ownershipActive {
		t.Fatalf("reverification did not restore active: %+v", snapshot)
	}
	if err := h.tracker.SetAvailable(false); err != nil {
		t.Fatal(err)
	}
	if err := h.model.SimulatedReverify(h.request); err == nil || !strings.Contains(err.Error(), "unavailable") {
		t.Fatalf("disconnected authority looked verified: %v", err)
	}
	if snapshot := h.model.Snapshot(h.key); snapshot.State != ownershipUnknown || snapshot.SimulatedMutationAllowed {
		t.Fatalf("authority failure did not revoke admission: %+v", snapshot)
	}
}

func TestWorkOwnershipChildrenDrainReleaseAndGenerationFencing(t *testing.T) {
	h := newOwnershipHarness(t)
	if err := h.model.SimulatedAcquire(h.request); err != nil {
		t.Fatal(err)
	}
	child := ownershipChildRequest{Key: h.key, ChildID: "child-1", BindingID: "owner-A", SessionID: "session-A", Scope: "fixture-only", Generation: 1}
	for name, mutate := range map[string]func(*ownershipChildRequest){
		"wrong-scope":    func(r *ownershipChildRequest) { r.Scope = "other" },
		"old-generation": func(r *ownershipChildRequest) { r.Generation = 0 },
		"wrong-session":  func(r *ownershipChildRequest) { r.SessionID = "other" },
	} {
		t.Run(name, func(t *testing.T) {
			bad := child
			mutate(&bad)
			if err := h.model.SimulatedAdmitChild(bad); err == nil {
				t.Fatal("mismatched delegate admitted")
			}
		})
	}
	if err := h.model.SimulatedAdmitChild(child); err != nil {
		t.Fatal(err)
	}
	if err := h.tracker.SetTreeKnown(h.key, false); err != nil {
		t.Fatal(err)
	}
	release := ownershipReleaseRequest{Key: h.key, BindingID: "owner-A", Generation: 1}
	if err := h.model.SimulatedRelease(ownershipReleaseRequest{Key: h.key, BindingID: "owner-B", Generation: 1}); err == nil {
		t.Fatal("wrong owner released current generation")
	}
	if err := h.model.SimulatedRelease(ownershipReleaseRequest{Key: h.key, BindingID: "owner-A", Generation: 2}); err == nil {
		t.Fatal("wrong generation released current owner")
	}
	if err := h.model.SimulatedRelease(release); err == nil || !strings.Contains(err.Error(), "unknown child tree") {
		t.Fatalf("unknown tree released: %v", err)
	}
	late := child
	late.ChildID = "late-child"
	if err := h.model.SimulatedAdmitChild(late); err == nil {
		t.Fatal("draining admitted a delayed child")
	}
	if err := h.tracker.SetTreeKnown(h.key, true); err != nil {
		t.Fatal(err)
	}
	if err := h.tracker.SetChildStatus(h.key, "child-1", "closed"); err != nil {
		t.Fatal(err)
	}
	if err := h.model.SimulatedRelease(release); err != nil {
		t.Fatalf("known terminal tree did not release: %v", err)
	}
	second := h.request
	second.SessionID = "session-A-2"
	second.Generation = 2
	skipped := second
	skipped.Generation = 3
	if err := h.model.SimulatedAcquire(skipped); err == nil || !strings.Contains(err.Error(), "strictly increase to 2") {
		t.Fatalf("skipped generation admitted: %v", err)
	}
	if err := h.model.SimulatedAcquire(second); err != nil {
		t.Fatalf("next generation did not activate: %v", err)
	}
	obsolete := child
	obsolete.ChildID = "obsolete"
	if err := h.model.SimulatedAdmitChild(obsolete); err == nil {
		t.Fatal("old-generation child admitted")
	}
	if snapshot := h.model.Snapshot(h.key); snapshot.Generation != 2 || snapshot.State != ownershipActive {
		t.Fatalf("generation fence lost: %+v", snapshot)
	}
}

func TestWorkOwnershipHandoffReleasesBeforeSuccessorAcquisition(t *testing.T) {
	h := newOwnershipHarness(t)
	if err := h.model.SimulatedAcquire(h.request); err != nil {
		t.Fatal(err)
	}
	successor := h.request
	successor.BindingID = "owner-B"
	successor.SessionID = "session-B"
	successor.Generation = 2
	if err := h.model.SimulatedHandoff(ownershipReleaseRequest{Key: h.key, BindingID: "owner-A", Generation: 1}, successor); err != nil {
		t.Fatal(err)
	}
	history := h.model.History()
	releasedIndex, successorPendingIndex := -1, -1
	for i, event := range history {
		if event.Kind == "released" && event.Generation == 1 {
			releasedIndex = i
		}
		if event.Kind == "pending" && event.Generation == 2 {
			successorPendingIndex = i
		}
	}
	if releasedIndex < 0 || successorPendingIndex <= releasedIndex {
		t.Fatalf("handoff ordering violated: %+v", history)
	}
	if snapshot := h.model.Snapshot(h.key); snapshot.State != ownershipActive || snapshot.BindingID != "owner-B" || snapshot.Generation != 2 {
		t.Fatalf("successor not active: %+v", snapshot)
	}
}

func TestWorkOwnershipRollbackRetainsBindingClaimAndHistory(t *testing.T) {
	h := newOwnershipHarness(t)
	if err := h.model.SimulatedAcquire(h.request); err != nil {
		t.Fatal(err)
	}
	historyBefore := len(h.model.History())
	if err := h.model.SimulatedRollback(); err != nil {
		t.Fatal(err)
	}
	snapshot := h.model.Snapshot(h.key)
	if snapshot.State != ownershipActive || snapshot.BindingID != "owner-A" || snapshot.AdmissionGate != "closed" || snapshot.SimulatedMutationAllowed {
		t.Fatalf("rollback did not retain read-only ownership while closing admission: %+v", snapshot)
	}
	task, _ := h.tracker.Read(h.key)
	if task.Assignee != "owner-A" || task.Status != "in_progress" {
		t.Fatalf("rollback cleared claim: %+v", task)
	}
	if len(h.model.History()) != historyBefore+1 {
		t.Fatal("rollback discarded history")
	}
	if err := h.model.SimulatedAdmitChild(ownershipChildRequest{Key: h.key, ChildID: "blocked", BindingID: "owner-A", SessionID: "session-A", Scope: "fixture-only", Generation: 1}); err == nil {
		t.Fatal("rollback admitted child")
	}
	if err := h.model.SimulatedRelease(ownershipReleaseRequest{Key: h.key, BindingID: "owner-A", Generation: 1}); err == nil {
		t.Fatal("rollback admitted release mutation")
	}
	restarted := h.reopen(t)
	if snapshot := restarted.Snapshot(h.key); snapshot.AdmissionGate != "closed" || snapshot.BindingID != "owner-A" {
		t.Fatalf("rollback did not survive reconstruction: %+v", snapshot)
	}
}

func TestWorkOwnershipUnsafeExternalClearRevokesSimulatedMutation(t *testing.T) {
	h := newOwnershipHarness(t)
	if err := h.model.SimulatedAcquire(h.request); err != nil {
		t.Fatal(err)
	}
	if err := h.tracker.UnsafeExternalClear(h.key); err != nil {
		t.Fatal(err)
	}
	if err := h.model.SimulatedObserveAuthority(h.key); err != nil {
		t.Fatal(err)
	}
	snapshot := h.model.Snapshot(h.key)
	if snapshot.State != ownershipUnknown || !snapshot.UnsafeExternalState || snapshot.SimulatedMutationAllowed || snapshot.ConfinementProven || snapshot.ImplementationAllowed {
		t.Fatalf("unsafe external state was treated as confined: %+v", snapshot)
	}
	if err := h.model.SimulatedReverify(h.request); err == nil || !strings.Contains(err.Error(), "revoked") {
		t.Fatalf("unsafe clear was reverified: %v", err)
	}
}

func TestWorkOwnershipSameTaskIDInDistinctTrackersIsIndependent(t *testing.T) {
	dir := t.TempDir()
	tracker, err := createOwnershipFakeTracker(filepath.Join(dir, "tracker.json"))
	if err != nil {
		t.Fatal(err)
	}
	native, err := createOwnershipFakeNative(filepath.Join(dir, "native.json"))
	if err != nil {
		t.Fatal(err)
	}
	keyA := ownershipKey{TrackerUUID: workUUIDA, TaskID: "same-1"}
	keyB := ownershipKey{TrackerUUID: workUUIDB, TaskID: "same-1"}
	for _, key := range []ownershipKey{keyA, keyB} {
		if err := tracker.SetTask(key, ownershipTrackerTask{Status: "open", Leaf: true, TreeKnown: true}); err != nil {
			t.Fatal(err)
		}
	}
	model, err := openWorkOwnershipModel(filepath.Join(dir, "journal.jsonl"), tracker, native, map[string]string{workUUIDA: "authority", workUUIDB: "authority"})
	if err != nil {
		t.Fatal(err)
	}
	requestA := ownershipAcquireRequest{Key: keyA, Endpoint: "authority", BindingID: "owner-A", SessionID: "session-A", Scope: "scope-A", Generation: 1}
	requestB := ownershipAcquireRequest{Key: keyB, Endpoint: "authority", BindingID: "owner-B", SessionID: "session-B", Scope: "scope-B", Generation: 1}
	if err := model.SimulatedAcquire(requestA); err != nil {
		t.Fatal(err)
	}
	if err := model.SimulatedAcquire(requestB); err != nil {
		t.Fatal(err)
	}
	if a, b := model.Snapshot(keyA), model.Snapshot(keyB); a.BindingID == b.BindingID || a.Scope == b.Scope || !a.Found || !b.Found {
		t.Fatalf("tracker UUID omitted from canonical key: A=%+v B=%+v", a, b)
	}
}

func TestWorkOwnershipIncidentReferenceReplayPreservesBothOwners(t *testing.T) {
	base := filepath.Join("testdata", "work-incidents")
	manifestBytes, err := os.ReadFile(filepath.Join(base, "manifest.json"))
	if err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		Fixtures []struct{ Fixture, SHA256 string }
	}
	if err := json.Unmarshal(manifestBytes, &manifest); err != nil {
		t.Fatal(err)
	}
	if len(manifest.Fixtures) != 2 {
		t.Fatal("expected both pinned incident briefs")
	}
	briefs := make([]string, 0, 2)
	for _, fixture := range manifest.Fixtures {
		data, err := os.ReadFile(filepath.Join(base, fixture.Fixture))
		if err != nil {
			t.Fatal(err)
		}
		if fmt.Sprintf("%x", sha256.Sum256(data)) != fixture.SHA256 {
			t.Fatalf("pinned brief changed: %s", fixture.Fixture)
		}
		briefs = append(briefs, string(data))
	}
	if briefs[0] == briefs[1] || !strings.Contains(briefs[0], "adaptive routing") || !strings.Contains(briefs[1], "11 projects") {
		t.Fatal("distinct incident requirements were merged or lost")
	}

	dir := t.TempDir()
	tracker, err := createOwnershipFakeTracker(filepath.Join(dir, "tracker.json"))
	if err != nil {
		t.Fatal(err)
	}
	native, err := createOwnershipFakeNative(filepath.Join(dir, "native.json"))
	if err != nil {
		t.Fatal(err)
	}
	// Read-only Beads snapshot, 2026-09-13: the portfolio task is in progress
	// without an assignee. Preserve that uncertainty; never invent an owner.
	// UUIDs remain disposable stand-ins for the two separate tracker authorities.
	keys := []ownershipKey{{TrackerUUID: workUUIDA, TaskID: "Sylveste-grez"}, {TrackerUUID: workUUIDB, TaskID: "mk-rzpe"}}
	owners := []string{"adaptive-routing-20260912", ""}
	for i, key := range keys {
		if err := tracker.SetTask(key, ownershipTrackerTask{Status: "in_progress", Assignee: owners[i], Leaf: true, TreeKnown: true}); err != nil {
			t.Fatal(err)
		}
	}
	model, err := openWorkOwnershipModel(filepath.Join(dir, "journal.jsonl"), tracker, native, map[string]string{workUUIDA: "authority", workUUIDB: "authority"})
	if err != nil {
		t.Fatal(err)
	}
	for i, key := range keys {
		attempt := ownershipAcquireRequest{Key: key, Endpoint: "authority", BindingID: "new-owner", SessionID: "new-session", Scope: "fixture", Generation: 1}
		if err := model.SimulatedAcquire(attempt); err == nil || !strings.Contains(err.Error(), "remains owned") {
			t.Fatalf("incident %d owner taken over: %v", i, err)
		}
		task, _ := tracker.Read(key)
		if task.Assignee != owners[i] {
			t.Fatalf("incident %d assignee changed: %+v", i, task)
		}
	}
	if keys[0].mapKey() == keys[1].mapKey() || len(model.History()) != 0 {
		t.Fatal("independent incident keys merged or takeover was journaled")
	}
}

func TestWorkOwnershipRepositoryAliasConsistencyUsesRegistryContract(t *testing.T) {
	root := t.TempDir()
	repoA := filepath.Join(root, "repo-a")
	repoB := filepath.Join(root, "repo-b")
	registry := workRegistry{Version: 1, AuthorityEndpoint: workAuthorityEndpoint{Kind: "local", Identity: "authority"}, Trackers: []workTracker{{
		TrackerUUID: workUUIDA, Root: root,
		Repositories: []workRepository{{Alias: "zeta", Worktree: repoB}, {Alias: "alpha", Worktree: repoA}},
	}}}
	if err := validateWorkRegistry(registry); err != nil {
		t.Fatalf("ownership fixture diverged from registry validation: %v", err)
	}
	aliases := trackerAliases(registry.Trackers[0])
	if strings.Join(aliases, ",") != "alpha,zeta" {
		t.Fatalf("registry aliases not canonical: %v", aliases)
	}
	key := ownershipKey{TrackerUUID: registry.Trackers[0].TrackerUUID, TaskID: "Case-Sensitive"}
	otherCase := ownershipKey{TrackerUUID: registry.Trackers[0].TrackerUUID, TaskID: "case-sensitive"}
	if key.mapKey() == otherCase.mapKey() {
		t.Fatal("repository aliases or normalization erased task ID case")
	}
}
