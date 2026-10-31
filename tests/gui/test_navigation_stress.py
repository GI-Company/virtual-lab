"""Short subprocess form; longer native stress is an explicit local command."""

import json
import os
from pathlib import Path
import subprocess
import sys


def test_navigation_gc_stress_subprocess(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    output = tmp_path / "stress"
    process = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts/stress_navigation.py"),
            "--cycles",
            "3",
            "--output",
            str(output),
        ],
        cwd=repository,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
        capture_output=True,
        text=True,
        timeout=75,
    )
    result = (
        json.loads((output / "result.json").read_bytes())
        if (output / "result.json").exists()
        else None
    )
    assert process.returncode == 0, process.stdout + process.stderr + str(result)
    assert result["status"] == "passed" and result["completed_cycles"] == 3
    assert result["collection_thread_ids"] == [result["gui_thread"]]
    assert result["default_gc_interval_ms"] == 1000
    assert result["simulation_threads"] and result["allocator_threads"]
    assert result["navigation_guards_blocked"] == 3
    assert result["cyclic_allocations"] > 0
    assert result["gc_policy_restored"]
    assert result["python_network_attempts"] == result["credential_store_attempts"] == 0
    assert not result["violations"]
