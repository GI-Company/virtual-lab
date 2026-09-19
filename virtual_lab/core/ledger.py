import sqlite3
import json
import hashlib
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from pathlib import Path
import os
from virtual_lab.core.canonical import canonical_json

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

def compute_event_hash(event: LedgerEvent) -> str:
    # Hash everything except the event_hash itself
    envelope = event.model_dump(exclude={"event_hash"})
    canonical_bytes = canonical_json(envelope)
    return hashlib.sha256(canonical_bytes).hexdigest()

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
        actor = Actor(type=row["actor_type"], id=row["actor_id"])
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

    def get_events_by_proposal(self, proposal_id: str) -> List[LedgerEvent]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ledger_events WHERE json_extract(payload_json, '$.proposal_id') = ? ORDER BY sequence ASC", (proposal_id,))
        return [self._row_to_event(row) for row in cursor.fetchall()]

    def append(self, event_id: str, actor: Actor, event_type: str, payload: Dict[str, Any]) -> str:
        head = self.get_head()
        if head is None:
            raise RuntimeError("Genesis ledger is empty; should have initialized.")
            
        proposal_id = payload.get("proposal_id")
        if proposal_id:
            workflow_events = self.get_events_by_proposal(proposal_id)
            workflow_types = [evt.event_type for evt in workflow_events]
            
            if event_type in ["AI_PROPOSAL", "RULE_EVALUATION", "HUMAN_DECISION"]:
                if event_type in workflow_types:
                    raise ChainIntegrityError(f"Workflow sequence violation: {event_type} already exists for {proposal_id}")
            
            if event_type == "RULE_EVALUATION" and "AI_PROPOSAL" not in workflow_types:
                raise ChainIntegrityError(f"Workflow sequence violation: RULE_EVALUATION requires preceding AI_PROPOSAL for {proposal_id}")
            if event_type == "HUMAN_DECISION" and ("AI_PROPOSAL" not in workflow_types or "RULE_EVALUATION" not in workflow_types):
                raise ChainIntegrityError(f"Workflow sequence violation: HUMAN_DECISION requires preceding AI_PROPOSAL and RULE_EVALUATION for {proposal_id}")

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
        
    def get_approval_record(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        events = self.get_events_by_proposal(proposal_id)
        for evt in events:
            if evt.event_type == "AI_PROPOSAL":
                return evt.payload
        return None

    def verify_chain(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ledger_events ORDER BY sequence ASC")
        rows = cursor.fetchall()
        
        if not rows:
            return
            
        prev_hash = "0" * 64
        for i, row in enumerate(rows):
            event = self._row_to_event(row)
            if event.parent_hash != prev_hash:
                raise ChainIntegrityError(
                    f"CHAIN INTEGRITY FAILURE: Event {event.event_id} expected parent {prev_hash} but found {event.parent_hash}."
                )
            expected_hash = compute_event_hash(event)
            if event.event_hash != expected_hash:
                raise ChainIntegrityError(
                    f"CHAIN INTEGRITY FAILURE: Event {event.event_id} has invalid hash. Expected {expected_hash}, observed {event.event_hash}."
                )
            prev_hash = event.event_hash
