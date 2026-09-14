import pytest
import sys
import numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from virtual_lab.diseases.rho_p23h.model import RhoP23HModel
from virtual_lab.biological.exposure import ConstantExposure
from virtual_lab.biological.simulation import simulate
from virtual_lab.biological.constraints import BiologicalConstraintViolation
from virtual_lab.diseases.rho_p23h.observables import VirtualTraffickingAssay

def get_base_params(model: RhoP23HModel):
    return {k: v.value for k, v in model.parameters().items()}

def test_numerical_stability():
    model = RhoP23HModel()
    params = get_base_params(model)
    exposure = ConstantExposure(0.0)
    
    eq_state = model.settle_to_equilibrium(params, exposure)
    
    # Verify that rhs(eq_state) ~ 0
    dydt = model.rhs(0.0, eq_state, params, exposure)
    assert np.allclose(dydt, 0.0, atol=1e-6)
    
    # Verify bounds logic hasn't pushed viability over 1
    assert eq_state[4] <= 1.0 + 1e-8
    assert eq_state[4] >= -1e-8

def test_yc001_directional_calibration_anchor():
    model = RhoP23HModel()
    params = get_base_params(model)
    
    exposure_zero = ConstantExposure(0.0)
    exposure_treated = ConstantExposure(10.0) # 10 uM, well above ec50=1.5
    
    # Get baseline disease equilibrium
    eq_untreated = model.settle_to_equilibrium(params, exposure_zero)
    
    # Run 48 hours of treatment from that equilibrium
    t, y_treated = simulate(model, eq_untreated, params, exposure_treated, 0, 48.0)
    
    final_treated_state = y_treated[:, -1]
    
    # R_s (index 2) should increase
    assert final_treated_state[2] > eq_untreated[2]
    
    # R_ER (index 1) should decrease
    assert final_treated_state[1] < eq_untreated[1]
    
    # Stress (index 3) should not increase (should decrease)
    assert final_treated_state[3] <= eq_untreated[3]
    
    # Viability (index 4) should be non-decreasing
    assert final_treated_state[4] >= eq_untreated[4] - 1e-8

def test_bounds_violations():
    model = RhoP23HModel()
    params = get_base_params(model)
    exposure = ConstantExposure(0.0)
    
    # Force a massive negative concentration to trigger violation
    bad_state = np.array([-10.0, 0.8, 0.05, 0.5, 0.8])
    
    with pytest.raises(BiologicalConstraintViolation):
        simulate(model, bad_state, params, exposure, 0, 1.0)
        
    # Force viability > 1
    bad_state_v = np.array([0.1, 0.8, 0.05, 0.5, 2.5])
    with pytest.raises(BiologicalConstraintViolation):
        simulate(model, bad_state_v, params, exposure, 0, 1.0)

def test_seeded_virtual_assay_noise():
    assay = VirtualTraffickingAssay(sigma=0.05)
    
    state = np.array([0.1, 0.8, 0.5, 0.5, 0.8]) # R_s is 0.5
    
    # Same seed should give identical readouts
    obs1 = assay.observe(state, seed=42)
    obs2 = assay.observe(state, seed=42)
    assert obs1.value == obs2.value
    assert obs1.noise == obs2.noise
    
    # Different seed should differ
    obs3 = assay.observe(state, seed=43)
    assert obs1.value != obs3.value
    
    # Hidden state must remain distinct from observed value due to noise
    assert obs1.value != obs1.true_hidden_state
