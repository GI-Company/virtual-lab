"""Experimental local numerical prediction controls, separate from conversational AI."""

import json
from pathlib import Path
import sys
from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QCheckBox,
    QComboBox,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
)
from virtual_lab.core.paths import app_data_dir
from virtual_lab.intent.controller import IntentController, parse
from virtual_lab.intent.model import canonical
from virtual_lab.pilots.storage import read_bounded


class IntentWorkspace(QWidget):
    def __init__(self, workspace, study, *, lease):
        super().__init__()
        self.workspace, self.study = workspace, study
        self.controller = IntentController(
            study.ledger, study.store, app_data_dir() / "intent", lease=lease
        )
        self.process = None
        self._job = None
        self._cancelled = False
        self._buffer = b""
        self.evaluation = None
        self.worker_timeout = QTimer(self)
        self.worker_timeout.setSingleShot(True)
        self.worker_timeout.timeout.connect(self.cancel)
        layout = QVBoxLayout(self)
        title = QLabel("INTENT Experiment Mini | Experimental local numerical learner")
        title.setStyleSheet("font-size:18px;font-weight:bold;")
        layout.addWidget(title)
        note = QLabel(
            "Not INTENT-R or a language model. No validated predictive accuracy. Imported MS spectra and workflow approvals are not verified training labels. Numerical learning never enables conversational AI or cloud calls."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.assistant = QLabel()
        layout.addWidget(self.assistant)
        self.predictions = QCheckBox("Enable INTENT predictions")
        self.learning = QCheckBox("Enable INTENT learning")
        self.project_training = QCheckBox(
            "Permit training for this project (separate signed outcome reviews still required)"
        )
        for w in (self.predictions, self.learning, self.project_training):
            layout.addWidget(w)
        save = QPushButton("Save INTENT permissions")
        save.clicked.connect(lambda: self.action(self.save_policy))
        layout.addWidget(save)
        self.models = QComboBox()
        self.models.currentIndexChanged.connect(self.refresh_model)
        layout.addWidget(self.models)
        self.schema = QPlainTextEdit()
        self.schema.setMaximumHeight(180)
        self.schema.setPlainText(
            json.dumps(
                {
                    "schema_id": "custom-outcome-v1",
                    "description": "Define a laboratory-reviewed outcome and encoding before research use.",
                    "features": [
                        {"name": "condition_1", "unit": "user-defined units"},
                        {"name": "condition_2", "unit": "user-defined units"},
                        {"name": "condition_3", "unit": "user-defined units"},
                    ],
                    "outcome_name": "Define measured outcome",
                    "outcome_unit": "user-defined units",
                    "target_offset": 0.0,
                    "target_scale": 1.0,
                },
                indent=2,
            )
        )
        layout.addWidget(
            QLabel(
                "Versioned feature / target schema (JSON; no built-in biological meaning)"
            )
        )
        layout.addWidget(self.schema)
        create = QPushButton("Initialize a new model from random weights")
        create.clicked.connect(lambda: self.action(self.initialize))
        layout.addWidget(create)
        form = QFormLayout()
        self.conditions = QLineEdit()
        self.conditions.setPlaceholderText(
            '{"condition_1":0,"condition_2":0,"condition_3":0}'
        )
        self.group = QLineEdit()
        self.group.setPlaceholderText(
            "Laboratory-defined acquisition/study group; not a scan ID"
        )
        form.addRow("Planned conditions", self.conditions)
        form.addRow("Independent group", self.group)
        self.observation = QLineEdit()
        self.review_path = QLineEdit()
        self.review_path.setPlaceholderText("Local signed review envelope JSON")
        form.addRow("Measured observation ID", self.observation)
        form.addRow("Signed review file", self.review_path)
        layout.addLayout(form)
        row = QHBoxLayout()
        for label, fn in [
            ("Commit pre-experiment prediction", self.predict),
            ("Accept signed measured outcome", self.accept),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, f=fn: self.action(f))
            row.addWidget(button)
        layout.addLayout(row)
        self.outcomes = QListWidget()
        self.outcomes.setMaximumHeight(150)
        self.outcomes.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(
            QLabel(
                "Accepted outcomes; select at least five holdout rows to freeze before training"
            )
        )
        layout.addWidget(self.outcomes)
        row = QHBoxLayout()
        for label, fn in [
            ("Freeze selected holdout", self.freeze),
            ("Train selected approved outcome", self.train),
            ("Cancel training", self.cancel),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, f=fn: self.action(f))
            row.addWidget(button)
        layout.addLayout(row)
        self.checkpoints = QListWidget()
        self.checkpoints.setMaximumHeight(150)
        layout.addWidget(
            QLabel(
                "Checkpoint history (candidate updates never activate automatically)"
            )
        )
        layout.addWidget(self.checkpoints)
        row = QHBoxLayout()
        for label, fn in [
            ("Evaluate selected checkpoint", self.evaluate),
            ("Promote evaluated candidate", self.promote),
            ("Restore previously active checkpoint", self.restore),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, f=fn: self.action(f))
            row.addWidget(button)
        layout.addLayout(row)
        self.monitor = QPlainTextEdit()
        self.monitor.setReadOnly(True)
        self.monitor.setMaximumHeight(220)
        layout.addWidget(self.monitor)
        self.status = QLabel(
            "Predictions and learning are off by default. No model is initialized automatically."
        )
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        workspace.activeExperimentChanged.connect(self.refresh)
        workspace.activeProjectChanged.connect(self.refresh)
        workspace.observationCommitted.connect(self.refresh_model)
        workspace.aiStateChanged.connect(self.refresh_assistant)
        self.refresh()

    @property
    def busy(self):
        return self.process is not None

    def action(self, fn):
        try:
            fn()
        except Exception as exc:
            self.status.setText(str(exc))

    def project_id(self):
        exp = self.workspace.active_experiment
        return getattr(exp, "project_id", None) if exp else self.workspace.active_project_id

    def model_id(self):
        value = self.models.currentData()
        if not value:
            raise ValueError("Initialize or select a model in the active project")
        return value

    def refresh_assistant(self, *_):
        self.assistant.setText(
            "Conversational assistant: "
            + getattr(self.workspace, "ai_state", "off")
            + " (independent of INTENT)"
        )

    def refresh(self, *_):
        policy = self.controller.policy()
        self.predictions.setChecked(policy.predictions_enabled)
        self.learning.setChecked(policy.learning_enabled)
        project = self.project_id()
        self.project_training.setChecked(project in policy.training_projects)
        self.project_training.setEnabled(bool(project))
        previous = self.models.currentData()
        self.models.blockSignals(True)
        self.models.clear()
        for model in self.controller.models(project):
            self.models.addItem(
                model["schema"]["schema_id"] + " | " + model["model_id"][:8],
                model["model_id"],
            )
        index = self.models.findData(previous)
        self.models.setCurrentIndex(index if index >= 0 else self.models.count() - 1)
        self.models.blockSignals(False)
        self.conditions.clear()
        self.group.clear()
        self.observation.clear()
        self.review_path.clear()
        self.evaluation = None
        self.refresh_assistant()
        self.refresh_model()

    def refresh_model(self, *_):
        self.outcomes.clear()
        self.checkpoints.clear()
        self.evaluation = None
        model = self.models.currentData()
        if not model:
            self.monitor.setPlainText(
                "No model, predictions, accepted outcomes or weight updates in this project."
            )
            return
        events = self.controller.events(model)
        active = self.controller.active(model)
        for event in events:
            p = event["payload"]
            kind = event["event_type"]
            if kind == "INTENT_OUTCOME_VERIFIED":
                item = QListWidgetItem(
                    p["purpose"]
                    + " | "
                    + p["experiment_id"][:8]
                    + " | group "
                    + p["group_id"]
                )
                item.setData(Qt.UserRole, event["event_id"])
                self.outcomes.addItem(item)
            if kind in (
                "INTENT_MODEL_REGISTERED",
                "INTENT_MODEL_UPDATED",
                "INTENT_MODEL_PROMOTED",
                "INTENT_MODEL_RESTORED",
            ):
                sha = p["checkpoint_sha256"]
                item = QListWidgetItem(
                    ("ACTIVE | " if sha == active else "")
                    + kind.replace("INTENT_MODEL_", "")
                    + " | "
                    + sha[:16]
                )
                item.setData(Qt.UserRole, sha)
                self.checkpoints.addItem(item)
        self.checkpoints.setCurrentRow(self.checkpoints.count() - 1)
        checkpoint = self.controller.checkpoint(model, active)
        outcomes = [
            e["payload"] for e in events if e["event_type"] == "INTENT_OUTCOME_VERIFIED"
        ]
        updates = [e for e in events if e["event_type"] == "INTENT_MODEL_UPDATED"]
        metrics = [
            e["payload"] for e in events if e["event_type"] == "INTENT_MODEL_EVALUATED"
        ]
        errors = (
            ", ".join(f"{p['preupdate_absolute_error']:.5g}" for p in outcomes[-10:])
            or "none"
        )
        holdout = "Holdout evaluation: not run"
        if metrics:
            latest = metrics[-1]
            holdout = (
                f"Holdout groups: {latest['groups']} | Candidate MAE: {latest['candidate_mae']:.6g} | "
                f"Active MAE: {latest['active_mae']:.6g} | Training-mean baseline MAE: {latest['training_mean_baseline_mae']:.6g}\n"
                f"Eligible for manual promotion: {latest['eligible_for_manual_promotion']}"
            )
        self.monitor.setPlainText(
            "\n".join(
                [
                    "Experimental numerical model; not scientifically validated",
                    "Active checkpoint: " + active,
                    "Candidate checkpoint: " + self.controller.candidate(model),
                    f"Accepted signed outcomes: {len(outcomes)} | Committed candidate updates: {len(updates)}",
                    f"Active weight updates: {checkpoint['state']['steps']} | Active replay examples: {len(checkpoint['state']['replay'])}",
                    "Latest prospective absolute errors (normalized target; at most 10 shown): "
                    + errors,
                    holdout,
                    "Uncertainty: unavailable; no independent calibration",
                ]
            )
        )

    def save_policy(self):
        project = self.project_id()
        policy = self.controller.policy()
        allowed = set(policy.training_projects)
        if self.project_training.isChecked() and project:
            allowed.add(project)
        elif project:
            allowed.discard(project)
        self.controller.set_policy(
            {
                "predictions_enabled": self.predictions.isChecked(),
                "learning_enabled": self.learning.isChecked(),
                "training_projects": sorted(allowed),
            }
        )
        self.status.setText(
            "INTENT permissions saved. No automatic training or model activation occurred."
        )

    def initialize(self):
        model = self.controller.initialize(
            self.project_id(), parse(self.schema.toPlainText().encode())
        )
        self.refresh()
        self.models.setCurrentIndex(self.models.findData(model))
        self.status.setText(
            "Random local model initialized. Predictions use the saved INTENT permissions; no observations or training were created."
        )

    def predict(self):
        exp = self.workspace.active_experiment
        if exp is None:
            raise ValueError("Create and select a planned experiment")
        event = self.controller.predict(
            self.model_id(),
            exp.id,
            parse(self.conditions.text().encode()),
            self.group.text().strip(),
        )
        p = event["payload"]
        self.refresh_model()
        self.status.setText(
            f"PREDICTED (unvalidated): {p['predicted_value']:.8g} {p['unit']}; checkpoint {p['checkpoint_sha256'][:16]}. No observation was created."
        )

    def accept(self):
        exp = self.workspace.active_experiment
        if exp is None:
            raise ValueError("Select an experiment")
        self.controller.accept_outcome(
            self.model_id(),
            exp.id,
            self.observation.text().strip(),
            parse(read_bounded(self.review_path.text().strip(), 65536)),
        )
        self.refresh_model()
        self.status.setText(
            "Signed measured outcome accepted for its declared train/holdout purpose. No weights updated."
        )

    def freeze(self):
        self.controller.freeze_holdout(
            self.model_id(),
            [i.data(Qt.UserRole) for i in self.outcomes.selectedItems()],
        )
        self.status.setText(
            "Independent holdout frozen before training. Its observations cannot enter replay."
        )

    def train(self):
        if self.busy:
            raise ValueError("A numerical worker is already running")
        item = self.outcomes.currentItem()
        if item is None:
            raise ValueError("Select a signed training outcome")
        job = self.controller.prepare_update(self.model_id(), item.data(Qt.UserRole))
        if "committed" in job:
            self.status.setText(
                "This outcome already has one committed update; no duplicate training."
            )
            return
        self._job = job["job_id"]
        self._job_project = self.project_id()
        self._cancelled = False
        self._buffer = b""
        process = QProcess(self)
        self.process = process
        process.setProgram(sys.executable)
        process.setArguments(["-m", "virtual_lab.intent.worker"])
        process.readyReadStandardOutput.connect(self._read_worker)
        process.started.connect(
            lambda: (
                process.write(canonical(job["request"])),
                process.closeWriteChannel(),
            )
        )
        process.finished.connect(self._finish_worker)
        process.errorOccurred.connect(self._worker_error)
        process.start()
        self.worker_timeout.start(30_000)
        self.status.setText(
            "Local CPU worker running outside the Qt process. Active checkpoint remains unchanged."
        )

    def _read_worker(self):
        if self.process is None:
            return
        self._buffer += bytes(self.process.readAllStandardOutput())
        if len(self._buffer) > 2 * 1024 * 1024:
            self.cancel()
            self.status.setText("Worker output exceeded its bound; discarded.")

    def _worker_error(self, error):
        if self.process is not None and error == QProcess.FailedToStart:
            self.worker_timeout.stop()
            self.controller.cancel_update(self._job)
            self._job = None
            self.process.deleteLater()
            self.process = None
            self.status.setText(
                "Numerical worker failed to start; active checkpoint unchanged."
            )

    def _finish_worker(self, code, *_):
        self.worker_timeout.stop()
        self._read_worker()
        process = self.process
        self.process = None
        try:
            if self._cancelled or code != 0 or self.project_id() != self._job_project:
                self.controller.cancel_update(self._job)
                self.status.setText(
                    "Training cancelled/failed or project changed; active checkpoint unchanged."
                )
            else:
                result = self.controller.complete_update(self._job, self._buffer)
                self.refresh_model()
                self.status.setText(
                    "Candidate checkpoint committed: "
                    + result["checkpoint_sha256"][:16]
                    + ". Active predictions still use the previous checkpoint."
                )
        except Exception as exc:
            self.status.setText(str(exc))
        finally:
            self._job = None
            if process is not None:
                process.deleteLater()

    def cancel(self):
        if self.process is not None:
            self._cancelled = True
            self.process.kill()

    def evaluate(self):
        item = self.checkpoints.currentItem()
        if item is None:
            raise ValueError("Select a checkpoint")
        evaluation = self.controller.evaluate(self.model_id(), item.data(Qt.UserRole))
        self.refresh_model()
        self.evaluation = evaluation["event_id"]
        p = evaluation["payload"]
        self.status.setText(
            f"Holdout MAE {p['candidate_mae']:.6g}; active {p['active_mae']:.6g}; training-mean baseline {p['training_mean_baseline_mae']:.6g}. Manual promotion gate: {p['eligible_for_manual_promotion']}."
        )

    def promote(self):
        if not self.evaluation:
            raise ValueError("Evaluate the current candidate first")
        self.controller.promote(self.model_id(), self.evaluation)
        self.refresh_model()
        self.status.setText(
            "Evaluated candidate manually activated. Scientific validation is not implied."
        )

    def restore(self):
        item = self.checkpoints.currentItem()
        if item is None:
            raise ValueError("Select a previously active checkpoint")
        self.controller.restore(self.model_id(), item.data(Qt.UserRole))
        self.refresh_model()
        self.status.setText("Previously active checkpoint restored; lineage retained.")
