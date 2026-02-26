.PHONY: codex-refresh codex-bootstrap codex-bootstrap-json codex-doctor codex-doctor-json codex-ecosystem-bootstrap codex-ecosystem-bootstrap-json codex-ecosystem-doctor codex-ecosystem-doctor-json shellcheck

codex-refresh:
	@bash scripts/install-codex.sh install --source "$(PWD)"
	@echo "Codex refresh complete. Restart Codex to reload skills/prompts."

codex-bootstrap:
	@bash scripts/codex-bootstrap.sh

codex-bootstrap-json:
	@bash scripts/codex-bootstrap.sh --json

codex-doctor:
	@bash scripts/install-codex.sh doctor --source "$(PWD)"

codex-doctor-json:
	@bash scripts/install-codex.sh doctor --source "$(PWD)" --json

codex-ecosystem-bootstrap:
	@bash scripts/install-codex-interverse.sh install --source "$(PWD)"

codex-ecosystem-bootstrap-json:
	@bash scripts/install-codex-interverse.sh install --source "$(PWD)" >/dev/null
	@bash scripts/install-codex-interverse.sh doctor --source "$(PWD)" --json

codex-ecosystem-doctor:
	@bash scripts/install-codex-interverse.sh doctor --source "$(PWD)"

codex-ecosystem-doctor-json:
	@bash scripts/install-codex-interverse.sh doctor --source "$(PWD)" --json

shellcheck:
	@echo "Linting entry-point hooks..."
	@find hooks/ -maxdepth 1 -name '*.sh' ! -name 'lib-*' ! -name 'lib.sh' -print0 \
		| xargs -0 shellcheck --severity=warning --shell=bash
	@echo "Linting entry-point scripts..."
	@find scripts/ -maxdepth 1 -name '*.sh' ! -name 'lib-*' -print0 \
		| xargs -0 shellcheck --severity=warning --shell=bash
	@echo "shellcheck: all clean"
