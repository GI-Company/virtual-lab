import json
import zipfile
from pathlib import Path

import pytest

from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.gui.shell.workspace_manager import WorkspaceState
from virtual_lab.gui.services.study_service import StudyService
from virtual_lab.computational.artifacts import execute, register
from virtual_lab.computational.requests import StructureRequest
from virtual_lab.computational.adapters import AlphaFoldDBAdapter


def service(root, monkeypatch):
    root.mkdir(exist_ok=True)
    monkeypatch.setenv('VIRTUALLAB_DATA_DIR', str(root))
    return StudyService(WorkspaceState(), GenesisLedger(str(root/'genesis.db')),
                        ExperimentStore(str(root/'experiments.db')))


def prediction(root, svc, experiment_id=''):
    run = execute(StructureRequest(accession='P69905', experiment_id=experiment_id),
                  AlphaFoldDBAdapter(lambda *args: b'[{"uniprotAccession":"P69905","latestVersion":6}]'), root/'runs')
    register(run, svc.ledger, svc.store)
    return run


def test_non_rho_roundtrip_and_restart(tmp_path, monkeypatch):
    svc = service(tmp_path/'source', monkeypatch)
    project = svc.create_project('Hemoglobin research')
    exp_id = svc.create_experiment(project, 'Reference confidence', 'What is known about P69905?')
    run = prediction(tmp_path, svc)
    svc.attach_staged(run.read()['run_id'])
    # A retry must preserve the assignment rather than recreate staging.
    assert register(run, svc.ledger, svc.store).experiment_id == exp_id
    assert svc.store.staged_count() == 0
    svc.restore()
    assert svc.workspace.active_experiment.observations[0].artifact_sha256 == run.sha256
    bundle = svc.export_study(tmp_path/'hemoglobin.vlab-study')
    # Reopen in an independent store, with source files unavailable.
    run_id = run.read()['run_id']
    run_path = Path(run.manifest_path)
    original = run_path.read_bytes(); run_path.unlink()
    other = service(tmp_path/'recipient', monkeypatch)
    assert other.import_study(bundle) == exp_id
    obs = other.workspace.active_experiment.observations[0]
    assert other.inspect(obs)['request']['accession'] == 'P69905'
    assert Path(obs.artifact_path).read_bytes() == original
    other.store.close()
    other = service(tmp_path/'recipient', monkeypatch); other.restore()
    assert other.workspace.active_experiment.id == exp_id
    assert other.inspect(other.workspace.active_experiment.observations[0])['run_id'] == run_id


def test_import_rejects_corruption_without_creating_experiment(tmp_path, monkeypatch):
    svc = service(tmp_path/'source', monkeypatch)
    exp = svc.create_experiment(svc.create_project('Research'), 'Reference', 'Inspect reference')
    prediction(tmp_path, svc, exp)
    bundle = svc.export_study(tmp_path/'good.vlab-study')
    with zipfile.ZipFile(bundle) as z: files = {n: z.read(n) for n in z.namelist()}
    artifact = next(n for n in files if n != 'study.json')
    files[artifact] += b'changed'
    bad = tmp_path/'bad.vlab-study'
    with zipfile.ZipFile(bad, 'w') as z:
        for n, raw in files.items(): z.writestr(n, raw)
    target = service(tmp_path/'target', monkeypatch)
    with pytest.raises(ValueError, match='hash mismatch'): target.import_study(bad)
    assert target.store.list_experiments() == []
    assert target.projects() == []


def test_invalid_assignment_preserves_staging(tmp_path, monkeypatch):
    svc = service(tmp_path/'source', monkeypatch)
    run = prediction(tmp_path, svc)
    with pytest.raises(ValueError): svc.store.assign_staged_to_experiment(run.read()['run_id'], 'missing')
    assert svc.store.staged_count() == 1


def test_project_switch_clears_previous_result(tmp_path, monkeypatch):
    svc = service(tmp_path/'source', monkeypatch)
    p = svc.create_project('Independent studies')
    svc.create_experiment(p, 'First', 'First question')
    svc.workspace.current_result = {'old': 'result'}
    svc.create_experiment(p, 'Second', 'Second question')
    assert svc.workspace.current_result is None


