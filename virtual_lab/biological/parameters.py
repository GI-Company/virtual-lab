from dataclasses import dataclass
from typing import Optional, Any
from enum import Enum

class EpistemicState(Enum):
    DEFINED = "DEFINED"
    MEASURED = "MEASURED"
    CURATED = "CURATED"
    DERIVED = "DERIVED"
    CALCULATED = "CALCULATED"
    SIMULATED = "SIMULATED"
    PREDICTED = "PREDICTED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"
    MODEL_ASSUMPTION = "MODEL_ASSUMPTION"

@dataclass(frozen=True)
class Parameter:
    name: str
    value: float
    epistemic_state: EpistemicState
    unit: Optional[str] = None
    uncertainty: Optional[float] = None
    source: Optional[str] = None
