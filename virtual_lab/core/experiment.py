from __future__ import annotations
import uuid
import copy
from enum import Enum
from typing import Any, Dict, List, Optional
from virtual_lab.core.provenance import ProvenanceTracker
from virtual_lab.engines.registry import EngineRegistry

class EnsembleKind(Enum):
    EPISTEMIC_UNCERTAINTY = "epistemic_uncertainty"
    BIOLOGICAL_VARIABILITY = "biological_variability"
    COMBINED = "combined"

class VirtualExperiment:
    def __init__(self, 
                 disease_id: str, 
                 compound_id: str, 
                 evidence_snapshot: str,
                 parent_id: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.disease_id = disease_id
        self.compound_id = compound_id
        self.evidence_snapshot = evidence_snapshot
        self.parent_id = parent_id
        
        self.parameters: Dict[str, Any] = {}
        self.results: Dict[str, Any] = {}
        self.status = "created"
        self.provenance = ProvenanceTracker()
        
        self.provenance.record("experiment_created", {
            "id": self.id,
            "disease_id": self.disease_id,
            "compound_id": self.compound_id,
            "evidence_snapshot": self.evidence_snapshot,
            "parent_id": self.parent_id
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
            parent_id=self.id
        )
        # Deep copy parameters so modifications don't affect parent
        child.parameters = copy.deepcopy(self.parameters)
        child.configure(**kwargs)
        self.provenance.record("branched", {"child_id": child.id, "branch_name": name})
        return child
