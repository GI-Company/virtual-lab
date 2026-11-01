"""Durable finite research plans for a trusted engine owner, not a hosted agent.

Call advance on the engine owner thread. No scheduler, network authority, model
inference, training permission or instrument access is implied by this API.
"""
from dataclasses import asdict
import hashlib
import json
import re
import time
import uuid

from virtual_lab.application.simulation_runner import RunConfig


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class ResearchCampaigns:
    def __init__(self, engine, *, clock=time.time):
        engine._check()
        self.engine, self.clock = engine, clock
        with engine.store._conn:
            engine.store._conn.execute('''CREATE TABLE IF NOT EXISTS research_campaigns (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, experiment_id TEXT NOT NULL,
                plan TEXT NOT NULL, plan_sha256 TEXT NOT NULL, checkpoint TEXT NOT NULL)''')

    def create(self, reference, *, objective, configs, max_runs, max_seconds, request_id=None):
        reference, _ = self.engine._experiment(reference)
        if not isinstance(objective, str) or not 1 <= len(objective.strip()) <= 2000:
            raise ValueError('Provide a bounded research objective')
        if type(max_runs) is not int or not 1 <= max_runs <= 20:
            raise ValueError('Run budget must be an integer from 1 to 20')
        if type(max_seconds) is not int or not 1 <= max_seconds <= 86400:
            raise ValueError('Wall-clock budget must be 1 to 86400 seconds')
        if not isinstance(configs, list) or not 1 <= len(configs) <= max_runs:
            raise ValueError('The complete plan must fit the approved run budget')
        normalized = []
        for value in configs:
            config = RunConfig(**value)
            config.validate()
            if config.backend != 'numpy':
                raise ValueError('Campaign qualification currently supports CPU numpy only')
            normalized.append(asdict(config))
        plan = {'format': 'virtuallab-research-plan-v1', 'reference': reference.model_dump(),
                'objective': objective.strip(), 'configs': normalized,
                'max_runs': max_runs, 'max_seconds': max_seconds}
        raw = encoded(plan)
        if len(raw.encode()) > 65536:
            raise ValueError('Research plan exceeds 64 KiB')
        digest = hashlib.sha256(raw.encode()).hexdigest()
        if request_id is not None:
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
                raise ValueError('A bounded idempotency request ID is required')
            identity = str(uuid.uuid5(uuid.NAMESPACE_URL, 'virtuallab-research-campaign-v1:' +
                                     encoded({'reference': reference.model_dump(), 'request_id': request_id})))
            previous = self.engine.store._conn.execute(
                'SELECT plan_sha256 FROM research_campaigns WHERE id=?', (identity,)).fetchone()
            if previous:
                existing = self.get(reference, identity)
                if existing['plan_sha256'] != digest or encoded(existing['plan']) != raw:
                    raise ValueError('Request ID already refers to a different research plan')
                return existing
        else:
            identity = str(uuid.uuid4())
        checkpoint = {'state': 'DRAFT', 'next_step': 0, 'active_job_id': None,
                      'observations': [], 'expires_at': None, 'error_code': None}
        with self.engine.store._conn:
            self.engine.store._conn.execute('INSERT INTO research_campaigns VALUES (?,?,?,?,?,?)',
                (identity, reference.project_id, reference.experiment_id, raw, digest, encoded(checkpoint)))
        self.engine._change('campaign_created', reference.project_id, reference.experiment_id,
                            campaign_id=identity, plan_sha256=digest)
        return self.get(reference, identity)

    def _load(self, reference, identity):
        reference, _ = self.engine._experiment(reference)
        row = self.engine.store._conn.execute('SELECT * FROM research_campaigns WHERE id=?', (identity,)).fetchone()
        if not row or row['project_id'] != reference.project_id or row['experiment_id'] != reference.experiment_id:
            raise ValueError('Campaign does not belong to this experiment')
        if hashlib.sha256(row['plan'].encode()).hexdigest() != row['plan_sha256']:
            raise ValueError('Campaign plan integrity check failed')
        plan = json.loads(row['plan'])
        if plan['reference'] != reference.model_dump():
            raise ValueError('Campaign reference does not match this instance')
        return reference, row, plan, json.loads(row['checkpoint'])

    def get(self, reference, identity):
        _, row, plan, checkpoint = self._load(reference, identity)
        return {'id': identity, 'plan': plan, 'plan_sha256': row['plan_sha256'], **checkpoint}

    def _save(self, reference, identity, checkpoint, operation):
        with self.engine.store._conn:
            self.engine.store._conn.execute('UPDATE research_campaigns SET checkpoint=? WHERE id=?',
                                           (encoded(checkpoint), identity))
        self.engine._change(operation, reference.project_id, reference.experiment_id,
                            campaign_id=identity, state=checkpoint['state'],
                            completed_steps=checkpoint['next_step'])
        return self.get(reference, identity)

    def start(self, reference, identity, *, approved_plan_sha256):
        reference, row, plan, state = self._load(reference, identity)
        if approved_plan_sha256 != row['plan_sha256']:
            raise ValueError('Approval must identify the complete saved plan')
        if state['state'] not in ('DRAFT', 'PAUSED'):
            raise ValueError('Only draft or paused campaigns may start')
        if state['expires_at'] is None:
            state['expires_at'] = self.clock() + plan['max_seconds']
        state['state'] = 'RUNNING'
        return self._save(reference, identity, state, 'campaign_started')

    def pause(self, reference, identity):
        reference, _, _, state = self._load(reference, identity)
        if state['state'] != 'RUNNING':
            raise ValueError('Only a running campaign may pause')
        state['state'] = 'PAUSED'
        return self._save(reference, identity, state, 'campaign_paused')

    def cancel(self, reference, identity):
        return self._stop(reference, identity, error_code=None)

    def stop_for_review(self, reference, identity, error_code):
        """Trusted host stop; keep reaping CANCELLING jobs after access is revoked."""
        if not isinstance(error_code, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', error_code):
            raise ValueError('Provide a bounded review error code')
        return self._stop(reference, identity, error_code=error_code)

    def _reconcile_job(self, reference, identity, plan, state):
        """Recover a submitted job without starting work or accepting its output."""
        index = state['next_step']
        if index >= len(plan['configs']):
            return
        row = self.engine.store._conn.execute(
            'SELECT * FROM application_jobs WHERE request_id=?',
            (f'campaign:{identity}:{index}',)).fetchone()
        if row is None:
            if state['active_job_id'] is not None:
                raise ValueError('Campaign job checkpoint does not match a submitted job')
            return
        self.engine._job_row(reference, row['id'])
        # Match the engine's persisted submission fingerprint before linking a
        # recovered request. Never attach a different configuration's result.
        payload = json.dumps(plan['configs'][index], sort_keys=True, allow_nan=False).encode()
        fingerprint = hashlib.sha256(reference.model_dump_json().encode() + payload).hexdigest()
        if row['request_sha256'] != fingerprint or state['active_job_id'] not in (None, row['id']):
            raise ValueError('Campaign job checkpoint does not match the approved step')
        recovered = state['active_job_id'] is None
        state['active_job_id'] = row['id']
        return recovered

    def _stop(self, reference, identity, *, error_code):
        reference, _, plan, state = self._load(reference, identity)
        if state['state'] in ('COMPLETED', 'CANCELLED', 'NEEDS_REVIEW'):
            return self.get(reference, identity)
        self._reconcile_job(reference, identity, plan, state)
        if state['active_job_id']:
            self.engine.cancel_job(reference, state['active_job_id'])
        state['error_code'] = state['error_code'] or error_code
        state['state'] = 'CANCELLING' if state['active_job_id'] else (
            'NEEDS_REVIEW' if state['error_code'] else 'CANCELLED')
        operation = 'campaign_review_required' if error_code else 'campaign_cancel_requested'
        return self._save(reference, identity, state, operation)

    def advance(self, reference, identity):
        """One bounded owner-thread tick. A separate host must schedule ticks."""
        reference, _, plan, state = self._load(reference, identity)
        if state['state'] not in ('RUNNING', 'PAUSED', 'CANCELLING'):
            return self.get(reference, identity)
        recovered = self._reconcile_job(reference, identity, plan, state)
        if state['state'] != 'CANCELLING' and self.clock() >= state['expires_at']:
            return self.stop_for_review(reference, identity, 'WALL_CLOCK_BUDGET')
        if state['active_job_id']:
            job = self.engine.job(reference, state['active_job_id'])
            if job.state in ('RUNNING', 'CANCELLING'):
                # A recovered live job needs its pointer persisted, including
                # while paused, so subsequent stops can reliably reap it.
                if recovered:
                    return self._save(reference, identity, state, 'campaign_job_recovered')
                return self.get(reference, identity)
            state['active_job_id'] = None
            if job.state == 'COMPLETED':
                state['observations'].append(job.result_observation_id)
                state['next_step'] += 1
            if state['state'] == 'CANCELLING':
                state['state'] = 'NEEDS_REVIEW' if state['error_code'] else 'CANCELLED'
            elif job.state != 'COMPLETED':
                state['state'], state['error_code'] = 'NEEDS_REVIEW', job.error_code or job.state
            else:
                if state['next_step'] == len(plan['configs']):
                    state['state'] = 'COMPLETED'
            return self._save(reference, identity, state, 'campaign_checkpointed')
        if state['state'] == 'CANCELLING':
            state['state'] = 'CANCELLED'
        elif state['state'] == 'PAUSED':
            return self.get(reference, identity)
        elif self.engine.settings.busy:
            # Another campaign or trusted operation owns the single worker.
            # Queueing here must not fail this campaign or replace that job.
            return self.get(reference, identity)
        else:
            index = state['next_step']
            # The stable request ID recovers a submission even if the owner dies
            # after job creation but before this checkpoint is saved.
            job = self.engine.submit_simulation(reference, plan['configs'][index],
                                               request_id=f'campaign:{identity}:{index}')
            state['active_job_id'] = job.id
        return self._save(reference, identity, state, 'campaign_advanced')
