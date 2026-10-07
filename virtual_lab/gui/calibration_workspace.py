"""Published-data calibration: declared splits, visible residuals, portable results."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView)

from virtual_lab.calibration.decay import load_benchmark, read_measurements, fit_decay


class CalibrationWorkspace(QWidget):
    def __init__(self, workspace, study_service):
        super().__init__()
        self.workspace, self.service = workspace, study_service
        self.result = None
        layout = QVBoxLayout(self)
        self.title = QLabel('mRNA decay: fit a rate, test a held-out biological replicate')
        layout.addWidget(self.title)
        self.description = QLabel('Published benchmark: yeast PGK1 (YCR012W), GSE12221, Shalem et al. 2008. '
            'Author-normalized Supplementary Table 1: the reference curve trains; reference2 tests. '
            'Baseline points are excluded from fit/error metrics. No stress samples are included.')
        self.description.setWordWrap(True); layout.addWidget(self.description)
        self.mode = QComboBox(); self.mode.addItems(['Published PGK1 benchmark', 'Local measurement CSV'])
        layout.addWidget(QLabel('Dataset for next fit'))
        layout.addWidget(self.mode)
        self.custom = QWidget(); custom_layout = QVBoxLayout(self.custom)
        self.path = QLineEdit(); self.path.setPlaceholderText('Absolute CSV path: sample_id,replicate,split,time_min,value')
        self.context = QLineEdit(); self.context.setPlaceholderText('Gene, organism, and experimental condition (required for local data)')
        self.source = QLineEdit(); self.source.setPlaceholderText('Dataset accession, citation, or local data source (required)')
        self.scale = QComboBox(); self.scale.addItem('Select the input scale',None)
        self.scale.addItem('Linear positive intensity','linear');self.scale.addItem('Log2 intensity','log2')
        for w in (self.path,self.context,self.source,self.scale):custom_layout.addWidget(w)
        layout.addWidget(self.custom); self.custom.hide()
        self.mode.currentIndexChanged.connect(self._mode_changed)
        row = QHBoxLayout(); self.fit_button = QPushButton('Fit training replicate and evaluate holdout')
        self.save_button = QPushButton('Save calibration to active experiment'); self.save_button.setEnabled(False)
        self.objects_button = QPushButton('Create RNA-decay objects from saved fit'); self.objects_button.setEnabled(False)
        self.objects_button.clicked.connect(self._objects)
        row.addWidget(self.objects_button)
        row.addWidget(self.fit_button);row.addWidget(self.save_button);layout.addLayout(row)
        self.summary = QLabel('No fit yet. Numerical agreement and biological validation are separate checks.')
        self.summary.setWordWrap(True);layout.addWidget(self.summary)
        charts = QHBoxLayout()
        self.plot = pg.PlotWidget(background='#16202d');self.plot.setLabel('bottom','Time after shutoff',units='min')
        self.plot.setLabel('left','Abundance relative to own baseline');self.plot.addLegend()
        self.residuals = pg.PlotWidget(background='#16202d');self.residuals.setLabel('bottom','Time after shutoff',units='min')
        self.residuals.setLabel('left','Observed minus predicted');self.residuals.addLegend()
        self.residuals.getAxis('left').enableAutoSIPrefix(False)
        charts.addWidget(self.plot,2);charts.addWidget(self.residuals,1);layout.addLayout(charts,2)
        self.table = QTableWidget(0,6)
        self.table.setHorizontalHeaderLabels(['Sample','Split','Time (min)','Relative abundance','Predicted','Residual'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table,1)
        self.limits = QLabel('The model assumes first-order decay and complete transcription shutoff. '
            'Rates do not transfer automatically to proteins, drug response, humans, or other conditions.')
        self.limits.setWordWrap(True);layout.addWidget(self.limits)
        self.fit_button.clicked.connect(self._fit);self.save_button.clicked.connect(self._save)
        workspace.activeExperimentChanged.connect(lambda _:self.clear())
        workspace.calibrationResultChanged.connect(self.show_result)
        for field in (self.path,self.context,self.source):field.textChanged.connect(lambda _:self.clear())
        self.scale.currentIndexChanged.connect(lambda _:self.clear())

    def _mode_changed(self,index):
        self.custom.setVisible(index==1)
        self.clear()

    def clear(self):
        self.result=None;self.save_button.setEnabled(False);self.objects_button.setEnabled(False)
        self.description.setText('Published PGK1 reference and reference2 curves from Shalem et al. (2008), Supplementary Table 1.' if self.mode.currentIndex()==0 else 'Declare the measurement source, biological context, scale, and training/holdout split before fitting.')
        self.plot.clear();self.residuals.clear();self.table.setRowCount(0)
        self.summary.setText('No fit selected. Open an experiment, then fit measurements or select a saved calibration in Projects.')

    def _fit(self):
        self.clear()
        try:
            if self.mode.currentIndex()==0:
                metadata, rows = load_benchmark()
            else:
                path=Path(self.path.text().strip()).expanduser()
                if not path.is_absolute() or not path.is_file() or path.stat().st_size>1_000_000:
                    raise ValueError('Choose an existing absolute CSV path up to 1 MB.')
                if not self.context.text().strip() or not self.source.text().strip():
                    raise ValueError('Declare gene/organism/condition and the data source.')
                if self.scale.currentData() is None:raise ValueError('Declare the input scale.')
                raw=path.read_bytes();rows=read_measurements(raw)
                metadata=dict(dataset_id=path.name,title=self.context.text().strip(),
                    source=self.source.text().strip(),value_scale=self.scale.currentData(),
                    csv_sha256=hashlib.sha256(raw).hexdigest(),
                    limitations=['Local data identity, scale, and split are user-declared, not independently verified.'])
            exp=self.workspace.active_experiment
            result=fit_decay(rows,metadata,exp.id if exp else '')
            self.show_result(result)
        except Exception as exc:self.summary.setText(f'Cannot fit: {exc}')

    def show_result(self,result):
        if not result:return self.clear()
        self.result=result
        self.description.setText(result['dataset'].get('citation',result['dataset'].get('source','Local dataset'))
            +' | Input scale: '+result['dataset']['value_scale']+'. '+result.get('normalization',''))
        self.plot.clear();self.residuals.clear()
        curve=result['curve'];self.plot.plot(curve['time_min'],curve['relative_abundance'],pen=pg.mkPen('#00bdf2',width=2),name='Fitted model')
        self.residuals.addLine(y=0,pen=pg.mkPen('#aaaaaa',style=Qt.DashLine))
        for split,color,symbol in [('train','#00bdf2','o'),('holdout','#ffbb55','t')]:
            rows=[r for r in result['measurements'] if r['split']==split]
            self.plot.plot([r['time_min'] for r in rows],[r['relative_abundance'] for r in rows],pen=None,symbol=symbol,symbolBrush=color,name=split)
            positive=[r for r in rows if r['time_min']>0]
            self.residuals.plot([r['time_min'] for r in positive],[r['residual'] for r in positive],pen=None,symbol=symbol,symbolBrush=color,name=split)
        rows=result['measurements'];self.table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            values=[r['sample_id'],r['split'],f"{r['time_min']:g}",f"{r['relative_abundance']:.4f}",f"{r['predicted_abundance']:.4f}",f"{r['residual']:.4f}"]
            for j,value in enumerate(values):self.table.setItem(i,j,QTableWidgetItem(value))
        p=result['parameters'];m=result['metrics'];half='unbounded' if p['half_life_min'] is None else f"{p['half_life_min']:.2f} min"
        r2=m['holdout']['r_squared'];r2_text='undefined' if r2 is None else f'{r2:.3f}'
        self.summary.setText(f"{result['dataset']['title']} | INFERRED decay rate {p['decay_per_hour']:.4f}/h; half-life {half}. "
            f"Training RMSE {m['train']['rmse']:.4f} (n={m['train']['n']}); holdout RMSE {m['holdout']['rmse']:.4f} (n={m['holdout']['n']}); "
            f"no-decay holdout baseline RMSE {m['holdout']['no_decay_rmse']:.4f}. "
            f"Holdout R² {r2_text}. "
            f"{result['validation_status'].replace('_', ' ').capitalize()}; no biological pass/fail threshold.")
        self.limits.setText(result['validation_scope']+' '+ ' '.join(result['limitations']))
        exp=self.workspace.active_experiment
        active = exp is not None and exp.id==result['experiment_id']
        saved = bool(self.service.store._conn.execute('SELECT 1 FROM observations WHERE observation_id=?',(result['id'],)).fetchone())
        self.save_button.setEnabled(active and not saved)
        self.objects_button.setEnabled(active and saved)

    def _save(self):
        try:
            self.service.save_calibration(self.result)
            self.save_button.setEnabled(False);self.objects_button.setEnabled(True)
            self.summary.setText(self.summary.text()+' Saved to the active experiment; export it in Projects.')
        except Exception as exc:self.summary.setText(f'Cannot save: {exc}')

    def _objects(self):
        try:
            exp = self.workspace.active_experiment
            if self.result is None or exp is None or self.result['experiment_id'] != exp.id:
                raise ValueError('Select a saved calibration in the active experiment.')
            obs = next((o for o in self.service.store.get_observations_for_experiment(exp.id)
                        if o.observation_id == self.result['id'] and o.instrument_id == 'decay_calibration'), None)
            if obs is None:
                raise ValueError('Save this calibration first.')
            # Reload the artifact and verify its hash before creating the draft.
            from virtual_lab.biology.calibration_bridge import system_from_calibration
            system = system_from_calibration(self.service.inspect(obs))
            self.workspace.biologicalDraftRequested.emit(system.model_dump(mode='json'))
        except Exception as exc:
            self.summary.setText(f'Cannot create biological objects: {exc}')
