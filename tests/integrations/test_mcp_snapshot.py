"""Snapshot authorization and integrity tests. No external connection or credentials."""
from pathlib import Path
import hashlib
import json
import pytest
from virtual_lab.core.ledger import GenesisLedger
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.pilots.datasets import MSDatasetService
from virtual_lab.integrations.mcp.snapshot import SnapshotReader, publish_snapshot
from virtual_lab.settings import SettingsRepository


@pytest.fixture
def snapshot(tmp_path):
    engine=tmp_path/'engine'; engine.mkdir()
    ledger=GenesisLedger(str(engine/'genesis.db'))
    store=ExperimentStore(str(engine/'experiments.db'))
    with store._conn:
        store._conn.execute("INSERT INTO projects(id,name,created_at) VALUES ('p','Shared demo','now')")
    store.save_experiment('e','','','',label='MS fixture',project_id='p')
    service=MSDatasetService(ledger,store,engine/'runs')
    source=tmp_path/'synthetic.csv'; source.write_text('mz,intensity\n101.5,3.25\n100.5,2\n101.5,1\n')
    obs=service.import_csv(source,experiment_id='e',dataset_id='synthetic',sample_id='synthetic',
        instrument_id='unverified',operator_id='private-operator',approved_nonconfidential=True,data_origin='synthetic')
    pin=publish_snapshot(service,obs.session_id,tmp_path/'snapshot')
    repo=SettingsRepository(tmp_path/'policy')
    reader=SnapshotReader(tmp_path/'snapshot',pin,repo.root)
    yield reader,repo,obs.session_id,service,tmp_path
    service.close(); store.close(); ledger.conn.close()


def allow(repo, *, spectrum=False, reports=False):
    data=repo.load().model_dump()
    data.update(mcp_enabled=True,allow_cloud=True,mcp_projects={'p':{'metadata':True,'spectrum':spectrum,'reports':reports}})
    repo.save(data)


def fingerprint(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_disabled_and_per_project_category_consent(snapshot):
    reader,repo,run,_,_=snapshot
    assert reader.list_projects()=={'projects':[]}
    with pytest.raises(PermissionError): reader.get_experiment('p','e')
    allow(repo)
    assert reader.list_projects()['projects'][0]['experiments'][0]['id']=='e'
    assert reader.get_experiment('p','e')['dataset_ids']==[run]
    assert reader.verify_dataset('p','e',run)['integrity']=='PASS'
    with pytest.raises(PermissionError): reader.get_spectrum('p','e',run)
    with pytest.raises(PermissionError): reader.get_report('p','e',run)
    with pytest.raises(PermissionError): reader.get_experiment('another-project','e')
    with pytest.raises(PermissionError): reader.verify_dataset('p','other',run)
    with pytest.raises(PermissionError): reader.verify_dataset('p','e','../../source.csv')


def test_exact_spectrum_pagination_and_read_only_summary(snapshot):
    reader,repo,run,service,root=snapshot
    allow(repo,spectrum=True,reports=True)
    before=fingerprint(root/'snapshot')
    events=len(service.events(run))
    points=reader.get_spectrum('p','e',run,offset=1,limit=1)
    assert points['total_peaks']==3 and points['points']==[{'mz':'101.5','intensity':'1'}]
    report=reader.get_report('p','e',run)
    assert report['epistemic_state']=='UNKNOWN' and report['summary']['total_intensity']=='6.25'
    assert report['review_status']=='not_included_in_snapshot' and report['workflow_check_status']=='INCOMPLETE'
    assert report['summary']['note']
    assert 'spectrum' not in report and 'manifest' not in report and 'provenance_events' not in report
    assert 'private-operator' not in json.dumps(report)
    sha=report.pop('report_sha256')
    from virtual_lab.pilots.ms_workflow import json_bytes
    assert hashlib.sha256(json_bytes(report)).hexdigest()==sha
    assert fingerprint(root/'snapshot')==before and len(service.events(run))==events
    assert reader.get_intent_status('p','e')['available'] is False


@pytest.mark.parametrize('setting',['mcp_enabled','allow_cloud','allow_exports','scope'])
def test_each_call_rechecks_revocation(snapshot,setting):
    reader,repo,run,_,_=snapshot
    allow(repo,spectrum=True,reports=True)
    assert reader.get_spectrum('p','e',run)['points']
    data=repo.load().model_dump()
    if setting=='scope': data['experiment_rules']={'e':{'mcp':False}}
    else: data[setting]=False
    repo.save(data)
    assert reader.list_projects()=={'projects':[]}
    with pytest.raises(PermissionError): reader.get_spectrum('p','e',run)
    with pytest.raises(PermissionError): reader.get_report('p','e',run)
    with pytest.raises(PermissionError): reader.verify_dataset('p','e',run)


@pytest.mark.parametrize('name',['source.csv','peaks.csv','manifest.json','snapshot.json'])
def test_tampered_files_fail_closed(snapshot,name):
    reader,repo,run,_,root=snapshot
    allow(repo,spectrum=True,reports=True)
    target=root/'snapshot'/name
    target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(ValueError): reader.get_spectrum('p','e',run)
    with pytest.raises(ValueError): reader.get_report('p','e',run)


def test_symlinks_and_non_public_sources_rejected(snapshot):
    reader,repo,run,service,root=snapshot
    allow(repo,spectrum=True)
    original=root/'snapshot'/'source.csv'
    other=root/'another.csv'; other.write_bytes(original.read_bytes())
    original.unlink(); original.symlink_to(other)
    with pytest.raises(ValueError): reader.get_spectrum('p','e',run)
    source=root/'lab.csv'; source.write_text('mz,intensity\n100,1\n')
    obs=service.import_csv(source,experiment_id='e',dataset_id='lab',sample_id='lab',instrument_id='unknown',
        operator_id='tester',approved_nonconfidential=True,data_origin='laboratory_supplied')
    with pytest.raises(PermissionError): publish_snapshot(service,obs.session_id,root/'blocked')
    assert not (root/'blocked').exists()


@pytest.mark.parametrize('offset,limit',[(-1,100),(0,0),(0,501),(True,1)])
def test_pagination_is_bounded(snapshot,offset,limit):
    reader,repo,run,_,_=snapshot
    allow(repo,spectrum=True)
    with pytest.raises(ValueError): reader.get_spectrum('p','e',run,offset,limit)
