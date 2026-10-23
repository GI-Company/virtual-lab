import sqlite3
import json
import hashlib
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from pathlib import Path
import os
import uuid
from virtual_lab.core.canonical import canonical_json, legacy_canonical_json, strict_json_loads

class Actor(BaseModel):
    type: str
    id: str
    provider: Optional[str] = None
    model: Optional[str] = None

class LedgerEvent(BaseModel):
    schema_version: str = "2.0"
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
    if event.schema_version == '2.0':
        encoded = canonical_json(envelope)
    elif event.schema_version == '1.0':
        encoded = legacy_canonical_json(envelope)
    else:
        raise ChainIntegrityError('Unsupported ledger schema: ' + event.schema_version)
    return hashlib.sha256(encoded).hexdigest()


def event_hash_matches(event):
    if event.schema_version == '2.0':
        return event.event_hash == compute_event_hash(event)
    if event.schema_version == '1.0':
        envelope = event.model_dump(exclude={'event_hash'})
        return any(event.event_hash == hashlib.sha256(legacy_canonical_json(
            envelope, normalize_zero=mode)).hexdigest() for mode in (False, True))
    raise ChainIntegrityError('Unsupported ledger schema: ' + event.schema_version)


class ChainIntegrityError(Exception):
    pass

class GenesisLedger:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        # Preflight before schema changes. Invalid history must not be altered.
        if db_path != ':memory:' and Path(db_path).is_file() and Path(db_path).stat().st_size:
            read_ledger_events(db_path)
        try:
            self._init_db()
            self.verify_chain()
        except BaseException:
            if hasattr(self, 'conn'):
                self.conn.close()
            raise
        
    def _init_db(self):
        dirname = os.path.dirname(self.db_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        if self.db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS ledger_events (
            sequence INTEGER PRIMARY KEY,
            event_id TEXT UNIQUE,
            timestamp_utc TEXT,
            actor_type TEXT,
            actor_id TEXT,
            actor_provider TEXT,
            actor_model TEXT,
            event_type TEXT,
            payload_json TEXT,
            parent_hash TEXT,
            event_hash TEXT UNIQUE,
            schema_version TEXT
        )
        """)
        existing_cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(ledger_events)")}
        if "actor_provider" not in existing_cols:
            self.conn.execute("ALTER TABLE ledger_events ADD COLUMN actor_provider TEXT")
        if "actor_model" not in existing_cols:
            self.conn.execute("ALTER TABLE ledger_events ADD COLUMN actor_model TEXT")
        
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

        self.conn.execute("BEGIN IMMEDIATE")
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ledger_events")
        if cursor.fetchone()[0] == 0:
            self._write_genesis()
        self.conn.commit()
            
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
                actor_provider, actor_model,
                event_type, payload_json, parent_hash, event_hash, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.sequence, event.event_id, event.timestamp_utc, 
                event.actor.type, event.actor.id,
                event.actor.provider, event.actor.model,
                event.event_type, 
                canonical_json(event.payload).decode('utf-8'), event.parent_hash, 
                event.event_hash, event.schema_version
            )
        )

    def get_head(self) -> Optional[LedgerEvent]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ledger_events ORDER BY sequence DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_event(row)
        
    def _row_to_event(self, row: sqlite3.Row) -> LedgerEvent:
        keys = row.keys()
        actor = Actor(
            type=row["actor_type"],
            id=row["actor_id"],
            provider=row["actor_provider"] if "actor_provider" in keys else None,
            model=row["actor_model"] if "actor_model" in keys else None,
        )
        return LedgerEvent(
            schema_version=row["schema_version"],
            sequence=row["sequence"],
            event_id=row["event_id"],
            timestamp_utc=row["timestamp_utc"],
            actor=actor,
            event_type=row["event_type"],
            payload=strict_json_loads(row["payload_json"]),
            parent_hash=row["parent_hash"],
            event_hash=row["event_hash"]
        )

    def get_events_by_proposal(self, proposal_id: str) -> List[LedgerEvent]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ledger_events WHERE json_extract(payload_json, '$.proposal_id') = ? ORDER BY sequence ASC", (proposal_id,))
        return [self._row_to_event(row) for row in cursor.fetchall()]

    def append(self, event_id: str, actor: Actor, event_type: str, payload: Dict[str, Any]) -> str:
        if self.conn.in_transaction:
            raise RuntimeError('Ledger append cannot nest inside an external transaction.')
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            self.verify_chain()
            result = self._append_locked(event_id, actor, event_type, payload)
            self.conn.commit()
            return result
        except BaseException:
            self.conn.rollback()
            raise

    def _append_locked(self, event_id, actor, event_type, payload):
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
        
    def claim_execution(self, proposal_id, nonce, actor_id, proposal_hash):
        """Consume approval before side effects, serializing concurrent processes.

        A crash or failed callback leaves the claim consumed. Recovery requires
        operator reconciliation and a newly signed proposal, never an automatic retry.
        """
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            self.verify_chain()
            for row in self.conn.execute("SELECT * FROM ledger_events WHERE event_type IN ('ACTION_CLAIMED', 'ACTION_EXECUTED')"):
                event = self._row_to_event(row)
                if event.payload.get('proposal_id') == proposal_id or (
                    event.actor.id == actor_id and event.payload.get('nonce') == nonce):
                    raise ValueError('PROPOSAL_ALREADY_EXECUTED_OR_CLAIMED')
            result = self._append_locked('CLAIM_' + uuid.uuid4().hex,
                Actor(type='HUMAN', id=actor_id), 'ACTION_CLAIMED',
                {'proposal_id': proposal_id, 'nonce': nonce, 'proposal_hash': proposal_hash})
            self.conn.commit()
            return result
        except BaseException:
            self.conn.rollback()
            raise

    def get_approval_record(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        events = self.get_events_by_proposal(proposal_id)
        for evt in events:
            if evt.event_type == "AI_PROPOSAL":
                return evt.payload
        return None

    def find_artifact_registration(self, artifact_id: str) -> Optional[LedgerEvent]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM ledger_events WHERE event_type = 'ARTIFACT_REGISTERED' AND json_extract(payload_json, '$.artifact_id') = ?",
            (artifact_id,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_event(row)
        return None

    def append_artifact_registration(self, payload: Dict[str, Any]) -> str:
        self.verify_chain() # verify before appending
        actor = Actor(type="INSTRUMENT", id=payload.get("device_id", "unknown"))
        event_id = f"evt_{uuid.uuid4().hex}"
        return self.append(event_id, actor, "ARTIFACT_REGISTERED", payload)

    def verify_chain(self):
        events = [self._row_to_event(row) for row in self.conn.execute(
            'SELECT * FROM ledger_events ORDER BY sequence')]
        verify_events(events)


def verify_events(events):
    previous = '0' * 64
    for index, event in enumerate(events):
        if event.sequence != index or event.parent_hash != previous:
            raise ChainIntegrityError('Ledger sequence or parent mismatch at ' + event.event_id)
        if index == 0 and (event.event_id != 'GENESIS' or event.event_type != 'LEDGER_INITIALIZED'):
            raise ChainIntegrityError('Missing ledger genesis identity.')
        if not event_hash_matches(event):
            raise ChainIntegrityError('Genesis hash mismatch at ' + event.event_id +
                '; history was not repaired or rehashed. Missing original actor metadata cannot be reconstructed.')
        previous = event.event_hash


def read_ledger_events(path):
    """Read and verify historical records without DDL or new genesis insertion."""
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        reader = object.__new__(GenesisLedger)
        events = [reader._row_to_event(row) for row in conn.execute(
            'SELECT * FROM ledger_events ORDER BY sequence')]
        verify_events(events)
        return events
    finally:
        conn.close()
