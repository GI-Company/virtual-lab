import numpy as np
from typing import List, Dict, Any
from scipy.optimize import root

from virtual_lab.diseases.base import DiseaseModel
from virtual_lab.biological.parameters import Parameter
from virtual_lab.biological.exposure import ExposureModel, ConstantExposure

from .parameters import RHO_P23H_PARAMETERS
from .processes import rhs_rho_p23h

class RhoP23HModel(DiseaseModel):
    disease_id = "rho_p23h"
    
    def state_schema(self) -> List[str]:
        return ["R_f", "R_ER", "R_s", "S", "V"]
        
    def state_constraints(self) -> Dict[int, Dict[str, float]]:
        # V (index 4) has a strict [0.0, 1.0] bound.
        # Other states implicitly bounded >= 0 by the engine unless specified.
        return {
            4: {"lower": 0.0, "upper": 1.0}
        }
        
    def parameters(self) -> Dict[str, Parameter]:
        return RHO_P23H_PARAMETERS
        
    def metadata(self) -> Dict[str, Any]:
        return {
            "mutation": "P23H",
            "model_version": "0.1.1",
            "anchor": "YC-001-directional"
        }
        
    def initial_state(self, condition: str = "P23H_UNTREATED") -> np.ndarray:
        # Approximate untreated state, far from equilibrium but a starting point
        # [R_f, R_ER, R_s, S, V]
        if condition == "P23H_UNTREATED":
            return np.array([0.1, 0.8, 0.05, 0.5, 0.8], dtype=float)
        elif condition == "REFERENCE_HEALTHY":
            # Wild-type-like
            return np.array([0.8, 0.1, 0.8, 0.05, 1.0], dtype=float)
        else:
            raise ValueError(f"Unknown condition {condition}")
            
    def rhs(self, t: float, y: np.ndarray, params: Dict[str, float], exposure: ExposureModel, xp: Any = np) -> np.ndarray:
        return rhs_rho_p23h(t, y, params, exposure, xp)

    def settle_to_equilibrium(self, params: Dict[str, float], exposure: ExposureModel, xp: Any = np) -> np.ndarray:
        """Find the steady state dx/dt = 0 for the given parameters using long simulation."""
        from scipy.integrate import solve_ivp
        
        y0 = self.initial_state("P23H_UNTREATED")
        
        def wrapped_rhs(t, y):
            return self.rhs(t, y, params, exposure, xp=np)
            
        res = solve_ivp(
            fun=wrapped_rhs,
            t_span=(0, 10000.0),
            y0=y0,
            method="Radau", # Radau is very good for stiff biological equations settling to equilibrium
            rtol=1e-6,
            atol=1e-9
        )
        
        if not res.success:
            raise RuntimeError(f"Could not find equilibrium: {res.message}")
            
        return res.y[:, -1]
