import numpy as np
from scipy.integrate import solve_ivp
from typing import Dict, Any, Tuple
from virtual_lab.diseases.base import DiseaseModel
from virtual_lab.biological.state import BiologicalState
from virtual_lab.biological.constraints import enforce_non_negative, enforce_bounds

def simulate(
    model: DiseaseModel,
    initial_state: np.ndarray,
    parameters: Dict[str, float],
    exposure: Any,
    t_start: float,
    t_end: float,
    t_eval: np.ndarray = None
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Run the SciPy reference solver on the model's pure RHS.
    """
    
    def wrapped_rhs(t, y):
        # We enforce basic tolerance constraints to prevent runaway negative states
        # but do not silently clip.
        constraints = model.state_constraints()
        for i, val in enumerate(y):
            if i in constraints:
                enforce_bounds(
                    val, f"var_{i}", 
                    lower=constraints[i].get("lower", 0.0), 
                    upper=constraints[i].get("upper", 1.0), 
                    tolerance=1e-8
                )
            else:
                enforce_non_negative(val, f"var_{i}", -1e-8)
                
        dydt = model.rhs(t, y, parameters, exposure, xp=np)
        return dydt

    res = solve_ivp(
        fun=wrapped_rhs,
        t_span=(t_start, t_end),
        y0=initial_state,
        t_eval=t_eval,
        method="RK45",
        rtol=1e-6,
        atol=1e-9
    )
    
    if not res.success:
        raise RuntimeError(f"Simulation failed: {res.message}")
        
    return res.t, res.y
