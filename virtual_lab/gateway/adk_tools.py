"""
virtual_lab.gateway.adk_tools
─────────────────────────────
Type-annotated, document-stringed tool callables for Google Vertex ADK agents.
Routes agent function calls directly to the authoritative Virtual Lab Gateway,
ExperimentStore, GenesisLedger, and numerical analysis engines.
Strictly complies with the Zero-Fabrication Rule.
"""

import os
import uuid
from typing import Dict, Any, List, Optional
import numpy as np

from virtual_lab.gateway.api import (
    device_list as gw_device_list,
    device_describe as gw_device_describe,
    device_status as gw_device_status,
    device_calibration_get as gw_device_calibration_get,
)
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.core.ledger import GenesisLedger, Actor
from virtual_lab.core.provenance_export import explain_provenance, verify_genesis_chain


# ─────────────────────────────────────────────────────────────────────────────
# 1. Instrument Agent Tools (Physical Hardware Interface)
# ─────────────────────────────────────────────────────────────────────────────

def device_list() -> Dict[str, Any]:
    """Discover all hardware instruments and SensorNode devices currently connected or known to Virtual Lab.

    Returns:
        A dictionary matching vlab.tool.v1 containing the list of discovered devices.
        Returns an empty list if no hardware is detected. Never fabricates devices.
    """
    resp = gw_device_list(requesting_agent="instrument_agent")
    return resp.model_dump()


def device_describe(device_id: str) -> Dict[str, Any]:
    """Retrieve factual specifications and capabilities of a known Virtual Lab hardware device.

    Args:
        device_id: The unique identifier of the device (e.g. sensornode-adb-R3CYA0ECXRW).

    Returns:
        A dictionary matching vlab.tool.v1 with factual hardware specifications.
        Unknown fields are null. Never infers missing characteristics.
    """
    resp = gw_device_describe(device_id, requesting_agent="instrument_agent")
    return resp.model_dump()


def device_status(device_id: str) -> Dict[str, Any]:
    """Query live connectivity and diagnostic status for a hardware device.

    Args:
        device_id: The unique identifier of the device.

    Returns:
        A dictionary matching vlab.tool.v1 containing status (ONLINE, OFFLINE, DEGRADED, BUSY)
        and diagnostic telemetry. Never reports ONLINE unless actual runtime evidence supports it.
    """
    resp = gw_device_status(device_id, requesting_agent="instrument_agent")
    return resp.model_dump()


def device_calibration_get(device_id: str) -> Dict[str, Any]:
    """Retrieve verified calibration metadata for a device.

    Args:
        device_id: The unique identifier of the device.

    Returns:
        A dictionary matching vlab.tool.v1 with calibration metadata.
        If no calibration record exists, returns status UNAVAILABLE with reason NO_CALIBRATION_RECORD.
        Never generates calibration values.
    """
    resp = gw_device_calibration_get(device_id, requesting_agent="instrument_agent")
    return resp.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Experiment Agent Tools (Safe Metadata & Protocol Tracking Only)
# ─────────────────────────────────────────────────────────────────────────────

def experiment_create(
    label: str,
    experiment_id: Optional[str] = None,
    disease_id: str = "general",
    compound_id: str = "none"
) -> Dict[str, Any]:
    """Create a structured experiment record in Virtual Lab.

    Does NOT execute runs or actuate hardware. Pure workflow definition.

    Args:
        label: Descriptive title or hypothesis label for the experiment.
        experiment_id: Optional custom identifier. Auto-generated if omitted.
        disease_id: Relevant disease or biological program ID.
        compound_id: Relevant chemical or test compound identifier.

    Returns:
        Dictionary with creation status and confirmed experiment ID.
    """
    exp_id = experiment_id or f"EXP-{uuid.uuid4().hex[:8]}"
    try:
        store = ExperimentStore()
        store.save_experiment(
            experiment_id=exp_id,
            disease_id=disease_id,
            compound_id=compound_id,
            evidence_snapshot="",
            label=label,
            status="active"
        )
        return {
            "schema_version": "vlab.tool.v1",
            "status": "COMPLETED",
            "experiment_id": exp_id,
            "label": label,
            "lifecycle_state": "DRAFT"
        }
    except Exception as e:
        return {
            "schema_version": "vlab.tool.v1",
            "status": "FAILED",
            "error": str(e)
        }


def experiment_get(experiment_id: str) -> Dict[str, Any]:
    """Retrieve existing experiment metadata and observations from Virtual Lab.

    Args:
        experiment_id: The experiment identifier to look up.

    Returns:
        Dictionary containing experiment details and attached observation count.
    """
    try:
        store = ExperimentStore()
        exp = store.get_experiment(experiment_id)
        if not exp:
            return {
                "schema_version": "vlab.tool.v1",
                "status": "UNAVAILABLE",
                "reason": f"Experiment '{experiment_id}' not found."
            }
        obs = store.get_observations_for_experiment(experiment_id)
        return {
            "schema_version": "vlab.tool.v1",
            "status": "COMPLETED",
            "experiment": dict(exp),
            "observation_count": len(obs)
        }
    except Exception as e:
        return {
            "schema_version": "vlab.tool.v1",
            "status": "FAILED",
            "error": str(e)
        }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Analysis Agent Tools (Empirical Dataset Processing Only)
