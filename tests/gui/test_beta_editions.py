"""Run the complete AI-free workflow independently for each student presentation."""
import os
from pathlib import Path
import subprocess
import sys
import pytest

@pytest.mark.parametrize('edition',['high-school','undergraduate','graduate'])
def test_student_full_workflow(edition,tmp_path):
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('manual_research_flow.py')),str(tmp_path)],
        env=dict(os.environ,VIRTUALLAB_EDITION=edition),capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    assert '"status": "passed"' in result.stdout
