import numpy as np
from typing import Dict, Any

def k_rescue_fn(C: float, rescue_max: float, ec50: float, hill_h: float, xp: Any = np) -> float:
    """Hill response form for drug rescue."""
    # Add epsilon to denominator to prevent div by zero
    return rescue_max * (C ** hill_h) / (ec50 ** hill_h + C ** hill_h + 1e-12)

def rhs_rho_p23h(t: float, y: np.ndarray, params: Dict[str, float], exposure: Any, xp: Any = np) -> np.ndarray:
    """
    y = [R_f, R_ER, R_s, S, V]
    """
    R_f, R_ER, R_s, S, V = y
    
    # 1. Evaluate concentration
    C = exposure.concentration(t)
    
    # 2. Evaluate rescue kinetics
    k_rescue_curr = k_rescue_fn(C, params["rescue_max"], params["ec50"], params["hill_h"], xp)
    
    # 3. Derivatives
    dR_f = (
        params["k_syn"]
        - params["k_mis"] * R_f
        - params["k_traffic"] * R_f
        + k_rescue_curr * R_ER
        - params["k_deg_f"] * R_f
    )
    
    dR_ER = (
        params["k_mis"] * R_f
        - k_rescue_curr * R_ER
        - params["k_ERAD"] * R_ER
    )
    
    dR_s = (
        params["k_traffic"] * R_f
        - params["k_internalize"] * R_s
        - params["k_deg_s"] * R_s
    )
    
    dS = (
        params["k_stress"] * R_ER
        - params["k_recover"] * S
    )
    
    dV = (
        params["k_repair"] * (1.0 - V)
        - params["k_death"] * S * V
    )
    
    return xp.stack([dR_f, dR_ER, dR_s, dS, dV], axis=0)
