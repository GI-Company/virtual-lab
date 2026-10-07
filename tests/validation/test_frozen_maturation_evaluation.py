import copy
import hashlib
import json
from pathlib import Path
import pytest
from virtual_lab.validation.maturation import Acquisition, Context, FrozenModel, Dataset, assess, create_report, validate_report, load_inputs


def inputs():
    context=Context(reporter='mEGFP',organism='E. coli',strain='MG1655',temperature_c=37,assay='live_cell')
    train=Acquisition(id='training',source_id='source',date='2020-01-01',biological_unit_id='culture1',source_hashes=('a'*64,),event_time_min=0,timing_basis='recorded',timing_source='Fixture timing record')
    evaluation=train.model_copy(update=dict(id='evaluation',date='2020-01-02',biological_unit_id='culture2',source_hashes=('b'*64,)))
    model=FrozenModel(label='Contract test only',source_report_sha256='c'*64,context=context,training_acquisitions=(train,),maturation_per_hour=2,immature_to_initial_mature_ratio=.2,valid_duration_h=1)
    raw='acquisition_id,series_id,time_min,fluorescence\nevaluation,one,0,10\nevaluation,one,10,11\nevaluation,one,20,11.5\nevaluation,one,30,11.8\n'
    dataset=Dataset(title='Contract test only',context=context,acquisitions=(evaluation,),csv_file='data.csv',csv_sha256=hashlib.sha256(raw.encode()).hexdigest(),previously_inspected=False,processing='Artificial fixture; gate mechanics only')
    return model,dataset,raw


def test_frozen_parameters_and_metrics():
    m,d,raw=inputs();before=m.model_dump()
    r=assess(m,d,raw)
    assert r['status']=='ELIGIBLE_BY_DECLARED_METADATA'
    assert r['metrics']['n_points']==3
    assert m.model_dump()==before
    changed=raw.replace('11.8','100')
    assess(m,d.model_copy(update={'csv_sha256':hashlib.sha256(changed.encode()).hexdigest()}),changed)
    assert m.model_dump()==before


@pytest.mark.parametrize('change,expected',[
    ({'id':'training'},'share an acquisition'),
    ({'date':'2020-01-01'},'share an acquisition'),
    ({'source_hashes':('a'*64,)},'source-file bytes'),
    ({'biological_unit_id':'culture1'},'share a biological unit'),
    ({'biological_unit_id':None},'identity is unavailable'),
    ({'timing_basis':'nominal'},'timing is assumed'),
    ({'timing_basis':'growth_proxy'},'timing is assumed')])
def test_acquisition_gates(change,expected):
    m,d,raw=inputs();a=d.acquisitions[0].model_copy(update=change)
    raw=raw.replace('evaluation,',a.id+',')
    d=d.model_copy(update=dict(acquisitions=(a,),csv_sha256=hashlib.sha256(raw.encode()).hexdigest()))
    r=assess(m,d,raw)
    assert r['status']=='EXPLORATORY_ONLY'
    assert any(expected in reason for reason in r['exclusions'])


@pytest.mark.parametrize('which',['context','synthetic','inspected','training_timing','training_unit','duration'])
def test_other_gates(which):
    m,d,raw=inputs()
    if which=='context':d=d.model_copy(update={'context':d.context.model_copy(update={'temperature_c':32})})
    if which=='synthetic':d=d.model_copy(update={'synthetic':True})
    if which=='inspected':d=d.model_copy(update={'previously_inspected':True})
    if which=='training_timing':m=m.model_copy(update={'training_acquisitions':(m.training_acquisitions[0].model_copy(update={'timing_basis':'unknown'}),)})
    if which=='training_unit':m=m.model_copy(update={'training_acquisitions':(m.training_acquisitions[0].model_copy(update={'biological_unit_id':None}),)})
    if which=='duration':m=m.model_copy(update={'valid_duration_h':.1})
    assert assess(m,d,raw)['status']=='EXPLORATORY_ONLY'


@pytest.mark.parametrize('event',[None,1,20])
def test_alignment_does_not_guess(event):
    m,d,raw=inputs();d=d.model_copy(update={'acquisitions':(d.acquisitions[0].model_copy(update={'event_time_min':event}),)})
    r=assess(m,d,raw)
    assert r['status']=='CANNOT_ALIGN' and r['metrics'] is None and r['rows']==[]


