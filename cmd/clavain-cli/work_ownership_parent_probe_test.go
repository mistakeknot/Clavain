package main

import (
	"errors"
	"path/filepath"
	"testing"
)

func TestWorkOwnershipObservationInterleavesCrashRecovery(t *testing.T) {
	for _, point := range []ownershipCrashPoint{crashAfterPendingAppend, crashAfterReleaseEffect} {
		for _, outage := range []bool{false, true} {
			t.Run(string(point)+map[bool]string{false: "/observation", true: "/outage"}[outage], func(t *testing.T) {
				h := newOwnershipHarness(t)
				request := h.request
				release := ownershipReleaseRequest{Key: h.key, BindingID: request.BindingID, Generation: 1, CrashAt: point}
				if point == crashAfterPendingAppend {
					request.CrashAt = point
					if err := h.model.SimulatedAcquire(request); !errors.Is(err, errOwnershipSimulatedCrash) {
						t.Fatal(err)
					}
				} else {
					if err := h.model.SimulatedAcquire(request); err != nil {
						t.Fatal(err)
					}
					if err := h.model.SimulatedRelease(release); !errors.Is(err, errOwnershipSimulatedCrash) {
						t.Fatal(err)
					}
				}
				m := h.reopen(t)
				if outage {
					if err := h.tracker.SetAvailable(false); err != nil {
						t.Fatal(err)
					}
					if err := m.SimulatedObserveAuthority(h.key); err != nil {
						t.Fatal(err)
					}
					if got := m.Snapshot(h.key).State; got != ownershipUnknown {
						t.Fatalf("outage state=%s", got)
					}
					if err := h.tracker.SetAvailable(true); err != nil {
						t.Fatal(err)
					}
				}
				if err := m.SimulatedObserveAuthority(h.key); err != nil {
					t.Fatal(err)
				}
				other := request
				other.CrashAt = ""
				other.BindingID = "other"
				other.SessionID = "other"
				if err := m.SimulatedAcquire(other); err == nil {
					t.Fatal("observation permitted takeover")
				}
				request.CrashAt = ""
				release.CrashAt = ""
				if point == crashAfterPendingAppend {
					if err := m.SimulatedAcquire(request); err != nil {
						t.Fatalf("pending recovery: %v", err)
					}
				} else {
					if err := m.SimulatedRelease(release); err != nil {
						t.Fatalf("release recovery: %v", err)
					}
				}
				task, err := h.tracker.Read(h.key)
				if err != nil {
					t.Fatal(err)
				}
				if task.ClaimWrites != 1 {
					t.Fatalf("duplicate claim: %+v", task)
				}
				if point == crashAfterReleaseEffect && task.ReleaseWrites != 1 {
					t.Fatalf("duplicate release: %+v", task)
				}
			})
		}
	}
}

func parentOwnershipFixture(t *testing.T) (*workOwnershipModel, ownershipAcquireRequest) {
	t.Helper()
	root := t.TempDir()
	tracker, err := createOwnershipFakeTracker(filepath.Join(root, "tracker.json"))
	if err != nil {
		t.Fatal(err)
	}
	native, err := createOwnershipFakeNative(filepath.Join(root, "native.json"))
	if err != nil {
		t.Fatal(err)
	}
	req := ownershipAcquireRequest{Key: ownershipKey{TrackerUUID: workUUIDA, TaskID: "probe-1"}, Endpoint: "authority", BindingID: "binding", SessionID: "session", Scope: "scope", Generation: 1}
	if err = tracker.SetTask(req.Key, ownershipTrackerTask{Status: "open", Leaf: true, TreeKnown: true}); err != nil {
		t.Fatal(err)
	}
	m, err := openWorkOwnershipModel(filepath.Join(root, "journal"), tracker, native, map[string]string{workUUIDA: "authority"})
	if err != nil {
		t.Fatal(err)
	}
	if err = m.SimulatedAcquire(req); err != nil {
		t.Fatal(err)
	}
	return m, req
}

func TestWorkOwnershipParentRestartRequiresReverification(t *testing.T) {
	m, req := parentOwnershipFixture(t)
	if err := m.native.SetAvailable(false); err != nil {
		t.Fatal(err)
	}
	reopened, err := openWorkOwnershipModel(m.journalPath, openOwnershipFakeTracker(m.tracker.path), openOwnershipFakeNative(m.native.path), m.authorities)
	if err != nil {
		t.Fatal(err)
	}
	if reopened.Snapshot(req.Key).SimulatedMutationAllowed {
		t.Error("restart trusts stale active journal despite disconnected native authority")
	}
	if err := reopened.SimulatedAcquire(req); err == nil {
		t.Error("active retry succeeds without native reverification")
	}
	if err := reopened.SimulatedAdmitChild(ownershipChildRequest{Key: req.Key, ChildID: "late", BindingID: req.BindingID, SessionID: req.SessionID, Scope: req.Scope, Generation: req.Generation}); err == nil {
		t.Error("child admitted with disconnected native authority")
	}
}

