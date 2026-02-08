.PHONY: codex-refresh codex-doctor

codex-refresh:
	@bash scripts/install-codex.sh install --source "$(PWD)"
	@echo "Codex refresh complete. Restart Codex to reload skills/prompts."

codex-doctor:
	@bash scripts/install-codex.sh doctor --source "$(PWD)"
