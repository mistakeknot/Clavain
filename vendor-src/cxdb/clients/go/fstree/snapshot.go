// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package fstree

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
)

// GetFile returns a reader for the file content given its hash.
// Returns nil if the file is not in this snapshot.
func (s *Snapshot) GetFile(hash [32]byte) (io.ReadCloser, error) {
	ref, ok := s.Files[hash]
	if !ok {
		return nil, fmt.Errorf("file not found: %x", hash[:8])
	}

	return os.Open(ref.Path)
}

// GetTree returns the deserialized tree object for a given hash.
func (s *Snapshot) GetTree(hash [32]byte) ([]TreeEntry, error) {
	data, ok := s.Trees[hash]
	if !ok {
		return nil, fmt.Errorf("tree not found: %x", hash[:8])
	}

	return DeserializeTree(data)
}

// GetRootEntries returns the entries at the root of the snapshot.
func (s *Snapshot) GetRootEntries() ([]TreeEntry, error) {
	return s.GetTree(s.RootHash)
}

// Walk traverses the snapshot tree, calling fn for each entry.
// The path argument is the full relative path from the root.
// If fn returns an error, walking stops and that error is returned.
func (s *Snapshot) Walk(fn func(path string, entry TreeEntry) error) error {
	return s.walkTree(s.RootHash, "", fn)
}

func (s *Snapshot) walkTree(hash [32]byte, prefix string, fn func(string, TreeEntry) error) error {
	entries, err := s.GetTree(hash)
	if err != nil {
		return err
	}

	for _, entry := range entries {
		path := entry.Name
		if prefix != "" {
			path = filepath.Join(prefix, entry.Name)
		}

		if err := fn(path, entry); err != nil {
			return err
		}

		if entry.Kind == EntryKindDirectory {
			if err := s.walkTree(entry.Hash, path, fn); err != nil {
				return err
			}
		}
	}

	return nil
}

// ListFiles returns all file paths in the snapshot.
func (s *Snapshot) ListFiles() ([]string, error) {
	var paths []string
	err := s.Walk(func(path string, entry TreeEntry) error {
		if entry.Kind == EntryKindFile {
			paths = append(paths, path)
		}
		return nil
	})
	return paths, err
}

// GetFileAtPath looks up a file by its path in the snapshot.
// Returns the TreeEntry and content reader if found.
func (s *Snapshot) GetFileAtPath(path string) (*TreeEntry, io.ReadCloser, error) {
	parts := splitPath(path)
	if len(parts) == 0 {
		return nil, nil, fmt.Errorf("empty path")
	}

	currentHash := s.RootHash

	for i, part := range parts {
		entries, err := s.GetTree(currentHash)
		if err != nil {
			return nil, nil, fmt.Errorf("get tree: %w", err)
		}

		var found *TreeEntry
		for _, entry := range entries {
			if entry.Name == part {
				found = &entry
				break
			}
		}

		if found == nil {
			return nil, nil, fmt.Errorf("path not found: %s", path)
		}

		// Last component
		if i == len(parts)-1 {
			if found.Kind == EntryKindFile {
				reader, err := s.GetFile(found.Hash)
				if err != nil {
					return nil, nil, err
				}
				return found, reader, nil
			}
			return found, nil, nil
		}

		// Navigate into directory
		if found.Kind != EntryKindDirectory {
			return nil, nil, fmt.Errorf("not a directory: %s", filepath.Join(parts[:i+1]...))
		}
		currentHash = found.Hash
	}

	return nil, nil, fmt.Errorf("path not found: %s", path)
}

// splitPath splits a path into components.
func splitPath(path string) []string {
	// Normalize to forward slashes for cross-platform consistency
	path = filepath.ToSlash(filepath.Clean(path))
	if path == "." || path == "" {
		return nil
	}

	// Simple split on forward slash
	var parts []string
	start := 0
	for i := 0; i <= len(path); i++ {
		if i == len(path) || path[i] == '/' {
			if i > start {
				part := path[start:i]
				if part != "." {
					parts = append(parts, part)
				}
			}
			start = i + 1
		}
	}
	return parts
}

// Diff compares two snapshots and returns the differences.
// old may be nil, in which case all files in s are considered added.
func (s *Snapshot) Diff(old *Snapshot) (*SnapshotDiff, error) {
	diff := &SnapshotDiff{
		NewRoot: s.RootHash,
	}

	if old != nil {
		diff.OldRoot = old.RootHash
	}

	// Quick check - if root hashes match, no changes
	if old != nil && s.RootHash == old.RootHash {
		return diff, nil
	}

	// Collect all paths from new snapshot
	newPaths := make(map[string][32]byte)
	if err := s.Walk(func(path string, entry TreeEntry) error {
		if entry.Kind == EntryKindFile || entry.Kind == EntryKindSymlink {
			newPaths[path] = entry.Hash
		}
		return nil
	}); err != nil {
		return nil, fmt.Errorf("walk new snapshot: %w", err)
	}

	// If no old snapshot, everything is added
	if old == nil {
		for path := range newPaths {
			diff.Added = append(diff.Added, path)
		}
		return diff, nil
	}

	// Collect all paths from old snapshot
	oldPaths := make(map[string][32]byte)
	if err := old.Walk(func(path string, entry TreeEntry) error {
		if entry.Kind == EntryKindFile || entry.Kind == EntryKindSymlink {
			oldPaths[path] = entry.Hash
		}
		return nil
	}); err != nil {
		return nil, fmt.Errorf("walk old snapshot: %w", err)
	}

	// Find added and modified
	for path, newHash := range newPaths {
		oldHash, exists := oldPaths[path]
		if !exists {
			diff.Added = append(diff.Added, path)
		} else if newHash != oldHash {
			diff.Modified = append(diff.Modified, path)
		}
	}

	// Find removed
	for path := range oldPaths {
		if _, exists := newPaths[path]; !exists {
			diff.Removed = append(diff.Removed, path)
		}
	}

	return diff, nil
}

// IsEmpty returns true if the diff contains no changes.
func (d *SnapshotDiff) IsEmpty() bool {
	return len(d.Added) == 0 && len(d.Removed) == 0 && len(d.Modified) == 0
}

// TotalChanges returns the total number of changed paths.
func (d *SnapshotDiff) TotalChanges() int {
	return len(d.Added) + len(d.Removed) + len(d.Modified)
}
