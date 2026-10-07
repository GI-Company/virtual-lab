# Extensible simulations

Simulation now lists registered models. RHO P23H remains available, alongside a generic transcription/translation model with mRNA and protein states. Analysis reads saved state names, units, and semantic descriptors rather than assuming five RHO states. RHO cell/tissue views explicitly clear for unrelated models.

Gene expression uses:

```
m' = transcription * (1 + induction * c / (ec50 + c)) - mrna_decay * m
p' = translation * m - protein_decay * p
m(0) = p(0) = 0
```

It is a generic, uncalibrated reference model, not a model of a named gene or organism. Constant exposure, arbitrary normalized abundances, first-order loss, and independent lognormal parameter uncertainty are assumptions. No feedback, cell division, resource limits, or stochastic transcription are included. Its rates have not been fitted to experimental data. AlphaGenome and AlphaFold outputs are not automatically converted into kinetic parameters.

## Model contract

A model supplies `initial_state()` (1-D NumPy array), `state_schema()` (ordered keys), and `rhs(t, y, params, exposure, xp=np)`. The right-hand side must support both a single state vector and state-by-ensemble arrays. Use `xp` operations when declaring MLX support. The shared runner handles paired control, seeded ensembles, integration, cancellation, checkpoints, and numerical comparison.

`ModelSpec` declares identity/version, a zero-argument model factory, bounded parameter controls, ordered `StateSpec` descriptors, supported backends, limitations, and readable source paths for provenance. Optional `prepare_parameters(model, controls)` converts UI controls into the numeric parameter mapping sampled by the runner. Every numeric parameter currently receives the same independent lognormal spread. Models requiring other distributions or time-dependent interventions need a runner extension.

An installed Python package can register an entry point:

```toml
[project.entry-points."virtual_lab.models"]
my_model = "my_package.model:get_spec"
```

The target returns a `ModelSpec` or directly exports one. For example:

```python
from pathlib import Path
import numpy as np
from virtual_lab.models.registry import ModelSpec, ParameterSpec, StateSpec

class Decay:
    def initial_state(self): return np.ones(1)
    def state_schema(self): return ['quantity']
    def rhs(self, t, y, params, exposure, xp=np):
        return -params['decay'] * y

def get_spec():
    return ModelSpec(
        id='example_decay', label='Example decay', version='1.0',
        description='A one-state extension example.', factory=Decay,
        parameters=(ParameterSpec('decay', 'Decay', .2, .01, 1, '1/h'),),
        states=(StateSpec('quantity', 'Quantity', semantic_name='example_quantity'),),
        source_files=(Path(__file__),),
        limitations=('Illustrative model; no biological calibration.',),
        backends=('numpy',),
    )
```

Extensions execute installed Python code in the application process; this is not a sandbox or an upload-and-run interface. Duplicate IDs and invalid descriptors fail registration. A failing installed extension rolls back discovery so it cannot silently leave a partial catalog. Uninstall or repair the extension before retrying.

## Saved results and verification

Schema 2 records model ID/version, controls, parameter samples, state semantics, source hashes, paired trajectories, final states, and experiment ownership. Outputs are `SIMULATED`; inputs remain `MODEL_ASSUMPTION`. Legacy RHO results still load. Study export/import carries the original result bytes and hash verification.

The numerical check compares the final state of the first up to eight ensemble members, under exposure and zero-exposure control, against SciPy DOP853. Bounds are checked at 97 checkpoints for all members. This does not establish biological validity or numerical accuracy between every checkpoint. Spearman rank correlation is displayed by its actual name; it is not partial rank correlation or causal evidence.

Tests cover the gene model against a closed-form solution (including equal decay rates), seeded pairing, validation, cancellation, RHO compatibility, an independent third model, entry-point discovery rollback, state semantics, and model-aware GUI analysis. Live GUI verification used NumPy; MLX was unavailable on the test machine.

See [measurement calibration](calibration.md) for the separate published-data fitting and held-out evaluation workflow.
