"""Desktop controls for isolated, cancellable computational biology runs."""
import json
from pathlib import Path
import sys

from pydantic import ValidationError
from PySide6.QtCore import QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSpinBox, QPlainTextEdit, QCheckBox, QTabWidget,
    QScrollArea, QSplitter,
)

from virtual_lab.ai.credentials import CredentialService
from virtual_lab.computational.artifacts import CompletedRun, register
from virtual_lab.computational.requests import GenomeRequest, StructureRequest, LENGTHS, OUTPUTS
from virtual_lab.domain.experiment_store import ExperimentStore


class ComputationalWorkspace(QWidget):
    def __init__(self, workspace, ledger, parent=None):
        super().__init__(parent)
        self.workspace, self.ledger = workspace, ledger
        self.process = None
        self.completed_run = None
        self._experiment_at_start = None
        self._cancel_reason = ""
        layout = QVBoxLayout(self)
        title = QLabel("Computational Biology · predictions and reference structures")
        layout.addWidget(title)
        self.context = QLabel()
        layout.addWidget(self.context)
        workspace.activeExperimentChanged.connect(self._update_context)
        self._update_context()
        self.hypothesis = QLineEdit()
        self.hypothesis.setPlaceholderText("Hypothesis or research question for this run")
        layout.addWidget(self.hypothesis)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.inputs = QTabWidget()
        scroll.setWidget(self.inputs)
        splitter.addWidget(scroll)
        self._genome_form()
        self._structure_form()
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.history = QComboBox()
        self.history.setPlaceholderText("Saved computational runs")
        self.history.activated.connect(self._select_history)
        right_layout.addWidget(self.history)
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setPlaceholderText("A completed run will show its summary, limitations, and saved artifacts here.")
        right_layout.addWidget(self.results, 1)
        buttons = QHBoxLayout()
        self.open_folder = QPushButton("Open artifact folder")
        self.open_folder.setEnabled(False)
        self.open_folder.clicked.connect(self._open_folder)
        buttons.addWidget(self.open_folder)
        self.retry_registration = QPushButton("Register saved run")
        self.retry_registration.setEnabled(False)
        self.retry_registration.clicked.connect(self._register_completed)
        buttons.addWidget(self.retry_registration)
        right_layout.addLayout(buttons)
        splitter.addWidget(right)
        splitter.setSizes([500, 700])
        actions = QHBoxLayout()
        self.run_button = QPushButton("Run computational assay")
        self.run_button.clicked.connect(self._start)
        self.cancel_button = QPushButton("Cancel run")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        actions.addWidget(self.run_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.status = QLabel("Ready. AlphaFold retrieves one accession at a time.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(lambda: self.cancel("Run timed out after 5 minutes. No result was registered."))
        self._refresh_history()

    @property
    def busy(self):
        return self.process is not None

    def _update_context(self, *_):
        experiment = self.workspace.active_experiment
        self.context.setText(f"Results will attach to experiment {experiment.id}" if experiment else
                             "No active experiment: results will enter observation staging.")

    def _genome_form(self):
        panel = QWidget()
        form = QFormLayout(panel)
        self.genome_form = form
        self.key_status = QLabel("Key saved in Keychain" if CredentialService().get_api_key("alphagenome") else "AlphaGenome key required")
        form.addRow(self.key_status)
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setPlaceholderText("New or replacement API key")
        key_layout.addWidget(self.key_input)
        save = QPushButton("Save key")
        save.clicked.connect(self._save_key)
        key_layout.addWidget(save)
        form.addRow(key_row)
        self.operation = QComboBox()
        for label, value in (("Reference interval", "interval"), ("DNA sequence", "sequence"),
                             ("REF / ALT variant", "variant"), ("Variant scoring", "score"),
                             ("In-silico mutagenesis", "ism")):
            self.operation.addItem(label, value)
        form.addRow("Assay", self.operation)
        form.addRow(QLabel("Human hg38 · intervals use 0-based start, variants use 1-based position"))
        self.chromosome = QComboBox()
        self.chromosome.addItems([f"chr{i}" for i in range(1, 23)] + ["chrX", "chrY", "chrM"])
        self.chromosome.setCurrentText("chr19")
        form.addRow("Chromosome", self.chromosome)
        self.start = QSpinBox()
        self.start.setRange(0, 300000000)
        self.start.setValue(44800000)
        form.addRow("Interval start (0-based)", self.start)
        self.length = QComboBox()
        for length in LENGTHS:
            self.length.addItem(f"{length:,} bases", length)
        form.addRow("Window length", self.length)
        self.position = QSpinBox()
        self.position.setRange(1, 300000000)
        self.position.setValue(44810000)
        form.addRow("Variant position (1-based)", self.position)
        self.reference = QLineEdit()
        self.alternate = QLineEdit()
        form.addRow("Reference allele", self.reference)
        form.addRow("Alternate allele", self.alternate)
        self.sequence = QPlainTextEdit()
        self.sequence.setMaximumHeight(90)
        self.sequence.setPlaceholderText("ACGTN sequence exactly matching the selected window length")
        form.addRow("DNA sequence", self.sequence)
        self.ism_start = QSpinBox()
        self.ism_start.setRange(0, 300000000)
        self.ism_start.setValue(44810000)
        form.addRow("ISM start (0-based)", self.ism_start)
        self.ism_width = QSpinBox()
        self.ism_width.setRange(1, 32)
        form.addRow("ISM bases (up to 96 variants)", self.ism_width)
        self.output = QComboBox()
        self.output.addItems(OUTPUTS)
        self.output.setCurrentText("RNA_SEQ")
        form.addRow("Output modality / scorer", self.output)
        self.ontology = QLineEdit()
        self.ontology.setPlaceholderText("Optional: UBERON:0002048; separate terms with commas")
        form.addRow("Tissue / cell ontology", self.ontology)
        self.scoring_note = QLabel("Scoring returns all tracks with gene/track annotations. ISM makes multiple API calls.")
        self.scoring_note.setWordWrap(True)
        form.addRow(self.scoring_note)
        self.model = QComboBox()
        self.model.addItems(["ALL_FOLDS", "FOLD_0", "FOLD_1", "FOLD_2", "FOLD_3", "FOLD_4"])
        form.addRow("Model selector", self.model)
        self.operation.currentIndexChanged.connect(self._mode_changed)
        self.inputs.addTab(panel, "AlphaGenome")
        self._mode_changed()

    def _mode_changed(self, *_):
        operation = self.operation.currentData()
        for field in (self.chromosome, self.start):
            self.genome_form.setRowVisible(field, operation != "sequence")
        for field in (self.position, self.reference, self.alternate):
            self.genome_form.setRowVisible(field, operation in ("variant", "score"))
        self.genome_form.setRowVisible(self.sequence, operation == "sequence")
        for field in (self.ism_start, self.ism_width):
            self.genome_form.setRowVisible(field, operation == "ism")
        self.genome_form.setRowVisible(self.ontology, operation not in ("score", "ism"))
        self.genome_form.setRowVisible(self.scoring_note, operation in ("score", "ism"))

    def _structure_form(self):
        panel = QWidget()
        form = QFormLayout(panel)
        note = QLabel("Retrieve existing predicted structures by UniProt accession. No local AlphaFold installation or database download is used.")
        note.setWordWrap(True)
        form.addRow(note)
        self.accession = QLineEdit("P08100")
        form.addRow("UniProt accession", self.accession)
        self.include_structure = QCheckBox("Retrieve this protein’s mmCIF structure (max 16 MB)")
        self.include_pae = QCheckBox("Retrieve its PAE confidence matrix (max 32 MB)")
        form.addRow(self.include_structure)
        form.addRow(self.include_pae)
        note = QLabel("Both unchecked: metadata only. A reference structure does not establish the effect of a mutation.")
        note.setWordWrap(True)
        form.addRow(note)
        self.inputs.addTab(panel, "AlphaFold DB")

    def _save_key(self):
        key = self.key_input.text().strip()
        if not key:
            self.status.setText("Enter a key to save.")
            return
        try:
            CredentialService().set_api_key("alphagenome", key)
            self.key_input.clear()
            self.key_status.setText("Key saved in Keychain")
            self.status.setText("AlphaGenome key saved securely. Run an assay to verify API access.")
        except Exception:
            self.status.setText("Could not save the key in the operating system credential store.")

    def _request(self):
        common = {"hypothesis": self.hypothesis.text().strip(),
                  "experiment_id": self._experiment_at_start.id if self._experiment_at_start else ""}
        if self.inputs.currentIndex() == 1:
            return StructureRequest(accession=self.accession.text().strip().upper(),
                                    include_structure=self.include_structure.isChecked(),
                                    include_pae=self.include_pae.isChecked(), **common)
        operation = self.operation.currentData()
        variant = operation in ("variant", "score")
        return GenomeRequest(
            operation=operation, chromosome=self.chromosome.currentText(), start=self.start.value(),
            length=self.length.currentData(), position=self.position.value() if variant else None,
            reference_bases=self.reference.text().strip().upper() if variant else "",
            alternate_bases=self.alternate.text().strip().upper() if variant else "",
            sequence="".join(self.sequence.toPlainText().split()).upper() if operation == "sequence" else "",
            outputs=(self.output.currentText(),),
            ontology_terms=tuple(t.strip() for t in self.ontology.text().split(",") if t.strip()) if operation not in ("score", "ism") else (),
            ism_start=self.ism_start.value() if operation == "ism" else None,
            ism_width=self.ism_width.value(), model_version=self.model.currentText(), **common)

    def _start(self):
        if self.busy:
            return
        self._experiment_at_start = self.workspace.active_experiment
        try:
            request = self._request()
        except ValidationError as exc:
            self.status.setText("; ".join(e["msg"] for e in exc.errors(include_input=False)))
            return
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return
        self._cancel_reason = ""
        self.completed_run = None
        self.open_folder.setEnabled(False)
        self.retry_registration.setEnabled(False)
        self.run_button.setEnabled(False)
        self.inputs.setEnabled(False)
        self.history.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status.setText("Running remote assay… Results will be recorded when the complete response is saved.")
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(Path(__file__).resolve().parents[2]))
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.process.start(sys.executable, ["-m", "virtual_lab.computational.cli"])
        self.process.write(request.model_dump_json().encode())
        self.process.closeWriteChannel()
        self.deadline.start(300000)

    def cancel(self, message="Run cancelled. No result was registered."):
        if self.process is not None:
            self._cancel_reason = message if isinstance(message, str) else "Run cancelled. No result was registered."
            self.process.kill()

    def _process_error(self, error):
        if error == QProcess.FailedToStart:
            self._cancel_reason = "Could not start the computational worker. Check the Python environment."
            self._finished(-1, QProcess.CrashExit)

    def _finished(self, exit_code, exit_status):
        if self.process is None:
            return
        process, self.process = self.process, None
        self.deadline.stop()
        raw = bytes(process.readAllStandardOutput())
        process.deleteLater()
        self.run_button.setEnabled(True)
        self.inputs.setEnabled(True)
        self.history.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self._cancel_reason:
            self.status.setText(self._cancel_reason)
            return
        try:
            response = json.loads(raw)
            if not response.get("ok"):
                self.status.setText(response.get("error", "Run failed."))
                return
            if exit_code != 0 or exit_status != QProcess.NormalExit:
                raise ValueError("Worker did not finish normally.")
            self.completed_run = CompletedRun(response["manifest_path"], response["sha256"])
            self._display_completed()
            self._register_completed()
        except Exception:
            self.status.setText("Could not verify the completed result. No successful registration is confirmed.")
        self._refresh_history()

    def _display_completed(self):
        manifest = self.completed_run.read()
        self.results.setPlainText(json.dumps(manifest, indent=2))
        self.open_folder.setEnabled(True)
        self.retry_registration.setEnabled(True)

    def _register_completed(self):
        if not self.completed_run:
            return
        store = None
        try:
            store = ExperimentStore()
            observation = register(self.completed_run, self.ledger, store)
            experiment = self._experiment_at_start
            if observation.experiment_id:
                if experiment and experiment.id == observation.experiment_id and not any(o.observation_id == observation.observation_id for o in experiment.observations):
                    experiment.attach_observation(observation)
                self.workspace.observationCommitted.emit(observation)
            else:
                self.workspace.observationStaged.emit(observation)
            self.retry_registration.setEnabled(False)
            self.status.setText(f"Saved and recorded as {observation.epistemic_state.value} evidence" +
                                (f" for experiment {observation.experiment_id}." if observation.experiment_id else " in observation staging."))
        except Exception:
            self.status.setText("Artifacts are saved, but registration failed. Use Register saved run to retry.")
        finally:
            if store is not None:
                store.close()

    def _refresh_history(self):
        self.history.clear()
        # Only ledger-backed runs are presented as trusted saved predictions.
        rows = self.ledger.conn.execute(
            "SELECT payload_json FROM ledger_events WHERE event_type = 'COMPUTATIONAL_PREDICTION_RECORDED' ORDER BY sequence DESC"
        ).fetchall()
        for row in rows:
            record = json.loads(row["payload_json"])
            self.history.addItem(f"{record['instrument']} · {record['run_id'][:8]}", record)

    def _select_history(self, index):
        record = self.history.itemData(index)
        if not record:
            return
        self._experiment_at_start = self.workspace.active_experiment
        self.completed_run = CompletedRun(record["artifact_path"], record["artifact_sha256"])
        try:
            self._display_completed()
            self.retry_registration.setEnabled(False)
            self.status.setText("Saved manifest and artifact hashes verified.")
        except Exception:
            self.completed_run = None
            self.open_folder.setEnabled(False)
            self.retry_registration.setEnabled(False)
            self.status.setText("Integrity error: a saved artifact is missing or has changed.")

    def _open_folder(self):
        if self.completed_run:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.completed_run.manifest_path).parent)))
