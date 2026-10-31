import os
from pathlib import Path
import subprocess
import sys


def test_full_shell_project_scope_and_restart(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("discipline_navigation_flow.py")),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=dict(os.environ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "passed"' in result.stdout
