from __future__ import annotations
import uuid
import copy
from enum import Enum
from typing import Any, Dict, List, Optional
from virtual_lab.core.provenance import ProvenanceTracker
from virtual_lab.engines.registry import EngineRegistry
from virtual_lab.domain.observation import ExperimentObservation

class EnsembleKind(Enum):
    EPISTEMIC_UNCERTAINTY = "epistemic_uncertainty"
    BIOLOGICAL_VARIABILITY = "biological_variability"
    COMBINED = "combined"

class VirtualExperiment:
    def __init__(self, 
                 disease_id: str, 
                 compound_id: str, 
                 evidence_snapshot: str,
                 parent_id: Optional[str] = None,
                 label: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.disease_id = disease_id
        self.compound_id = compound_id
        self.evidence_snapshot = evidence_snapshot
        self.parent_id = parent_id
        self.label = label
        
        self.parameters: Dict[str, Any] = {}
        self.results: Dict[str, Any] = {}
        self.status = "active"
        self.provenance = ProvenanceTracker()
        
        self.observations: List[ExperimentObservation] = []
        
        self.provenance.record("experiment_created", {
            "id": self.id,
            "disease_id": self.disease_id,
            "compound_id": self.compound_id,
            "evidence_snapshot": self.evidence_snapshot,
            "parent_id": self.parent_id,
            "label": self.label
        })

    def attach_observation(self, observation: ExperimentObservation):
        """Attach an observation to this experiment."""
        if observation.experiment_id != self.id:
            raise ValueError(f"Observation {observation.observation_id} belongs to experiment {observation.experiment_id}, not {self.id}")
        self.observations.append(observation)
        self.provenance.record("observation_attached", {
            "observation_id": observation.observation_id,
            "kind": observation.kind.value,
            "session_id": observation.session_id
        })

    def configure(self, **kwargs):
        """Set parameters for the experiment."""
        self.parameters.update(kwargs)
        self.provenance.record("parameters_configured", kwargs)
        
    def run(self, stages: List[str]) -> Dict[str, Any]:
        """Execute a series of engines on the experiment state."""
        self.status = "running"
        self.provenance.record("run_started", {"stages": stages})
        
        for stage in stages:
            engine = EngineRegistry.get(stage)
            if not engine.validate(self):
                raise ValueError(f"Engine {stage} failed validation for experiment {self.id}")
                
            self.provenance.record("stage_started", {"stage": stage, "engine_version": engine.version})
            
            # Execute the engine
            stage_result = engine.run(self)
            self.results[stage] = stage_result
            
            self.provenance.record("stage_completed", {"stage": stage})

        self.status = "completed"
        self.provenance.record("run_completed", {"final_hash": self.provenance.generate_hash()})
        return self.results

    def branch(self, name: str, **kwargs) -> VirtualExperiment:
        """Create a new experiment branched from this one, optionally overriding parameters."""
        child = VirtualExperiment(
            disease_id=self.disease_id,
            compound_id=self.compound_id,
            evidence_snapshot=self.evidence_snapshot,
            parent_id=self.id,
            label=name
        )
        # Deep copy parameters so modifications don't affect parent
        child.parameters = copy.deepcopy(self.parameters)
        child.configure(**kwargs)
        self.provenance.record("branched", {"child_id": child.id, "branch_name": name})
        return child
