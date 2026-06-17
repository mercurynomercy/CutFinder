#!/bin/bash
# CutFinder.app launcher (Contents/MacOS/CutFinder).
#
# Self-setup model: the .app bundles the backend source + the pre-built frontend
# (Contents/Resources/payload). On launch it copies the payload to a writable
# per-user location, makes sure uv + ffmpeg are present, creates/updates the
# Python environment with `uv sync`, then starts the local server (which serves
# both the API and the built UI) and opens it in the browser.
#
# Nothing is written inside the .app bundle, so it survives code-signing and
# updates cleanly.

set -uo pipefail

PORT="${CUTFINDER_PORT:-5080}"
APP_RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
SUPPORT="$HOME/Library/Application Support/CutFinder"
RUNTIME="$SUPPORT/app"
LOG="$SUPPORT/launch.log"

mkdir -p "$SUPPORT" "$RUNTIME"
# Keep a single rotating-ish log (truncate if it gets big).
[ -f "$LOG" ] && [ "$(wc -c <"$LOG")" -gt 2000000 ] && : >"$LOG"
exec >>"$LOG" 2>&1
echo "==================== launch $(date) ===================="

notify() { osascript -e "display notification \"$1\" with title \"CutFinder\"" >/dev/null 2>&1 || true; }
alert()  { osascript -e "display dialog \"$1\" buttons {\"OK\"} with title \"CutFinder\" with icon caution" >/dev/null 2>&1 || true; }

open_ui() { open "http://127.0.0.1:$PORT/"; }

# ── Already running? Just focus the browser tab. ───────────────────
if curl -fsS "http://127.0.0.1:$PORT/api/library" >/dev/null 2>&1; then
  echo "Server already running on :$PORT — opening UI."
  open_ui
  exit 0
fi

# ── 1. Sync the bundled payload into the writable runtime dir. ─────
# Preserve the venv, catalog and any user state (never delete those).
echo "Syncing payload → $RUNTIME"
rsync -a --delete \
  --exclude 'backend/.venv' \
  --exclude '__pycache__' \
  "$APP_RES/payload/" "$RUNTIME/" || { alert "CutFinder: failed to copy app files."; exit 1; }

# ── 2. Ensure uv (Python toolchain) is available. ──────────────────
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  notify "First-time setup: installing uv…"
  echo "Installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh || { alert "CutFinder needs 'uv' but it could not be installed. See https://docs.astral.sh/uv/"; exit 1; }
  export PATH="$HOME/.local/bin:$PATH"
fi

# ── 3. Ensure ffmpeg / ffprobe (video metadata, thumbnails, frames). ─
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    notify "First-time setup: installing ffmpeg…"
    echo "Installing ffmpeg via Homebrew…"
    brew install ffmpeg || true
  fi
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  alert "CutFinder needs ffmpeg. Install Homebrew (https://brew.sh) then run:  brew install ffmpeg"
fi

# ── 4. Create / update the Python environment. ─────────────────────
cd "$RUNTIME/backend" || { alert "CutFinder: app files are missing."; exit 1; }
notify "Preparing CutFinder… (first run may take a minute)"
echo "uv sync…"
uv sync --frozen 2>&1 || uv sync 2>&1 || { alert "CutFinder: failed to set up the Python environment. See $LOG"; exit 1; }

# ── 5. Launch the server (as a child) and open the UI. ─────────────
export CUTFINDER_STATIC_DIR="$RUNTIME/frontend/dist"
echo "Starting server on :$PORT (static=$CUTFINDER_STATIC_DIR)"

# IMPORTANT: do NOT `exec` into Python. The .app's Dock icon is tied to this
# script (the bundle's CFBundleExecutable). `exec`-ing into the venv's Python —
# which lives outside the bundle — makes macOS think the app quit and removes
# the Dock tile, leaving the server running with no way to quit it.
#
# Instead we keep this script as the foreground process (so the Dock keeps its
# tile), run uvicorn as a child, and forward the Dock's "Quit" (SIGTERM) to it.
PYBIN="$RUNTIME/backend/.venv/bin/python"
if [ -x "$PYBIN" ]; then
  "$PYBIN" -m uvicorn cutfinder.api.app:app \
    --host 127.0.0.1 --port "$PORT" --timeout-graceful-shutdown 5 &
else
  uv run uvicorn cutfinder.api.app:app \
    --host 127.0.0.1 --port "$PORT" --timeout-graceful-shutdown 5 &
fi
SERVER_PID=$!

# Quit from the Dock → stop the server, then exit this script.
trap 'echo "shutting down…"; kill -TERM "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; exit 0' TERM INT

# Open the browser once the server answers.
(
  for _ in $(seq 1 120); do
    curl -fsS "http://127.0.0.1:$PORT/api/library" >/dev/null 2>&1 && { open_ui; break; }
    sleep 0.5
  done
) &

wait "$SERVER_PID"
