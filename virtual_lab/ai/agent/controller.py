import uuid
import json
import hashlib
from typing import Dict, Any, List, Optional, Callable

from virtual_lab.ai.agent.genesis_adapter import AgentGenesisRecorder
from virtual_lab.ai.agent.tool_registry import ToolRegistry
from virtual_lab.ai.agent.policy import PolicyEngine
from virtual_lab.ai.agent.context import ScientificContextAssembler
from virtual_lab.ai.agent.reasoning_dag import ReasoningDAG, StepType
from virtual_lab.ai.agent.episode import AgentEpisode

class AgentTerminationReason:
    ANSWER_COMPLETE = "ANSWER_COMPLETE"
    USER_APPROVAL_REQUIRED = "USER_APPROVAL_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    TOOL_FAILURE = "TOOL_FAILURE"
    CONTEXT_LIMIT = "CONTEXT_LIMIT"
    STEP_LIMIT = "STEP_LIMIT"
    CANCELLED = "CANCELLED"

class AgentController:
    def __init__(self, 
                 registry: ToolRegistry, 
                 policy: PolicyEngine, 
                 context_assembler: ScientificContextAssembler,
                 genesis: AgentGenesisRecorder,
                 model_backend: Callable = None):
        self.registry = registry
        self.policy = policy
        self.context_assembler = context_assembler
        self.genesis = genesis
        # The model_backend function mocks or wraps the actual Gemma call
        self.model_backend = model_backend
        
        self.max_agent_steps = 10
        self.max_tool_calls = 5
        self.max_hviews = 3
        
    def run_episode(self, user_request: str, experiment_id: str, hview_summary: str, 
                    authoritative_records: List[Dict[str, Any]], memory_revision: int,
                    hview_projection_dict: Dict[str, Any] = None, stream_callback=None) -> AgentEpisode:
        
        episode_id = f"ep_{uuid.uuid4().hex[:8]}"
        self.genesis.record_episode_started(episode_id, user_request, experiment_id)
        
        dag = ReasoningDAG(f"dag_{episode_id}")
        episode = AgentEpisode(
            episode_id=episode_id,
            experiment_id=experiment_id,
            user_request=user_request,
            reasoning_dag=dag,
            memory_revisions=[memory_revision]
        )
        
        dag.add_step(StepType.USER_REQUEST, [], [], experiment_id=experiment_id)
        
        return self._run_episode_loop(episode, hview_summary, authoritative_records, hview_projection_dict, stream_callback)

    def resume_episode(self, episode: AgentEpisode, tool_name: str, tool_args: dict, result: dict, 
                       hview_summary: str, authoritative_records: List[Dict[str, Any]], hview_projection_dict: Dict[str, Any] = None, stream_callback=None) -> AgentEpisode:
        req_step_id = episode.reasoning_dag.steps[-1].step_id
        res_hash = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        self.genesis.record_tool_completed(episode.episode_id, req_step_id, res_hash)
        
        episode.tool_results.append({"tool": tool_name, "result": result})
        episode.reasoning_dag.add_step(StepType.TOOL_RESULT, [req_step_id], [], tool_name=tool_name, experiment_id=episode.experiment_id)
        episode.step_count += 1
        
        return self._run_episode_loop(episode, hview_summary, authoritative_records, hview_projection_dict, stream_callback)

    def _run_episode_loop(self, episode: AgentEpisode, hview_summary: str, authoritative_records: List[Dict[str, Any]], hview_projection_dict: Dict[str, Any] = None, stream_callback=None) -> AgentEpisode:
        # Assemble context
        context_data = self.context_assembler.assemble(
            episode.user_request, episode.experiment_id, hview_summary, authoritative_records, hview_projection_dict
        )
        context_data["tool_results"] = episode.tool_results
        
        tool_count = len(episode.tool_results)
        hview_count = 1  # assuming one is passed in
        
        termination_reason = AgentTerminationReason.ANSWER_COMPLETE
        
        while episode.step_count < self.max_agent_steps:
            if not self.model_backend:
                raise ValueError("Model backend is structurally required in Operational PoC v0.1")
                
            # Invoke Model
            try:
                model_output = self.model_backend(context_data, episode.reasoning_dag.serialize(), stream_callback=stream_callback)
                print(f"Agent Action: {json.dumps(model_output, indent=2)}")
            except Exception as e:
                if "context overflow" in str(e).lower():
                    termination_reason = AgentTerminationReason.CONTEXT_LIMIT
                    break
                elif "MODEL_OUTPUT_INVALID" in str(e):
                    print(f"DEBUG EXCEPTION: {str(e)}")
                    termination_reason = AgentTerminationReason.TOOL_FAILURE
                    self.genesis.record_episode_completed(episode.episode_id, termination_reason, "INVALID_MODEL_OUTPUT")
                    return episode
                else:
                    raise
            
            if model_output.get("type") == "answer":
                episode.reasoning_dag.add_step(StepType.RESPONSE_GENERATED, [], [], experiment_id=episode.experiment_id)
                termination_reason = AgentTerminationReason.ANSWER_COMPLETE
                episode.final_response_hash = hashlib.sha256(model_output.get("text", "").encode()).hexdigest()
                break
                
            elif model_output.get("type") == "tool_call":
                if tool_count >= self.max_tool_calls:
                    termination_reason = AgentTerminationReason.STEP_LIMIT
                    break
                    
                tool_name = model_output.get("tool_name")
                tool_args = model_output.get("args", {})
                
                # Capability Enforcement: L1 Authority is Deny-by-default for mutations
                # All PROPOSE and ACTION tools are structurally absent/denied from L1
                tool_schema = self.registry.get_tool(tool_name)
                from virtual_lab.ai.agent.types import ToolActionType
                if tool_schema.action_type in [ToolActionType.PROPOSE, ToolActionType.ACTION]:
                    termination_reason = AgentTerminationReason.TOOL_FAILURE
                    self.genesis.record_tool_failed(episode.episode_id, f"req_{uuid.uuid4().hex[:8]}", f"L1_CAPABILITY_DENIED: {tool_schema.action_type.name} is structurally absent from L1")
                    break
                
                # Enforce HVIEW limits
                if tool_name == "envision_memory":
                    hview_count += 1
                    if hview_count > self.max_hviews:
                        termination_reason = AgentTerminationReason.STEP_LIMIT
                        break
                        
                current_call = (tool_name, json.dumps(tool_args, sort_keys=True))
                if getattr(episode, 'last_tool_call', None) == current_call:
                    episode.tool_results.append({"tool": tool_name, "error": "DUPLICATE_CALL: You just called this tool with identical arguments. Please use different arguments or provide justification."})
                    tool_count += 1
                    episode.step_count += 1
                    continue
                episode.last_tool_call = current_call
                
                # Pre-execution DAG logging
                req_step = episode.reasoning_dag.add_step(StepType.TOOL_REQUEST, [], [], tool_name=tool_name, experiment_id=episode.experiment_id)
                args_hash = hashlib.sha256(json.dumps(tool_args, sort_keys=True).encode()).hexdigest()
                self.genesis.record_tool_requested(episode.episode_id, req_step.step_id, tool_name, args_hash)
                
                # Execute via Policy
                try:
                    result = self.policy.execute_tool(episode.episode_id, tool_name, tool_args)
                    
                    if isinstance(result, dict) and result.get("status") == "PENDING":
                        # Proposal created
                        termination_reason = AgentTerminationReason.USER_APPROVAL_REQUIRED
                        
                        # In the real system, we'd fetch the actual proposal from the ledger.
                        # For now, we construct the immutable proposal reference based on the tool result.
                        proposal_id = result["proposal_id"]
                        
                        from virtual_lab.ai.agent.types import Proposal
                        from datetime import datetime, timezone
                        
                        p = Proposal(proposal_id, tool_name, tool_args, tool_args.get("evidence_refs", []), tool_args.get("hview_id"), "gemma4_unified", datetime.now(timezone.utc).isoformat())
                        episode.proposals.append(p)
                        
                        episode.reasoning_dag.add_step(
                            StepType.SIMULATION_PROPOSED if "simulation" in tool_name else StepType.HYPOTHESIS_PROPOSED,
                            [req_step.step_id], [], tool_name=tool_name, experiment_id=episode.experiment_id
                        )
                        break
                        
                    res_hash = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
                    self.genesis.record_tool_completed(episode.episode_id, req_step.step_id, res_hash)
                    
                    # Update context with result
                    episode.tool_results.append({"tool": tool_name, "result": result})
                    episode.reasoning_dag.add_step(StepType.TOOL_RESULT, [req_step.step_id], [], tool_name=tool_name, experiment_id=episode.experiment_id)
                    tool_count += 1
                    
                except ValueError as ve:
                    if "ACTION INTERCEPTED" in str(ve):
                        termination_reason = AgentTerminationReason.USER_APPROVAL_REQUIRED
                        if not hasattr(episode, "pending_actions"):
                            episode.pending_actions = {}
                        episode.pending_actions[tool_args.get("proposal_id", "unknown")] = tool_name
                        break
                    else:
                        self.genesis.record_tool_failed(episode.episode_id, req_step.step_id, str(ve))
                        termination_reason = AgentTerminationReason.TOOL_FAILURE
                        break
                except Exception as e:
                    self.genesis.record_tool_failed(episode.episode_id, req_step.step_id, str(e))
                    termination_reason = AgentTerminationReason.TOOL_FAILURE
                    break
            
            episode.step_count += 1
            
        if episode.step_count >= self.max_agent_steps:
            termination_reason = AgentTerminationReason.STEP_LIMIT
            
        self.genesis.record_episode_completed(episode.episode_id, termination_reason, getattr(episode, 'final_response_hash', ""))
        return episode
