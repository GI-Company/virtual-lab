import os
import tempfile
import pytest
from virtual_lab.core.ledger import GenesisLedger, Actor
from virtual_lab.core.artifact_registration import ArtifactRegistrationService
from virtual_lab.instruments.transport.protocol_v1 import ArtifactRegister

@pytest.fixture
def ledger():
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "genesis.db")
        yield GenesisLedger(db_path)

@pytest.fixture
def registration_service(ledger):
    return ArtifactRegistrationService(ledger)

def test_idempotent_registration(registration_service, ledger):
    # Setup first valid registration
    data = b"test payload"
    import base64
    payload_b64 = base64.b64encode(data).decode('utf-8')
    import hashlib
    h = hashlib.sha256()
    h.update(data)
    checksum = h.hexdigest()
    
    reg1 = ArtifactRegister(
        measurement_id="meas-1",
        device_id="dev-1",
        artifact_id="art-1",
        correlation_id="corr-1",
        edge_artifact_ref="local/path/1",
        edge_sha256=checksum,
        payload_base64=payload_b64,
        size_bytes=len(data)
    )
    
    resp_json1 = registration_service.handle_registration(reg1, "dev-1")
    import json
    resp1 = json.loads(resp_json1)
    
    assert resp1["message_type"] == "LEDGER_REGISTERED"
    assert resp1["measurement_id"] == "meas-1"
    
    # Try exact same registration again - should be idempotent
    resp_json2 = registration_service.handle_registration(reg1, "dev-1")
    resp2 = json.loads(resp_json2)
    assert resp2["message_type"] == "LEDGER_REGISTERED"
    
    # Check that ledger only has 1 event for this registration
    conn = ledger.conn
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM ledger_events WHERE event_type = 'ARTIFACT_REGISTERED'")
    count = cursor.fetchone()[0]
    assert count == 1

def test_registration_conflict(registration_service, ledger):
    data1 = b"test payload 1"
    import base64, hashlib
    
    reg1 = ArtifactRegister(
        measurement_id="meas-2",
        device_id="dev-1",
        artifact_id="art-2",
        correlation_id="corr-2",
        edge_artifact_ref="local/path/2",
        edge_sha256=hashlib.sha256(data1).hexdigest(),
        payload_base64=base64.b64encode(data1).decode('utf-8'),
        size_bytes=len(data1)
    )
    registration_service.handle_registration(reg1, "dev-1")
    
    data2 = b"test payload 2"
    reg2 = ArtifactRegister(
        measurement_id="meas-2",
        device_id="dev-1",
        artifact_id="art-2",
        correlation_id="corr-2",
        edge_artifact_ref="local/path/2",
        edge_sha256=hashlib.sha256(data2).hexdigest(),
        payload_base64=base64.b64encode(data2).decode('utf-8'),
        size_bytes=len(data2)
    )
    resp_json = registration_service.handle_registration(reg2, "dev-1")
    import json
    resp = json.loads(resp_json)
    assert resp["message_type"] == "LEDGER_REJECTED"
    assert resp["reason"] == "DIGEST_CONFLICT"

def test_invalid_device(registration_service):
    data = b"test payload"
    import base64, hashlib
    reg = ArtifactRegister(
        measurement_id="meas-3",
        device_id="dev-1",
        artifact_id="art-3",
        correlation_id="corr-3",
        edge_artifact_ref="local/path/3",
        edge_sha256=hashlib.sha256(data).hexdigest(),
        payload_base64=base64.b64encode(data).decode('utf-8'),
        size_bytes=len(data)
    )
    resp_json = registration_service.handle_registration(reg, "dev-2")
    import json
    resp = json.loads(resp_json)
    assert resp["message_type"] == "LEDGER_REJECTED"
    assert "Device ID" in resp["error_message"]

