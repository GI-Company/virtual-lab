from dataclasses import dataclass
from typing import Optional

from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.gui.services.evidence_store import EvidenceStore
from virtual_lab.ai.agent.tool_registry import ToolRegistry
from virtual_lab.ai.agent.policy import PolicyEngine
from virtual_lab.ai.agent.context import ScientificContextAssembler
from virtual_lab.ai.agent.gemma_backend import GemmaBackend, GemmaRuntimeConfig
from virtual_lab.ai.agent.controller import AgentController

@dataclass
class VirtualLabRuntime:
    ledger: GenesisLedger
    evidence_store: EvidenceStore
    tool_registry: ToolRegistry
    policy_engine: PolicyEngine
    context_assembler: ScientificContextAssembler
    gemma_backend: Optional[GemmaBackend]
    agent_controller: AgentController

def create_virtual_lab_runtime(ledger_path: str = ".virtuallab/genesis.db") -> VirtualLabRuntime:
    import os
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    
    ledger = GenesisLedger(ledger_path)
    evidence_store = EvidenceStore()
    
    registry = ToolRegistry()
    policy = PolicyEngine(registry, ledger)
    assembler = ScientificContextAssembler(registry.get_all_schemas())
    
    backend = None
    try:
        config = GemmaRuntimeConfig(local_only=True)
        backend = GemmaBackend(config)
    except Exception as e:
        import logging
        logging.getLogger("virtuallab.runtime").warning(f"GemmaBackend offline: {e}")
        
    controller = AgentController(registry, policy, assembler, ledger, model_backend=backend)
    
    return VirtualLabRuntime(
        ledger=ledger,
        evidence_store=evidence_store,
        tool_registry=registry,
        policy_engine=policy,
        context_assembler=assembler,
        gemma_backend=backend,
        agent_controller=controller
    )
