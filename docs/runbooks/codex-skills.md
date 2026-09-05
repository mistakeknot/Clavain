# Codex skill discovery budget

Keep one discoverable copy per capability, and measure the running host before
disabling useful workflows. The warning about shortened descriptions concerns
the initial catalog, not truncated `SKILL.md` instructions.

Alignment: reduce redundant context while preserving useful routing and safety constraints.
Conflict/Risk: over-curation can hide workflows; prefer reversible, user-selected changes.

## What to measure

From a Clavain checkout, with Node 18+ and Codex installed:

```bash
node scripts/codex-skill-audit.mjs --cwd /absolute/project/path
node scripts/codex-skill-audit.mjs --cwd /absolute/project/path --output /tmp/new-skill-audit.json
node --test scripts/tests/codex-skill-audit.test.mjs
```

The audit queries the installed CLI's `skills/list` with `forceReload: true`.
It submits no model turn, changes no configuration, reports loader errors,
and refuses to overwrite an existing evidence file. Duplicate names are
candidates for inspection, **not** proof that their contents are equivalent.
Compare the entire skill directories, including references and scripts, before
disabling either copy. Never disable a system/plugin skill merely because its
name or description resembles a local skill.

The report measures Unicode characters in full names, descriptions, and paths.
It is not an exact token count or a reconstruction of the rendered prompt:
Codex can alias paths, shorten descriptions, and load additional plugin skills
after MCP startup. Explicit-only skills may remain in `skills/list`.
Verify the actual CLI's first turn too. `codex exec --json` did not surface the
catalog warning in the September 5 probe, while the interactive TUI did.
Do not infer that the warning disappeared from a successful headless run.

## Curation order

1. Remove duplicate discovery through reversible per-path disablement. Preserve
   the retained copy and existing configuration. Do not delete skill trees.
2. Keep concise capability-and-trigger descriptions. Put detailed procedures in
   the body and conditional material in references. Do not mass-truncate text
   or rewrite provider-managed caches; those edits are fragile on updates.
3. Keep every unique Sylveste capability eligible for automatic selection. Do
   not hide specialist engines, disable plugins, or add explicit-only policy to
   meet the catalog allowance. Preserve the 13 verified duplicate-path overrides.
4. Audit older companion links against canonical skill directories, including
   references, scripts, assets, and cross-tool metadata. Refresh only verified
   compatible targets after their producer commits are pushed. Preserve divergent
   local content and track unresolved upgrades separately.
5. Test the default allowance after deduplication and description cleanup. If it
   shortens the runtime catalog, test increasing 500-token steps up to 10,000.
   Require repeated first-turn passes at the lowest candidate and repeat the
   immediately lower failure. Leave the setting unset if default passes; if the
   cap still shortens descriptions, retain every capability and report the limit.
   Do not suppress warnings or change model context settings.

Disable a specific local entry using its resolved path from the inventory:

```toml
[[skills.config]]
path = "/absolute/path/to/redundant-skill/SKILL.md"
enabled = false
```

Restart Codex after editing configuration. Roll back by removing only the
selected override or setting it to `true`; do not restore a whole old config
over unrelated changes. A disabled duplicate stays disabled if the retained
copy later disappears, so re-audit after installs, updates, or path changes.

OpenAI documents a default catalog allowance of 2% of model context and an
explicit `skills.max_context_tokens` setting capped at 10,000. Raising that
setting trades more prompt space for fuller discovery; it is not a reduction
in overhead and should not be the first response to duplication.

## Verified Mac change — September 5, 2026

Codex 0.153.3, Astra base configuration, CWD `~/projects`:

| Measurement | Before | After duplicate disablement |
|---|---:|---:|
| Enabled entries from fresh `skills/list` | 115 | 102 |
| Unique enabled names in that inventory | 102 | 102 |
| Full metadata characters, excluding rendering syntax | 36,096 | 30,377 |
| Duplicate enabled names | 13 | 0 |
| Loader errors | 0 | 0 |

This removes 5,719 metadata characters (15.8%). All 13 duplicate directory
pairs were byte-identical, including their supporting files. The redundant
`~/.codex/skills/` copies of these skills were disabled; their
`~/.agents/skills/` copies remain enabled:

`agents-sdk`, `cloudflare`, `cloudflare-email-service`, `cloudflare-one`,
`cloudflare-one-migrations`, `durable-objects`, `sandbox-migrate-to-next`,
`sandbox-next`, `sandbox-stable`, `turnstile-spin`, `web-perf`,
`workers-best-practices`, and `wrangler`.

The post-deduplication inventory also reports one pre-existing disabled
`interplug:troubleshoot` entry: 14 disabled inventory entries include these 13
duplicate overrides. A separate pre-existing GitHub plugin override is retained
in configuration but is not in that startup inventory. Inventory counts and
configuration-entry counts describe different surfaces.

Every pre-existing config byte was preserved. No unique skill, plugin, model,
approval rule, MCP setting, or context budget changed. The backup remains local
at `/private/tmp/codex-skills.UK5HMC/config.before.toml`; it is not a public
artifact and must not be committed. This backup is temporary, not permanent
recovery storage; the per-path rollback above needs no backup.

