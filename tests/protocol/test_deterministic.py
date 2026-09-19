import pytest
import os
from virtual_lab.core.ledger import GenesisLedger, Actor, ChainIntegrityError
from virtual_lab.domain.observation import QuantityDescriptor, PhysicalDimension, NormalizedObservation, RawObservation, ObservationKind
from virtual_lab.domain.epistemics import EpistemicState

def test_chain_integrity_tampering(tmp_path):
    db_path = os.path.join(tmp_path, "genesis.db")
    ledger = GenesisLedger(db_path)
    
    actor = Actor(type="SYSTEM", id="test")
    hash1 = ledger.append("evt1", actor, "TEST", {"val": 1})
    hash2 = ledger.append("evt2", actor, "TEST", {"val": 2})
    
    # Tamper with the database directly - this should now raise IntegrityError
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        ledger.conn.execute("UPDATE ledger_events SET payload_json = '{\"val\": 999}' WHERE event_id = 'evt1'")
        ledger.conn.commit()

def test_strict_validation_boundaries():
    quantities = [
        QuantityDescriptor("test", "t", "desc", PhysicalDimension.DIMENSIONLESS, "")
    ]
    
    # RawObservation enforces MEASURED implicitly
    raw = RawObservation(
        observation_id="OBS-1",
        experiment_id="EXP-1",
        session_id="SESS-1",
        instrument_id="INST-1",
        kind=ObservationKind.CHEMISTRY,
        quantities=quantities,
        artifact_path="/tmp/test",
        artifact_sha256="abc",
        acquisition_utc="2026-09-18"
    )
    assert raw.epistemic_state == EpistemicState.MEASURED
    
    # NormalizedObservation rejects MEASURED
    with pytest.raises(ValueError, match="NormalizedObservation cannot claim MEASURED"):
        NormalizedObservation(
            observation_id="OBS-2",
            experiment_id="EXP-1",
            session_id="SESS-1",
            instrument_id="INST-1",
            kind=ObservationKind.CHEMISTRY,
            quantities=quantities,
            artifact_path="/tmp/test",
            artifact_sha256="abc",
            acquisition_utc="2026-09-18",
            epistemic_state=EpistemicState.MEASURED,
            parent_observation_id="OBS-1"
        )
