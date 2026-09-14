import numpy as np
from dataclasses import dataclass
from typing import List

@dataclass
class BiologicalState:
    """Represents a snapshot of a continuous biological system in normalized abundances."""
    variables: List[str]
    values: np.ndarray
    time: float
    
    def get(self, name: str) -> float:
        idx = self.variables.index(name)
        return self.values[idx]