The interactive first-turn probe still showed the shortening warning and
listed 112 skill entries after runtime plugin loading. Therefore this is a
verified reduction, **not** a claim that the warning is fixed. Both the
headless and interactive probes returned `OK` without tool use. They are
diagnostics, not evidence of skill-selection quality or canary task acceptance.

Track this work in `Sylveste-x7va`. The changed discovery configuration is a
new evidence boundary for `Sylveste-kbh5`; do not pool future enrolled work
with a different skill configuration without recording that distinction.
Do not run the global Codex installer or bootstrap while `Sylveste-8nov`'s
MCP-schema discrepancy remains unresolved. Older companion links require a scoped compatibility audit; they are not
permission to run a global installer here.

## Current official guidance

- [Build skills](https://learn.chatgpt.com/docs/build-skills): progressive disclosure, precise descriptions, discovery roots, per-skill disablement, invocation policy.
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference): `skills.config` and `skills.max_context_tokens`.
- [App Server](https://learn.chatgpt.com/docs/app-server): `skills/list`, force reload, and per-path configuration.

Recheck these sources and the invoked CLI on later versions. Neither a count
from another host nor an old source checkout establishes current loading.

## Always-on OODARCS and narrow instruction sync

The source-owned `config/codex-instructions.md` is the canonical managed block.
Clavain's installer applies it to the Codex global instructions maintained in
dotfiles; the skill router supplies conditional workflow detail. Synthesize
reconciles learning with prior evidence and goals and updates conclusions or next
priorities within scope. The operating contract does not migrate OODARC telemetry,
grant memory-write authority, or require a full lifecycle for trivial requests.

```bash
bash scripts/install-codex.sh sync-instructions --source /absolute/Clavain --dry-run
bash scripts/install-codex.sh sync-instructions --source /absolute/Clavain
python3 -m unittest discover -s scripts/tests -p test_sync_instructions.py
```

The narrow action requires a local source, supports `--codex-home` for isolated
fixtures, and never fetches, installs plugins/hooks, configures MCP, or invokes
refresh. It replaces only the existing Clavain managed block (or appends it if
absent), follows instruction symlinks, preserves unrelated bytes and target mode,
and rejects malformed/duplicate markers or dangling links without writing. Dry
runs print the diff and create nothing. Dotfiles' one-time removal of the separate
Compound tool map and stale routing text is an explicit source edit, not behavior
hidden in the sync command. Future runs touch only Clavain's block.
The instruction target directory must already exist. Broad installation retains
content backups and checks the new instruction dependencies before consumer
changes; those paths remain unused during this rollout.

Review and push producers before applying the installed consumer update. The Mac
is the first rollout target; do not deploy to zklw automatically. Existing source
symlinks can expose uncommitted edits immediately, so prepare and test candidates
in a separate staging directory until the review gate permits landing.
Before publishing, inspect actual refresh registration and producer autosync
markers on the target and other linked hosts. A shared Git push is not a host
rollout boundary when existing automation pulls it into live instructions. If
such wiring exists, retain the rollout gate until it is resolved within the
user's authority; do not silently deploy to another host.

## Acceptance fixtures and evidence

`docs/runbooks/oodarcs-fixtures.json` contains prompts without skill names and
separate acceptance criteria. Run baseline and candidate with the same invoked
CLI, model, effort, service tier, plugins, permission settings, and CWD class.
Only the instruction/catalog configuration and tested catalog allowance may vary.
Disable automatic source refresh for probes with `CLAVAIN_SESSION_REFRESH=0`;
do not run an installer as part of a probe. Use the same refresh setting in both
variants. Launch the interactive TUI without an initial prompt, wait for plugin
initialization, then submit the first prompt. Inspect the actual first-turn
catalog and tool calls. An immediate startup prompt may race plugin loading.

Record session ID, CLI version/path, source SHAs and staged patch digest, CWD,
model/effort, permission mode, plugin set, allowance, rendered catalog count and
shortening, selected skill paths, actual tools, final result/artifacts, input
usage, and acceptance verdict. Distinguish full inventory characters from rendered
catalog characters and actual model input tokens. Count differences across hosts
or loading stages are not evidence that capabilities were removed.

Test inside a repository and outside Git roots. Repeat failures, trivial and
restricted-authority cases, and the budget boundary. Resume a session after a
substantive result and introduce contradictory evidence: the conclusion or
priority must update explicitly without unauthorized persistence or scope growth.
A missing companion must not cause automatic installation. A blocked review must
not trigger a provider change. Skill reads and warning removal alone do not pass
behavioral acceptance; inspect useful, evidence-backed outcomes.

These probes are a new instruction/catalog evidence boundary for the Astra
canary, with **zero task-completion credit**. Keep model routing, release authority,
MCP configuration, and Astra promotion gates unchanged. Do not combine baseline
and candidate outcomes as if they used the same instructions.

Rollback only this change's managed block, individually selected links, and
catalog-budget override. Preserve unrelated current config; never restore a whole
old configuration file. The dotfiles cleanup can be reversed with its scoped Git
diff. Re-run both the inventory and interactive acceptance after future skill or
plugin updates.
