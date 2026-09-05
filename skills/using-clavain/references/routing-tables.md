# Conditional routing reference

Read this only when the quick router needs a domain or host-specific extension.
The current installed catalog is the authority for available names and paths;
these routes do not restrict automatic selection of any other unique capability.

## Domain extensions

| Need | Skill capability to resolve in the installed catalog |
|------|---------------------------------------------------|
| Unfamiliar multi-file code | `tldrs-agent-workflow` |
| Previous agent decisions | `alwe` |
| Research across sources | `interdeep:deep-research`, or an installed research skill whose depth matches the request |
| Documentation health | `interscribe:interscribe`, `interwatch:doc-watch` |
| Solved-problem documentation | `clavain:engineering-docs` |
| Roadmap or PRD | `interpath:artifact-gen` |
| Migration safety | `clavain:data-migration-expert` |
| Review findings | `clavain:pr-comment-resolver` |
| Deep review | `interflux:flux-engine`, `interflux:flux-review-engine`, `interflux:flux-melange-engine` according to the requested review |
| Cross-model opinion | `interpeer:interpeer-engine` |
| UI design or polish | `interform:distinctive-design`, `clavain:ui-polish` |
| Native runtime verification | `interhelm:runtime-diagnostics`, `interhelm:cuj-verification` |
| Skill authoring/audit | `skill-creator` for Codex, `interskill:skill` for Claude, `interskill:audit` |
| Plugin authoring/validation | `plugin-creator` for Codex, `interplug:create-plugin`, `interplug:validate` |
| Claude integration | `interdev:working-with-claude-code` |
| Codex configuration | `openai-docs` |
| Coordination when delegated work is authorized | `clavain:dispatching-parallel-agents`, `interlock:coordination-protocol` |

Process guidance determines how to work; domain guidance supplies the specialist
details. Read only what helps the next decision. Research and documentation are
substantive work in their own right and do not require a software sprint.

## Host adaptation

In **Codex**, use catalog paths, available tools, and supported CLIs. Loading an
engine skill does not make its Claude slash command a Codex API. If the procedure
requires a command document, resolve it in the installed companion's `commands/`
directory and read it; adapt its tool calls to the host while preserving gates.
Do not pretend an unavailable command ran.

In **Claude Code**, these installed command entrypoints remain useful:

| Action | Command |
|--------|---------|
| Route a newly selected engineering task | `/clavain:route` |
| Explicit full lifecycle | `/clavain:sprint` |
| Execute a plan | `/clavain:work` |
| Gate a finished diff | `/clavain:quality-gates` |
| Deep review | `/interflux:flux-drive` |
| Cross-model review | `/interpeer:interpeer` |
| Land verified work | `/clavain:land` |

Do not restart routing in an already active workflow. A command marked
`disable-model-invocation` remains user-invoked in that host; this does not disable
the companion skill's automatic Codex discovery. Required review and release
authority remain gates in either host. For missing companions, use the boundary
instructions in the main router instead of running an installer.
