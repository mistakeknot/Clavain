---
artifact_type: brainstorm
bead: iv-test1
stage: discover
---
# Test Feature Brainstorm

## Problem Statement

This is the problem statement section with enough words to pass the minimum word count
threshold. We need to validate that the handoff contract system correctly identifies
required sections in brainstorm documents. The problem is that currently artifacts are
only checked for existence, not content quality. This leads to downstream stages receiving
incomplete input and wasting tokens on recovery. We need structured validation.

## Research

Research into existing artifact validation patterns shows that frontmatter-based
validation is well-established in static site generators. Hugo, Jekyll, and Obsidian
all use YAML frontmatter for document metadata. Applying this pattern to sprint
artifacts gives us self-describing documents that can be validated programmatically.
The key insight is that section presence correlates strongly with artifact quality.

## Design Options

There are several approaches to solving this problem. Option A uses frontmatter
schemas with local validation. Option B uses sidecar manifest files. Option C
delegates entirely to the kernel. We recommend Option A for its simplicity and
backward compatibility with existing artifacts.

## Tradeoffs

The main tradeoff is between validation strictness and adoption friction. Too strict
and every sprint gets blocked. Too loose and the validation is meaningless. Shadow
mode provides a pragmatic middle ground — validate and warn without blocking advancement.
