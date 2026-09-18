import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTableWidget, QTableWidgetItem
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.domain.compatibility import find_compatible_pairs

class CompareWorkspace(QWidget):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.experiments = []
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Compare experiments • requires semantic and dimensional compatibility"))
        
        selectors = QHBoxLayout()
        self.left = QComboBox()
        self.right = QComboBox()
        selectors.addWidget(self.left)
        selectors.addWidget(self.right)
        layout.addLayout(selectors)
        
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Quantity", "Dim / Unit", "Exp A", "Exp B", "B − A"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        
        self.note = QLabel("No experiments to compare.")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        
        self.left.currentIndexChanged.connect(self.render)
        self.right.currentIndexChanged.connect(self.render)
        
        # In a real app we'd connect to workspace state signals to refresh
        self.workspace.activeExperimentChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        db = ExperimentStore()
        self.experiments = db.list_experiments()
        db.close()
        
        self.left.blockSignals(True)
        self.right.blockSignals(True)
        self.left.clear()
        self.right.clear()
        
        for exp in self.experiments:
            label = exp.get("label") or "Unnamed"
            text = f"{exp['id'][:8]} • {exp['compound_id']} • {label}"
            self.left.addItem(text, userData=exp['id'])
            self.right.addItem(text, userData=exp['id'])
            
        if self.experiments:
            self.right.setCurrentIndex(len(self.experiments)-1)
            
        self.left.blockSignals(False)
        self.right.blockSignals(False)
        self.render()

    def render(self, *_):
        if not self.experiments:
            return
            
        idx_a = self.left.currentIndex()
        idx_b = self.right.currentIndex()
        if idx_a < 0 or idx_b < 0: return
        
        exp_a_id = self.left.itemData(idx_a)
        exp_b_id = self.right.itemData(idx_b)
        
        db = ExperimentStore()
        obs_a = db.get_observations_for_experiment(exp_a_id)
        obs_b = db.get_observations_for_experiment(exp_b_id)
        db.close()
        
        compatible, incompatible = find_compatible_pairs(obs_a, obs_b)
        
        self.table.setRowCount(len(compatible))
        for i, pair in enumerate(compatible):
            # We don't have scalar values easily accessible in the generic model without loading the artifact.
            # For this prototype we will just show the compatibility link.
            # In a full implementation we would parse the artifacts or stats.
            
            # Since simulation output creates observations with 0 samples, we just display the quantity name.
            name = pair.quantity_a.semantic_name
            dim_unit = f"{pair.quantity_a.physical_dimension.value} ({pair.quantity_a.units})"
            
            # Display epistemic state to show lineage
            val_a = f"[{pair.quantity_a.epistemic_state.value}]"
            val_b = f"[{pair.quantity_b.epistemic_state.value}]"
            
            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(dim_unit))
            self.table.setItem(i, 2, QTableWidgetItem(val_a))
            self.table.setItem(i, 3, QTableWidgetItem(val_b))
            self.table.setItem(i, 4, QTableWidgetItem("N/A (See Artifacts)"))

        if incompatible:
            incomp_names = [inc.quantity_a.semantic_name for inc in incompatible]
            self.note.setText(f"Incompatible quantities in Exp A not comparable to Exp B: {', '.join(incomp_names)}")
        else:
            self.note.setText("All quantities from Exp A were semantically matched to Exp B.")
