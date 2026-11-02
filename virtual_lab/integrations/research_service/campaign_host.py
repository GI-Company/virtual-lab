"""Opt-in, single-owner campaign service with expiring execution authority.

The host schedules finite acknowledged plans, not model-generated experiments.
It persists no bearer credentials and never extends a token's original expiry.
"""
import asyncio
from dataclasses import asdict
import hashlib
import json
import time
import uuid

import numpy as np

from virtual_lab.application.campaigns import ResearchCampaigns, encoded
from virtual_lab.application.contracts import ExperimentRef
from virtual_lab.application.research_outputs import simulation_arrays
from virtual_lab.application.simulation_runner import RunConfig
from virtual_lab.pilots.ms_workflow import json_bytes

from .auth import Principal
from .policy import NotFound, Unavailable
from .reader import Reader, select


class CampaignConflict(ValueError):
    """A retry changed its payload or an operation conflicts with saved state."""


class CampaignReader(Reader):
    MAX_PROJECT_CAMPAIGNS = 1000
    MAX_ACTIVE_CAMPAIGNS = 16

    def __init__(self, root, policy_path, audit_path, *, tick_interval=.2):
        super().__init__(root, policy_path, audit_path)
        if not isinstance(tick_interval, (float, int)) or not .01 <= tick_interval <= 5:
            raise ValueError('Tick interval must be between .01 and 5 seconds')
        self.tick_interval = tick_interval
        self._ticker = None
        self._faulted = False

    def _open(self):
        super()._open()
        try:
            self.campaigns = ResearchCampaigns(self.engine)
            with self.engine.store._conn:
                self.engine.store._conn.execute('''CREATE TABLE IF NOT EXISTS service_campaigns (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, experiment_id TEXT NOT NULL,
                    creator_subject TEXT NOT NULL, tenant_id TEXT NOT NULL,
                    request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
                    runner_subject TEXT, token_id TEXT, expires INTEGER,
                    UNIQUE(creator_subject, request_id))''')
                self.engine.store._conn.execute('''CREATE TABLE IF NOT EXISTS service_campaign_commands (
                    actor TEXT NOT NULL, request_id TEXT NOT NULL, campaign_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, status TEXT NOT NULL,
                    PRIMARY KEY(actor, request_id))''')
        except BaseException:
            self.engine.close()
            self.engine = None
            raise

    async def start(self):
        await super().start()
        self._ticker = asyncio.create_task(self._run_ticks())

    async def close(self):
        if self._ticker is not None:
            self._ticker.cancel()
            try:
                await self._ticker
            except asyncio.CancelledError:
                pass
            self._ticker = None
        await super().close()

    async def _run_ticks(self):
        while True:
            await asyncio.sleep(self.tick_interval)
            # Await every dispatch: at most one scheduled tick is queued. Close
            # is queued behind an in-flight tick on this same owner executor.
            await asyncio.get_running_loop().run_in_executor(self.pool, self._safe_tick)

    async def write(self, principal, operation, scope, body, request_id, surface='unspecified'):
        if self.pending >= 8:
            raise Unavailable()
        self.pending += 1
        future = asyncio.get_running_loop().run_in_executor(
            self.pool, self._write, principal, operation, scope, body, request_id, surface)
        future.add_done_callback(lambda _: setattr(self, 'pending', self.pending - 1))
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=15)
        except asyncio.TimeoutError as exc:
            raise Unavailable() from exc

    def _campaign_grant(self, principal, scope, category, *, execute=False):
        grant = self._grant(principal, scope, category)
        if execute:
            try:
                self.engine.settings.repository.require('tools', scope['project_id'],
                    scope.get('experiment_id'), route='cloud')
            except PermissionError as exc:
                raise NotFound() from exc
        return grant

    def _binding(self, scope):
        row = self.engine.store._conn.execute('SELECT * FROM service_campaigns WHERE id=?',
            (scope['campaign_id'],)).fetchone()
        if (row is None or row['project_id'] != scope['project_id'] or
                row['experiment_id'] != scope['experiment_id']):
            raise NotFound()
        return row

    def _view(self, reference, binding):
        data = self.campaigns.get(reference, binding['id'])
        return {**data, 'authorization_expires_at': binding['expires'],
                'host_status': 'UNAVAILABLE' if self._faulted else 'READY'}

    def _summary(self, reference, binding):
        data = self._view(reference, binding)
        return {**select(data, 'id', 'state', 'plan_sha256', 'next_step', 'error_code',
                        'expires_at', 'authorization_expires_at', 'host_status'),
                'total_steps': len(data['plan']['configs'])}

    def _pack(self, data):
        raw = json_bytes(data)
        if len(raw) > 1024 * 1024:
            raise Unavailable()
        return raw, hashlib.sha256(raw).hexdigest()

    def _read(self, principal, operation, scope, query, request_id, surface):
        if operation not in ('campaign.get', 'campaign.list', 'campaign.results'):
            return super()._read(principal, operation, scope, query, request_id, surface)
        try:
            self.engine._check()
            grant = self._campaign_grant(principal, scope, 'campaign_read')
            reference = self._reference(scope)
            if operation == 'campaign.list':
                rows = self.engine.store._conn.execute('''SELECT s.* FROM service_campaigns s
                    JOIN research_campaigns c ON c.id=s.id
                    WHERE s.project_id=? AND s.experiment_id=? AND s.tenant_id=? ORDER BY s.rowid
                    LIMIT ? OFFSET ?''', (scope['project_id'], scope['experiment_id'], grant.tenant_id,
                    query.get('limit', 100) + 1, query.get('offset', 0))).fetchall()
                limit = query.get('limit', 100)
                data = {'reference': reference.model_dump(),
                    'campaigns': [self._summary(reference, row) for row in rows[:limit]],
                    'offset': query.get('offset', 0), 'has_more': len(rows) > limit}
            else:
                binding = self._binding(scope)
                if binding['tenant_id'] != grant.tenant_id:
                    raise NotFound()
                data = self._view(reference, binding)
                if operation == 'campaign.results':
                    data = self._results(reference, data)
            if self._campaign_grant(principal, scope, 'campaign_read') != grant:
                raise NotFound()
            output = self._pack(data)
            self._audit(principal, operation, scope, 'ALLOWED', request_id, surface,
                        'SIMULATED' if operation == 'campaign.results' else None)
            return output
        except (NotFound, ValueError, KeyError, TypeError) as exc:
            self._audit(principal, operation, scope, 'DENIED', request_id, surface)
            raise NotFound() from exc
        except Exception as exc:
            self._audit(principal, operation, scope, 'UNAVAILABLE', request_id, surface)
            raise Unavailable() from exc

    def _validate_create(self, body):
        if not isinstance(body, dict) or set(body) != {'objective', 'configs', 'max_runs', 'max_seconds', 'request_id'}:
            raise ValueError('Invalid campaign request fields')
        if not isinstance(body['request_id'], str) or str(uuid.UUID(body['request_id'])) != body['request_id']:
            raise ValueError('request_id must be a canonical UUID')
        objective = body['objective']
        if not isinstance(objective, str) or not 1 <= len(objective.strip()) <= 2000:
            raise ValueError('Provide a bounded objective')
        if type(body['max_runs']) is not int or not 1 <= body['max_runs'] <= 20:
            raise ValueError('Invalid run budget')
        if type(body['max_seconds']) is not int or not 1 <= body['max_seconds'] <= 86400:
            raise ValueError('Invalid wall-clock budget')
        if not isinstance(body['configs'], list) or not 1 <= len(body['configs']) <= body['max_runs']:
            raise ValueError('The complete plan must fit the run budget')
        configs = []
        for value in body['configs']:
            if not isinstance(value, dict):
                raise ValueError('Invalid numerical configuration')
            config = RunConfig(**value)
            config.validate()
            if config.backend != 'numpy':
                raise ValueError('Only the CPU numpy backend is qualified')
            configs.append(asdict(config))
        return {'objective': objective.strip(), 'configs': configs,
                'max_runs': body['max_runs'], 'max_seconds': body['max_seconds']}

    def _create(self, principal, reference, grant, body):
        fields = self._validate_create(body)
        payload = encoded({'reference': reference.model_dump(), **fields})
        if len(payload.encode()) > 65536:
            raise ValueError('Campaign exceeds 64 KiB')
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()
        conn = self.engine.store._conn
        old = conn.execute('SELECT * FROM service_campaigns WHERE creator_subject=? AND request_id=?',
            (principal.subject, body['request_id'])).fetchone()
        if old and (old['request_sha256'] != fingerprint or old['tenant_id'] != grant.tenant_id):
            raise CampaignConflict('Request ID already identifies a different campaign')
        if old:
            return self._view(reference, old)
        count = conn.execute('SELECT COUNT(*) FROM service_campaigns WHERE project_id=?',
            (reference.project_id,)).fetchone()[0]
        if count >= self.MAX_PROJECT_CAMPAIGNS:
            raise CampaignConflict('Project campaign limit reached')
        # The controller's deterministic ID closes the crash window between its
        # committed creation and this service binding. Retrying recreates no job.
        controller_key = hashlib.sha256(encoded([principal.subject, body['request_id']]).encode()).hexdigest()
        data = self.campaigns.create(reference, request_id=controller_key, **fields)
        with conn:
            conn.execute('INSERT INTO service_campaigns VALUES (?,?,?,?,?,?,?,?,?,?)',
                (data['id'], reference.project_id, reference.experiment_id, principal.subject,
                 grant.tenant_id, body['request_id'], fingerprint, None, None, None))
        return self._view(reference, conn.execute('SELECT * FROM service_campaigns WHERE id=?',
                                                  (data['id'],)).fetchone())

    def _write(self, principal, operation, scope, body, request_id, surface):
        try:
            self.engine._check()
            if self._faulted:
                raise Unavailable()
            if operation not in ('campaign.create', 'campaign.start', 'campaign.pause', 'campaign.cancel'):
                raise NotFound()
            grant = self._campaign_grant(principal, scope, 'campaign_write',
                                         execute=operation in ('campaign.create', 'campaign.start'))
            if self._campaign_grant(principal, scope, 'campaign_read') != grant:
                raise NotFound()
            try:
                reference = self._reference(scope)
            except ValueError as exc:
                raise NotFound() from exc
            binding = None
            if operation != 'campaign.create':
                binding = self._binding(scope)
                if binding['tenant_id'] != grant.tenant_id:
                    raise NotFound()
            if operation == 'campaign.start':
                if self._campaign_grant(principal, scope, 'campaign_run', execute=True) != grant:
                    raise NotFound()
                if not isinstance(body, dict) or set(body) != {'approved_plan_sha256', 'request_id'}:
                    raise ValueError('Start requires the acknowledged plan digest')
            elif operation in ('campaign.pause', 'campaign.cancel') and set(body) != {'request_id'}:
                raise ValueError('This operation takes no arguments')
            # Audit is durable before any mutation. Never record bodies, tokens,
            # objectives or numerical inputs in the service audit.
            self._audit(principal, operation, scope, 'INTENT', request_id, surface)
            if operation == 'campaign.create':
                data = self._create(principal, reference, grant, body)
            else:
                if self._command_replay(principal, operation, scope, body):
                    data = self._view(reference, binding)
                    if self._campaign_grant(principal, scope, 'campaign_read') != grant:
                        raise NotFound()
                    self._audit(principal, operation, scope, 'REPLAYED', request_id, surface)
                    return self._pack(data)
                current = self.campaigns.get(reference, binding['id'])
                if operation == 'campaign.start':
                    if body['approved_plan_sha256'] != current['plan_sha256']:
                        raise CampaignConflict('Acknowledgement does not match the saved plan')
                    if current['state'] not in ('DRAFT', 'PAUSED', 'RUNNING'):
                        raise CampaignConflict('Campaign cannot start in its current state')
                elif operation == 'campaign.pause' and current['state'] not in ('RUNNING', 'PAUSED'):
                    raise CampaignConflict('Campaign cannot pause in its current state')
                if operation == 'campaign.cancel' and current['state'] in (
                        'COMPLETED', 'CANCELLED', 'NEEDS_REVIEW', 'CANCELLING'):
                    if self._campaign_grant(principal, scope, 'campaign_read') != grant:
                        raise NotFound()
                    self._audit(principal, operation, scope, 'ALLOWED', request_id, surface)
                    return self._pack(self._view(reference, binding))
                # A persisted intent prevents a lost response or delayed retry
                # from re-starting a campaign after the user has paused it.
                self._record_command(principal, operation, scope, body)
                if operation == 'campaign.start':
                    if current['state'] == 'RUNNING':
                        # A retry cannot silently renew an earlier execution lease.
                        data = self._view(reference, binding)
                    else:
                        if current['state'] not in ('DRAFT', 'PAUSED'):
                            raise CampaignConflict('Campaign cannot start in its current state')
                        active = self.engine.store._conn.execute('''SELECT COUNT(*) FROM service_campaigns s
                            JOIN research_campaigns c ON c.id=s.id
                            WHERE json_extract(c.checkpoint,'$.state') IN ('RUNNING','PAUSED','CANCELLING')''').fetchone()[0]
                        if current['state'] == 'DRAFT' and active >= self.MAX_ACTIVE_CAMPAIGNS:
                            raise CampaignConflict('Active campaign limit reached')
                        # Persist authority first; a crash before start leaves a
                        # draft/paused plan that still requires an explicit start.
                        with self.engine.store._conn:
                            self.engine.store._conn.execute('''UPDATE service_campaigns
                                SET runner_subject=?,token_id=?,expires=? WHERE id=?''',
                                (principal.subject, principal.token_id, principal.expires, binding['id']))
                        data = self.campaigns.start(reference, binding['id'],
                            approved_plan_sha256=body['approved_plan_sha256'])
                        data['authorization_expires_at'] = principal.expires
                elif operation == 'campaign.pause':
                    if current['state'] == 'PAUSED':
                        data = current
                    elif current['state'] != 'RUNNING':
                        raise CampaignConflict('Campaign cannot pause in its current state')
                    else:
                        data = self.campaigns.pause(reference, binding['id'])
                else:
                    data = self.campaigns.cancel(reference, binding['id'])
                with self.engine.store._conn:
                    self.engine.store._conn.execute('''UPDATE service_campaign_commands SET status='APPLIED'
                        WHERE actor=? AND request_id=?''', (principal.subject, body['request_id']))
                data = self._view(reference, self._binding(scope))
            if self._campaign_grant(principal, scope, 'campaign_read') != grant:
                raise NotFound()
            output = self._pack(data)
            self._audit(principal, operation, scope, 'ALLOWED', request_id, surface)
            return output
        except (CampaignConflict, ValueError, TypeError, KeyError) as exc:
            self._audit(principal, operation, scope, 'REJECTED', request_id, surface)
            if isinstance(exc, CampaignConflict):
                raise
            raise ValueError('Invalid campaign request') from exc
        except NotFound:
            self._audit(principal, operation, scope, 'DENIED', request_id, surface)
            raise
        except Exception as exc:
            self._audit(principal, operation, scope, 'UNAVAILABLE', request_id, surface)
            raise Unavailable() from exc

    def _command_fingerprint(self, operation, scope, body):
        if not isinstance(body.get('request_id'), str) or str(uuid.UUID(body['request_id'])) != body['request_id']:
            raise ValueError('A canonical UUID command request ID is required')
        return hashlib.sha256(encoded([operation, scope, body]).encode()).hexdigest()

    def _command_replay(self, principal, operation, scope, body):
        fingerprint = self._command_fingerprint(operation, scope, body)
        previous = self.engine.store._conn.execute('''SELECT * FROM service_campaign_commands
            WHERE actor=? AND request_id=?''', (principal.subject, body['request_id'])).fetchone()
        if previous is None:
            return False
        if previous['fingerprint'] != fingerprint or previous['status'] != 'APPLIED':
            raise CampaignConflict('Changed command or interrupted command requires review')
        return True

    def _record_command(self, principal, operation, scope, body):
        conn = self.engine.store._conn
        if operation != 'campaign.cancel' and conn.execute(
                'SELECT COUNT(*) FROM service_campaign_commands WHERE campaign_id=?',
                (scope['campaign_id'],)).fetchone()[0] >= 100:
            raise CampaignConflict('Campaign command limit reached')
        with conn:
            conn.execute('INSERT INTO service_campaign_commands VALUES (?,?,?,?,?)',
                (principal.subject, body['request_id'], scope['campaign_id'],
                 self._command_fingerprint(operation, scope, body), 'INTENT'))

    def _safe_tick(self):
        if self._faulted:
            return
        try:
            self._tick()
        except Exception:
            # Corrupt persisted metadata must not silently kill the scheduler
            # while leaving children running. Refuse further writes until restart.
            self._faulted = True
            for job_id, handle in list(self.engine._processes.items()):
                try:
                    row = self.engine.store._conn.execute('SELECT * FROM application_jobs WHERE id=?', (job_id,)).fetchone()
                    reference = ExperimentRef(instance_id=self.engine.instance_id,
                        project_id=row['project_id'], experiment_id=row['experiment_id'])
                    self.engine.cancel_job(reference, job_id)
                    handle['process'].wait(timeout=5)
                    self.engine.job(reference, job_id)
                except Exception:
                    if handle['process'].poll() is None:
                        handle['process'].kill()
                    handle['process'].wait(timeout=5)
                    handle['output'].close()
                    self.engine._processes.pop(job_id, None)
                    self.engine.settings.release(job_id)

    def _tick(self):
        self.engine._check()
        rows = self.engine.store._conn.execute('''SELECT s.* FROM service_campaigns s
            JOIN research_campaigns c ON c.id=s.id
            WHERE json_extract(c.checkpoint,'$.state') IN ('RUNNING','PAUSED','CANCELLING')
            ORDER BY s.rowid LIMIT ?''', (self.MAX_ACTIVE_CAMPAIGNS,)).fetchall()
        for binding in rows:
            scope = {'instance_id': self.engine.instance_id, 'project_id': binding['project_id'],
                'experiment_id': binding['experiment_id'], 'campaign_id': binding['id']}
            reference = ExperimentRef(**select(scope, 'instance_id', 'project_id', 'experiment_id'))
            principal = Principal(binding['runner_subject'], binding['token_id'], binding['expires'] or 0)
            try:
                grant = self._campaign_grant(principal, scope, 'campaign_run', execute=True)
                if grant.tenant_id != binding['tenant_id']:
                    raise NotFound()
                current = self.campaigns.get(reference, binding['id'])
                # Even a paused campaign may have a lost submission pointer.
                # Audit before reconciliation/polling can commit any result.
                tick_id = str(uuid.uuid4())
                self._audit(principal, 'campaign.advance', scope, 'INTENT', tick_id, 'service')
                updated = self.campaigns.advance(reference, binding['id'])
                if updated != current:
                    self._audit(principal, 'campaign.advance', scope, 'ALLOWED', tick_id, 'service')
            except Exception:
                # Safety cancellation does not depend on a working policy/audit.
                # A subsequent tick continues reaping the cancelled worker.
                try:
                    self.campaigns.stop_for_review(reference, binding['id'], 'AUTHORIZATION_UNAVAILABLE')
                    self.campaigns.advance(reference, binding['id'])
                    try:
                        self._audit(principal, 'campaign.stopped', scope, 'REVIEW_REQUIRED', str(uuid.uuid4()), 'service')
                    except Unavailable:
                        pass
                except Exception:
                    # The outer safety handler reaps all children and fails closed.
                    raise

    def _results(self, reference, campaign):
        observations = {o['observation_id']: o for o in self.engine.observations(reference)}
        results = []
        for observation_id in campaign['observations']:
            observation = observations.get(observation_id)
            if not observation or observation['epistemic_state'] != 'SIMULATED':
                raise ValueError('Campaign result is not a scoped simulated observation')
            result = self.engine.result(reference, observation_id)
            states, treated, control, _ = simulation_arrays(result)
            summaries = []
            for index, state in enumerate(states):
                summaries.append({'state': state['label'], 'units': state['units'],
                    'treated': dict(zip(('p05', 'median', 'p95'), np.quantile(treated[:, index], [.05, .5, .95]).tolist())),
                    'control': dict(zip(('p05', 'median', 'p95'), np.quantile(control[:, index], [.05, .5, .95]).tolist()))})
            results.append({**select(result, 'id', 'model_id', 'model_version', 'model_label',
                'epistemic_state', 'config', 'parameter_epistemic_state', 'numerical_check', 'limitations'),
                'observation_id': observation_id, 'artifact_sha256': observation['artifact_sha256'],
                'summary': summaries})
        return {'format': 'virtuallab-service-campaign-results-v1', 'reference': reference.model_dump(),
            'campaign_id': campaign['id'], 'plan_sha256': campaign['plan_sha256'], 'state': campaign['state'],
            'epistemic_state': 'SIMULATED', 'results': results,
            'verification_scope': 'Hashes verify saved software artifacts; numerical checks do not validate biological predictions.'}
