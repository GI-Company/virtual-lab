from typing import Protocol, List, Dict, Any
from virtual_lab.biological.parameters import Parameter
import numpy as np

class DiseaseModel(Protocol):
    disease_id: str

    def state_schema(self) -> List[str]:
        ...
        
    def state_constraints(self) -> Dict[int, Dict[str, float]]:
        """Returns bounds for variables by index. e.g. {4: {'lower': 0.0, 'upper': 1.0}}"""
        ...
        
    def parameters(self) -> Dict[str, Parameter]:
        ...
        
    def metadata(self) -> Dict[str, Any]:
        """Returns non-scientific run settings, mutation info, etc."""
        ...
        
    def initial_state(self, condition: str) -> np.ndarray:
        ...
        
    def rhs(self, t: float, y: np.ndarray, params: Dict[str, float], exposure: Any, xp: Any = np) -> np.ndarray:
        ...
        
    def settle_to_equilibrium(self, params: Dict[str, float], exposure: Any, xp: Any = np) -> np.ndarray:
        ...
