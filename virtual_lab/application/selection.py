from dataclasses import dataclass
from typing import Optional
from enum import Enum, auto

class SelectionKind(Enum):
    EXPERIMENT = auto()
    BRANCH = auto()
    COMPOUND = auto()
    PROTEIN = auto()
    RESIDUE = auto()
    PARAMETER = auto()
    EVIDENCE = auto()
    LEDGER_EVENT = auto()
    ENDPOINT = auto()
    NONE = auto()

@dataclass(frozen=True)
class ScientificSelection:
    kind: SelectionKind
    experiment_id: Optional[str] = None
    compound_id: Optional[str] = None
    protein_id: Optional[str] = None
    chain_id: Optional[str] = None
    residue_number: Optional[int] = None
    parameter_id: Optional[str] = None
    evidence_id: Optional[str] = None
    ledger_event_id: Optional[str] = None
    structure_id: Optional[str] = None
    model_id: Optional[int] = None
    auth_residue_number: Optional[int] = None
    insertion_code: str = ""
    label: Optional[str] = None
