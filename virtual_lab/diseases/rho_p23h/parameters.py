from typing import Dict
from virtual_lab.biological.parameters import Parameter, EpistemicState

# Baseline parameters for P23H ODE Model
# Time unit: hours
# Concentration: normalized

RHO_P23H_PARAMETERS: Dict[str, Parameter] = {
    "k_syn": Parameter("k_syn", 1.0, EpistemicState.INFERRED, unit="1/h"),
    "k_mis": Parameter("k_mis", 0.5, EpistemicState.INFERRED, unit="1/h"),
    "k_deg_f": Parameter("k_deg_f", 0.05, EpistemicState.INFERRED, unit="1/h"),
    "k_traffic": Parameter("k_traffic", 0.3, EpistemicState.INFERRED, unit="1/h"),
    "k_ERAD": Parameter("k_ERAD", 0.2, EpistemicState.INFERRED, unit="1/h"),
    "k_internalize": Parameter("k_internalize", 0.1, EpistemicState.INFERRED, unit="1/h"),
    "k_deg_s": Parameter("k_deg_s", 0.05, EpistemicState.INFERRED, unit="1/h"),
    
    "k_stress": Parameter("k_stress", 0.1, EpistemicState.MODEL_ASSUMPTION, unit="1/h"),
    "k_recover": Parameter("k_recover", 0.1, EpistemicState.MODEL_ASSUMPTION, unit="1/h"),
    
    "k_repair": Parameter("k_repair", 0.01, EpistemicState.MODEL_ASSUMPTION, unit="1/h"),
    "k_death": Parameter("k_death", 0.05, EpistemicState.MODEL_ASSUMPTION, unit="1/h"),
    
    "rescue_max": Parameter("rescue_max", 0.8, EpistemicState.INFERRED, unit="1/h"),
    "ec50": Parameter("ec50", 1.5, EpistemicState.MEASURED, unit="uM"),
    "hill_h": Parameter("hill_h", 1.0, EpistemicState.UNKNOWN, unit="dimensionless"),
}
