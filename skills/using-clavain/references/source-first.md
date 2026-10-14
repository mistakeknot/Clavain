# Source First

Read a dependency's installed source before you use its API. Memory of a library is often a different version from the one this repo pins, and a wrong guess compiles until it fails at runtime.

## Rule

Before writing code that calls a dependency, read the version this repo actually resolves:

1. Find the pinned version in the lockfile or manifest (`package-lock.json`, `pnpm-lock.yaml`, `go.sum`, `Cargo.lock`, `uv.lock`).
2. Read the installed copy at that version:
   - Node: `node_modules/<pkg>`. Read its `AGENTS.md` or `README` first, then the exported types and source.
   - Go: `$(go env GOMODCACHE)/<module>@<version>`.
   - Python: the package under the active environment's `site-packages`.
   - Rust: `~/.cargo/registry/src/*/<crate>-<version>`.
3. Use a documentation lookup tool (such as context7) only second, to find where to look or to fill gaps the source leaves. Check that it names the pinned version.
4. When memory, docs and the installed source disagree, the installed source wins. Compiler, type-checker, linter and test output outrank memory too: if they reject your call, change the call.

## When the installed package is not readable

Some packages ship only compiled output. Then read their published type declarations and changelog at the pinned version, and say in your report that the implementation source was not read. Do not guess at behavior the declarations do not show.

## What this does not change

- It adds no dependency and bumps no version. Dependency bumps stay with the repo's own upgrade process.
- It does not apply to the standard library of the language version you are already told to target.

Source: bead mk-3yqi5 (the source-first practice from rat-stack, bead mk-u93pn).
