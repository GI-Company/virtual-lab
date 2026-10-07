from copy import deepcopy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from virtual_lab.calibration.decay import fit_decay, normalize, load_benchmark, read_measurements


def synthetic(k=2):
    return [dict(sample_id=f'{rep}-{t}',replicate=str(rep),split=split,time_min=float(t),
                 value=100*math.exp(-k*t/60))
            for rep,split in [(1,'train'),(2,'holdout')] for t in (0,10,20,30)]


def test_known_rate_and_ode_check():
    result=fit_decay(synthetic(),{'value_scale':'linear','title':'Synthetic test'})
    assert result['parameters']['decay_per_hour']==pytest.approx(2,rel=1e-6)
    assert result['parameters']['half_life_min']==pytest.approx(30*math.log(2),rel=1e-6)
    assert result['metrics']['holdout']['rmse']<1e-8
    assert result['numerical_check']['passed']
    assert result['epistemic_state']=='INFERRED'


def test_holdout_does_not_change_fit():
    rows=synthetic(); a=fit_decay(rows,{'value_scale':'linear'})
    for r in rows:
        if r['split']=='holdout' and r['time_min']>0:r['value']*=4
    b=fit_decay(rows,{'value_scale':'linear'})
    assert a['parameters']==b['parameters']
    assert b['metrics']['holdout']['rmse']>a['metrics']['holdout']['rmse']


def test_scale_equivalence_and_arithmetic_baseline():
    linear=synthetic();linear.append(dict(linear[0],sample_id='technical',value=200))
    logs=[dict(r,value=math.log2(r['value'])) for r in linear]
    a,b=normalize(linear,'linear'),normalize(logs,'log2')
    np.testing.assert_allclose([r['relative_abundance'] for r in a],[r['relative_abundance'] for r in b])
    assert a[0]['relative_abundance']==pytest.approx(2/3)
    assert all('relative_abundance' not in r for r in linear)


@pytest.mark.parametrize('problem',['duplicate','split','baseline','nan','negative_time','scale','zero_intensity'])
def test_reject_invalid_measurements(problem):
    rows=synthetic();scale='linear'
    if problem=='duplicate':rows[1]['sample_id']=rows[0]['sample_id']
    if problem=='split':rows[1]['split']='holdout'
    if problem=='baseline':rows[0]['time_min']=1
    if problem=='nan':rows[1]['value']=float('nan')
    if problem=='negative_time':rows[1]['time_min']=-1
    if problem=='scale':scale='unknown'
    if problem=='zero_intensity':rows[1]['value']=0
    with pytest.raises(ValueError):fit_decay(rows,{'value_scale':scale})


def test_no_decay_boundary_is_not_fabricated_half_life():
    result=fit_decay(synthetic(0),{'value_scale':'linear'})
    assert result['parameters']['half_life_min'] is None
    assert result['validation_status']=='BOUNDARY_FIT'
    json.dumps(result,allow_nan=False)


def test_published_benchmark_split_and_negative_holdout_r_squared():
    metadata,rows=load_benchmark();result=fit_decay(rows,metadata)
    assert len(rows)==15
    assert len({r['sample_id'] for r in rows})==15
    assert result['metrics']['train']['n']==8 and result['metrics']['holdout']['n']==5
    assert result['metrics']['holdout']['r_squared']<0
    assert result['parameters']['half_life_min']==pytest.approx(37.167336,rel=1e-5)


def make_service(root,monkeypatch):
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from virtual_lab.gui.services.study_service import StudyService
    root.mkdir();monkeypatch.setenv('VIRTUALLAB_DATA_DIR',str(root))
    return StudyService(WorkspaceState(),GenesisLedger(str(root/'ledger.db')),ExperimentStore(str(root/'experiments.db')))


def test_saved_calibration_roundtrip_and_identity(tmp_path,monkeypatch):
    source=make_service(tmp_path/'source',monkeypatch)
    eid=source.create_experiment(source.create_project('Decay'),'PGK1','Does the fit transfer?')
    meta,rows=load_benchmark(); result=fit_decay(rows,meta,eid)
    obs=source.save_calibration(result)
    assert source.inspect(obs)['parameters']==result['parameters']
    with pytest.raises(ValueError,match='already saved'):source.save_calibration(result)
    bundle=source.export_study(tmp_path/'decay.vlab-study')
    target=make_service(tmp_path/'target',monkeypatch);target.import_study(bundle)
    other=target.workspace.active_experiment.observations[0]
    assert target.inspect(other)==result
    from dataclasses import replace
    with pytest.raises(ValueError,match='identity'):target.inspect(replace(other,session_id='wrong'))


def test_gui_fit_save_clear_and_restore(qtbot,tmp_path,monkeypatch):
    from virtual_lab.gui.calibration_workspace import CalibrationWorkspace
    svc=make_service(tmp_path/'gui',monkeypatch)
    svc.create_experiment(svc.create_project('Decay'),'PGK1','Transfer?')
    panel=CalibrationWorkspace(svc.workspace,svc);qtbot.addWidget(panel)
    panel._fit()
    assert panel.result['metrics']['holdout']['r_squared']<0
    assert panel.save_button.isEnabled()
    panel._save();assert not panel.save_button.isEnabled()
    result=panel.result
    svc.activate(None);assert panel.result is None and panel.table.rowCount()==0
    svc.workspace.calibrationResultChanged.emit(result)
    assert panel.table.rowCount()==15 and not panel.save_button.isEnabled()


def test_csv_requires_explicit_schema():
    with pytest.raises(ValueError,match='requires'):read_measurements(b'time,value\n0,1\n')


def test_local_gui_requires_scale_and_clears_stale_fit(qtbot,tmp_path,monkeypatch):
    from virtual_lab.gui.calibration_workspace import CalibrationWorkspace
    from virtual_lab.calibration.decay import DATA
    svc=make_service(tmp_path/'local_gui',monkeypatch)
    svc.create_experiment(svc.create_project('Decay'),'Local','Transfer?')
    panel=CalibrationWorkspace(svc.workspace,svc);qtbot.addWidget(panel)
    panel.mode.setCurrentIndex(1)
    panel.path.setText(str(DATA/'pgk1_decay.csv'))
    panel.context.setText('Yeast PGK1 transcription shutoff')
    panel.source.setText('Local copy of published benchmark')
    panel._fit();assert panel.result is None
    assert 'Declare the input scale' in panel.summary.text()
    panel.scale.setCurrentIndex(1);panel._fit()
    assert panel.result is not None
    prior=panel.result
    panel.context.setText('Changed context');assert panel.result is None
    svc.activate(None)
    with pytest.raises(ValueError,match='active experiment'):svc.save_calibration(prior)


def test_distinct_contexts_have_distinct_quantity_identity(tmp_path,monkeypatch):
    svc=make_service(tmp_path/'identity',monkeypatch)
    eid=svc.create_experiment(svc.create_project('Decay'),'Local','Transfer?')
    meta,rows=load_benchmark()
    first=svc.save_calibration(fit_decay(rows,meta,eid))
    meta=dict(meta,title='Different biological context')
    second=svc.save_calibration(fit_decay(rows,meta,eid))
    assert first.quantities[0].semantic_name != second.quantities[0].semantic_name
