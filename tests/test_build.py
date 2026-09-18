import os
import pytest
import tempfile
import zipfile
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.core.provenance_export import explain_provenance
from scripts.build_vlab_bundle import build_vlab_bundle

def test_vlab_build_and_provenance():
    with tempfile.TemporaryDirectory() as tmp_workspace:
        # 1. Create a dummy workspace with genesis.db
        genesis_path = os.path.join(tmp_workspace, "genesis.db")
        ledger = GenesisLedger(genesis_path)
        
        from virtual_lab.core.ledger import Actor
        actor = Actor(type="SYSTEM", id="test")
        ledger.append("TEST_EVT", actor, "TEST", {"key": "val"})
        
        # 2. Build the bundle
        bundle_path = os.path.join(tmp_workspace, "test_output.vlab")
        build_vlab_bundle(tmp_workspace, bundle_path)
        
        assert os.path.exists(bundle_path)
        assert zipfile.is_zipfile(bundle_path)
        
        # 3. Test provenance parsing
        report = explain_provenance(bundle_path)
        assert "GENESIS AUDIT TRAIL" in report
        assert "TEST_EVT" in report
