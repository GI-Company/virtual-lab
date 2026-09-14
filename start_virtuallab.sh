#!/usr/bin/env bash
set -e

# VirtualLab macOS Launcher Script (v1.0.0-beta.1-rc1)

# Ensure we're in the correct directory (the repository root)
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Verify python virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Please create one with 'python3 -m venv .venv' and install requirements."
    exit 1
fi

echo "Starting VirtualLab Desktop (RHO P23H Beta)..."
source .venv/bin/activate

# Execute the main window using the python module path
python3 -m virtual_lab.gui.main_window
