"""Two clients share actual research services; no hosted-auth claim is made."""
import base64
import importlib.abc
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import pytest
from virtual_lab.application.engine import ResearchEngine
from virtual_lab.application.client import ResearchClient
from virtual_lab.application.contracts import ExperimentRef

@pytest.fixture
def engine(tmp_path):
    value=ResearchEngine(tmp_path/'owned-instance')
    yield value
    value.close()


def request(client, operation, *, reference=None, **payload):
    return client.request({'instance_id':client.engine.instance_id,'operation':operation,
                           'reference':reference,'payload':payload})['data']


def context(engine):
    desktop=ResearchClient(engine,surface='desktop')
    web=ResearchClient(engine,surface='web')
    project=request(desktop,'project.create',name='Shared research',domain_id='physics_simulation')
    reference=request(web,'experiment.create',project_id=project['id'],name='Conditions',question='Software fixture?')
    return desktop,web,project,reference


def wait_job(client, reference, job_id):
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        job=request(client,'job.get',reference=reference,job_id=job_id)
        if job['state'] not in ('RUNNING','CANCELLING'):
            return job
        time.sleep(.01)
    raise AssertionError('Numerical worker did not finish')


def test_headless_import_does_not_load_qt_or_gui(tmp_path):
    code='''
import importlib.abc, sys
class NoGUI(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.startswith(('PySide6','virtual_lab.gui','google.genai','google.adk','mlx_lm')):
   raise ImportError('Headless boundary violated: '+fullname)
sys.meta_path.insert(0,NoGUI())
from virtual_lab.application.engine import ResearchEngine
engine=ResearchEngine(sys.argv[1])
p=engine.create_project('Headless')
e=engine.create_experiment(p['id'],'Plan','Test')
engine.save_plan(e,hypothesis='A',method='B',expected_outcome='C',acceptance_criteria='D')
assert len(engine.observations(e))==1
engine.close()
'''
    process=subprocess.run([sys.executable,'-c',code,str(tmp_path/'headless')],capture_output=True,text=True,timeout=20)
    assert process.returncode==0,process.stderr


def test_desktop_and_web_see_same_project_plan_and_cursor(engine):
    desktop,web,project,reference=context(engine)
    cursor=request(web,'changes.list',project_id=project['id'])['cursor']
    plan=request(desktop,'plan.save',reference=reference,hypothesis='Higher expression',
        method='Paired simulated control',expected_outcome='Higher model output',acceptance_criteria='Compare saved runs')
    assert request(web,'observations.list',reference=reference)[0]['observation_id']==plan['observation_id']
    changes=request(web,'changes.list',project_id=project['id'],cursor=cursor)
    assert changes['changes'][-1]['operation']=='plan_saved'
    assert request(desktop,'changes.list',project_id=project['id'],cursor=changes['cursor'])['changes']==[]
    assert request(web,'result.get',reference=reference,observation_id=plan['observation_id'])['record_type']=='plan'


def test_actual_jobs_comparison_idempotency_and_restart(engine,tmp_path):
    desktop,web,project,reference=context(engine)
    config={'model_id':'gene_expression','members':3,'duration_h':1,'concentration_um':0}
    first=request(web,'simulation.submit',reference=reference,config=config,request_id='same-request')
    repeated=request(desktop,'simulation.submit',reference=reference,config=config,request_id='same-request')
    assert repeated['id']==first['id']
    a=wait_job(desktop,reference,first['id'])
    assert a['state']=='COMPLETED',a
    assert not engine.settings.busy
    result=request(web,'result.get',reference=reference,observation_id=a['result_observation_id'])
    assert result['epistemic_state']=='SIMULATED' and result['numerical_check']['status']=='PASSED'
    second=request(desktop,'simulation.submit',reference=reference,
        config=dict(config,concentration_um=5),request_id='second')
    b=wait_job(web,reference,second['id'])
    assert b['state']=='COMPLETED',b
    comparison=request(web,'simulation.compare',reference=reference,
        first_observation=a['result_observation_id'],second_observation=b['result_observation_id'])
    assert comparison and any(row['delta']!=0 for row in comparison)
    with pytest.raises(ValueError,match='different inputs'):
        request(web,'simulation.submit',reference=reference,config=dict(config,seed=99),request_id='same-request')
    root=engine.root; identity=engine.instance_id
    engine.close()
    reopened=ResearchEngine(root)
    try:
        assert reopened.instance_id==identity
        assert reopened.job(reference,a['id']).state=='COMPLETED'
        assert len(reopened.observations(reference))==2
        assert reopened.result(reference,a['result_observation_id'])['id']==result['id']
    finally:
        reopened.close()


def test_job_cancelled_before_acceptance_does_not_create_result(engine):
    desktop,web,_,reference=context(engine)
    job=request(web,'simulation.submit',reference=reference,
        config={'model_id':'gene_expression','duration_h':1,'members':100},request_id='cancel')
    request(desktop,'job.cancel',reference=reference,job_id=job['id'])
    done=wait_job(web,reference,job['id'])
    assert done['state']=='CANCELLED'
    assert request(web,'observations.list',reference=reference)==[]
    assert not engine.settings.busy


def test_explicit_scope_rejects_cross_project_instance_result_and_job(engine):
    desktop,web,project,reference=context(engine)
    other=request(desktop,'project.create',name='Other')
    wrong=dict(reference,project_id=other['id'])
    with pytest.raises(ValueError,match='does not belong'):
        request(web,'experiment.get',reference=wrong)
    wrong=dict(reference,instance_id='another-instance')
    with pytest.raises(ValueError,match='different research instance'):
        request(web,'experiment.get',reference=wrong)
    with pytest.raises(ValueError,match='does not belong'):
        request(web,'result.get',reference=reference,observation_id='unknown')
    with pytest.raises(ValueError,match='does not belong'):
        request(web,'job.get',reference=reference,job_id='unknown')
    cursor=request(web,'changes.list',project_id=project['id'])['cursor']
    with pytest.raises(ValueError,match='cursor'):
        request(web,'changes.list',project_id=other['id'],cursor=cursor)


