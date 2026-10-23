"""Stable application storage, independent of the launch directory."""
import os
import sys
from pathlib import Path


def app_data_dir():
    override = os.environ.get("VIRTUALLAB_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    from virtual_lab.edition import current_edition
    edition_path = 'beta/' + current_edition()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/VirtualLab" / edition_path
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "VirtualLab" / edition_path
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "VirtualLab" / edition_path
