"""Single-owner, Qt-independent research instance for trusted local adapters.

No network listener or account authentication is provided here. A hosted gateway
must authenticate users and authorize instance/project membership before calling.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from virtual_lab.application.contracts import ExperimentRef, ChangeCursor, JobStatus
from virtual_lab.application.study_service import StudyService
from virtual_lab.application.workspace import HeadlessWorkspace
from virtual_lab.application.run_store import RunStore
from virtual_lab.application.simulation_persistence import save_simulation
from virtual_lab.application.simulation_runner import RunConfig
from virtual_lab.application.research_outputs import compare_simulations
from virtual_lab.core.ledger import GenesisLedger, Actor
from virtual_lab.domain.experiment_store import ExperimentStore
from virtual_lab.pilots.lease import WorkspaceLease
from virtual_lab.pilots.storage import checked_path, read_bounded, write_private
from virtual_lab.pilots.ms_workflow import parse_centroids, canonical_decimal
from virtual_lab.pilots.datasets import MSDatasetService
from virtual_lab.intent.controller import IntentController
from virtual_lab.settings import SettingsRepository, SettingsService

MAX_JOB_BYTES = 16 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


class ResearchEngine:
    def __init__(self, root):
        self.root = checked_path(root)
        self._thread = threading.get_ident()
        self._closed = False
        self._processes = {}
        self.lease = WorkspaceLease(self.root)
        self.ledger = self.store = self.ms = None
        try:
            identity = self.root / 'instance.json'
            if not identity.exists():
                write_private(identity, json.dumps({'version':1, 'id':str(uuid.uuid4())}).encode())
            data = json.loads(read_bounded(identity, 1024))
            if set(data) != {'version','id'} or data['version'] != 1:
                raise ValueError('Unsupported research instance identity')
            self.instance_id = str(uuid.UUID(data['id']))
            self.ledger = GenesisLedger(str(self.root/'genesis.db'))
            self.store = ExperimentStore(str(self.root/'experiments.db'))
            self.workspace = HeadlessWorkspace()
            self.study = StudyService(self.workspace, self.ledger, self.store, artifact_root=self.root)
            self.settings = SettingsService(SettingsRepository(self.root))
            self.settings.context = lambda: (self.workspace.active_project_id,
                self.workspace.active_experiment.id if self.workspace.active_experiment else None)
            self.ms = MSDatasetService(self.ledger, self.store, self.root/'ms-runs', lease=self.lease)
            self.intent = IntentController(self.ledger, self.store, self.root/'intent',
                                           lease=self.lease, settings=self.settings)
            with self.store._conn:
                self.store._conn.execute('''CREATE TABLE IF NOT EXISTS application_jobs (
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, request_sha256 TEXT NOT NULL,
                    project_id TEXT NOT NULL, experiment_id TEXT NOT NULL, state TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    result_observation_id TEXT, error_code TEXT)''')
                interrupted = list(self.store._conn.execute(
                    "SELECT * FROM application_jobs WHERE state IN ('RUNNING','CANCELLING')"))
                self.store._conn.execute("UPDATE application_jobs SET state='INTERRUPTED',error_code='OWNER_RESTARTED',updated_at=? WHERE state IN ('RUNNING','CANCELLING')", (now(),))
            for job in interrupted:
                self._change('job_interrupted', job['project_id'], job['experiment_id'], job_id=job['id'])
        except BaseException:
            if self.ms is not None:
                self.ms.close()
            if self.store is not None:
                self.store.close()
            if self.ledger is not None:
                self.ledger.conn.close()
            self.lease.close()
            raise

    def _check(self):
        if self._closed:
            raise RuntimeError('Research instance is closed')
        if threading.get_ident() != self._thread:
            raise RuntimeError('Dispatch research operations on the instance owner thread')

    def _project(self, project_id):
        self._check()
        project = next((p for p in self.study.projects() if p['id']==project_id), None)
        if project is None:
            raise ValueError('Project does not belong to this instance')
        return project

    def _experiment(self, reference):
        reference = ExperimentRef.model_validate(reference)
        self._project(reference.project_id)
        if reference.instance_id != self.instance_id:
            raise ValueError('Reference belongs to a different research instance')
        experiment = self.store.get_experiment(reference.experiment_id)
        if not experiment or experiment['project_id'] != reference.project_id:
            raise ValueError('Experiment does not belong to this project')
        return reference, experiment

    def _activate(self, reference):
        reference, _ = self._experiment(reference)
        self.study.activate(reference.experiment_id)
        return reference

    def _change(self, operation, project_id, experiment_id=None, **identifiers):
        self.ledger.append(str(uuid.uuid4()), Actor(type='USER', id='local-instance-owner'),
            'APPLICATION_CHANGE_COMMITTED', {'format':'virtuallab-application-change-v1',
            'operation':operation, 'project_id':project_id, 'experiment_id':experiment_id, **identifiers})

    def projects(self):
        self._check()
        return self.study.projects()

    def create_project(self, name, domain_id='general'):
        self._check()
        project = self.study.create_project(name, domain_id)
        self._change('project_created', project)
        return self._project(project)

    def create_experiment(self, project_id, name, question):
        self._project(project_id)
        experiment = self.study.create_experiment(project_id, name, question)
        self._change('experiment_created', project_id, experiment)
        return ExperimentRef(instance_id=self.instance_id,project_id=project_id,experiment_id=experiment)

    def experiments(self, project_id):
        self._project(project_id)
        return [row for row in self.store.list_experiments() if row['project_id']==project_id]

    def experiment(self, reference):
        _, row = self._experiment(reference)
        return row

    def save_plan(self, reference, **fields):
        reference = self._activate(reference)
        observation = self.study.save_research_plan(**fields)
        self._change('plan_saved',reference.project_id,reference.experiment_id,
                     observation_id=observation.observation_id)
        return self.observation_metadata(observation)

    def save_conclusion(self, reference, **fields):
        reference = self._activate(reference)
        observation = self.study.save_research_conclusion(**fields)
        self._change('conclusion_saved',reference.project_id,reference.experiment_id,
                     observation_id=observation.observation_id)
        return self.observation_metadata(observation)

    @staticmethod
    def observation_metadata(observation):
        return {'observation_id':observation.observation_id,'experiment_id':observation.experiment_id,
                'instrument_id':observation.instrument_id,'kind':observation.kind.value,
                'epistemic_state':observation.epistemic_state.value,'artifact_sha256':observation.artifact_sha256,
                'session_id':observation.session_id}

    def observations(self, reference):
        reference, _ = self._experiment(reference)
        return [self.observation_metadata(o) for o in
                self.store.get_observations_for_experiment(reference.experiment_id)]

    def result(self, reference, observation_id):
        reference, _ = self._experiment(reference)
        observation = next((o for o in self.store.get_observations_for_experiment(reference.experiment_id)
                            if o.observation_id==observation_id),None)
        if observation is None:
            raise ValueError('Result does not belong to this experiment')
        return self.study.inspect(observation)

    def compare(self, reference, first_observation, second_observation):
        return compare_simulations(self.result(reference, first_observation),
                                   self.result(reference, second_observation))

    def import_spectrum(self, reference, source_bytes, **metadata):
        reference = self._activate(reference)
        if not isinstance(source_bytes,bytes) or not 0<len(source_bytes)<=16*1024*1024:
            raise ValueError('Provide bounded CSV bytes')
        folder = self.root/'uploads'; folder.mkdir(mode=0o700, exist_ok=True)
        path = folder/(str(uuid.uuid4())+'.csv')
        write_private(path,source_bytes)
        try:
            observation = self.ms.import_csv(path,experiment_id=reference.experiment_id,**metadata)
        finally:
            path.unlink(missing_ok=True)
        self._change('ms_imported',reference.project_id,reference.experiment_id,
                     observation_id=observation.observation_id,run_id=observation.session_id)
        return self.observation_metadata(observation)

    def spectrum(self, reference, run_id, *, offset=0, limit=100):
        reference, _ = self._experiment(reference)
        if type(offset) is not int or type(limit) is not int or offset<0 or not 1<=limit<=500:
            raise ValueError('Invalid spectrum page')
        if not any(r['run_id']==run_id for r in self.ms.runs(reference.experiment_id)):
            raise ValueError('Spectrum does not belong to this experiment')
        manifest, files, _ = self.ms.read(run_id)
        points = parse_centroids(files['peaks.csv'], normalized=True)
        return {'epistemic_state':'UNKNOWN','total_peaks':len(points),'offset':offset,
                'source_sha256':manifest['source_sha256'],
                'points':[{'mz':canonical_decimal(mz),'intensity':canonical_decimal(intensity)}
                          for mz,intensity in points[offset:offset+limit]]}

    def changes(self, project_id, cursor=None, *, limit=100):
        self._project(project_id)
        cursor = ChangeCursor.model_validate(cursor) if cursor is not None else ChangeCursor(
            instance_id=self.instance_id,project_id=project_id)
        if cursor.instance_id!=self.instance_id or cursor.project_id!=project_id or not 1<=limit<=100:
            raise ValueError('Invalid project change cursor')
        head = self.ledger.get_head()
        head_sequence = head.sequence if head else 0
        if cursor.sequence>head_sequence:
            raise ValueError('Change cursor is beyond the committed ledger')
        changes=[]; sequence=cursor.sequence
        for row in self.ledger.conn.execute('SELECT * FROM ledger_events WHERE sequence>? ORDER BY sequence LIMIT 1000', (cursor.sequence,)):
            sequence=row['sequence']
            if row['event_type']=='APPLICATION_CHANGE_COMMITTED':
                event=self.ledger._row_to_event(row)
                if event.payload.get('project_id')==project_id:
                    changes.append({'sequence':sequence,'timestamp_utc':event.timestamp_utc,**event.payload})
                    if len(changes)>=limit:
                        break
        return {'changes':changes,'cursor':ChangeCursor(instance_id=self.instance_id,
            project_id=project_id,sequence=sequence).model_dump(),'has_more':sequence<head_sequence}

    def submit_simulation(self, reference, config, *, request_id):
        reference, _ = self._experiment(reference)
        if not isinstance(request_id,str) or not 1<=len(request_id)<=100:
            raise ValueError('A bounded idempotency request ID is required')
        config = RunConfig(**config)
        config.validate()
        from dataclasses import asdict
        payload=json.dumps(asdict(config),sort_keys=True,allow_nan=False).encode()
        fingerprint=hashlib.sha256(reference.model_dump_json().encode()+payload).hexdigest()
        previous=self.store._conn.execute('SELECT * FROM application_jobs WHERE request_id=?',(request_id,)).fetchone()
        if previous:
            if previous['request_sha256']!=fingerprint:
                raise ValueError('Request ID already refers to different inputs or experiment')
            return self.job(reference,previous['id'])
        job_id=str(uuid.uuid4())
        self.settings.reserve(job_id)
        process=None; output=None
        try:
            directory=self.root/'jobs'/job_id
            directory.mkdir(parents=True,mode=0o700)
            output=(directory/'output.json').open('xb')
            process=subprocess.Popen([sys.executable,'-m','virtual_lab.application.simulation_worker'],
                stdin=subprocess.PIPE,stdout=output,stderr=subprocess.DEVNULL)
            process.stdin.write(payload); process.stdin.close()
            created=now()
            with self.store._conn:
                self.store._conn.execute('INSERT INTO application_jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (job_id,request_id,fingerprint,reference.project_id,reference.experiment_id,
                     'RUNNING',created,created,None,None))
            self._processes[job_id]={'process':process,'output':output,'directory':directory,
                'started':time.monotonic(),'timeout':self.settings.repository.load().timeout_seconds, 'config':config}
            self._change('job_submitted',reference.project_id,reference.experiment_id,job_id=job_id)
            return self.job(reference,job_id)
        except BaseException:
            if process is not None and process.poll() is None:
                process.kill(); process.wait(timeout=5)
            if output is not None:
                output.close()
            self.settings.release(job_id)
            raise

    def _job_row(self, reference, job_id):
        reference, _ = self._experiment(reference)
        row=self.store._conn.execute('SELECT * FROM application_jobs WHERE id=?',(job_id,)).fetchone()
        if not row or row['project_id']!=reference.project_id or row['experiment_id']!=reference.experiment_id:
            raise ValueError('Job does not belong to this experiment')
        return reference, row

    def _set_job(self, row, state, *, observation_id=None, error=None):
        with self.store._conn:
            self.store._conn.execute('UPDATE application_jobs SET state=?,updated_at=?,result_observation_id=?,error_code=? WHERE id=?',
                                     (state,now(),observation_id,error,row['id']))
        self._change('job_'+state.lower(),row['project_id'],row['experiment_id'],
                     job_id=row['id'],observation_id=observation_id)

    def job(self, reference, job_id):
        reference, row=self._job_row(reference,job_id)
        handle=self._processes.get(job_id)
        if handle:
            process=handle['process']
            oversized=(handle['directory']/'output.json').stat().st_size>MAX_JOB_BYTES
            timed_out=time.monotonic()-handle['started']>handle['timeout']
            if oversized or timed_out:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                self._set_job(row,'FAILED',error='OUTPUT_LIMIT' if oversized else 'TIMEOUT')
            elif process.poll() is None:
                return JobStatus(**{key:row[key] for key in JobStatus.model_fields if key in row.keys()})
            else:
                try:
                    if row['state']=='CANCELLING':
                        self._set_job(row,'CANCELLED')
                    elif process.returncode!=0:
                        self._set_job(row,'FAILED',error='WORKER_FAILED')
                    else:
                        raw=read_bounded(handle['directory']/'output.json',MAX_JOB_BYTES)
                        result=json.loads(raw)
                        config=handle['config']
                        if (result.get('model_id')!=config.model_id or
                            any(result.get('config',{}).get(key)!=getattr(config,key)
                                for key in ('members','seed','duration_h','concentration_um','dt_h'))):
                            raise ValueError('Worker result does not match its submitted job')
                        self._activate(reference)
                        _, observation=save_simulation(result,self.workspace.active_experiment,
                            self.workspace,self.store,run_store=RunStore(self.root))
                        self._set_job(row,'COMPLETED',observation_id=observation.observation_id)
                except Exception:
                    self._set_job(row,'FAILED',error='RESULT_REJECTED')
            handle['output'].close()
            self._processes.pop(job_id,None)
            self.settings.release(job_id)
            _,row=self._job_row(reference,job_id)
        return JobStatus(**{key:row[key] for key in JobStatus.model_fields if key in row.keys()})

    def cancel_job(self, reference, job_id):
        _,row=self._job_row(reference,job_id)
        handle=self._processes.get(job_id)
        if handle and row['state']=='RUNNING':
            self._set_job(row,'CANCELLING')
            if handle['process'].poll() is None:
                handle['process'].kill()
        return self.job(reference,job_id)

    def close(self):
        if self._closed:
            return
        self._check()
        for job_id in list(self._processes):
            row=self.store._conn.execute('SELECT * FROM application_jobs WHERE id=?',(job_id,)).fetchone()
            ref=ExperimentRef(instance_id=self.instance_id,project_id=row['project_id'],experiment_id=row['experiment_id'])
            self.cancel_job(ref,job_id)
            if job_id in self._processes:
                self._processes[job_id]['process'].wait(timeout=5)
                self.job(ref,job_id)
        self.settings.cancel()
        self.ms.close()
        self.store.close()
        self.ledger.conn.close()
        self.lease.close()
        self._closed=True
