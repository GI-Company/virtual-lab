"""Geometry regression: pages and their scroll ranges remain reachable on resize."""
import os
from pathlib import Path
import subprocess
import sys


def test_all_workspaces_fit_or_scroll_at_small_window_sizes(tmp_path):
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('layout_scenario.py')), str(tmp_path)],
        capture_output=True, text=True, timeout=60, env=dict(os.environ))
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'layout passed:' in result.stdout
