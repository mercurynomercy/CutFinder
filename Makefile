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
	cd backend && $(UV) run python -c "import mlx_whisper; mlx_whisper.load_model('large-v3')"

# ── 4. check-omlx — verify OMLX endpoint & models are ready ────
check-omlx: uv-sync
	cd backend && $(UV) run python -c "\
import os, httpx; \
base = os.environ.get('OMLX_BASE_URL', 'http://localhost:8000/v1'); \
key  = os.environ.get('OMLX_API_KEY', ''); \
if not key: raise SystemExit('OMLX_API_KEY is empty — set it in .env'); \
resp = httpx.get(f'{base}/models', headers={'Authorization': f'Bearer {key}'}); \
resp.raise_for_status(); \
models = [m['id'] for m in resp.json().get('data', [])]; \
print('OMLX OK — models:', models); \
required = ['qwen3.6-35b-a3b', 'qwen3-vl-8b-instruct']; \
missing = [m for m in required if not any(m.lower() in mid.lower() for mid in models)]; \
if missing: raise SystemExit('Missing required OMLX models: ' + ', '.join(missing)); \
print('All required text/vision models are present.')"

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
