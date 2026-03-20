// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

// Package fstree provides filesystem snapshot capabilities for CXDB.
//
// It builds content-addressed Merkle trees from filesystem state, suitable for
// tracking "what could the agent see" at any given turn. The design is similar
// to Git's tree/blob model but optimized for portable snapshots (no uid/gid).
//
// # Usage
//
//	snapshot, err := fstree.Capture("/path/to/workspace")
//	if err != nil {
//	    log.Fatal(err)
//	}
//
//	fmt.Printf("Root hash: %x\n", snapshot.RootHash)
//	fmt.Printf("Trees: %d, Files: %d\n", len(snapshot.Trees), len(snapshot.Files))
//
// # Design
//
// The filesystem is represented as a Merkle tree:
//   - Files are content-addressed blobs (BLAKE3 hash of contents)
//   - Directories are tree objects containing sorted entries
//   - Tree objects are also content-addressed (BLAKE3 hash of serialized entries)
//   - Unchanged subtrees share the same hash across snapshots (dedup)
//
// # Wire Format
//
// Tree objects are msgpack-encoded arrays of TreeEntry, sorted by name.
// This ensures deterministic hashing regardless of filesystem enumeration order.
package fstree

import "time"

// EntryKind indicates the type of filesystem entry.
type EntryKind uint8

const (
	// EntryKindFile is a regular file.
	EntryKindFile EntryKind = 0

	// EntryKindDirectory is a directory.
	EntryKindDirectory EntryKind = 1

	// EntryKindSymlink is a symbolic link.
	EntryKindSymlink EntryKind = 2
)

// TreeEntry represents a single entry in a directory.
// Entries are sorted by name for deterministic tree hashing.
type TreeEntry struct {
	// Name is the filename (no path separators).
	Name string `msgpack:"1" json:"name"`

	// Kind indicates file, directory, or symlink.
	Kind EntryKind `msgpack:"2" json:"kind"`

	// Mode contains POSIX permission bits (e.g., 0755, 0644).
	// Only the lower 12 bits are used (no uid/gid for portability).
	Mode uint32 `msgpack:"3" json:"mode"`

	// Size is the uncompressed size in bytes (files only, 0 for dirs/symlinks).
	Size uint64 `msgpack:"4" json:"size"`

	// Hash is the BLAKE3-256 hash:
	//   - For files: hash of file contents
	//   - For directories: hash of serialized TreeObject
	//   - For symlinks: hash of target path bytes
	Hash [32]byte `msgpack:"5" json:"hash"`
}

// TreeObject is a directory listing - a collection of entries.
// When serialized, entries are sorted by name for deterministic hashing.
type TreeObject struct {
	Entries []TreeEntry
}

// Snapshot represents a complete filesystem snapshot.
type Snapshot struct {
	// RootHash is the BLAKE3-256 hash of the root TreeObject.
	RootHash [32]byte

	// Trees maps tree hashes to their serialized TreeObject bytes.
	// Includes all directory tree objects in the snapshot.
	Trees map[[32]byte][]byte

	// Files maps file content hashes to FileRef.
	// The client retains file paths so content can be sent on demand.
	Files map[[32]byte]*FileRef

	// Symlinks maps symlink target hashes to their target path strings.
	// Stored separately from Files because the content is the target path, not file content.
	Symlinks map[[32]byte]string

	// Stats contains snapshot statistics.
	Stats SnapshotStats

	// CapturedAt is when this snapshot was taken.
	CapturedAt time.Time
}

// FileRef references a file's content without loading it into memory.
type FileRef struct {
	// Path is the absolute path to the file.
	Path string

	// Size is the file size in bytes.
	Size uint64

	// Hash is the BLAKE3-256 hash of the file contents.
	Hash [32]byte
}

// SnapshotStats contains statistics about a snapshot.
type SnapshotStats struct {
	// FileCount is the number of regular files.
	FileCount int

	// DirCount is the number of directories.
	DirCount int

	// SymlinkCount is the number of symbolic links.
	SymlinkCount int

	// TotalBytes is the total size of all files.
	TotalBytes uint64

	// Duration is how long the snapshot took.
	Duration time.Duration
}

// SnapshotDiff represents the difference between two snapshots.
type SnapshotDiff struct {
	// Added contains paths that exist in New but not Old.
	Added []string

	// Removed contains paths that exist in Old but not New.
	Removed []string

	// Modified contains paths that exist in both but have different content.
	Modified []string

	// OldRoot is the root hash of the old snapshot (zero if none).
	OldRoot [32]byte

	// NewRoot is the root hash of the new snapshot.
	NewRoot [32]byte
}