# ─────────────────────────────────────────────────────────────────────────────

def dataset_summary_statistics(values: List[float], metric_name: str = "measurement") -> Dict[str, Any]:
    """Compute exact descriptive statistics over supplied numerical data.

    Never fabricates missing observations or extrapolates beyond supplied data.

    Args:
        values: List of numerical measurements.
        metric_name: Label or physical dimension name for the metric.

    Returns:
        Dictionary containing sample count, mean, std, min, max, median, and uncertainty estimate.
    """
    if not values:
        return {
            "schema_version": "vlab.tool.v1",
            "status": "FAILED",
            "error": "No data values supplied for analysis."
        }

    arr = np.array(values, dtype=float)
    count = int(len(arr))
    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr, ddof=1)) if count > 1 else 0.0
    sem = std_val / np.sqrt(count) if count > 1 else 0.0

    return {
        "schema_version": "vlab.tool.v1",
        "status": "COMPLETED",
        "metric_name": metric_name,
        "sample_count": count,
        "mean": mean_val,
        "std_dev": std_val,
        "standard_error": sem,
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "median": float(np.median(arr)),
        "epistemic_classification": "DERIVED_STATISTICAL_RESULT"
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Integrity Agent Tools (Provenance & Cryptographic Verification)
# ─────────────────────────────────────────────────────────────────────────────

def provenance_verify(target_path: Optional[str] = None) -> Dict[str, Any]:
    """Verify the cryptographic hash chain of the Genesis Ledger or a .vlab research bundle.

    Args:
        target_path: Path to genesis.db or .vlab bundle file. Defaults to .virtuallab/genesis.db.

    Returns:
        Verification verdict (VERIFIED, FAILED, or UNAVAILABLE).
    """
    path = target_path or ".virtuallab/genesis.db"
    if not os.path.exists(path):
        return {
            "schema_version": "vlab.tool.v1",
            "status": "UNAVAILABLE",
            "verdict": "UNSUPPORTED",
            "reason": f"Path '{path}' does not exist on disk."
        }

    if path.endswith(".vlab"):
        report = explain_provenance(path)
        is_ok = "BUNDLE PROVENANCE VERIFIED" in report or "Genesis hash chain: VERIFIED" in report
        return {
            "schema_version": "vlab.tool.v1",
            "status": "COMPLETED" if is_ok else "FAILED",
            "verdict": "VERIFIED" if is_ok else "CONFLICTING",
            "report": report
        }
    else:
        try:
            events = verify_genesis_chain(path)
            return {
                "schema_version": "vlab.tool.v1",
                "status": "COMPLETED",
                "verdict": "VERIFIED",
                "verified_event_count": len(events)
            }
        except Exception as exc:
            return {
                "schema_version": "vlab.tool.v1",
                "status": "FAILED",
                "verdict": "CONFLICTING",
                "error": str(exc)
            }


def artifact_get(artifact_ref: str) -> Dict[str, Any]:
    """Retrieve factual metadata and cryptographic hash of a stored laboratory artifact.

    Args:
        artifact_ref: Relative path or filename of the artifact (e.g. .virtuallab/artifacts/capture.jpg).

    Returns:
        Dictionary matching vlab.tool.v1 containing existence, sha256 hash, size_bytes, and path.
        Returns UNAVAILABLE if the artifact does not exist on disk.
    """
    import hashlib

    if not artifact_ref or not isinstance(artifact_ref, str):
        return {
            "schema_version": "vlab.tool.v1",
            "status": "FAILED",
            "error": "artifact_ref must be a non-empty string."
        }

    norm_path = os.path.normpath(artifact_ref.strip())
    if norm_path.startswith("..") or (os.path.isabs(norm_path) and not norm_path.startswith(os.getcwd())):
        return {
            "schema_version": "vlab.tool.v1",
            "status": "FAILED",
            "error": "Access outside project directory is disallowed."
        }

    if not os.path.exists(norm_path):
        return {
            "schema_version": "vlab.tool.v1",
            "status": "UNAVAILABLE",
            "reason": f"Artifact '{artifact_ref}' does not exist on disk."
        }

    try:
        size = os.path.getsize(norm_path)
        hasher = hashlib.sha256()
        with open(norm_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()

        return {
            "schema_version": "vlab.tool.v1",
            "status": "COMPLETED",
            "artifact_ref": artifact_ref,
            "artifact_path": norm_path,
            "artifact_sha256": digest,
            "size_bytes": size,
        }
    except Exception as e:
        return {
            "schema_version": "vlab.tool.v1",
            "status": "FAILED",
            "error": str(e)
        }

