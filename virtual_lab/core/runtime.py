"""Research runtime. AI is loaded only after an explicit user request."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.core.paths import app_data_dir
from virtual_lab.gui.services.evidence_store import EvidenceStore
from virtual_lab.instruments.transport.gateway import InstrumentGateway


@dataclass
class VirtualLabRuntime:
    ledger: GenesisLedger
    evidence_store: EvidenceStore
    gateway: InstrumentGateway
    agent_runtime: Any = None
    agent_controller: Any = None
    tool_registry: Any = None
    policy_engine: Any = None
    context_assembler: Any = None
    gemma_backend: Any = None
    settings: Any = None
    _closed: bool = False

    def enable_ai(self):
        if self._closed:
            raise RuntimeError("The research workspace is closed.")
        self.settings.repository.require('assistant', *self.settings.context())
        if self.agent_runtime is not None:
            return self.agent_runtime
        from virtual_lab.settings.runtime import ManagedAssistantRuntime as AgentRuntimeService
        from virtual_lab.ai.agent.tool_registry import ToolRegistry
        from virtual_lab.ai.agent.policy import PolicyEngine
        from virtual_lab.ai.agent.context import ScientificContextAssembler
        from virtual_lab.ai.agent.controller import AgentController
        from virtual_lab.ai.agent.genesis_adapter import AgentGenesisRecorder

        registry = ToolRegistry()
        recorder = AgentGenesisRecorder(self.ledger)
        policy = PolicyEngine(registry, recorder, settings=self.settings)
        assembler = ScientificContextAssembler(registry.get_all_schemas())
        controller = AgentController(registry, policy, assembler, recorder, model_backend=None)
        runtime = AgentRuntimeService(self.settings)
        self.tool_registry, self.policy_engine = registry, policy
        self.context_assembler, self.agent_controller = assembler, controller
        self.agent_runtime = runtime
        return runtime

    def shutdown(self):
        if self._closed:
            return
        if self.settings is not None:
            self.settings.cancel()
        self.gateway.stop()
        if self.agent_runtime is not None:
            self.agent_runtime.shutdown()
        self.ledger.conn.close()
        self._closed = True


def create_virtual_lab_runtime(ledger_path=None):
    path = Path(ledger_path) if ledger_path is not None else app_data_dir() / "genesis.db"
    ledger = GenesisLedger(str(path))
    try:
        # The hardware listener is started only when the Instruments tab is opened.
        from virtual_lab.settings import SettingsService, SettingsRepository
        return VirtualLabRuntime(ledger, EvidenceStore(), InstrumentGateway(ledger=ledger, port=8765),
                                 settings=SettingsService(SettingsRepository(path.parent)))
    except BaseException:
        ledger.conn.close()
        raise