def test_gui_creates_and_restores_project(qtbot, tmp_path, monkeypatch):
    from virtual_lab.gui.projects_workspace import ProjectsWorkspace
    svc = service(tmp_path/'gui', monkeypatch)
    panel = ProjectsWorkspace(svc.workspace, svc.ledger, store=svc.store)
    qtbot.addWidget(panel)
    panel.project_name.setText('Hemoglobin research'); panel._create_project()
    panel.experiment_name.setText('Confidence'); panel.question.setText('Inspect P69905'); panel._create_experiment()
    run = prediction(tmp_path, svc, svc.workspace.active_experiment.id)
    panel.refresh_results()
    panel.results.setCurrentRow(0)
    assert 'Artifact hashes verified' in panel.details.toPlainText()
    assert 'P69905' in panel.details.toPlainText()
    assert panel.projects.currentText() == 'Hemoglobin research'


def test_imported_predictions_available_with_explicit_origin(tmp_path, monkeypatch):
    from virtual_lab.computational.context import prediction_context
    svc = service(tmp_path/'source', monkeypatch)
    exp_id = svc.create_experiment(svc.create_project('Research'), 'Reference', 'Inspect P69905')
    prediction(tmp_path, svc, exp_id)
    bundle = svc.export_study(tmp_path/'context.vlab-study')
    other = service(tmp_path/'recipient', monkeypatch)
    other.import_study(bundle)
    context = prediction_context(other.ledger, other.store, exp_id)
    assert 'P69905' in context
    assert 'unsigned imported study' in context
    assert '"excluded_unverified_runs": []' in context


def test_simulation_captures_original_experiment_and_artifact(qtbot, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from virtual_lab.gui.services.experiment_controller import ExperimentController
    from virtual_lab.gui.services.simulation_runner import run_simulation, RunConfig
    svc = service(tmp_path/'simulation', monkeypatch)
    project = svc.create_project('Simulation tests')
    original = svc.create_experiment(project, 'Original', 'First scenario')
    controller = ExperimentController(svc.workspace)
    controller.experiment_at_start = svc.workspace.active_experiment
    svc.create_experiment(project, 'Different', 'Second scenario')
    result = run_simulation(RunConfig(members=2, duration_h=1))
    controller._complete(result)
    obs = svc.store.get_observations_for_experiment(original)[0]
    assert svc.inspect(obs)['id'] == result['id']
    assert svc.workspace.current_result is None
    assert not svc.store.get_observations_for_experiment(svc.workspace.active_experiment.id)


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'artifacts/../../escape', 'artifacts\\escape'])
def test_unsafe_package_paths_rejected(tmp_path, monkeypatch, name):
    target = service(tmp_path/'target', monkeypatch)
    bundle = tmp_path/'unsafe.vlab-study'
    with zipfile.ZipFile(bundle, 'w') as z: z.writestr(name, b'x')
    with pytest.raises(ValueError, match='Unsafe'): target.import_study(bundle)
    assert not target.store.list_experiments()


def test_gui_package_exchange_without_modal_file_picker(qtbot, tmp_path, monkeypatch):
    from virtual_lab.gui.projects_workspace import ProjectsWorkspace
    source = service(tmp_path/'source', monkeypatch)
    exp = source.create_experiment(source.create_project('Hemoglobin'), 'Reference', 'Inspect P69905')
    prediction(tmp_path, source, exp)
    panel = ProjectsWorkspace(source.workspace, source.ledger, store=source.store)
    qtbot.addWidget(panel)
    panel.package_path.setText(str(tmp_path/'gui.vlab-study'))
    panel._export()
    assert 'exported' in panel.status.text()
    target = service(tmp_path/'recipient', monkeypatch)
    imported = ProjectsWorkspace(target.workspace, target.ledger, store=target.store)
    qtbot.addWidget(imported)
    imported.package_path.setText(str(tmp_path/'gui.vlab-study'))
    imported._import()
    assert 'imported' in imported.status.text()
    imported.results.setCurrentRow(0)
    assert 'Artifact hashes verified' in imported.details.toPlainText()
    # Reimporting never overwrites an existing study.
    imported._import()
    assert 'already exists' in imported.status.text()
    assert len(target.store.list_experiments()) == 1
