// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package fstree

import (
	"context"
	"fmt"
	"io"
	"os"

	cxdb "github.com/strongdm/ai-cxdb/clients/go"
)

// UploadResult contains the result of uploading a snapshot.
type UploadResult struct {
	// RootHash is the BLAKE3-256 hash of the root tree object.
	RootHash [32]byte

	// TreesUploaded is the number of tree objects uploaded.
	TreesUploaded int

	// TreesSkipped is the number of tree objects already present.
	TreesSkipped int

	// FilesUploaded is the number of file blobs uploaded.
	FilesUploaded int

	// FilesSkipped is the number of file blobs already present.
	FilesSkipped int

	// BytesUploaded is the total bytes uploaded.
	BytesUploaded int64
}

// Upload uploads all tree objects and file blobs from a snapshot to the server.
// Returns the root hash which can be used to attach the snapshot to a turn.
func (s *Snapshot) Upload(ctx context.Context, client *cxdb.Client) (*UploadResult, error) {
	result := &UploadResult{
		RootHash: s.RootHash,
	}

	// Upload all tree objects first (they're already serialized)
	for hash, data := range s.Trees {
		wasNew, err := uploadBlob(ctx, client, hash, data)
		if err != nil {
			return nil, fmt.Errorf("upload tree %x: %w", hash[:8], err)
		}
		if wasNew {
			result.TreesUploaded++
			result.BytesUploaded += int64(len(data))
		} else {
			result.TreesSkipped++
		}
	}

	// Upload all file blobs
	for hash, ref := range s.Files {
		// Read file content
		content, err := readFile(ref.Path)
		if err != nil {
			return nil, fmt.Errorf("read file %s: %w", ref.Path, err)
		}

		wasNew, err := uploadBlob(ctx, client, hash, content)
		if err != nil {
			return nil, fmt.Errorf("upload file %s: %w", ref.Path, err)
		}
		if wasNew {
			result.FilesUploaded++
			result.BytesUploaded += int64(len(content))
		} else {
			result.FilesSkipped++
		}
	}

	// Upload all symlink targets
	for hash, target := range s.Symlinks {
		wasNew, err := uploadBlob(ctx, client, hash, []byte(target))
		if err != nil {
			return nil, fmt.Errorf("upload symlink target %s: %w", target, err)
		}
		if wasNew {
			result.FilesUploaded++ // Count symlinks with files
			result.BytesUploaded += int64(len(target))
		} else {
			result.FilesSkipped++
		}
	}

	return result, nil
}

// uploadBlob uploads a single blob to the server.
func uploadBlob(ctx context.Context, client *cxdb.Client, hash [32]byte, data []byte) (bool, error) {
	_, wasNew, err := client.PutBlobIfAbsent(ctx, data)
	return wasNew, err
}

// readFile reads the entire contents of a file.
func readFile(path string) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = f.Close() }()
	return io.ReadAll(f)
}

// UploadAndAttach captures a filesystem snapshot, uploads it, and attaches it to a turn.
// This is a convenience function that combines Capture, Upload, and AttachFs.
func UploadAndAttach(ctx context.Context, client *cxdb.Client, root string, turnID uint64, opts ...Option) (*UploadResult, error) {
	// Capture snapshot
	snap, err := Capture(root, opts...)
	if err != nil {
		return nil, fmt.Errorf("capture: %w", err)
	}

	// Upload all blobs
	result, err := snap.Upload(ctx, client)
	if err != nil {
		return nil, fmt.Errorf("upload: %w", err)
	}

	// Attach to turn
	_, err = client.AttachFs(ctx, &cxdb.AttachFsRequest{
		TurnID:     turnID,
		FsRootHash: snap.RootHash,
	})
	if err != nil {
		return nil, fmt.Errorf("attach: %w", err)
	}

	return result, nil
}

// CaptureAndUpload captures a filesystem snapshot and uploads it to the server.
// Returns the snapshot and upload result. The snapshot can be attached to a turn later.
func CaptureAndUpload(ctx context.Context, client *cxdb.Client, root string, opts ...Option) (*Snapshot, *UploadResult, error) {
	// Capture snapshot
	snap, err := Capture(root, opts...)
	if err != nil {
		return nil, nil, fmt.Errorf("capture: %w", err)
	}

	// Upload all blobs
	result, err := snap.Upload(ctx, client)
	if err != nil {
		return nil, nil, fmt.Errorf("upload: %w", err)
	}

	return snap, result, nil
}
