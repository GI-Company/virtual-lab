from pathlib import Path

import pytest

from virtual_lab.core.paths import app_data_dir
from virtual_lab.computational.artifacts import data_root
from virtual_lab.domain.experiment_store import _default_db_path
from virtual_lab.gui.services.run_store import RunStore


@pytest.mark.parametrize('platform,subpath', [('darwin','Library/Application Support/VirtualLab/beta/researcher'),
    ('linux','.local/share/VirtualLab/beta/researcher'), ('win32','AppData/Local/VirtualLab/beta/researcher')])
def test_platform_default(platform, subpath, tmp_path, monkeypatch):
    monkeypatch.delenv('VIRTUALLAB_DATA_DIR', raising=False)
    monkeypatch.delenv('XDG_DATA_HOME', raising=False)
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    monkeypatch.setattr('sys.platform', platform)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    assert app_data_dir() == tmp_path/subpath


def test_all_stores_share_override_across_launch_directories(tmp_path, monkeypatch):
    root = tmp_path/'research-data'
    monkeypatch.setenv('VIRTUALLAB_DATA_DIR',str(root))
    for name in ('launch-a','launch-b'):
        folder=tmp_path/name; folder.mkdir(); monkeypatch.chdir(folder)
        assert data_root() == root == RunStore().root
        assert Path(_default_db_path()).parent == root
        assert not (folder/'.virtuallab').exists()
