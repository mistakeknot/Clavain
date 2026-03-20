// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package fstree

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"time"

	"github.com/vmihailenco/msgpack/v5"
	"github.com/zeebo/blake3"
)

// Common errors
var (
	ErrTooManyFiles = errors.New("fstree: too many files")
	ErrFileTooLarge = errors.New("fstree: file too large")
	ErrCyclicLink   = errors.New("fstree: cyclic symbolic link detected")
)

// Capture takes a snapshot of the filesystem at the given root path.
// Returns a Snapshot containing the Merkle tree of all files and directories.
//
// The snapshot uses content-addressing:
//   - Unchanged files have the same hash across snapshots
//   - Unchanged directories have the same tree hash
//   - This enables efficient deduplication in the CXDB blob store
func Capture(root string, opts ...Option) (*Snapshot, error) {
	start := time.Now()

	// Resolve to absolute path
	absRoot, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("resolve root: %w", err)
	}

	// Check root exists and is a directory
	info, err := os.Stat(absRoot)
	if err != nil {
		return nil, fmt.Errorf("stat root: %w", err)
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("root is not a directory: %s", absRoot)
	}

	// Apply options
	o := defaultOptions()
	for _, opt := range opts {
		opt(o)
	}

	// Build the tree
	b := &builder{
		root:     absRoot,
		opts:     o,
		trees:    make(map[[32]byte][]byte),
		files:    make(map[[32]byte]*FileRef),
		symlinks: make(map[[32]byte]string),
		visited:  make(map[string]bool), // for cycle detection with symlinks
	}

	rootHash, err := b.buildTree(absRoot, "")
	if err != nil {
		return nil, err
	}

	return &Snapshot{
		RootHash:   rootHash,
		Trees:      b.trees,
		Files:      b.files,
		Symlinks:   b.symlinks,
		CapturedAt: start,
		Stats: SnapshotStats{
			FileCount:    b.fileCount,
			DirCount:     b.dirCount,
			SymlinkCount: b.symlinkCount,
			TotalBytes:   b.totalBytes,
			Duration:     time.Since(start),
		},
	}, nil
}

// builder accumulates state during tree construction.
type builder struct {
	root     string
	opts     *options
	trees    map[[32]byte][]byte
	files    map[[32]byte]*FileRef
	symlinks map[[32]byte]string // target path for symlinks
	visited  map[string]bool     // resolved paths for cycle detection

	fileCount    int
	dirCount     int
	symlinkCount int
	totalBytes   uint64
}

// buildTree recursively builds the tree for a directory.
// Returns the hash of the TreeObject for this directory.
func (b *builder) buildTree(absPath, relPath string) ([32]byte, error) {
	// Check for cycles (when following symlinks)
	realPath, err := filepath.EvalSymlinks(absPath)
	if err == nil {
		if b.visited[realPath] {
			return [32]byte{}, ErrCyclicLink
		}
		b.visited[realPath] = true
		defer delete(b.visited, realPath)
	}

	// Read directory entries
	dirEntries, err := os.ReadDir(absPath)
	if err != nil {
		return [32]byte{}, fmt.Errorf("read dir %s: %w", relPath, err)
	}

	// Build entries for this directory
	var entries []TreeEntry

	for _, de := range dirEntries {
		name := de.Name()
		childRelPath := filepath.Join(relPath, name)
		childAbsPath := filepath.Join(absPath, name)

		// Check exclusions
		if b.opts.shouldExclude(childRelPath, de.IsDir()) {
			continue
		}

		// Get file info (follows symlinks if needed)
		var info fs.FileInfo
		if b.opts.followSymlinks {
			info, err = os.Stat(childAbsPath)
		} else {
			info, err = os.Lstat(childAbsPath)
		}
		if err != nil {
			// Skip files we can't stat (permission errors, etc.)
			continue
		}

		entry, err := b.buildEntry(childAbsPath, childRelPath, name, info)
		if err != nil {
			if errors.Is(err, ErrTooManyFiles) || errors.Is(err, ErrCyclicLink) {
				return [32]byte{}, err
			}
			// Skip individual files on error
			continue
		}

		entries = append(entries, entry)
	}

	// Sort entries by name for deterministic hashing
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Name < entries[j].Name
	})

	// Serialize and hash the tree object
	treeBytes, err := serializeTree(entries)
	if err != nil {
		return [32]byte{}, fmt.Errorf("serialize tree %s: %w", relPath, err)
	}

	hash := blake3.Sum256(treeBytes)
	b.trees[hash] = treeBytes
	b.dirCount++

	return hash, nil
}