func TestWorkOwnershipParentDrainingSurvivesUncertainty(t *testing.T) {
	m, req := parentOwnershipFixture(t)
	child := ownershipChildRequest{Key: req.Key, ChildID: "live", BindingID: req.BindingID, SessionID: req.SessionID, Scope: req.Scope, Generation: req.Generation}
	if err := m.SimulatedAdmitChild(child); err != nil {
		t.Fatal(err)
	}
	if err := m.SimulatedRelease(ownershipReleaseRequest{Key: req.Key, BindingID: req.BindingID, Generation: 1}); err == nil {
		t.Fatal("live child did not block release")
	}
	if err := m.tracker.SetChildStatus(req.Key, "live", "completed"); err != nil {
		t.Fatal(err)
	}
	if err := m.tracker.SetAvailable(false); err != nil {
		t.Fatal(err)
	}
	if err := m.SimulatedObserveAuthority(req.Key); err != nil {
		t.Fatal(err)
	}
	if err := m.tracker.SetAvailable(true); err != nil {
		t.Fatal(err)
	}
	t.Logf("reverify=%v snapshot=%+v", m.SimulatedReverify(req), m.Snapshot(req.Key))
	child.ChildID = "late"
	if err := m.SimulatedAdmitChild(child); err == nil {
		t.Error("authority recovery reopened draining child admission")
	} else {
		t.Logf("child rejection: %v", err)
	}
}

func TestWorkOwnershipParentMissingKnownChildBlocksRelease(t *testing.T) {
	m, req := parentOwnershipFixture(t)
	if err := m.SimulatedAdmitChild(ownershipChildRequest{Key: req.Key, ChildID: "live", BindingID: req.BindingID, SessionID: req.SessionID, Scope: req.Scope, Generation: 1}); err != nil {
		t.Fatal(err)
	}
	task, err := m.tracker.Read(req.Key)
	if err != nil {
		t.Fatal(err)
	}
	task.Children = map[string]string{}
	if err := m.tracker.SetTask(req.Key, task); err != nil {
		t.Fatal(err)
	}
	if err := m.SimulatedRelease(ownershipReleaseRequest{Key: req.Key, BindingID: req.BindingID, Generation: 1}); err == nil {
		t.Error("release forgot a previously admitted live child")
	}
}

func TestWorkOwnershipParentNativeOutageBlocksMutation(t *testing.T) {
	for _, operation := range []string{"child", "release"} {
		t.Run(operation, func(t *testing.T) {
			m, req := parentOwnershipFixture(t)
			if err := m.native.SetAvailable(false); err != nil {
				t.Fatal(err)
			}
			var err error
			if operation == "child" {
				err = m.SimulatedAdmitChild(ownershipChildRequest{Key: req.Key, ChildID: "late", BindingID: req.BindingID, SessionID: req.SessionID, Scope: req.Scope, Generation: 1})
			} else {
				err = m.SimulatedRelease(ownershipReleaseRequest{Key: req.Key, BindingID: req.BindingID, Generation: 1})
			}
			if err == nil {
				t.Fatal("native outage allowed simulated mutation")
			}
		})
	}
}

func TestWorkOwnershipDelegateTreeIsNotBeadsHierarchy(t *testing.T) {
	m, req := parentOwnershipFixture(t)
	child := ownershipChildRequest{Key: req.Key, ChildID: "one", BindingID: req.BindingID, SessionID: req.SessionID, Scope: req.Scope, Generation: 1}
	if err := m.SimulatedAdmitChild(child); err != nil {
		t.Fatal(err)
	}
	child.ChildID = "two"
	if err := m.SimulatedAdmitChild(child); err != nil {
		t.Fatal(err)
	}
	task, err := m.tracker.Read(req.Key)
	if err != nil {
		t.Fatal(err)
	}
	if !task.Leaf || len(task.Children) != 2 {
		t.Fatal("execution delegates changed Beads leaf identity")
	}
	task.Leaf = false
	if err := m.tracker.SetTask(req.Key, task); err != nil {
		t.Fatal(err)
	}
	child.ChildID = "three"
	if err := m.SimulatedAdmitChild(child); err == nil {
		t.Fatal("non-leaf Bead admitted execution")
	}
}

