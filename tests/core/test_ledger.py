import pytest
import sqlite3
import os
from virtual_lab.core.ledger import GenesisLedger, Actor, LedgerEvent, ChainIntegrityError

def test_ledger_initialization(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    ledger = GenesisLedger(db_path=db_path)
    
    # Genesis event should be inserted
    head = ledger.get_head()
    assert head is not None
    assert head.sequence == 0
    assert head.event_id == "GENESIS"
    assert head.event_type == "LEDGER_INITIALIZED"

def test_ledger_append(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    ledger = GenesisLedger(db_path=db_path)
    
    actor = Actor(type="SYSTEM", id="test")
    payload = {"foo": "bar"}
    event_hash = ledger.append(event_id="EVT-1", actor=actor, event_type="TEST_EVENT", payload=payload)
    
    head = ledger.get_head()
    assert head.sequence == 1
    assert head.event_id == "EVT-1"
    assert head.event_hash == event_hash
    assert head.payload == payload
    
    # Verify chain integrity
    ledger.verify_chain()

def test_ledger_chain_integrity(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    ledger = GenesisLedger(db_path=db_path)
    
    actor = Actor(type="SYSTEM", id="test")
    ledger.append(event_id="EVT-1", actor=actor, event_type="TEST_EVENT_1", payload={"data": 1})
    ledger.append(event_id="EVT-2", actor=actor, event_type="TEST_EVENT_2", payload={"data": 2})
    
    # Now manually corrupt the database to check if verify_chain catches it
    conn = sqlite3.connect(db_path)
    # The triggers prevent update, so we'll bypass triggers or drop them
    conn.execute("DROP TRIGGER prevent_ledger_update")
    conn.execute("UPDATE ledger_events SET payload_json = '{\"data\": 3}' WHERE event_id = 'EVT-2'")
    conn.commit()
    conn.close()
    
    with pytest.raises(ChainIntegrityError):
        ledger2 = GenesisLedger(db_path=db_path) # Will call verify_chain()

def test_ledger_sqlite_triggers(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    ledger = GenesisLedger(db_path=db_path)
    
    conn = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.IntegrityError, match="Genesis Ledger is append-only"):
        conn.execute("UPDATE ledger_events SET payload_json = '{}'")
        
    with pytest.raises(sqlite3.IntegrityError, match="Genesis Ledger is append-only"):
        conn.execute("DELETE FROM ledger_events")
