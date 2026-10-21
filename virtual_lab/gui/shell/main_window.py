from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QGridLayout, QLabel, QPushButton, QSizePolicy, QDockWidget, QFrame, QScrollArea, QLayout
from PySide6.QtCore import Qt

from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.gui.shell.theme import get_stylesheet
from virtual_lab.gui.shell.system_monitor import SystemMonitorWidget
from virtual_lab.gui.world.world_view import WorldWorkspace
from virtual_lab.gui.experiments.experiment_workspace import ExperimentWorkspace
from virtual_lab.gui.analysis.analysis_workspace import AnalysisWorkspace
from virtual_lab.gui.evidence.evidence_workspace import EvidenceWorkspace
from virtual_lab.gui.provenance.provenance_workspace import ProvenanceWorkspace
from virtual_lab.gui.inspectors.numerical_workspace import NumericalWorkspace
from virtual_lab.gui.compare.compare_workspace import CompareWorkspace
from virtual_lab.gui.services.evidence_store import EvidenceStore
from virtual_lab.gui.services.mapping import StructureMappingService
from virtual_lab.core.runtime import create_virtual_lab_runtime
from virtual_lab.version import __version__
from virtual_lab.gui.shell.layout import make_workspace_scrollable


class VirtualLabApplication(QMainWindow):
    def __init__(self):
        super().__init__()
        # Destroy child WebEngine pages before QApplication releases its profile.
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"VirtualLab v{__version__} - Scientific Cockpit")
        available = self.screen().availableGeometry()
        self.resize(min(1600, available.width()), min(1000, available.height()-30))
        self.setMinimumSize(800, 600)
        
        self.setStyleSheet(get_stylesheet())
        
        self.local_research = None
        self.workspace = WorkspaceState()
        self.mapping_service = StructureMappingService()
        
        # Initialize Unified Runtime
        self.runtime = create_virtual_lab_runtime()
        self.ledger = self.runtime.ledger
        self.evidence_store = self.runtime.evidence_store
        
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Global Header
        header = QWidget()
        header.setObjectName('globalHeader')
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        header.setStyleSheet("QWidget#globalHeader { background-color: #1c2838; border-bottom: 1px solid #293647; }")
        h_layout = QGridLayout(header)
        h_layout.setContentsMargins(10, 4, 10, 4)
        h_layout.setColumnStretch(1, 1)
        h_layout.setColumnStretch(2, 1)
        
        lbl_title = QLabel("<b>VirtualLab</b>")
        lbl_title.setStyleSheet("font-size: 16px; color: #ffffff;")
        h_layout.addWidget(lbl_title, 0, 0)
        
        lbl_proj = QLabel("Project: None selected")
        self.project_label = lbl_proj
        lbl_exp = QLabel("Experiment: Unassigned staging")
        self.experiment_label = lbl_exp
        lbl_proj.setTextFormat(Qt.PlainText)
        lbl_exp.setTextFormat(Qt.PlainText)
        for label in (lbl_proj, lbl_exp):
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        h_layout.addWidget(lbl_proj, 1, 0, 1, 3)
        h_layout.addWidget(lbl_exp, 2, 0, 1, 3)
        
        lbl_status = QLabel("No saved run verified yet")
        self.ledger_status = lbl_status
        lbl_status.setStyleSheet("color: #22c55e; font-weight: bold;")
        lbl_status.setWordWrap(True)
        lbl_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        # Guided research steps remain reachable in a narrow header.
        self.pipeline_bar = QFrame()
        self.pipeline_bar.setObjectName("pipelineBar")
        self.pipeline_bar.setStyleSheet(
            "QFrame#pipelineBar { background: transparent; border: none; }"
            "QFrame#pipelineBar QPushButton { padding: 2px 6px; font-size: 11px; }"
        )
        pipe_layout = QHBoxLayout(self.pipeline_bar)
        pipe_layout.setContentsMargins(0, 0, 0, 0)
        pipe_layout.setSpacing(4)
        self.pipeline_hint = QLabel("Pipeline: 1. Plan")
        self.pipeline_hint.setStyleSheet("color: #cbd5e1; font-size: 11px; font-weight: bold;")
        self.pipeline_hint.setWordWrap(True)
        self.pipeline_hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        h_layout.addWidget(self.pipeline_hint, 4, 0, 1, 3)

        self.btn_pipe_plan = QPushButton("1. Plan")
        self.btn_pipe_plan.clicked.connect(lambda: self._navigate("Plan"))
        self.btn_pipe_sim = QPushButton("2. Simulate")
        self.btn_pipe_sim.clicked.connect(lambda: self._navigate("Simulation"))
        self.btn_pipe_compare = QPushButton("3. Compare")
        self.btn_pipe_compare.clicked.connect(lambda: self._navigate("Compare"))
        self.btn_pipe_verify = QPushButton("4. Verify")
        self.btn_pipe_verify.clicked.connect(lambda: self._navigate("Numerical"))
        self.btn_pipe_evidence = QPushButton("5. Evidence")
        self.btn_pipe_evidence.clicked.connect(lambda: self._navigate("Evidence"))
        self.btn_pipe_conclude = QPushButton("6. Conclude")
        self.btn_pipe_conclude.clicked.connect(lambda: self._navigate("Conclusion"))
        self.btn_ai_drawer = QPushButton("AI Drawer")
        self.btn_ai_drawer.setCheckable(True)
        self.btn_ai_drawer.setToolTip("Open or close the side-by-side Gemini assistant without leaving the current research stage")
        self.btn_ai_drawer.toggled.connect(self._toggle_ai_drawer)
        for btn in (
            self.btn_pipe_plan,
            self.btn_pipe_sim,
            self.btn_pipe_compare,
            self.btn_pipe_verify,
            self.btn_pipe_evidence,
            self.btn_pipe_conclude,
            self.btn_ai_drawer,
        ):
            btn.setMinimumHeight(22)
            btn.setMaximumHeight(24)
            btn.setMinimumWidth(0)
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            pipe_layout.addWidget(btn)
        self.pipeline_bar.setMinimumWidth(0)
        self.pipeline_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        pipe_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.pipeline_scroll = QScrollArea()
        self.pipeline_scroll.setObjectName("pipelineScroll")
        self.pipeline_scroll.setAccessibleName("Research steps; scroll horizontally for more actions")
        self.pipeline_scroll.setWidgetResizable(True)
        self.pipeline_scroll.setFrameShape(QFrame.NoFrame)
        self.pipeline_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pipeline_scroll.setFixedHeight(44)
        self.pipeline_scroll.setMinimumWidth(0)
        self.pipeline_scroll.setWidget(self.pipeline_bar)

        h_layout.addWidget(lbl_status, 3, 0, 1, 3)
        h_layout.addWidget(self.pipeline_scroll, 5, 0, 1, 3)

        # System monitor — Metal GPU / RAM / Disk
        self.sys_monitor = SystemMonitorWidget()
        h_layout.addWidget(self.sys_monitor, 0, 1, 1, 2)

        main_layout.addWidget(header)

        # Side-by-side AI Assistant Dock (remains closed unless explicitly opened by the researcher)
        self.ai_dock = QDockWidget("Gemini Scientific Assistant (Optional)", self)
        self.ai_dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.ai_dock.setMaximumWidth(560)
        self.ai_dock.setMinimumWidth(0)
        # Keep panel minimum-size hints inside a viewport, not on the window.
        self.ai_dock_scroll = QScrollArea()
        self.ai_dock_scroll.setWidgetResizable(True)
        self.ai_dock_scroll.setMinimumSize(0, 0)
        self.ai_dock_scroll.setFrameShape(QFrame.NoFrame)
        self.ai_dock.setWidget(self.ai_dock_scroll)
        self.ai_dock.visibilityChanged.connect(self._on_ai_dock_visibility_changed)
        self.addDockWidget(Qt.RightDockWidgetArea, self.ai_dock)
        self.ai_dock.hide()
        
        # Main Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        main_layout.addWidget(self.tabs, 1)
        
        # Initialize Workspaces
        self.world = WorldWorkspace(self.workspace, self.evidence_store, self.mapping_service)
        self.experiment = ExperimentWorkspace(self.workspace)
        self.analysis = AnalysisWorkspace(self.workspace)
        self.ai_panel = QWidget()
        self.ai_layout = QVBoxLayout(self.ai_panel)
        self.ai_status = QLabel("AI assistance is off. You can plan, run, analyze, conclude, and export studies without AI.")
        self.ai_status.setWordWrap(True)
        self.ai_enable_button = QPushButton("Enable optional AI assistance")
        self.ai_enable_button.clicked.connect(self._enable_ai)
        self.ai_layout.addWidget(self.ai_status)
        self.ai_layout.addWidget(self.ai_enable_button)
        self.ai_layout.addStretch()
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
        self.tabs.addTab(self.ai_panel, "AI assistance (optional)")
        self.tabs.addTab(self.instruments, "Instruments")
        self.tabs.addTab(self.computational, "Computational Biology")
        self.tabs.addTab(self.evidence, "Evidence")
        self.tabs.addTab(self.provenance, "Provenance")
        self.tabs.addTab(self.numerical, "Numerical")
        self.tabs.addTab(self.compare, "Compare")
        for index in range(self.tabs.count()):
            make_workspace_scrollable(self.tabs.widget(index))
        
        self.tabs.currentChanged.connect(self._tab_changed)
        self.projects.navigateRequested.connect(self._navigate)
        self.experiment.navigateRequested.connect(self._navigate)
        self.analysis.navigateRequested.connect(self._navigate)
        self.numerical.navigateRequested.connect(self._navigate)
        self.compare.navigateRequested.connect(self._navigate)
        self.evidence.navigateRequested.connect(self._navigate)
        self.workspace.evidenceSelectionChanged.connect(lambda _: self.tabs.setCurrentWidget(self.evidence))
        self.workspace.resultChanged.connect(self._refresh_status)
        self.workspace.observationCommitted.connect(self._refresh_status)
        self.workspace.observationStaged.connect(self._refresh_status)
        self._refresh_status()
        self.workspace.activeExperimentChanged.connect(self._refresh_context)
        self._refresh_context()

    def _enable_ai(self):
        if self.local_research is not None:
            return
        try:
            from virtual_lab.gui.ai.local_research_workspace import LocalResearchWorkspace
            runtime = self.runtime.enable_ai()
            panel = LocalResearchWorkspace(self.workspace, agent_runtime=runtime, prediction_ledger=self.ledger)
            panel.controller = self.runtime.agent_controller
        except ImportError:
            self.ai_status.setText("Optional AI assistance is not installed. All manual research tools remain available. Install the ai extra to enable assistance.")
            return
        except Exception as exc:
            self.ai_status.setText(f"AI assistance could not start: {exc}. Manual research remains available.")
            return
        self.local_research = panel
        make_workspace_scrollable(panel)
        self.ai_enable_button.hide()
        self.ai_status.hide()
        if self.workspace.ai_state == "off":
            self.workspace.ai_state = "enabled"
        if self.ai_dock.isVisible():
            self._place_ai_in_dock()
        else:
            self.ai_layout.insertWidget(0, panel)

    def _place_ai_in_dock(self):
        if self.local_research is None:
            return
        self.ai_layout.removeWidget(self.local_research)
        if hasattr(self.local_research, "set_compact_mode"):
            self.local_research.set_compact_mode(True)
        self.ai_dock_scroll.setWidget(self.local_research)
        self.local_research.show()
        self.ai_status.setText("Gemini assistant is open in the side-by-side drawer so you can stay on your current research stage.")
        self.ai_status.show()

    def _place_ai_in_tab(self):
        if self.local_research is None:
            return
        if self.ai_dock_scroll.widget() is self.local_research:
            self.ai_dock_scroll.takeWidget()
        if hasattr(self.local_research, "set_compact_mode"):
            self.local_research.set_compact_mode(False)
        self.ai_status.hide()
        self.ai_layout.insertWidget(0, self.local_research)
        self.local_research.show()

    def _toggle_ai_drawer(self, checked: bool):
        if checked:
            if self.local_research is None:
                self._enable_ai()
            if self.local_research is None:
                self.btn_ai_drawer.blockSignals(True)
                self.btn_ai_drawer.setChecked(False)
                self.btn_ai_drawer.blockSignals(False)
                self.tabs.setCurrentWidget(self.ai_panel)
                return
            self._place_ai_in_dock()
            self.ai_dock.show()
            target_w = max(320, min(420, int(self.width() * 0.30)))
            self.resizeDocks([self.ai_dock], [target_w], Qt.Horizontal)
        else:
            self.ai_dock.hide()
            self._place_ai_in_tab()

    def _on_ai_dock_visibility_changed(self, visible: bool):
        self.btn_ai_drawer.blockSignals(True)
        self.btn_ai_drawer.setChecked(visible)
        self.btn_ai_drawer.blockSignals(False)
        if not visible and getattr(self, "local_research", None) is not None:
            self._place_ai_in_tab()

    def _tab_changed(self, *_):
        if self.tabs.currentWidget() is self.instruments and not self.runtime.gateway.server.isListening():
            if not self.runtime.gateway.start():
                self.instruments.lbl_status.setText("Instrument listener could not start; port 8765 may be in use.")

    def _navigate(self, name):
        if name == "Plan":
            self.tabs.setCurrentWidget(self.projects)
            self.projects.notebook.setCurrentIndex(1)
            return
        if name == "Conclusion":
            self.tabs.setCurrentWidget(self.projects)
            self.projects.notebook.setCurrentIndex(2)
            return
        target = {
            "Projects": self.projects,
            "Simulation": self.experiment,
            "Analysis": self.analysis,
            "Compare": self.compare,
            "Numerical": self.numerical,
            "Evidence": self.evidence,
            "Provenance": self.provenance,
        }.get(name)
        if target is not None:
            self.tabs.setCurrentWidget(target)

    def _refresh_context(self, *_):
        exp = self.workspace.active_experiment
        project = next((p for p in self.projects.service.projects()
                        if exp and p['id'] == exp.project_id), None)
        self.project_label.setText('Project: ' + (project['name'] if project else 'None selected'))
        self.experiment_label.setText('Experiment: ' + ((exp.label or exp.id) if exp else 'Unassigned staging'))
        for label in (self.project_label, self.experiment_label):
            label.setToolTip(label.text())
        self._refresh_status()

    def _refresh_status(self,*_):
        from virtual_lab.gui.services.run_store import RunStore
        try:
            store=RunStore();runs=store.load_all()
            all_events = store.events()
            sim_events = [e for e in all_events if e.get("event_type") in ("SIMULATION_SAVED", "DESIGN_SAVED")]
            exp = self.workspace.active_experiment
            obs = self.projects.service.store.get_observations_for_experiment(exp.id) if exp else []
            imported_events = [e for e in all_events if e.get("event_type") == "STUDY_IMPORTED"]
            if self.ledger is not None:
                for row in self.ledger.conn.execute("SELECT event_type FROM ledger_events WHERE event_type = 'STUDY_IMPORTED'"):
                    imported_events.append({"event_type": row[0]})

            if sim_events and imported_events and obs:
                self.ledger_status.setText(f"{len(runs)} local simulation run(s) + {len(obs)} active study record(s) verified")
            elif sim_events:
                self.ledger_status.setText(f"{len(runs)} saved simulation runs verified")
            elif obs and imported_events:
                plans = sum(o.instrument_id == 'research_plan' for o in obs)
                sims = sum(o.instrument_id == 'simulation' for o in obs)
                conclusions = sum(o.instrument_id == 'research_conclusion' for o in obs)
                for o in obs:
                    self.projects.service.inspect(o)
                self.ledger_status.setText(
                    f"Imported study verified ({len(obs)} records: {plans} plan, {sims} simulation, {conclusions} conclusion · 0 local runs)"
                )
            elif obs:
                self.ledger_status.setText(f"{len(obs)} study record(s) verified (no local simulation runs yet)")
            else:
                self.ledger_status.setText("No local ledger yet")
            self._refresh_pipeline(obs)
        except Exception as exc:
            self.ledger_status.setText("INTEGRITY ERROR")
            self.ledger_status.setToolTip(str(exc))

    def _refresh_pipeline(self, obs=None):
        exp = self.workspace.active_experiment
        if obs is None:
            obs = self.projects.service.store.get_observations_for_experiment(exp.id) if exp else []
        plans = sum(o.instrument_id == 'research_plan' for o in obs)
        sims = sum(o.instrument_id == 'simulation' for o in obs)
        conclusions = sum(o.instrument_id == 'research_conclusion' for o in obs)
        has_current = self.workspace.current_result is not None

        self.btn_pipe_compare.setEnabled(sims >= 2)
        self.btn_pipe_verify.setEnabled(has_current or sims >= 1)
        self.btn_pipe_conclude.setEnabled(exp is not None and plans >= 1 and sims >= 1)

        # Highlight the recommended next pipeline button
        for b in (
            self.btn_pipe_plan,
            self.btn_pipe_sim,
            self.btn_pipe_compare,
            self.btn_pipe_verify,
            self.btn_pipe_evidence,
            self.btn_pipe_conclude,
        ):
            b.setObjectName("")
            b.style().unpolish(b)
            b.style().polish(b)

        if exp is None:
            self.pipeline_hint.setText("Pipeline: Create or open an experiment in Projects to begin")
            recommended = self.btn_pipe_plan
        elif plans == 0:
            self.pipeline_hint.setText("Pipeline Next Step: Save a research plan in Projects")
            recommended = self.btn_pipe_plan
        elif sims == 0:
            self.pipeline_hint.setText("Pipeline Next Step: Run your first simulation scenario")
            recommended = self.btn_pipe_sim
        elif sims == 1:
            self.pipeline_hint.setText("Pipeline Next Step: Run a second exposure scenario to enable Compare Results")
            recommended = self.btn_pipe_sim
        elif conclusions == 0:
            self.pipeline_hint.setText("Pipeline Next Step: Compare Results, Verify Numerical Certificate, Review Evidence, and Record Conclusion")
            recommended = self.btn_pipe_compare
        else:
            self.pipeline_hint.setText("Pipeline Complete: Plan, simulations, and evidence-linked conclusion recorded (ready to export)")
            recommended = None

        if recommended is not None:
            recommended.setObjectName("primary")
            recommended.style().unpolish(recommended)
            recommended.style().polish(recommended)

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
            if self.instruments.session_state == 'RECORDING':
                try:
                    self.instruments._stop_session()
                except Exception as exc:
                    self.instruments.lbl_session_status.setText(f"Could not save recording: {exc}. Stop the session before closing.")
                    event.ignore()
                    return
            if self.local_research is not None and not self.local_research.shutdown_agent_runtime():
                event.ignore()
                return
            try:
                self.instruments.discovery.stop()
            except Exception:
                pass
            if hasattr(self.instruments, "thread_pool"):
                self.instruments.thread_pool.waitForDone(2000)
            self.projects.service.store.close()
            self.runtime.shutdown()
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
