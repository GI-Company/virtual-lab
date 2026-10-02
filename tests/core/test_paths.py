from pathlib import Path

from virtual_lab.core.paths import app_data_dir


def test_app_data_dir_respects_environment_override(monkeypatch, tmp_path):
    target = tmp_path / "vlab-data"
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(target))

    assert app_data_dir() == target
    assert target.is_dir()
