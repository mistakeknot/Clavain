# CLI Tool Domain Profile

## Detection Signals

Primary signals (strong indicators):
- Directories: `cmd/`, `cli/`, `commands/`, `subcmd/`
- Files: `main.go`, `cli.*`, `Cargo.toml`
- Frameworks: Cobra, Clap, Click, argparse, Commander, Yargs, oclif, Bubble Tea, Charmbracelet, Inquirer
- Keywords: `subcommand`, `flag`, `argument`, `parse_args`, `terminal`, `stdin`, `stdout`, `exit_code`

Secondary signals (supporting):
- Directories: `internal/`, `pkg/`, `completions/`
- Files: `*.bash`, `*.zsh`, `*.fish` (shell completions), `man/*.1`
- Keywords: `cli`, `tty`, `isatty`, `color`, `spinner`, `progress_bar`, `prompt`

## Injection Criteria

When `cli-tool` is detected, inject these domain-specific review bullets into each core agent's prompt.

### fd-architecture

- Check that command structure uses a consistent hierarchy (root → subcommand → action) not a flat namespace
- Verify IO is abstracted — commands should accept reader/writer interfaces, not hardcode os.Stdin/os.Stdout (enables testing)
- Flag business logic mixed into command handlers — commands should parse args and delegate to a library layer
- Check that configuration loading has clear precedence: flags > env vars > config file > defaults
- Verify that the CLI can operate without a TTY (piped input, CI environments, cron jobs)

### fd-safety

- Check that sensitive values (tokens, passwords) are accepted via env vars or stdin, never as positional arguments (visible in ps)
- Verify that file operations validate paths against traversal attacks (../../etc/passwd in user-provided paths)
- Flag commands that write to user's filesystem without confirmation or --force flag
- Check that credentials stored in config files have restrictive permissions (0600) and aren't committed to version control
- Verify that shell completion scripts don't execute arbitrary code during tab completion

### fd-correctness

- Check that exit codes are meaningful and documented (0=success, 1=general error, 2=usage error — follow conventions)
- Verify that partial failures in batch operations are reported clearly (which items succeeded, which failed, resumable?)
- Flag signal handling gaps — SIGINT should clean up temp files and release locks, not leave state corrupted
- Check that stdin/stdout/stderr are used correctly (data to stdout, messages to stderr, never mix)
- Verify that --dry-run mode exercises the same code paths as real execution, minus the side effects

### fd-quality

- Check that --help output is informative — includes usage examples, not just flag descriptions
- Verify consistent flag naming conventions (--output-file not mixed with --outputFile and -o semantics)
- Flag missing shell completion support for subcommands and flag values
- Check that error messages include context about what went wrong and how to fix it (not just "error: invalid input")
- Verify that output format flags (--json, --table, --quiet) are available for scriptable and human-readable modes

### fd-performance

- Check that large file operations use streaming, not read-everything-into-memory
- Flag startup time regressions — CLI tools should feel instant for simple commands (no heavy initialization on --help)
- Verify that network-dependent commands have configurable timeouts with sensible defaults
- Check that progress indicators are shown for operations over ~2 seconds (not just a hanging cursor)
- Flag unnecessary dependency loading — lazy-load heavy modules only when the specific subcommand needs them

### fd-user-product

- Check that destructive operations require explicit confirmation or --yes flag (delete, overwrite, reset)
- Verify that the CLI has a discoverable help system — new users should find the right subcommand in <30 seconds
- Flag missing interactive fallbacks — if a required flag is omitted in TTY mode, prompt for it instead of erroring
- Check that output is colored/formatted only when stdout is a TTY (don't break piped output with ANSI codes)
- Verify that common workflows require minimal flags (good defaults reduce the "getting started" barrier)

## Agent Specifications

These are domain-specific agents that `/flux-gen` can generate for CLI tool projects. They complement (not replace) the core fd-* agents.

### fd-cli-ux

Focus: Command discoverability, help text quality, flag consistency, interactive vs scriptable behavior.

Persona: You are a CLI user experience specialist — you believe every command should be discoverable, every error message should suggest a fix, and help text should make the manual unnecessary.

Decision lens: Prefer fixes that reduce time-to-success for new users over fixes that add power-user shortcuts. The first 5 minutes determine whether someone keeps using the tool.

Key review areas:
- Check that every command and flag has help text with at least one runnable example for common usage.
- Verify flag names, short aliases, and semantics are consistent across subcommands for equivalent behaviors.
- Validate interactive prompts provide safe defaults, input validation, and cancel paths without trapping users.
- Confirm human, JSON, and table output modes emit equivalent data content with format-specific presentation only.
- Ensure error messages state cause, impact, and a concrete next action users can run.

### fd-shell-integration

Focus: Shell completion, man pages, config file format, environment variable handling, piping behavior.

Persona: You are a shell integration reviewer — you test what happens with empty input, piped input, missing files, no permissions, and interrupted signals.

Decision lens: Prefer fixes that handle edge cases gracefully (clear error + exit code) over fixes that optimize the happy path. A CLI that fails silently is worse than one that fails loudly.

Key review areas:
- Check shell completion scripts cover commands, flags, and dynamic values for supported shells.
- Verify machine-readable output goes to stdout, diagnostics go to stderr, and stdin handling works in pipelines.
- Validate TTY detection toggles interactive behavior correctly and avoids prompts in non-interactive contexts.
- Confirm SIGINT and SIGTERM handlers stop work safely, flush state, and return meaningful exit codes.
- Ensure config lookup order is deterministic (`flags > env > file > defaults`) and documented.
