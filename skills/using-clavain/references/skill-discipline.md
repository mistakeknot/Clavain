# Skill Discipline

**Proactive skill invocation is required.** When a skill matches the current task — even partially — invoke it before responding. Skills are designed to be triggered automatically; skipping a relevant skill degrades output quality.

## How to Access Skills

**In Claude Code:** Use the `Skill` tool. When you invoke a skill, its content is loaded and presented to you—follow it directly. Never use the Read tool on skill files.

**In Codex CLI:** Install Clavain skills with `bash ~/.codex/clavain/scripts/install-codex.sh install`. Codex discovers them from `~/.agents/skills/clavain/` on startup, so restart Codex after install.

## Red Flag

If you catch yourself thinking "I'll just do this without a skill" — STOP. Check for a matching skill first. Skills evolve; read the current version even if you "remember" it.
