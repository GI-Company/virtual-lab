import numpy as np
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QComboBox,QTableWidget,QTableWidgetItem
from virtual_lab.gui.services.run_store import RunStore
class CompareWorkspace(QWidget):
    def __init__(self,workspace,parent=None):
        super().__init__(parent);self.runs=[];layout=QVBoxLayout(self)
        layout.addWidget(QLabel("Compare saved runs • differences are exploratory model outputs"))
        self.left=QComboBox();self.right=QComboBox();layout.addWidget(self.left);layout.addWidget(self.right)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(["State","Run A median","Run B median","B − A"])
        self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table)
        self.note=QLabel("No saved experiments.");self.note.setWordWrap(True);layout.addWidget(self.note)
        self.left.currentIndexChanged.connect(self.render);self.right.currentIndexChanged.connect(self.render)
        workspace.resultChanged.connect(self.refresh);self.refresh()
    def refresh(self,*_):
        try:self.runs=RunStore().load_all()
        except Exception as exc:self.note.setText(f"Cannot verify saved runs: {exc}");return
        self.left.blockSignals(True);self.right.blockSignals(True);self.left.clear();self.right.clear()
        for r in self.runs:
            text=f"{r['id'][:8]} • {r['config']['compound']} • {r['config']['concentration_um']} µM"
            self.left.addItem(text);self.right.addItem(text)
        self.right.setCurrentIndex(len(self.runs)-1)
        self.left.blockSignals(False);self.right.blockSignals(False);self.render()
    def render(self,*_):
        if not self.runs:return
        a,b=self.runs[self.left.currentIndex()],self.runs[self.right.currentIndex()]
        x,y=np.median(a['final_state'],axis=0),np.median(b['final_state'],axis=0)
        self.table.setRowCount(len(x))
        for i,name in enumerate(a['state_names']):
            for j,value in enumerate([name,f"{x[i]:.5g}",f"{y[i]:.5g}",f"{y[i]-x[i]:+.5g}"]):self.table.setItem(i,j,QTableWidgetItem(value))
        mismatches=[k for k in a['config'] if a['config'][k]!=b['config'][k]]
        vehicle=np.median(b['control_final_state'],axis=0)
        self.note.setText("Changed settings: "+(", ".join(mismatches) or "none")+f"\nRun B surface-pool change versus its paired vehicle: {y[2]-vehicle[2]:+.5g}.\nNumerical checks: A {a['numerical_check']['status']}, B {b['numerical_check']['status']}. Source code identical: {a['source_hashes']==b['source_hashes']}.")
