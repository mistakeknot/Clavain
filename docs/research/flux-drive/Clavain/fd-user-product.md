### Findings Index
- P0 | P0-1 | "Command Naming" | /triage references non-existent /resolve_todo_parallel command
- P1 | P1-1 | "Skill Discoverability" | 3 skills missing from README and routing table (prompterpeer, winterpeer, splinterpeer)
- P1 | P1-2 | "Command Naming" | /review vs /flux-drive vs /quality-gates vs /plan-review — four review entry points with unclear selection criteria
- P1 | P1-3 | "Command Naming" | /work vs /execute-plan distinction requires reading command internals to understand
- P1 | P1-4 | "First-Run Experience" | No guided first-use path after install — user goes from /setup to a wall of 24 commands
- P1 | P1-5 | "Changelog Command" | /changelog references non-existent EVERY_WRITE_STYLE.md file
- P1 | P1-6 | "Cognitive Load" | Routing table is injected every session but is 113 lines of dense tables — no progressive disclosure
- IMP | IMP-1 | "First-Run Experience" | Add a /quickstart command that guides a first-time user through one complete cycle
- IMP | IMP-2 | "Command Naming" | Consolidate review entry points with argument-based routing instead of 4 separate commands
- IMP | IMP-3 | "Skill Discoverability" | Add a /help or /commands command that groups commands by workflow stage
- IMP | IMP-4 | "README Quality" | Add a "Getting Started in 5 Minutes" section to README between Install and My Workflow
- IMP | IMP-5 | "Routing Table" | Replace dense routing table with a decision-tree heuristic that asks 2-3 questions
- IMP | IMP-6 | "Roadmap" | Prioritize fixing phantom references and naming confusion before adding new features
Verdict: needs-changes

### Summary (3-5 lines)

The primary user is a developer installing Clavain to enhance their Claude Code workflow. Their job is to get from "installed" to "productive" as fast as possible, and to find the right command when they need it. Clavain has a genuine productivity proposition — the /lfg lifecycle and flux-drive multi-agent review are novel and valuable. However, the current state has a P0 phantom command reference, four overlapping review entry points that confuse selection, three skills invisible in documentation, and a first-run experience that drops users into 34 skills and 24 commands with no guided path. The README is well-written for someone who already understands the system but does not serve a new user trying to accomplish their first task.

### Issues Found

**P0-1: /triage references non-existent /resolve_todo_parallel command** (independently confirmed from codebase analysis)

File: `/root/projects/Clavain/commands/triage.md`, lines 199-209

The `/triage` command's "Next Steps" section tells users to run `/resolve_todo_parallel` to resolve approved todos. This command does not exist. The `upstreams.json` file shows it was mapped from a compound-engineering upstream (`commands/resolve_todo_parallel.md` -> `commands/resolve-todo-parallel.md`), but the actual file was never created or was dropped during consolidation. The correct command is `/resolve`. A user who completes a triage session and follows the suggested next step will hit a dead end with no error recovery guidance.

Evidence: `grep -r "resolve_todo_parallel" commands/` returns only `triage.md`. No file `commands/resolve-todo-parallel.md` exists. The `/resolve` command (`commands/resolve.md`) auto-detects todo files and handles the same workflow.

Fix: Replace `/resolve_todo_parallel` references in `triage.md` with `/clavain:resolve` (which auto-detects todo sources).

---

**P1-1: 3 skills missing from README and routing table** (independently confirmed)

Files:
- `/root/projects/Clavain/README.md` (skills table, lines 99-143)
- `/root/projects/Clavain/skills/using-clavain/SKILL.md` (routing table)

The skills `prompterpeer`, `winterpeer`, and `splinterpeer` exist as directories under `skills/` (counting toward the "34 skills" total) but are absent from both the README skills table and the `using-clavain` routing table. All three are redirect stubs pointing to `interpeer` modes (deep, council, mine respectively). Their bodies say things like "This skill has been merged into interpeer. Load the interpeer skill and follow the Mode: deep section."

This creates two problems:
1. A user searching the README or routing table for "council review" or "disagreement extraction" will not find these terms — they must know to look under `interpeer`.
2. The "34 skills" count includes these stubs, which inflates the apparent surface area. If they are redirects, either remove them from the count or list them as aliases.

Previous review (2026-02-09) flagged skill discoverability as a systemic problem. This is independently confirmed — the gap exists in the actual files.

---

**P1-2: Four review entry points with unclear selection criteria**

Files:
- `/root/projects/Clavain/commands/review.md`
- `/root/projects/Clavain/commands/flux-drive.md`
- `/root/projects/Clavain/commands/quality-gates.md`
- `/root/projects/Clavain/commands/plan-review.md`

A user who wants to "review something" faces four commands:

| Command | What it actually does |
|---------|----------------------|
| `/review` | PR-oriented multi-agent review (expects PR number/URL/branch) |
| `/flux-drive` | Document or repo review with intelligent triage |
| `/quality-gates` | Diff-based review of current changes (git diff) |
| `/plan-review` | Plan-specific 3-agent review |

