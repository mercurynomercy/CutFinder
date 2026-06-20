#!/bin/bash
# Build CutFinder.app — a native macOS shell around the local web app.
#
# The bundle's executable is the compiled Swift wrapper (Cocoa + WKWebView),
# which on first launch syncs the bundled payload (backend source + built
# frontend) into a writable per-user location, provisions the Python env / models,
# serves the app locally and hosts it in a native window. Nothing is written
# inside the bundle, so it signs and updates cleanly. Drag the result to /Applications.
#
# Usage:  ./scripts/build-app.sh   (or `make app`)
# Output: dist/CutFinder.app  (and dist/CutFinder.dmg if hdiutil ok)
#
# Optional signing / notarization (auto-detected, never required for a dev build):
#   - Signs with hardened runtime + entitlements if a "Developer ID Application"
#     identity is present in the keychain.
#   - Notarizes the .dmg if signed AND $CUTFINDER_NOTARY_PROFILE names a stored
#     `notarytool` keychain profile (see `xcrun notarytool store-credentials`).

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

# ── 2. Assemble the runtime payload (backend source + built UI + scripts). ─
echo "▶ Assembling payload…"
# Backend: source + dependency manifests (no .venv / caches / local DBs).
rsync -a \
  --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.pytest_cache' --exclude '.mypy_cache' --exclude '.ruff_cache' \
  --exclude 'tests' \
  backend/ "$PAYLOAD/backend/"
cp -R frontend/dist "$PAYLOAD/frontend/dist"
# Model-download scripts the Swift Provisioner runs at first launch
# (it looks for them under <runtime>/packaging/).
mkdir -p "$PAYLOAD/packaging"
cp scripts/download_whisper.py scripts/download_demucs.py "$PAYLOAD/packaging/"

# ── 3. Build the Swift wrapper → bundle executable (compiled Mach-O). ──────
echo "▶ Building Swift wrapper…"
( cd packaging/macapp && swift build -c release )
cp packaging/macapp/.build/release/CutFinder "$CONTENTS/MacOS/CutFinder"
chmod +x "$CONTENTS/MacOS/CutFinder"

# ── 4. Info.plist (with version substitution). ────────────────────────────
sed "s/__VERSION__/$VERSION/g" packaging/Info.plist.template > "$CONTENTS/Info.plist"

# ── 5. App icon (.icns) from the brand artwork. ───────────────────────────
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

# ── 6. Code signing (guarded — Developer ID Application identity). ─────────
# The only Mach-O in the bundle is Contents/MacOS/CutFinder, so signing the
# .app signs everything that needs it — no nested/--deep signing required.
# venv + models live in Application Support (outside the bundle, unsigned).
ENTITLEMENTS="packaging/macapp/CutFinder.entitlements"
SIGNED=0
IDENTITY="$(security find-identity -p codesigning -v 2>/dev/null \
  | grep "Developer ID Application" | head -1 | sed -E 's/.*"(.+)".*/\1/' || true)"
if [ -n "$IDENTITY" ]; then
  echo "▶ Signing with hardened runtime: $IDENTITY"
  codesign --force --options runtime --entitlements "$ENTITLEMENTS" \
    --sign "$IDENTITY" "$APP"
  codesign --verify --strict --verbose=2 "$APP" || true
  SIGNED=1
else
  echo "  (signing skipped — no \"Developer ID Application\" identity found; producing an unsigned dev .app)"
fi

# ── 7. .dmg for distribution. ─────────────────────────────────────────────
echo "▶ Creating .dmg…"
DMG="dist/CutFinder.dmg"
DMG_OK=0
rm -f "$DMG"
STAGE="dist/_dmg"; rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
if hdiutil create -volname "CutFinder" -srcfolder "$STAGE" -ov -quiet -format UDZO "$DMG"; then
  DMG_OK=1
  echo "  → $DMG"
else
  echo "  (dmg step skipped)"
fi
rm -rf "$STAGE"

# ── 8. Notarization (guarded — needs a signed app + stored credentials). ──
# Submit the DMG, then staple the ticket onto both the app and the DMG.
if [ "$SIGNED" -eq 1 ] && [ "$DMG_OK" -eq 1 ] && [ -n "${CUTFINDER_NOTARY_PROFILE:-}" ]; then
  echo "▶ Notarizing (profile: $CUTFINDER_NOTARY_PROFILE)…"
  if xcrun notarytool submit "$DMG" --keychain-profile "$CUTFINDER_NOTARY_PROFILE" --wait; then
    xcrun stapler staple "$APP" || echo "  (stapling the .app failed)"
    xcrun stapler staple "$DMG" || echo "  (stapling the .dmg failed)"
  else
    echo "  (notarization submission failed — distribute manually after fixing)"
  fi
else
  echo "  (notarization skipped — needs a signed app + \$CUTFINDER_NOTARY_PROFILE)"
fi

echo ""
echo "✅ Built $APP"
echo "   Drag it to /Applications (or open $DMG)."
echo "   Note: OMLX must be installed separately (it serves the AI models)."
