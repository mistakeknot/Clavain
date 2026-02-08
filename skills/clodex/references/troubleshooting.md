# Common Issues

| Problem | Solution |
|---------|----------|
| GOCACHE permission denied | Add `GOCACHE=/tmp/go-build-cache` to prompt |
| Agent test hangs | Scope test commands: `-run`, `-short`, `-timeout=60s` |
| Output file empty | Check `~/.codex/sessions/` for transcript |
| Agent over-engineers | Add "keep it minimal" to constraints |
| Agent reformats code | Add "do not reformat unchanged code" |
| Agent touches wrong files | List files explicitly in constraints |
| Two agents conflict | Check file overlap before dispatching |
| Agent commits despite "don't" | Use `workspace-write` sandbox, always `git status` after |
