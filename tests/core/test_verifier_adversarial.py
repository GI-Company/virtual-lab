import pytest
import zipfile
import json
import os
import tempfile
import sqlite3
import hashlib
from virtual_lab.core.provenance_export import secure_extract, verify_genesis_chain, VerifierError, explain_provenance
from virtual_lab.core.canonical import canonical_json

def create_mock_vlab(path, malicious_type=None):
    with zipfile.ZipFile(path, 'w') as zf:
        if malicious_type == "traversal":
            # Simulate traversal attempt
            zf.writestr("../evil.txt", b"evil")
        elif malicious_type == "missing_manifest":
            pass # No manifest
        else:

            # Genesis DB
            db_fd, db_path = tempfile.mkstemp()
            os.close(db_fd)
            conn = sqlite3.connect(db_path)
            conn.execute('''CREATE TABLE ledger_events (
                            schema_version TEXT,
                            sequence INTEGER,
                            event_id TEXT,
                            timestamp_utc TEXT,
                            actor_type TEXT,
                            actor_id TEXT,
                            event_type TEXT,
                            payload_json TEXT,
                            parent_hash TEXT,
                            event_hash TEXT
                        )''')
            
            envelope = {
                "schema_version": "1.0",
                "sequence": 1,
                "event_id": "EVT-1",
                "timestamp_utc": "2026-09-18T00:00:00Z",
                "actor": {
                    "type": "HUMAN",
                    "id": "H-1",
                    "provider": None,
                    "model": None
                },
                "event_type": "PROPOSAL_CREATED",
                "payload": {"target": "test"},
                "parent_hash": "0" * 64
            }
            canonical_bytes = canonical_json(envelope)
            event_hash = hashlib.sha256(canonical_bytes).hexdigest()
            
            event_payload = json.dumps({"target": "test"})
            
            if malicious_type == "tampered_hash":
                event_hash = "badhash"
            elif malicious_type == "genesis_event_changed":
                # Changing the payload, which should invalidate the hash
                event_payload = json.dumps({"target": "evil"})
                
            conn.execute('''INSERT INTO ledger_events VALUES 
                            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                         ("1.0", 1, "EVT-1", "2026-09-18T00:00:00Z", 
                          "HUMAN", "H-1", "PROPOSAL_CREATED", 
                          event_payload, "0" * 64, event_hash))
            conn.commit()
            conn.close()
            
            with open(db_path, 'rb') as f:
                genesis_hash = hashlib.sha256(f.read()).hexdigest()
                
            manifest = {
                "vlab_version": "1.0", 
                "build_utc": "2026-09-18T00:00:00Z",
                "contents": [
                    {"path": "genesis.db", "sha256": genesis_hash}
                ]
            }
            
            if malicious_type == "missing_artifact":
                # Add to manifest, but don't add to zip
                manifest["contents"].append({"path": "file1.txt", "sha256": hashlib.sha256(b"artifact_data").hexdigest()})
            else:
                # Add a normal file to the manifest and zip
                file_content = b"artifact_data"
                if malicious_type == "artifact_byte_changed":
                    file_content = b"artifact_data_changed"
                manifest["contents"].append({"path": "file1.txt", "sha256": hashlib.sha256(b"artifact_data").hexdigest()})
                zf.writestr("file1.txt", file_content)
                
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.write(db_path, "genesis.db")
            os.remove(db_path)

def test_secure_extract_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        vlab_path = os.path.join(tmpdir, "test.vlab")
        create_mock_vlab(vlab_path, "traversal")
        
        with pytest.raises(VerifierError, match="traversal"):
            with zipfile.ZipFile(vlab_path, 'r') as bundle:
                secure_extract(bundle, os.path.join(tmpdir, "extract"))

def test_verify_genesis_tampered():
    with tempfile.TemporaryDirectory() as tmpdir:
        vlab_path = os.path.join(tmpdir, "test.vlab")
        create_mock_vlab(vlab_path, "tampered_hash")
        
        report = explain_provenance(vlab_path)
        assert "Error: Genesis hash mismatch" in report

def test_verify_genesis_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        vlab_path = os.path.join(tmpdir, "test.vlab")
        create_mock_vlab(vlab_path)
        
        report = explain_provenance(vlab_path)
        assert "Genesis hash chain: VERIFIED" in report

def test_missing_artifact():
    with tempfile.TemporaryDirectory() as tmpdir:
        vlab_path = os.path.join(tmpdir, "test.vlab")
        create_mock_vlab(vlab_path, "missing_artifact")
        
        report = explain_provenance(vlab_path)
        assert "Error: Missing artifact: file1.txt" in report

def test_artifact_byte_changed():
    with tempfile.TemporaryDirectory() as tmpdir:
        vlab_path = os.path.join(tmpdir, "test.vlab")
        create_mock_vlab(vlab_path, "artifact_byte_changed")
        
        report = explain_provenance(vlab_path)
        assert "Error: Artifact hash mismatch: file1.txt" in report

def test_genesis_event_changed():
    with tempfile.TemporaryDirectory() as tmpdir:
        vlab_path = os.path.join(tmpdir, "test.vlab")
        create_mock_vlab(vlab_path, "genesis_event_changed")
        
        report = explain_provenance(vlab_path)
        assert "Genesis hash mismatch" in report
