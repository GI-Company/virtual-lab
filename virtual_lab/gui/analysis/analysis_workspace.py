import numpy as np
from scipy.stats import spearmanr
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, 
                               QListWidget, QLabel, QTableWidget, QTableWidgetItem)
from PySide6.QtCore import Qt
import pyqtgraph as pg

# State names map
STATE_NAMES = [
    "Surface RHO",
    "ER Retention",
    "ER Stress",
    "Viability"
]
# The actual states are indices 2, 1, 3, 4 based on the Rho ODE (R_f=0, R_ER=1, R_s=2, S=3, V=4)
STATE_INDICES = [2, 1, 3, 4] 

class AnalysisWorkspace(QWidget):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.result = None
        
        # UI Layout
        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        
        # Left Panel - Endpoints
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Endpoints"))
        
        self.list_endpoints = QListWidget()
        self.list_endpoints.addItems(STATE_NAMES)
        self.list_endpoints.setCurrentRow(0)
        self.list_endpoints.currentRowChanged.connect(self.refresh)
        
        # When an endpoint is clicked, update global selected_object
        self.list_endpoints.itemClicked.connect(self._on_endpoint_clicked)
        left_layout.addWidget(self.list_endpoints)
        
        # Right Panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Top right: Distribution and PRCC
        top_right = QHBoxLayout()
        
        # Endpoint Distribution
        dist_panel = QVBoxLayout()
        dist_panel.addWidget(QLabel("Endpoint Distribution (final_state)"))
        self.plot_dist = pg.PlotWidget(background="#16202d")
        self.plot_dist.setLabel('bottom', "Normalized State")
        self.plot_dist.setLabel('left', "Count")
        dist_panel.addWidget(self.plot_dist)
        top_right.addLayout(dist_panel)
        
        # PRCC Table
        prcc_panel = QVBoxLayout()
        prcc_panel.addWidget(QLabel("PRCC (Monotonic Association)"))
        self.table_prcc = QTableWidget(0, 2)
        self.table_prcc.setHorizontalHeaderLabels(["Parameter", "PRCC"])
        self.table_prcc.horizontalHeader().setStretchLastSection(True)
        prcc_panel.addWidget(self.table_prcc)
        top_right.addLayout(prcc_panel)
        
        right_layout.addLayout(top_right)
        
        # Bottom right: Time Course
        bottom_right = QVBoxLayout()
        bottom_right.addWidget(QLabel("Time Course (summary_trajectory)"))
        self.plot_time = pg.PlotWidget(background="#16202d")
        self.plot_time.setLabel('bottom', "Time (hours)")
        self.plot_time.setLabel('left', "Normalized State")
        self.plot_time.addLegend()
        bottom_right.addWidget(self.plot_time)
        
        right_layout.addLayout(bottom_right)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        
        main_layout.addWidget(splitter)
        
        workspace.resultChanged.connect(self.set_result)

    def _on_endpoint_clicked(self, item):
        # Update global selection when an endpoint is clicked
        from virtual_lab.gui.services.selection import ScientificSelection, SelectionKind
        self.workspace.selected_object = ScientificSelection(
            kind=SelectionKind.ENDPOINT,
            label=item.text()
        )

    def set_result(self, result):
        self.result = result
        self.refresh()

    def refresh(self):
        if not self.result: return
        r = self.result
        idx = self.list_endpoints.currentRow()
        if idx < 0: return
        state_idx = STATE_INDICES[idx]
        state_name = STATE_NAMES[idx]
        
        # 1. Endpoint Distribution
        self.plot_dist.clear()
        final_state = r.final_state[:, state_idx]
        
        # Create histogram using numpy
        if len(final_state) > 1:
            y, x = np.histogram(final_state, bins=40)
            # pg.BarGraphItem draws bars. x[:-1] is left edge.
            bg = pg.BarGraphItem(x0=x[:-1], x1=x[1:], height=y, brush="#38bdf8")
            self.plot_dist.addItem(bg)
        
        # 2. Time Course
        self.plot_time.clear()
        times = r.times_h
        
        if r.summary_trajectory:
            # Treated median and bands
            p05 = r.summary_trajectory["p05"][:, state_idx]
            med = r.summary_trajectory["median"][:, state_idx]
            p95 = r.summary_trajectory["p95"][:, state_idx]
            
            # Fill between p05 and p95
            fill = pg.FillBetweenItem(
                pg.PlotCurveItem(times, p95),
                pg.PlotCurveItem(times, p05),
                brush=(56, 189, 248, 50)
            )
            self.plot_time.addItem(fill)
            self.plot_time.plot(times, med, pen=pg.mkPen("#38bdf8", width=2), name="Treated Median")
            
        # 3. PRCC Table
        # We calculate PRCC on the fly using Spearman correlation as a proxy for monotonic association
        self.table_prcc.clearContents()
        y = r.final_state[:, state_idx]
        
        items = []
        for param_name, values in r.parameter_samples.items():
            if len(y) > 2 and np.ptp(values) > 0 and np.ptp(y) > 0:
                rho = float(spearmanr(values, y).statistic)
                items.append((param_name, rho))
                
        items.sort(key=lambda kv: abs(kv[1] or 0), reverse=True)
        self.table_prcc.setRowCount(len(items))
        for row, (k, v) in enumerate(items):
            self.table_prcc.setItem(row, 0, QTableWidgetItem(k))
            val_str = f"{v:.3f}" if v is not None and np.isfinite(v) else "Not estimable"
            self.table_prcc.setItem(row, 1, QTableWidgetItem(val_str))
