"""Reproducible exploratory simulations of the existing RHO ODE; no efficacy predictions."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, math, time, uuid
import numpy as np
from scipy.integrate import solve_ivp
from virtual_lab.diseases.rho_p23h.model import RhoP23HModel
from virtual_lab.biological.exposure import ConstantExposure

class RunCancelled(Exception):
    pass

@dataclass(frozen=True)
class RunConfig:
    compound: str = "YC-001 hypothesis"
    concentration_um: float = 1.0
    members: int = 128
    duration_h: float = 48.0
    seed: int = 42
    backend: str = "numpy"
    variation: float = 0.1
    erad_multiplier: float = 1.0
    traffic_multiplier: float = 1.0
    ec50_um: float = 1.5
    rescue_max: float = 0.8
    dt_h: float = 0.025

    def validate(self):
        for name in ("members", "seed"):
            if isinstance(getattr(self, name), bool) or not isinstance(getattr(self, name), int):
                raise ValueError(f"{name} must be an integer")
        bounds = {"members": (1, 10000), "seed": (0, 2147483647),
                  "duration_h": (1, 48), "concentration_um": (0, 100),
                  "variation": (0, .5), "erad_multiplier": (.1, 3),
                  "traffic_multiplier": (.1, 3), "ec50_um": (.01, 100),
                  "rescue_max": (0, 2), "dt_h": (.005, .05)}
        for name, (lo, hi) in bounds.items():
            v = getattr(self, name)
            if not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError(f"{name} must be finite and in [{lo}, {hi}]")
        if self.backend not in ("numpy", "mlx"):
            raise ValueError("Unsupported backend")
        if not self.compound.strip() or len(self.compound) > 120:
            raise ValueError("Provide a compound or hypothesis name (max 120 characters)")


def run_simulation(config, progress=lambda _: None, cancelled=lambda: False):
    cfg = config if isinstance(config, RunConfig) else RunConfig(**config)
    cfg.validate()
    started = time.perf_counter()
    model = RhoP23HModel()
    base = {k: v.value for k, v in model.parameters().items()}
    base.update(ec50=cfg.ec50_um, rescue_max=cfg.rescue_max)
    base["k_ERAD"] *= cfg.erad_multiplier
    base["k_traffic"] *= cfg.traffic_multiplier
    rng = np.random.default_rng(cfg.seed)
    # Positive lognormal ensemble represents assumed parameter uncertainty, not patients.
    draws = {k: v * rng.lognormal(-cfg.variation**2 / 2, cfg.variation, cfg.members)
             for k, v in base.items()}
    xp = np
    if cfg.backend == "mlx":
        import mlx.core as xp
    dtype = xp.float64 if cfg.backend == "numpy" else xp.float32
    params = {k: xp.array(v, dtype=dtype) for k, v in draws.items()}
    y0 = np.repeat(model.initial_state()[:, None], cfg.members, axis=1)
    treated = xp.array(y0, dtype=dtype)
    control = xp.array(y0, dtype=dtype)
    times = np.linspace(0, cfg.duration_h, 97)
    exposure, vehicle = ConstantExposure(cfg.concentration_um), ConstantExposure(0)
    traces, controls = [], []
    def materialize(y):
        if cfg.backend == "mlx":
            xp.eval(y)
        a = np.asarray(y).astype(float)
        if not np.isfinite(a).all() or (a < -1e-6).any() or (a[4] > 1+1e-6).any():
            raise ValueError("Integration violated state constraints; no successful result was saved")
        return a
    def step(t, y, dt, exp):
        f = model.rhs
        k1 = f(t,y,params,exp,xp=xp)
        k2 = f(t+dt/2,y+dt*k1/2,params,exp,xp=xp)
        k3 = f(t+dt/2,y+dt*k2/2,params,exp,xp=xp)
        k4 = f(t+dt,y+dt*k3,params,exp,xp=xp)
        return y + dt*(k1+2*k2+2*k3+k4)/6
    for i, end in enumerate(times):
        if cancelled(): raise RunCancelled("Cancelled by user")
        if i:
            start = times[i-1]
            steps = math.ceil((end-start)/cfg.dt_h)
            dt = (end-start)/steps
            for j in range(steps):
                if cancelled(): raise RunCancelled("Cancelled by user")
                treated = step(start+j*dt, treated, dt, exposure)
                control = step(start+j*dt, control, dt, vehicle)
                if cfg.backend == "mlx" and j % 16 == 0:
                    xp.eval(treated, control)
        a, b = materialize(treated), materialize(control)
        traces.append(np.quantile(a,[.05,.5,.95],axis=1).tolist())
        controls.append(np.quantile(b,[.05,.5,.95],axis=1).tolist())
        progress(round(i/96*90))
    # Independently check a declared subset, at the final checkpoint.
    errors, scaled = [], []
    for member in range(min(cfg.members, 8)):
        if cancelled(): raise RunCancelled("Cancelled by user")
        p = {k: v[member] for k,v in draws.items()}
        for exp, final in ((exposure,a),(vehicle,b)):
            ref = solve_ivp(lambda t,y: model.rhs(t,y,p,exp), (0,cfg.duration_h),
                            y0[:,member], method="DOP853", rtol=1e-10, atol=1e-12)
            if not ref.success: raise ValueError(ref.message)
            delta = abs(ref.y[:,-1] - final[:,member])
            errors.append(float(delta.max()))
            scaled.append(float((delta/(1e-5+1e-4*abs(ref.y[:,-1]))).max()))
    sources = [Path(__file__), Path(__file__).parents[2]/'diseases/rho_p23h/model.py',
               Path(__file__).parents[2]/'diseases/rho_p23h/processes.py',
               Path(__file__).parents[2]/'diseases/rho_p23h/parameters.py']
    # __file__ is gui/services; disease files live below virtual_lab.
    sources = [sources[0]] + [Path(__file__).parents[2]/'diseases/rho_p23h'/p.name for p in sources[1:]]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    result = {"schema_version":1, "id":str(uuid.uuid4()), "created_at":datetime.now(timezone.utc).isoformat(),
              "status":"completed", "epistemic_state":"MODEL_ASSUMPTION",
              "config":asdict(cfg), "state_names":model.state_schema(), "times_h":times.tolist(),
              "treated_quantiles":traces, "control_quantiles":controls,
              "final_state":a.T.tolist(), "control_final_state":b.T.tolist(),
              "parameter_samples":{k:v.tolist() for k,v in draws.items()}, "source_hashes":hashes,
              "numerical_check":{"status":"PASSED" if max(scaled)<=1 else "FAILED",
                 "reference":"SciPy DOP853 float64", "checked_members":min(cfg.members,8),
                 "scope":"Final state of first up to 8 members, treated and paired vehicle; not biological validation",
                 "atol":1e-5, "rtol":1e-4, "max_absolute_error":max(errors), "max_scaled_error":max(scaled)},
              "runtime_seconds":time.perf_counter()-started, "numpy_version":np.__version__,
              "constraint_check_scope":"97 trajectory checkpoints, all members, treated and control",
              "limitations":["Uncalibrated RHO P23H model; outputs are normalized model states, not patient outcomes.",
                  "All compound-response values entered here are hypotheses; a compound name does not transfer activity evidence.",
                  "Uncertainty bands reflect the chosen lognormal parameter distribution, not clinical confidence intervals.",
                  "No ML training or tissue/clinical efficacy validation was performed."]}
    progress(100)
    return result
