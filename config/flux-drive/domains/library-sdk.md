# Library / SDK Domain Profile

## Detection Signals

Primary signals (strong indicators):
- Directories: `src/`, `lib/`, `examples/`, `docs/`, `api/`
- Files: `package.json`, `Cargo.toml`, `go.mod`, `setup.py`, `pyproject.toml`, `*.gemspec`, `*.podspec`, `CHANGELOG.md`, `CONTRIBUTING.md`
- Frameworks: (language-agnostic — detected by package manifest and documentation patterns)
- Keywords: `public_api`, `export`, `semver`, `breaking_change`, `backward_compatible`, `deprecate`, `generic`, `interface`, `trait`

Secondary signals (supporting):
- Directories: `benchmarks/`, `fixtures/`, `types/`, `internal/`
- Files: `LICENSE`, `*.d.ts`, `index.ts`, `mod.rs`, `__init__.py`
- Keywords: `type_definition`, `re_export`, `pub(crate)`, `__all__`, `module.exports`

## Injection Criteria

When `library-sdk` is detected, inject these domain-specific review bullets into each core agent's prompt.

### fd-architecture

- Check that the public API surface is minimal and intentional — only expose what consumers need, keep internals private
- Verify that the library has a clear extension mechanism (plugins, middleware, hooks) rather than forcing consumers to fork
- Flag circular dependencies between modules — library consumers shouldn't need the entire package for one feature
- Check that the dependency tree is minimal (libraries with heavy transitive deps cause version conflicts in consumer projects)
- Verify that the library supports tree-shaking or selective imports (consumers shouldn't pay for features they don't use)

### fd-safety

- Check that user-supplied inputs are validated at the public API boundary (don't trust caller data shapes or ranges)
- Verify that the library doesn't execute arbitrary code from config files or data inputs (no eval/exec on user strings)
- Flag APIs that accept file paths without documenting or restricting access scope (path traversal via library misuse)
- Check that default configurations are secure (opt-in to dangerous features, not opt-out)
- Verify that error messages from the library don't leak internal implementation details to end users

### fd-correctness

- Check that public API types are precise — use union types/enums over stringly-typed parameters, optional vs required is accurate
- Verify that the library is re-entrant and thread-safe where documented, or clearly states single-threaded requirements
- Flag mutable global state — library-level globals create hidden coupling and make testing impossible for consumers
- Check that generic/template constraints are tight enough to produce useful error messages (not "type X doesn't implement Y" 3 layers deep)
- Verify that deprecated APIs still work correctly until removal — deprecation means "will be removed", not "might be broken"

### fd-quality

- Check that every public type, function, and method has documentation with usage examples
- Verify that error types are specific and documented — consumers need to match on error kinds, not parse error strings
- Flag inconsistent naming across the API surface (mix of get/fetch/retrieve, or create/new/make for the same pattern)
- Check that CHANGELOG follows Keep a Changelog format with entries categorized by Added/Changed/Deprecated/Removed/Fixed
- Verify that examples in docs are tested (doctest, mdbook test, or CI-compiled example directory)

### fd-performance

- Check that hot paths avoid allocations — reuse buffers, accept slices/references instead of owned types where possible
- Flag APIs that force consumers into inefficient patterns (returning Vec when iterator would allow streaming)
- Verify that benchmarks exist for performance-critical paths and are run in CI (detect regressions before release)
- Check that the library doesn't do unnecessary work on initialization (lazy-init expensive resources)
- Flag hidden O(n) operations in APIs that look O(1) (e.g., len() that traverses a linked list)

### fd-user-product

- Check that getting-started documentation works end-to-end (copy-paste the example, it compiles and runs)
- Verify that migration guides exist for breaking version changes (consumers need step-by-step upgrade instructions)
- Flag missing error context — when the library returns an error, the consumer should understand what they did wrong
- Check that the README includes: what the library does, installation, minimal example, link to full docs
- Verify that common use cases have dedicated examples (not just API reference — show how pieces compose)

## Agent Specifications

These are domain-specific agents that `/flux-gen` can generate for library/SDK projects. They complement (not replace) the core fd-* agents.

### fd-api-surface

Focus: Public API design, backward compatibility, type safety, documentation coverage.

Persona: You are a library API surface reviewer — you design for the developer who will use this API for years and curse every breaking change.

Decision lens: Prefer smaller, composable API surfaces over feature-rich interfaces. Every public symbol is a maintenance commitment.

Key review areas:
- Check public API exports include only intended stable symbols, and flag accidental exposure of internal types.
- Verify API changes map to semantic versioning rules (patch, minor, major) based on compatibility impact.
- Validate type signatures are precise enough to prevent misuse while remaining ergonomic for common calls.
- Confirm each public item has documentation covering purpose, parameters, returns, and failure modes.
- Ensure compatibility tests cover supported old and new version combinations and detect integration breaks.

### fd-consumer-experience

Focus: Onboarding, error messages, examples, integration patterns, ecosystem compatibility.

Persona: You are a consumer experience reviewer — you catch breaking changes before they ship as patch bumps and ensure upgrade paths are documented and tested.

Decision lens: Prefer backward-compatible evolution over clean redesigns. A breaking change in a minor release erodes trust faster than a missing feature.

Key review areas:
- Check first-use flow reaches a working example from install with minimal required configuration.
- Verify consumer-facing errors include cause and concrete remediation steps with relevant docs links or commands.
- Validate examples cover core use cases and reflect current API signatures and best practices.
- Confirm dependency versions are compatible with target framework versions listed in support policy.
- Ensure migration guides describe breaking changes, replacement APIs, and stepwise upgrade actions.
