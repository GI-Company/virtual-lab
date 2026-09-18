"""
virtual_lab.core.genesis_tracker
────────────────────────────────
Structures the sequential entry of AI Proposals into the Genesis ledger.
Sequence: AI_PROPOSAL → RULE_EVALUATION → HUMAN_DECISION
"""

from typing import Dict, Any, Optional
import uuid
from datetime import datetime, timezone

from virtual_lab.core.ledger import GenesisLedger, Actor
from virtual_lab.ai.model_fingerprint import get_current_fingerprint
from virtual_lab.ai.epistemic_identity import AIEpistemicIdentity
from virtual_lab.domain.approval_policy import Proposal

class GenesisTracker:
    def __init__(self, ledger: GenesisLedger):
        self.ledger = ledger

    def record_ai_proposal(self, action_type: str, parameters: Dict[str, Any], target: str) -> str:
        """
        Records an AI proposal as INFERRED and NON-AUTHORITATIVE.
        Returns the generated proposal_id.
        """
        proposal_id = f"prop_{uuid.uuid4().hex[:12]}"
        fingerprint = get_current_fingerprint()
        
        payload = {
            "proposal_id": proposal_id,
            "action_type": action_type,
            "parameters": parameters,
            "target": target,
            "epistemic_state": AIEpistemicIdentity.epistemic_state,
            "authoritative": AIEpistemicIdentity.authoritative,
            "model_fingerprint": fingerprint.__dict__,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        actor = Actor(type="AI_MODEL", id=f"{fingerprint.model_family}/{fingerprint.model_variant}")
        self.ledger.append(f"AI_PROPOSAL_{proposal_id}", actor, "AI_PROPOSAL", payload)
        
        return proposal_id

    def record_rule_evaluation(self, proposal_id: str, criteria: str, evidence_refs: list, result: str) -> str:
        """
        Records the deterministic evaluation of a proposal against advancement/quality rules.
        """
        payload = {
            "proposal_id": proposal_id,
            "criteria": criteria,
            "evidence_references": evidence_refs,
            "result": result
        }
        
        actor = Actor(type="SYSTEM", id="rule_engine")
        event_id = f"RULE_EVAL_{proposal_id}_{uuid.uuid4().hex[:8]}"
        self.ledger.append(event_id, actor, "RULE_EVALUATION", payload)
        return event_id

    def record_human_decision(self, proposal_id: str, human_actor_id: str, decision: str, signature: str) -> str:
        """
        Records the human's final approval or rejection.
        """
        payload = {
            "proposal_id": proposal_id,
            "decision": decision,
            "signature": signature
        }
        
        actor = Actor(type="HUMAN", id=human_actor_id)
        event_id = f"DECISION_{proposal_id}_{uuid.uuid4().hex[:8]}"
        self.ledger.append(event_id, actor, "HUMAN_DECISION", payload)
        return event_id
