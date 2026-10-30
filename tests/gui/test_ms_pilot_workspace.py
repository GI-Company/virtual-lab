import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys


def test_pilot_window_import_review_export_and_reopen(qtbot, tmp_path, monkeypatch):
    from virtual_lab.pilots.desktop import MSPilotWindow
    from virtual_lab.pilots.ms_workflow import load_manifest
    from PySide6.QtWidgets import QFileDialog
    window = MSPilotWindow()
    qtbot.addWidget(window)
    service = window.projects.service
    project = service.create_project('Synthetic MS pilot')
    experiment = service.create_experiment(project, 'CSV workflow', 'Does the workflow preserve and trace synthetic data?')
    panel = window.ms_pilot
    source = tmp_path/'synthetic.csv'
    source.write_text('mz,intensity\n101,2\n100,1\n100,3\n')
    for key,value in dict(source=str(source), dataset_id='synthetic-001', sample_id='sample', instrument_id='instrument', operator_id='operator').items():
        panel.fields[key].setText(value)
    panel.validate_input()
    assert not panel.import_button.isEnabled()
    panel.approval.setChecked(True)
    panel.validate_input()
    assert panel.import_button.isEnabled()
    panel.finalize_import()
    assert 'Import complete' in panel.status.text()
    assert panel.datasets.count() == 1
    assert panel.selected_run is not None
    panel.reprocess()
    assert 'identical' in panel.status.text()
    panel.reviewer.setText('reviewer')
    panel.review_note.setText('Synthetic workflow checked')
    panel.review()
    assert 'remains UNKNOWN' in panel.status.text()
    destination = tmp_path/'workflow-report.json'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a,**k: (str(destination), 'JSON report (*.json)'))
    panel.export()
    assert json.loads(destination.read_bytes())['review_status'] == 'approved'
    package = service.export_study(tmp_path/'synthetic.vlab-study')
    # Reopen exported study in an independent workspace and verify all CSV artifacts.
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.gui.services.study_service import StudyService
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    monkeypatch.setenv('VIRTUALLAB_DATA_DIR', str(tmp_path/'recipient'))
    recipient_root = tmp_path/'recipient'
    recipient_root.mkdir()
    ledger = GenesisLedger(str(recipient_root/'genesis.db'))
    store = ExperimentStore(str(recipient_root/'experiments.db'))
    recipient = StudyService(WorkspaceState(), ledger, store)
    recipient.import_study(package)
    imported = store.get_observations_for_experiment(experiment)
    assert len(imported) == 1
    assert recipient.inspect(imported[0])['peak_count'] == 3
    assert imported[0].epistemic_state.value == 'UNKNOWN'
    from virtual_lab.pilots.datasets import MSDatasetService
    imported_service = MSDatasetService(ledger, store, recipient_root/'ms-pilot-runs')
    assert imported_service.runs(experiment)[0]['run_id'] == imported[0].session_id
    assert imported_service.verify(imported[0].session_id)['verified']
    store.close()
    ledger.conn.close()
    window.close()


def test_offline_pilot_does_not_load_ai_or_open_sockets(tmp_path):
    script = '''
import importlib.abc, socket, sys
class NoAI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith(('google', 'groq', 'virtual_lab.ai')):
            raise AssertionError('Pilot attempted to load AI: ' + fullname)
sys.meta_path.insert(0, NoAI())
def deny(*args, **kwargs):
    raise AssertionError('Pilot attempted network access')
socket.socket.connect = deny
socket.socket.bind = deny
from PySide6.QtWidgets import QApplication
from virtual_lab.pilots.desktop import MSPilotWindow
app = QApplication([])
window = MSPilotWindow()
window.show()
app.processEvents()
window.close()
print('OFFLINE_PILOT_OK')
'''
    result = subprocess.run([sys.executable, '-c', script], env=dict(os.environ,
        QT_QPA_PLATFORM='offscreen', VIRTUALLAB_DATA_DIR=str(tmp_path/'offline')), capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'OFFLINE_PILOT_OK' in result.stdout
