from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTableWidget, QTableWidgetItem, QPushButton, QFrame
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.gui.services.study_service import StudyService
from virtual_lab.gui.services.research_outputs import compare_simulations


class CompareWorkspace(QWidget):
    navigateRequested = Signal(str)

    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.runs = {}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Compare saved simulations • final ensemble medians and 5th–95th percentiles'))
        selectors = QHBoxLayout()
        self.left, self.right = QComboBox(), QComboBox()
        self.left.setAccessibleName('Simulation A')
        self.right.setAccessibleName('Simulation B')
        for label, selector in [('A', self.left), ('B', self.right)]:
            selectors.addWidget(QLabel(label)); selectors.addWidget(selector, 1)
        self.btn_numerical = QPushButton("Verify Numerical Certificate")
        self.btn_numerical.clicked.connect(lambda: self.navigateRequested.emit("Numerical"))
        self.btn_evidence = QPushButton("Review Evidence")
        self.btn_evidence.clicked.connect(lambda: self.navigateRequested.emit("Evidence"))
        self.btn_conclusion = QPushButton("Record Conclusion")
        self.btn_conclusion.setObjectName("primary")
        self.btn_conclusion.clicked.connect(lambda: self.navigateRequested.emit("Conclusion"))
        for btn in (self.btn_numerical, self.btn_evidence, self.btn_conclusion):
            selectors.addWidget(btn)
        layout.addLayout(selectors)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Quantity', 'Unit', 'A median [p05, p95]', 'B median [p05, p95]', 'B − A median'])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.note = QLabel()
        self.note.setTextFormat(Qt.PlainText)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.left.currentIndexChanged.connect(self.render)
        self.right.currentIndexChanged.connect(self.render)
        workspace.activeExperimentChanged.connect(self.refresh)
        workspace.activeProjectChanged.connect(self.refresh)
        workspace.observationCommitted.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        selected = (self.left.currentData(), self.right.currentData())
        self.runs = {}
        db = ExperimentStore()
        try:
            for exp in db.list_experiments():
                if not self.workspace.active_project_id or exp['project_id'] != self.workspace.active_project_id:
                    continue
                for obs in db.get_observations_for_experiment(exp['id']):
                    if obs.instrument_id == 'simulation':
                        self.runs[obs.observation_id] = (obs, f"{exp['label'] or exp['id'][:8]} · {obs.session_id[:8]}")
        finally:
            db.close()
        for selector, previous in zip((self.left, self.right), selected):
            selector.blockSignals(True); selector.clear()
            for key, (_, label) in self.runs.items(): selector.addItem(label, key)
            index = selector.findData(previous)
            if index >= 0: selector.setCurrentIndex(index)
            selector.blockSignals(False)
        if selected[1] is None and self.right.count() > 1:
            self.right.setCurrentIndex(self.right.count()-1)
        self.render()

    def render(self, *_):
        self.table.setRowCount(0)
        a, b = self.left.currentData(), self.right.currentData()
        if a not in self.runs or b not in self.runs:
            self.note.setText('Save and attach simulations to experiments, then select two runs.')
            return
        try:
            payload_a = StudyService.inspect(self.runs[a][0])
            payload_b = StudyService.inspect(self.runs[b][0])
            rows = compare_simulations(payload_a, payload_b)
            self.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                qa, qb = row['a'], row['b']
                values = [row['state'], row['units'], f'{qa[1]:.6g} [{qa[0]:.6g}, {qa[2]:.6g}]',
                          f'{qb[1]:.6g} [{qb[0]:.6g}, {qb[2]:.6g}]', f"{row['delta']:.6g}"]
                for j, value in enumerate(values): self.table.setItem(i, j, QTableWidgetItem(value))
            self.note.setText('SIMULATED inputs; differences are CALCULATED. Percentiles describe ensemble spread, not confidence intervals or biological validation. '
                f"A: {payload_a['config']['compound']}; B: {payload_b['config']['compound']}. Inspect each saved protocol for other input differences.")
        except Exception as exc:
            self.table.setRowCount(0)
            self.note.setText(f'Could not compare verified runs: {exc}')
