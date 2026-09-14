from typing import Dict, List, Optional
from virtual_lab.core.experiment import VirtualExperiment

class WorkspaceState:
    """Manages the overall VirtualLab workspace and currently loaded experiments."""
    def __init__(self):
        self.experiments: Dict[str, VirtualExperiment] = {}
        self.active_experiment_id: Optional[str] = None
        
    def add_experiment(self, experiment: VirtualExperiment):
        self.experiments[experiment.id] = experiment
        
    def get_experiment(self, experiment_id: str) -> Optional[VirtualExperiment]:
        return self.experiments.get(experiment_id)

    def set_active(self, experiment_id: str):
        if experiment_id not in self.experiments:
            raise ValueError("Experiment not found in workspace.")
        self.active_experiment_id = experiment_id

    def get_active(self) -> Optional[VirtualExperiment]:
        if self.active_experiment_id:
            return self.experiments.get(self.active_experiment_id)
        return None
