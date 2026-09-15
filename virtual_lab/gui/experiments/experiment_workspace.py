from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QGroupBox,QComboBox,
    QSpinBox,QDoubleSpinBox,QPushButton,QSlider,QLabel,QProgressBar,QLineEdit)
from PySide6.QtCore import Qt
from virtual_lab.gui.services.experiment_controller import ExperimentController

class ExperimentWorkspace(QWidget):
    def __init__(self,workspace,parent=None):
        super().__init__(parent)
        self.workspace=workspace
        self.controller=ExperimentController(workspace)
        layout=QVBoxLayout(self)
        note=QLabel("Computational experiment • RHO P23H ODE • assumed parameter uncertainty\nPaired vehicle control uses identical parameter draws. Results are model states, not human efficacy.")
        note.setWordWrap(True);layout.addWidget(note)
        self.config_group=QGroupBox("Experiment design")
        form=QFormLayout(self.config_group)
        self.compound=QLineEdit("YC-001 hypothesis");form.addRow("Compound / design label",self.compound)
        self.fields={}
        for key,label,lo,hi,value,dec in [
            ("concentration_um","Exposure (µM)",0,100,1,2),
            ("duration_h","Duration (h)",1,48,48,1),
            ("variation","Assumed lognormal spread",0,.5,.1,2),
            ("ec50_um","Assumed EC50 (µM)",.01,100,1.5,2),
            ("rescue_max","Assumed maximum rescue (1/h)",0,2,.8,2),
            ("erad_multiplier","ERAD rate multiplier",.1,3,1,2),
            ("traffic_multiplier","Trafficking rate multiplier",.1,3,1,2)]:
            spin=QDoubleSpinBox();spin.setDecimals(dec);spin.setRange(lo,hi);spin.setValue(value)
            self.fields[key]=spin;form.addRow(label,spin)
        self.spn_ensemble=QSpinBox();self.spn_ensemble.setRange(1,10000);self.spn_ensemble.setValue(128)
        self.seed=QSpinBox();self.seed.setRange(0,2147483647);self.seed.setValue(42)
        form.addRow("Uncertainty realizations",self.spn_ensemble);form.addRow("Random seed",self.seed)
        self.cmb_backend=QComboBox();self.cmb_backend.addItem("NumPy CPU • float64","numpy")
        import importlib.util
        if importlib.util.find_spec("mlx"): self.cmb_backend.addItem("MLX / Metal • float32","mlx")
        form.addRow("Execution backend",self.cmb_backend);layout.addWidget(self.config_group)
        buttons=QHBoxLayout()
        self.btn_run=QPushButton("Run paired experiment");self.btn_run.setObjectName("primary")
        self.btn_cancel=QPushButton("Cancel");self.btn_cancel.setEnabled(False)
        buttons.addWidget(self.btn_run);buttons.addWidget(self.btn_cancel);layout.addLayout(buttons)
        self.progress=QProgressBar();layout.addWidget(self.progress)
        self.status=QLabel("Ready. No numerical check has been performed.");self.status.setWordWrap(True);layout.addWidget(self.status)
        timeline=QHBoxLayout();self.slider=QSlider(Qt.Horizontal);self.slider.setRange(0,48)
        self.lbl_time=QLabel("0.0 h");timeline.addWidget(self.slider);timeline.addWidget(self.lbl_time);layout.addLayout(timeline)
        self.slider.valueChanged.connect(lambda v:setattr(workspace,"simulation_time_h",float(v)))
        workspace.simulationTimeChanged.connect(self._sync_timeline)
        self.btn_run.clicked.connect(self._run);self.btn_cancel.clicked.connect(self.controller.cancel)
        self.controller.runStarted.connect(lambda:self._busy(True))
        self.controller.runProgress.connect(self._sync_progress)
        self.controller.runFinished.connect(self._finished)
        self.controller.runFailed.connect(lambda message:self._stop("Failed: "+message))
        self.controller.runCancelled.connect(lambda:self._stop("Cancelled. No result was saved."))
        layout.addStretch()
    def _sync_timeline(self,value):
        self.slider.blockSignals(True);self.slider.setValue(round(value));self.slider.blockSignals(False)
        self.lbl_time.setText(f"{value:.1f} h")
    def _sync_progress(self, percent):
        self.progress.setValue(percent)
        duration = self.fields["duration_h"].value()
        sim_h = duration * (percent / 100.0)
        self.status.setText(f"Simulating: {sim_h:.1f} / {duration:.1f} h (Progress: {percent}%)")

    def _busy(self,busy):
        self.btn_run.setEnabled(not busy);self.config_group.setEnabled(not busy);self.btn_cancel.setEnabled(busy)
        if busy:self.progress.setValue(0);self.status.setText("Integrating treatment and paired vehicle…")
    def _stop(self,message):self._busy(False);self.status.setText(message)
    def _finished(self,result):
        self._stop(f"Saved {result.run_id[:8]} • {result.execution_metadata['runtime_seconds']:.2f} s • numerical subset check {result.numerical_check['status']}. See Analysis and Compare.")
    def _run(self):
        config={k:v.value() for k,v in self.fields.items()}
        config.update(compound=self.compound.text(),members=self.spn_ensemble.value(),seed=self.seed.value(),backend=self.cmb_backend.currentData())
        self.controller.run_experiment(config)
