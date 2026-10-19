"""Run the browser-bearing shell in a process with its own QApplication lifetime."""
import os
from pathlib import Path
import subprocess
import sys


def test_main_window_constructs_without_cloud_credentials(tmp_path):
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('manual_research_flow.py')),
        str(tmp_path), '--shell-only'], capture_output=True, text=True, timeout=40, env=dict(os.environ))
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'shell passed without AI' in result.stdout
