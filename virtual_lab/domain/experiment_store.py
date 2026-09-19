"""
virtual_lab.domain.experiment_store
─────────────────────────────────────
Durable SQLite persistence for VirtualExperiment and ExperimentObservation
relationships.

Design
──────
• Genesis ledger = immutable append-only event history (who did what, when).
  It is the scientific audit record and never used as a query database.

• ExperimentStore = the primary query database for experiment/observation
  relationships. It answers: "which observations belong to experiment X?",
  "what experiments exist?", "what is in the staging area?"

• Both are updated on every mutation, but serve different roles.

Schema
──────
  experiments(id, disease_id, compound_id, evidence_snapshot, parent_id,
              status, created_at, label)
  observations(observation_id, experiment_id, session_id, instrument_id,
               kind, epistemic_state, artifact_path, artifact_sha256,
               acquisition_utc, sample_count, duration_s, quantities_json,
               calibration_id, notes)
  staging(observation_id, staged_at, quantities_json, kind, instrument_id,
          session_id, artifact_path, artifact_sha256, acquisition_utc,
          sample_count, duration_s, notes)
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from virtual_lab.domain.epistemics import EpistemicState, QualityState
from virtual_lab.domain.observation import (
    ExperimentObservation,
    ObservationKind,
    QuantityDescriptor,
    PhysicalDimension,
)


def _default_db_path() -> str:
    data_dir = Path(
        os.environ.get(
            "VIRTUALLAB_DATA_DIR",
            Path.home() / "Library/Application Support/VirtualLab/cockpit",
        )
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "experiments.db")


def _serialize_quantities(quantities: List[QuantityDescriptor]) -> str:
    return json.dumps([
        {
            "semantic_name": q.semantic_name,
            "symbol": q.symbol,
            "description": q.description,
            "physical_dimension": q.physical_dimension.value,
            "units": q.units,
            "component_axis": q.component_axis,
            "epistemic_state": q.epistemic_state.value,
        }
        for q in quantities
    ])


def _deserialize_quantities(raw: str) -> List[QuantityDescriptor]:
    items = json.loads(raw)
    result = []
    for item in items:
        try:
            dim = PhysicalDimension(item["physical_dimension"])
        except ValueError:
            dim = PhysicalDimension.UNKNOWN_DIMENSION
        try:
            ep = EpistemicState(item["epistemic_state"])
        except ValueError:
            ep = EpistemicState.UNKNOWN
        result.append(QuantityDescriptor(
            semantic_name=item["semantic_name"],
            symbol=item["symbol"],
            description=item["description"],
            physical_dimension=dim,
            units=item["units"],
            component_axis=item.get("component_axis"),
            epistemic_state=ep,
        ))
    return result


class ExperimentStore:
    """
    Durable, queryable store for experiments and observations.
    Thread-safety: use one instance per thread or guard externally.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _default_db_path()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def _migrate(self):
        c = self._conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS experiments (
                id               TEXT PRIMARY KEY,
                disease_id       TEXT NOT NULL,
                compound_id      TEXT NOT NULL,
                evidence_snapshot TEXT NOT NULL,
                parent_id        TEXT,
                status           TEXT NOT NULL DEFAULT 'active',
                created_at       TEXT NOT NULL,
                label            TEXT
            );

            CREATE TABLE IF NOT EXISTS observations (
                observation_id   TEXT PRIMARY KEY,
                experiment_id    TEXT NOT NULL,
                session_id       TEXT NOT NULL,
                instrument_id    TEXT NOT NULL,
                kind             TEXT NOT NULL,
                epistemic_state  TEXT NOT NULL,
                quality_state    TEXT NOT NULL DEFAULT 'UNKNOWN',
                artifact_path    TEXT NOT NULL,
                artifact_sha256  TEXT NOT NULL,
                acquisition_utc  TEXT NOT NULL,
                sample_count     INTEGER NOT NULL DEFAULT 0,
                duration_s       REAL NOT NULL DEFAULT 0.0,
                quantities_json  TEXT NOT NULL DEFAULT '[]',
                calibration_id   TEXT,
                notes            TEXT,
                parent_observation_id TEXT,
                FOREIGN KEY (experiment_id) REFERENCES experiments(id)
            );

            CREATE TABLE IF NOT EXISTS staging (
                observation_id   TEXT PRIMARY KEY,
                staged_at        TEXT NOT NULL,
                kind             TEXT NOT NULL,
                instrument_id    TEXT NOT NULL,
                session_id       TEXT NOT NULL,
                epistemic_state  TEXT NOT NULL,
                quality_state    TEXT NOT NULL DEFAULT 'UNKNOWN',
                artifact_path    TEXT NOT NULL,
                artifact_sha256  TEXT NOT NULL,
                acquisition_utc  TEXT NOT NULL,
                sample_count     INTEGER NOT NULL DEFAULT 0,
                duration_s       REAL NOT NULL DEFAULT 0.0,
                quantities_json  TEXT NOT NULL DEFAULT '[]',
                notes            TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_obs_experiment
                ON observations(experiment_id);
        """)
        
        # Migrate schema for existing tables if columns are missing
        obs_cols = {r[1] for r in c.execute("PRAGMA table_info(observations)").fetchall()}
        if "quality_state" not in obs_cols:
            c.execute("ALTER TABLE observations ADD COLUMN quality_state TEXT NOT NULL DEFAULT 'UNKNOWN'")
        if "parent_observation_id" not in obs_cols:
            c.execute("ALTER TABLE observations ADD COLUMN parent_observation_id TEXT")

        staging_cols = {r[1] for r in c.execute("PRAGMA table_info(staging)").fetchall()}
        if "quality_state" not in staging_cols:
            c.execute("ALTER TABLE staging ADD COLUMN quality_state TEXT NOT NULL DEFAULT 'UNKNOWN'")
            
        c.commit()

    # ── Experiments ───────────────────────────────────────────────────────────

    def save_experiment(
        self,
        experiment_id: str,
        disease_id: str,
        compound_id: str,
        evidence_snapshot: str,
        parent_id: Optional[str] = None,
        label: Optional[str] = None,
        status: str = "active",
    ):
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO experiments
                (id, disease_id, compound_id, evidence_snapshot,
                 parent_id, status, created_at, label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (experiment_id, disease_id, compound_id, evidence_snapshot,
             parent_id, status, now, label),
        )
        self._conn.commit()

    def update_experiment_status(self, experiment_id: str, status: str):
        self._conn.execute(
            "UPDATE experiments SET status = ? WHERE id = ?",
            (status, experiment_id),
        )
        self._conn.commit()

    def get_experiment(self, experiment_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_experiments(self) -> List[dict]:
        rows = self._conn.execute(
            "SELECT * FROM experiments ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Observations ──────────────────────────────────────────────────────────

    def save_observation(self, obs: ExperimentObservation):
        existing = self._conn.execute(
            "SELECT epistemic_state, artifact_sha256 FROM observations WHERE observation_id = ?",
            (obs.observation_id,)
        ).fetchone()

        if existing and existing["epistemic_state"] == EpistemicState.MEASURED.value:
            if existing["artifact_sha256"] != obs.artifact_sha256:
                raise ValueError("Cannot mutate an existing MEASURED RawObservation")
                
        parent_id = getattr(obs, "parent_observation_id", None)

        self._conn.execute(
            """
            INSERT OR REPLACE INTO observations
                (observation_id, experiment_id, session_id, instrument_id,
                 kind, epistemic_state, quality_state, artifact_path, artifact_sha256,
                 acquisition_utc, sample_count, duration_s, quantities_json,
                 calibration_id, notes, parent_observation_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obs.observation_id,
                obs.experiment_id,
                obs.session_id,
                obs.instrument_id,
                obs.kind.value,
                obs.epistemic_state.value,
                getattr(obs, "quality_state", getattr(QualityState, "UNKNOWN", "UNKNOWN")).value if hasattr(obs, "quality_state") and hasattr(getattr(obs, "quality_state"), "value") else getattr(obs, "quality_state", "UNKNOWN"),
                obs.artifact_path,
                obs.artifact_sha256,
                obs.acquisition_utc,
                obs.sample_count,
                obs.duration_s,
                _serialize_quantities(obs.quantities),
                obs.calibration_id,
                obs.notes,
                parent_id
            ),
        )
        self._conn.commit()

    def get_observations_for_experiment(
        self, experiment_id: str
    ) -> List[ExperimentObservation]:
        rows = self._conn.execute(
            "SELECT * FROM observations WHERE experiment_id = ? ORDER BY acquisition_utc",
            (experiment_id,),
        ).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def _row_to_obs(self, row: sqlite3.Row) -> ExperimentObservation:
        from virtual_lab.domain.observation import RawObservation, NormalizedObservation
        kind = ObservationKind(row["kind"])
        epistemic_state = EpistemicState(row["epistemic_state"])
        quality_state = QualityState(row["quality_state"]) if "quality_state" in row.keys() else QualityState.UNKNOWN
        parent_id = row["parent_observation_id"] if "parent_observation_id" in row.keys() else None

        kwargs = {
            "observation_id": row["observation_id"],
            "experiment_id": row["experiment_id"],
            "session_id": row["session_id"],
            "instrument_id": row["instrument_id"],
            "kind": kind,
            "artifact_path": row["artifact_path"],
            "artifact_sha256": row["artifact_sha256"],
            "acquisition_utc": row["acquisition_utc"],
            "sample_count": row["sample_count"],
            "duration_s": row["duration_s"],
            "quantities": _deserialize_quantities(row["quantities_json"]),
            "calibration_id": row["calibration_id"],
            "notes": row["notes"],
            "quality_state": quality_state
        }

        if epistemic_state == EpistemicState.MEASURED:
            return RawObservation(**kwargs)
        else:
            return NormalizedObservation(epistemic_state=epistemic_state, parent_observation_id=parent_id, **kwargs)

    # ── Staging ───────────────────────────────────────────────────────────────

    def stage_observation(self, obs: ExperimentObservation):
        """
        Store an observation that was captured without an active experiment.
        It lives in staging until a researcher assigns it to an experiment.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO staging
                (observation_id, staged_at, kind, instrument_id, session_id,
                 epistemic_state, quality_state, artifact_path, artifact_sha256,
                 acquisition_utc, sample_count, duration_s,
                 quantities_json, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obs.observation_id,
                now,
                obs.kind.value,
                obs.instrument_id,
                obs.session_id,
                obs.epistemic_state.value,
                getattr(obs, "quality_state", getattr(QualityState, "UNKNOWN", "UNKNOWN")).value if hasattr(obs, "quality_state") and hasattr(getattr(obs, "quality_state"), "value") else getattr(obs, "quality_state", "UNKNOWN"),
                obs.artifact_path,
                obs.artifact_sha256,
                obs.acquisition_utc,
                obs.sample_count,
                obs.duration_s,
                _serialize_quantities(obs.quantities),
                obs.notes,
            ),
        )
        self._conn.commit()

    def list_staged(self) -> List[dict]:
        rows = self._conn.execute(
            "SELECT * FROM staging ORDER BY staged_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def assign_staged_to_experiment(
        self, observation_id: str, experiment_id: str
    ) -> Optional[ExperimentObservation]:
        """
        Move an observation from staging to the experiments table.
        Returns the fully attached ExperimentObservation on success.
        """
        row = self._conn.execute(
            "SELECT * FROM staging WHERE observation_id = ?", (observation_id,)
        ).fetchone()
        if not row:
            return None

        from virtual_lab.domain.observation import RawObservation, NormalizedObservation
        
        kind = ObservationKind(row["kind"])
        epistemic_state = EpistemicState(row["epistemic_state"])
        quality_state = QualityState(row["quality_state"]) if "quality_state" in row.keys() else QualityState.UNKNOWN

        kwargs = {
            "observation_id": row["observation_id"],
            "experiment_id": experiment_id,
            "session_id": row["session_id"],
            "instrument_id": row["instrument_id"],
            "kind": kind,
            "artifact_path": row["artifact_path"],
            "artifact_sha256": row["artifact_sha256"],
            "acquisition_utc": row["acquisition_utc"],
            "sample_count": row["sample_count"],
            "duration_s": row["duration_s"],
            "quantities": _deserialize_quantities(row["quantities_json"]),
            "notes": row["notes"],
            "quality_state": quality_state,
        }

        if epistemic_state == EpistemicState.MEASURED:
            obs = RawObservation(**kwargs)
        else:
            obs = NormalizedObservation(epistemic_state=epistemic_state, **kwargs)
        self.save_observation(obs)
        self._conn.execute(
            "DELETE FROM staging WHERE observation_id = ?", (observation_id,)
        )
        self._conn.commit()
        return obs

    def staged_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM staging").fetchone()
        return row[0] if row else 0

    def close(self):
        self._conn.close()