// buildEntry creates a TreeEntry for a single filesystem entry.
func (b *builder) buildEntry(absPath, relPath, name string, info fs.FileInfo) (TreeEntry, error) {
	mode := uint32(info.Mode().Perm())

	switch {
	case info.Mode()&fs.ModeSymlink != 0:
		// Symbolic link - hash the target path
		target, err := os.Readlink(absPath)
		if err != nil {
			return TreeEntry{}, fmt.Errorf("readlink %s: %w", relPath, err)
		}

		hash := blake3.Sum256([]byte(target))
		b.symlinkCount++

		// Store symlink target string (not as FileRef since content is the target path)
		b.symlinks[hash] = target

		return TreeEntry{
			Name: name,
			Kind: EntryKindSymlink,
			Mode: mode,
			Size: uint64(len(target)),
			Hash: hash,
		}, nil

	case info.IsDir():
		// Directory - recurse
		dirHash, err := b.buildTree(absPath, relPath)
		if err != nil {
			return TreeEntry{}, err
		}

		return TreeEntry{
			Name: name,
			Kind: EntryKindDirectory,
			Mode: mode,
			Size: 0,
			Hash: dirHash,
		}, nil

	default:
		// Regular file
		if b.fileCount >= b.opts.maxFiles {
			return TreeEntry{}, ErrTooManyFiles
		}

		size := info.Size()
		if size > b.opts.maxFileSize {
			return TreeEntry{}, fmt.Errorf("%w: %s (%d bytes)", ErrFileTooLarge, relPath, size)
		}

		hash, err := hashFile(absPath)
		if err != nil {
			return TreeEntry{}, fmt.Errorf("hash file %s: %w", relPath, err)
		}

		b.files[hash] = &FileRef{
			Path: absPath,
			Size: uint64(size),
			Hash: hash,
		}
		b.fileCount++
		b.totalBytes += uint64(size)

		return TreeEntry{
			Name: name,
			Kind: EntryKindFile,
			Mode: mode,
			Size: uint64(size),
			Hash: hash,
		}, nil
	}
}

// hashFile computes the BLAKE3-256 hash of a file's contents.
func hashFile(path string) ([32]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return [32]byte{}, err
	}
	defer func() { _ = f.Close() }()

	h := blake3.New()
	if _, err := io.Copy(h, f); err != nil {
		return [32]byte{}, err
	}

	var hash [32]byte
	copy(hash[:], h.Sum(nil))
	return hash, nil
}

// serializeTree serializes a list of TreeEntry to msgpack.
// Uses numeric field tags matching the TreeEntry struct tags.
func serializeTree(entries []TreeEntry) ([]byte, error) {
	buf := &bytes.Buffer{}
	enc := msgpack.NewEncoder(buf)
	enc.SetSortMapKeys(true)

	if err := enc.Encode(entries); err != nil {
		return nil, err
	}

	return buf.Bytes(), nil
}

// DeserializeTree deserializes msgpack bytes to TreeEntry slice.
func DeserializeTree(data []byte) ([]TreeEntry, error) {
	var entries []TreeEntry
	if err := msgpack.Unmarshal(data, &entries); err != nil {
		return nil, err
	}
	return entries, nil
}
