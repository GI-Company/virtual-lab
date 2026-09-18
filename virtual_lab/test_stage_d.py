import unittest
import os
import sys

# Ensure we can import virtual_lab
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from virtual_lab.ai.agent.tool_registry import ToolRegistry, ToolSchema
from virtual_lab.ai.agent.genesis_adapter import AgentGenesisRecorder
from virtual_lab.ai.agent.policy import PolicyEngine, LocalResearchPolicyException
from virtual_lab.ai.agent.context import ScientificContextAssembler
from virtual_lab.ai.agent.controller import AgentController, AgentTerminationReason
from virtual_lab.ai.agent.types import ProposalDecisionStatus
from virtual_lab.domain.epistemics import EpistemicState
from virtual_lab.core.ledger import GenesisLedger, ChainIntegrityError

class MockGemmaBackend:
    def __init__(self, script):
        self.script = script
        self.step = 0
        
    def __call__(self, context, dag):
        if self.step < len(self.script):
            res = self.script[self.step]
            self.step += 1
            return res
        return {"type": "answer", "text": "I have run out of scripted actions."}

class TestStageD(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        # Add a dummy network tool for local-mode testing
        from virtual_lab.ai.agent.types import ToolActionType
        self.registry.register_tool(ToolSchema("network_literature_retrieval", "Network tool", ToolActionType.READ, {}))
        
        self.ledger = GenesisLedger(":memory:")
        self.genesis = AgentGenesisRecorder(self.ledger)
        self.policy = PolicyEngine(self.registry, self.genesis, local_research_mode=True)
        self.context_assembler = ScientificContextAssembler(self.registry.get_all_schemas())

        # Register mock executors
        self.policy.register_executor("get_simulation_runs", lambda **kwargs: [{"run_id": "sim_1", "state": EpistemicState.SIMULATED.value, "viability": "improved"}])
        self.policy.register_executor("show_memory_evidence", lambda **kwargs: [{"node": "yc-001", "state": EpistemicState.MEASURED.value}])
        self.policy.register_executor("run_simulation", lambda **kwargs: {"result": "Success"})

    def test_01_scenario_1_end_to_end_read(self):
        # Scenario 1: Why did the latest YC-001 experiment predict improved viability?
        script = [
            {"type": "tool_call", "tool_name": "get_simulation_runs", "args": {"experiment_id": "YC-001"}},
            {"type": "tool_call", "tool_name": "show_memory_evidence", "args": {"node_ids": ["yc-001-sim-node"]}},
            {"type": "answer", "text": "Based on EVIDENCE_BACKED data, the SIMULATED parameter settings predict viability improvement."}
        ]
        backend = MockGemmaBackend(script)
        controller = AgentController(self.registry, self.policy, self.context_assembler, self.genesis, model_backend=backend)
        
        episode = controller.run_episode("Why did the latest YC-001 experiment predict improved viability?", "YC-001", "HVIEW_summary_1", [], 1)
        
        # Verify Episode termination
        head = self.ledger.get_head()
        self.assertEqual(head.event_type, "AGENT_EPISODE_COMPLETED")
        self.assertEqual(head.payload["termination_reason"], AgentTerminationReason.ANSWER_COMPLETE)
        
        # Verify Context Epistemic output
        # Tool outputs got recorded to genesis, let's verify dag
        self.assertEqual(len(episode.reasoning_dag.steps), 6) # REQUEST, TOOL1 REQ, TOOL1 RES, TOOL2 REQ, TOOL2 RES, ANSWER
        self.assertEqual(episode.reasoning_dag.steps[-1].step_type.value, "RESPONSE_GENERATED")
        
    def test_02_scenario_2_propose(self):
        # Scenario 2: Propose experiment
        script = [
            {"type": "tool_call", "tool_name": "propose_experiment_branch", "args": {"branch_name": "YC-002", "parameters": {}}}
        ]
        backend = MockGemmaBackend(script)
        controller = AgentController(self.registry, self.policy, self.context_assembler, self.genesis, model_backend=backend)
        
        episode = controller.run_episode("What experiment should we run next?", "YC-001", "HVIEW_summary_1", [], 1)
        
        # Verify Proposal Created
        head = self.ledger.get_head()
        self.assertEqual(head.event_type, "AGENT_EPISODE_COMPLETED")
        self.assertEqual(head.payload["termination_reason"], AgentTerminationReason.USER_APPROVAL_REQUIRED)
        self.assertEqual(len(episode.proposals), 1)
        
    def test_03_scenario_3_action_gate(self):
        # Scenario 3: Gemma tries to run_simulation
        script = [
            {"type": "tool_call", "tool_name": "run_simulation", "args": {"proposal_id": "prop_fake123"}}
        ]
        backend = MockGemmaBackend(script)
        controller = AgentController(self.registry, self.policy, self.context_assembler, self.genesis, model_backend=backend)
        
        episode = controller.run_episode("Run the simulation for me.", "YC-001", "HVIEW_summary_1", [], 1)
        
        # Verify Action Intercepted
        head = self.ledger.get_head()
        self.assertEqual(head.event_type, "AGENT_EPISODE_COMPLETED")
        self.assertEqual(head.payload["termination_reason"], AgentTerminationReason.USER_APPROVAL_REQUIRED)
        
        # Manually Approve and Execute
        decision = self.policy.human_approve_proposal(episode.episode_id, "prop_fake123", "hanna")
        self.assertEqual(decision.decision, ProposalDecisionStatus.APPROVED)
        
        result = self.policy.execute_approved_action(episode.episode_id, "prop_fake123", "run_simulation", {"proposal_id": "prop_fake123"})
        self.assertEqual(result["result"], "Success")
        
        # Verify Genesis chain
        self.ledger.verify_chain() # Should not raise

    def test_04_failure_local_mode(self):
        script = [
            {"type": "tool_call", "tool_name": "network_literature_retrieval", "args": {}}
        ]
        backend = MockGemmaBackend(script)
        controller = AgentController(self.registry, self.policy, self.context_assembler, self.genesis, model_backend=backend)
        
        episode = controller.run_episode("Search literature.", "YC-001", "HVIEW_summary_1", [], 1)
        
        head = self.ledger.get_head()
        self.assertEqual(head.payload["termination_reason"], AgentTerminationReason.TOOL_FAILURE)

    def test_05_failure_loop_guard(self):
        # An infinite loop of envision
        script = [{"type": "tool_call", "tool_name": "envision_memory", "args": {}} for _ in range(20)]
        backend = MockGemmaBackend(script)
        controller = AgentController(self.registry, self.policy, self.context_assembler, self.genesis, model_backend=backend)
        
        episode = controller.run_episode("Envision forever.", "YC-001", "HVIEW_summary_1", [], 1)
        
        head = self.ledger.get_head()
        self.assertEqual(head.payload["termination_reason"], AgentTerminationReason.STEP_LIMIT)

if __name__ == "__main__":
    unittest.main()
