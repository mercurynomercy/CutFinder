# CutFinder — development Makefile.
# Targets: setup, dev, models, check-omlx, test, test-integration, e2e

PYTHON  := python3
UV      := uv
VITE    := npx vite
NODE    ?= node

.PHONY: setup dev models check-omlx test test-integration e2e clean

# ── 1. setup — install everything needed to develop and run ───────
setup: \
	install-mise \
	brew-bundle \
	uv-sync \
	frontend-deps \
	env-boilerplate

install-mise:
	@command -v mise >/dev/null 2>&1 || ( \
		echo "mise not found — install via: brew install mise"; \
		exit 1; \
	)
	mise install

brew-bundle:
	@missing=false; \
	for formula in $$(awk -F'"' '/^brew "/{print $$2}' Brewfile); do \
		if ! brew list --versions "$$formula" >/dev/null 2>&1; then \
			echo "brew-bundle: $$formula not installed — running brew bundle"; \
			missing=true; break; \
		fi; \
	done; \
	if [ "$$missing" = false ]; then \
		echo "brew-bundle: all deps already installed"; \
	fi; \
	if [ "$$missing" = true ]; then \
		brew bundle --file Brewfile; \
	fi

uv-sync:
	cd backend && $(UV) sync

frontend-deps:
	cd frontend && npm install

env-boilerplate:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — edit it with your OMLX key.")

# ── 2. dev — start both backend and frontend servers in one command ─
dev: uv-sync frontend-deps env-boilerplate
	@bash scripts/dev.sh

# ── 3. models — download MLX Whisper model cache ───────────────
models: uv-sync
	cd backend && $(UV) run python -c "from mlx_whisper.load_models import load_model; load_model('mlx-community/whisper-large-v3-mlx')"

# ── 4. check-omlx — verify OMLX endpoint & models are ready ────
check-omlx: uv-sync
	cd backend && set -a && [ -f ../.env ] && . ../.env; set +a; $(UV) run python ../scripts/check_omlx.py

# ── 5. test — unit tests only (no external deps) ───────────────
test: uv-sync
	cd backend && $(UV) run pytest

# ── 6. test-integration — real ffmpeg / OMLX (manual run) ──────
test-integration: uv-sync
	cd backend && $(UV) run pytest -m integration

# ── 7. e2e — Playwright (requires backend with fake adapters) ───
e2e: frontend-deps
	cd frontend && npx playwright test

# ── Cleanup (local venv, node_modules) ───────────────────────────
clean:
	rm -rf backend/.venv frontend/node_modules
