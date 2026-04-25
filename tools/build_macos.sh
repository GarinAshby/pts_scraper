#!/usr/bin/env bash
# tools/build_macos.sh — one-shot build for the self-contained .app.
#
# Requires (one-time):
#   brew install tesseract poppler python-tk@3.14 expat
#   /opt/homebrew/bin/python3.14 -m venv .venv
#   .venv/bin/pip install pyinstaller pdf2image pillow opencv-python \
#                          pytesseract reportlab tkinterdnd2 numpy
#
# Run from project root:
#   ./tools/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

VENV=${VENV:-.venv}
APP=dist/UEEMobileGaragePermits.app

# Homebrew's Python 3.14 ships with a pyexpat that references symbols not
# present in /usr/lib/libexpat on macOS Tahoe. Steer dyld to Homebrew's expat
# during the build only — the .app itself does not depend on this.
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/expat/lib

rm -rf build dist
"$VENV/bin/pyinstaller" --noconfirm build.spec
"$VENV/bin/python" tools/fixup_macos_app.py "$APP"

echo
echo "✓ Built: $APP"
du -sh "$APP"
