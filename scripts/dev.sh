#!/usr/bin/env bash
# Start both frontend and backend dev servers in background.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="$ROOT/.dev-pids"

# Load OMLX endpoint/key (and optional CUTFINDER_LIBRARY) from the root .env so
# the backend can reach the model server. EnvSettings reads these at startup.
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

_cleaned=0
cleanup() {
  [ "$_cleaned" = 1 ] && return
  _cleaned=1
  echo "Shutting down dev servers..."
  if [ -f "$PIDFILE" ]; then
    while read -r pid; do kill "$pid" 2>/dev/null || true; done < "$PIDFILE"
    rm -f "$PIDFILE"
  fi
}

trap cleanup EXIT INT TERM

# ── Backend (FastAPI / uvicorn)
echo "Starting backend on http://localhost:5081 ..."
cd "$ROOT/backend"
uv run uvicorn cutfinder.api.app:app --reload --port 5081 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PIDFILE"

# ── Frontend (Vite dev server)
echo "Starting frontend on http://localhost:5080 ..."
cd "$ROOT/frontend"
npx vite &
FRONTEND_PID=$!
echo "$FRONTEND_PID" >> "$PIDFILE"

echo ""
echo "Ready — open http://localhost:5080"
echo "Press Ctrl+C to stop both servers."

# Keep the script alive until either server exits, then cleanup() runs via the
# EXIT trap. Note: macOS ships bash 3.2, which lacks `wait -n`, so we poll
# instead (portable). Ctrl+C is handled by the INT trap.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
