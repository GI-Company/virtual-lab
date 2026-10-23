"""Source-linked predictions and CSV data survive the complete study flow."""
import base64
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import zipfile
import pytest
from tests.projects.test_manual_research import study,plan,conclude
from tests.projects.test_study_lifecycle import service
from virtual_lab.extensions.records import validate_result
from virtual_lab.extensions.models import predict_linear
from virtual_lab.extensions.instruments import CSVInstrument
from virtual_lab.domain.epistemics import EpistemicState

EXAMPLES=Path(__file__).parents[2]/'examples/extensions'


def test_extension_study_roundtrip_retains_sources_and_citations(tmp_path,monkeypatch):
    svc=study(tmp_path/'source',monkeypatch);plan(svc)
    predicted=svc.save_predictor(EXAMPLES/'linear.json',{'concentration':3})
    imported=svc.save_csv_instrument(EXAMPLES/'instrument.json',EXAMPLES/'signal.csv')
    assert predicted.epistemic_state==EpistemicState.PREDICTED
    assert imported.epistemic_state==EpistemicState.UNKNOWN
    original={obs.observation_id:Path(obs.artifact_path).read_bytes() for obs in [predicted,imported]}
    assert base64.b64decode(svc.inspect(imported)['result']['raw_csv_base64'])==(EXAMPLES/'signal.csv').read_bytes()
    conclusion=conclude(svc,[predicted.observation_id,imported.observation_id])
    assert len(svc.inspect(conclusion)['result_refs'])==2
    package=tmp_path/'study.vlab-study';svc.export_study(package)
    recipient=service(tmp_path/'recipient',monkeypatch)
    exp=recipient.import_study(package)
    observations=recipient.store.get_observations_for_experiment(exp)
    assert len(observations)==4
    for obs in observations:
        recipient.inspect(obs)
        if obs.observation_id in original:
            assert Path(obs.artifact_path).read_bytes()==original[obs.observation_id]
            assert obs.epistemic_state in (EpistemicState.PREDICTED,EpistemicState.UNKNOWN)
    recipient.export_study(tmp_path/'second-export.vlab-study')


@pytest.mark.parametrize('kind',['predictive_model','instrument_import'])
def test_semantic_tampering_rejected_even_after_outer_hash_updated(tmp_path,monkeypatch,kind):
    svc=study(tmp_path/'source',monkeypatch)
    obs=svc.save_predictor(EXAMPLES/'linear.json',{'concentration':3}) if kind=='predictive_model' else svc.save_csv_instrument(EXAMPLES/'instrument.json',EXAMPLES/'signal.csv')
    record=svc.inspect(obs)
    if kind=='predictive_model': record['result']['outputs']['response']=999
    else: record['result']['samples'][0]['signal']=999
    raw=json.dumps(record).encode();Path(obs.artifact_path).write_bytes(raw)
    forged=replace(obs,artifact_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError,match='disagrees'): svc.inspect(forged)


def test_status_and_identity_cannot_be_promoted(tmp_path,monkeypatch):
    svc=study(tmp_path/'source',monkeypatch)
    result=predict_linear(EXAMPLES/'linear.json',{'concentration':3})
    result['epistemic_state']='MEASURED'
    before=svc.ledger.get_head().event_hash
    with pytest.raises(ValueError): svc._save_extension(result)
    assert svc.ledger.get_head().event_hash==before
    assert not (tmp_path/'source'/'notebook-extensions').exists()
    obs=svc.save_csv_instrument(EXAMPLES/'instrument.json',EXAMPLES/'signal.csv')
    with pytest.raises(ValueError,match='identity or status'):
        svc.inspect(replace(obs,epistemic_state=EpistemicState.PREDICTED))


def test_malformed_import_leaves_no_observation_or_success_event(tmp_path,monkeypatch):
    svc=study(tmp_path/'source',monkeypatch)
    bad=tmp_path/'bad.csv';bad.write_text('time,signal\n0,nan\n')
    before=svc.ledger.get_head().event_hash
    with pytest.raises(ValueError): svc.save_csv_instrument(EXAMPLES/'instrument.json',bad)
    assert svc.ledger.get_head().event_hash==before
    assert not svc.store.get_observations_for_experiment(svc.workspace.active_experiment.id)


