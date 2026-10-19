from tests.projects.test_study_lifecycle import service
from virtual_lab.gui.instruments.workspace import InstrumentsWorkspace
from virtual_lab.instruments.transport.gateway import InstrumentGateway
from virtual_lab.instruments.measurements import Measurement, ScientificState


def test_recording_stays_with_experiment_selected_at_start(qtbot, tmp_path, monkeypatch):
    svc = service(tmp_path/'source', monkeypatch)
    project = svc.create_project('Instrument study')
    original = svc.create_experiment(project, 'Capture', 'Inspect the recorded signal')
    gateway = InstrumentGateway(svc.ledger)
    panel = InstrumentsWorkspace(svc.workspace, gateway, ledger=svc.ledger)
    qtbot.addWidget(panel)
    panel.current_instrument = 'synthetic-test-device'
    panel._start_session()
    panel.store.append(Measurement('fixture-1', panel.current_session, None, panel.current_instrument,
        'sensor-1', 0, 1, 1, 1, 'ILLUMINANCE', {'illuminance': 12.}, {'illuminance': 'lx'},
        None, None, ScientificState.MEASURED))
    other = svc.create_experiment(project, 'Another capture', 'A different question')
    panel._stop_session()
    assert panel.session_state == 'COMMITTED'
    saved = svc.store.get_observations_for_experiment(original)
    assert len(saved) == 1 and svc.inspect(saved[0])['sample_count'] == 1
    assert not svc.store.get_observations_for_experiment(other)
    assert not gateway.server.isListening()
