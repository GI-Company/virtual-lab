import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

class StepType(Enum):
    USER_REQUEST = "USER_REQUEST"
    MEMORY_RETRIEVAL = "MEMORY_RETRIEVAL"
    HVIEW_COMPILED = "HVIEW_COMPILED"
    TOOL_REQUEST = "TOOL_REQUEST"
    TOOL_RESULT = "TOOL_RESULT"
    EVIDENCE_RETRIEVED = "EVIDENCE_RETRIEVED"
    HYPOTHESIS_PROPOSED = "HYPOTHESIS_PROPOSED"
    SIMULATION_PROPOSED = "SIMULATION_PROPOSED"
    ACTION_APPROVED = "ACTION_APPROVED"
    ACTION_REJECTED = "ACTION_REJECTED"
    RESULT_OBSERVED = "RESULT_OBSERVED"
    RESPONSE_GENERATED = "RESPONSE_GENERATED"

@dataclass
class ReasoningStep:
    step_id: str
    step_type: StepType
    timestamp: str
    input_refs: List[str]
    output_refs: List[str]
    tool_name: Optional[str] = None
    hview_id: Optional[str] = None
    experiment_id: Optional[str] = None
    provenance_refs: List[str] = field(default_factory=list)

class ReasoningDAG:
    def __init__(self, dag_id: str):
        self.dag_id = dag_id
        self.steps: List[ReasoningStep] = []
        
    def add_step(self, step_type: StepType, input_refs: List[str], output_refs: List[str], 
                 tool_name: Optional[str] = None, hview_id: Optional[str] = None, 
                 experiment_id: Optional[str] = None, provenance_refs: Optional[List[str]] = None) -> ReasoningStep:
        step = ReasoningStep(
            step_id=f"step_{uuid.uuid4().hex[:8]}",
            step_type=step_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            input_refs=input_refs,
            output_refs=output_refs,
            tool_name=tool_name,
            hview_id=hview_id,
            experiment_id=experiment_id,
            provenance_refs=provenance_refs or []
        )
        self.steps.append(step)
        return step

    def serialize(self) -> Dict[str, Any]:
        return {
            "dag_id": self.dag_id,
            "steps": [
                {
                    "step_id": s.step_id,
                    "step_type": s.step_type.value,
                    "timestamp": s.timestamp,
                    "input_refs": s.input_refs,
                    "output_refs": s.output_refs,
                    "tool_name": s.tool_name,
                    "hview_id": s.hview_id,
                    "experiment_id": s.experiment_id,
                    "provenance_refs": s.provenance_refs
                } for s in self.steps
            ]
        }