def test_desktop_file_adapter_controls_attach_and_refresh(qtbot,tmp_path,monkeypatch):
    from virtual_lab.gui.projects_workspace import ProjectsWorkspace
    svc=study(tmp_path/'source',monkeypatch)
    panel=ProjectsWorkspace(svc.workspace,svc.ledger,store=svc.store);qtbot.addWidget(panel)
    ui=panel.extension_files
    ui.manifest.setText(str(EXAMPLES/'linear.json'));ui.inputs.setText('{"concentration":3}')
    ui.save_button.click()
    assert 'PREDICTED' in ui.status.text()
    assert panel.evidence_choices.count()==1
    ui.mode.setCurrentIndex(1)
    ui.manifest.setText(str(EXAMPLES/'instrument.json'));ui.csv_path.setText(str(EXAMPLES/'signal.csv'))
    ui.save_button.click()
    assert 'UNKNOWN' in ui.status.text() and panel.evidence_choices.count()==2
    assert len(svc.store.get_observations_for_experiment(svc.workspace.active_experiment.id))==2


def test_extension_csv_exports_retain_units_and_uncertain_status(tmp_path,monkeypatch):
    import csv
    svc=study(tmp_path/'source',monkeypatch)
    prediction=svc.save_predictor(EXAMPLES/'linear.json',{'concentration':3})
    source=svc.save_csv_instrument(EXAMPLES/'instrument.json',EXAMPLES/'signal.csv')
    for obs,expected_count in [(prediction,2),(source,6)]:
        path=tmp_path/(obs.observation_id+'.csv')
        svc.export_result_csv(obs.observation_id,path)
        with path.open() as stream: rows=list(csv.DictReader(stream))
        assert len(rows)==expected_count
        assert {r['observation_id'] for r in rows}=={obs.observation_id}
        assert {r['artifact_sha256'] for r in rows}=={obs.artifact_sha256}
        assert all(r['unit'] for r in rows)
        if obs is source: assert {r['epistemic_state'] for r in rows}=={'UNKNOWN'}
        else: assert [r['epistemic_state'] for r in rows]==['UNKNOWN','PREDICTED']
        original=path.read_bytes()
        with pytest.raises(ValueError): svc.export_result_csv(obs.observation_id,path)
        assert path.read_bytes()==original


