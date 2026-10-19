"""Stable application storage, independent of the launch directory."""
import os
import sys
from pathlib import Path


def app_data_dir():
    override = os.environ.get("VIRTUALLAB_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/VirtualLab/cockpit"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "VirtualLab/cockpit"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "VirtualLab/cockpit"
