import os
from pathlib import Path
import subprocess
import sys


def test_full_manual_flow_without_ai_installed(tmp_path):
    script = Path(__file__).with_name('manual_research_flow.py')
    env = dict(os.environ, VIRTUALLAB_DATA_DIR=str(tmp_path/'unused'))
    result = subprocess.run([sys.executable, str(script), str(tmp_path)], env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"ai_imports": 0' in result.stdout
