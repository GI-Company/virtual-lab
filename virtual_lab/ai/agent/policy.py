import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Callable

from virtual_lab.ai.agent.types import (
    ToolActionType, Proposal, ProposalDecision, ProposalDecisionStatus,
    ProposalExecution, ProposalExecutionStatus
)
from virtual_lab.ai.agent.genesis_adapter import AgentGenesisRecorder
from virtual_lab.ai.agent.tool_registry import ToolRegistry

class LocalResearchPolicyException(Exception):
    pass

class PolicyEngine:
    def __init__(self, registry: ToolRegistry, genesis: AgentGenesisRecorder, local_research_mode: bool = True):
        self.registry = registry
        self.genesis = genesis
        self.local_research_mode = local_research_mode
        self._executors: Dict[str, Callable] = {}
        
    def register_executor(self, tool_name: str, executor: Callable):
        self._executors[tool_name] = executor

    def execute_tool(self, episode_id: str, tool_name: str, args: Dict[str, Any]) -> Any:
        schema = self.registry.get_tool(tool_name)
        
        # Local Research Mode Enforcement
        if self.local_research_mode and tool_name == "network_literature_retrieval":
            raise LocalResearchPolicyException("Network literature retrieval is DENIED in Local Research Mode.")
            
        if schema.action_type == ToolActionType.READ:
            # Execute automatically
            if tool_name not in self._executors:
                raise NotImplementedError(f"No executor registered for READ tool {tool_name}")
            return self._executors[tool_name](**args)
            
        elif schema.action_type == ToolActionType.PROPOSE:
            # Create immutable proposal, do not execute actual scientific state changes
            proposal_id = f"prop_{uuid.uuid4().hex[:8]}"
            proposal = Proposal(
                proposal_id=proposal_id,
                proposal_type=tool_name,
                parameters=args,
                evidence_refs=args.get("evidence_refs", []),
                hview_id=args.get("hview_id"),
                created_by_model="gemma4_unified",
                created_at=datetime.now(timezone.utc).isoformat()
            )
            # Record in Genesis
            self.genesis.record_proposal_created(episode_id, proposal.proposal_id, proposal.content_hash)
            return {"status": "PENDING", "proposal_id": proposal.proposal_id, "hash": proposal.content_hash}
            
        elif schema.action_type == ToolActionType.ACTION:
            # Actions MUST take a proposal_id and require explicit approval
            proposal_id = args.get("proposal_id")
            if not proposal_id:
                raise ValueError(f"ACTION tool {tool_name} requires a proposal_id.")
                
            # In a real system, we would query the Ledger to check if ProposalDecision exists and is APPROVED
            # For this interceptor, if we haven't seen an approval in memory (or passed in), we reject.
            # We simulate action interception:
            # We return an interception message. The actual execution happens only when human approves.
            raise ValueError(f"ACTION INTERCEPTED: Execution of {tool_name} requires explicit human approval for proposal {proposal_id}.")
            
        raise ValueError(f"Unknown action type {schema.action_type}")

    def human_approve_proposal(self, episode_id: str, proposal_id: str, human_actor: str):
        decision = ProposalDecision(
            proposal_id=proposal_id,
            decision=ProposalDecisionStatus.APPROVED,
            human_actor=human_actor,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        self.genesis.record_human_decision(proposal_id, "APPROVED", human_actor)
        return decision

    def human_reject_proposal(self, episode_id: str, proposal_id: str, human_actor: str):
        decision = ProposalDecision(
            proposal_id=proposal_id,
            decision=ProposalDecisionStatus.REJECTED,
            human_actor=human_actor,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        self.genesis.record_human_decision(proposal_id, "REJECTED", human_actor)
        return decision

    def execute_approved_action(self, episode_id: str, proposal_id: str, tool_name: str, args: Dict[str, Any]):
        # This bypasses the typical interception because it's invoked by the human gateway
        try:
            if tool_name in self._executors:
                result = self._executors[tool_name](**args)
            else:
                raise NotImplementedError(f"No executor registered for ACTION tool {tool_name}")
            
            self.genesis.record_action_executed(episode_id, proposal_id, target_ref=tool_name)
            return result
        except Exception as e:
            self.genesis.record_action_failed(episode_id, proposal_id, str(e))
            raise