The naming does not encode these distinctions. A user thinking "I want to review my code changes" could reasonably pick any of `/review`, `/quality-gates`, or `/flux-drive`. The routing table in `using-clavain/SKILL.md` lists all four under the "Review" stage, separated only by whether you are reviewing docs vs code — but `/review` and `/quality-gates` both review code, and `/flux-drive` can review both docs and repos.

The `/work` command (line 219-227) tries to clarify by saying "Run `/clavain:quality-gates` only when [conditions]" but this guidance is buried inside a different command, not at the point of selection.

The README lifecycle diagram shows `/flux-drive` as "review plan" and `/review` as "review code" — this is the clearest framing but contradicts `/flux-drive`'s actual capability (it can review repos, not just plans).

---

**P1-3: /work vs /execute-plan distinction requires reading command internals**

Files:
- `/root/projects/Clavain/commands/work.md`
- `/root/projects/Clavain/commands/execute-plan.md`

Both commands take a plan file as input and execute it. The `execute-plan.md` file (line 7) explains: "Use /execute-plan for batch execution with architect review checkpoints between batches. Use /work for autonomous feature shipping." The `work.md` file (line 15) repeats the same guidance.

This distinction ("batch with checkpoints" vs "autonomous") is meaningful but not discoverable from command names. `/work` sounds like a generic "do the work" command. `/execute-plan` sounds like the specific "execute this plan file" command. In practice, both do the same thing with different levels of oversight. A new user would pick `/execute-plan` if they have a plan file, which may not be what they want.

The README table describes `/work` as "Execute a plan autonomously" and `/execute-plan` as "Execute plan in batches with checkpoints" — this is clearer but still requires reading both descriptions to compare.

---

**P1-4: No guided first-use path after install** (independently confirmed — primed by prior finding about bootstrap experience)

Files:
- `/root/projects/Clavain/commands/setup.md`
- `/root/projects/Clavain/README.md`

The previous review (2026-02-09) flagged that first-time users encounter no `.claude/flux-drive/` directory, no ad-hoc agents, and no qmd index. This finding is independently confirmed with additional evidence:

After running `/setup`, the user sees a status table listing plugin counts and MCP server health, then "Next steps: Run `/clavain:lfg [task]`". But `/lfg` is the most complex command in Clavain — an 8-step lifecycle that chains 7 other commands. Sending a new user directly to `/lfg` is like telling someone who just installed an IDE to run the full CI pipeline.

What is missing:
1. A command that demonstrates one small, complete cycle (e.g., "brainstorm a small improvement, see the plan, see a review")
2. Any explanation of what will happen when `/lfg` is invoked (the user does not know it will take 8 steps)
3. A recommendation for something simpler first (e.g., "Try `/clavain:brainstorm improve the README` to see how Clavain's brainstorming works")

The README's "My Workflow" section is excellent for understanding the system conceptually but does not provide a concrete first task a user can try in under 2 minutes to experience value.

---

**P1-5: /changelog references non-existent EVERY_WRITE_STYLE.md file**

File: `/root/projects/Clavain/commands/changelog.md`, line 101

The command instructs: "Now review the changelog using the EVERY_WRITE_STYLE.md file and go one by one to make sure you are following the style guide. Use multiple agents, run in parallel to make it faster."

