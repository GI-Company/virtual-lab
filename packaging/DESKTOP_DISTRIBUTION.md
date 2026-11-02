# Desktop Distribution

VirtualLab ships as a real desktop application on Linux, macOS, and Windows.

## Current status

The scientific cockpit is fully functional as a Python application.  
Packaging for end-user installation is provided under `packaging/`.

## Installable builds

Users should **not** need to create a virtual environment or run `pip install`.

| Platform | Artifact | Signing | First-launch note |
|----------|----------|---------|-------------------|
| macOS    | `VirtualLab.app` | Ad-hoc (`codesign --sign -`) | Right-click → Open |
| Windows  | `VirtualLab/` folder containing `VirtualLab.exe` | Unsigned | SmartScreen → More info → Run anyway |
| Linux    | `VirtualLab/` folder containing `VirtualLab` binary | N/A | Run the binary directly |

## Building

See `packaging/README.md` for exact commands.  
Builds must be performed on the target operating system (PyInstaller is not a cross-compiler).

## Ad-hoc signing policy

- **macOS**: Ad-hoc signature is applied automatically by `build_macos.sh`. This allows the app to run without an Apple Developer ID. It is suitable for beta distribution and internal use. Full notarization requires a paid Apple Developer account and is optional for later.
- **Windows**: No equivalent ad-hoc mechanism that fully suppresses SmartScreen. Unsigned binaries are the practical beta path. Production distribution should use a code-signing certificate.
- **Linux**: No code signing step is required.

## What is bundled

- PySide6 desktop cockpit
- Core scientific libraries (NumPy, SciPy, Pint, PyNaCl, keyring)
- All 13 workspaces
- Manual research workflow (AI remains optional and is not required)

Optional extras (`ai`, `biology`, MLX) are not included in the default binary. They can be enabled later via configuration or a future extended build.

## User data

Studies, ledgers, and evidence are stored outside the application bundle in the platform-appropriate application support directory.
