from copy import deepcopy
import math
import numpy as np
import pytest
from scipy.integrate import solve_ivp

from virtual_lab.biology.objects import starter_system, Intervention, BiologicalSystem
from virtual_lab.biology.simulation import simulate, BiologicalRun
from virtual_lab.domain.epistemics import EpistemicState


def event(time=2,target='transcription',multiplier=0):
    return Intervention(time_h=time,target=target,multiplier=multiplier,rationale='Test intervention')


def test_piecewise_shutoff_matches_analytic_and_independent_ode():
    s=starter_system();r=simulate(s,4,[event()],'exp')
    t=np.array(r.time_h)
    expected=np.where(t<=2,2*(1-np.exp(-.5*t)),2*(1-np.exp(-1))*np.exp(-.5*(t-2)))
    np.testing.assert_allclose(r.rna,expected,atol=1e-12)
    first=solve_ivp(lambda t,y:[1-.5*y[0],2*y[0]-.25*y[1]],(0,2),[0,0],rtol=1e-11,atol=1e-12)
    second=solve_ivp(lambda t,y:[-.5*y[0],2*y[0]-.25*y[1]],(2,4),first.y[:,-1],rtol=1e-11,atol=1e-12)
    np.testing.assert_allclose([r.rna[-1],r.protein[-1]],second.y[:,-1],rtol=1e-9)
    assert s.time_h==0 and s.history==()
    assert [o.id for o in s.objects]==[o.id for o in r.final_system.objects]
    assert all(o.state.evidence.state==EpistemicState.SIMULATED for o in r.final_system.objects if o.kind!='gene')
    assert r.final_system.objects[0].state.evidence.state==EpistemicState.MODEL_ASSUMPTION


def test_continuation_equals_single_run_and_preserves_event_history():
    s=starter_system();a=simulate(s,2,[event(1)],'exp');b=simulate(a.final_system,2,[],'exp')
    whole=simulate(s,4,[a.interventions[0]],'exp')
    np.testing.assert_allclose([b.rna[-1],b.protein[-1]],[whole.rna[-1],whole.protein[-1]],rtol=1e-12)
    assert b.initial_system.last_result_id==a.id
    assert b.final_system.history==a.final_system.history
    assert b.final_system.revision==2


def test_interventions_at_start_and_end_use_correct_boundary():
    s=starter_system()
    off=simulate(s,4,[event(0)],'exp');assert max(off.rna)==0 and max(off.protein)==0
    at_end=simulate(s,4,[event(4)],'exp');control=simulate(s,4,[],'exp')
    np.testing.assert_allclose(at_end.rna,control.rna,atol=1e-12)
    continuation=simulate(at_end.final_system,1,[],'exp')
    assert continuation.rna[-1]==pytest.approx(at_end.rna[-1]*math.exp(-.5),rel=1e-12)


def test_translation_inhibition_leaves_rna_unchanged():
    s=starter_system(initial_protein=2)
    r=simulate(s,4,[event(0,'translation')],'exp');control=simulate(s,4,[],'exp')
    np.testing.assert_allclose(r.rna,control.rna)
    assert r.protein[-1]==pytest.approx(2*math.exp(-1),rel=1e-12)


def test_zero_decay_equal_decay_and_zero_copies():
    s=starter_system(parameters=dict(transcription=1,translation=2,rna_decay=0,protein_decay=0))
    r=simulate(s,4,[],'exp');assert r.rna[-1]==pytest.approx(4);assert r.protein[-1]==pytest.approx(16)
    s=starter_system(parameters=dict(transcription=1,translation=2,rna_decay=.5,protein_decay=.5))
    r=simulate(s,4,[],'exp')
    assert r.protein[-1]==pytest.approx(8*(1-math.exp(-2)*(1+2)),rel=1e-12)
    raw=s.model_dump(mode='json');raw['objects'][0]['state']['abundance']=0
    r=simulate(BiologicalSystem.model_validate(raw),4,[],'exp');assert max(r.rna)==max(r.protein)==0


@pytest.mark.parametrize('fault',['duplicate_id','reference','units','rate','sequence','mechanism','future_history'])
def test_invalid_objects_rejected(fault):
    raw=starter_system().model_dump(mode='json')
    if fault=='duplicate_id':raw['objects'][1]['id']=raw['objects'][0]['id']
    if fault=='reference':raw['mechanism']['rna_id']='missing'
    if fault=='units':raw['mechanism']['parameters']['rna_decay']['units']='min'
    if fault=='rate':raw['mechanism']['parameters']['rna_decay']['value']=float('nan')
    if fault=='sequence':raw['objects'][0]['identity']['sequence']='NOTDNA'
    if fault=='mechanism':raw['mechanism']['model_id']='unknown'
    if fault=='future_history':raw['history']=[event().model_dump(mode='json')]
    with pytest.raises(ValueError):BiologicalSystem.model_validate(raw)


