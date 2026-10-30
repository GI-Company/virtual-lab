"""Local MS workflow panel. No AI, instrument control or network requests."""
import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QCheckBox, QPlainTextEdit, QTabWidget,
    QListWidget, QListWidgetItem, QSplitter, QComboBox, QGroupBox, QScrollArea)
import pyqtgraph as pg
from virtual_lab.core.paths import app_data_dir
from virtual_lab.pilots.datasets import MSDatasetService
from virtual_lab.pilots.ms_workflow import (normalize_centroid_csv, parse_centroids,
    load_manifest, _sha256)
from virtual_lab.pilots.storage import read_bounded
from virtual_lab.pilots.schemas import MAX_SOURCE_BYTES, AcquisitionMetadata, PilotError
from virtual_lab.pilots.reporting import spectrum_summary


class MSPilotWorkspace(QWidget):
    def __init__(self, workspace, study_service, parent=None, *, lease=None):
        super().__init__(parent)
        self.workspace, self.study_service = workspace, study_service
        self.service = MSDatasetService(study_service.ledger, study_service.store, app_data_dir()/'ms-pilot-runs', lease=lease)
        self.selected_run = None
        self.validated = None
        layout = QVBoxLayout(self)
        title = QLabel('MS Workflow | Nonconfidential pilot')
        title.setStyleSheet('font-size: 20px; font-weight: bold;')
        layout.addWidget(title)
        self.context = QLabel()
        self.context.setWordWrap(True)
        layout.addWidget(self.context)
        note = QLabel('Local processing. Imported evidence stays UNKNOWN. Checksums verify bytes; instrument origin and scientific validity are unverified.')
        note.setWordWrap(True)
        layout.addWidget(note)
        split = QSplitter(Qt.Horizontal)
        layout.addWidget(split, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        split.addWidget(left)
        self.datasets = QListWidget()
        self.datasets.setAccessibleName('Imported MS datasets')
        self.datasets.currentItemChanged.connect(self.select_dataset)
        left_layout.addWidget(QLabel('Datasets in the active experiment'))
        left_layout.addWidget(self.datasets)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs)
        intake = QWidget()
        form_layout = QVBoxLayout(intake)
        form = QFormLayout()
        self.fields = {}
        for key, label in [('source','CSV file'),('pilot_id','Pilot ID'),('dataset_id','Dataset ID'),
                           ('sample_id','Sample ID'),('instrument_id','Instrument ID'),('operator_id','Operator / pseudonym'),
                           ('acquired_at','Acquired at (ISO time with zone, optional)'),('mz_units','m/z units (optional)'),
                           ('intensity_units','Intensity units (optional)')]:
            edit = QLineEdit()
            edit.setAccessibleName(label)
            edit.setMaxLength(4096 if key == 'source' else 100)
            edit.textChanged.connect(self.invalidate_preview)
            self.fields[key] = edit
            form.addRow(label, edit)
        self.fields['pilot_id'].setText('mild-biotec-initial-ms')
        self.data_origin = QComboBox()
        self.data_origin.addItem('Unspecified', 'unspecified')
        self.data_origin.addItem('Synthetic example', 'synthetic')
        self.data_origin.addItem('Public reference peak list (origin unverified)', 'public_reference')
        self.data_origin.addItem('Laboratory supplied (origin unverified)', 'laboratory_supplied')
        self.data_origin.currentIndexChanged.connect(self.invalidate_preview)
        form.addRow('Declared data origin', self.data_origin)
        form_layout.addLayout(form)
        browse = QPushButton('Select CSV file')
        browse.clicked.connect(self.browse)
        form_layout.addWidget(browse)
        self.approval = QCheckBox('I confirm this dataset is synthetic or approved nonconfidential data permitted for this pilot')
        self.approval.toggled.connect(self.invalidate_preview)
        form_layout.addWidget(self.approval)
        self.source_group=QGroupBox('Include source attribution (public references)')
        self.source_group.setCheckable(True)
        self.source_group.setChecked(False)
        source_layout=QVBoxLayout(self.source_group)
        source_content=QWidget()
        source_form=QFormLayout(source_content)
        self.source_fields={}
        for key,label in [('accession','Reference accession'),('url','Primary source URL'),('license','Source license'),('attribution','Source authors / attribution'),('notes','Conversion / source notes')]:
            field=QLineEdit()
            field.setAccessibleName(label)
            field.textChanged.connect(self.invalidate_preview)
            self.source_fields[key]=field
            source_form.addRow(label,field)
        source_content.setVisible(False)
        self.source_group.toggled.connect(source_content.setVisible)
        self.source_group.toggled.connect(self.invalidate_preview)
        source_layout.addWidget(source_content)
        form_layout.addWidget(self.source_group)
        row = QHBoxLayout()
        self.validate_button = QPushButton('Validate and preview')
        self.validate_button.clicked.connect(self.validate_input)
        self.import_button = QPushButton('Finalize import')
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self.finalize_import)
        row.addWidget(self.validate_button)
        row.addWidget(self.import_button)
        form_layout.addLayout(row)
        form_layout.addStretch()
        self.import_scroll = QScrollArea()
        self.import_scroll.setWidgetResizable(True)
        self.import_scroll.setFrameShape(QScrollArea.NoFrame)
        self.import_scroll.setWidget(intake)
        self.tabs.addTab(self.import_scroll, 'Import')
        spectrum = QWidget()
        spectrum_layout = QVBoxLayout(spectrum)
        self.plot = pg.PlotWidget()
        self.plot.setLabel('bottom', 'Recorded m/z')
        self.plot.setLabel('left', 'Intensity (units unspecified)')
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.showGrid(x=True, y=True, alpha=.2)
        self.plot.scene().sigMouseMoved.connect(self.peak_coordinates)
        spectrum_layout.addWidget(self.plot)
        self.coordinates = QLabel('Drag to pan; scroll to zoom; right-click for plot controls')
        spectrum_layout.addWidget(self.coordinates)
        self.log_scale = QCheckBox('Log intensity scale (zero values omitted from log display)')
        self.log_scale.toggled.connect(lambda enabled: self.plot.setLogMode(y=enabled))
        spectrum_layout.addWidget(self.log_scale)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(160)
        spectrum_layout.addWidget(self.summary)
        self.tabs.addTab(spectrum, 'Spectrum')
        comparison = QWidget()
        compare_layout = QHBoxLayout(comparison)
        self.original, self.normalized = QPlainTextEdit(), QPlainTextEdit()
        for editor in (self.original, self.normalized):
            editor.setReadOnly(True)
            compare_layout.addWidget(editor)
        self.original.setAccessibleName('Original CSV preview, first 16 KiB')
        self.normalized.setAccessibleName('Normalized CSV preview, first 16 KiB')
        self.tabs.addTab(comparison, 'Original / normalized')
        provenance = QWidget()
        provenance_layout = QVBoxLayout(provenance)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        provenance_layout.addWidget(self.history)
        review_form = QFormLayout()
        self.reviewer = QLineEdit()
        self.review_note = QLineEdit()
        self.decision = QComboBox()
        self.decision.addItems(['Approve workflow', 'Reject workflow'])
        review_form.addRow('Reviewer / pseudonym', self.reviewer)
        review_form.addRow('Review note', self.review_note)
        review_form.addRow('Decision', self.decision)
        provenance_layout.addLayout(review_form)
        review_button = QPushButton('Record workflow review')
        review_button.clicked.connect(self.review)
        provenance_layout.addWidget(review_button)
        self.tabs.addTab(provenance, 'Provenance / review')
        actions = QHBoxLayout()
        for label, handler in [('Verify integrity', self.verify), ('Compare repeat processing', self.reprocess), ('Test alteration detection', self.test_alteration),
                               ('Export JSON / PDF report', self.export)]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        right_layout.addLayout(actions)
        verify_exports=QPushButton('Verify exported PDF / JSON checksums')
        verify_exports.clicked.connect(self.verify_exports)
        right_layout.addWidget(verify_exports)
        self.status = QLabel('Select a CSV and enter metadata to begin. CSV previews are limited to the first 16 KiB.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        workspace.activeExperimentChanged.connect(self.refresh)
        self.refresh()

    def fail(self, exc):
        self.status.setText(f"{getattr(exc, 'code', 'WORKFLOW_ERROR')}: {exc}")

    def invalidate_preview(self, *_):
        self.validated = None
        if hasattr(self, 'import_button'):
            self.import_button.setEnabled(False)

    def metadata(self):
        fields = {key: edit.text().strip() for key, edit in self.fields.items() if key != 'source'}
        for key in ('acquired_at','mz_units','intensity_units'):
            fields[key] = fields[key] or None
        fields['data_origin'] = self.data_origin.currentData()
        if self.source_group.isChecked():
            fields['source_reference'] = {key:edit.text().strip() for key,edit in self.source_fields.items()}
        AcquisitionMetadata(**{('acquired_at_utc' if key == 'acquired_at' else key): value for key,value in fields.items()})
        return {**fields, 'approved_nonconfidential': self.approval.isChecked()}

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select permitted centroid CSV', '', 'Centroid CSV (*.csv)')
        if path:
            self.fields['source'].setText(path)

    def show_spectrum(self, raw, normalized, units=None):
        peaks = parse_centroids(normalized, normalized=True)
        x, y = [float(p[0]) for p in peaks], [float(p[1]) for p in peaks]
        self.plot.clear()
        # Centroid sticks preserve every input point, including repeated m/z values.
        self.plot.plot([v for v in x for _ in (0,1)], [v for val in y for v in (0,val)],
            connect='pairs', pen=pg.mkPen('#36b7db'))
        self.plot.plot(x,y, pen=None, symbol='o', symbolSize=4, symbolBrush='#36b7db')
        self.plot.setLabel('left', 'Intensity (' + (units or 'unspecified units') + ')')
        self.plot.autoRange()
        self.original.setPlainText('Original bytes (first 16 KiB)\n' + raw[:16384].decode('utf-8-sig', errors='replace'))
        self.normalized.setPlainText('Normalized bytes (first 16 KiB)\n' + normalized[:16384].decode('utf-8', errors='replace'))
        stats = spectrum_summary(normalized)
        self.summary.setPlainText(
            f"Peak entries: {stats['peak_count']} | Repeated m/z entries: {stats['duplicate_mz_count']}\n"
            f"m/z range: {stats['mz_min']} to {stats['mz_max']}\n"
            f"Base peak: m/z {stats['base_peak']['mz']}, intensity {stats['base_peak']['intensity']}\n"
            f"Sum of centroid intensities: {stats['total_intensity']} ({units or 'unspecified units'})\n"
            'Descriptive peak-list metrics only; no instrument or scientific validation.')

    def peak_coordinates(self, position):
        if self.plot.sceneBoundingRect().contains(position):
            point = self.plot.plotItem.vb.mapSceneToView(position)
            self.coordinates.setText(f'Cursor m/z: {point.x():.8g} | intensity axis: {point.y():.8g} | drag to pan, scroll to zoom')

    def validate_input(self):
        self.invalidate_preview()
        try:
            metadata = self.metadata()
            if not metadata['approved_nonconfidential']:
                raise PilotError('DATA_APPROVAL', 'Confirm permitted nonconfidential pilot data before preview')
            raw = read_bounded(self.fields['source'].text(), MAX_SOURCE_BYTES)
            normalized, _ = normalize_centroid_csv(raw)
            self.show_spectrum(raw, normalized, metadata['intensity_units'])
            self.validated = (_sha256(raw), metadata)
            self.import_button.setEnabled(True)
            self.status.setText('Validation passed. Preview is ready; finalize import to preserve files and record provenance.')
            self.tabs.setCurrentIndex(1)
        except Exception as exc:
            self.fail(exc)

    def finalize_import(self):
        try:
            if self.validated is None:
                raise PilotError('PREVIEW_REQUIRED', 'Validate and preview the current file before import')
            raw = read_bounded(self.fields['source'].text(), MAX_SOURCE_BYTES)
            if (_sha256(raw), self.metadata()) != self.validated:
                self.invalidate_preview()
                raise PilotError('SOURCE_CHANGED', 'The source or metadata changed; validate it again')
            exp = self.workspace.active_experiment
            obs = self.service.import_csv(self.fields['source'].text(), experiment_id=exp.id if exp else '', expected_source_sha256=self.validated[0], **self.validated[1])
            exp.attach_observation(obs)
            self.workspace.observationCommitted.emit(obs)
            self.invalidate_preview()
            self.refresh()
            for i in range(self.datasets.count()):
                item = self.datasets.item(i)
                if item.data(Qt.UserRole) == obs.session_id:
                    self.datasets.setCurrentItem(item)
            self.status.setText('Import complete. Original and normalized bytes preserved. Evidence: UNKNOWN.')
        except Exception as exc:
            self.fail(exc)

    def refresh(self, *_):
        exp = self.workspace.active_experiment
        self.context.setText('Experiment: ' + (exp.label if exp else 'Create and select one in Projects'))
        self.datasets.clear()
        self.selected_run = None
        if exp:
            for record in self.service.runs(exp.id):
                item = QListWidgetItem(record['dataset_id'] + ' | ' + record['run_id'][:8])
                item.setData(Qt.UserRole, record['run_id'])
                self.datasets.addItem(item)
        self.history.clear()
        self.plot.clear()
        self.summary.clear()
        self.original.clear()
        self.normalized.clear()

    def select_dataset(self, item, *_):
        self.selected_run = None
        if item is None:
            return
        try:
            run_id = item.data(Qt.UserRole)
            manifest, contents, _ = self.service.read(run_id)
            self.show_spectrum(contents['source.csv'], contents['peaks.csv'], manifest['intensity_units'])
            self.history.setPlainText(json.dumps(self.service.events(run_id), indent=2))
            self.selected_run = run_id
            self.status.setText('Source and normalized checksums verified against the local ledger. Source authenticity unverified.')
        except Exception as exc:
            self.fail(exc)

    def verify(self):
        try:
            result = self.service.verify(self.selected_run)
            self.status.setText(result['note'])
        except Exception as exc:
            self.fail(exc)

    def reprocess(self):
        try:
            result = self.service.reprocess(self.selected_run)
            self.history.setPlainText(json.dumps(self.service.events(self.selected_run), indent=2))
            self.status.setText('Repeat processing: ' + ('identical normalized bytes and digest' if result['identical'] else 'MISMATCH'))
        except Exception as exc:
            self.fail(exc)

    def test_alteration(self):
        try:
            result = self.service.test_alteration(self.selected_run)
            self.history.setPlainText(json.dumps(self.service.events(self.selected_run), indent=2))
            self.status.setText('Alteration check: ' + ('PASS; altered copy rejected, original preserved' if result['detected'] else 'FAIL; alteration not detected'))
        except Exception as exc:
            self.fail(exc)

    def review(self):
        try:
            self.service.review(self.selected_run, reviewer=self.reviewer.text().strip(), approved=self.decision.currentIndex()==0,
                                note=self.review_note.text().strip())
            self.history.setPlainText(json.dumps(self.service.events(self.selected_run), indent=2))
            self.status.setText('Workflow review recorded. Evidence remains UNKNOWN.')
        except Exception as exc:
            self.fail(exc)

    def verify_exports(self):
        try:
            from virtual_lab.pilots.reporting import verify_report_files
            path,_=QFileDialog.getOpenFileName(self,'Verify report checksums','','SHA-256 checksums (*.sha256)')
            if path:
                result=verify_report_files(path)
                self.status.setText('Report verification PASS: '+', '.join(result['files'])+'. '+result['scope'])
        except Exception as exc:
            self.fail(exc)

    def export(self):
        try:
            self.service.verify(self.selected_run)
            path, _ = QFileDialog.getSaveFileName(self, 'Export reproducible workflow report', 'ms-report.json',
                                                 'JSON report (*.json);;PDF report (*.pdf)')
            if path:
                self.service.export_report(self.selected_run, path)
                self.status.setText('Report exported' + (' with companion JSON and SHA-256 checksums.' if Path(path).suffix == '.pdf' else ' with SHA-256 checksums.') + ' Transfer only through an agreed channel.')
        except Exception as exc:
            self.fail(exc)
