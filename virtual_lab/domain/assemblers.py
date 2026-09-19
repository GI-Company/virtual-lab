"""
virtual_lab.domain.assemblers
──────────────────────────────
Stateless converters: Instrument Runtime artifacts → ExperimentObservation.
Simulation run results → ExperimentObservation.

No Android transport DTOs (CameraStreamKey, AdbReverseRunner, etc.) appear here.
The Instruments layer provides plain dicts from commit() / run_simulation().
"""
from __future__ import annotations

from typing import Dict, List

from virtual_lab.domain.epistemics import EpistemicState
from virtual_lab.domain.observation import (
    ExperimentObservation,
    ObservationKind,
    QuantityDescriptor,
    SENSOR_QUANTITY_MAP,
    RHO_STATE_QUANTITIES,
)


import uuid

def session_commit_to_observation(
    commit_info: dict,
    experiment_id: str,
) -> ExperimentObservation:
    """
    Convert a JsonlMeasurementStore.commit() result dict into an ExperimentObservation.
    """
    session_id      = commit_info["session_id"]
    instrument_id   = commit_info.get("instrument_id", "UNKNOWN")
    artifact_path   = commit_info["artifact_path"]
    artifact_sha256 = commit_info["artifact_sha256"]
    acquisition_utc = commit_info.get("acquisition_utc", "")
    sample_count    = commit_info.get("sample_count_total", 0)
    duration_s      = commit_info.get("duration_s", 0.0)
    quantity_types: Dict[str, int] = commit_info.get("sample_counts", {})

    quantities: List[QuantityDescriptor] = []
    for qt in quantity_types:
        descriptors = SENSOR_QUANTITY_MAP.get(qt)
        if descriptors:
            quantities.extend(descriptors)
        else:
            from virtual_lab.domain.observation import PhysicalDimension
            quantities.append(QuantityDescriptor(
                semantic_name=f"unknown_{qt.lower()}",
                symbol=qt,
                description=f"Unknown quantity type: {qt}",
                physical_dimension=PhysicalDimension.UNKNOWN_DIMENSION,
                units="",
                epistemic_state=EpistemicState.MEASURED,
            ))

    from virtual_lab.domain.observation import RawObservation
    return RawObservation(
        observation_id=str(uuid.uuid4()),
        experiment_id=experiment_id,
        session_id=session_id,
        instrument_id=instrument_id,
        kind=ObservationKind.SENSOR_STREAM,
        quantities=quantities,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        acquisition_utc=acquisition_utc,
        sample_count=sample_count,
        duration_s=duration_s,
    )


def simulation_result_to_observation(
    result: dict,
    experiment_id: str,
) -> ExperimentObservation:
    """
    Convert a simulation_runner.run_simulation() result dict into an ExperimentObservation.
    """
    run_id          = result["id"]
    artifact_sha256 = result.get("artifact_sha256", "")
    artifact_path   = result.get("artifact_path", "")
    acquisition_utc = result.get("created_at", "")

    from virtual_lab.domain.observation import NormalizedObservation
    return NormalizedObservation(
        observation_id=str(uuid.uuid4()),
        experiment_id=experiment_id,
        session_id=run_id,
        instrument_id="simulation",
        kind=ObservationKind.SIMULATION,
        quantities=list(RHO_STATE_QUANTITIES),
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        acquisition_utc=acquisition_utc,
        sample_count=result.get("config", {}).get("members", 0),
        duration_s=result.get("runtime_seconds", 0.0),
        epistemic_state=EpistemicState.SIMULATED,
    )


def chemistry_result_to_observation(
    chem_result: dict,
    experiment_id: str,
    compound_id: str,
) -> ExperimentObservation:
    """
    Convert a ChemistryEngine result dict into an ExperimentObservation.
    """
    from virtual_lab.domain.observation import (
        CHEM_MOLECULAR_WEIGHT, CHEM_LOGP, CHEM_TPSA, NormalizedObservation
    )
    import json
    from datetime import datetime, timezone

    quantities = [CHEM_MOLECULAR_WEIGHT, CHEM_LOGP, CHEM_TPSA]

    return NormalizedObservation(
        observation_id=str(uuid.uuid4()),
        experiment_id=experiment_id,
        session_id=f"chem-{compound_id}",
        instrument_id="rdkit",
        kind=ObservationKind.CHEMISTRY,
        quantities=quantities,
        artifact_path="",
        artifact_sha256=chem_result.get("artifact_sha256", ""),
        acquisition_utc=datetime.now(timezone.utc).isoformat(),
        sample_count=1,
        duration_s=0.0,
        epistemic_state=EpistemicState.CALCULATED,
        notes=json.dumps({
            "calculation_type": chem_result.get("calculation_type", "COMPUTED_GEOMETRY"),
            "canonical_smiles": chem_result.get("canonical_smiles", ""),
            "uff_converged": chem_result.get("uff_converged"),
            "limitations": chem_result.get("limitations", ""),
        }),
    )
