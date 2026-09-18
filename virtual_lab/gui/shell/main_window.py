from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt

from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.gui.shell.theme import get_stylesheet
from virtual_lab.gui.shell.system_monitor import SystemMonitorWidget
from virtual_lab.gui.world.world_view import WorldWorkspace
from virtual_lab.gui.experiments.experiment_workspace import ExperimentWorkspace
from virtual_lab.gui.analysis.analysis_workspace import AnalysisWorkspace
from virtual_lab.gui.ai.workbench import AIWorkbench
from virtual_lab.gui.ai.local_research_workspace import LocalResearchWorkspace
from virtual_lab.gui.evidence.evidence_workspace import EvidenceWorkspace
from virtual_lab.gui.provenance.provenance_workspace import ProvenanceWorkspace
from virtual_lab.gui.inspectors.numerical_workspace import NumericalWorkspace
from virtual_lab.gui.compare.compare_workspace import CompareWorkspace
from virtual_lab.gui.services.evidence_store import EvidenceStore
from virtual_lab.gui.services.mapping import StructureMappingService
from virtual_lab.core.runtime import create_virtual_lab_runtime

class VirtualLabApplication(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VirtualLab v1.0.0-beta.1 - Scientific Cockpit")
        self.resize(1600, 1000)
        self.setMinimumSize(1200, 800)
        self.setMaximumSize(1800, 1200)
        
        self.setStyleSheet(get_stylesheet())
        
        self.workspace = WorkspaceState()
        self.mapping_service = StructureMappingService()
        
        # Initialize Unified Runtime
        self.runtime = create_virtual_lab_runtime(".virtuallab/genesis.db")
        self.ledger = self.runtime.ledger
        self.evidence_store = self.runtime.evidence_store
        
        print("\n--- VIRTUAL LAB RUNTIME ---")
        print(f"runtime_id: {id(self.runtime)}")
        print(f"agent_controller_id: {id(self.runtime.agent_controller)}")
        print(f"gemma_backend_id: {id(self.runtime.gemma_backend)}")
        print(f"memory_store_id: N/A")
        print(f"genesis_ledger_id: {id(self.runtime.ledger)}")
        print(f"tool_registry_id: {id(self.runtime.tool_registry)}")
        print(f"context_assembler_id: {id(self.runtime.context_assembler)}")
        print("---------------------------\n")
        
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Global Header
        header = QWidget()
        header.setStyleSheet("background-color: #1c2838; border-bottom: 1px solid #293647; padding: 10px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 0, 10, 0)
        
        lbl_title = QLabel("<b>VirtualLab</b>")
        lbl_title.setStyleSheet("font-size: 16px; color: #ffffff;")
        h_layout.addWidget(lbl_title)
        
        h_layout.addStretch()
        
        lbl_proj = QLabel("Project: <b>RHO P23H</b>")
        lbl_exp = QLabel("Experiment: <b>Computational hypothesis</b>")
        lbl_branch = QLabel("Model: <b>Exploratory</b>")
        
        h_layout.addWidget(lbl_proj)
        h_layout.addSpacing(15)
        h_layout.addWidget(lbl_exp)
        h_layout.addSpacing(15)
        h_layout.addWidget(lbl_branch)
        h_layout.addSpacing(15)
        
        lbl_status = QLabel("No saved run verified yet")
        self.ledger_status = lbl_status
        lbl_status.setStyleSheet("color: #22c55e; font-weight: bold;")
        h_layout.addWidget(lbl_status)
        
        # System monitor — Metal GPU / RAM / Disk
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet("color: #334155;")
        h_layout.addWidget(sep)
        self.sys_monitor = SystemMonitorWidget()
        h_layout.addWidget(self.sys_monitor)
        
        main_layout.addWidget(header)
        
        # Main Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs)
        
        # Initialize Workspaces
        self.world = WorldWorkspace(self.workspace, self.evidence_store, self.mapping_service)
        self.experiment = ExperimentWorkspace(self.workspace)
        self.analysis = AnalysisWorkspace(self.workspace)
        self.ai = AIWorkbench(self.workspace)
        self.local_research = LocalResearchWorkspace(self.workspace)
        from virtual_lab.gui.instruments.workspace import InstrumentsWorkspace
        self.instruments = InstrumentsWorkspace(self.workspace, ledger=self.ledger)
        self.evidence = EvidenceWorkspace(self.workspace)
        self.provenance = ProvenanceWorkspace(self.workspace)
        self.numerical = NumericalWorkspace(self.workspace)
        self.compare = CompareWorkspace(self.workspace)
        
        self.tabs.addTab(self.world, "World")
        self.tabs.addTab(self.experiment, "Experiment")
        self.tabs.addTab(self.analysis, "Analysis")
        self.tabs.addTab(self.local_research, "Local Research Mode")
        self.tabs.addTab(self.ai, "Design & ML Gate (Legacy)")
        self.tabs.addTab(self.instruments, "Instruments")
        self.tabs.addTab(self.evidence, "Evidence")
        self.tabs.addTab(self.provenance, "Provenance")
        self.tabs.addTab(self.numerical, "Numerical")
        self.tabs.addTab(self.compare, "Compare")
        self.ai.controller = self.experiment.controller
        
        # Setup LocalResearchWorkspace backend wiring
        self.local_research.controller = self.runtime.agent_controller
        
        if not self.runtime.gemma_backend:
            self.local_research.lbl_answer.setText("<span style='color:red;'>BACKEND OFFLINE</span>")
            self.local_research.lbl_mem_info.setText("NO ACTIVE HVIEW")
            
        self.workspace.evidenceSelectionChanged.connect(lambda _: self.tabs.setCurrentWidget(self.evidence))
        self.workspace.resultChanged.connect(self._refresh_status)
        self._refresh_status()
        from virtual_lab.gui.services.run_store import RunStore
        from virtual_lab.gui.services.simulation_result import SimulationResult
        try:
            runs=RunStore().load_all()
            if runs:self.workspace.current_result=SimulationResult.from_dict(runs[-1])
        except Exception:
            pass  # Integrity error is visible in the header and Provenance workspace.

    def _refresh_status(self,*_):
        from virtual_lab.gui.services.run_store import RunStore
        try:
            store=RunStore();runs=store.load_all()
            self.ledger_status.setText(f"{len(runs)} saved runs verified" if store.events() else "No local ledger yet")
        except Exception as exc:
            self.ledger_status.setText("INTEGRITY ERROR")
            self.ledger_status.setToolTip(str(exc))

    def closeEvent(self,event):
        if self.experiment.controller.worker is not None:
            self.experiment.controller.cancel()
            self.experiment.status.setText("Cancelling active run; close again when cancellation completes.")
            event.ignore()
        else:
            event.accept()


def run():
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = VirtualLabApplication()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run()
