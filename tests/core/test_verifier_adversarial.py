"""Regression checks against the current .vlab verifier interface."""

import sqlite3
import zipfile

from virtual_lab.core.provenance_export import (
    VerifierError,
    explain_provenance,
    verify_genesis_chain,
)


def test_traversal_rejected_before_extraction(tmp_path):
    bundle = tmp_path / "traversal.vlab"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../escape.txt", b"escape")
    assert "Zip traversal attack detected" in explain_provenance(str(bundle))
    assert not (tmp_path / "escape.txt").exists()


def test_missing_signature_rejected(tmp_path):
    bundle = tmp_path / "unsigned.vlab"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", b"{}")
    assert "missing manifest.json or manifest.sig" in explain_provenance(str(bundle))


def test_tampered_genesis_hash_rejected(tmp_path):
    db = tmp_path / "genesis.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE ledger_events (
            schema_version TEXT, sequence INTEGER, event_id TEXT,
            timestamp_utc TEXT, actor_type TEXT, actor_id TEXT,
            event_type TEXT, payload_json TEXT, parent_hash TEXT,
            event_hash TEXT)""")
        conn.execute("INSERT INTO ledger_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("1.0", 1, "EVT-1", "2026-09-18T00:00:00Z", "HUMAN",
                      "H-1", "PROPOSAL_CREATED", '{"target":"test"}', "0" * 64,
                      "tampered"))
    try:
        verify_genesis_chain(str(db))
    except VerifierError as error:
        assert "Genesis hash mismatch" in str(error)
    else:
        raise AssertionError("Tampered ledger event was accepted")


def test_artifact_digest_checked_after_signature_gate(tmp_path, monkeypatch):
    """Isolate the digest stage; signature enforcement is checked separately."""
    import hashlib
    from unittest.mock import Mock

    from virtual_lab.core.canonical import canonical_json

    db = tmp_path / "genesis.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE ledger_events (
            schema_version TEXT, sequence INTEGER, event_id TEXT,
            timestamp_utc TEXT, actor_type TEXT, actor_id TEXT,
            event_type TEXT, payload_json TEXT, parent_hash TEXT,
            event_hash TEXT)""")
    original = b"original data"
    manifest = {
        "vlab_version": "1.0",
        "build_utc": "2026-09-18T00:00:00Z",
        "contents": [
            {"path": "genesis.db", "sha256": hashlib.sha256(db.read_bytes()).hexdigest()},
            {"path": "artifact.bin", "sha256": hashlib.sha256(original).hexdigest()},
        ],
    }
    bundle = tmp_path / "tampered.vlab"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", canonical_json(manifest))
        archive.writestr("manifest.sig", b"test-only-signature")
        archive.write(db, "genesis.db")
        archive.writestr("artifact.bin", b"altered data")

    monkeypatch.setattr("virtual_lab.core.trusted_signers.verify_signer_role", lambda *_: True)
    monkeypatch.setattr("nacl.signing.VerifyKey", Mock(return_value=Mock()))
    assert "Artifact hash mismatch: artifact.bin" in explain_provenance(str(bundle))
