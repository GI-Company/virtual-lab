#!/usr/bin/env bash
set -euo pipefail

# Build VirtualLab.app on macOS with ad-hoc signature.
# Run from the packaging/ directory inside a venv that has the cockpit extra + pyinstaller.

echo "Building VirtualLab for macOS..."
# Use --windowed so PyInstaller produces a proper .app bundle on macOS
pyinstaller --clean --noconfirm --windowed --name VirtualLab \
  --paths .. \
  --hidden-import virtual_lab \
  --hidden-import virtual_lab.gui.shell.main_window \
  launch.py

APP="dist/VirtualLab.app"
if [[ ! -d "$APP" ]]; then
  echo "ERROR: Expected $APP not found."
  ls -la dist/ || true
  exit 1
fi

echo "Applying ad-hoc signature (codesign --sign -)..."
codesign --force --deep --sign - "$APP"

echo "Signature details:"
codesign -dv --verbose=4 "$APP" || true

echo ""
echo "Done: $APP"
echo ""
echo "First-launch instructions for users:"
echo "  • Right-click VirtualLab.app → Open"
echo "  • Or: open $APP"
echo "  • Gatekeeper will show a one-time warning for ad-hoc signed apps."
