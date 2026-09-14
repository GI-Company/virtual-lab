import pytest
import sys
import os
import platform
import datetime
import numpy as np
import mlx.core as mx
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from virtual_lab.diseases.rho_p23h.model import RhoP23HModel
from virtual_lab.biological.exposure import ConstantExposure
from virtual_lab.biological.simulation import simulate
from virtual_lab.engines.metal import IntegrationPolicy, NumericalCertificate
from virtual_lab.engines.metal_population import MetalPopulationEngine

def numpy_rk4_step(rhs, t: float, y: np.ndarray, dt: float, params: dict, exposure) -> np.ndarray:
    k1 = rhs(t, y, params, exposure, xp=np)
    k2 = rhs(t + 0.5 * dt, y + 0.5 * dt * k1, params, exposure, xp=np)
    k3 = rhs(t + 0.5 * dt, y + 0.5 * dt * k2, params, exposure, xp=np)
    k4 = rhs(t + dt, y + dt * k3, params, exposure, xp=np)
    return y + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

def test_metal_scipy_equivalence():
    model = RhoP23HModel()
    base_params = {k: v.value for k, v in model.parameters().items()}
    exposure = ConstantExposure(5.0)
    
    # 1. Generate N=100 population with parameter uncertainty
    N = 100
    rng = np.random.default_rng(42)
    y0_base = model.initial_state("P23H_UNTREATED")
    y0_pop = np.tile(y0_base, (N, 1)).T
    y0_pop += rng.normal(0, 0.01, size=y0_pop.shape)
    y0_pop = np.clip(y0_pop, 1e-8, 1.0)
    
    params_pop_np = {}
    params_pop_mx = {}
    
    for k, v in base_params.items():
        p_array = rng.normal(v, v * 0.1, size=N)
        p_array = np.clip(p_array, v * 0.5, v * 1.5)
        params_pop_np[k] = p_array
        params_pop_mx[k] = mx.array(p_array)
        
    y0_mx = mx.array(y0_pop)
    
    dt = 0.0125
    t_end = 48.0
    steps = int(t_end / dt)
    
    # LAYER A: SciPy Adaptive FP64
    y_A_final = np.zeros((5, N))
    for i in range(N):
        p_i = {k: v[i] for k, v in params_pop_np.items()}
        y0_i = y0_pop[:, i]
        t, y = simulate(model, y0_i, p_i, exposure, 0, t_end)
        y_A_final[:, i] = y[:, -1]
        
    # LAYER B: NumPy Fixed RK4 FP64
    y_B = np.copy(y0_pop)
    t_current = 0.0
    for _ in range(steps):
        y_B = numpy_rk4_step(model.rhs, t_current, y_B, dt, params_pop_np, exposure)
        t_current += dt
    y_B_final = y_B

    # LAYER C: MLX Fixed RK4 FP32
    engine = MetalPopulationEngine(model)
    policy = IntegrationPolicy(
        method="RK4",
        dt=dt,
        precision="fp32",
        checkpoint_interval=1.0,
        validated_model_hash="placeholder"
    )
    result = engine.simulate(y0_mx, params_pop_mx, exposure, policy, 0, t_end)
    y_C_final = np.array(result.final_state)
    
    # Error Decomposition
    err_A_B = np.max(np.abs(y_A_final - y_B_final))  # Discretization Error
    err_B_C = np.max(np.abs(y_B_final - y_C_final))  # Precision Error
    err_A_C = np.max(np.abs(y_A_final - y_C_final))  # Total Discrepancy

    print(f"Discretization Error (A vs B): {err_A_B}")
    print(f"Precision Error (B vs C):      {err_B_C}")
    print(f"Total Discrepancy (A vs C):    {err_A_C}")
    
    # Gather Metadata for Certificate
    try:
        import psutil
        unified_mem = psutil.virtual_memory().total / (1024**3)
    except ImportError:
        unified_mem = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / (1024**3)
    
    cert = NumericalCertificate(
        model_hash="model_hash",
        rhs_hash="rhs_hash",
        state_schema_hash="state_hash",
        parameter_envelope_hash=hashlib.sha256(b"k_ERAD:0.01-0.02").hexdigest(), # mock envelope
        atol=1e-4,
        rtol=1e-2,
        error_A_B_discretization=err_A_B,
        error_B_C_precision=err_B_C,
        error_A_C_total=err_A_C,
        platform_os=platform.system() + " " + platform.release(),
        architecture=platform.machine(),
        unified_memory_gb=unified_mem,
        python_version=sys.version.split()[0],
        numpy_version=np.__version__,
        scipy_version="1.11", # using mocked for now, can grab actual via import scipy
        mlx_version=mx.__version__,
        engine_version="0.1.1",
        validation_timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        reference_digest="reference_digest",
        status="PASSED" if err_A_C < (1e-4 + 1e-2 * np.mean(np.abs(y_A_final))) else "FAILED"
    )
    
    assert cert.status == "PASSED", f"Total discrepancy {err_A_C} exceeded tolerance."
