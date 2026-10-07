from copy import deepcopy
import math
import numpy as np
import pytest
from scipy.integrate import solve_ivp

from virtual_lab.biology.objects import BiologicalSystem, starter_system
from virtual_lab.biology.simulation import BiologicalRun, simulate
from virtual_lab.biology.calibration_bridge import system_from_calibration
from virtual_lab.calibration.decay import load_benchmark, fit_decay
from test_objects import event, service


def test_maturation_transfers_pool_without_creating_total_protein():
    s=starter_system(model_id='maturing_gene_expression',initial_immature_protein=1,
        parameters=dict(transcription=0,translation=0,rna_decay=0,protein_decay=0,maturation=1))
    r=simulate(s,4,[],'exp');t=np.array(r.time_h)
    np.testing.assert_allclose(r.immature_protein,np.exp(-t),atol=1e-12)
    np.testing.assert_allclose(r.protein,1-np.exp(-t),atol=1e-12)
    np.testing.assert_allclose(np.array(r.protein)+r.immature_protein,1,atol=1e-12)


def test_maturation_after_translation_stop_and_ode_agreement():
    s=starter_system(model_id='maturing_gene_expression',initial_rna=1,initial_immature_protein=2)
    r=simulate(s,4,[event(0,'translation')],'exp')
    ode=solve_ivp(lambda t,y:[1-.5*y[0],-1.25*y[1],y[1]-.25*y[2]],(0,4),[1,2,0],t_eval=r.time_h,rtol=1e-10,atol=1e-12)
    np.testing.assert_allclose([r.rna,r.immature_protein,r.protein],ode.y,rtol=1e-8,atol=1e-10)
    assert r.protein[1]>0 and r.immature_protein[-1]<2


def test_maturation_continuation_and_total_matches_single_pool():
    s=starter_system(model_id='maturing_gene_expression')
    a=simulate(s,2,[event(1)],'exp');b=simulate(a.final_system,2,[],'exp')
    whole=simulate(s,4,[a.interventions[0]],'exp')
    old=simulate(starter_system(),4,[a.interventions[0]],'exp')
    np.testing.assert_allclose(np.array(whole.protein)+whole.immature_protein,old.protein,atol=1e-11)
    assert b.protein[-1]==pytest.approx(whole.protein[-1],rel=1e-12)
    assert b.immature_protein[-1]==pytest.approx(whole.immature_protein[-1],rel=1e-12)
    assert [o.id for o in b.final_system.objects]==[o.id for o in s.objects]


@pytest.mark.parametrize('fault',['missing_object','wrong_reference','missing_rate','wrong_units','extra_trace','missing_trace'])
def test_maturation_invalid_graph_and_trace(fault):
    raw=simulate(starter_system(model_id='maturing_gene_expression'),1,[],'exp').model_dump(mode='json')
    if fault=='missing_object':raw['initial_system']['objects'].pop()
    if fault=='wrong_reference':raw['initial_system']['mechanism']['immature_protein_id']='other'
    if fault=='missing_rate':raw['initial_system']['mechanism']['parameters'].pop('maturation')
    if fault=='wrong_units':raw['initial_system']['objects'][-1]['state']['units']='copies'
    if fault=='missing_trace':raw['immature_protein']=None
    if fault=='extra_trace':raw=simulate(starter_system(),1,[],'exp').model_dump(mode='json');raw['immature_protein']=raw['protein']
    with pytest.raises(ValueError):BiologicalRun.model_validate(raw)


def benchmark(eid='exp'):
    metadata,rows=load_benchmark()
    return fit_decay(rows,metadata,eid)


def test_calibrated_rate_predicts_holdout_without_refitting():
    fit=benchmark();s=system_from_calibration(fit);r=simulate(s,1,[],'exp')
    k=fit['parameters']['decay_per_hour']
    np.testing.assert_allclose(r.rna,np.exp(-k*np.array(r.time_h)),atol=1e-12)
    assert max(r.protein)==0
    assert s.mechanism.parameters['rna_decay'].evidence.state.value=='INFERRED'
    assert r.final_system.objects[1].state.evidence.state.value=='SIMULATED'
    holdout=[x for x in fit['measurements'] if x['split']=='holdout' and x['time_min']>0]
    errors=[simulate(s,x['time_min']/60,[],'exp').rna[-1]-x['relative_abundance'] for x in holdout]
    assert math.sqrt(np.mean(np.square(errors)))==pytest.approx(fit['metrics']['holdout']['rmse'],abs=1e-12)