def test_database_failure_retains_artifact_without_claiming_attachment(tmp_path,monkeypatch):
    svc=study(tmp_path/'source',monkeypatch)
    def unavailable(*args,**kwargs): raise RuntimeError('simulated database unavailable')
    monkeypatch.setattr(svc.store,'save_observation',unavailable)
    with pytest.raises(RuntimeError): svc.save_predictor(EXAMPLES/'linear.json',{'concentration':3})
    assert not svc.store.get_observations_for_experiment(svc.workspace.active_experiment.id)
    event=svc.ledger.get_head()
    assert event.event_type=='EXTENSION_ARTIFACT_RECORDED'
    path=Path(event.payload['artifact_path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==event.payload['artifact_sha256']


def test_import_rejects_rehashed_false_predictions_without_partial_rows(tmp_path,monkeypatch):
    svc=study(tmp_path/'source',monkeypatch)
    obs=svc.save_predictor(EXAMPLES/'linear.json',{'concentration':3})
    original=tmp_path/'original.vlab-study';svc.export_study(original)
    with zipfile.ZipFile(original) as package:
        entries={name:package.read(name) for name in package.namelist()}
    snapshot=json.loads(entries['study.json'])
    row=next(o for o in snapshot['observations'] if o['observation_id']==obs.observation_id)
    name=row['artifact_path'];payload=json.loads(entries[name]);payload['result']['outputs']['response']=99
    entries[name]=json.dumps(payload).encode();sha=hashlib.sha256(entries[name]).hexdigest()
    snapshot['files'][name]=row['artifact_sha256']=sha
    entries['study.json']=json.dumps(snapshot).encode()
    forged=tmp_path/'forged.vlab-study'
    with zipfile.ZipFile(forged,'w') as package:
        for name,raw in entries.items(): package.writestr(name,raw)
    recipient=service(tmp_path/'recipient',monkeypatch)
    before=recipient.ledger.get_head().event_hash
    with pytest.raises(ValueError,match='disagrees'): recipient.import_study(forged)
    assert not recipient.store.list_experiments()
    assert recipient.ledger.get_head().event_hash==before


def test_csv_export_escapes_formula_text_without_changing_scientific_source(tmp_path,monkeypatch):
    import csv
    svc=study(tmp_path/'source',monkeypatch)
    manifest=json.loads((EXAMPLES/'linear.json').read_text())
    manifest['outputs']=['=1+1'];manifest['coefficients']=[[-2]]
    path=tmp_path/'model.json';path.write_text(json.dumps(manifest))
    obs=svc.save_predictor(path,{'concentration':3})
    exported=tmp_path/'result.csv';svc.export_result_csv(obs.observation_id,exported)
    with exported.open() as stream: rows=list(csv.DictReader(stream))
    assert rows[-1]['channel']=="'=1+1" and float(rows[-1]['value'])==-5
    assert svc.inspect(obs)['result']['outputs']=={'=1+1':-5}


@pytest.mark.parametrize('kind',['predictive_model','instrument_import'])
def test_record_retains_original_adapter_fingerprint_after_installed_code_changes(tmp_path,monkeypatch,kind):
    svc=study(tmp_path/'source',monkeypatch)
    obs=svc.save_predictor(EXAMPLES/'linear.json',{'concentration':3}) if kind=='predictive_model' else svc.save_csv_instrument(EXAMPLES/'instrument.json',EXAMPLES/'signal.csv')
    before=Path(obs.artifact_path).read_bytes();record=svc.inspect(obs)
    replacement=tmp_path/'new-adapter.py';replacement.write_text('# Later adapter implementation\n')
    import virtual_lab.extensions.models as models
    import virtual_lab.extensions.instruments as instruments
    monkeypatch.setattr(models if kind=='predictive_model' else instruments,'__file__',str(replacement))
    assert svc.inspect(obs)['result']['adapter_sha256']==record['result']['adapter_sha256']
    assert Path(obs.artifact_path).read_bytes()==before


def test_header_verifies_non_simulation_records_before_claiming_integrity(qtbot,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QLabel
    from virtual_lab.gui.shell.main_window import VirtualLabApplication
    svc=study(tmp_path/'source',monkeypatch)
    label=QLabel();qtbot.addWidget(label)
    window=SimpleNamespace(workspace=svc.workspace,projects=SimpleNamespace(service=svc),ledger=svc.ledger,
        ledger_status=label,_refresh_pipeline=lambda obs:None)
    VirtualLabApplication._refresh_status(window)
    assert label.text().startswith('Ledger chain verified')
    obs=svc.save_predictor(EXAMPLES/'linear.json',{'concentration':3})
    VirtualLabApplication._refresh_status(window)
    assert label.text().startswith('1 study record(s) verified')
    Path(obs.artifact_path).write_bytes(b'tampered')
    VirtualLabApplication._refresh_status(window)
    assert label.text()=='INTEGRITY ERROR'


def test_predictor_replay_is_independent_of_blas_accumulation_order(tmp_path):
    manifest=json.loads((EXAMPLES/'linear.json').read_text())
    manifest.update(inputs=['a','b','c'],input_units=['dimensionless']*3,
        coefficients=[[1e16,1,-1e16]],intercept=[0])
    path=tmp_path/'cancellation.json';path.write_text(json.dumps(manifest))
    result=predict_linear(path,dict(a=1,b=1,c=1))
    assert result['outputs']=={'response':1}
    assert result['arithmetic']=='binary64-exact-linear-v1'
    validate_result(result)
