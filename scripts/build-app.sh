#!/bin/bash
# Build CutFinder.app — a self-setup macOS launcher.
#
# Bundles the backend source + the pre-built frontend into a .app whose launcher
# sets up its own Python env (via uv) and ffmpeg on first run, then serves the
# app locally and opens it in the browser. Drag the result to /Applications.
#
# Usage:  ./scripts/build-app.sh   (or `make app`)
# Output: dist/CutFinder.app  (and dist/CutFinder.dmg if create-dmg/hdiutil ok)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(git -C "$ROOT" describe --tags --always 2>/dev/null || echo "0.1.0")"
APP="dist/CutFinder.app"
CONTENTS="$APP/Contents"
RES="$CONTENTS/Resources"
PAYLOAD="$RES/payload"

echo "▶ Building CutFinder.app  (version $VERSION)"
rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS" "$PAYLOAD/backend" "$PAYLOAD/frontend"

# ── 1. Build the frontend (served statically by the backend at runtime). ──
echo "▶ Building frontend…"
( cd frontend && npm install --no-audit --no-fund >/dev/null 2>&1 && npx vite build )

# ── 2. Assemble the runtime payload (backend source + built UI). ──────────
echo "▶ Assembling payload…"
# Backend: source + dependency manifests (no .venv / caches / local DBs).
rsync -a \
  --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.pytest_cache' --exclude '.mypy_cache' --exclude '.ruff_cache' \
  --exclude 'tests' \
  backend/ "$PAYLOAD/backend/"
cp -R frontend/dist "$PAYLOAD/frontend/dist"

# ── 3. Launcher executable + Info.plist. ──────────────────────────────────
cp packaging/launcher.sh "$CONTENTS/MacOS/CutFinder"
chmod +x "$CONTENTS/MacOS/CutFinder"
sed "s/__VERSION__/$VERSION/g" packaging/Info.plist.template > "$CONTENTS/Info.plist"

# ── 4. App icon (.icns) from the brand artwork. ───────────────────────────
echo "▶ Generating icon…"
ICON_SRC="branding/cut_finder_clapperboard_open_magnifier.png"
if [ -f "$ICON_SRC" ]; then
  TMP_ICON="dist/_icon_1024.png"
  # Square, transparent, full-content 1024px master (no cropping) via ephemeral Pillow.
  uv run --with pillow python - "$ICON_SRC" "$TMP_ICON" <<'PY'
import sys
from PIL import Image
src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGBA")
im = im.crop(im.getbbox())               # trim transparent margins only
side = max(im.size)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
canvas.alpha_composite(im, ((side - im.width) // 2, (side - im.height) // 2))
canvas.resize((1024, 1024), Image.LANCZOS).save(out)
PY
  ICONSET="dist/CutFinder.iconset"
  rm -rf "$ICONSET"; mkdir -p "$ICONSET"
  for sz in 16 32 128 256 512; do
    sips -z "$sz" "$sz"            "$TMP_ICON" --out "$ICONSET/icon_${sz}x${sz}.png"      >/dev/null
    sips -z $((sz*2)) $((sz*2))    "$TMP_ICON" --out "$ICONSET/icon_${sz}x${sz}@2x.png"   >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$RES/icon.icns"
  rm -rf "$ICONSET" "$TMP_ICON"
else
  echo "  (skipped — $ICON_SRC not found)"
fi

# ── 5. Optional .dmg for distribution. ────────────────────────────────────
echo "▶ Creating .dmg…"
DMG="dist/CutFinder.dmg"
rm -f "$DMG"
STAGE="dist/_dmg"; rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "CutFinder" -srcfolder "$STAGE" -ov -quiet -format UDZO "$DMG" \
  && echo "  → $DMG" || echo "  (dmg step skipped)"
rm -rf "$STAGE"

echo ""
echo "✅ Built $APP"
echo "   Drag it to /Applications (or open $DMG)."
echo "   Note: OMLX must be installed separately (it serves the AI models)."