@pytest.mark.parametrize('fault',['rate','metrics','context','protein','evidence','identity','experiment'])
def test_calibration_transfer_rejects_silent_changes(fault):
    fit=benchmark()
    if fault in ('rate','metrics'):
        if fault=='rate':fit['parameters']['decay_per_hour']+=.1
        else:fit['metrics']['holdout']['rmse']=0
        with pytest.raises(ValueError):system_from_calibration(fit)
        return
    raw=system_from_calibration(fit).model_dump(mode='json')
    if fault=='context':raw['context']='different conditions'
    if fault=='protein':raw['mechanism']['parameters']['translation']['value']=2
    if fault=='evidence':raw['mechanism']['parameters']['rna_decay']['evidence']['state']='MEASURED'
    if fault=='identity':raw['objects'][0]['identity']['label']='RHO'
    if fault=='experiment':
        with pytest.raises(ValueError):simulate(BiologicalSystem.model_validate(raw),1,[],'different')
        return
    with pytest.raises(ValueError):BiologicalSystem.model_validate(raw)


def test_maturation_gui_and_calibration_transfer_roundtrip(qtbot,tmp_path,monkeypatch):
    from virtual_lab.gui.biological_workspace import BiologicalWorkspace
    from virtual_lab.gui.calibration_workspace import CalibrationWorkspace
    svc=service(tmp_path/'source',monkeypatch)
    eid=svc.create_experiment(svc.create_project('Mechanisms'),'Maturation and calibration','What does each parameter support?')
    bio=BiologicalWorkspace(svc.workspace,svc);cal=CalibrationWorkspace(svc.workspace,svc)
    qtbot.addWidget(bio);qtbot.addWidget(cal)
    bio.maturation_enabled.setChecked(True);bio._create();bio._run();bio._save()
    first=bio.result
    assert bio.table.rowCount()==4 and first.immature_protein is not None
    fit=benchmark(eid);cal.show_result(fit)
    assert not cal.objects_button.isEnabled()
    cal._save();cal._objects()
    assert bio.system.calibration_result==fit and bio.table.rowCount()==3
    bio._run();bio._save();second=bio.result
    bundle=svc.export_study(tmp_path/'new.vlab-study')
    other=service(tmp_path/'target',monkeypatch);other.import_study(bundle)
    runs=[BiologicalRun.model_validate(other.inspect(o)) for o in other.workspace.active_experiment.observations if o.instrument_id=='biological_system']
    assert {r.id for r in runs}=={first.id,second.id}
    for r in runs:
        other.save_biological_run(simulate(r.final_system,1,[],eid).model_dump(mode='json'))


def test_legacy_snapshot_defaults_allow_continuation(tmp_path,monkeypatch):
    from pathlib import Path
    import hashlib,json
    svc=service(tmp_path/'legacy',monkeypatch)
    eid=svc.create_experiment(svc.create_project('Legacy'),'Old file','Continue?')
    a=simulate(starter_system(),1,[],eid);obs=svc.save_biological_run(a.model_dump(mode='json'))
    old=a.model_dump(mode='json');old.pop('immature_protein')
    for key in ('initial_system','final_system'):
        old[key].pop('calibration_result');old[key]['mechanism'].pop('immature_protein_id')
    raw=json.dumps(old).encode();Path(obs.artifact_path).write_bytes(raw)
    svc.store._conn.execute('UPDATE observations SET artifact_sha256=? WHERE observation_id=?',(hashlib.sha256(raw).hexdigest(),a.id));svc.store._conn.commit()
    svc.save_biological_run(simulate(a.final_system,1,[],eid).model_dump(mode='json'))


def test_zero_maturation_retains_immature_pool():
    s=starter_system(model_id='maturing_gene_expression',initial_immature_protein=2,
        parameters=dict(transcription=0,translation=0,rna_decay=0,protein_decay=.25,maturation=0))
    r=simulate(s,4,[],'exp')
    assert max(r.protein)==0
    assert r.immature_protein[-1]==pytest.approx(2*math.exp(-1),rel=1e-12)


def test_calibration_request_preserves_unsaved_biological_run(qtbot,tmp_path,monkeypatch):
    from virtual_lab.gui.biological_workspace import BiologicalWorkspace
    svc=service(tmp_path/'unsaved',monkeypatch)
    eid=svc.create_experiment(svc.create_project('Unsaved'),'Protected run','Keep result?')
    bio=BiologicalWorkspace(svc.workspace,svc);qtbot.addWidget(bio)
    bio._create();bio._run();pending=bio.result
    bio.show_draft(system_from_calibration(benchmark(eid)).model_dump(mode='json'))
    assert bio.result==pending and bio.save_button.isEnabled()
    assert 'Save the current biological run' in bio.status.text()
