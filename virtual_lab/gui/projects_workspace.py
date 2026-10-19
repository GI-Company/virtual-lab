"""Research project creation, result inspection, and portable study exchange."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QSplitter, QInputDialog, QTabWidget, QScrollArea, QLayout)

from virtual_lab.gui.services.study_service import StudyService
from virtual_lab.gui.services.simulation_result import SimulationResult


class StudyPathEdit(QLineEdit):
    """Local paths or Finder drops without the macOS Qt file-picker AX crash."""
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setPlaceholderText('Paste a full .vlab-study path, or drag a study file here')
        self.setAccessibleName('Study package path')

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            self.setText(urls[0].toLocalFile())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class ProjectsWorkspace(QWidget):
    navigateRequested = Signal(str)
    def __init__(self, workspace, ledger, parent=None, store=None):
        super().__init__(parent)
        self.workspace = workspace
        self.service = StudyService(workspace, ledger, store)
        outer = QVBoxLayout(self)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setWidget(content)
        outer.addWidget(self.content_scroll)
        title = QLabel('Projects and experiments')
        layout.addWidget(title)
        self.workflow_status = QLabel()
        self.workflow_status.setWordWrap(True)
        layout.addWidget(self.workflow_status)
        navigation = QHBoxLayout()
        for name in ('Simulation', 'Analysis', 'Compare'):
            button = QPushButton('Open ' + name)
            button.clicked.connect(lambda checked=False, target=name: self.navigateRequested.emit(target))
            navigation.addWidget(button)
        layout.addLayout(navigation)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText('e.g. Hemoglobin reference research')
        new_project = QPushButton('Create project')
        new_project.clicked.connect(lambda: self._action(self._create_project))
        row = QHBoxLayout(); row.addWidget(self.project_name); row.addWidget(new_project)
        form.addRow('New project', row)
        self.projects = QComboBox()
        self.projects.currentIndexChanged.connect(self._refresh_experiments)
        form.addRow('Project', self.projects)
        self.experiment_name = QLineEdit()
        self.question = QLineEdit()
        form.addRow('New experiment name', self.experiment_name)
        form.addRow('Research question', self.question)
        create = QPushButton('Create and open experiment')
        create.clicked.connect(lambda: self._action(self._create_experiment))
        form.addRow(create)
        self.experiments = QComboBox()
        form.addRow('Saved experiment', self.experiments)
        open_button = QPushButton('Open experiment')
        open_button.clicked.connect(lambda: self._action(lambda: self.service.activate(self.experiments.currentData())))
        form.addRow(open_button)
        edit_question = QPushButton("Edit active research question")
        edit_question.clicked.connect(self._edit_question)
        form.addRow(edit_question)
        self.setup_widget = QWidget()
        self.setup_widget.setLayout(form)
        self.setup_toggle = QPushButton('Project and experiment setup')
        self.setup_toggle.setCheckable(True)
        self.setup_toggle.setChecked(True)
        self.setup_toggle.toggled.connect(self.setup_widget.setVisible)
        layout.addWidget(self.setup_toggle)
        layout.addWidget(self.setup_widget)
        for kind in (QLineEdit, QComboBox, QPushButton):
            for editor in self.setup_widget.findChildren(kind):
                editor.setMinimumHeight(30)
        self.active = QLabel('No active experiment. New results enter staging.')
        self.active.setTextFormat(Qt.PlainText)
        self.active.setWordWrap(True); layout.addWidget(self.active)
        split = QSplitter()
        left = QWidget(); left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel('Results attached to the active experiment'))
        self.results = QListWidget(); left_layout.addWidget(self.results)
        self.results.currentItemChanged.connect(self._inspect)
        left_layout.addWidget(QLabel('Unassigned results'))
        self.staging = QListWidget(); left_layout.addWidget(self.staging)
        attach = QPushButton('Attach selected result to active experiment')
        attach.clicked.connect(lambda: self._action(self._attach)); left_layout.addWidget(attach)
        split.addWidget(left)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True)
        self.details.setPlaceholderText('Select a result to verify its files and inspect its protocol and output.')
        self._build_notebook()
        split.addWidget(self.notebook); split.setSizes([450, 750]); layout.addWidget(split, 1)
        csv_row = QHBoxLayout()
        self.csv_path = QLineEdit(); self.csv_path.setPlaceholderText('Absolute path for a new trajectory .csv file')
        self.csv_export_button = QPushButton('Export selected simulation CSV')
        self.csv_export_button.clicked.connect(lambda: self._action(self._export_csv, 'Verified simulation trajectories exported as CSV.'))
        csv_row.addWidget(self.csv_path); csv_row.addWidget(self.csv_export_button); layout.addLayout(csv_row)
        package_row = QFormLayout()
        self.package_path = StudyPathEdit()
        package_row.addRow('Study package path', self.package_path)
        package_row.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addLayout(package_row)
        buttons = QHBoxLayout()
        export = QPushButton('Export study package')
        export.clicked.connect(self._export)
        import_button = QPushButton('Import study package')
        import_button.clicked.connect(self._import)
        unselect = QPushButton('Return to unassigned staging')
        unselect.clicked.connect(lambda: self._action(lambda: self.service.activate(None)))
        for button in (export, import_button, unselect): buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status = QLabel('Study packages verify stored bytes, not scientific validity or publisher identity.')
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True); layout.addWidget(self.status)
        workspace.activeExperimentChanged.connect(self.refresh_results)
        workspace.observationCommitted.connect(self.refresh_results)
        workspace.observationStaged.connect(self.refresh_results)
        self.refresh_projects()
        self.service.restore()
        if workspace.active_experiment:
            self.refresh_projects(workspace.active_experiment.project_id)
            self.experiments.setCurrentIndex(self.experiments.findData(workspace.active_experiment.id))
        self.refresh_results()

    def _build_notebook(self):
        self.notebook = QTabWidget()
        self.notebook.setMinimumHeight(350)
        self.notebook.addTab(self.details, 'Result details')
        self.plan_fields = {}
        form_widget = QWidget(); form = QFormLayout(form_widget)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for key, label in [('hypothesis', 'Hypothesis'), ('method', 'Method and controls'),
                           ('expected_outcome', 'Expected outcome'), ('acceptance_criteria', 'Decision criteria')]:
            field = QPlainTextEdit(); field.setMaximumHeight(85); field.setAccessibleName(label)
            self.plan_fields[key] = field; form.addRow(label, field)
        self.save_plan_button = QPushButton('Save research plan')
        self.save_plan_button.clicked.connect(lambda: self._action(self._save_plan,
            'Research plan saved as a new immutable record. Configure and run the experiment in Simulation.'))
        form.addRow(self.save_plan_button)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(form_widget)
        self.notebook.addTab(scroll, 'Research plan')
        conclusion = QWidget(); form = QFormLayout(conclusion)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.interpretation = QPlainTextEdit(); self.interpretation.setMaximumHeight(85)
        self.limitations = QPlainTextEdit(); self.limitations.setMaximumHeight(65)
        self.decision = QComboBox()
        for label, value in [('Inconclusive', 'inconclusive'), ('Supports hypothesis within stated scope', 'supports_within_scope'),
                             ('Does not support hypothesis', 'does_not_support')]: self.decision.addItem(label, value)
        self.evidence_choices = QListWidget(); self.evidence_choices.setMaximumHeight(120)
        self.save_conclusion_button = QPushButton('Save researcher conclusion')
        self.save_conclusion_button.clicked.connect(lambda: self._action(self._save_conclusion,
            'Human interpretation saved with its plan and selected result hashes. Export the study to preserve the full record.'))
        form.addRow('Interpretation', self.interpretation); form.addRow('Limitations', self.limitations)
        form.addRow('Decision', self.decision); form.addRow('Select supporting results', self.evidence_choices)
        timing_note = QLabel('Uses the latest saved plan. A plan saved after selected results is labeled retrospective.'); timing_note.setWordWrap(True); form.addRow(timing_note)
        form.addRow(QLabel('Conclusions are human interpretations [INFERRED], not measurements or biological validation.'))
        form.addRow(self.save_conclusion_button)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(conclusion)
        self.notebook.addTab(scroll, 'Conclusion')
        self._notebook_experiment = None

    def _refresh_notebook(self):
        exp = self.workspace.active_experiment
        experiment_id = exp.id if exp else None
        checked = {self.evidence_choices.item(i).data(Qt.UserRole) for i in range(self.evidence_choices.count())
                   if self.evidence_choices.item(i).checkState() == Qt.Checked}
        if experiment_id != self._notebook_experiment:
            checked.clear()
            for field in self.plan_fields.values(): field.clear()
            self.interpretation.clear(); self.limitations.clear(); self.decision.setCurrentIndex(0)
            self._notebook_experiment = experiment_id
            self.setup_toggle.setChecked(exp is None)
            if exp:
                for obs, value in self.service.research_records(exp.id):
                    if value['record_type'] == 'plan':
                        for key, field in self.plan_fields.items(): field.setPlainText(value['content'][key])
                    else:
                        self.interpretation.setPlainText(value['content']['interpretation'])
                        self.limitations.setPlainText(value['content']['limitations'])
                        self.decision.setCurrentIndex(self.decision.findData(value['content']['decision']))
                        checked = {r['observation_id'] for r in value['result_refs']}
        self.evidence_choices.clear()
        observations = self.service.store.get_observations_for_experiment(experiment_id) if exp else []
        for obs in observations:
            if obs.instrument_id in ('research_plan', 'research_conclusion'): continue
            item = QListWidgetItem(f'{obs.instrument_id} · {obs.epistemic_state.value} · {obs.session_id[:8]}')
            item.setData(Qt.UserRole, obs.observation_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if obs.observation_id in checked else Qt.Unchecked)
            self.evidence_choices.addItem(item)
        self.save_plan_button.setEnabled(exp is not None)
        self.save_conclusion_button.setEnabled(exp is not None)
        plans = sum(o.instrument_id == 'research_plan' for o in observations)
        conclusions = sum(o.instrument_id == 'research_conclusion' for o in observations)
        results = sum(o.instrument_id not in ('research_plan', 'research_conclusion') for o in observations)
        self.workflow_status.setText('Create/open an experiment to begin.' if exp is None else
            f'Manual research: {plans} plan(s) · {results} saved result(s) · {conclusions} conclusion(s). No AI required.')

    def _save_plan(self):
        self.service.save_research_plan(**{key: field.toPlainText() for key, field in self.plan_fields.items()})

    def _save_conclusion(self):
        selected = [self.evidence_choices.item(i).data(Qt.UserRole) for i in range(self.evidence_choices.count())
                    if self.evidence_choices.item(i).checkState() == Qt.Checked]
        self.service.save_research_conclusion(self.interpretation.toPlainText(), self.limitations.toPlainText(),
            self.decision.currentData(), selected)

    def _export_csv(self):
        item = self.results.currentItem()
        if item is None: raise ValueError('Select a saved simulation first.')
        self.service.export_result_csv(item.data(Qt.UserRole).observation_id, self.csv_path.text().strip())

    def _action(self, action, success="Saved. Select a result to inspect its verified artifacts."):
        try:
            action()
            self.status.setText(success)
        except Exception as exc:
            self.status.setText(f'Could not complete action: {exc}')

    def refresh_projects(self, selected=None):
        selected = selected or self.projects.currentData()
        self.projects.blockSignals(True); self.projects.clear()
        for row in self.service.projects(): self.projects.addItem(row['name'], row['id'])
        idx = self.projects.findData(selected)
        if idx >= 0: self.projects.setCurrentIndex(idx)
        self.projects.blockSignals(False); self._refresh_experiments()

    def _refresh_experiments(self, *_):
        self.experiments.clear()
        for row in self.service.store.list_experiments():
            if row['project_id'] == self.projects.currentData():
                self.experiments.addItem(row['label'] or row['id'], row['id'])

    def _create_project(self):
        project_id = self.service.create_project(self.project_name.text())
        self.project_name.clear(); self.refresh_projects(project_id)

    def _create_experiment(self):
        exp_id = self.service.create_experiment(self.projects.currentData(), self.experiment_name.text(), self.question.text())
        self._refresh_experiments()
        self.experiments.setCurrentIndex(self.experiments.findData(exp_id))
        self.experiment_name.clear(); self.question.clear()

    def refresh_results(self, *_):
        self.results.clear(); self.staging.clear(); self.details.clear()
        exp = self.workspace.active_experiment
        if exp:
            row = self.service.store.get_experiment(exp.id)
            self.active.setText(f"Active: {exp.label or exp.id}\n{row['research_question']}")
            for obs in self.service.store.get_observations_for_experiment(exp.id):
                item = QListWidgetItem(f'{obs.instrument_id} · {obs.epistemic_state.value} · {obs.session_id[:8]}')
                item.setData(Qt.UserRole, obs); self.results.addItem(item)
        else:
            self.active.setText('No active experiment. New results enter staging.')
        self._refresh_notebook()
        for row in self.service.store.list_staged():
            item = QListWidgetItem(f"{row['instrument_id']} · {row['epistemic_state']} · {row['session_id'][:8]}")
            item.setData(Qt.UserRole, row['observation_id']); self.staging.addItem(item)

    def _attach(self):
        item = self.staging.currentItem()
        if item is None: raise ValueError('Select an unassigned result.')
        self.service.attach_staged(item.data(Qt.UserRole))

    def _inspect(self, item, *_):
        if item is None: return
        try:
            obs = item.data(Qt.UserRole)
            result = self.service.inspect(obs)
            self.details.setPlainText('Artifact hashes verified. This is not biological validation.\n\n' + json.dumps(result, indent=2))
            if obs.instrument_id in ('research_plan', 'research_conclusion'):
                return
            self.workspace.biologicalResultChanged.emit(None)
            self.workspace.validationResultChanged.emit(None)
            if obs.instrument_id == 'biological_system':
                self.workspace.current_result = None
                self.workspace.calibrationResultChanged.emit(None)
                self.workspace.biologicalResultChanged.emit(result)
            elif obs.instrument_id == 'simulation':
                self.workspace.calibrationResultChanged.emit(None)
                self.workspace.current_result = SimulationResult.from_dict(result)
            elif obs.instrument_id == 'maturation_validation':
                self.workspace.current_result = None
                self.workspace.calibrationResultChanged.emit(None)
                self.workspace.validationResultChanged.emit(result)
            elif obs.instrument_id == 'decay_calibration':
                self.workspace.current_result = None
                self.workspace.calibrationResultChanged.emit(result)
        except Exception as exc:
            self.details.setPlainText(f'Integrity error: {exc}')

    def _edit_question(self):
        exp = self.workspace.active_experiment
        if exp is None:
            self.status.setText('Open an experiment first.')
            return
        text, accepted = QInputDialog.getMultiLineText(self, 'Research question', 'Research question', exp.research_question)
        if accepted:
            self._action(lambda: self.service.update_question(text))

    def _package_path(self):
        raw = self.package_path.text().strip()
        if not raw:
            raise ValueError('Enter a study package path, or drag a study file into the path field.')
        path = Path(raw).expanduser()
        if not path.is_absolute() or path.suffix != '.vlab-study':
            raise ValueError('Use a full path ending in .vlab-study.')
        return path

    def _export(self):
        def run():
            self.service.export_study(self._package_path())
        self._action(run, 'Study package exported. Its files are ready to share.')

    def _import(self):
        def run():
            self.service.import_study(self._package_path())
            self.refresh_projects(self.workspace.active_experiment.project_id)
            self.refresh_results()
        self._action(run, 'Study imported. Select a result to verify and inspect its local files.')
