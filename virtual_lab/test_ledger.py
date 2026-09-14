import pytest
import sqlite3
import os
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from virtual_lab.core.ledger import GenesisLedger, Actor, ChainIntegrityError

def test_ledger_immutability():
    # Use a temporary DB for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_ledger.db")
        ledger = GenesisLedger(db_path)
        
        # Initial head should be genesis
        head = ledger.get_head()
        assert head.sequence == 0
        assert head.event_id == "GENESIS"
        
        # Append some events
        actor = Actor(type="HUMAN", id="user-1")
        hash1 = ledger.append("EVT-1", actor, "TEST_EVENT", {"k": "v"})
        hash2 = ledger.append("EVT-2", actor, "TEST_EVENT_2", {"data": [1, 2, 3]})
        
        head = ledger.get_head()
        assert head.sequence == 2
        assert head.event_id == "EVT-2"
        assert head.event_hash == hash2
        
        # Re-initialize should verify cleanly
        ledger_reopen = GenesisLedger(db_path)
        
        # Tamper with the database manually
        conn = sqlite3.connect(db_path)
        # SQLite trigger prevents updates, so we drop the trigger temporarily to simulate an adversary with raw DB access
        conn.execute("DROP TRIGGER prevent_ledger_update")
        conn.execute("UPDATE ledger_events SET payload_json = '{\"k\": \"TAMPERED\"}' WHERE event_id = 'EVT-1'")
        conn.commit()
        
        # Next reopen should fail verification
        with pytest.raises(ChainIntegrityError):
            GenesisLedger(db_path)
