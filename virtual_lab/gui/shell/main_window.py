from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt

from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.gui.shell.theme import get_stylesheet
from virtual_lab.gui.shell.system_monitor import SystemMonitorWidget
from virtual_lab.gui.world.world_view import WorldWorkspace
from virtual_lab.gui.experiments.experiment_workspace import ExperimentWorkspace
from virtual_lab.gui.analysis.analysis_workspace import AnalysisWorkspace
from virtual_lab.gui.ai.local_research_workspace import LocalResearchWorkspace
from virtual_lab.gui.evidence.evidence_workspace import EvidenceWorkspace
from virtual_lab.gui.provenance.provenance_workspace import ProvenanceWorkspace
from virtual_lab.gui.inspectors.numerical_workspace import NumericalWorkspace
from virtual_lab.gui.compare.compare_workspace import CompareWorkspace
from virtual_lab.gui.services.evidence_store import EvidenceStore
from virtual_lab.gui.services.mapping import StructureMappingService
from virtual_lab.core.runtime import create_virtual_lab_runtime
from virtual_lab.version import __version__


class VirtualLabApplication(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"VirtualLab v{__version__} - Scientific Cockpit")
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
        
        lbl_proj = QLabel("Project: None selected")
        self.project_label = lbl_proj
        lbl_exp = QLabel("Experiment: Unassigned staging")
        self.experiment_label = lbl_exp
        lbl_branch = QLabel("Research workspace")
        lbl_proj.setTextFormat(Qt.PlainText)
        lbl_exp.setTextFormat(Qt.PlainText)
        
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
        self.local_research = LocalResearchWorkspace(self.workspace, agent_runtime=self.runtime.agent_runtime, prediction_ledger=self.ledger)
        from virtual_lab.gui.instruments.workspace import InstrumentsWorkspace
        self.instruments = InstrumentsWorkspace(self.workspace, gateway=self.runtime.gateway, ledger=self.ledger)
        from virtual_lab.gui.computational_workspace import ComputationalWorkspace
        self.computational = ComputationalWorkspace(self.workspace, ledger=self.ledger)
        self.evidence = EvidenceWorkspace(self.workspace)
        self.provenance = ProvenanceWorkspace(self.workspace, ledger=self.ledger)
        self.numerical = NumericalWorkspace(self.workspace)
        self.compare = CompareWorkspace(self.workspace)
        
        from virtual_lab.gui.projects_workspace import ProjectsWorkspace
        self.projects = ProjectsWorkspace(self.workspace, self.ledger)
        from virtual_lab.gui.calibration_workspace import CalibrationWorkspace
        self.calibration = CalibrationWorkspace(self.workspace, self.projects.service)
        from virtual_lab.gui.biological_workspace import BiologicalWorkspace
        self.biological = BiologicalWorkspace(self.workspace, self.projects.service)
        self.tabs.addTab(self.projects, "Projects")
        self.tabs.addTab(self.biological, "Biological objects")
        self.workspace.biologicalDraftRequested.connect(lambda _: self.tabs.setCurrentWidget(self.biological))
        self.tabs.addTab(self.world, "RHO reference")
        self.tabs.addTab(self.experiment, "Simulation")
        self.tabs.addTab(self.analysis, "Analysis")
        from virtual_lab.gui.maturation_validation_workspace import MaturationValidationWorkspace
        self.maturation_validation = MaturationValidationWorkspace(self.workspace, self.projects.service)
        self.calibration_tabs = QTabWidget()
        self.calibration_tabs.addTab(self.calibration, "RNA decay")
        self.calibration_tabs.addTab(self.maturation_validation, "Maturation validation")
        self.workspace.validationResultChanged.connect(lambda value: self.calibration_tabs.setCurrentWidget(self.maturation_validation) if value else None)
        self.workspace.calibrationResultChanged.connect(lambda value: self.calibration_tabs.setCurrentWidget(self.calibration) if value else None)
        self.tabs.addTab(self.calibration_tabs, "Calibration")
        self.tabs.addTab(self.local_research, "Local Research Mode")
        self.tabs.addTab(self.instruments, "Instruments")
        self.tabs.addTab(self.computational, "Computational Biology")
        self.tabs.addTab(self.evidence, "Evidence")
        self.tabs.addTab(self.provenance, "Provenance")
        self.tabs.addTab(self.numerical, "Numerical")
        self.tabs.addTab(self.compare, "Compare")
        
        # Setup LocalResearchWorkspace backend wiring
        self.local_research.controller = self.runtime.agent_controller
        
        # LocalResearchWorkspace reports whether Vertex credentials are configured.

            
        self.workspace.evidenceSelectionChanged.connect(lambda _: self.tabs.setCurrentWidget(self.evidence))
        self.workspace.resultChanged.connect(self._refresh_status)
        self._refresh_status()
        self.workspace.activeExperimentChanged.connect(self._refresh_context)
        self._refresh_context()

    def _refresh_context(self, *_):
        exp = self.workspace.active_experiment
        project = next((p for p in self.projects.service.projects()
                        if exp and p['id'] == exp.project_id), None)
        self.project_label.setText('Project: ' + (project['name'] if project else 'None selected'))
        self.experiment_label.setText('Experiment: ' + ((exp.label or exp.id) if exp else 'Unassigned staging'))

    def _refresh_status(self,*_):
        from virtual_lab.gui.services.run_store import RunStore
        try:
            store=RunStore();runs=store.load_all()
            self.ledger_status.setText(f"{len(runs)} saved simulation runs verified" if store.events() else "No local ledger yet")
        except Exception as exc:
            self.ledger_status.setText("INTEGRITY ERROR")
            self.ledger_status.setToolTip(str(exc))

    def closeEvent(self,event):
        if self.computational.busy:
            self.computational.cancel()
            self.computational.status.setText("Cancelling computational run; close again when cancellation completes.")
            event.ignore()
            return
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