This file does not exist in the Clavain repo. It appears to be a remnant from the compound-engineering upstream (Every.to's internal style guide). The command will silently fail to find this file and either skip the style review or produce an error. A user running `/changelog` will see the agent search for a non-existent file, wasting time and creating confusion.

Evidence: `grep -r "EVERY_WRITE_STYLE" /root/projects/Clavain/` returns only `commands/changelog.md`.

Fix: Either remove the style guide reference entirely or replace it with a Clavain-specific changelog style section embedded in the command.

---

**P1-6: Routing table injected every session is 113 lines of dense tables with no progressive disclosure** (independently confirmed)

File: `/root/projects/Clavain/skills/using-clavain/SKILL.md`

The entire `using-clavain` skill (113 lines of tables, rules, and heuristics) is injected into every session via the SessionStart hook. This means every conversation starts with ~3,000 tokens of routing context regardless of whether the user needs it.

For new users, this wall of tables is opaque — it uses internal jargon ("fd-architecture", "flux-drive", "splinterpeer", "clodex") that has not been explained yet. For experienced users, the routing heuristic on lines 90-96 is the only part they need, and it works fine. But the mandatory injection of the full table means every session pays the context cost.

The previous review (2026-02-09) flagged routing table usability as a systemic problem. This is independently confirmed — the file is dense and its injection is unconditional.

### Improvements Suggested

**IMP-1: Add a /quickstart command for first-time users**

Create a `/quickstart` command that guides a user through one complete small cycle:
1. Pick a trivial improvement (e.g., "add a comment to the README" or "improve an error message")
2. Run `/brainstorm` on it (shows the brainstorm phase)
3. Run `/write-plan` (shows the planning phase)
4. Skip execution (too early for that)
5. Run `/flux-drive` on the plan (shows the review system)
6. Summarize what happened and what each command did

This gives the user a mental model of the lifecycle in under 5 minutes without committing to a full `/lfg` run. The `/setup` command's "Next steps" should recommend `/quickstart` instead of `/lfg`.

Rationale: Time-to-first-value is the single biggest predictor of plugin adoption. Currently, a user must understand the entire system before they can use any part of it productively.

---

**IMP-2: Consolidate review entry points with clearer naming or argument-based routing**

Instead of four separate commands, consider either:

Option A: Keep `/flux-drive` as the single review entry point with argument-based routing:
- `/flux-drive <plan-file>` -> plan review (currently `/plan-review`)
- `/flux-drive <directory>` -> repo review (current behavior)
- `/flux-drive` (no args, on PR branch) -> PR review (currently `/review`)
- `/flux-drive --quick` or `/quality-gates` -> quick diff review

Option B: Rename for clarity:
- `/review-plan` (not `/plan-review` — verb-noun is more natural than noun-verb)
- `/review-pr` (not `/review` — disambiguates from general "review")
- `/review-diff` or keep `/quality-gates`
- `/flux-drive` stays for intelligent document/repo review

Either approach reduces the "which review command?" decision from 4-way to 2-way or eliminates it entirely.

---

**IMP-3: Add a /help command that groups commands by workflow stage**

Currently, users must read the README or the routing table to find commands. A `/help` command that presents commands grouped by what the user wants to do would reduce friction:

```
Explore:  /brainstorm
Plan:     /write-plan, /plan-review
Execute:  /work, /execute-plan, /codex-first
Review:   /flux-drive (docs/repo), /review (PR), /quality-gates (diff)
Ship:     /changelog, /resolve
Debug:    /repro-first-debugging
Meta:     /setup, /heal-skill, /create-agent-skill
```

This is a 15-line command that dramatically improves discoverability. Users can also say "help review" to filter by stage.

---

**IMP-4: Add a "Getting Started in 5 Minutes" section to README**

The README currently goes from "Install" (2 lines) directly to "My Workflow" (a conceptual essay). Insert a section between them that gives a concrete first task:

```markdown
## Getting Started

After installing, try this in any project:

1. `/clavain:brainstorm improve error handling in this project`
   - Clavain will research your repo, ask clarifying questions, and propose approaches
2. `/clavain:write-plan`
   - Creates a structured implementation plan from the brainstorm
3. `/clavain:flux-drive docs/plans/<the-plan-file>.md`
   - Reviews the plan with multiple specialized agents

That is the core cycle. For the full autonomous lifecycle, use `/clavain:lfg <task>`.
```

This serves users who learn by doing rather than by reading.

---

**IMP-5: Replace dense routing table injection with a lighter heuristic**

Instead of injecting the full 113-line `using-clavain/SKILL.md` into every session, inject a shorter decision-tree version (30 lines) that covers the 80% case:

```
When a user message arrives:
- "build/implement/add" -> brainstorming first, then writing-plans, then work
- "fix bug/debug"       -> systematic-debugging
- "review"              -> flux-drive (docs/repo) or quality-gates (code diff)
- "plan"                -> writing-plans
- "ship/deploy/merge"   -> landing-a-change
- "what should we"      -> brainstorming

For the full routing table, invoke skill: using-clavain
```

The full table remains available on-demand but does not consume context in every session. This reduces per-session overhead by ~2,500 tokens while preserving discoverability.

---

**IMP-6: Prioritize fixing phantom references and naming confusion before adding new features**

The current roadmap (inferred from recent commits) focuses on adding flux-drive capabilities, upstream sync, and Codex integration. Before these, the following maintenance items would have higher user impact:

1. Fix `/resolve_todo_parallel` phantom reference in `/triage` (P0, 5 minutes)
2. Fix `EVERY_WRITE_STYLE.md` phantom reference in `/changelog` (P1, 5 minutes)
3. Add `prompterpeer`/`winterpeer`/`splinterpeer` to README as interpeer aliases (P1, 10 minutes)
4. Clarify review command selection in the routing table or README (P1, 30 minutes)

Total effort: under 1 hour. These eliminate dead ends that damage first-use trust.

### Overall Assessment

Clavain is a genuinely novel and well-structured Claude Code agent rig with a strong productivity proposition. The /lfg lifecycle and flux-drive multi-agent review represent real workflow innovation. However, the gap between "installed" and "productive" is too wide: phantom command references create dead ends, four review entry points confuse selection, three skills are invisible in documentation, and the first-run experience sends users directly to the most complex command. Fixing the P0 and P1 issues above requires under 2 hours of work and would meaningfully improve adoption confidence. The improvements (especially IMP-1 through IMP-4) should be considered high-priority roadmap items because they directly address the question "can a new user succeed with this plugin?"
<!-- flux-drive:complete -->
