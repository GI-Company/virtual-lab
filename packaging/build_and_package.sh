#!/usr/bin/env bash
set -euo pipefail

# Build, sign (macOS), zip, and generate SHA-256 for VirtualLab desktop.
# Run on each target platform from the packaging/ directory.

VERSION="${VERSION:-1.0.0-beta.1}"
NAME="VirtualLab-${VERSION}"

case "$(uname -s)" in
  Darwin)
    echo "=== macOS build ==="
    pyinstaller --clean --noconfirm --windowed --name VirtualLab \
      --paths .. \
      --hidden-import virtual_lab \
      --hidden-import virtual_lab.gui.shell.main_window \
      launch.py
    APP="dist/VirtualLab.app"
    codesign --force --deep --sign - "$APP"
    codesign -dv --verbose=4 "$APP" || true
    cd dist
    ditto -c -k --keepParent VirtualLab.app "../${NAME}-macOS.zip"
    cd ..
    shasum -a 256 "${NAME}-macOS.zip" | tee "${NAME}-macOS.zip.sha256"
    echo "Artifact: ${NAME}-macOS.zip"
    ;;
  Linux)
    echo "=== Linux build ==="
    pyinstaller --clean --noconfirm --windowed --name VirtualLab \
      --paths .. \
      --hidden-import virtual_lab \
      --hidden-import virtual_lab.gui.shell.main_window \
      launch.py
    cd dist
    zip -r "../${NAME}-Linux.zip" VirtualLab
    cd ..
    sha256sum "${NAME}-Linux.zip" | tee "${NAME}-Linux.zip.sha256"
    echo "Artifact: ${NAME}-Linux.zip"
    ;;
  MINGW*|MSYS*|CYGWIN*|Windows*)
    echo "=== Windows build ==="
    pyinstaller --clean --noconfirm --windowed --name VirtualLab \
      --paths .. \
      --hidden-import virtual_lab \
      --hidden-import virtual_lab.gui.shell.main_window \
      launch.py
    cd dist
    powershell -Command "Compress-Archive -Path VirtualLab -DestinationPath '../${NAME}-Windows.zip' -Force"
    cd ..
    powershell -Command "Get-FileHash -Algorithm SHA256 '${NAME}-Windows.zip' | Format-List" | tee "${NAME}-Windows.zip.sha256"
    echo "Artifact: ${NAME}-Windows.zip"
    ;;
  *)
    echo "Unsupported platform: $(uname -s)"
    exit 1
    ;;
esac

echo ""
echo "Upload the .zip and .sha256 files to a GitHub Release or your CDN."
echo "Then enable the download buttons on the GIC /virtual-lab/beta page."