func TestWorkOwnershipDrainingHeartbeatRecovery(t *testing.T) {
	m, req := parentOwnershipFixture(t)
	if err := m.SimulatedAdmitChild(ownershipChildRequest{Key: req.Key, ChildID: "live", BindingID: req.BindingID, SessionID: req.SessionID, Scope: req.Scope, Generation: 1}); err != nil {
		t.Fatal(err)
	}
	release := ownershipReleaseRequest{Key: req.Key, BindingID: req.BindingID, Generation: 1}
	if err := m.SimulatedRelease(release); err == nil {
		t.Fatal("live tree released")
	}
	if err := m.SimulatedLoseHeartbeat(req.Key, req.BindingID, 1); err != nil {
		t.Fatal(err)
	}
	if got := m.Snapshot(req.Key).State; got != ownershipUnknown {
		t.Fatalf("expiry state=%s", got)
	}
	if err := m.tracker.SetAvailable(false); err != nil {
		t.Fatal(err)
	}
	if err := m.SimulatedRelease(release); err == nil {
		t.Fatal("disconnected release succeeded")
	}
	if got := m.Snapshot(req.Key).State; got != ownershipUnknown {
		t.Fatalf("outage state=%s", got)
	}
	if err := m.tracker.SetAvailable(true); err != nil {
		t.Fatal(err)
	}
	if err := m.tracker.SetChildStatus(req.Key, "live", "completed"); err != nil {
		t.Fatal(err)
	}
	if err := m.SimulatedRelease(release); err != nil {
		t.Fatal(err)
	}
	if got := m.Snapshot(req.Key).State; got != ownershipReleased {
		t.Fatalf("reconciled state=%s", got)
	}
}

func TestWorkOwnershipPendingReverifyCannotSkipReceipts(t *testing.T) {
	h := newOwnershipHarness(t)
	r := h.request
	r.CrashAt = crashAfterClaimEffect
	if err := h.model.SimulatedAcquire(r); !errors.Is(err, errOwnershipSimulatedCrash) {
		t.Fatal(err)
	}
	if err := h.tracker.SetAvailable(false); err != nil {
		t.Fatal(err)
	}
	if err := h.model.SimulatedObserveAuthority(h.key); err != nil {
		t.Fatal(err)
	}
	if err := h.tracker.SetAvailable(true); err != nil {
		t.Fatal(err)
	}
	r.CrashAt = ""
	if err := h.model.SimulatedReverify(r); err == nil {
		t.Fatal("reverify skipped pending claim and activation receipts")
	}
	if err := h.model.SimulatedAcquire(r); err != nil {
		t.Fatal(err)
	}
	seen := map[string]bool{}
	for _, e := range h.model.History() {
		seen[e.Kind] = true
	}
	if !seen["claim-verified"] || !seen["active"] {
		t.Fatal("acquisition recovery omitted verified receipts")
	}
}

func TestWorkOwnershipReleaseReceiptSurvivesLaterClaims(t *testing.T) {
	for _, mode := range []string{"other-owner", "same-actor", "other-released"} {
		t.Run(mode, func(t *testing.T) {
			h := newOwnershipHarness(t)
			if err := h.model.SimulatedAcquire(h.request); err != nil {
				t.Fatal(err)
			}
			release := ownershipReleaseRequest{Key: h.key, BindingID: h.request.BindingID, Generation: 1, CrashAt: crashAfterReleaseEffect}
			if err := h.model.SimulatedRelease(release); !errors.Is(err, errOwnershipSimulatedCrash) {
				t.Fatal(err)
			}
			external := h.request
			external.Generation = 99
			if mode != "same-actor" {
				external.BindingID = "external-owner"
			}
			if err := h.tracker.ClaimExact(external); err != nil {
				t.Fatal(err)
			}
			if mode == "other-released" {
				if err := h.tracker.ReleaseExact(ownershipReleaseRequest{Key: h.key, BindingID: external.BindingID, Generation: 99}); err != nil {
					t.Fatal(err)
				}
			}
			before, err := h.tracker.Read(h.key)
			if err != nil {
				t.Fatal(err)
			}
			m := h.reopen(t)
			if err := m.SimulatedObserveAuthority(h.key); err != nil {
				t.Fatal(err)
			}
			release.CrashAt = ""
			if err := m.SimulatedRelease(release); err != nil {
				t.Fatalf("historical release reconciliation: %v", err)
			}
			after, err := h.tracker.Read(h.key)
			if err != nil {
				t.Fatal(err)
			}
			if after.ReleaseWrites != before.ReleaseWrites || after.Assignee != before.Assignee || after.Status != before.Status {
				t.Fatalf("reconciliation changed later ownership: before=%+v after=%+v", before, after)
			}
			if snapshot := m.Snapshot(h.key); snapshot.State != ownershipReleased || snapshot.SimulatedMutationAllowed {
				t.Fatalf("old generation admitted: %+v", snapshot)
			}
		})
	}
}
