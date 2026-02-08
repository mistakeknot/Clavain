# Codex-First Behavioral Contract

When codex-first mode is active (`/clodex-toggle`), these rules apply:

## The Three Rules
1. **Read freely**: Read, Grep, Glob, WebFetch, WebSearch -- without restriction
2. **Write via Codex**: All code changes go through dispatch.sh -> Codex agents
3. **Bash discipline**: Read-only commands only. File-modifying Bash goes through Codex.

**Exception**: Git operations (add, commit, push) are Claude's responsibility -- do them directly.

## Allowed Bash (read-only)
`git status/diff/log/show`, `go build/test`, `make test`, `npm test`, `pytest`, `cat/head/tail/wc/ls/find`, `codex exec resume`

## Must Dispatch via Codex (file-modifying)
File creation/modification/deletion, `sed -i`, package installs
