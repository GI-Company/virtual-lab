import json
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from virtual_lab.ai.agent.reasoning_dag import ReasoningDAG
from virtual_lab.ai.agent.types import Proposal, ProposalDecision

@dataclass
class AgentEpisode:
    episode_id: str
    experiment_id: str
    user_request: str
    reasoning_dag: ReasoningDAG
    hview_ids: List[str] = field(default_factory=list)
    memory_revisions: List[int] = field(default_factory=list)
    retrieved_evidence: List[str] = field(default_factory=list)
    proposals: List[Proposal] = field(default_factory=list)
    human_decisions: List[ProposalDecision] = field(default_factory=list)
    final_response_hash: Optional[str] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    step_count: int = 0
    pending_actions: Dict[str, str] = field(default_factory=dict)
    
    def serialize(self) -> Dict[str, Any]:
        data = {
            "episode_id": self.episode_id,
            "experiment_id": self.experiment_id,
            "user_request": self.user_request,
            "reasoning_dag_id": self.reasoning_dag.dag_id,
            "hview_ids": self.hview_ids,
            "memory_revisions": self.memory_revisions,
            "retrieved_evidence": self.retrieved_evidence,
            "proposals": [p.proposal_id for p in self.proposals],
            "human_decisions": [{"proposal": d.proposal_id, "decision": d.decision.value} for d in self.human_decisions],
            "final_response_hash": self.final_response_hash
        }
        return data

    def compute_hash(self) -> str:
        canonical_str = json.dumps(self.serialize(), separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()
