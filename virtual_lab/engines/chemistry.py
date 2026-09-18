"""
virtual_lab.engines.chemistry
──────────────────────────────
Real RDKit-based chemistry descriptor engine.

Epistemic contract
──────────────────
• Results carry epistemic_state = CALCULATED
• calculation_type = "COMPUTED_GEOMETRY" for 3D conformer-derived properties
• Unavailability is explicit — never returns fabricated values
"""
import json
from pathlib import Path
from typing import Any, Dict

from virtual_lab.engines.base import Engine
from virtual_lab.engines.registry import EngineRegistry

_COMPOUNDS_PATH = Path(__file__).parents[1] / "gui" / "assets" / "compounds.json"


def _get_smiles_for_compound(compound_id: str) -> str | None:
    """Look up the SMILES string for compound_id from the compounds asset."""
    try:
        records = json.loads(_COMPOUNDS_PATH.read_text())
        for rec in records:
            if rec.get("compound_name", "").upper() == compound_id.upper():
                smiles = rec.get("smiles", "").strip()
                return smiles if smiles else None
    except Exception:
        pass
    return None


class ChemistryEngine(Engine):
    name = "chemistry"
    version = "2.0.0"

    def run(self, experiment: Any) -> Dict[str, Any]:
        """
        Calculate molecular descriptors using RDKit.

        Returns a dict with:
            status:           "CALCULATED" | "UNAVAILABLE"
            epistemic_state:  "CALCULATED"
            calculation_type: "COMPUTED_GEOMETRY"
            ... descriptor values on success ...
            reason:           description of failure if UNAVAILABLE
        """
        compound_id = getattr(experiment, "compound_id", None)
        if not compound_id:
            return _unavailable("No compound_id set on experiment")

        smiles = _get_smiles_for_compound(compound_id)
        if not smiles:
            return _unavailable(
                f"No machine-readable SMILES registered for compound '{compound_id}'. "
                "Check identity_status in compounds.json."
            )

        try:
            from virtual_lab.gui.services.molecule_design import build_design
        except ImportError as e:
            return _unavailable(f"RDKit or molecule_design not importable: {e}")

        try:
            result = build_design(smiles)
        except ValueError as e:
            return _unavailable(f"RDKit descriptor calculation failed: {e}")
        except Exception as e:
            return _unavailable(f"Unexpected chemistry engine error: {type(e).__name__}: {e}")

        return {
            "status": "CALCULATED",
            "epistemic_state": "CALCULATED",
            "calculation_type": "COMPUTED_GEOMETRY",
            "compound_id": compound_id,
            "canonical_smiles": result.get("canonical_smiles"),
            "formula": result.get("formula"),
            "molecular_weight": result.get("molecular_weight"),
            "logp": result.get("logp"),
            "tpsa": result.get("tpsa"),
            "hbd": result.get("hbd"),
            "hba": result.get("hba"),
            "uff_converged": result.get("uff_converged"),
            "sdf": result.get("sdf"),
            "nearest_neighbors": result.get("neighbors", []),
            "limitations": result.get("limitations", ""),
        }


def _unavailable(reason: str) -> Dict[str, Any]:
    return {
        "status": "UNAVAILABLE",
        "epistemic_state": "UNKNOWN",
        "reason": reason,
    }


EngineRegistry.register(ChemistryEngine())
