"""Object-based gene → RNA → protein experiments, with explicit assumptions."""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QCheckBox, QLineEdit, QPushButton, QDoubleSpinBox, QButtonGroup, QRadioButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QSplitter)
from PySide6.QtCore import Qt
import pyqtgraph as pg

from virtual_lab.biology.objects import starter_system, Intervention, BiologicalSystem
from virtual_lab.domain.epistemics import EpistemicState
from virtual_lab.biology.simulation import BiologicalRun, simulate
from virtual_lab.biology.mechanisms import get_mechanism


def number(value, low=0., high=100., decimals=3):
    box=QDoubleSpinBox();box.setRange(low,high);box.setDecimals(decimals);box.setValue(value)
    return box


class InterventionChoice(QWidget):
    def __init__(self):
        super().__init__()
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0)
        self.group=QButtonGroup(self)
        for i,label in enumerate(('None','Transcription','Translation')):
            button=QRadioButton(label);self.group.addButton(button,i);row.addWidget(button)
        self.group.button(0).setChecked(True)

    def currentData(self):
        return (None,'transcription','translation')[self.group.checkedId()]

    def setCurrentIndex(self,index):
        self.group.button(index).setChecked(True)


class BiologicalWorkspace(QWidget):
    def __init__(self, workspace, service):
        super().__init__()
        self.workspace,self.service=workspace,service
        self.system=None;self.result=None;self.bound_experiment=None
        layout=QVBoxLayout(self)
        title=QLabel('Biological objects: gene → RNA → protein');layout.addWidget(title)
        self.scope=QLabel('An illustrative system with explicit rates. Identity stays stable as RNA and protein evolve. '
            'Gene names and sequences do not supply kinetics. RNA and protein use separate normalized units; genes use copies. No biological validation is established.')
        self.scope.setWordWrap(True);layout.addWidget(self.scope)
        self.inputs=QGroupBox('New system identity and assumptions');form=QHBoxLayout(self.inputs)
        identity=QFormLayout();rates=QFormLayout()
        for group in (identity,rates):
            group.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            group.setLabelAlignment(Qt.AlignLeft)
            group.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.name=QLineEdit('Expression system');self.gene=QLineEdit('Example gene')
        self.organism=QLineEdit('Unspecified organism');self.context=QLineEdit('Illustrative conditions')
        for label,field in [('System name',self.name),('Gene label',self.gene),('Organism',self.organism),('Conditions',self.context)]:
            identity.addRow(label,field)
        self.maturation_enabled=QCheckBox('Include immature → mature protein');identity.addRow(self.maturation_enabled)
        self.initial_immature=number(0,high=1e12)
        identity.addRow('Initial immature protein',self.initial_immature)
        self.initial_rna=number(0,high=1e12);self.initial_protein=number(0,high=1e12)
        identity.addRow('Initial RNA (normalized)',self.initial_rna);identity.addRow('Initial protein (normalized)',self.initial_protein)
        spec=get_mechanism('linear_gene_expression','1.0.0');self.parameters={}
        labels={'transcription':'Transcription / gene copy / h','translation':'Translation / RNA / h',
                'rna_decay':'RNA decay / h','protein_decay':'Protein decay / h'}
        for key,value in spec.defaults.items():
            self.parameters[key]=number(value);rates.addRow(labels[key],self.parameters[key])
        self.parameters['maturation']=number(1.);rates.addRow('Maturation / h',self.parameters['maturation'])
        self.maturation_enabled.toggled.connect(self._maturation_changed)
        self._maturation_changed(False)
        note=QLabel('New drafts use MODEL_ASSUMPTION inputs.\nActive state evidence is shown below. One fixed gene copy.');note.setWordWrap(True)
        rates.addRow(note);form.addLayout(identity,3);form.addLayout(rates,2);layout.addWidget(self.inputs)
        controls=QHBoxLayout();self.create_button=QPushButton('Create new biological system')
        self.create_button.clicked.connect(self._create);controls.addWidget(self.create_button)
        self.run_button=QPushButton('Run next interval');self.run_button.clicked.connect(self._run);controls.addWidget(self.run_button)
        self.save_button=QPushButton('Save result and object states');self.save_button.clicked.connect(self._save);controls.addWidget(self.save_button)
        layout.addLayout(controls)
        schedule=QHBoxLayout();self.duration=number(4,.01,168)
        self.target=InterventionChoice()
        self.event_time=number(2,0,168);self.multiplier=number(0,0,10)
        for label,widget in [('Duration (h)',self.duration),('Intervention',self.target),('Hours into interval',self.event_time),('Activity multiplier',self.multiplier)]:
            schedule.addWidget(QLabel(label));schedule.addWidget(widget)
        layout.addLayout(schedule)
        self.status=QLabel('Open an experiment in Projects, then create a biological system.');self.status.setWordWrap(True);layout.addWidget(self.status)
        split=QSplitter(Qt.Horizontal)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Object','Kind','Abundance','Evidence','Persistent ID'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setWordWrap(False)
        split.addWidget(self.table)
        self.plot=pg.PlotWidget(background='#16202d');self.plot.addLegend()
        self.plot.setLabel('bottom','System time',units='h');self.plot.setLabel('left','Normalized abundance')
        split.addWidget(self.plot);split.setSizes([650,650]);layout.addWidget(split,2)
        self.history=QLabel('No interventions.');self.history.setWordWrap(True);layout.addWidget(self.history)
        self.mechanism=QLabel('Mechanism: transcription, translation, and first-order RNA/protein turnover.');self.mechanism.setWordWrap(True);layout.addWidget(self.mechanism)
        workspace.activeExperimentChanged.connect(lambda _:self.clear())
        workspace.biologicalResultChanged.connect(self.show_result)
        workspace.biologicalDraftRequested.connect(self.show_draft)
        for label in (self.status,self.history,self.mechanism):label.setTextFormat(Qt.PlainText)
        self.clear()

    def clear(self):
        self.system=None;self.result=None;self.bound_experiment=None
        self.inputs.setEnabled(True);self.inputs.setTitle('New system identity and assumptions')
        self.create_button.setEnabled(True);self.create_button.setText('Create new biological system')
        self.table.setRowCount(0);self.plot.clear();self.run_button.setEnabled(False);self.save_button.setEnabled(False)
        self.status.setText('Open an experiment in Projects, then create a biological system.')
        self.history.setText('No interventions.');self.mechanism.setText('No system selected.')

    def _create(self):
        # The button first unlocks a new draft; it never edits a saved identity in place.
        if self.system is not None:
            self.clear();return
        try:
            exp=self.workspace.active_experiment
            if exp is None:raise ValueError('Open an experiment in Projects first.')
            system=starter_system(name=self.name.text().strip(),gene_label=self.gene.text().strip(),
                organism=self.organism.text().strip(),context=self.context.text().strip(),
                parameters={k:w.value() for k,w in self.parameters.items() if k != 'maturation' or self.maturation_enabled.isChecked()},
                model_id='maturing_gene_expression' if self.maturation_enabled.isChecked() else 'linear_gene_expression',
                initial_immature_protein=self.initial_immature.value(),
                initial_rna=self.initial_rna.value(),initial_protein=self.initial_protein.value())
            self.bound_experiment=exp.id;self.system=system;self.result=None
            self.inputs.setEnabled(False);self.inputs.setTitle('Selected system (read-only)');self.create_button.setText('Start a separate new system')
            self.run_button.setEnabled(True);self.save_button.setEnabled(False);self._display_system()
            self.status.setText('Draft created with stable object IDs. Run and save to persist the system. All initial values are assumptions.')
        except Exception as exc:self.status.setText(f'Cannot create system: {exc}')

    def _display_system(self):
        self.table.setRowCount(len(self.system.objects))
        for i,obj in enumerate(self.system.objects):
            for j,text in enumerate([obj.identity.label,obj.kind,f'{obj.state.abundance:.5g}',('Assumed' if obj.state.evidence.state==EpistemicState.MODEL_ASSUMPTION else obj.state.evidence.state.value.title()),obj.id[:8]]):
                item=QTableWidgetItem(text);item.setToolTip(obj.state.units+'\n'+obj.id+'\n'+obj.state.evidence.state.value+'\n'+obj.state.evidence.source+'\n'+obj.state.evidence.scope)
                self.table.setItem(i,j,item)
        params='; '.join(f'{k}={r.value:g} {r.units} ({r.evidence.state.value})' for k,r in self.system.mechanism.parameters.items())
        self.mechanism.setText(f'{self.system.mechanism.model_id} v{self.system.mechanism.version}. '+params)
        if self.system.calibration_result is not None:
            fit=self.system.calibration_result
            self.mechanism.setText(self.mechanism.text()+f" | RNA-only fit {fit['id'][:8]}; holdout RMSE {fit['metrics']['holdout']['rmse']:.4g}. Protein behavior is not calibrated.")
        self.mechanism.setToolTip(self.system.mechanism.scope+'\n'+'\n'.join(k+': '+r.evidence.source+' — '+r.evidence.scope for k,r in self.system.mechanism.parameters.items()))
        history=[f't={e.time_h:g} h: {e.target} activity set to {e.multiplier:g}×' for e in self.system.history]
        self.history.setText('History: '+(' · '.join(history[-8:]) if history else 'No interventions.')+
            f' Current activity: transcription {self.system.transcription_multiplier:g}×, translation {self.system.translation_multiplier:g}×.'+
            (f' Showing last 8 of {len(history)} events; all events are saved.' if len(history)>8 else ''))

    def _run(self):
        try:
            exp=self.workspace.active_experiment
            if self.system is None or exp is None or exp.id != self.bound_experiment:
                raise ValueError('Create or restore a system in the active experiment.')
            if self.result is not None and self.save_button.isEnabled():
                raise ValueError('Save the current result before continuing its history.')
            events=[]
            if self.target.currentData():
                events=[Intervention(time_h=self.system.time_h+self.event_time.value(),target=self.target.currentData(),
                    multiplier=self.multiplier.value(),rationale='User-specified experimental intervention')]
            result=simulate(self.system,self.duration.value(),events,exp.id)
            self.show_result(result.model_dump(mode='json'))
        except Exception as exc:self.status.setText(f'Cannot run: {exc}')

    def show_result(self,payload):
        if payload is None:return self.clear()
        result=BiologicalRun.model_validate(payload)
        self.result=result;self.system=result.final_system;self.bound_experiment=result.experiment_id
        self.inputs.setEnabled(False);self.inputs.setTitle('Selected system (read-only)');self.create_button.setText('Start a separate new system')
        self.name.setText(self.system.name);self.context.setText(self.system.context)
        gene=next(o for o in self.system.objects if o.kind=='gene')
        self.gene.setText(gene.identity.label);self.organism.setText(gene.identity.organism)
        self.maturation_enabled.setChecked(self.system.mechanism.model_id=='maturing_gene_expression')
        self.initial_immature.setValue(next((o.state.abundance for o in result.initial_system.objects if o.kind=='immature_protein'),0.))
        for key,rate in self.system.mechanism.parameters.items():self.parameters[key].setValue(rate.value)
        for kind,field in [('rna',self.initial_rna),('protein',self.initial_protein)]:
            field.setValue(next(o.state.abundance for o in result.initial_system.objects if o.kind==kind))
        self.plot.clear();self.plot.plot(result.time_h,result.rna,pen=pg.mkPen('#00bdf2',width=2),name='RNA')
        self.plot.plot(result.time_h,result.protein,pen=pg.mkPen('#ffbb55',width=2),name='Mature protein' if result.immature_protein is not None else 'Protein')
        if result.immature_protein is not None:
            self.plot.plot(result.time_h,result.immature_protein,pen=pg.mkPen('#bf8aff',width=2),name='Immature protein')
        for event in result.interventions:self.plot.addLine(x=event.time_h,pen=pg.mkPen('#aaaaaa',style=Qt.DashLine))
        self._display_system()
        exp=self.workspace.active_experiment;active=exp is not None and exp.id==result.experiment_id
        saved=bool(self.service.store._conn.execute('SELECT 1 FROM observations WHERE observation_id=?',(result.id,)).fetchone())
        self.save_button.setEnabled(active and not saved);self.run_button.setEnabled(active and saved)
        self.create_button.setEnabled(saved or not active)
        self.status.setText(f'SIMULATED: {self.system.name}, revision {self.system.revision}, time {self.system.time_h:g} h. '
            +('Saved result restored. Continue from these states or start a separate system.' if saved else 'Save to persist the object states and intervention history.'))

    def _save(self):
        try:
            self.service.save_biological_run(self.result.model_dump(mode='json'))
            self.save_button.setEnabled(False);self.run_button.setEnabled(True);self.create_button.setEnabled(True)
            self.status.setText('Saved biological objects, mechanism, trajectory, and history. Export the study in Projects, or run the next interval.')
        except Exception as exc:self.status.setText(f'Cannot save: {exc}')

    def _maturation_changed(self, enabled):
        self.initial_immature.setEnabled(enabled)
        self.parameters['maturation'].setEnabled(enabled)

    def show_draft(self, payload):
        try:
            if self.result is not None and self.save_button.isEnabled():
                raise ValueError('Save the current biological run before opening a calibrated draft.')
            system=BiologicalSystem.model_validate(payload)
            exp=self.workspace.active_experiment
            if exp is None or system.calibration_result is None or system.calibration_result['experiment_id'] != exp.id:
                raise ValueError('The calibrated draft requires its source experiment.')
            self.clear();self.system=system;self.bound_experiment=exp.id
            self.name.setText(system.name);self.context.setText(system.context)
            gene=next(o for o in system.objects if o.kind=='gene')
            self.gene.setText(gene.identity.label);self.organism.setText(gene.identity.organism)
            self.maturation_enabled.setChecked(False);self.initial_immature.setValue(0.)
            self.initial_rna.setValue(1.);self.initial_protein.setValue(0.)
            for key,rate in system.mechanism.parameters.items():self.parameters[key].setValue(rate.value)
            self.inputs.setEnabled(False);self.inputs.setTitle('Calibrated RNA-only probe (read-only)')
            self.create_button.setText('Start a separate new system');self.run_button.setEnabled(True)
            self.target.setCurrentIndex(0)
            self.duration.setValue(max(r['time_min'] for r in system.calibration_result['measurements'])/60)
            self._display_system()
            self.status.setText('Draft from saved calibration. RNA decay is INFERRED; protein and production are disabled. Run and save to persist. Same-study holdout evaluation is not independent validation.')
        except Exception as exc:
            self.status.setText(f'Cannot open calibrated draft: {exc}')
