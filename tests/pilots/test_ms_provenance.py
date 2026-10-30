import json
import pytest
from virtual_lab.pilots.schemas import PilotError


def import_run(service, tmp_path):
    source = tmp_path/'synthetic.csv'
    source.write_text('mz,intensity\n101,2\n100,1\n101,3\n')
    return service.import_csv(source, experiment_id='exp', dataset_id='synthetic-001', sample_id='sample',
        instrument_id='instrument', operator_id='operator', approved_nonconfidential=True)


def test_lifecycle_observation_and_review(service, tmp_path):
    from virtual_lab.gui.services.study_service import StudyService
    obs = import_run(service, tmp_path)
    assert obs.epistemic_state.value == 'UNKNOWN'
    assert len(service.store.get_observations_for_experiment('exp')) == 1
    assert StudyService.inspect(obs)['sample_id'] == 'sample'
    assert [e['event_type'] for e in service.events(obs.session_id)] == [
        'MS_DATASET_REGISTERED', 'MS_DATASET_VALIDATED', 'MS_DATASET_NORMALIZED', 'MS_DATASET_COMPLETED']
    assert service.reprocess(obs.session_id)['identical']
    service.review(obs.session_id, reviewer='lab-reviewer', approved=True, note='Workflow checked using synthetic data')
    assert service.events(obs.session_id)[-1]['payload']['epistemic_state'] == 'UNKNOWN'


def test_ledger_pin_rejects_valid_manifest_replacement(service, tmp_path):
    obs = import_run(service, tmp_path)
    from pathlib import Path
    path = Path(obs.artifact_path)
    manifest = json.loads(path.read_bytes())
    manifest['sample_id'] = 'forged'
    path.write_text(json.dumps(manifest))
    with pytest.raises(PilotError, match='independently recorded'):
        service.verify(obs.session_id)


def test_failure_and_restart_recovery(service, tmp_path, monkeypatch):
    original = service._event
    def fail(kind, payload, *args, **kwargs):
        if kind == 'MS_DATASET_COMPLETED':
            raise OSError('simulated commit failure')
        return original(kind, payload, *args, **kwargs)
    monkeypatch.setattr(service, '_event', fail)
    with pytest.raises(OSError):
        import_run(service, tmp_path)
    assert service.runs() == []
    assert service.store.get_observations_for_experiment('exp') == []
    assert not list(service.root.iterdir())
    original('MS_DATASET_REGISTERED', {'run_id':'interrupted'})
    service.recover()
    assert service.events('interrupted')[-1]['payload']['code'] == 'INTERRUPTED'
    size = len(service.events())
    service.recover()
    assert len(service.events()) == size


def test_invalid_source_records_rejection_without_filename(service, tmp_path):
    source = tmp_path/'private-name.csv'
    source.write_text('bad,data\n1,2\n')
    with pytest.raises(PilotError):
        service.import_csv(source, experiment_id='exp', sample_id='s', instrument_id='i', operator_id='o', approved_nonconfidential=True)
    last = service.events()[-1]
    assert last['event_type'] == 'MS_DATASET_REJECTED'
    assert 'private-name' not in str(last)
    assert not service.runs()


def test_three_dataset_limit_allows_explicit_reruns(service, tmp_path):
    source = tmp_path/'synthetic.csv'
    source.write_text('mz,intensity\n100,1\n')
    metadata = dict(experiment_id='exp', sample_id='s', instrument_id='i', operator_id='o', approved_nonconfidential=True)
    for name in ('one', 'two', 'three'):
        service.import_csv(source, dataset_id=name, **metadata)
    with pytest.raises(PilotError) as exc:
        service.import_csv(source, dataset_id='four', **metadata)
    assert exc.value.code == 'PILOT_DATASET_LIMIT'
    service.import_csv(source, dataset_id='one', **metadata)
    assert len(service.runs()) == 4


def test_real_process_interruption_recovered(tmp_path):
    import os, subprocess, sys
    from pathlib import Path
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.pilots.datasets import MSDatasetService
    script = r"""
import os,sys
from pathlib import Path
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.pilots.datasets import MSDatasetService
root=Path(sys.argv[1])
ledger=GenesisLedger(str(root/'genesis.db'))
store=ExperimentStore(str(root/'store.db'))
store.save_experiment('e','','','')
service=MSDatasetService(ledger,store,root/'runs')
original=service._event
def interrupt(kind,payload,*a,**k):
    if kind=='MS_DATASET_COMPLETED': os._exit(17)
    return original(kind,payload,*a,**k)
service._event=interrupt
source=root/'synthetic.csv'
source.write_text('mz,intensity\n100,1\n')
service.import_csv(source,experiment_id='e',sample_id='s',instrument_id='i',operator_id='o',approved_nonconfidential=True)
"""
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 17, result.stdout+result.stderr
    ledger=GenesisLedger(str(tmp_path/'genesis.db'))
    store=ExperimentStore(str(tmp_path/'store.db'))
    try:
        assert len(store.get_observations_for_experiment('e')) == 1
        service=MSDatasetService(ledger,store,tmp_path/'runs')
        assert service.runs() == []
        assert store.get_observations_for_experiment('e') == []
        assert not list((tmp_path/'runs').glob('*/manifest.json'))
        assert len(list((tmp_path/'runs').glob('*/manifest.interrupted.json'))) == 1
    finally:
        service.close()
        store.close()
        ledger.conn.close()
