# Clodex Behavioral Contract

When clodex mode is active (`/clodex-toggle`), these rules apply:

## The Three Rules
1. **Read freely**: Read, Grep, Glob, WebFetch, WebSearch -- without restriction
2. **Write source code via Codex**: All source code changes go through dispatch.sh -> Codex agents
3. **Edit non-code directly**: Markdown, JSON, YAML, config files, and /tmp/ files can be edited normally

**Exception**: Git operations (add, commit, push) are Claude's responsibility -- do them directly.

## Allowed Direct Edits (not blocked by hook)
`*.md`, `*.json`, `*.yaml`, `*.yml`, `*.toml`, `*.txt`, `*.csv`, `*.xml`, `*.html`, `*.css`, `*.svg`, `/tmp/*`, dotfiles

## Allowed Bash (read-only)
`git status/diff/log/show`, `go build/test`, `make test`, `npm test`, `pytest`, `cat/head/tail/wc/ls/find`, `codex exec resume`

## Must Dispatch via Codex (source code)
Source file creation/modification/deletion (`*.go`, `*.py`, `*.ts`, `*.js`, `*.rs`, `*.java`, `*.rb`, `*.c`, `*.cpp`, `*.h`, `*.swift`, `*.kt`, `*.sh`)
