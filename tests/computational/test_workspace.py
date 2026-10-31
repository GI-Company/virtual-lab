import json
from types import SimpleNamespace

from PySide6.QtCore import QProcess

from virtual_lab.computational.artifacts import execute
from virtual_lab.computational.adapters import AlphaFoldDBAdapter
from virtual_lab.computational.requests import StructureRequest
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.gui.computational_workspace import ComputationalWorkspace
from virtual_lab.gui.shell.workspace_manager import WorkspaceState


def make_panel(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("virtual_lab.gui.computational_workspace.CredentialService.get_api_key", lambda *a: None)
    ledger = GenesisLedger(str(tmp_path / "ledger.db"))
    workspace = WorkspaceState()
    panel = ComputationalWorkspace(workspace, ledger)
    qtbot.addWidget(panel)
    return panel, workspace, ledger


def test_defaults_are_metadata_only_and_modes_validate(qtbot, tmp_path, monkeypatch):
    panel, _, ledger = make_panel(qtbot, tmp_path, monkeypatch)
    panel.inputs.setCurrentIndex(1)
    req = panel._request()
    assert req.accession == "P08100"
    assert not req.include_structure and not req.include_pae
    panel.inputs.setCurrentIndex(0)
    panel.operation.setCurrentIndex(2)
    panel._start()
    assert panel.process is None
    assert "alleles" in panel.status.text()
    ledger.conn.close()


def test_completion_attaches_to_original_experiment(qtbot, tmp_path, monkeypatch):
    panel, workspace, ledger = make_panel(qtbot, tmp_path, monkeypatch)
    class Experiment:
        id = "original"
        observations = []
        def attach_observation(self, observation):
            self.observations.append(observation)
    original = Experiment()
    panel._experiment_at_start = original
    run = execute(StructureRequest(accession="P08100", experiment_id="original"),
                  AlphaFoldDBAdapter(lambda *a: b'[{"uniprotAccession":"P08100","latestVersion":6}]'), tmp_path / "runs")
    payload = json.dumps({"ok": True, "manifest_path": run.manifest_path, "sha256": run.sha256}).encode()
    panel.process = SimpleNamespace(readAllStandardOutput=lambda: payload, deleteLater=lambda: None)
    workspace.active_experiment = SimpleNamespace(id="different")
    panel._finished(0, QProcess.NormalExit)
    assert original.observations[0].experiment_id == "original"
    assert "original" in panel.status.text()
    assert panel.history.count() == 0  # Original experiment is outside the current project context.
    assert panel.results.toPlainText() == ""
    ledger.conn.close()


def test_cancel_does_not_register(qtbot, tmp_path, monkeypatch):
    panel, _, ledger = make_panel(qtbot, tmp_path, monkeypatch)
    killed = []
    panel.process = SimpleNamespace(kill=lambda: killed.append(True), readAllStandardOutput=lambda: b"", deleteLater=lambda: None)
    panel.cancel()
    panel._finished(-1, QProcess.CrashExit)
    assert killed
    assert not panel.busy
    assert "cancelled" in panel.status.text()
    assert ledger.conn.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0] == 1
    ledger.conn.close()


def test_computational_history_is_scoped_and_cleared_on_project_switch(qtbot,tmp_path,monkeypatch):
    from virtual_lab.computational.artifacts import register
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.gui.services.study_service import StudyService
    panel,workspace,ledger=make_panel(qtbot,tmp_path,monkeypatch)
    store=ExperimentStore();study=StudyService(workspace,ledger,store)
    try:
        a=study.create_project('A','computational_biology');ea=study.create_experiment(a,'A','Question')
        run=execute(StructureRequest(accession='P08100',experiment_id=ea),AlphaFoldDBAdapter(lambda *a:b'[{"uniprotAccession":"P08100","latestVersion":6}]'),tmp_path/'runs')
        register(run,ledger,store);panel._refresh_history();assert panel.history.count()==1
        panel._select_history(0);assert 'P08100' in panel.results.toPlainText()
        b=study.create_project('B','computational_biology');study.create_experiment(b,'B','Question')
        assert panel.history.count()==0 and panel.results.toPlainText()==''
        assert panel.completed_run is None and not panel.open_folder.isEnabled()
        study.open_project(a);assert panel.history.count()==1
    finally:store.close();ledger.conn.close()