def test_ms_upload_and_original_bytes_are_shared_without_qt(engine):
    desktop,web,_,reference=context(engine)
    raw=b'mz,intensity\n101.5,3\n100.5,2\n'
    observation=request(web,'spectrum.import',reference=reference,source_base64=base64.b64encode(raw).decode(),
        dataset_id='synthetic',sample_id='synthetic',instrument_id='unverified',operator_id='tester',
        approved_nonconfidential=True,data_origin='synthetic')
    spectrum=request(desktop,'spectrum.get',reference=reference,run_id=observation['session_id'])
    assert spectrum['epistemic_state']=='UNKNOWN' and spectrum['total_peaks']==2
    assert spectrum['points'][0]=={'mz':'100.5','intensity':'2'}
    _,files,_=engine.ms.read(observation['session_id'])
    assert files['source.csv']==raw


def test_owner_thread_and_writer_lease_are_enforced(engine):
    failures=[]
    def invalid_thread():
        try: engine.projects()
        except Exception as exc: failures.append(exc)
    thread=threading.Thread(target=invalid_thread);thread.start();thread.join()
    assert failures and 'owner thread' in str(failures[0])
    with pytest.raises(ValueError,match='already open'):
        ResearchEngine(engine.root)


def test_artifacts_are_bound_to_instance_not_process_environment(engine,tmp_path,monkeypatch):
    desktop,web,_,reference=context(engine)
    monkeypatch.setenv('VIRTUALLAB_DATA_DIR',str(tmp_path/'unrelated'))
    plan=request(web,'plan.save',reference=reference,hypothesis='A',method='B',expected_outcome='C',acceptance_criteria='D')
    observation=engine.store.get_observations_for_experiment(reference['experiment_id'])[0]
    assert Path(observation.artifact_path).is_relative_to(engine.root)
    assert not (tmp_path/'unrelated').exists()


def test_interleaved_client_navigation_does_not_reassign_job(engine):
    desktop,web,project,reference=context(engine)
    submitted=request(web,'simulation.submit',reference=reference,
        config={'model_id':'gene_expression','duration_h':1,'members':2},request_id='scoped')
    other=request(desktop,'project.create',name='Separate project')
    other_ref=request(desktop,'experiment.create',project_id=other['id'],name='Other',question='Other fixture?')
    with pytest.raises(ValueError,match='does not belong'):
        request(desktop,'job.get',reference=other_ref,job_id=submitted['id'])
    completed=wait_job(web,reference,submitted['id'])
    assert completed['state']=='COMPLETED'
    assert request(desktop,'observations.list',reference=other_ref)==[]
    assert request(web,'observations.list',reference=reference)[0]['observation_id']==completed['result_observation_id']


@pytest.mark.parametrize('tamper',['state','config'])
def test_worker_output_is_validated_before_scientific_publication(engine,tamper):
    desktop,web,_,reference=context(engine)
    job=request(web,'simulation.submit',reference=reference,
        config={'model_id':'gene_expression','duration_h':1,'members':2},request_id='bad-result')
    handle=engine._processes[job['id']]
    handle['process'].wait(timeout=15)
    path=handle['directory']/'output.json'
    result=json.loads(path.read_text())
    if tamper=='state': result['epistemic_state']='MEASURED'
    else: result['config']['members']=999
    path.write_text(json.dumps(result))
    status=request(desktop,'job.get',reference=reference,job_id=job['id'])
    assert status['state']=='FAILED' and status['error_code']=='RESULT_REJECTED'
    assert request(web,'observations.list',reference=reference)==[]
    assert not engine.settings.busy


def test_job_deadline_releases_resources_without_a_result(engine):
    desktop,web,_,reference=context(engine)
    job=request(web,'simulation.submit',reference=reference,
        config={'model_id':'gene_expression','duration_h':1,'members':100},request_id='deadline')
    handle=engine._processes[job['id']]
    handle['started']-=handle['timeout']+1
    status=request(desktop,'job.get',reference=reference,job_id=job['id'])
    assert status['state']=='FAILED' and status['error_code']=='TIMEOUT'
    assert request(web,'observations.list',reference=reference)==[] and not engine.settings.busy


def test_owner_crash_recovers_job_as_interrupted_not_completed(tmp_path):
    root=tmp_path/'crash-instance'
    code='''
import json,os,sys
from pathlib import Path
from virtual_lab.application.engine import ResearchEngine
e=ResearchEngine(sys.argv[1])
p=e.create_project('Crash fixture')
r=e.create_experiment(p['id'],'Run','Restart test')
j=e.submit_simulation(r,{'model_id':'gene_expression','duration_h':1,'members':2},request_id='crash')
Path(sys.argv[1],'test-reference.json').write_text(json.dumps({'ref':r.model_dump(),'job':j.id}))
os._exit(0)
'''
    process=subprocess.run([sys.executable,'-c',code,str(root)],capture_output=True,text=True,timeout=15)
    assert process.returncode==0,process.stderr
    context_data=json.loads((root/'test-reference.json').read_text())
    resumed=ResearchEngine(root)
    try:
        job=resumed.job(context_data['ref'],context_data['job'])
        assert job.state=='INTERRUPTED' and job.error_code=='OWNER_RESTARTED'
        assert resumed.observations(context_data['ref'])==[]
        assert not resumed.settings.busy
    finally:
        resumed.close()