def test_names_do_not_change_equations_and_nested_mutations_revalidated():
    a=simulate(starter_system(gene_label='RHO'),4,[],'exp')
    b=simulate(starter_system(gene_label='PGK1'),4,[],'exp')
    np.testing.assert_array_equal(a.rna,b.rna)
    s=starter_system();s.mechanism.parameters.pop('rna_decay')
    with pytest.raises(ValueError):simulate(s,4,[],'exp')


@pytest.mark.parametrize('fault',['time','conflict','duration'])
def test_bad_intervention_schedule_rejected(fault):
    events=[event(5)] if fault=='time' else [event(1),event(1)] if fault=='conflict' else []
    with pytest.raises(ValueError):simulate(starter_system(),float('nan') if fault=='duration' else 4,events,'exp')


@pytest.mark.parametrize('fault',['identity','endpoint','evidence','history','multiplier'])
def test_malformed_saved_result_rejected(fault):
    raw=simulate(starter_system(),4,[event()],'exp').model_dump(mode='json')
    if fault=='identity':raw['final_system']['objects'][0]['identity']['label']='Changed'
    if fault=='endpoint':raw['rna'][-1]+=1
    if fault=='evidence':raw['final_system']['objects'][1]['state']['evidence']['state']='MEASURED'
    if fault=='history':raw['final_system']['history']=[]
    if fault=='multiplier':raw['final_system']['transcription_multiplier']=1
    with pytest.raises(ValueError):BiologicalRun.model_validate(raw)


def service(root,monkeypatch):
    from virtual_lab.core.ledger import GenesisLedger
    from virtual_lab.domain.experiment_store import ExperimentStore
    from virtual_lab.gui.shell.workspace_manager import WorkspaceState
    from virtual_lab.gui.services.study_service import StudyService
    root.mkdir();monkeypatch.setenv('VIRTUALLAB_DATA_DIR',str(root))
    return StudyService(WorkspaceState(),GenesisLedger(str(root/'ledger.db')),ExperimentStore(str(root/'experiments.db')))


def test_save_restore_export_import_and_continue(tmp_path,monkeypatch):
    svc=service(tmp_path/'source',monkeypatch)
    eid=svc.create_experiment(svc.create_project('Objects'),'Expression','How does RNA affect protein?')
    a=simulate(starter_system(),4,[event()],eid)
    svc.save_biological_run(a.model_dump(mode='json'))
    b=simulate(a.final_system,2,[],eid);svc.save_biological_run(b.model_dump(mode='json'))
    with pytest.raises(ValueError,match='already saved'):svc.save_biological_run(b.model_dump(mode='json'))
    bundle=svc.export_study(tmp_path/'objects.vlab-study')
    other=service(tmp_path/'target',monkeypatch);other.import_study(bundle)
    results=[other.inspect(o) for o in other.workspace.active_experiment.observations]
    assert results[-1]==b.model_dump(mode='json')
    c=simulate(BiologicalRun.model_validate(results[-1]).final_system,1,[],eid)
    other.save_biological_run(c.model_dump(mode='json'))
    assert c.final_system.revision==3
    other.activate(None)
    with pytest.raises(ValueError,match='active experiment'):other.save_biological_run(c.model_dump(mode='json'))


def test_parent_state_must_be_saved_and_exact(tmp_path,monkeypatch):
    svc=service(tmp_path/'parent',monkeypatch)
    eid=svc.create_experiment(svc.create_project('Objects'),'Expression','What changes?')
    a=simulate(starter_system(),4,[],eid);b=simulate(a.final_system,1,[],eid)
    with pytest.raises(ValueError,match='parent state'):svc.save_biological_run(b.model_dump(mode='json'))
    svc.save_biological_run(a.model_dump(mode='json'))
    changed=a.final_system.model_dump(mode='json');changed['objects'][1]['state']['abundance']+=1
    b=simulate(BiologicalSystem.model_validate(changed),1,[],eid)
    with pytest.raises(ValueError,match='parent state'):svc.save_biological_run(b.model_dump(mode='json'))


def test_gui_create_run_save_restore_and_clear(qtbot,tmp_path,monkeypatch):
    from virtual_lab.gui.biological_workspace import BiologicalWorkspace
    svc=service(tmp_path/'gui',monkeypatch)
    panel=BiologicalWorkspace(svc.workspace,svc);qtbot.addWidget(panel)
    panel._create();assert panel.system is None
    eid=svc.create_experiment(svc.create_project('Objects'),'Expression','What changes?')
    panel._create();assert panel.system is not None
    panel.target.setCurrentIndex(1);panel._run()
    first=panel.result;assert first.final_system.transcription_multiplier==0
    assert not panel.run_button.isEnabled() and panel.save_button.isEnabled()
    panel._save();assert panel.run_button.isEnabled()
    svc.activate(None);assert panel.system is None and panel.table.rowCount()==0
    svc.activate(eid);svc.workspace.biologicalResultChanged.emit(first.model_dump(mode='json'))
    assert panel.table.rowCount()==3 and panel.run_button.isEnabled() and not panel.save_button.isEnabled()
    panel.target.setCurrentIndex(0);panel._run()
    assert panel.result.initial_system.last_result_id==first.id
    assert panel.result.final_system.revision==2
