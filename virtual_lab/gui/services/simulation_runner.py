"""Shared, reproducible paired simulations for registered models; no efficacy predictions."""
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
import hashlib, json, math, time, uuid
import numpy as np
from scipy.integrate import solve_ivp
from virtual_lab.models.registry import get_model
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
    model_id: str = "rho_p23h"
    model_parameters: dict = field(default_factory=dict)

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
        spec = get_model(self.model_id)
        spec.validated_parameters(self.model_parameters)
        if self.backend not in spec.backends:
            raise ValueError("Unsupported backend")
        if not self.compound.strip() or len(self.compound) > 120:
            raise ValueError("Provide a compound or hypothesis name (max 120 characters)")


def run_simulation(config, progress=lambda _: None, cancelled=lambda: False):
    cfg = config if isinstance(config, RunConfig) else RunConfig(**config)
    cfg.validate()
    started = time.perf_counter()
    spec = get_model(cfg.model_id)
    model = spec.factory()
    supplied = cfg.model_parameters
    if cfg.model_id == 'rho_p23h' and not supplied:
        # Preserve old scripts and saved designs that used top-level RHO controls.
        supplied = dict(ec50=cfg.ec50_um, rescue_max=cfg.rescue_max,
                        erad_multiplier=cfg.erad_multiplier, traffic_multiplier=cfg.traffic_multiplier)
    model_controls = spec.validated_parameters(supplied)
    base = spec.prepare_parameters(model, model_controls)
    if list(model.state_schema()) != [state.key for state in spec.states]:
        raise ValueError('Model state schema does not match its registered metadata.')
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
    if y0.shape != (len(spec.states), cfg.members):
        raise ValueError("Model initial state has the wrong shape.")
    treated = xp.array(y0, dtype=dtype)
    control = xp.array(y0, dtype=dtype)
    times = np.linspace(0, cfg.duration_h, 97)
    exposure, vehicle = ConstantExposure(cfg.concentration_um), ConstantExposure(0)
    traces, control_traces = [], []
    def materialize(y):
        if cfg.backend == "mlx":
            xp.eval(y)
        a = np.asarray(y).astype(float)
        if not np.isfinite(a).all():
            raise ValueError("Integration produced nonfinite states.")
        for index, state in enumerate(spec.states):
            if (a[index] < state.lower - 1e-6).any() or (state.upper is not None and (a[index] > state.upper + 1e-6).any()):
                raise ValueError(f"Integration violated constraints for {state.key}; no successful result was saved")
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
        control_traces.append(np.quantile(b,[.05,.5,.95],axis=1).tolist())
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
    from virtual_lab.models import registry
    sources = (Path(__file__), Path(registry.__file__), Path(registry.__file__).with_name('builtin.py'), *spec.source_files)
    hashes = {str(p.relative_to(Path(__file__).parents[2])) if p.is_relative_to(Path(__file__).parents[2]) else str(p):
              hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    saved_config = asdict(cfg)
    for key in ('ec50_um', 'rescue_max', 'erad_multiplier', 'traffic_multiplier'):
        saved_config.pop(key)
    saved_config['model_parameters'] = model_controls
    result = {"schema_version":2, "id":str(uuid.uuid4()), "created_at":datetime.now(timezone.utc).isoformat(),
              "status":"completed", "epistemic_state":"SIMULATED",
              "model_id":spec.id, "model_version":spec.version, "model_label":spec.label,
              "state_metadata":[asdict(state) for state in spec.states],
              "resolved_parameters":model_controls, "parameter_epistemic_state":"MODEL_ASSUMPTION",
              "config":saved_config, "state_names":model.state_schema(), "times_h":times.tolist(),
              "treated_quantiles":traces, "control_quantiles":control_traces,
              "final_state":a.T.tolist(), "control_final_state":b.T.tolist(),
              "parameter_samples":{k:v.tolist() for k,v in draws.items()}, "source_hashes":hashes,
              "numerical_check":{"status":"PASSED" if max(scaled)<=1 else "FAILED",
                 "reference":"SciPy DOP853 float64", "checked_members":min(cfg.members,8),
                 "scope":"Final state of first up to 8 members, exposure and paired zero-exposure control; not biological validation",
                 "atol":1e-5, "rtol":1e-4, "max_absolute_error":max(errors), "max_scaled_error":max(scaled)},
              "runtime_seconds":time.perf_counter()-started, "numpy_version":np.__version__,
              "constraint_check_scope":"97 trajectory checkpoints, all members, treated and control",
              "limitations":[*spec.limitations,
                  "Uncertainty bands reflect the chosen lognormal parameter distribution, not clinical confidence intervals.",
                  "Numerical agreement is not biological validation."]}
    progress(100)
    return result
