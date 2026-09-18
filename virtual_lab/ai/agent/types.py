import hashlib
import json
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from virtual_lab.domain.epistemics import EpistemicState

class ToolActionType(Enum):
    READ = "READ"
    PROPOSE = "PROPOSE"
    ACTION = "ACTION"

class ProposalDecisionStatus(Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class ProposalExecutionStatus(Enum):
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"

@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    proposal_type: str
    parameters: Dict[str, Any]
    evidence_refs: List[str]
    hview_id: Optional[str]
    created_by_model: str
    created_at: str
    content_hash: str = field(init=False)
    
    def __post_init__(self):
        # Compute hash over deterministic JSON dump
        data = {
            "proposal_id": self.proposal_id,
            "proposal_type": self.proposal_type,
            "parameters": self.parameters,
            "evidence_refs": self.evidence_refs,
            "hview_id": self.hview_id,
            "created_by_model": self.created_by_model,
            "created_at": self.created_at
        }
        canonical_str = json.dumps(data, separators=(",", ":"), sort_keys=True)
        h = hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()
        object.__setattr__(self, 'content_hash', h)

@dataclass(frozen=True)
class ProposalDecision:
    proposal_id: str
    decision: ProposalDecisionStatus
    human_actor: str
    timestamp: str

@dataclass(frozen=True)
class ProposalExecution:
    proposal_id: str
    status: ProposalExecutionStatus
    result_refs: List[str]
    timestamp: str