def test_invalid_checksum(registration_service):
    data = b"test payload"
    import base64
    reg = ArtifactRegister(
        measurement_id="meas-4",
        device_id="dev-1",
        artifact_id="art-4",
        correlation_id="corr-4",
        edge_artifact_ref="local/path/4",
        edge_sha256="1111111111111111111111111111111111111111111111111111111111111111",
        payload_base64=base64.b64encode(data).decode('utf-8'),
        size_bytes=len(data)
    )
    resp_json = registration_service.handle_registration(reg, "dev-1")
    import json
    resp = json.loads(resp_json)
    assert resp["message_type"] == "LEDGER_REJECTED"
    assert resp["reason"] == "DIGEST_CONFLICT"

def test_different_device_replay_rejected(registration_service, ledger):
    data = b"test payload device"
    import base64, hashlib
    
    # Register with device 1
    reg1 = ArtifactRegister(
        measurement_id="meas-dev",
        device_id="dev-1",
        artifact_id="art-dev",
        correlation_id="corr-dev",
        edge_artifact_ref="local/path/dev",
        edge_sha256=hashlib.sha256(data).hexdigest(),
        payload_base64=base64.b64encode(data).decode('utf-8'),
        size_bytes=len(data)
    )
    resp_json1 = registration_service.handle_registration(reg1, "dev-1")
    import json
    resp1 = json.loads(resp_json1)
    assert resp1["message_type"] == "LEDGER_REGISTERED"

    # Register same artifact with device 2
    reg2 = ArtifactRegister(
        measurement_id="meas-dev",
        device_id="dev-2",
        artifact_id="art-dev",
        correlation_id="corr-dev",
        edge_artifact_ref="local/path/dev",
        edge_sha256=hashlib.sha256(data).hexdigest(),
        payload_base64=base64.b64encode(data).decode('utf-8'),
        size_bytes=len(data)
    )
    resp_json2 = registration_service.handle_registration(reg2, "dev-2")
    resp2 = json.loads(resp_json2)
    assert resp2["message_type"] == "LEDGER_REJECTED"
    assert resp2["reason"] == "IDENTITY_CONFLICT"

def test_orphan_file_recovery_and_mismatch(registration_service, ledger, tmp_path):
    # Override artifacts_dir to tmp_path for easier manipulation
    registration_service.artifacts_dir = str(tmp_path)
    
    data = b"orphan file payload"
    import base64, hashlib, os
    sha = hashlib.sha256(data).hexdigest()
    
    # Manually create orphan file
    target_file = os.path.join(str(tmp_path), "art-orphan.json")
    with open(target_file, "wb") as f:
        f.write(data)
        
    # Attempt registration with matching payload
    reg = ArtifactRegister(
        measurement_id="meas-orphan",
        device_id="dev-1",
        artifact_id="art-orphan",
        correlation_id="corr-orphan",
        edge_artifact_ref="local/path/orphan",
        edge_sha256=sha,
        payload_base64=base64.b64encode(data).decode('utf-8'),
        size_bytes=len(data)
    )
    resp_json1 = registration_service.handle_registration(reg, "dev-1")
    import json
    resp1 = json.loads(resp_json1)
    # Should succeed and skip writing since orphan matches
    assert resp1["message_type"] == "LEDGER_REGISTERED"
    
    # Now simulate a mismatch orphan
    data2 = b"orphan file payload 2 mismatch"
    sha2 = hashlib.sha256(data2).hexdigest()
    
    target_file_mismatch = os.path.join(str(tmp_path), "art-mismatch.json")
    with open(target_file_mismatch, "wb") as f:
        f.write(b"something completely different")
        
    reg_mismatch = ArtifactRegister(
        measurement_id="meas-mismatch",
        device_id="dev-1",
        artifact_id="art-mismatch",
        correlation_id="corr-mismatch",
        edge_artifact_ref="local/path/mismatch",
        edge_sha256=sha2,
        payload_base64=base64.b64encode(data2).decode('utf-8'),
        size_bytes=len(data2)
    )
    resp_json2 = registration_service.handle_registration(reg_mismatch, "dev-1")
    resp2 = json.loads(resp_json2)
    
    # Should reject because target file exists with different contents
    assert resp2["message_type"] == "LEDGER_REJECTED"
    assert resp2["reason"] == "IMMUTABLE_ARTIFACT_CONFLICT"
