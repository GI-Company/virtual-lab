#!/usr/bin/env bash
set -euo pipefail

# Build VirtualLab for Linux (onedir layout).
# Run from the packaging/ directory inside a venv that has the cockpit extra + pyinstaller.

echo "Building VirtualLab for Linux..."
pyinstaller --clean --noconfirm --windowed --name VirtualLab \
  --paths .. \
  --hidden-import virtual_lab \
  --hidden-import virtual_lab.gui.shell.main_window \
  launch.py

echo ""
echo "Done: dist/VirtualLab/"
echo "Distribute the entire dist/VirtualLab directory."
echo "Users can run: ./dist/VirtualLab/VirtualLab"
echo ""
echo "Optional: wrap as AppImage later with appimagetool."
