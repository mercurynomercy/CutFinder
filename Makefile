# CutFinder — development Makefile.
# Targets: setup, dev, models, check-omlx, test, test-integration, e2e

PYTHON  := python3
UV      := uv
VITE    := npx vite
NODE    ?= node

.PHONY: setup dev models check-omlx test test-integration e2e clean frontend backend app

# ── 1. setup — install everything needed to develop and run ───────
setup: \
	install-mise \
	brew-bundle \
	uv-sync \
	frontend-deps

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

# ── 2. dev — start both backend and frontend servers in one command ─
# No .env is required: configure OMLX in the Settings UI (stored in
# ~/.cutfinder/config.json). A .env, if present, is read as a fallback only.
dev: uv-sync frontend-deps
	@bash scripts/dev.sh

# ── 3. models — download MLX Whisper + Demucs models (honors WHISPER_MODEL_PATH) ──
models: uv-sync
	cd backend && set -a && [ -f ../.env ] && . ../.env; set +a; $(UV) run python ../scripts/download_whisper.py; $(UV) run python ../scripts/download_demucs.py

# ── 4. check-omlx — verify OMLX endpoint & models are ready ────
check-omlx: uv-sync
	cd backend && set -a && [ -f ../.env ] && . ../.env; set +a; $(UV) run python ../scripts/check_omlx.py

# ── 5. test — full suite (incl. integration; needs ffmpeg/OMLX) ─
test: uv-sync
	cd backend && $(UV) run pytest

# ── 5b. test-unit — unit tests only, fast (no external deps) ───
test-unit: uv-sync
	cd backend && $(UV) run pytest tests/unit

# ── 6. test-integration — real ffmpeg / OMLX (manual run) ──────
test-integration: uv-sync
	cd backend && $(UV) run pytest -m integration

# ── 7. e2e — Playwright (requires backend with fake adapters) ───
e2e: frontend-deps
	cd frontend && npx playwright test

# ── 8. frontend — start Vite dev server only ───────────────────
frontend: frontend-deps
	cd frontend && $(VITE)

# ── 9. backend — start uvicorn dev server only (with --reload) ─
backend:
	cd backend && $(UV) run uvicorn cutfinder.api.app:app --reload --port 5081

# ── 10. app — package the self-setup macOS .app (+ .dmg) ─────────
app:
	./scripts/build-app.sh

# ── Cleanup (local venv, node_modules) ───────────────────────────
clean:
	rm -rf backend/.venv frontend/node_modules
