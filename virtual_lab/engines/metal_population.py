import mlx.core as mx
import time
import numpy as np
from typing import Dict, Any, Tuple
from virtual_lab.diseases.base import DiseaseModel
from virtual_lab.biological.exposure import ExposureModel
from virtual_lab.biological.analysis import prcc
from .metal import IntegrationPolicy, PopulationResult

def _rk4_step(rhs, t: float, y: mx.array, dt: float, params: Dict[str, mx.array], exposure: ExposureModel) -> mx.array:
    """Fixed-step RK4 integration step in MLX."""
    k1 = rhs(t, y, params, exposure, xp=mx)
    k2 = rhs(t + 0.5 * dt, y + 0.5 * dt * k1, params, exposure, xp=mx)
    k3 = rhs(t + 0.5 * dt, y + 0.5 * dt * k2, params, exposure, xp=mx)
    k4 = rhs(t + dt, y + dt * k3, params, exposure, xp=mx)
    
    return y + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

class MetalPopulationEngine:
    """
    Massive parallel simulation engine using Apple Metal via MLX.
    Uses Structure-of-Arrays (SoA) layout for fast execution.
    """
    def __init__(self, model: DiseaseModel):
        self.model = model
        
    def simulate(
        self,
        y0: mx.array, # Shape: (num_variables, N)
        params: Dict[str, mx.array], # Each value is shape (N,)
        exposure: ExposureModel,
        policy: IntegrationPolicy,
        t_start: float,
        t_end: float,
        progress_callback: Any = None
    ) -> PopulationResult:
        
        N = y0.shape[1]
        dt = policy.dt
        steps = int((t_end - t_start) / dt)
        
        # Warmup / Cold-start timing
        # We do 1 step to compile/allocate the graph
        cold_start_begin = time.time()
        y_warmup = _rk4_step(self.model.rhs, t_start, y0, dt, params, exposure)
        mx.eval(y_warmup)
        cold_start_end = time.time()
        cold_start_time = cold_start_end - cold_start_begin

        # Steady-state execution
        t = t_start
        y = y0
        steady_state_start = time.time()
        
        progress_interval = max(1, steps // 10)
        
        for step in range(steps):
            y = _rk4_step(self.model.rhs, t, y, dt, params, exposure)
            t += dt
            
            # Periodically force evaluation to prevent the compute graph from growing infinitely
            if step > 0 and step % progress_interval == 0:
                mx.eval(y)
                if progress_callback:
                    from .metal import PopulationProgress
                    prog = PopulationProgress(
                        fraction=step / steps,
                        elapsed_seconds=time.time() - steady_state_start,
                        current_time_hours=t,
                        constraint_violations=0 
                    )
                    progress_callback(prog)
                
        # Final eval to ensure GPU execution is fully complete before stopping the timer
        mx.eval(y)
        steady_state_end = time.time()
        steady_state_time = steady_state_end - steady_state_start
        
        # Summary statistics
        medians = mx.median(y, axis=1).tolist()
        
        # PRCC Sensitivity Analysis
        # 1. Gather inputs into (N, K)
        param_names = list(params.keys())
        # params[k] is shape (N,), stack into (N, K)
        X_np = np.column_stack([np.array(params[k]) for k in param_names])
        # 2. Outputs: Let's compute PRCC against each state variable
        y_np = np.array(y) # (5, N)
        
        prcc_results = {}
        for state_idx in range(y_np.shape[0]):
            state_prcc = prcc(X_np, y_np[state_idx, :])
            prcc_results[state_idx] = {param_names[j]: float(state_prcc[j]) for j in range(len(param_names))}
        
        summaries = {
            "median_state": medians,
            "prcc": prcc_results
        }
        
        exec_meta = {
            "backend": "mlx",
            "cold_start_seconds": cold_start_time,
            "steady_state_seconds": steady_state_time,
            "total_runtime_seconds": cold_start_time + steady_state_time,
            "population_size": N,
            "steps_taken": steps
        }
        
        return PopulationResult(
            final_state=y,
            summaries=summaries,
            constraint_report=None,
            numerical_validation=None,
            execution_metadata=exec_meta,
            provenance=None
        )
