from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone

from virtual_lab.core.ledger import GenesisLedger, Actor

class AgentGenesisRecorder:
    def __init__(self, ledger: Optional[GenesisLedger] = None):
        """
        Adapter for appending cognitive agent events to the VirtualLab Genesis Ledger.
        If ledger is None, a GenesisLedger is instantiated in memory for testing.
        """
        self.ledger = ledger if ledger is not None else GenesisLedger(":memory:")
        self.actor = Actor(type="AI_AGENT", id="gemma4_unified")
        
    def _append(self, event_type: str, event_id: str, payload: Dict[str, Any]) -> str:
        return self.ledger.append(
            event_id=event_id,
            actor=self.actor,
            event_type=event_type,
            payload=payload
        )

    def record_episode_started(self, episode_id: str, user_request: str, experiment_id: Optional[str]) -> str:
        return self._append("AGENT_EPISODE_STARTED", f"evt_{episode_id}_start", {
            "episode_id": episode_id,
            "user_request": user_request,
            "experiment_id": experiment_id
        })

    def record_hview_created(self, episode_id: str, hview_id: str, memory_revision: int) -> str:
        return self._append("HVIEW_CREATED", f"evt_hview_{hview_id}", {
            "episode_id": episode_id,
            "hview_id": hview_id,
            "memory_revision": memory_revision
        })

    def record_memory_retrieved(self, episode_id: str, retrieval_refs: list[str]) -> str:
        return self._append("MEMORY_RETRIEVED", f"evt_mem_{episode_id}_{len(retrieval_refs)}", {
            "episode_id": episode_id,
            "retrieval_refs": retrieval_refs
        })

    def record_evidence_retrieved(self, episode_id: str, evidence_refs: list[str]) -> str:
        return self._append("EVIDENCE_RETRIEVED", f"evt_evid_{episode_id}", {
            "episode_id": episode_id,
            "evidence_refs": evidence_refs
        })

    def record_tool_requested(self, episode_id: str, step_id: str, tool_name: str, args_hash: str) -> str:
        return self._append("TOOL_REQUESTED", f"evt_tool_req_{step_id}", {
            "episode_id": episode_id,
            "step_id": step_id,
            "tool_name": tool_name,
            "args_hash": args_hash
        })

    def record_tool_completed(self, episode_id: str, step_id: str, result_hash: str) -> str:
        return self._append("TOOL_COMPLETED", f"evt_tool_comp_{step_id}", {
            "episode_id": episode_id,
            "step_id": step_id,
            "result_hash": result_hash
        })

    def record_tool_failed(self, episode_id: str, step_id: str, error_msg: str) -> str:
        return self._append("TOOL_FAILED", f"evt_tool_fail_{step_id}", {
            "episode_id": episode_id,
            "step_id": step_id,
            "error_msg": error_msg
        })

    def record_proposal_created(self, episode_id: str, proposal_id: str, proposal_hash: str) -> str:
        return self._append("PROPOSAL_CREATED", f"evt_prop_{proposal_id}", {
            "episode_id": episode_id,
            "proposal_id": proposal_id,
            "proposal_hash": proposal_hash
        })

    def record_human_decision(self, proposal_id: str, decision: str, human_actor: str) -> str:
        return self._append(f"HUMAN_{decision}", f"evt_dec_{proposal_id}", {
            "proposal_id": proposal_id,
            "decision": decision,
            "human_actor": human_actor
        })

    def record_action_executed(self, episode_id: str, action_id: str, target_ref: str) -> str:
        return self._append("ACTION_EXECUTED", f"evt_act_exec_{action_id}", {
            "episode_id": episode_id,
            "action_id": action_id,
            "target_ref": target_ref
        })

    def record_action_failed(self, episode_id: str, action_id: str, error_msg: str) -> str:
        return self._append("ACTION_FAILED", f"evt_act_fail_{action_id}", {
            "episode_id": episode_id,
            "action_id": action_id,
            "error_msg": error_msg
        })

    def record_episode_completed(self, episode_id: str, termination_reason: str, result_hash: str) -> str:
        return self._append("AGENT_EPISODE_COMPLETED", f"evt_{episode_id}_end", {
            "episode_id": episode_id,
            "termination_reason": termination_reason,
            "result_hash": result_hash
        })
