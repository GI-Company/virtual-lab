from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QGroupBox,QComboBox,
    QSpinBox,QDoubleSpinBox,QPushButton,QSlider,QLabel,QProgressBar,QLineEdit,QFrame)
from PySide6.QtCore import Qt, Signal
from virtual_lab.gui.services.experiment_controller import ExperimentController

class ExperimentWorkspace(QWidget):
    navigateRequested = Signal(str)

    def __init__(self,workspace,parent=None):
        super().__init__(parent)
        self.workspace=workspace
        self.controller=ExperimentController(workspace)
        layout=QVBoxLayout(self)
        from virtual_lab.models.registry import models
        self.model_selector=QComboBox()
        for spec in models(): self.model_selector.addItem(spec.label, spec.id)
        model_row=QFormLayout();model_row.addRow("Simulation model",self.model_selector);layout.addLayout(model_row)
        self.model_import_path=QLineEdit()
        self.model_import_path.setPlaceholderText('Absolute path to a vlab-ode-v1 JSON manifest')
        self.model_import_button=QPushButton('Import equation model JSON')
        self.model_import_button.clicked.connect(self._import_model)
        import_row=QHBoxLayout();import_row.addWidget(self.model_import_path);import_row.addWidget(self.model_import_button)
        layout.addLayout(import_row)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        self.config_group=QGroupBox("Experiment design");self.config_group.setObjectName("experimentDesign")
        form=QFormLayout(self.config_group)
        self.compound=QLineEdit("Exploratory scenario");self.compound.setAccessibleName("Scenario label");self.compound.setObjectName("scenarioLabel");form.addRow("Scenario label",self.compound)
        self.fields={}
        for key,label,lo,hi,value,dec in [
            ("concentration_um","Exposure (µM)",0,100,1,2),
            ("duration_h","Duration (h)",1,48,48,1),
            ("variation","Assumed lognormal spread",0,.5,.1,2)]:
            spin=QDoubleSpinBox();spin.setDecimals(dec);spin.setRange(lo,hi);spin.setValue(value)
            spin.setObjectName("design-"+key);spin.setAccessibleName(label)
            self.fields[key]=spin;form.addRow(label,spin)
        self.spn_ensemble=QSpinBox();self.spn_ensemble.setRange(1,10000);self.spn_ensemble.setValue(128)
        self.seed=QSpinBox();self.seed.setRange(0,2147483647);self.seed.setValue(42)
        form.addRow("Uncertainty realizations",self.spn_ensemble);form.addRow("Random seed",self.seed)
        self.cmb_backend=QComboBox();self.cmb_backend.addItem("NumPy CPU • float64","numpy")
        import importlib.util
        if importlib.util.find_spec("mlx"): self.cmb_backend.addItem("MLX / Metal • float32","mlx")
        form.addRow("Execution backend",self.cmb_backend);layout.addWidget(self.config_group)
        self.model_group=QGroupBox('Model assumptions');self.model_group.setObjectName('modelAssumptions')
        self.model_form=QFormLayout(self.model_group)
        self.model_fields={}
        layout.addWidget(self.model_group)
        self.model_selector.currentIndexChanged.connect(self._model_changed)
        self._model_changed()
        buttons=QHBoxLayout()
        self.btn_run=QPushButton("Run paired experiment");self.btn_run.setObjectName("primary")
        self.btn_cancel=QPushButton("Cancel");self.btn_cancel.setEnabled(False)
        self.btn_open_analysis=QPushButton("Analyze Trajectories")
        self.btn_open_analysis.setEnabled(False)
        self.btn_open_analysis.clicked.connect(lambda: self.navigateRequested.emit("Analysis"))
        self.btn_open_numerical=QPushButton("Verify Numerical Certificate")
        self.btn_open_numerical.setEnabled(False)
        self.btn_open_numerical.clicked.connect(lambda: self.navigateRequested.emit("Numerical"))
        self.btn_open_compare=QPushButton("Compare Results")
        self.btn_open_compare.setEnabled(False)
        self.btn_open_compare.clicked.connect(lambda: self.navigateRequested.emit("Compare"))
        for b in (self.btn_run, self.btn_cancel, self.btn_open_analysis, self.btn_open_numerical, self.btn_open_compare):
            buttons.addWidget(b)
        layout.addLayout(buttons)
        self.progress=QProgressBar();layout.addWidget(self.progress)
        self.status=QLabel("Ready. No numerical check has been performed.");self.status.setWordWrap(True);layout.addWidget(self.status)
        self.next_hint=self.status
        timeline=QHBoxLayout();self.slider=QSlider(Qt.Horizontal);self.slider.setRange(0,48)
        self.lbl_time=QLabel("0.0 h");timeline.addWidget(self.slider);timeline.addWidget(self.lbl_time);layout.addLayout(timeline)
        self.slider.valueChanged.connect(lambda v:setattr(workspace,"simulation_time_h",float(v)))
        workspace.simulationTimeChanged.connect(self._sync_timeline)
        workspace.activeExperimentChanged.connect(self._refresh_next_steps)
        workspace.observationCommitted.connect(self._refresh_next_steps)
        workspace.observationStaged.connect(self._refresh_next_steps)
        self.btn_run.clicked.connect(self._run);self.btn_cancel.clicked.connect(self.controller.cancel)
        self.controller.runStarted.connect(lambda:self._busy(True))
        self.controller.runProgress.connect(self._sync_progress)
        self.controller.runFinished.connect(self._finished)
        self.controller.runFailed.connect(lambda message:self._stop("Failed: "+message))
        self.controller.runCancelled.connect(lambda:self._stop("Cancelled. No result was saved."))
        layout.addStretch()
        self._refresh_next_steps()
    def _import_model(self):
        try:
            from virtual_lab.extensions.models import import_ode
            from virtual_lab.core.paths import app_data_dir
            spec=import_ode(self.model_import_path.text().strip(), app_data_dir() / 'model-snapshots')
            self.model_selector.addItem(spec.label, spec.id)
            self.model_selector.setCurrentIndex(self.model_selector.findData(spec.id))
            self.status.setText('Imported data-only model. Review its assumptions and units before running.')
        except Exception as error:
            self.status.setText('Model import failed: ' + str(error))

    def _model_changed(self, *_):
        from virtual_lab.models.registry import get_model
        spec=get_model(self.model_selector.currentData())
        self.note.setText(spec.description + '\nPaired zero-exposure control uses identical parameter draws. ' + ' '.join(spec.limitations))
        while self.model_form.rowCount(): self.model_form.removeRow(0)
        self.model_fields={}
        for parameter in spec.parameters:
            spin=QDoubleSpinBox();spin.setDecimals(3)
            spin.setRange(parameter.minimum,parameter.maximum);spin.setValue(parameter.default)
            spin.setObjectName("assumption-"+parameter.key)
            spin.setAccessibleName(f"{parameter.label} ({parameter.units})")
            self.model_fields[parameter.key]=spin
            self.model_form.addRow(f'{parameter.label} ({parameter.units})',spin)
        self.cmb_backend.clear()
        for backend in spec.backends:
            if backend == 'numpy': self.cmb_backend.addItem('NumPy CPU • float64', backend)
            elif backend == 'mlx':
                import importlib.util
                if importlib.util.find_spec('mlx'): self.cmb_backend.addItem('MLX / Metal • float32', backend)
        from virtual_lab.gui.shell.layout import _prepare_controls
        _prepare_controls(self.model_group)

    def _sync_timeline(self,value):
        self.slider.blockSignals(True);self.slider.setValue(round(value));self.slider.blockSignals(False)
        self.lbl_time.setText(f"{value:.1f} h")
    def _sync_progress(self, percent):
        self.progress.setValue(percent)
        duration = self.fields["duration_h"].value()
        sim_h = duration * (percent / 100.0)
        self.status.setText(f"Simulating: {sim_h:.1f} / {duration:.1f} h (Progress: {percent}%)")

    def _busy(self,busy):
        self.model_selector.setEnabled(not busy);self.model_group.setEnabled(not busy)
        self.btn_run.setEnabled(not busy);self.config_group.setEnabled(not busy);self.btn_cancel.setEnabled(busy)
        from virtual_lab.edition import current_edition
        if current_edition() == 'high-school':
            self.model_selector.setEnabled(False);self.model_group.setEnabled(False)
        self.model_import_button.setEnabled(not busy and current_edition() != 'high-school')
        if busy:self.progress.setValue(0);self.status.setText("Integrating treatment and paired vehicle…")
    def _stop(self,message):self._busy(False);self.status.setText(message)
    def _finished(self,result):
        self._stop(f"Saved {result.run_id[:8]} • {result.execution_metadata['runtime_seconds']:.2f} s • numerical subset check {result.numerical_check['status']}. See Analysis and Compare.")
        self._refresh_next_steps()

    def _refresh_next_steps(self, *_):
        has_current = self.workspace.current_result is not None
        sim_count = 0
        try:
            from virtual_lab.domain.experiment_store import ExperimentStore
            store = ExperimentStore()
            try:
                exp = self.workspace.active_experiment
                if exp:
                    sim_count = sum(
                        1 for o in store.get_observations_for_experiment(exp.id) if o.instrument_id == "simulation"
                    )
                else:
                    sim_count = sum(
                        1
                        for e in store.list_experiments()
                        for o in store.get_observations_for_experiment(e["id"])
                        if o.instrument_id == "simulation"
                    )
            finally:
                store.close()
        except Exception:
            pass
        self.btn_open_analysis.setEnabled(has_current or sim_count >= 1)
        self.btn_open_numerical.setEnabled(has_current or sim_count >= 1)
        self.btn_open_compare.setEnabled(sim_count >= 2)
        self.btn_open_compare.setObjectName("primary" if sim_count >= 2 else "")
        self.btn_open_compare.style().unpolish(self.btn_open_compare)
        self.btn_open_compare.style().polish(self.btn_open_compare)
    def _run(self):
        config={k:v.value() for k,v in self.fields.items()}
        config.update(compound=self.compound.text(),members=self.spn_ensemble.value(),seed=self.seed.value(),backend=self.cmb_backend.currentData())
        config.update(model_id=self.model_selector.currentData(),model_parameters={k:v.value() for k,v in self.model_fields.items()})
        self.controller.run_experiment(config)
