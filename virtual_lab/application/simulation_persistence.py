"""One save/registration path for desktop and headless numerical results."""
from pathlib import Path
from virtual_lab.application.run_store import RunStore
from virtual_lab.application.simulation_result import SimulationResult
from virtual_lab.computational.artifacts import digest
from virtual_lab.domain.assemblers import simulation_result_to_observation


def save_simulation(result, experiment, workspace, store, *, run_store=None):
    from virtual_lab.application.research_outputs import simulation_arrays
    if result.get('status') != 'completed' or result.get('epistemic_state') != 'SIMULATED':
        raise ValueError('Only completed SIMULATED numerical results can be saved')
    simulation_arrays(result)
    result = dict(result, experiment_id=experiment.id if experiment else '')
    path = (run_store or RunStore()).save(result)
    result = dict(result, artifact_path=path, artifact_sha256=digest(Path(path)))
    observation = simulation_result_to_observation(result, experiment.id if experiment else '')
    if experiment:
        store.save_observation(observation)
        experiment.attach_observation(observation)
        workspace.observationCommitted.emit(observation)
    else:
        store.stage_observation(observation)
        workspace.observationStaged.emit(observation)
    simulation = SimulationResult.from_dict(result)
    if workspace.active_experiment is experiment:
        workspace.current_result = simulation
    return simulation, observation
