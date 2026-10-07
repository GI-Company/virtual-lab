from dataclasses import dataclass
from typing import Optional, Dict, Any
import numpy as np
from virtual_lab.domain.epistemics import EpistemicState

# A stub enum to match what the user requested
class EnsembleKind:
    EPISTEMIC_UNCERTAINTY = "EPISTEMIC_UNCERTAINTY"
    POPULATION_VARIABILITY = "POPULATION_VARIABILITY"

@dataclass(frozen=True)
class SimulationResult:
    run_id: str
    experiment_id: str

    times_h: np.ndarray
    final_state: np.ndarray

    summary_trajectory: Optional[Dict[str, np.ndarray]]
    endpoint_summaries: Dict[str, Any]
    numerical_check: Dict[str, Any]
    parameter_samples: Dict[str, np.ndarray]

    ensemble_kind: str # e.g. "EPISTEMIC_UNCERTAINTY"
    members: int
    seed: int
    epistemic_state: EpistemicState

    execution_metadata: Dict[str, Any]
    model_id: str = "rho_p23h"
    model_label: str = "RHO P23H trafficking"
    state_metadata: tuple = ()
    control_trajectory: Optional[Dict[str, np.ndarray]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationResult":
        # Extract summary trajectories from treated/control quantiles if available
        # The runner returns them as a list of T arrays of shape (3, N_states) where 3 is (5th, 50th, 95th)
        treated_quantiles = np.array(data.get("treated_quantiles", []))
        summary_traj = None
        if treated_quantiles.ndim == 3:
            # treated_quantiles shape is (T, 3, N_states)
            summary_traj = {
                "p05": treated_quantiles[:, 0, :],
                "median": treated_quantiles[:, 1, :],
                "p95": treated_quantiles[:, 2, :],
            }
        
        return cls(
            run_id=data.get("id", ""),
            experiment_id=data.get("experiment_id", ""),
            model_id=data.get("model_id", "rho_p23h"),
            model_label=data.get("model_label", "RHO P23H trafficking"),
            state_metadata=tuple(data.get("state_metadata") or _legacy_states()),
            control_trajectory=_quantiles(data.get("control_quantiles", [])),
            times_h=np.array(data.get("times_h", [])),
            final_state=np.array(data.get("final_state", [])),
            summary_trajectory=summary_traj,
            endpoint_summaries={},
            numerical_check=data.get("numerical_check", {}),
            parameter_samples={k: np.array(v) for k, v in data.get("parameter_samples", {}).items()},
            ensemble_kind=data.get("ensemble_kind", "EPISTEMIC_UNCERTAINTY"),
            members=data.get("config", {}).get("members", 0),
            seed=data.get("config", {}).get("seed", 42),
            epistemic_state=EpistemicState.SIMULATED,
            execution_metadata={
                "runtime_seconds": data.get("runtime_seconds", 0),
                "numpy_version": data.get("numpy_version", "")
            }
        )


def _legacy_states():
    from virtual_lab.models.registry import get_model
    from dataclasses import asdict
    return [asdict(s) for s in get_model('rho_p23h').states]


def _quantiles(raw):
    values = np.asarray(raw)
    if values.ndim != 3:
        return None
    return {'p05': values[:, 0, :], 'median': values[:, 1, :], 'p95': values[:, 2, :]}
