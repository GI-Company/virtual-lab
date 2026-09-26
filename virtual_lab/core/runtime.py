from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.gui.services.evidence_store import EvidenceStore
from virtual_lab.ai.agent.tool_registry import ToolRegistry
from virtual_lab.ai.agent.policy import PolicyEngine
from virtual_lab.ai.agent.context import ScientificContextAssembler
if TYPE_CHECKING:
    from virtual_lab.ai.agent.gemma_backend import GemmaBackend
from virtual_lab.ai.agent.controller import AgentController
from virtual_lab.instruments.transport.gateway import InstrumentGateway
from virtual_lab.ai.runtime_service import AgentRuntimeService

@dataclass
class VirtualLabRuntime:
    ledger: GenesisLedger
    evidence_store: EvidenceStore
    tool_registry: ToolRegistry
    policy_engine: PolicyEngine
    context_assembler: ScientificContextAssembler
    gemma_backend: Optional[GemmaBackend]
    agent_controller: AgentController
    gateway: InstrumentGateway
    agent_runtime: AgentRuntimeService

def create_virtual_lab_runtime(ledger_path: str = ".virtuallab/genesis.db") -> VirtualLabRuntime:
    import os
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    
    ledger = GenesisLedger(ledger_path)
    evidence_store = EvidenceStore()
    
    registry = ToolRegistry()
    policy = PolicyEngine(registry, ledger)
    assembler = ScientificContextAssembler(registry.get_all_schemas())
    
    backend = None
    # We now use Vertex ADK Multi-Agent runner dynamically in LocalResearchWorkspace
    from virtual_lab.ai.agent.genesis_adapter import AgentGenesisRecorder
    agent_genesis = AgentGenesisRecorder(ledger)
        
    controller = AgentController(registry, policy, assembler, agent_genesis, model_backend=backend)
    
    gateway = InstrumentGateway(ledger=ledger, port=8765)
    gateway.start()

    agent_runtime = AgentRuntimeService()

    return VirtualLabRuntime(
        ledger=ledger,
        evidence_store=evidence_store,
        tool_registry=registry,
        policy_engine=policy,
        context_assembler=assembler,
        gemma_backend=backend,
        agent_controller=controller,
        gateway=gateway,
        agent_runtime=agent_runtime
    )
