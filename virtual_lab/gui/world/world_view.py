from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel, QSplitter, QHBoxLayout, QSlider
from PySide6.QtCore import Qt

from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.gui.services.selection_controller import SelectionController
from virtual_lab.gui.world.protein_view import ProteinView
from virtual_lab.gui.world.navigator import ScientificNavigator
from virtual_lab.gui.world.tissue_view import TissueView
from virtual_lab.gui.world.molecule_view import MoleculeView
from virtual_lab.gui.world.cell_view import CellView
from virtual_lab.gui.inspectors.object_inspector import ObjectInspector

class StubView(QWidget):
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #8b9bb4;")
        lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_title)
        lbl_msg = QLabel(message)
        lbl_msg.setStyleSheet("color: #5c6d86;")
        lbl_msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_msg)

class WorldWorkspace(QWidget):
    def __init__(self, workspace: WorkspaceState, evidence_store, mapping_service, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.controller = SelectionController(workspace, mapping_service)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 3-Column Splitter Layout
        splitter = QSplitter(Qt.Horizontal)
        
        # Left: Navigator
        self.navigator = ScientificNavigator(self.controller)
        splitter.addWidget(self.navigator)
        
        # Center: Viewports (Tabs)
        self.center_widget = QWidget()
        center_layout = QVBoxLayout(self.center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tabs = QTabWidget()
        self.protein_view = ProteinView(self.workspace, self.controller)
        self.cellular_view = CellView(workspace)
        self.tissue_view = TissueView(workspace)
        self.molecular_view = MoleculeView(workspace)
        
        self.tabs.addTab(self.molecular_view, "Molecular")
        self.tabs.addTab(self.protein_view, "Protein Context")
        self.tabs.addTab(self.cellular_view, "Cellular")
        self.tabs.addTab(self.tissue_view, "Tissue")
        self.tabs.setCurrentIndex(1)
        self.controller.viewRequested.connect(lambda title: self.tabs.setCurrentIndex(next((i for i in range(self.tabs.count()) if self.tabs.tabText(i)==title), 1)))
        
        center_layout.addWidget(self.tabs)
        splitter.addWidget(self.center_widget)
        
        # Right: Inspector
        self.inspector = ObjectInspector(workspace, evidence_store)
        splitter.addWidget(self.inspector)
        
        splitter.setSizes([250, 750, 300]) # Approximate 20% / 60% / 20%
        main_layout.addWidget(splitter)
        
        # Bottom: Timeline
        timeline_widget = QWidget()
        timeline_widget.setStyleSheet("background-color: #16202d; border-top: 1px solid #293647;")
        tl_layout = QHBoxLayout(timeline_widget)
        tl_layout.addWidget(QLabel("0 h"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 48)
        self.slider.valueChanged.connect(self._on_slider_changed)
        tl_layout.addWidget(self.slider)
        self.lbl_time = QLabel("0.0 h")
        tl_layout.addWidget(self.lbl_time)
        tl_layout.addWidget(QLabel("48 h"))
        
        main_layout.addWidget(timeline_widget)
        
        # Sync slider if workspace time changes elsewhere
        self.workspace.simulationTimeChanged.connect(self._sync_timeline)
        
    def _on_slider_changed(self, value):
        self.lbl_time.setText(f"{float(value):.1f} h")
        self.workspace.simulation_time_h = float(value)
        
    def _sync_timeline(self, value):
        if self.slider.value() != int(value):
            self.slider.setValue(int(value))
            self.lbl_time.setText(f"{float(value):.1f} h")
