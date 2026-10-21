from dataclasses import dataclass
from typing import Optional, Any
from virtual_lab.domain.epistemics import EpistemicState

@dataclass(frozen=True)
class Parameter:
    name: str
    value: float
    epistemic_state: EpistemicState
    unit: Optional[str] = None
    uncertainty: Optional[float] = None
    source: Optional[str] = None
