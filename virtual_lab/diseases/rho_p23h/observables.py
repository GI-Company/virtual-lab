import numpy as np
from virtual_lab.biological.observables import VirtualAssay, AssayResult
from virtual_lab.biological.parameters import EpistemicState

class VirtualTraffickingAssay(VirtualAssay):
    """
    Measures surface rhodopsin fluorescence.
    Model: y = a * R_s + b + N(0, sigma)
    """
    def __init__(self, a: float = 1.0, b: float = 0.0, sigma: float = 0.05):
        self.a = a
        self.b = b
        self.sigma = sigma
        
    def observe(self, state: np.ndarray, seed: int) -> AssayResult:
        # R_s is index 2
        R_s = state[2]
        
        rng = np.random.default_rng(seed)
        noise = rng.normal(0, self.sigma)
        
        measured = self.a * R_s + self.b + noise
        # Assay fluorescence can't be strictly negative in real life typically,
        # but for v0.1 we just return it.
        measured = max(0.0, measured)
        
        return AssayResult(
            value=measured,
            true_hidden_state=R_s,
            noise=noise,
            epistemic_state=EpistemicState.SIMULATED
        )

class VirtualViabilityAssay(VirtualAssay):
    """
    Measures cell viability.
    Model: y = V + N(0, sigma)
    """
    def __init__(self, sigma: float = 0.02):
        self.sigma = sigma
        
    def observe(self, state: np.ndarray, seed: int) -> AssayResult:
        # V is index 4
        V = state[4]
        
        rng = np.random.default_rng(seed)
        noise = rng.normal(0, self.sigma)
        
        measured = V + noise
        measured = np.clip(measured, 0.0, 1.0)
        
        return AssayResult(
            value=measured,
            true_hidden_state=V,
            noise=noise,
            epistemic_state=EpistemicState.SIMULATED
        )
