"""Evidence integrity and recovery checks for the manual research workflow."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from tests.projects.test_study_lifecycle import service
from virtual_lab.gui.services.experiment_controller import ExperimentController
from virtual_lab.gui.services.simulation_runner import RunConfig, run_simulation
from virtual_lab.gui.services.research_outputs import compare_simulations


def plan(svc):
    return svc.save_research_plan('Induction increases protein.', 'Use matched assumed rates and paired control.',
                                  'Higher final protein.', 'Compare final protein medians.')


def run(svc):
    controller = ExperimentController(svc.workspace)
    controller.experiment_at_start = svc.workspace.active_experiment
    controller._complete(run_simulation(RunConfig(model_id='gene_expression', members=3, duration_h=1)))
    return next(o for o in reversed(svc.store.get_observations_for_experiment(svc.workspace.active_experiment.id))
                if o.instrument_id == 'simulation')


def study(root, monkeypatch):
    svc = service(root, monkeypatch)
    svc.create_experiment(svc.create_project('Manual study'), 'Induction', 'Does exposure change expression?')
    return svc


def conclude(svc, observations):
    return svc.save_research_conclusion('Interpretation within the assumed model.', 'No measured biological validation.',
                                       'inconclusive', observations)


def test_retrospective_plan_and_append_only_records(tmp_path, monkeypatch):
    svc = study(tmp_path/'source', monkeypatch)
    observation = run(svc)
    first = plan(svc)
    original = Path(first.artifact_path).read_bytes()
    conclusion = conclude(svc, [observation.observation_id])
    assert svc.inspect(conclusion)['planning_scope'] == 'retrospective'
    plan(svc)
    assert Path(first.artifact_path).read_bytes() == original
    assert len(svc.research_records()) == 3


def test_conclusions_require_verified_local_evidence_and_current_question(tmp_path, monkeypatch):
    svc = study(tmp_path/'source', monkeypatch)
    with pytest.raises(ValueError, match='Save a research plan'): conclude(svc, ['missing'])
    plan(svc)
    with pytest.raises(ValueError, match='Select one or more'): conclude(svc, [])
    obs = run(svc)
    other_id = svc.create_experiment(svc.workspace.active_experiment.project_id, 'Other', 'Another question')
    plan(svc)
    with pytest.raises(ValueError, match='in this experiment'): conclude(svc, [obs.observation_id])
    local = run(svc)
    svc.update_question('Changed question')
    with pytest.raises(ValueError, match='updated plan'): conclude(svc, [local.observation_id])
    plan(svc)
    Path(local.artifact_path).write_text('{}')
    with pytest.raises(ValueError, match='hash mismatch'): conclude(svc, [local.observation_id])
    assert svc.workspace.active_experiment.id == other_id
    assert not any(o.instrument_id == 'research_conclusion' for o in svc.workspace.active_experiment.observations)


def test_import_rejects_broken_citation_even_when_all_file_hashes_match(tmp_path, monkeypatch):
    svc = study(tmp_path/'source', monkeypatch)
    plan(svc); obs = run(svc); conclusion = conclude(svc, [obs.observation_id])
    package = svc.export_study(tmp_path/'good.vlab-study')
    with zipfile.ZipFile(package) as archive:
        files = {n:archive.read(n) for n in archive.namelist()}
    snapshot = json.loads(files['study.json'])
    row = next(o for o in snapshot['observations'] if o['observation_id'] == conclusion.observation_id)
    content = json.loads(files[row['artifact_path']]); content['result_refs'][0]['sha256'] = '0'*64
    raw = json.dumps(content).encode(); sha = hashlib.sha256(raw).hexdigest()
    files[row['artifact_path']] = raw
    row['artifact_sha256'] = sha; snapshot['files'][row['artifact_path']] = sha
    files['study.json'] = json.dumps(snapshot).encode()
    bad = tmp_path/'bad.vlab-study'
    with zipfile.ZipFile(bad, 'w') as archive:
        for name, raw in files.items(): archive.writestr(name, raw)
    recipient = study(tmp_path/'recipient', monkeypatch)
    before = len(recipient.store.list_experiments())
    with pytest.raises(ValueError, match='evidence reference'): recipient.import_study(bad)
    assert len(recipient.store.list_experiments()) == before
    assert not list((tmp_path/'recipient/imported-studies').glob('study-*'))


def test_csv_export_preserves_existing_files_and_uses_assignment(tmp_path, monkeypatch):
    svc = study(tmp_path/'source', monkeypatch)
    obs = run(svc)
    path = tmp_path/'data.csv'
    svc.export_result_csv(obs.observation_id, path)
    original = path.read_bytes()
    with pytest.raises(ValueError, match='existing files'): svc.export_result_csv(obs.observation_id, path)
    assert path.read_bytes() == original
    assert b'SIMULATED' in original and b'control' in original


def test_comparison_rejects_mismatched_model_and_time_span():
    a = run_simulation(RunConfig(model_id='gene_expression', members=2, duration_h=1))
    b = run_simulation(RunConfig(model_id='gene_expression', members=2, duration_h=2))
    with pytest.raises(ValueError, match='time span'): compare_simulations(a,b)
    b['model_version'] = 'other'
    with pytest.raises(ValueError, match='model/version'): compare_simulations(a,b)


def test_raw_sensor_session_can_be_reviewed_cited_and_transferred(tmp_path, monkeypatch):
    from virtual_lab.instruments.storage import JsonlMeasurementStore
    from virtual_lab.instruments.measurements import Measurement, ScientificState
    from virtual_lab.domain.assemblers import session_commit_to_observation
    svc = study(tmp_path/'source', monkeypatch)
    plan(svc)
    store = JsonlMeasurementStore()
    store.begin('synthetic-test-session', 'test-device', {'fixture': True})
    for i in range(2):
        store.append(Measurement(str(i),'synthetic-test-session',None,'test-device','test-sensor',
            i, i*1000000000, i*1000000000, i*1000000000,'ILLUMINANCE',{'illuminance':float(i)},
            {'illuminance':'lx'},None,None,ScientificState.MEASURED))
    committed = store.commit()
    assert committed['duration_s'] == 1.0
    obs = session_commit_to_observation(committed, svc.workspace.active_experiment.id)
    svc.store.save_observation(obs)
    assert svc.inspect(obs)['sample_count'] == 2
    conclude(svc,[obs.observation_id])
    package = svc.export_study(tmp_path/'raw.vlab-study')
    target = service(tmp_path/'recipient',monkeypatch);target.import_study(package)
    restored = next(o for o in target.workspace.active_experiment.observations if o.instrument_id=='test-device')
    assert target.inspect(restored)['epistemic_state']=='MEASURED'
    assert Path(restored.artifact_path).read_bytes()==Path(obs.artifact_path).read_bytes()
    original=Path(obs.artifact_path).read_bytes()
    with pytest.raises(FileExistsError): store.begin('synthetic-test-session','test-device',{})
    assert Path(obs.artifact_path).read_bytes()==original
