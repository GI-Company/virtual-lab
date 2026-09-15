import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QFormLayout
from PySide6.QtCore import Qt
import pyqtgraph as pg

class TissueView(QWidget):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.result = None
        
        layout = QVBoxLayout(self)
        
        # Header
        lbl_title = QLabel("Tissue: Outer Nuclear Layer (ONL) Thickness")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #8b9bb4;")
        layout.addWidget(lbl_title)
        
        self.note = QLabel("Extrapolating tissue-level macroscopic ONL thickness from median cellular viability.")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #5c6d86;")
        layout.addWidget(self.note)
        
        # Plot
        self.plot = pg.PlotWidget(background="#16202d")
        self.plot.setLabel('bottom', "Time (hours)")
        self.plot.setLabel('left', "ONL Thickness (μm)")
        self.plot.setYRange(0, 50)
        self.plot.addLegend()
        layout.addWidget(self.plot, 1)
        
        # Current status
        status_layout = QHBoxLayout()
        self.lbl_current_time = QLabel("0.0 h")
        self.lbl_current_onl = QLabel("-- μm")
        self.lbl_current_onl.setStyleSheet("font-size: 18px; font-weight: bold; color: #38bdf8;")
        
        status_layout.addWidget(QLabel("Current Checkpoint:"))
        status_layout.addWidget(self.lbl_current_time)
        status_layout.addWidget(QLabel("ONL Thickness:"))
        status_layout.addWidget(self.lbl_current_onl)
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        workspace.resultChanged.connect(self.set_result)
        workspace.simulationTimeChanged.connect(self.render)
        
    def set_result(self, result):
        self.result = result
        self._update_plot()
        self.render(workspace_time=self.workspace.simulation_time_h)
        
    def _update_plot(self):
        self.plot.clear()
        if not self.result: return
        r = self.result
        
        times = r.times_h
        # Viability is state index 4
        # Assuming healthy ONL is ~45 μm
        base_onl = 45.0 
        
        if r.summary_trajectory:
            med_v = r.summary_trajectory["median"][:, 4]
            med_onl = med_v * base_onl
            
            p05_v = r.summary_trajectory["p05"][:, 4]
            p95_v = r.summary_trajectory["p95"][:, 4]
            
            fill = pg.FillBetweenItem(
                pg.PlotCurveItem(times, p95_v * base_onl),
                pg.PlotCurveItem(times, p05_v * base_onl),
                brush=(56, 189, 248, 50)
            )
            self.plot.addItem(fill)
            self.plot.plot(times, med_onl, pen=pg.mkPen("#38bdf8", width=2), name="Treated Median ONL")
            
            # Baseline reference (healthy)
            self.plot.plot([times[0], times[-1]], [base_onl, base_onl], pen=pg.mkPen("#5c6d86", style=Qt.DashLine), name="Healthy Reference")

    def render(self, workspace_time=0):
        if not self.result: return
        r = self.result
        
        index = int(np.argmin(abs(np.asarray(r.times_h) - workspace_time)))
        if r.summary_trajectory:
            med_v = r.summary_trajectory["median"][index, 4]
            current_onl = med_v * 45.0
            
            self.lbl_current_time.setText(f"{r.times_h[index]:.2f} h")
            self.lbl_current_onl.setText(f"{current_onl:.1f} μm")
