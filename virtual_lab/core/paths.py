"""Cross-platform VirtualLab application data paths."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """
    Return the writable VirtualLab cockpit data directory.

    VIRTUALLAB_DATA_DIR always wins so tests, containers, and deployments can
    choose an explicit location without depending on the current directory.
    """
    override = os.environ.get("VIRTUALLAB_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "VirtualLab" / "cockpit"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / "VirtualLab" / "cockpit"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        path = base / "VirtualLab" / "cockpit"

    path.mkdir(parents=True, exist_ok=True)
    return path
