# VirtualLab Desktop Downloads — Website Integration

Users should never need the command line.

## Recommended hosting

**GitHub Releases** on `GI-Company/virtual-lab` (simplest, free, direct download links).

1. On each platform, run:
   ```bash
   cd packaging
   ./build_and_package.sh
   ```
2. Create a release (e.g. `v1.0.0-beta.1`).
3. Upload:
   - `VirtualLab-1.0.0-beta.1-macOS.zip`
   - `VirtualLab-1.0.0-beta.1-Windows.zip`
   - `VirtualLab-1.0.0-beta.1-Linux.zip`
   - Their `.sha256` files
4. Copy the direct download URLs into the website config.

## Website page

The existing `/virtual-lab/beta` page is the right place.  
Add three download buttons (or auto-detect platform) plus SHA-256 verification instructions.

## First-launch notes to show on the page

- **macOS**: Ad-hoc signed. Right-click the app → Open the first time.
- **Windows**: Unsigned beta. If SmartScreen warns, click More info → Run anyway.
- **Linux**: Extract the zip and run the binary.

## Status

The packaging scripts are ready. Once you build on each OS and upload the zips to a GitHub Release, the website can point to those URLs and the download buttons become live.