@pytest.mark.parametrize('replacement',['evaluation,one,0,11','evaluation,one,40,nan','evaluation,one,40,-1','evaluation,one','unknown,one,40,11'])
def test_bad_measurements(replacement):
    m,d,raw=inputs();raw+=replacement+'\n';d=d.model_copy(update={'csv_sha256':hashlib.sha256(raw.encode()).hexdigest()})
    with pytest.raises(ValueError):assess(m,d,raw)


def test_hash_and_path_checks(tmp_path):
    m,d,raw=inputs()
    with pytest.raises(ValueError):assess(m,d,raw+'\n')
    with pytest.raises(ValueError):Dataset.model_validate({**d.model_dump(),'csv_file':'../data.csv'})
    (tmp_path/'model.json').write_text(m.model_dump_json());(tmp_path/'dataset.json').write_text(d.model_dump_json());(tmp_path/'data.csv').write_bytes(raw.encode())
    assert load_inputs(tmp_path/'model.json',tmp_path/'dataset.json')==(m,d,raw)


@pytest.mark.parametrize('field',['metrics','status','csv'])
def test_report_recomputes(field):
    m,d,raw=inputs();p=create_report(m,d,raw,'experiment');validate_report(p)
    if field=='metrics':p['assessment']['metrics']['rmse']=0
    if field=='status':p['assessment']['status']='PASS'
    if field=='csv':p['csv_text']+='\n'
    with pytest.raises(ValueError):validate_report(p)


def service(root,monkeypatch):
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from virtual_lab.gui.services.study_service import StudyService
    root.mkdir();monkeypatch.setenv('VIRTUALLAB_DATA_DIR',str(root))
    return StudyService(WorkspaceState(),GenesisLedger(str(root/'ledger.db')),ExperimentStore(str(root/'experiments.db')))


@pytest.mark.parametrize('aligned',[True,False])
def test_study_roundtrip(tmp_path,monkeypatch,aligned):
    svc=service(tmp_path/'source',monkeypatch)
    exp=svc.create_experiment(svc.create_project('Validation'),'Frozen evaluation','Does eligibility hold?')
    m,d,raw=inputs()
    if not aligned:d=d.model_copy(update={'acquisitions':(d.acquisitions[0].model_copy(update={'event_time_min':None}),)})
    p=create_report(m,d,raw,exp);obs=svc.save_maturation_evaluation(p)
    assert svc.inspect(obs)==p
    with pytest.raises(ValueError):svc.save_maturation_evaluation(p)
    bundle=svc.export_study(tmp_path/'study.vlab-study');Path(obs.artifact_path).unlink()
    recipient=service(tmp_path/'recipient',monkeypatch);recipient.import_study(bundle)
    assert recipient.inspect(recipient.workspace.active_experiment.observations[0])==p


def test_gui_evaluate_save_restore_clear(qtbot,tmp_path,monkeypatch):
    from virtual_lab.gui.maturation_validation_workspace import MaturationValidationWorkspace
    svc=service(tmp_path/'source',monkeypatch)
    svc.create_experiment(svc.create_project('Validation'),'Evaluation','Question')
    m,d,raw=inputs()
    (tmp_path/'model.json').write_text(m.model_dump_json());(tmp_path/'dataset.json').write_text(d.model_dump_json());(tmp_path/'data.csv').write_text(raw)
    widget=MaturationValidationWorkspace(svc.workspace,svc);qtbot.addWidget(widget)
    widget.model_path.setText(str(tmp_path/'model.json'));widget.dataset_path.setText(str(tmp_path/'dataset.json'));widget._evaluate()
    assert widget.result is not None and widget.save_button.isEnabled()
    widget._save();assert not widget.save_button.isEnabled()
    obs=svc.workspace.active_experiment.observations[0];svc.workspace.validationResultChanged.emit(svc.inspect(obs))
    assert 'ELIGIBLE BY DECLARED METADATA' in widget.status.text()
    widget.model_path.setText('');assert widget.result is None


def test_normalization_overflow():
    m,d,raw=inputs();raw=raw.replace('0,10','0,1e-320')
    d=d.model_copy(update={'csv_sha256':hashlib.sha256(raw.encode()).hexdigest()})
    with pytest.raises(ValueError,match='Normalized'):assess(m,d,raw)


def test_duplicate_training_acquisitions():
    m,d,raw=inputs()
    with pytest.raises(ValueError,match='unique'):
        FrozenModel.model_validate({**m.model_dump(),'training_acquisitions':[m.training_acquisitions[0]]*2})
