import numpy as np
from typing import Protocol, Any, Dict
from dataclasses import dataclass
from virtual_lab.domain.epistemics import EpistemicState

@dataclass
class AssayResult:
    value: float
    true_hidden_state: float
    noise: float
    epistemic_state: EpistemicState

class VirtualAssay(Protocol):
    def observe(self, state: np.ndarray, seed: int) -> AssayResult:
        """Map hidden states to virtual assay observations with seeded noise."""
        ...
