"""Inspect frozen-model evaluations without conflating eligibility and accuracy."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QPlainTextEdit
from PySide6.QtCore import Qt
import pyqtgraph as pg
from virtual_lab.validation.maturation import load_inputs,create_report,validate_report


class MaturationValidationWorkspace(QWidget):
    def __init__(self,workspace,service):
        super().__init__();self.workspace=workspace;self.service=service;self.result=None
        layout=QVBoxLayout(self)
        title=QLabel('Maturation: evaluate a frozen model on a declared acquisition');layout.addWidget(title)
        note=QLabel('No parameters are fitted here. Acquisition separation and timing are checked independently of prediction error. Metadata declarations are not authenticated evidence or a biological pass/fail.');note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();self.model_path=QLineEdit();self.dataset_path=QLineEdit()
        self.model_path.setPlaceholderText('Absolute path to frozen-model JSON')
        self.dataset_path.setPlaceholderText('Absolute dataset-manifest JSON path; its CSV must be beside it')
        form.addRow('Frozen model',self.model_path);form.addRow('Evaluation dataset',self.dataset_path);layout.addLayout(form)
        buttons=QHBoxLayout();self.evaluate_button=QPushButton('Evaluate frozen model');self.save_button=QPushButton('Save assessment to experiment')
        buttons.addWidget(self.evaluate_button);buttons.addWidget(self.save_button);layout.addLayout(buttons)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText);layout.addWidget(self.status)
        self.reasons=QPlainTextEdit();self.reasons.setReadOnly(True);self.reasons.setMaximumHeight(200);layout.addWidget(self.reasons)
        self.plot=pg.PlotWidget(background='#16202d');self.plot.addLegend();self.plot.setLabel('bottom','Hours after declared event');self.plot.setLabel('left','Fluorescence / event baseline');layout.addWidget(self.plot,1)
        self.metrics=QLabel();self.metrics.setWordWrap(True);self.metrics.setTextFormat(Qt.PlainText);layout.addWidget(self.metrics)
        self.evaluate_button.clicked.connect(self._evaluate);self.save_button.clicked.connect(self._save)
        workspace.activeExperimentChanged.connect(lambda _:self.clear());workspace.validationResultChanged.connect(self.show_result)
        self.model_path.textChanged.connect(self.clear);self.dataset_path.textChanged.connect(self.clear)
        self.clear()

    def clear(self,*_):
        self.result=None;self.save_button.setEnabled(False);self.plot.clear();self.reasons.clear();self.metrics.clear()
        self.status.setText('Open an experiment, then select a frozen model and dataset manifest. Evaluation can be saved even when eligibility fails.')

    def _evaluate(self):
        self.clear()
        try:
            exp=self.workspace.active_experiment
            if exp is None:raise ValueError('Open an experiment in Projects first.')
            model,dataset,raw=load_inputs(self.model_path.text().strip(),self.dataset_path.text().strip())
            self.show_result(create_report(model,dataset,raw,exp.id))
        except Exception as exc:self.status.setText(f'Cannot evaluate: {exc}')

    def show_result(self,payload):
        if payload is None:return self.clear()
        result=validate_report(payload);self.result=result;a=result['assessment']
        self.status.setText(a['status'].replace('_',' ')+': '+result['dataset']['title'])
        self.reasons.setPlainText('\n'.join([a['verification_scope'],*a['exclusions'],*a['alignment_errors']]))
        self.plot.clear();colors=['#00bdf2','#ffbb55','#bf8aff','#69cf8a','#f48b8b','#c8d88a']
        groups={}
        for row in a['rows']:groups.setdefault((row['acquisition_id'],row['series_id']),[]).append(row)
        for i,(key,rows) in enumerate(groups.items()):
            color=colors[i%len(colors)];self.plot.plot([r['time_h'] for r in rows],[r['observed'] for r in rows],pen=pg.mkPen(color,width=1),name=key[1])
        if a['rows']:
            curve=sorted({r['time_h']:r['predicted'] for r in a['rows']}.items())
            self.plot.plot([t for t,y in curve],[y for t,y in curve],pen=pg.mkPen('#ffffff',width=2,style=Qt.DashLine),name='Frozen prediction')
        m=a['metrics'];p=result['frozen_model']
        if m:
            r2='undefined' if m['r_squared'] is None else f"{m['r_squared']:.4f}"
            self.metrics.setText(f"Frozen rate {p['maturation_per_hour']:.6g}/h; initial immature/mature ratio {p['immature_to_initial_mature_ratio']:.6g}. "
                f"RMSE {m['rmse']:.6f}; R² {r2}; no-maturation RMSE {m['no_maturation_rmse']:.6f}. "
                f"{m['n_acquisitions']} acquisition(s), {m['n_series']} series, {m['n_points']} correlated positive-time points. Accuracy does not override eligibility.")
        else:self.metrics.setText('No metrics: an explicit measured event-time baseline is required for every series.')
        exp=self.workspace.active_experiment
        saved=bool(self.service.store._conn.execute('SELECT 1 FROM observations WHERE observation_id=?',(result['id'],)).fetchone())
        self.save_button.setEnabled(exp is not None and exp.id==result['experiment_id'] and not saved)

    def _save(self):
        try:
            self.service.save_maturation_evaluation(self.result);self.save_button.setEnabled(False)
            self.status.setText(self.status.text()+' — saved with embedded inputs; export in Projects.')
        except Exception as exc:self.status.setText(f'Cannot save assessment: {exc}')
