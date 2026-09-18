"""
virtual_lab.engines.evidence
──────────────────────────────
Real EvidenceStore and ML eligibility engines.

Epistemic contract
──────────────────
• EvidenceEngine reads actual records from EvidenceStore — never fabricates EC50 values
• MLEngine counts real model_eligible compounds from compounds.json
• Both return UNAVAILABLE rather than fake data on failure
"""
import json
from pathlib import Path
from typing import Any, Dict

from virtual_lab.engines.base import Engine
from virtual_lab.engines.registry import EngineRegistry

_COMPOUNDS_PATH = Path(__file__).parents[1] / "gui" / "assets" / "compounds.json"


class EvidenceEngine(Engine):
    name = "evidence"
    version = "2.0.0"

    def run(self, experiment: Any) -> Dict[str, Any]:
        """
        Audit the evidence base for this experiment's compound.

        Returns real record IDs and counts from EvidenceStore.
        Never fabricates numeric pharmacological values.
        """
        try:
            from virtual_lab.gui.services.evidence_store import EvidenceStore
            from virtual_lab.gui.services.selection import ScientificSelection, SelectionKind
        except ImportError as e:
            return _unavailable("EvidenceStore", f"Import error: {e}")

        compound_id = getattr(experiment, "compound_id", None)
        evidence_snapshot = getattr(experiment, "evidence_snapshot", None)

        try:
            store = EvidenceStore()
        except Exception as e:
            return _unavailable("EvidenceStore", f"Failed to load evidence assets: {e}")

        if compound_id:
            selection = ScientificSelection(
                kind=SelectionKind.COMPOUND,
                compound_id=compound_id,
            )
            records = store.records_for_selection(selection)
        else:
            records = store.records

        return {
            "status": "AUDITED",
            "epistemic_state": "MEASURED",
            "snapshot": evidence_snapshot,
            "compound_id": compound_id,
            "record_count": len(records),
            "record_ids": [r.get("id") for r in records],
            "limitations": (
                "Evidence records establish pharmacological hypothesis only. "
                "They do not validate ODE parameters or predict clinical outcomes."
            ),
        }


class MLEngine(Engine):
    name = "ml_readiness"
    version = "2.0.0"

    def run(self, experiment: Any) -> Dict[str, Any]:
        """
        Evaluate ML training eligibility from compounds.json.

        Counts compounds with identity_status == 'model_eligible'.
        Never fabricates eligibility status.
        """
        try:
            records = json.loads(_COMPOUNDS_PATH.read_text())
        except Exception as e:
            return _unavailable("MLEngine", f"Could not load compounds.json: {e}")

        eligible = [
            r["compound_name"]
            for r in records
            if r.get("identity_status") == "model_eligible" and r.get("smiles", "").strip()
        ]
        n = len(eligible)

        if n < 10:
            eligibility = "INSUFFICIENT_DATA"
            note = f"Only {n} model-eligible compounds with SMILES. Minimum threshold is 10."
        elif n < 30:
            eligibility = "EXPLORATORY_QSAR"
            note = f"{n} model-eligible compounds. Sufficient for exploratory QSAR only."
        else:
            eligibility = "QSAR_READY"
            note = f"{n} model-eligible compounds with verified SMILES."

        return {
            "status": "ASSESSED",
            "epistemic_state": "CALCULATED",
            "eligibility": eligibility,
            "n_model_eligible": n,
            "eligible_compound_names": eligible,
            "note": note,
            "limitations": (
                "ML eligibility is based on SMILES availability and identity status only. "
                "No training or cross-validation has been performed."
            ),
        }


def _unavailable(engine_name: str, reason: str) -> Dict[str, Any]:
    return {
        "status": "UNAVAILABLE",
        "epistemic_state": "UNKNOWN",
        "engine": engine_name,
        "reason": reason,
    }


EngineRegistry.register(EvidenceEngine())
EngineRegistry.register(MLEngine())
