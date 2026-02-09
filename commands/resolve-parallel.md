---
name: resolve-parallel
description: Resolve all TODO comments using parallel processing
argument-hint: "[optional: specific TODO pattern or file]"
---
Resolve all TODO comments in the codebase using parallel processing.

## Source

Gather TODO comments from the codebase using Grep to find `TODO` patterns.

## Workflow

### 1. Analyze

Search for TODO comments across the codebase. Group by file and dependency.

### 2. Plan

Create a TodoWrite list of all items. Check for dependencies — if one fix requires another to land first, note the order. Output a brief mermaid diagram showing the parallel/sequential flow.

### 3. Implement (PARALLEL)

Spawn a `pr-comment-resolver` agent for each independent item in parallel. Wait for sequential dependencies to complete before spawning dependent items.

### 4. Commit

Commit changes. Do not push unless asked.
