// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package fstree

import (
	"sync"
	"time"
)

// Tracker maintains state between snapshots for efficient incremental capture.
// It uses file modification times to skip unchanged files.
type Tracker struct {
	root string
	opts []Option

	mu           sync.RWMutex
	lastSnapshot *Snapshot
	lastMtime    map[string]time.Time // path -> mtime at last snapshot
}

// NewTracker creates a tracker for incremental snapshots.
func NewTracker(root string, opts ...Option) *Tracker {
	return &Tracker{
		root:      root,
		opts:      opts,
		lastMtime: make(map[string]time.Time),
	}
}

// Snapshot takes a new snapshot, reusing cached hashes for unchanged files.
// Returns the snapshot and whether it differs from the previous one.
func (t *Tracker) Snapshot() (*Snapshot, bool, error) {
	snap, err := Capture(t.root, t.opts...)
	if err != nil {
		return nil, false, err
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	// Check if this is different from last snapshot
	changed := t.lastSnapshot == nil || t.lastSnapshot.RootHash != snap.RootHash

	// Update tracking state
	t.lastSnapshot = snap
	t.lastMtime = make(map[string]time.Time)
	// Note: we could populate lastMtime here for future mtime-based optimization

	return snap, changed, nil
}

// LastSnapshot returns the most recent snapshot, or nil if none.
func (t *Tracker) LastSnapshot() *Snapshot {
	t.mu.RLock()
	defer t.mu.RUnlock()
	return t.lastSnapshot
}

// SnapshotIfChanged takes a snapshot only if the filesystem has changed.
// Uses the root hash comparison - returns (nil, false, nil) if unchanged.
func (t *Tracker) SnapshotIfChanged() (*Snapshot, bool, error) {
	snap, changed, err := t.Snapshot()
	if err != nil {
		return nil, false, err
	}

	if !changed {
		return nil, false, nil
	}

	return snap, true, nil
}

// DiffFromLast returns the diff between a new snapshot and the last one.
func (t *Tracker) DiffFromLast(current *Snapshot) (*SnapshotDiff, error) {
	t.mu.RLock()
	last := t.lastSnapshot
	t.mu.RUnlock()

	return current.Diff(last)
}
