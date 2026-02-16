.PHONY: codex-refresh codex-bootstrap codex-bootstrap-json codex-doctor codex-doctor-json

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
