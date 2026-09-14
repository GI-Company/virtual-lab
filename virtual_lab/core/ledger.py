import sqlite3
import json
import hashlib
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from pathlib import Path
import os

class Actor(BaseModel):
    type: str
    id: str
    provider: Optional[str] = None
    model: Optional[str] = None

class LedgerEvent(BaseModel):
    schema_version: str = "1.0"
    sequence: int
    event_id: str
    timestamp_utc: str
    actor: Actor
    event_type: str
    payload: Dict[str, Any]
    parent_hash: str
    event_hash: str = ""

def canonicalJSON(data: Any) -> str:
    """Produces a deterministic, canonical JSON string for hashing."""
    return json.dumps(data, separators=(",", ":"), sort_keys=True, allow_nan=False)

def compute_event_hash(event: LedgerEvent) -> str:
    # Hash everything except the event_hash itself
    envelope = event.model_dump(exclude={"event_hash"})
    canonical_str = canonicalJSON(envelope)
    return hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()

class ChainIntegrityError(Exception):
    pass

class GenesisLedger:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._init_db()
        self.verify_chain() # Fails fast if chain is broken
        
    def _init_db(self):
        dirname = os.path.dirname(self.db_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        # We don't pretend SQLite itself makes this immutable against a determined adversary,
        # but the hash chain ensures tampering is evident.
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS ledger_events (
            sequence INTEGER PRIMARY KEY,
            event_id TEXT UNIQUE,
            timestamp_utc TEXT,
            actor_type TEXT,
            actor_id TEXT,
            event_type TEXT,
            payload_json TEXT,
            parent_hash TEXT,
            event_hash TEXT UNIQUE,
            schema_version TEXT
        )
        """)
        
        # SQLite trigger to prevent UPDATE/DELETE at the DB level (basic safety guardrail)
        self.conn.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_ledger_update
        BEFORE UPDATE ON ledger_events
        BEGIN
            SELECT RAISE(ABORT, 'Genesis Ledger is append-only.');
        END;
        """)
        self.conn.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_ledger_delete
        BEFORE DELETE ON ledger_events
        BEGIN
            SELECT RAISE(ABORT, 'Genesis Ledger is append-only.');
        END;
        """)
        self.conn.commit()

        # If table is empty, write Genesis event
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ledger_events")
        if cursor.fetchone()[0] == 0:
            self._write_genesis()
            
    def _write_genesis(self):
        genesis_event = LedgerEvent(
            sequence=0,
            event_id="GENESIS",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            actor=Actor(type="SYSTEM", id="genesis"),
            event_type="LEDGER_INITIALIZED",
            payload={"message": "VirtualLab Genesis Ledger Created"},
            parent_hash="0" * 64
        )
        genesis_event.event_hash = compute_event_hash(genesis_event)
        self._insert_event(genesis_event)
        
    def _insert_event(self, event: LedgerEvent):
        actor_dict = event.actor.model_dump()
        self.conn.execute(
            """
            INSERT INTO ledger_events (
                sequence, event_id, timestamp_utc, actor_type, actor_id, 
                event_type, payload_json, parent_hash, event_hash, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.sequence, event.event_id, event.timestamp_utc, 
                event.actor.type, event.actor.id, event.event_type, 
                json.dumps(event.payload), event.parent_hash, 
                event.event_hash, event.schema_version
            )
        )
        self.conn.commit()

    def get_head(self) -> Optional[LedgerEvent]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ledger_events ORDER BY sequence DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_event(row)
        
    def _row_to_event(self, row: sqlite3.Row) -> LedgerEvent:
        # Reconstruct Actor
        actor = Actor(type=row["actor_type"], id=row["actor_id"])
        
        # In a real app we might store provider/model in dedicated columns or serialized actor JSON. 
        # For simplicity here we just instantiate with type/id.
        
        return LedgerEvent(
            schema_version=row["schema_version"],
            sequence=row["sequence"],
            event_id=row["event_id"],
            timestamp_utc=row["timestamp_utc"],
            actor=actor,
            event_type=row["event_type"],
            payload=json.loads(row["payload_json"]),
            parent_hash=row["parent_hash"],
            event_hash=row["event_hash"]
        )

    def append(self, event_id: str, actor: Actor, event_type: str, payload: Dict[str, Any]) -> str:
        head = self.get_head()
        if head is None:
            raise RuntimeError("Genesis ledger is empty; should have initialized.")
            
        new_event = LedgerEvent(
            sequence=head.sequence + 1,
            event_id=event_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            event_type=event_type,
            payload=payload,
            parent_hash=head.event_hash
        )
        new_event.event_hash = compute_event_hash(new_event)
        self._insert_event(new_event)
        return new_event.event_hash
        
    def verify_chain(self):
        """Verifies the complete hash chain from Genesis to HEAD."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ledger_events ORDER BY sequence ASC")
        rows = cursor.fetchall()
        
        if not rows:
            return
            
        prev_hash = "0" * 64
        for i, row in enumerate(rows):
            event = self._row_to_event(row)
            
            # Verify parent link
            if event.parent_hash != prev_hash:
                raise ChainIntegrityError(
                    f"CHAIN INTEGRITY FAILURE: Event {event.event_id} (seq {event.sequence}) "
                    f"expected parent {prev_hash} but found {event.parent_hash}."
                )
                
            # Verify event hash
            expected_hash = compute_event_hash(event)
            if event.event_hash != expected_hash:
                raise ChainIntegrityError(
                    f"CHAIN INTEGRITY FAILURE: Event {event.event_id} (seq {event.sequence}) "
                    f"has invalid hash. Expected {expected_hash}, observed {event.event_hash}."
                )
                
            prev_hash = event.event_hash
