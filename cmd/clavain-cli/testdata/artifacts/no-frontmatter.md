# Brainstorm Without Frontmatter

## Problem Statement

This brainstorm document has all the required sections but lacks YAML frontmatter.
The validator should still be able to check content sections and report that
frontmatter is missing. This tests graceful degradation when artifacts were created
before the frontmatter convention was introduced. The content validation should
still run and provide useful feedback about section presence.

## Research

Research section is present with adequate content about the topic at hand.
We investigated multiple approaches and found relevant prior art in the
codebase and external documentation sources.

## Design Options

Option A is the recommended approach because it balances simplicity with
correctness. We can iterate on more sophisticated validation later.
