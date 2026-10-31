"""Opt-in user-supplied fixture. No downloaded measurement files in the repository."""

import os
from pathlib import Path
import pytest
from scripts.verify_bsa_workflow import run


def test_bsa_three_scans_one_acquisition_workflow(tmp_path):
    archive = os.environ.get("VIRTUALLAB_BSA_ZIP")
    if not archive:
        pytest.skip("Set VIRTUALLAB_BSA_ZIP to the supplied repaired BSA archive")
    result = run(Path(archive), tmp_path / "bsa-workflow")
    assert result["repair"]["offsets_checked"] == 1684
    assert result["scan_summary_rejected"]
    assert [r["peaks"] for r in result["datasets"]] == [467, 478, 102]
    assert len({r["experiment_id"] for r in result["datasets"]}) == 1
    assert len({r["group_id"] for r in result["datasets"]}) == 1
