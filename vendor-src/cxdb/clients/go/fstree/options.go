// Copyright 2025 StrongDM Inc
// SPDX-License-Identifier: Apache-2.0

package fstree

import "path/filepath"

// Option configures snapshot behavior.
type Option func(*options)

type options struct {
	excludePatterns []string
	excludeFn       func(path string, isDir bool) bool
	followSymlinks  bool
	maxFileSize     int64
	maxFiles        int
}

func defaultOptions() *options {
	return &options{
		excludePatterns: nil,
		followSymlinks:  false,
		maxFileSize:     100 * 1024 * 1024, // 100MB default max file size
		maxFiles:        100000,            // 100k files max
	}
}

// WithExclude adds glob patterns for paths to exclude.
// Patterns are matched against the relative path from the root.
// Examples: "*.log", ".git/**", "node_modules/**"
func WithExclude(patterns ...string) Option {
	return func(o *options) {
		o.excludePatterns = append(o.excludePatterns, patterns...)
	}
}

// WithExcludeFunc sets a custom exclusion function.
// Return true to exclude the path. Called for every file and directory.
func WithExcludeFunc(fn func(path string, isDir bool) bool) Option {
	return func(o *options) {
		o.excludeFn = fn
	}
}

// WithFollowSymlinks enables following symbolic links.
// By default, symlinks are captured as symlinks (their target path is stored).
// With this option, symlinks are dereferenced and their target content is captured.
// Circular symlinks are detected and skipped.
func WithFollowSymlinks() Option {
	return func(o *options) {
		o.followSymlinks = true
	}
}

// WithMaxFileSize sets the maximum file size to include.
// Files larger than this are skipped. Default is 100MB.
func WithMaxFileSize(bytes int64) Option {
	return func(o *options) {
		o.maxFileSize = bytes
	}
}

// WithMaxFiles sets the maximum number of files to include.
// Default is 100,000.
func WithMaxFiles(n int) Option {
	return func(o *options) {
		o.maxFiles = n
	}
}

// shouldExclude checks if a path should be excluded based on options.
func (o *options) shouldExclude(relPath string, isDir bool) bool {
	// Check custom function first
	if o.excludeFn != nil && o.excludeFn(relPath, isDir) {
		return true
	}

	// Check glob patterns
	for _, pattern := range o.excludePatterns {
		// Try direct match
		if matched, _ := filepath.Match(pattern, relPath); matched {
			return true
		}
		// Try matching just the base name
		if matched, _ := filepath.Match(pattern, filepath.Base(relPath)); matched {
			return true
		}
		// For ** patterns, do prefix matching on directories
		if isDir && len(pattern) > 3 && pattern[len(pattern)-3:] == "/**" {
			prefix := pattern[:len(pattern)-3]
			if matched, _ := filepath.Match(prefix, relPath); matched {
				return true
			}
		}
	}

	return false
}
