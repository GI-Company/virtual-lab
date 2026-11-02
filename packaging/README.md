# VirtualLab Desktop Packaging

This directory turns the VirtualLab scientific cockpit into installable desktop applications for **Linux**, **macOS**, and **Windows**.

The application is **not a toy**. It is a full PySide6 research cockpit with:
- 13 workspaces (Projects, Simulation, Analysis, Evidence, Provenance, Instruments, etc.)
- Cryptographic Genesis Ledger
- Epistemic state classification
- Mechanistic simulations
- Optional AI
- Instrument transport

## Requirements

- Python 3.10–3.12
- The `cockpit` extra installed in a clean virtual environment
- PyInstaller (`pip install pyinstaller`)

## Build (recommended: build on each target OS)

PyInstaller is not a cross-compiler. Build on the platform you want to ship.

### macOS (Apple Silicon or Intel)

```bash
# From repository root, in a clean venv with cockpit installed
pip install pyinstaller
cd packaging
./build_macos.sh
```

Produces `dist/VirtualLab.app` with **ad-hoc signature** (`codesign --sign -`).

Users can open it by right-clicking → Open the first time (Gatekeeper).

### Windows

```bat
pip install pyinstaller
cd packaging
build_windows.bat
```

Produces `dist/VirtualLab/VirtualLab.exe` (onedir layout, more reliable with Qt).

### Linux

```bash
pip install pyinstaller
cd packaging
./build_linux.sh
```

Produces `dist/VirtualLab/` directory. You can further wrap it as an AppImage if desired.

## Ad-hoc Signing

- **macOS**: The build script runs `codesign --force --deep --sign - VirtualLab.app`. This is a valid ad-hoc signature that allows local execution. It is **not** notarized and will not pass Gatekeeper on first launch without user override.
- **Windows**: No official ad-hoc equivalent. The executable is unsigned. Users may see SmartScreen warnings; they can click “More info” → “Run anyway”. For production, use an OV code-signing certificate.
- **Linux**: No code signing required for normal distribution.

## Entry Point

The packaged application uses `virtual_lab.gui.shell.main_window` as the entry point. A thin launcher is provided in `packaging/launch.py` for PyInstaller.

## Notes

- Builds include the `cockpit` dependencies (PySide6, pyqtgraph, etc.).
- Optional `ai` and `biology` extras are **not** bundled by default (they can be added later).
- Data directories and user studies are stored in the user’s home / platform application support folder at runtime (not inside the bundle).
- Test the packaged binary on a clean machine before distributing.

## CI

A sample GitHub Actions workflow that builds on all three platforms is in `packaging/ci-packaging.yml` (copy to `.github/workflows/` when ready).
