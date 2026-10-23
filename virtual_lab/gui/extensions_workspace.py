"""Bounded, data-only file adapters attached to the active study."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QFormLayout, QComboBox, QLineEdit, QPushButton, QLabel
from virtual_lab.core.canonical import strict_json_loads

class ExtensionFilesPanel(QWidget):
    def __init__(self, service):
        super().__init__()
        self.service = service
        form = QFormLayout(self)
        self.mode = QComboBox()
        self.mode.addItem('Predictive model: linear JSON', 'predictive_model')
        self.mode.addItem('Instrument: declared CSV file', 'instrument_import')
        form.addRow('Source type', self.mode)
        self.manifest = QLineEdit(); self.manifest.setAccessibleName('Extension manifest path')
        self.manifest.setPlaceholderText('Full path to the model or instrument JSON manifest')
        form.addRow('Manifest path', self.manifest)
        self.csv_path = QLineEdit(); self.csv_path.setAccessibleName('Instrument CSV path')
        form.addRow('Instrument CSV path', self.csv_path)
        self.inputs = QLineEdit('{}'); self.inputs.setAccessibleName('Predictor inputs JSON')
        self.inputs.setMaxLength(32000)
        form.addRow('Predictor inputs JSON', self.inputs)
        self.note = QLabel('Predictors remain PREDICTED; imported CSV remains UNKNOWN. Source bytes are retained. No instrument control or scientific validation is performed.')
        self.note.setWordWrap(True); form.addRow(self.note)
        self.save_button = QPushButton('Run adapter and attach result')
        self.save_button.clicked.connect(self._save)
        form.addRow(self.save_button)
        self.status = QLabel('Open an experiment, then choose its source files.')
        self.status.setWordWrap(True); self.status.setTextFormat(Qt.PlainText)
        form.addRow(self.status)
        self.mode.currentIndexChanged.connect(self._refresh)
        service.workspace.activeExperimentChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self, *_):
        predictor = self.mode.currentData() == 'predictive_model'
        self.inputs.setEnabled(predictor); self.csv_path.setEnabled(not predictor)
        self.save_button.setEnabled(self.service.workspace.active_experiment is not None)

    def _save(self):
        try:
            if self.mode.currentData() == 'predictive_model':
                obs = self.service.save_predictor(self.manifest.text().strip(), strict_json_loads(self.inputs.text()))
            else:
                obs = self.service.save_csv_instrument(self.manifest.text().strip(), self.csv_path.text().strip())
            self.status.setText('Attached ' + obs.observation_id + ' (' + obs.epistemic_state.value + '). Inspect it in Result details and select it as evidence for a conclusion.')
        except Exception as error:
            self.status.setText('Could not attach result: ' + str(error))
