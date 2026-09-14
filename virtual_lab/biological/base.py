from typing import Protocol, Any, Dict
import numpy as np

class BiologicalProcess(Protocol):
    process_id: str
    
    def requirements(self) -> Dict[str, Any]:
        """Return the requirements (states, parameters) this process needs."""
        ...
        
    def derivatives(self, t: float, state: np.ndarray, parameters: Dict[str, float], exposure: Any, xp: Any = np) -> np.ndarray:
        """
        Pure function computing the rate of change (dx/dt) for the state vector.
        Uses backend-agnostic numeric ops (xp).
        """
        ...
